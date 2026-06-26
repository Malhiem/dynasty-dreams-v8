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
from pydantic import BaseModel, Field
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



# ─── Iter 228e — Archived drafts admin UI ──────────────────────


@router.get("/admin/drafts/archived")
async def admin_list_archived_drafts(request: Request):
    """Returns every soft-deleted draft across the platform, sorted by
    `archived_at` DESC, with `days_until_purge` computed against the
    15-day TTL. Site-admin only.
    """
    user = await _get_user(request)
    if not _is_site_admin(user):
        raise HTTPException(status_code=403, detail="Site admin only")

    from datetime import datetime as _dt, timezone as _tz, timedelta as _td

    drafts = await _db().drafts.find(
        {"status": "archived"},
        {"team_map": 0, "picks": 0, "chat_messages": 0},
    ).sort("archived_at", -1).to_list(500)

    now = _dt.now(_tz.utc)
    out = []
    for d in drafts:
        archived_iso = d.get("archived_at")
        days_left = None
        try:
            if archived_iso:
                arch_dt = _dt.fromisoformat(str(archived_iso).replace("Z", "+00:00"))
                days_left = max(0, 15 - int((now - arch_dt).total_seconds() // 86400))
        except Exception:
            pass
        out.append({
            "id": str(d["_id"]),
            "name": d.get("name") or "Untitled Draft",
            "league_id": d.get("league_id"),
            "league_name": d.get("league_name"),
            "draft_type": d.get("draft_type"),
            "total_rounds": d.get("total_rounds"),
            "scheduled_time": d.get("scheduled_time"),
            "archived_at": archived_iso,
            "archived_by": d.get("archived_by"),
            "days_until_purge": days_left,
        })
    return {"drafts": out, "count": len(out)}


@router.post("/admin/drafts/{draft_id}/purge")
async def admin_purge_draft(draft_id: str, request: Request):
    """Permanently delete an archived draft (bypasses the 15-day TTL).
    Site-admin only. Refuses to purge a non-archived draft.

    Iter 228f — writes an `admin_user_actions` audit row so compliance
    can demonstrate the deletion was traceable (admin id, timestamp,
    pre-purge draft snapshot).
    """
    user = await _get_user(request)
    if not _is_site_admin(user):
        raise HTTPException(status_code=403, detail="Site admin only")
    try:
        draft = await _db().drafts.find_one({"_id": ObjectId(draft_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid draft_id")
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    if draft.get("status") != "archived":
        raise HTTPException(
            status_code=400,
            detail="Only archived drafts can be purged. Soft-delete first via DELETE /api/drafts/{id}.",
        )
    league = None
    try:
        league = await _db().leagues.find_one({"_id": ObjectId(draft.get("league_id"))})
    except Exception:
        pass

    # Audit BEFORE delete so the row references the live draft snapshot.
    from datetime import datetime as _dt, timezone as _tz
    await _db().admin_user_actions.insert_one({
        "admin_id": str(user.get("_id")),
        "admin_email": user.get("email"),
        "admin_tier": user.get("permission_tier") or user.get("role") or "admin",
        "target_user_id": (league or {}).get("commissioner_id"),
        "action": "draft_purge",
        "reason": "Admin permanent purge of archived draft (bypasses 15-day TTL)",
        "metadata": {
            "draft_id": draft_id,
            "draft_name": draft.get("name"),
            "league_id": draft.get("league_id"),
            "league_name": draft.get("league_name"),
            "archived_at": draft.get("archived_at"),
            "archived_by": draft.get("archived_by"),
            "total_rounds": draft.get("total_rounds"),
            "scheduled_time": draft.get("scheduled_time"),
        },
        "prior_state": {"status": draft.get("status")},
        "mocked": False,
        "ts": _dt.now(_tz.utc).isoformat(),
    })

    await _db().drafts.delete_one({"_id": ObjectId(draft_id)})
    return {"draft_id": draft_id, "status": "purged"}


@router.post("/admin/drafts/{draft_id}/restore")
async def admin_restore_archived_draft(draft_id: str, request: Request):
    """Site-admin shortcut to restore an archived draft.

    Iter 228f — writes an `admin_user_actions` audit row so the restore
    appears in the recent-admin-actions feed.
    """
    user = await _get_user(request)
    if not _is_site_admin(user):
        raise HTTPException(status_code=403, detail="Site admin only")
    try:
        draft = await _db().drafts.find_one({"_id": ObjectId(draft_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid draft_id")
    if not draft:
        raise HTTPException(status_code=404, detail="Archived draft not found")
    if draft.get("status") != "archived":
        raise HTTPException(status_code=404, detail="Archived draft not found")
    league = None
    try:
        league = await _db().leagues.find_one({"_id": ObjectId(draft.get("league_id"))})
    except Exception:
        pass

    res = await _db().drafts.update_one(
        {"_id": ObjectId(draft_id), "status": "archived"},
        {"$set": {"status": "scheduled"},
         "$unset": {"archived_at": "", "archived_by": ""}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Archived draft not found")

    from datetime import datetime as _dt, timezone as _tz
    await _db().admin_user_actions.insert_one({
        "admin_id": str(user.get("_id")),
        "admin_email": user.get("email"),
        "admin_tier": user.get("permission_tier") or user.get("role") or "admin",
        "target_user_id": (league or {}).get("commissioner_id"),
        "action": "draft_restore",
        "reason": "Admin restored archived draft to scheduled status",
        "metadata": {
            "draft_id": draft_id,
            "draft_name": draft.get("name"),
            "league_id": draft.get("league_id"),
            "league_name": draft.get("league_name"),
        },
        "prior_state": {
            "status": "archived",
            "archived_at": draft.get("archived_at"),
        },
        "mocked": False,
        "ts": _dt.now(_tz.utc).isoformat(),
    })
    return {"draft_id": draft_id, "status": "scheduled"}


@router.get("/admin/drafts/{draft_id}/audit")
async def admin_draft_audit_log(draft_id: str, request: Request):
    """Iter 228l — Return the audit-log timeline for a specific draft.

    Surfaces every `admin_user_actions` row whose `metadata.draft_id`
    matches, regardless of which actor triggered it. Used by the
    Admin → Archived Drafts panel's "History" drawer so compliance can
    inspect the full lifecycle (commissioner archive → admin purge /
    restore / auto-purge) without leaving the page.
    """
    user = await _get_user(request)
    if not _is_site_admin(user):
        raise HTTPException(status_code=403, detail="Site admin only")

    rows = await _db().admin_user_actions.find({
        "metadata.draft_id": draft_id,
        "action": {"$in": [
            "draft_archive", "draft_restore", "draft_purge", "draft_auto_purge",
        ]},
    }).sort("ts", -1).to_list(200)

    entries = []
    for r in rows:
        entries.append({
            "id": str(r.get("_id")),
            "action": r.get("action"),
            "admin_id": r.get("admin_id"),
            "admin_email": r.get("admin_email"),
            "admin_tier": r.get("admin_tier"),
            "reason": r.get("reason"),
            "metadata": r.get("metadata") or {},
            "prior_state": r.get("prior_state") or {},
            "ts": r.get("ts"),
        })
    return {"draft_id": draft_id, "entries": entries, "count": len(entries)}


# ─── Iter 228e — Player roster verification UI ─────────────────


@router.get("/admin/players/verify")
async def admin_verify_players(
    request: Request,
    search: Optional[str] = None,
    league_status: Optional[str] = None,  # "NHL" | "AHL" | "Europe" | "Junior" | "Draft Eligible" | "Retired"
    position: Optional[str] = None,
    nhl_team: Optional[str] = None,
    limit: int = Query(default=100, ge=1, le=500),
    page: int = Query(default=1, ge=1),
):
    """Site-admin player browse / verify endpoint.

    Returns the platform-wide player pool with the new `league_status`
    field highlighted so an admin can quickly verify whether a player
    is already on file before manually inserting a new one. Filters
    mirror the public `/api/players` endpoint plus `league_status`.
    """
    user = await _get_user(request)
    if not _is_site_admin(user):
        raise HTTPException(status_code=403, detail="Site admin only")

    query: dict = {}
    if search:
        query["$or"] = [
            {"name": {"$regex": search, "$options": "i"}},
            {"team": {"$regex": search, "$options": "i"}},
        ]
    if nhl_team:
        # Iter 228e — match team regardless of case so the UI doesn't have
        # to upper-case before passing the filter (admin_create_player
        # stores team uppercased).
        query["team"] = {"$regex": f"^{nhl_team}$", "$options": "i"}
    if position:
        query["position"] = position.upper()
    if league_status:
        # Backward-compatible default: NHL when missing
        if league_status.upper() == "NHL":
            query["$or"] = (query.get("$or") or []) + [
                {"league_status": {"$exists": False}},
                {"league_status": "NHL"},
                {"league_status": None},
            ]
        else:
            query["league_status"] = league_status

    total = await _db().players.count_documents(query)
    skip = (page - 1) * limit
    docs = await _db().players.find(
        query, {
            "name": 1, "team": 1, "position": 1, "primary_position": 1,
            "jersey_number": 1, "nhl_id": 1, "player_type": 1,
            "league_status": 1, "injury_status": 1, "date_of_birth": 1,
            "minors_eligible": 1, "source": 1, "draft_year": 1,
            "draft_rank_final": 1,
        }
    ).sort("name", 1).skip(skip).limit(limit).to_list(limit)
    for p in docs:
        p["id"] = str(p["_id"])
        del p["_id"]
        # Default visible status when missing
        if not p.get("league_status"):
            p["league_status"] = "NHL"
    return {
        "players": docs,
        "page": page,
        "limit": limit,
        "total": total,
        "pages": (total + limit - 1) // limit,
    }


class AdminCreatePlayerRequest(BaseModel):
    name: str
    position: str
    team: Optional[str] = None
    jersey_number: Optional[int] = None
    league_status: str = "NHL"  # NHL/AHL/Europe/Junior/Draft Eligible/Retired
    player_type: str = "skater"
    date_of_birth: Optional[str] = None
    notes: Optional[str] = None


@router.post("/admin/players")
async def admin_create_player(req: AdminCreatePlayerRequest, request: Request):
    """Admin shortcut to add a new player record (e.g. a European/AHL/Junior
    prospect missing from the NHL feed). Generates a synthetic nhl_id in the
    9-digit reserved range so the upstream sync never collides."""
    user = await _get_user(request)
    if not _is_site_admin(user):
        raise HTTPException(status_code=403, detail="Site admin only")

    from datetime import datetime as _dt, timezone as _tz
    import secrets

    if not req.name.strip():
        raise HTTPException(status_code=400, detail="name is required")

    # Synthetic nhl_id in 9xx,xxx,xxx range (reserved for admin-created)
    synth_id = 900_000_000 + secrets.randbelow(99_999_999)

    doc = {
        "name": req.name.strip(),
        "position": req.position.upper(),
        "primary_position": req.position.upper(),
        "team": (req.team or "").upper(),
        "jersey_number": req.jersey_number,
        "league_status": req.league_status,
        "player_type": req.player_type,
        "nhl_id": synth_id,
        "date_of_birth": req.date_of_birth,
        "notes": req.notes,
        "source": "admin_manual",
        "created_at": _dt.now(_tz.utc).isoformat(),
        "created_by": user.get("_id"),
    }
    res = await _db().players.insert_one(doc)
    doc["id"] = str(res.inserted_id)
    del doc["_id"]
    return doc


# ─── Iter 228g — NHL draft-class sync ─────────────────────────


class DraftClassSyncRequest(BaseModel):
    year: int = Field(default=2026, ge=2008, le=2030)
    overwrite: bool = False  # If True, update existing players with the new rankings


@router.post("/admin/players/sync-draft-class")
async def admin_sync_draft_class(req: DraftClassSyncRequest, request: Request):
    """Pulls the public NHL Central Scouting rankings for the given draft
    year across all 4 categories (NA Skater, INT Skater, NA Goalie, INT
    Goalie) and upserts each prospect into the players collection with
    `league_status="Draft Eligible"` + `draft_year=<year>`. Site admin only.

    Endpoint: https://api-web.nhle.com/v1/draft/rankings/{year}/{categoryId}
    """
    user = await _get_user(request)
    if not _is_site_admin(user):
        raise HTTPException(status_code=403, detail="Site admin only")

    import httpx
    import re
    from datetime import datetime as _dt, timezone as _tz

    CATEGORIES = [
        (1, "North American Skater"),
        (2, "International Skater"),
        (3, "North American Goalie"),
        (4, "International Goalie"),
    ]
    added = 0
    updated = 0
    errors: list[str] = []
    seen_ids: list[str] = []

    async with httpx.AsyncClient(timeout=15.0) as client:
        for cat_id, cat_name in CATEGORIES:
            url = f"https://api-web.nhle.com/v1/draft/rankings/{req.year}/{cat_id}"
            try:
                r = await client.get(url)
                if r.status_code != 200:
                    errors.append(f"{cat_name}: HTTP {r.status_code}")
                    continue
                data = r.json()
            except Exception as ex:
                errors.append(f"{cat_name}: {ex}")
                continue

            rankings = data.get("rankings") or []
            for p in rankings:
                first = (p.get("firstName") or "").strip()
                last = (p.get("lastName") or "").strip()
                if not first and not last:
                    continue
                name = f"{first} {last}".strip()
                position = (p.get("positionCode") or "").upper() or ("G" if "Goalie" in cat_name else "C")
                team = p.get("lastAmateurClub") or p.get("lastAmateurLeague") or ""

                # Look for an existing player by name + DOB (best dedup signal)
                query: dict = {"name": {"$regex": f"^{re.escape(name)}$", "$options": "i"}}
                if p.get("birthDate"):
                    query["date_of_birth"] = p.get("birthDate")

                existing = await _db().players.find_one(query)

                doc_set = {
                    "name": name,
                    "position": position,
                    "primary_position": position,
                    "team": team,
                    "league_status": "Draft Eligible",
                    "player_type": "goalie" if "Goalie" in cat_name else "skater",
                    "date_of_birth": p.get("birthDate"),
                    "draft_year": req.year,
                    "draft_category": cat_name,
                    "draft_rank_midterm": p.get("midtermRank"),
                    "draft_rank_final": p.get("finalRank"),
                    "shoots_catches": p.get("shootsCatches"),
                    "height_inches": p.get("heightInInches"),
                    "weight_pounds": p.get("weightInPounds"),
                    "birth_city": p.get("birthCity"),
                    "birth_state": p.get("birthStateProvince"),
                    "birth_country": p.get("birthCountry"),
                    "source": "nhl_central_scouting",
                }
                if existing:
                    if req.overwrite:
                        await _db().players.update_one(
                            {"_id": existing["_id"]}, {"$set": doc_set},
                        )
                        updated += 1
                        seen_ids.append(str(existing["_id"]))
                else:
                    import secrets
                    doc_set["nhl_id"] = 950_000_000 + secrets.randbelow(49_999_999)
                    doc_set["created_at"] = _dt.now(_tz.utc).isoformat()
                    doc_set["created_by"] = user.get("_id")
                    res = await _db().players.insert_one(doc_set)
                    added += 1
                    seen_ids.append(str(res.inserted_id))

    return {
        "year": req.year,
        "added": added,
        "updated": updated,
        "total_processed": added + updated,
        "errors": errors,
        "sample_ids": seen_ids[:5],
    }


# ─── Iter 228h — Bulk CSV player import ─────────────────────────


class BulkImportRow(BaseModel):
    name: str
    position: str
    team: Optional[str] = None
    league_status: str = "NHL"
    date_of_birth: Optional[str] = None
    jersey_number: Optional[int] = None
    notes: Optional[str] = None


class BulkImportRequest(BaseModel):
    rows: list[BulkImportRow]
    skip_duplicates: bool = True


@router.post("/admin/players/bulk-import")
async def admin_bulk_import_players(req: BulkImportRequest, request: Request):
    """Bulk insert player rows (CSV row → object). Frontend parses the
    CSV and POSTs the rows here. Admin only. Returns per-row outcomes
    so the UI can highlight skipped duplicates and errors.
    """
    user = await _get_user(request)
    if not _is_site_admin(user):
        raise HTTPException(status_code=403, detail="Site admin only")

    import secrets
    import re
    from datetime import datetime as _dt, timezone as _tz

    added = 0
    skipped: list[dict] = []
    errors: list[dict] = []
    now = _dt.now(_tz.utc).isoformat()

    for idx, row in enumerate(req.rows):
        if not row.name.strip():
            errors.append({"row": idx + 1, "error": "name is required"})
            continue
        try:
            query: dict = {"name": {"$regex": f"^{re.escape(row.name.strip())}$",
                                     "$options": "i"}}
            if row.date_of_birth:
                query["date_of_birth"] = row.date_of_birth
            if req.skip_duplicates:
                existing = await _db().players.find_one(query)
                if existing:
                    skipped.append({"row": idx + 1, "name": row.name,
                                    "reason": "duplicate"})
                    continue
            await _db().players.insert_one({
                "name": row.name.strip(),
                "position": (row.position or "C").upper(),
                "primary_position": (row.position or "C").upper(),
                "team": (row.team or "").upper(),
                "jersey_number": row.jersey_number,
                "league_status": row.league_status or "NHL",
                "player_type": "goalie" if (row.position or "").upper() == "G" else "skater",
                "date_of_birth": row.date_of_birth,
                "notes": row.notes,
                "source": "admin_bulk_csv",
                "nhl_id": 950_000_000 + secrets.randbelow(49_999_999),
                "created_at": now,
                "created_by": user.get("_id"),
            })
            added += 1
        except Exception as ex:
            errors.append({"row": idx + 1, "name": row.name, "error": str(ex)})

    return {
        "received": len(req.rows),
        "added": added,
        "skipped": skipped,
        "errors": errors,
    }



# ─── Iter 230 — Player status change notification trigger ─────────


class PlayerStatusChangeRequest(BaseModel):
    """Admin endpoint payload — kicks off a fanout to all rostering teams."""
    change_kind: str = Field(
        ...,
        pattern=r"^(injured|recovered|sent_down|called_up|injury_status_changed)$",
        description="Which downstream notification event to emit.",
    )
    detail_message: Optional[str] = Field(
        default=None,
        max_length=240,
        description="Optional human-readable detail appended to the notification body.",
    )
    update_player_doc: bool = Field(
        default=False,
        description=(
            "When True AND change_kind is injury-related, also patch the "
            "player's injury_status on the players collection so the rest "
            "of the app reflects the change."
        ),
    )
    new_injury_status: Optional[str] = Field(
        default=None,
        max_length=64,
        description="Used when update_player_doc=True and change_kind is injury-related.",
    )


@router.post("/admin/players/{player_id}/status-change")
async def admin_trigger_player_status_change(
    player_id: str,
    req: PlayerStatusChangeRequest,
    request: Request,
):
    """Trigger a player status change notification fanout.

    Iter 230 — Single hook the future NHL data ingestion worker will call
    when a real-world status update lands. Today admins can drive it
    manually so the UX surfaces end-to-end without needing the ingestion
    job. Notifies every team currently rostering the player.
    """
    user = await _get_user(request)
    if not _is_site_admin(user):
        raise HTTPException(status_code=403, detail="Site admin only")

    # Optionally write through to the player doc so the rest of the app
    # (rosters, lineup checks, injury widgets) reflects the change.
    if req.update_player_doc and req.new_injury_status is not None:
        try:
            await _db().players.update_one(
                {"_id": ObjectId(player_id)},
                {"$set": {"injury_status": req.new_injury_status}},
            )
        except Exception:
            pass

    from services.player_status_notifier import notify_player_status_change

    sent = await notify_player_status_change(
        _db(),
        player_id=player_id,
        change_kind=req.change_kind,
        create_notification=_deps.get("create_notification"),
        detail_message=req.detail_message,
    )
    return {
        "player_id": player_id,
        "change_kind": req.change_kind,
        "notifications_sent": sent,
    }
