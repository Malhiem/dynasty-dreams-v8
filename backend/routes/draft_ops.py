"""Draft Ops router — Iter 232N.46.

Commissioner-facing observability for draft workers + per-draft health.
Surfaces the same data the `draft_autostart_worker` and
`draft_pick_timer_worker` heartbeat into Mongo (`draft_autostart_runs`
and `draft_pick_timer_runs`), plus a live per-draft rollup so
commissioners can spot stalls before managers do.

Single endpoint:

  • GET /api/leagues/{league_id}/draft-ops
      → { workers, drafts, checked_at }

Auth: commissioner, co-commissioner, or platform admin (via
`is_league_admin`).

Wired via the `setup(deps)` injection pattern; see `server.py`.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Request

from routes._authz import is_league_admin


router = APIRouter()
_deps: dict = {}
logger = logging.getLogger(__name__)


def setup(deps: dict) -> None:
    _deps.update(deps)


def _db():
    return _deps["db"]


async def _get_user(request: Request):
    return await _deps["get_current_user"](request)


def _parse_iso(value):
    if not value:
        return None
    try:
        s = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _is_user_in_draft_room(draft_id: str, user_id: str) -> bool:
    """True if `user_id` currently has an authenticated Socket.IO session
    in the `draft_{draft_id}` room. Reads `server.connected_users` (a
    module-level dict populated on every `join_room` event)."""
    if not user_id:
        return False
    try:
        from server import connected_users
    except Exception:
        return False
    room = f"draft_{draft_id}"
    uid = str(user_id)
    for info in connected_users.values():
        if info.get("room_id") == room and str(info.get("user_id")) == uid:
            return True
    return False


async def _resolve_on_clock(db, draft: dict) -> dict | None:
    """Return {abbr, team_id, team_name, owners:[{id,name,online}],
    admin_managed, is_ownerless} for the team on the clock — or None
    when the draft has no team_abbrs / current_pick is out of range."""
    team_abbrs = draft.get("team_abbrs") or []
    if not team_abbrs:
        return None
    try:
        from draft_engine import get_team_for_pick
        abbr = get_team_for_pick(
            team_abbrs,
            draft.get("current_pick", 1),
            draft.get("snake_draft", True),
        )
    except Exception:
        return None
    if not abbr:
        return None
    tm = (draft.get("team_map") or {}).get(abbr) or {}
    team_id = tm.get("id")
    team_name = tm.get("name") or abbr
    team = None
    if team_id:
        try:
            team = await db.teams.find_one({"_id": ObjectId(team_id)})
        except Exception:
            team = None
    owner_ids = []
    if team:
        if team.get("owner_id"):
            owner_ids.append(team["owner_id"])
        owner_ids.extend(team.get("co_owner_ids") or [])
    owners = []
    for uid in owner_ids:
        try:
            u = await db.users.find_one(
                {"_id": ObjectId(uid)},
                {"name": 1, "email": 1, "username": 1},
            )
        except Exception:
            u = None
        owners.append({
            "id": str(uid),
            "name": (u or {}).get("name") or (u or {}).get("username") or (u or {}).get("email") or "unknown",
            "online": _is_user_in_draft_room(str(draft["_id"]), str(uid)),
        })
    return {
        "abbr": abbr,
        "team_id": team_id,
        "team_name": team_name,
        "owners": owners,
        "admin_managed": bool(team and team.get("admin_managed")),
        "is_ownerless": bool(team is not None and not owner_ids),
    }


def _seconds_until_expiry(draft: dict, now: datetime) -> int | None:
    """Compute seconds until this draft's current pick auto-picks
    (positive = time remaining; negative = elapsed past deadline).
    Returns None when the draft isn't running / no clock started."""
    started = _parse_iso(draft.get("current_pick_started_at"))
    if not started or draft.get("status") != "active":
        return None
    pick_time = int(
        draft.get("time_per_pick")
        or draft.get("pick_time_seconds")
        or 60
    )
    personal_cap = draft.get("personal_pick_timer_seconds")
    try:
        personal_cap = int(personal_cap) if personal_cap else None
    except (TypeError, ValueError):
        personal_cap = None
    effective = pick_time
    if personal_cap and personal_cap < pick_time:
        effective = personal_cap
    return int((started.timestamp() + effective) - now.timestamp())


