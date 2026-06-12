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


# ─── Iter 163 — Trade verification harness ───────────────────────────
# Three site-admin endpoints that together let us reset, seed and
# exercise every trade-workflow path end-to-end:
#
#   1) POST /admin/trades/clear?league_id=X
#        Wipes all trades for the league AND resets every draft pick's
#        `current_team_id` back to its `original_team_id` (so pick
#        ownership starts clean for the next seed run).
#
#   2) POST /admin/seed/draft-picks?league_id=X&year=YYYY&rounds=N
#        Materialises `rounds × len(teams)` draft picks under
#        db.draft_picks. Idempotent — only inserts the (league, year,
#        round, original_team_id) combos that don't already exist.
#
#   3) POST /admin/seed/trade-scenarios?league_id=X
#        Creates a fresh set of trades covering the 4 workflow paths
#        the user wants to verify (timer auto-approval, commissioner
#        veto, league veto, party-cancel) plus a fifth pick-only trade
#        that chains pick ownership through three teams.


@router.post("/admin/trades/clear")
async def admin_clear_trades(league_id: str = Query(...), request: Request = None):
    """Reset trade & pick-ownership state for a league.

    - Deletes every `trades` document for the league.
    - Resets every `draft_picks.current_team_id` back to `original_team_id`
      (and clears `trade_history`).
    """
    user = await _get_user(request)
    if not _is_site_admin(user):
        raise HTTPException(status_code=403, detail="Site admin only")
    db = _db()
    trades_res = await db.trades.delete_many({"league_id": league_id})
    # Reset every draft pick to its original owner
    picks_res = await db.draft_picks.update_many(
        {"league_id": league_id},
        [{"$set": {
            "current_team_id": "$original_team_id",
            "current_team_name": "$original_team_name",
            "trade_history": [],
        }}],
    )
    return {
        "league_id": league_id,
        "trades_deleted": trades_res.deleted_count,
        "picks_reset": picks_res.modified_count,
    }


@router.post("/admin/seed/draft-picks")
async def admin_seed_draft_picks(
    league_id: str = Query(...),
    year: int = Query(2026, ge=2020, le=2040),
    rounds: int = Query(5, ge=1, le=10),
    request: Request = None,
):
    """Materialise N rounds × team-count draft picks for the league.

    Idempotent on (league_id, year, round, original_team_id) — skips
    rows that already exist so the endpoint can be re-run safely.
    """
    from datetime import datetime, timezone
    user = await _get_user(request)
    if not _is_site_admin(user):
        raise HTTPException(status_code=403, detail="Site admin only")
    db = _db()
    league = await db.leagues.find_one({"_id": ObjectId(league_id)})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    teams = await db.teams.find({"league_id": league_id}).to_list(200)
    if not teams:
        raise HTTPException(status_code=400, detail="League has no teams")

    inserted = 0
    skipped = 0
    now = datetime.now(timezone.utc)
    for r in range(1, rounds + 1):
        for slot, team in enumerate(teams, start=1):
            tid = str(team["_id"])
            tname = team.get("name", "Unknown")
            existing = await db.draft_picks.find_one({
                "league_id": league_id,
                "year": year,
                "round": r,
                "original_team_id": tid,
            })
            if existing:
                skipped += 1
                continue
            await db.draft_picks.insert_one({
                "league_id": league_id,
                "year": year,
                "round": r,
                "slot": slot,
                "overall": (r - 1) * len(teams) + slot,
                "original_team_id": tid,
                "original_team_name": tname,
                "current_team_id": tid,
                "current_team_name": tname,
                "trade_history": [],
                "created_at": now,
            })
            inserted += 1
    return {
        "league_id": league_id,
        "year": year,
        "rounds": rounds,
        "teams": len(teams),
        "inserted": inserted,
        "skipped": skipped,
    }


