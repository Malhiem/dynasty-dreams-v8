"""Site-admin endpoints — extracted from server.py (iter 115).

Endpoints:
    POST /api/admin/snapshot-ownership — manually trigger an ownership snapshot
    GET  /api/admin/health-deep        — per-route latency + error rates +
                                         DB / worker liveness (iter 116)
"""
from __future__ import annotations

import asyncio
import os
import time

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel
from typing import Optional
from bson import ObjectId

from metrics import snapshot as _metrics_snapshot


router = APIRouter()
_deps: dict = {}


def setup(deps: dict) -> None:
    _deps.update(deps)


def _db(): return _deps["db"]
async def _get_user(request): return await _deps["get_current_user"](request)


def _is_site_admin(user: dict) -> bool:
    admin_email = os.environ.get("ADMIN_EMAIL", "admin@dynastydreams.com")
    return user.get("email") == admin_email


@router.post("/admin/snapshot-ownership")
async def admin_snapshot_ownership(request: Request):
    """Site-admin trigger to capture an ownership snapshot RIGHT NOW.

    Useful when site operators want the % Change column to populate before
    the natural 24h tick fires. Auth: only the user with email ==
    ADMIN_EMAIL can call this.
    """
    user = await _get_user(request)
    if not _is_site_admin(user):
        raise HTTPException(status_code=403, detail="Site admin only")
    from ownership_snapshot_worker import snapshot_once
    return await snapshot_once(_db())


@router.get("/admin/health-deep")
async def admin_health_deep(
    request: Request,
    top: int = Query(25, ge=1, le=200, description="Limit routes returned (slowest first by p95)"),
):
    """Deep health probe surfacing per-route latency + error rates so the
    admin page can spot which endpoint is dragging before users feel it.

    Returns
    -------
    {
      "ok": bool,                # all probes green
      "checked_at": ISO,
      "service": {
        "started_at": ISO,
        "uptime_seconds": float,
        "total_requests": int,
        "total_errors": int,
        "error_rate_pct": float,
      },
      "database": {
        "alive": bool,
        "ping_ms": float|None,
        "error": str|None,
      },
      "workers": {
        "live_scoring": bool,
        "ownership_snapshot": bool,
        "tbd_deadline": bool,
      },
      "routes": [ {method, route, count, error_count, error_rate_pct,
                   avg_latency_ms, p50_latency_ms, p95_latency_ms,
                   max_latency_ms, last_status, last_seen_at}, ... ]
    }

    Auth: site admin only.
    """
    user = await _get_user(request)
    if not _is_site_admin(user):
        raise HTTPException(status_code=403, detail="Site admin only")

    # ── DB liveness: motor admin.command("ping") with a short timeout ──
    db_info: dict = {"alive": False, "ping_ms": None, "error": None}
    try:
        t0 = time.perf_counter()
        await asyncio.wait_for(_db().command("ping"), timeout=2.0)
        db_info["alive"] = True
        db_info["ping_ms"] = round((time.perf_counter() - t0) * 1000.0, 2)
    except Exception as e:
        db_info["error"] = str(e)

    # ── Background worker liveness (set in server.py startup hook) ──
    fastapi_state = request.app.state
    workers = {
        "live_scoring": _task_alive(getattr(fastapi_state, "live_scoring_task", None)),
        "ownership_snapshot": _task_alive(getattr(fastapi_state, "ownership_snapshot_task", None)),
        "tbd_deadline": _task_alive(getattr(fastapi_state, "tbd_deadline_task", None)),
    }

    snap = _metrics_snapshot(top_n=top)
    ok = db_info["alive"] and all(workers.values())

    return {
        "ok": ok,
        "checked_at": _now_iso(),
        "service": {
            "started_at": snap["started_at"],
            "uptime_seconds": snap["uptime_seconds"],
            "total_requests": snap["total_requests"],
            "total_errors": snap["total_errors"],
            "error_rate_pct": snap["error_rate_pct"],
        },
        "database": db_info,
        "workers": workers,
        "routes": snap["routes"],
    }


# ─── Helpers ─────────────────────────────────────────────────────────


def _task_alive(task) -> bool:
    """An asyncio task is 'alive' if it exists and isn't done/cancelled."""
    if task is None:
        return False
    try:
        return not task.done()
    except Exception:
        return False


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


# ─── Iter 149 — Trade fixture seed helper ────────────────────────────
# Used by QA / testing-agent runs to exercise the Draft Room "Trades" tab
# (vote + force-approve + force-veto) without manually proposing trades
# through the UI. Creates ONE pending + ONE vetoed + ONE processed trade
# for the given league using the first two teams + a sampled player on
# each side. Site-admin only.

