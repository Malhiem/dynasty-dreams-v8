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


# Iter 230h+ hardening — skip leagues that are clearly junk (archived,
# explicitly archived status, or a leftover automated-test fixture).
# Mirrors the iter 230g Week-at-a-Glance filter so the worker doesn't
# spam reminders into TEST_*/archived leagues.
def _is_skippable_league(lg: dict) -> bool:
    if not lg:
        return True
    if lg.get("archived") is True:
        return True
    if (lg.get("status") or "").lower() == "archived":
        return True
    name = lg.get("name") or ""
    if name.startswith("TEST_"):
        return True
    return False


async def _emit_to_recipients(
    create_notification,
    recipients,
    event_id,
    title,
    body,
    league_id,
    link,
    reason: Optional[dict] = None,
):
    """Iter 230h+ — Forwards an optional `reason` dict so each emission
    carries provenance ("Why am I being notified?" Info popover reads
    this). Falls back to a positional call when the downstream
    `create_notification` doesn't accept the kwarg (older test stubs)."""
    if not create_notification:
        return
    for uid in recipients:
        try:
            if reason is not None:
                try:
                    await create_notification(uid, event_id, title, body, league_id, link, reason=reason)
                    continue
                except TypeError:
                    # Stub didn't accept `reason=` — fall through to the
                    # legacy positional form so we still deliver.
                    pass
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
        {"_id": 1, "name": 1, "matchup_lock_at": 1, "archived": 1, "status": 1},
    ):
        # Iter 230h+ — Skip junk/archived leagues so the worker never
        # fans out reminders into TEST_*/archived fixtures.
        if _is_skippable_league(league):
            continue
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
                reason={
                    "kind": "lineup_lock_reminder",
                    "league_id": league_id,
                    "league_name": league.get("name"),
                    "lock_at": target_iso,
                    "minutes_until_lock": mins,
                    "source": "notification_worker",
                },
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
            # Dedupe owners (owner could also be co_owner historically).
            owners: set = set()
            if team.get("owner_id"):
                owners.add(team["owner_id"])
            for co in (team.get("co_owner_ids") or []):
                if co:
                    owners.add(co)
            owners_list = list(owners)
            body = f"{team.get('name') or 'Your team'} has empty or invalid active-lineup slots before lock."
            await _emit_to_recipients(
                create_notification,
                owners_list,
                EVT_LINEUP_PROBLEM,
                "Fix your lineup",
                body,
                league_id,
                f"/teams/{team['_id']}",
                reason={
                    "kind": "lineup_problem",
                    "league_id": league_id,
                    "league_name": league.get("name"),
                    "team_id": str(team["_id"]),
                    "team_name": team.get("name"),
                    "lock_at": target_iso,
                    "source": "notification_worker",
                },
            )
            await _mark_fired(db, league_id, team_key, target_iso)
            counts["lineup_problems"] += len(owners_list)

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
        # Iter 230h+ — Skip junk leagues here too. One extra read but
        # cached by the driver; safer than the alternative.
        parent = await db.leagues.find_one(
            {"_id": ObjectId(league_id) if ObjectId.is_valid(league_id) else league_id},
            {"name": 1, "archived": 1, "status": 1},
        )
        if _is_skippable_league(parent):
            continue
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
            reason={
                "kind": "reminder_important",
                "milestone": "draft",
                "league_id": league_id,
                "league_name": (parent or {}).get("name"),
                "draft_id": str(draft["_id"]),
                "draft_name": draft.get("name"),
                "target_at": target_iso,
                "hours_until": hrs,
                "source": "notification_worker",
            },
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
        {"_id": 1, "name": 1, "trade_deadline_at": 1, "season_start_at": 1, "archived": 1, "status": 1},
    ):
        if _is_skippable_league(lg):
            continue
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
                reason={
                    "kind": "reminder_important",
                    "milestone": field,
                    "league_id": league_id,
                    "league_name": lg.get("name"),
                    "target_at": target_iso,
                    "hours_until": hrs,
                    "source": "notification_worker",
                },
            )
            await _mark_fired(db, league_id, family_key, target_iso)
            counts["reminders_important"] += len(recipients)

    return counts


async def notification_worker_loop(db, create_notification, interval_seconds: int = 1800):
    """Long-running asyncio task. Sleeps `interval_seconds` between passes
    (default 30 min).

    Iter 230h+ — Writes a `notification_worker_runs` heartbeat doc every
    pass for observability (last run timestamp, counts, error if any).
    Always upserts so the most recent state is queryable from admin
    tools without needing log file access.
    """
    import asyncio
    import logging
    log = logging.getLogger("notification_worker")
    while True:
        started_at = datetime.now(timezone.utc)
        counts: dict = {"lineup_lock_reminders": 0, "lineup_problems": 0, "reminders_important": 0}
        error_msg: Optional[str] = None
        try:
            counts = await run_once(db, create_notification)
            if any(counts.values()):
                log.info(f"notification_worker: emitted {counts}")
        except Exception as e:
            error_msg = str(e)
            log.error(f"notification_worker loop error: {e}")
        try:
            await db.notification_worker_runs.update_one(
                {"_id": "latest"},
                {"$set": {
                    "_id": "latest",
                    "started_at": started_at.isoformat(),
                    "finished_at": datetime.now(timezone.utc).isoformat(),
                    "counts": counts,
                    "error": error_msg,
                }},
                upsert=True,
            )
        except Exception:
            pass  # heartbeat write must never crash the worker
        await asyncio.sleep(interval_seconds)
