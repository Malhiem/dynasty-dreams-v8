"""Draft Ops router — Iter 232N.46.

Commissioner-facing observability for draft workers + per-draft health.
Surfaces the same data the `draft_autostart_worker` and
`draft_pick_timer_worker` heartbeat into Mongo (`draft_autostart_runs`
and `draft_pick_timer_runs`), plus a live per-draft rollup so
commissioners can spot stalls before managers do.

Endpoints:

  • GET  /api/leagues/{league_id}/draft-ops
        → { workers, drafts, checked_at }
  • POST /api/leagues/{league_id}/drafts/{draft_id}/ping-owner
        → { ok, channels_fired, next_ping_at }
        Iter 232N.47 — Commissioner-fired nudge (in-app + push + email)
        to a specific offline owner while their team is on the clock.
        Rate-limited to one ping per (draft, owner) per 5 minutes to
        prevent spam.

Auth: commissioner, co-commissioner, or platform admin (via
`is_league_admin`).

Wired via the `setup(deps)` injection pattern; see `server.py`.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from routes import admin_metrics
from routes._authz import is_league_admin
from routes.notification_events import EVT_DRAFT_COMMISSIONER_PING


router = APIRouter()
_deps: dict = {}
logger = logging.getLogger(__name__)


def setup(deps: dict) -> None:
    _deps.update(deps)
    admin_metrics.setup(deps)


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


# ─── Iter 232N.47 — Commissioner "Ping offline manager" ────────────────


class PingOwnerRequest(BaseModel):
    user_id: str = Field(..., description="Target user (owner/co-owner) to ping")
    message: str | None = Field(
        None,
        description="Optional custom nudge from the commissioner. Truncated to 200 chars.",
        max_length=200,
    )


# In-memory rate limit: at most one ping per (draft_id, target_user_id) per
# window. Single-process backend so a dict is sufficient — a Mongo-based
# store would be needed if we ever fan out to multiple replicas.
_PING_COOLDOWN_SECONDS = 300  # 5 minutes
_PING_LAST_FIRED: dict[str, datetime] = {}


def _ping_key(draft_id: str, user_id: str) -> str:
    return f"{draft_id}:{user_id}"


@router.post("/leagues/{league_id}/drafts/{draft_id}/ping-owner")
async def ping_offline_owner(
    league_id: str,
    draft_id: str,
    payload: PingOwnerRequest,
    request: Request,
):
    """Nudge a specific offline owner: in-app notification + Expo push +
    SendGrid email + Socket.IO `commissioner_ping` broadcast.

    Rate-limited: at most one ping per (draft, target) per 5 minutes.
    Only the commissioner / co-commissioner / platform admin may fire.
    Only owners or co-owners of a team in this draft's roster are valid
    targets — commissioners can't spam arbitrary users through this route.
    """
    caller = await _get_user(request)
    db = _db()

    try:
        league = await db.leagues.find_one({"_id": ObjectId(league_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid league id")
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    if not is_league_admin(caller, league):
        raise HTTPException(
            status_code=403,
            detail="Commissioner / co-commissioner / admin only",
        )

    try:
        draft = await db.drafts.find_one({"_id": ObjectId(draft_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid draft id")
    if not draft or draft.get("league_id") != league_id:
        raise HTTPException(status_code=404, detail="Draft not found in this league")
    if draft.get("status") not in ("active", "scheduled"):
        raise HTTPException(
            status_code=400,
            detail="Ping only applies to active or scheduled drafts.",
        )

    # Verify the target is actually an owner/co-owner of a team in this
    # draft's team_map. Prevents commissioners from using this route to
    # blast arbitrary users.
    team_map = draft.get("team_map") or {}
    valid_owner = False
    target_team_name = None
    for _abbr, info in team_map.items():
        tid = info.get("id")
        if not tid:
            continue
        try:
            team = await db.teams.find_one(
                {"_id": ObjectId(tid)},
                {"owner_id": 1, "co_owner_ids": 1, "name": 1},
            )
        except Exception:
            team = None
        if not team:
            continue
        team_owners = {team.get("owner_id"), *(team.get("co_owner_ids") or [])}
        team_owners.discard(None)
        if payload.user_id in {str(u) for u in team_owners}:
            valid_owner = True
            target_team_name = team.get("name") or info.get("name") or _abbr
            break
    if not valid_owner:
        raise HTTPException(
            status_code=400,
            detail="Target user is not an owner or co-owner of any team in this draft.",
        )

    # Rate-limit
    now = datetime.now(timezone.utc)
    key = _ping_key(draft_id, payload.user_id)
    last = _PING_LAST_FIRED.get(key)
    if last and (now - last).total_seconds() < _PING_COOLDOWN_SECONDS:
        remaining = int(_PING_COOLDOWN_SECONDS - (now - last).total_seconds())
        raise HTTPException(
            status_code=429,
            detail=f"Already pinged this manager recently. Try again in {remaining}s.",
        )

    # Look up target for the email envelope + audit trail.
    try:
        target_user = await db.users.find_one(
            {"_id": ObjectId(payload.user_id)},
            {"email": 1, "name": 1, "username": 1},
        )
    except Exception:
        target_user = None
    if not target_user:
        raise HTTPException(status_code=404, detail="Target user not found")

    draft_name = draft.get("name") or "the draft"
    league_name = league.get("name") or "your league"
    commish_name = caller.get("name") or caller.get("email") or "the commissioner"
    custom = (payload.message or "").strip()
    body = (
        f"{commish_name} nudged you — {target_team_name} is on the clock in {draft_name}. "
        f"Head to the Draft Room to make your pick."
    )
    if custom:
        body = f"{commish_name} says: “{custom}” — {target_team_name} is on the clock in {draft_name}."
    title = f"Commissioner ping — {draft_name}"

    channels_fired: list[str] = []

    # 1) In-app + Expo push (bundled in `create_notification`)
    create_notification = _deps.get("create_notification")
    if create_notification is not None:
        try:
            notif = await create_notification(
                payload.user_id,
                EVT_DRAFT_COMMISSIONER_PING,
                title,
                body,
                league_id,
                "/draft-room",
                {
                    "draft_id": draft_id,
                    "draft_name": draft_name,
                    "commissioner_id": caller.get("_id"),
                    "commissioner_name": commish_name,
                    "team_name": target_team_name,
                    "custom_message": custom or None,
                },
            )
            if notif:
                channels_fired.append("in_app")
                # Expo push is fired inside `create_notification` when the
                # user has the push channel enabled. We assume push if the
                # notification broadcast succeeded; the actual delivery
                # is best-effort inside that helper.
                channels_fired.append("push")
        except Exception as e:
            logger.warning(f"ping_offline_owner in-app notify failed: {e}")

    # 2) SendGrid email — always fires (channel preference for the ping
    # event defaults to on; a hard opt-out on this event effectively
    # means the manager doesn't want to be pinged, so we already dropped
    # the in-app write via `channel_enabled` inside create_notification).
    send_email = _deps.get("send_sendgrid_email")
    target_email = target_user.get("email")
    if send_email is not None and target_email:
        try:
            frontend_link = "/draft-room"
            html = (
                f"<p>Hi {target_user.get('name') or target_user.get('username') or 'manager'},</p>"
                f"<p><b>{commish_name}</b> nudged you — <b>{target_team_name}</b> is on the clock in "
                f"<b>{draft_name}</b> ({league_name}).</p>"
            )
            if custom:
                html += f"<p><i>“{custom}”</i></p>"
            html += (
                f"<p><a href=\"{frontend_link}\">Open the Draft Room →</a></p>"
                f"<p style=\"color:#888;font-size:12px\">Sent by your league commissioner via Dynasty Dreams.</p>"
            )
            send_email(target_email, title, html)
            channels_fired.append("email")
        except Exception as e:
            logger.warning(f"ping_offline_owner email failed: {e}")

    # 3) Real-time Socket.IO broadcast to the user's personal room so
    # any open tab shows a modal/toast immediately (no polling wait).
    broadcast = _deps.get("broadcast_to_room")
    if broadcast is not None:
        try:
            await broadcast(
                f"user_{payload.user_id}",
                "commissioner_ping",
                {
                    "draft_id": draft_id,
                    "draft_name": draft_name,
                    "league_id": league_id,
                    "league_name": league_name,
                    "commissioner_name": commish_name,
                    "team_name": target_team_name,
                    "custom_message": custom or None,
                    "created_at": now.isoformat(),
                },
            )
            channels_fired.append("socket")
        except Exception as e:
            logger.debug(f"ping_offline_owner socket broadcast skipped: {e}")

    # Latch the cooldown ONLY if at least one channel actually fired —
    # a total misfire (all channels failed) shouldn't lock the
    # commissioner out for 5 minutes.
    if channels_fired:
        _PING_LAST_FIRED[key] = now

    # Audit row so the commissioner has a searchable log of pings.
    try:
        await db.commissioner_pings.insert_one({
            "league_id": league_id,
            "draft_id": draft_id,
            "commissioner_id": caller.get("_id"),
            "target_user_id": payload.user_id,
            "target_team_name": target_team_name,
            "custom_message": custom or None,
            "channels_fired": channels_fired,
            "created_at": now.isoformat(),
        })
    except Exception as e:
        logger.debug(f"ping_offline_owner audit insert skipped: {e}")

    next_ping_at = (now + timedelta(seconds=_PING_COOLDOWN_SECONDS)).isoformat() if channels_fired else None
    return {
        "ok": True,
        "channels_fired": channels_fired,
        "next_ping_at": next_ping_at,
        "cooldown_seconds": _PING_COOLDOWN_SECONDS,
    }


# ─── Iter 232N.52 — Recent commissioner overrides feed ─────────────────


async def _user_can_view_league(db, user: dict, league: dict) -> bool:
    """Any league member (team owner / co-owner / commissioner / admin)
    may read the overrides feed — this is a transparency surface, not
    a privileged one."""
    if is_league_admin(user, league):
        return True
    uid = user.get("_id")
    if not uid:
        return False
    # Team ownership implies membership.
    exists = await db.teams.find_one(
        {
            "league_id": str(league["_id"]),
            "$or": [{"owner_id": uid}, {"co_owner_ids": uid}],
        },
        {"_id": 1},
    )
    return exists is not None


@router.get("/leagues/{league_id}/commissioner-overrides")
async def list_commissioner_overrides(
    league_id: str,
    request: Request,
    limit: int = 30,
):
    """Unified reverse-chronological feed of every commissioner-fired
    action in this league. Currently surfaces two event types:

      • `pick_undo` — from `draft_undo_audit` (Iter 232N.51). Records
        who undid which pick, why, cascade impact, and which team was
        on the clock after.
      • `owner_ping` — from `commissioner_pings` (Iter 232N.47). Records
        who was pinged, which team, custom message if any, and which
        channels fired.

    Auth: any league member (team owner, co-owner, commissioner, or
    platform admin). Not restricted to commissioners because the whole
    point is transparency — league mates should be able to see when
    the commissioner has stepped in.
    """
    user = await _get_user(request)
    db = _db()

    try:
        league = await db.leagues.find_one({"_id": ObjectId(league_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid league id")
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    if not await _user_can_view_league(db, user, league):
        raise HTTPException(status_code=403, detail="League members only")

    limit = max(1, min(int(limit), 100))
    now = datetime.now(timezone.utc)

    # ─── pick_undo events ─────────────────────────────────────────
    undos: list[dict] = []
    async for row in db.draft_undo_audit.find(
        {"league_id": league_id}
    ).sort([("undone_at", -1)]).limit(limit):
        removed_picks = row.get("removed_picks") or []
        primary = removed_picks[0] if removed_picks else {}
        undos.append({
            "type": "pick_undo",
            "at": row.get("undone_at"),
            "commissioner": {
                "id": row.get("commissioner_id"),
                "name": row.get("commissioner_name") or "Commissioner",
            },
            "reason": row.get("reason"),
            "detail": {
                "pick_number": row.get("pick_number"),
                "removed_count": row.get("removed_count", len(removed_picks)),
                "cascade": bool(row.get("cascade")),
                "player_name": (primary.get("player") or {}).get("name")
                    if isinstance(primary.get("player"), dict) else None,
                "team": primary.get("team"),
                "on_the_clock_after": row.get("on_the_clock_after"),
            },
        })

    # ─── owner_ping events ────────────────────────────────────────
    pings: list[dict] = []
    async for row in db.commissioner_pings.find(
        {"league_id": league_id}
    ).sort([("created_at", -1)]).limit(limit):
        target_name = None
        try:
            tuid = row.get("target_user_id")
            if tuid:
                tu = await db.users.find_one(
                    {"_id": ObjectId(tuid)},
                    {"name": 1, "username": 1, "email": 1},
                )
                if tu:
                    target_name = tu.get("name") or tu.get("username") or tu.get("email")
        except Exception:
            pass
        commish_name = None
        try:
            cuid = row.get("commissioner_id")
            if cuid:
                cu = await db.users.find_one(
                    {"_id": ObjectId(cuid)},
                    {"name": 1, "username": 1, "email": 1},
                )
                if cu:
                    commish_name = cu.get("name") or cu.get("username") or cu.get("email")
        except Exception:
            pass
        pings.append({
            "type": "owner_ping",
            "at": row.get("created_at"),
            "commissioner": {
                "id": row.get("commissioner_id"),
                "name": commish_name or "Commissioner",
            },
            "reason": row.get("custom_message"),
            "detail": {
                "target_user_id": row.get("target_user_id"),
                "target_name": target_name or "Manager",
                "target_team_name": row.get("target_team_name"),
                "draft_id": row.get("draft_id"),
                "channels_fired": row.get("channels_fired") or [],
            },
        })

    # Merge, sort DESC by timestamp, cap at limit. Rows missing an `at`
    # sink to the bottom rather than crashing the sort.
    def _sort_key(e):
        v = e.get("at")
        return v if isinstance(v, str) else ""

    merged = sorted(undos + pings, key=_sort_key, reverse=True)[:limit]

    return {
        "league_id": league_id,
        "checked_at": now.isoformat(),
        "count": len(merged),
        "events": merged,
    }


# ─── Iter 232N.53 — Platform-wide commissioner activity feed ────────────


@router.get("/admin/commissioner-activity")
async def platform_commissioner_activity(
    request: Request,
    limit: int = 50,
    days: int = 30,
):
    """Platform-admin-only feed of every commissioner override across
    ALL leagues on the platform, plus lightweight aggregate stats to
    surface problem patterns (a commissioner who's undone 12 picks in
    a week, a league that's had 40 offline-manager pings, etc.).

    Response shape:
      {
        checked_at, window_days, count, events: [ ... ],
        aggregates: {
          by_league:      [{id, name, undos, pings, total}, ...],
          by_commissioner:[{id, name, undos, pings, total}, ...],
          totals: {undos, pings, total},
        }
      }

    Events carry `league_id` + `league_name` so the admin UI can group
    / filter without extra lookups. `limit` is post-merge; aggregates
    scan the full window (not paginated).

    Auth: `user.role == "admin"` (platform tier). Any other role → 403.
    """
    user = await _get_user(request)
    if not user or user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Platform admin only")

    db = _db()
    limit = max(1, min(int(limit), 200))
    days = max(1, min(int(days), 365))
    now = datetime.now(timezone.utc)
    cutoff_iso = (now - timedelta(days=days)).isoformat()

    league_cache: dict[str, str] = {}

    async def _league_name(league_id: str | None) -> str | None:
        if not league_id:
            return None
        if league_id in league_cache:
            return league_cache[league_id]
        try:
            lg = await db.leagues.find_one(
                {"_id": ObjectId(league_id)}, {"name": 1}
            )
            name = (lg or {}).get("name")
        except Exception:
            name = None
        league_cache[league_id] = name or "(unknown league)"
        return league_cache[league_id]

    # ─── pick_undo events ───
    undos: list[dict] = []
    async for row in db.draft_undo_audit.find(
        {"undone_at": {"$gte": cutoff_iso}}
    ).sort([("undone_at", -1)]).limit(limit * 2):
        removed_picks = row.get("removed_picks") or []
        primary = removed_picks[0] if removed_picks else {}
        undos.append({
            "type": "pick_undo",
            "at": row.get("undone_at"),
            "league_id": row.get("league_id"),
            "league_name": await _league_name(row.get("league_id")),
            "commissioner": {
                "id": row.get("commissioner_id"),
                "name": row.get("commissioner_name") or "Commissioner",
            },
            "reason": row.get("reason"),
            "detail": {
                "pick_number": row.get("pick_number"),
                "removed_count": row.get("removed_count", len(removed_picks)),
                "cascade": bool(row.get("cascade")),
                "player_name": (primary.get("player") or {}).get("name")
                    if isinstance(primary.get("player"), dict) else None,
                "team": primary.get("team"),
                "on_the_clock_after": row.get("on_the_clock_after"),
            },
        })

    # ─── owner_ping events ───
    pings: list[dict] = []
    async for row in db.commissioner_pings.find(
        {"created_at": {"$gte": cutoff_iso}}
    ).sort([("created_at", -1)]).limit(limit * 2):
        commish_name = None
        try:
            cuid = row.get("commissioner_id")
            if cuid:
                cu = await db.users.find_one(
                    {"_id": ObjectId(cuid)},
                    {"name": 1, "username": 1, "email": 1},
                )
                if cu:
                    commish_name = cu.get("name") or cu.get("username") or cu.get("email")
        except Exception:
            pass
        pings.append({
            "type": "owner_ping",
            "at": row.get("created_at"),
            "league_id": row.get("league_id"),
            "league_name": await _league_name(row.get("league_id")),
            "commissioner": {
                "id": row.get("commissioner_id"),
                "name": commish_name or "Commissioner",
            },
            "reason": row.get("custom_message"),
            "detail": {
                "target_user_id": row.get("target_user_id"),
                "target_team_name": row.get("target_team_name"),
                "draft_id": row.get("draft_id"),
                "channels_fired": row.get("channels_fired") or [],
            },
        })

    def _sort_key(e):
        v = e.get("at")
        return v if isinstance(v, str) else ""

    merged = sorted(undos + pings, key=_sort_key, reverse=True)[:limit]

    # ─── Aggregates + trend from `commissioner_activity_daily` rollup ───
    # Iter 232N.54 — Prefer the pre-computed rollup (nightly worker in
    # `services/commissioner_activity_rollup.py`). Falls back to a live
    # in-memory aggregation when the rollup collection is empty (first
    # boot, tests, or during the initial backfill window).
    cutoff_day = (now - timedelta(days=days)).date().isoformat()

    rollup_league: dict[str, dict] = {}
    rollup_commish: dict[str, dict] = {}
    trend_by_day: dict[str, dict] = {}
    async for row in db.commissioner_activity_daily.find(
        {"day": {"$gte": cutoff_day}}
    ):
        kind = row.get("kind")
        rid = row.get("id")
        undos_n = int(row.get("undos") or 0)
        pings_n = int(row.get("pings") or 0)
        total = undos_n + pings_n
        if kind == "league":
            b = rollup_league.setdefault(
                rid, {"id": rid, "name": row.get("name") or "?", "undos": 0, "pings": 0, "total": 0}
            )
            b["undos"] += undos_n
            b["pings"] += pings_n
            b["total"] += total
            # Trend day (aggregated across all leagues for that day).
            day = row.get("day")
            if day:
                d = trend_by_day.setdefault(
                    day, {"day": day, "undos": 0, "pings": 0, "total": 0}
                )
                d["undos"] += undos_n
                d["pings"] += pings_n
                d["total"] += total
        elif kind == "commissioner":
            b = rollup_commish.setdefault(
                rid, {"id": rid, "name": row.get("name") or "?", "undos": 0, "pings": 0, "total": 0}
            )
            b["undos"] += undos_n
            b["pings"] += pings_n
            b["total"] += total

    if rollup_league or rollup_commish:
        # Rollup path — populated.
        by_league = sorted(rollup_league.values(), key=lambda x: x["total"], reverse=True)
        by_commish = sorted(rollup_commish.values(), key=lambda x: x["total"], reverse=True)
        agg_source = "rollup"
    else:
        # Live-scan fallback (identical logic to the pre-N.54 path).
        league_agg: dict[str, dict] = {}
        commish_agg: dict[str, dict] = {}

        def _bump(bucket: dict, key: str, name: str, kind: str):
            if key not in bucket:
                bucket[key] = {"id": key, "name": name, "undos": 0, "pings": 0, "total": 0}
            if kind == "pick_undo":
                bucket[key]["undos"] += 1
            elif kind == "owner_ping":
                bucket[key]["pings"] += 1
            bucket[key]["total"] += 1

        async for row in db.draft_undo_audit.find(
            {"undone_at": {"$gte": cutoff_iso}}
        ):
            lid = row.get("league_id") or "unknown"
            ln = await _league_name(row.get("league_id")) or "(unknown league)"
            _bump(league_agg, lid, ln, "pick_undo")
            cid = row.get("commissioner_id") or "unknown"
            cname = row.get("commissioner_name") or "Commissioner"
            _bump(commish_agg, cid, cname, "pick_undo")
        async for row in db.commissioner_pings.find(
            {"created_at": {"$gte": cutoff_iso}}
        ):
            lid = row.get("league_id") or "unknown"
            ln = await _league_name(row.get("league_id")) or "(unknown league)"
            _bump(league_agg, lid, ln, "owner_ping")
            cid = row.get("commissioner_id") or "unknown"
            cname = "Commissioner"
            if cid != "unknown":
                try:
                    cu = await db.users.find_one(
                        {"_id": ObjectId(cid)},
                        {"name": 1, "username": 1, "email": 1},
                    )
                    if cu:
                        cname = cu.get("name") or cu.get("username") or cu.get("email") or cname
                except Exception:
                    pass
            _bump(commish_agg, cid, cname, "owner_ping")

        by_league = sorted(league_agg.values(), key=lambda x: x["total"], reverse=True)
        by_commish = sorted(commish_agg.values(), key=lambda x: x["total"], reverse=True)
        agg_source = "live_scan_fallback"

    # Fill trend gaps with zero-day rows so the frontend chart draws
    # a continuous line instead of a spiky one.
    trend: list[dict] = []
    for i in range(days):
        d = (now - timedelta(days=days - 1 - i)).date().isoformat()
        trend.append(trend_by_day.get(d) or {"day": d, "undos": 0, "pings": 0, "total": 0})

    return {
        "checked_at": now.isoformat(),
        "window_days": days,
        "count": len(merged),
        "events": merged,
        "aggregates": {
            "by_league": by_league[:10],
            "by_commissioner": by_commish[:10],
            "totals": {
                "undos": sum(l["undos"] for l in by_league),
                "pings": sum(l["pings"] for l in by_league),
                "total": sum(l["total"] for l in by_league),
            },
            "source": agg_source,
        },
        "trend": trend,
    }

router.include_router(admin_metrics.router)