class SeedPendingTradeInput(BaseModel):
    league_id: str
    proposer_team_id: Optional[str] = None
    target_team_id: Optional[str] = None
    proposer_player_id: Optional[str] = None
    target_player_id: Optional[str] = None
    # If true, also seed a `vetoed` and an `executed` (processed) trade so
    # the Draft Room chat can display all three terminal stamps at once.
    seed_terminal_fixtures: bool = True


@router.post("/admin/seed/pending-trade")
async def admin_seed_pending_trade(body: SeedPendingTradeInput, request: Request):
    """Create demo trade fixtures so the Draft Room ✓/✗ vote UI is
    exercisable end-to-end. Returns the created trade IDs grouped by status.

    The seed is idempotent-ish: it does NOT dedupe existing trades, so
    each call adds a fresh batch. Wipe via direct Mongo if regression
    state needs to be clean.
    """
    from datetime import datetime, timezone
    user = await _get_user(request)
    if not _is_site_admin(user):
        raise HTTPException(status_code=403, detail="Site admin only")
    db = _db()

    league = await db.leagues.find_one({"_id": ObjectId(body.league_id)})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")

    teams = await db.teams.find({"league_id": body.league_id}).to_list(50)
    if len(teams) < 2:
        raise HTTPException(status_code=400, detail="League needs at least 2 teams to seed a trade")

    def _team(team_id):
        if not team_id:
            return None
        for t in teams:
            if str(t["_id"]) == str(team_id):
                return t
        return None

    proposer = _team(body.proposer_team_id) or teams[0]
    target = _team(body.target_team_id) or next((t for t in teams if str(t["_id"]) != str(proposer["_id"])), None)
    if not target:
        raise HTTPException(status_code=400, detail="Could not resolve target team")

    async def _pick_player(team_doc, override_id):
        if override_id:
            p = await db.players.find_one({"_id": ObjectId(override_id)})
            if p:
                return p
        # Fall back to any roster player owned by the team
        roster = await db.rosters.find_one({"team_id": str(team_doc["_id"])})
        pids = (roster or {}).get("players") or []
        for pid in pids:
            try:
                p = await db.players.find_one({"_id": ObjectId(pid)})
            except Exception:
                p = await db.players.find_one({"_id": pid})
            if p:
                return p
        # Last resort — any player in the league's pool
        return await db.players.find_one({})

    proposer_player = await _pick_player(proposer, body.proposer_player_id)
    target_player = await _pick_player(target, body.target_player_id)
    if not proposer_player or not target_player:
        raise HTTPException(status_code=400, detail="Could not resolve seed players")

    def _asset(player):
        return {
            "asset_type": "player",
            "player_id": str(player["_id"]),
            "player_name": player.get("name") or "Player",
            "position": player.get("position") or player.get("primary_position"),
            "nhl_team": player.get("nhl_team"),
            "salary_retained_pct": 0,
        }

    def _trade_doc(status: str, processed: bool = False):
        now = datetime.now(timezone.utc).isoformat()
        doc = {
            "league_id": body.league_id,
            "proposer_id": proposer.get("owner_id"),
            "proposer_team_id": str(proposer["_id"]),
            "proposer_team_name": proposer.get("name") or "Proposer",
            "target_owner_id": target.get("owner_id"),
            "target_team_id": str(target["_id"]),
            "target_team_name": target.get("name") or "Target",
            "proposer_assets": [_asset(proposer_player)],
            "target_assets": [_asset(target_player)],
            "status": status,
            "submitted_at": now,
            "votes": {"approve": 0, "veto": 0, "choices": {}, "voters": []},
            "_seed": "iter149_draftchat",
        }
        if processed:
            doc["processed_at"] = now
            doc["responded_at"] = now
        return doc

    created = {}
    pending_doc = _trade_doc("pending")
    pending_res = await db.trades.insert_one(pending_doc)
    created["pending"] = str(pending_res.inserted_id)

    if body.seed_terminal_fixtures:
        vetoed_res = await db.trades.insert_one(_trade_doc("vetoed", processed=True))
        executed_res = await db.trades.insert_one(_trade_doc("executed", processed=True))
        created["vetoed"] = str(vetoed_res.inserted_id)
        created["executed"] = str(executed_res.inserted_id)

    return {
        "league_id": body.league_id,
        "proposer_team": proposer.get("name"),
        "target_team": target.get("name"),
        "trades": created,
    }

