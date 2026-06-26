"""Iter 230c — Notification worker (scheduled-job framework).

Runs every 30 minutes and fires three families of "time-based" notifications
that the iter 230 catalog declares but no synchronous flow can emit:

  • lineup_lock_reminder — when a league's `matchup_lock_at` (per-week lock)
    is between `LOCK_WINDOW_MIN` and `LOCK_WINDOW_MAX` minutes away. Notifies
    every team owner + co-owner so they can finalize their roster.

  • lineup_problem — for any team in a league inside the lock window whose
    active lineup has empty/invalid slots. Detected via the `lineup` map on
    the team doc (active slots that point to no player_id, or to a player
    not on the roster).

  • reminder_important — sent for milestone events that are about to fire:
    upcoming draft within 24h, league trade deadline within 24h, and the
    season start within 24h.

The worker is intentionally cheap: it ranges over leagues/drafts that have
the relevant timestamp populated, computes deltas in pure Python, and uses
the existing `create_notification` helper (which already honours user
preferences) for delivery.

Per-event dedup is handled with a small `notification_worker_state` doc
per league so we don't re-fire reminders every loop tick. State is keyed
on `(league_id, event_id, target_iso)` so a future re-scheduling of the
same milestone fires again as expected.
"""
from datetime import datetime, timezone, timedelta
from typing import Awaitable, Callable, Optional

from bson import ObjectId

from routes.notification_events import (
    EVT_LINEUP_LOCK_REMINDER,
    EVT_LINEUP_PROBLEM,
    EVT_REMINDER_IMPORTANT,
)


# Lock window: notify when within (15 min, 4h) of lock time.
LOCK_WINDOW_MIN = timedelta(minutes=15)
LOCK_WINDOW_MAX = timedelta(hours=4)

# Important-reminder window: 24h.
REMINDER_WINDOW = timedelta(hours=24)


def _parse_iso(value) -> Optional[datetime]:
    if not value:
        return None
    try:
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        s = str(value).replace("Z", "+00:00")
        return datetime.fromisoformat(s)
    except Exception:
        return None


async def _already_fired(db, league_id: str, event_id: str, target_iso: str) -> bool:
    """Per-league per-event dedup. Returns True if we've already fired this
    notification family for this target timestamp."""
    key = f"{event_id}:{target_iso}"
    doc = await db.notification_worker_state.find_one({"league_id": league_id, "key": key})
    return bool(doc)


async def _mark_fired(db, league_id: str, event_id: str, target_iso: str) -> None:
    key = f"{event_id}:{target_iso}"
    await db.notification_worker_state.update_one(
        {"league_id": league_id, "key": key},
        {"$set": {
            "league_id": league_id,
            "key": key,
            "fired_at": datetime.now(timezone.utc).isoformat(),
        }},
        upsert=True,
    )


async def _league_recipients(db, league_id: str) -> list:
    """Returns the union of owner_id + co_owner_ids across all teams in
    the league. Used for league-wide reminder fanouts."""
    teams = await db.teams.find(
        {"league_id": league_id},
        {"owner_id": 1, "co_owner_ids": 1},
    ).to_list(200)
    recipients: set = set()
    for t in teams:
        if t.get("owner_id"):
            recipients.add(t["owner_id"])
        for co in (t.get("co_owner_ids") or []):
            if co:
                recipients.add(co)
    return list(recipients)


async def _emit_to_recipients(
    create_notification,
    recipients,
    event_id,
    title,
    body,
    league_id,
    link,
):
    if not create_notification:
        return
    for uid in recipients:
        try:
            await create_notification(uid, event_id, title, body, league_id, link)
        except Exception:
            pass


def _has_lineup_problem(team: dict) -> bool:
    """Return True if the team's active lineup has empty/invalid slots.

    "Active" excludes bench / minors / IR sections. A slot is considered
    a problem if it doesn't reference a player_id, OR the referenced
    player_id isn't on the team's roster array.
    """
    lineup = team.get("lineup") or {}
    roster_set = set(team.get("roster") or [])
    for player_id, slot in lineup.items():
        if not isinstance(slot, dict):
            continue
        section = (slot.get("section") or "").lower()
        if section in ("bench", "minors", "ir"):
            continue
        # An entry exists with no player_id → empty slot.
        if not player_id:
            return True
        if player_id not in roster_set:
            return True
    return False