@router.post("/admin/seed/trade-scenarios")
async def admin_seed_trade_scenarios(league_id: str = Query(...), request: Request = None):
    """Create five real trades covering every workflow the commissioner
    wants to verify. Caller should `POST /admin/trades/clear` first.

    Returns the trade IDs grouped by scenario name.
    """
    from datetime import datetime, timedelta, timezone
    user = await _get_user(request)
    if not _is_site_admin(user):
        raise HTTPException(status_code=403, detail="Site admin only")
    db = _db()
    league = await db.leagues.find_one({"_id": ObjectId(league_id)})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    teams = await db.teams.find({"league_id": league_id}).to_list(200)
    if len(teams) < 4:
        raise HTTPException(status_code=400, detail="Need ≥ 4 teams for full scenario set")

    a, b, c, d = teams[0], teams[1], teams[2], teams[3]

    async def _first_roster_player(team):
        for pid in team.get("roster", []) or []:
            try:
                p = await db.players.find_one({"_id": ObjectId(pid)})
                if p:
                    return p
            except Exception:
                continue
        return None

    async def _team_pick(team_id: str, year: int = 2026, round_: int = 1):
        return await db.draft_picks.find_one({
            "league_id": league_id,
            "year": year,
            "round": round_,
            "current_team_id": team_id,
        })

    def _player_asset(p):
        return {
            "asset_type": "player",
            "player_id": str(p["_id"]),
            "player_name": p.get("name") or "Player",
            "position": p.get("position") or p.get("primary_position"),
            "nhl_team": p.get("nhl_team"),
            "salary_retained_pct": 0,
        }

    def _pick_asset(pick):
        return {
            "asset_type": "pick",
            "pick_id": str(pick["_id"]),
            "pick_year": pick["year"],
            "pick_round": pick["round"],
            "from_team_id": pick["current_team_id"],
            "from_team_name": pick["current_team_name"],
        }

    now = datetime.now(timezone.utc)
    past = now - timedelta(hours=1)
    future = now + timedelta(hours=24)

    async def _create_trade(*, scenario, proposer, target, offered, requested,
                             status="pending", processes_at=None, votes=None,
                             responded=False):
        doc = {
            "league_id": league_id,
            "proposer_id": proposer.get("owner_id"),
            "proposer_team_id": str(proposer["_id"]),
            "proposer_team_name": proposer.get("name"),
            "target_owner_id": target.get("owner_id"),
            "target_team_id": str(target["_id"]),
            "target_team_name": target.get("name"),
            "assets_offered": offered,
            "assets_requested": requested,
            "status": status,
            "submitted_at": now.isoformat(),
            "processes_at": (processes_at or future).isoformat(),
            "votes": votes or {"approve": 0, "veto": 0, "choices": {}, "voters": []},
            "_seed_scenario": scenario,
        }
        if responded:
            doc["responded_at"] = now.isoformat()
        res = await db.trades.insert_one(doc)
        return str(res.inserted_id)

    created = {}

    # Scenario 1 — Timer auto-approval
    # A → B trades a player + 2026 R1 pick. processes_at is in the past
    # so calling /execute will immediately settle it.
    a_player = await _first_roster_player(a)
    b_player = await _first_roster_player(b)
    a_pick = await _team_pick(str(a["_id"]))
    if a_player and b_player and a_pick:
        created["timer_auto_approve"] = await _create_trade(
            scenario="timer_auto_approve",
            proposer=a, target=b,
            offered=[_player_asset(a_player), _pick_asset(a_pick)],
            requested=[_player_asset(b_player)],
            processes_at=past,
            responded=True,  # both parties already accepted
        )

    # Scenario 2 — Commissioner approval / force-veto path
    # A → C player swap; left pending so commish can /vote veto.
    c_player = await _first_roster_player(c)
    if a_player and c_player:
        # Need a different player for proposer this time
        a_roster = list(a.get("roster", []) or [])
        a_player_2 = None
        for pid in a_roster[1:]:
            try:
                a_player_2 = await db.players.find_one({"_id": ObjectId(pid)})
                if a_player_2 and str(a_player_2["_id"]) != str(a_player["_id"]):
                    break
            except Exception:
                continue
        if a_player_2:
            created["commissioner_veto"] = await _create_trade(
                scenario="commissioner_veto",
                proposer=a, target=c,
                offered=[_player_asset(a_player_2)],
                requested=[_player_asset(c_player)],
            )

    # Scenario 3 — League veto via votes (threshold)
    # B → D player + pick for player.
    d_player = await _first_roster_player(d)
    b_pick = await _team_pick(str(b["_id"]), round_=2)
    if b_player and d_player and b_pick:
        created["league_veto"] = await _create_trade(
            scenario="league_veto",
            proposer=b, target=d,
            offered=[_player_asset(b_player), _pick_asset(b_pick)],
            requested=[_player_asset(d_player)],
        )

    # Scenario 4 — Both parties accept, then withdraw (cancel)
    # C → A pick-only trade, both accepted (responded=true), still
    # pre-execute so it can be withdrawn before settle.
    c_pick = await _team_pick(str(c["_id"]))
    if c_pick and a_pick:
        # a_pick is already used above — pull a different one
        a_pick_2 = await _team_pick(str(a["_id"]), round_=3)
        if a_pick_2:
            created["party_cancel"] = await _create_trade(
                scenario="party_cancel",
                proposer=c, target=a,
                offered=[_pick_asset(c_pick)],
                requested=[_pick_asset(a_pick_2)],
                responded=True,
            )

    # Scenario 5 — Pick-only chain (B trades R4 to D, then D will trade to A)
    # Phase 1 here; phase 2 is created post-execute by the test.
    b_pick_4 = await _team_pick(str(b["_id"]), round_=4)
    if b_pick_4:
        created["pick_chain_phase1"] = await _create_trade(
            scenario="pick_chain_phase1",
            proposer=b, target=d,
            offered=[_pick_asset(b_pick_4)],
            requested=[],
            processes_at=past,
            responded=True,
        )

    return {
        "league_id": league_id,
        "scenarios_created": created,
        "teams": {"A": a.get("name"), "B": b.get("name"), "C": c.get("name"), "D": d.get("name")},
    }