@router.get("/leagues/{league_id}/draft-ops")
async def get_draft_ops(league_id: str, request: Request):
    user = await _get_user(request)
    db = _db()

    try:
        league = await db.leagues.find_one({"_id": ObjectId(league_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid league id")
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    if not is_league_admin(user, league):
        raise HTTPException(
            status_code=403,
            detail="Commissioner / co-commissioner / admin only",
        )

    now = datetime.now(timezone.utc)

    # Worker heartbeats — the workers upsert `_id: "latest"` every tick,
    # so we get the very latest run of each. `error: null` = healthy.
    autostart_run = await db.draft_autostart_runs.find_one({"_id": "latest"}) or {}
    timer_run = await db.draft_pick_timer_runs.find_one({"_id": "latest"}) or {}

    def _worker_summary(doc: dict, expected_interval_seconds: int) -> dict:
        finished = _parse_iso(doc.get("finished_at"))
        seconds_since = int((now - finished).total_seconds()) if finished else None
        # "healthy" == the worker ran within 3× its expected cadence
        # (short bursts of GC pressure or one slow DB call shouldn't
        # flip the light red).
        healthy = (
            finished is not None
            and seconds_since is not None
            and seconds_since <= expected_interval_seconds * 3
            and not doc.get("error")
        )
        return {
            "last_run_at": doc.get("finished_at"),
            "seconds_since_last_run": seconds_since,
            "counts": doc.get("counts") or {},
            "error": doc.get("error"),
            "healthy": healthy,
            "expected_interval_seconds": expected_interval_seconds,
        }

    workers = {
        # `draft_autostart_worker` runs every 60s.
        "autostart": _worker_summary(autostart_run, 60),
        # `draft_pick_timer_worker` runs every 15s.
        "pick_timer": _worker_summary(timer_run, 15),
    }

    # Scan all non-archived drafts in this league. `sort` newest-first
    # so active drafts naturally float to the top of the panel.
    drafts_out = []
    async for d in db.drafts.find(
        {"league_id": league_id, "status": {"$ne": "archived"}}
    ).sort("scheduled_time", 1):
        picks = d.get("picks") or []
        picks_made = sum(1 for p in picks if p.get("player_id"))
        total_rounds = int(d.get("total_rounds") or 0)
        team_count = len(d.get("team_abbrs") or [])
        total_picks = total_rounds * team_count if total_rounds and team_count else None
        on_clock = None
        if d.get("status") == "active":
            on_clock = await _resolve_on_clock(db, d)
        seconds_remaining = _seconds_until_expiry(d, now)
        drafts_out.append({
            "id": str(d["_id"]),
            "name": d.get("name") or "(unnamed draft)",
            "status": d.get("status"),
            "scheduled_time": d.get("scheduled_time"),
            "started_at": d.get("started_at"),
            "current_pick": d.get("current_pick") or 1,
            "total_picks": total_picks,
            "picks_made": picks_made,
            "team_count": team_count,
            "total_rounds": total_rounds,
            "time_per_pick": d.get("time_per_pick") or d.get("pick_time_seconds"),
            "personal_pick_timer_seconds": d.get("personal_pick_timer_seconds"),
            "missed_pick_action": d.get("missed_pick_action") or "auto-select",
            "timer_paused": bool(d.get("timer_paused")),
            "current_pick_started_at": d.get("current_pick_started_at"),
            "seconds_remaining": seconds_remaining,
            "on_clock": on_clock,
        })

    return {
        "league_id": league_id,
        "checked_at": now.isoformat(),
        "workers": workers,
        "drafts": drafts_out,
    }