async def run_once(db, create_notification: Callable[..., Awaitable]) -> dict:
    """Single pass of the worker. Returns a counts dict for observability."""
    now = datetime.now(timezone.utc)
    counts = {
        "lineup_lock_reminders": 0,
        "lineup_problems": 0,
        "reminders_important": 0,
    }

    # ── Lineup lock reminders + lineup problem detection ────────────────
    async for league in db.leagues.find(
        {"matchup_lock_at": {"$exists": True, "$ne": None}},
        {"_id": 1, "name": 1, "matchup_lock_at": 1},
    ):
        league_id = str(league["_id"])
        lock_at = _parse_iso(league.get("matchup_lock_at"))
        if not lock_at:
            continue
        delta = lock_at - now
        if delta < LOCK_WINDOW_MIN or delta > LOCK_WINDOW_MAX:
            continue
        target_iso = lock_at.isoformat()

        # 1. Lock reminder — once per lock target.
        if not await _already_fired(db, league_id, EVT_LINEUP_LOCK_REMINDER, target_iso):
            recipients = await _league_recipients(db, league_id)
            mins = max(1, int(delta.total_seconds() // 60))
            body = f"{league.get('name') or 'Your league'} lineup locks in ~{mins} min."
            await _emit_to_recipients(
                create_notification,
                recipients,
                EVT_LINEUP_LOCK_REMINDER,
                "Lineup lock approaching",
                body,
                league_id,
                "/rosters",
            )
            await _mark_fired(db, league_id, EVT_LINEUP_LOCK_REMINDER, target_iso)
            counts["lineup_lock_reminders"] += len(recipients)

        # 2. Lineup-problem detection — per-team.
        teams = await db.teams.find({"league_id": league_id}).to_list(200)
        for team in teams:
            if not _has_lineup_problem(team):
                continue
            team_key = f"{EVT_LINEUP_PROBLEM}:{team['_id']}"
            if await _already_fired(db, league_id, team_key, target_iso):
                continue
            owners = []
            if team.get("owner_id"):
                owners.append(team["owner_id"])
            for co in (team.get("co_owner_ids") or []):
                if co:
                    owners.append(co)
            body = f"{team.get('name') or 'Your team'} has empty or invalid active-lineup slots before lock."
            await _emit_to_recipients(
                create_notification,
                owners,
                EVT_LINEUP_PROBLEM,
                "Fix your lineup",
                body,
                league_id,
                f"/teams/{team['_id']}",
            )
            await _mark_fired(db, league_id, team_key, target_iso)
            counts["lineup_problems"] += len(owners)

    # ── Important reminders: drafts + trade deadlines + season starts ────
    # Drafts within 24h.
    async for draft in db.drafts.find(
        {
            "scheduled_time": {"$exists": True, "$ne": None},
            "status": {"$in": ["scheduled", "pending"]},
        },
        {"_id": 1, "league_id": 1, "name": 1, "scheduled_time": 1},
    ):
        sched = _parse_iso(draft.get("scheduled_time"))
        if not sched:
            continue
        delta = sched - now
        if delta <= timedelta(0) or delta > REMINDER_WINDOW:
            continue
        league_id = str(draft["league_id"])
        target_iso = sched.isoformat()
        family_key = f"draft:{draft['_id']}"
        if await _already_fired(db, league_id, family_key, target_iso):
            continue
        recipients = await _league_recipients(db, league_id)
        hrs = max(1, int(delta.total_seconds() // 3600))
        body = f"{draft.get('name') or 'Draft'} starts in ~{hrs}h."
        await _emit_to_recipients(
            create_notification, recipients,
            EVT_REMINDER_IMPORTANT,
            "Draft starting soon",
            body, league_id, "/draft-room",
        )
        await _mark_fired(db, league_id, family_key, target_iso)
        counts["reminders_important"] += len(recipients)

    # League trade deadlines + season starts.
    async for lg in db.leagues.find(
        {
            "$or": [
                {"trade_deadline_at": {"$exists": True, "$ne": None}},
                {"season_start_at": {"$exists": True, "$ne": None}},
            ],
        },
        {"_id": 1, "name": 1, "trade_deadline_at": 1, "season_start_at": 1},
    ):
        league_id = str(lg["_id"])
        for field, label, link in [
            ("trade_deadline_at", "Trade deadline", "/transactions"),
            ("season_start_at",   "Season start",   "/league-home"),
        ]:
            target = _parse_iso(lg.get(field))
            if not target:
                continue
            delta = target - now
            if delta <= timedelta(0) or delta > REMINDER_WINDOW:
                continue
            target_iso = target.isoformat()
            family_key = f"{field}"
            if await _already_fired(db, league_id, family_key, target_iso):
                continue
            recipients = await _league_recipients(db, league_id)
            hrs = max(1, int(delta.total_seconds() // 3600))
            body = f"{lg.get('name') or 'Your league'} — {label.lower()} in ~{hrs}h."
            await _emit_to_recipients(
                create_notification, recipients,
                EVT_REMINDER_IMPORTANT,
                f"{label} approaching",
                body, league_id, link,
            )
            await _mark_fired(db, league_id, family_key, target_iso)
            counts["reminders_important"] += len(recipients)

    return counts


async def notification_worker_loop(db, create_notification, interval_seconds: int = 1800):
    """Long-running asyncio task. Sleeps `interval_seconds` between passes
    (default 30 min)."""
    import asyncio
    import logging
    log = logging.getLogger("notification_worker")
    while True:
        try:
            counts = await run_once(db, create_notification)
            if any(counts.values()):
                log.info(f"notification_worker: emitted {counts}")
        except Exception as e:
            log.error(f"notification_worker loop error: {e}")
        await asyncio.sleep(interval_seconds)
