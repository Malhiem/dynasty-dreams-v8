"""Iter 231q — Draft pick timer worker.

When a manager is on the clock but the pick timer elapses without a
selection, the clock should "roll over" — the team auto-picks the
best available player (or the next un-drafted player in their queue
when `missed_pick_action != "defer-to-user"`) and the next manager is
on the clock.

Without this worker the auto-pick only fires when the frontend's local
countdown hits 0 AND someone has the Draft Room page open. If everyone
disconnected, the draft would stall. This loop covers that offline
case + acts as a server-authoritative belt-and-suspenders.

Implementation:
  • Polls every 15s — short enough that an expired pick clock catches
    up within ~15s after it elapses, long enough to not thrash Mongo
    for leagues with hundreds of active drafts.
  • Only acts on `status: "active"` drafts that have
    `current_pick_started_at` set AND are not paused (`timer_paused !=
    True`) AND `missed_pick_action != "defer-to-user"` (in that mode
    we wait for the owner to choose via the dialog).
  • Uses `pick_time_seconds` from the draft doc; falls back to 60s if
    unset (matches the frontend default).
  • Re-uses `services/draft_helpers.perform_one_auto_pick` so the
    behaviour matches the manual `/auto-pick` endpoint exactly.
"""
import asyncio
import logging
from datetime import datetime, timezone

from bson import ObjectId

logger = logging.getLogger("draft_pick_timer_worker")


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


async def _is_within_clock_window(draft: dict, now: datetime) -> bool:
    """Iter 231y — Time-of-day clock window guard.

    A draft can optionally restrict its pick clock to a daily window
    (e.g. 9am-9pm in the league's local timezone) so timeouts don't
    fire overnight. Honours `clock_starts_at` / `clock_stops_at`
    (HH:MM strings) in `clock_timezone` (IANA name, default UTC).

    Returns True when no window is configured (legacy default) OR
    when `now` falls inside the configured window. Returns False to
    signal the worker should skip this draft on this pass.
    """
    starts = draft.get("clock_starts_at")
    stops = draft.get("clock_stops_at")
    if not starts and not stops:
        return True  # No window configured — clock runs 24/7 (legacy default).
    tz_name = draft.get("clock_timezone") or "UTC"
    try:
        from zoneinfo import ZoneInfo
        local_now = now.astimezone(ZoneInfo(tz_name))
    except Exception:
        local_now = now
    cur_minutes = local_now.hour * 60 + local_now.minute

    def _parse_hhmm(s):
        try:
            h, m = str(s).split(":")[:2]
            return int(h) * 60 + int(m)
        except Exception:
            return None

    start_min = _parse_hhmm(starts) if starts else 0
    stop_min = _parse_hhmm(stops) if stops else 24 * 60
    if start_min is None or stop_min is None:
        return True  # Malformed window — fail open (don't block picks).
    if start_min <= stop_min:
        # Same-day window (e.g. 09:00–21:00).
        return start_min <= cur_minutes < stop_min
    # Window crosses midnight (e.g. 21:00–06:00).
    return cur_minutes >= start_min or cur_minutes < stop_min


async def run_once(db, *, draft_ids_filter: list[str] | None = None) -> dict:
    """Single pass: find active drafts whose current pick clock has
    elapsed, and trigger an auto-pick. Returns counts for observability.

    `draft_ids_filter` — Iter 231x test-isolation hook. When provided,
    only scans the listed draft ids instead of every active draft in
    the DB. Production callers (the long-running loop) always pass
    None so behaviour is unchanged. Tests pass their own seeded
    draft_id(s) so a unit test can never touch a production draft.
    """
    from routes.draft_helpers import perform_one_auto_pick
    from draft_engine import get_team_for_pick

    now = datetime.now(timezone.utc)
    counts = {"checked": 0, "expired": 0, "picked": 0, "skipped": 0, "errors": 0, "ownerless_picks": 0}

    query: dict = {"status": "active"}
    if draft_ids_filter is not None:
        query["_id"] = {"$in": [ObjectId(d) for d in draft_ids_filter]}

    async for draft in db.drafts.find(query):
        counts["checked"] += 1
        if draft.get("timer_paused"):
            counts["skipped"] += 1
            continue

        # Iter 231ab — Resolve the team currently on the clock so we can
        # detect ownerless (Open Slot) teams. Open Slot teams have no
        # human to pick for them, so the worker auto-picks IMMEDIATELY
        # regardless of clock window, missed_pick_action, or remaining
        # time — the draft can't progress otherwise.
        try:
            on_clock_abbr = get_team_for_pick(
                draft.get("team_abbrs") or [],
                draft.get("current_pick", 1),
                draft.get("snake_draft", True),
            )
        except Exception:
            on_clock_abbr = None
        on_clock_team_id = (draft.get("team_map") or {}).get(on_clock_abbr, {}).get("id") if on_clock_abbr else None
        on_clock_team = None
        if on_clock_team_id:
            try:
                on_clock_team = await db.teams.find_one({"_id": ObjectId(on_clock_team_id)})
            except Exception:
                on_clock_team = None
        is_ownerless = bool(
            on_clock_team is not None
            and not on_clock_team.get("owner_id")
            and not (on_clock_team.get("co_owner_ids") or [])
        )

        if is_ownerless:
            # Iter 231ab — Fire immediately; bypass defer-to-user + clock
            # window + deadline checks. No grace period — the team has
            # no owner who could possibly act.
            # Iter 231ad — Rate-limit: at most 1 ownerless auto-pick per
            # draft per tick. With ~6 worker ticks per minute (10s
            # cadence), an 8-team Open-Slot block now takes ~80 seconds
            # to fully resolve instead of being decided in <1ms — gives
            # commissioners time to react ("oh no, undo!") + matches the
            # cadence of real-owner picks so chat / roster updates don't
            # firehose.
            # Iter 231ae — Also honour `admin_managed=True`: when the
            # commissioner has explicitly opted the team into manual
            # admin management (for owner-removal continuity), DO NOT
            # auto-pick. The admin will pick manually via the UI.
            if on_clock_team.get("admin_managed"):
                counts["skipped"] += 1
                continue
            counts["expired"] += 1
            try:
                await perform_one_auto_pick(str(draft["_id"]), source="ownerless")
                counts["picked"] += 1
                counts["ownerless_picks"] += 1
            except Exception as e:
                counts["errors"] += 1
                logger.error(f"draft_pick_timer_worker ownerless auto-pick failed for {draft['_id']}: {e}")
            continue

        if (draft.get("missed_pick_action") or "auto-best") == "defer-to-user":
            # Don't auto-pick when the league configured the timer to
            # defer to the owner's dialog choice.
            counts["skipped"] += 1
            continue
        # Iter 231y — Honour the time-of-day clock window (e.g. only
        # auto-pick between 9am–9pm in the league's timezone). Drafts
        # without a window configured fall through (legacy 24/7 behaviour).
        if not await _is_within_clock_window(draft, now):
            counts["skipped"] += 1
            continue
        started = _parse_iso(draft.get("current_pick_started_at"))
        if not started:
            counts["skipped"] += 1
            continue
        # Iter 231y — `time_per_pick` is the canonical field set by
        # `create_draft` (CreateDraftRequest); `pick_time_seconds` is
        # the legacy alias some older drafts have. Honour BOTH in that
        # order — without this, TFHL Inaugural Draft (configured for
        # 4-hour picks via `time_per_pick: 14400`) was being timed out
        # after just 60s because `pick_time_seconds` was None and the
        # worker fell back to the 60s default.
        pick_time = int(
            draft.get("time_per_pick")
            or draft.get("pick_time_seconds")
            or 60
        )
        # 3s grace so the worker isn't racing the frontend's own auto-pick.
        deadline = started.timestamp() + pick_time + 3
        if now.timestamp() < deadline:
            continue
        counts["expired"] += 1
        try:
            await perform_one_auto_pick(str(draft["_id"]), source="timeout")
            counts["picked"] += 1
        except Exception as e:
            counts["errors"] += 1
            logger.error(f"draft_pick_timer_worker auto-pick failed for {draft['_id']}: {e}")

    return counts


async def draft_pick_timer_loop(db, interval_seconds: int = 15):
    """Long-running asyncio task. Default 15s cadence."""
    while True:
        started_at = datetime.now(timezone.utc)
        counts = {"checked": 0, "expired": 0, "picked": 0, "skipped": 0, "errors": 0}
        error_msg = None
        try:
            counts = await run_once(db)
            if counts.get("picked"):
                logger.info(
                    f"draft_pick_timer_worker: auto-picked {counts['picked']} "
                    f"of {counts['expired']} expired clocks"
                )
        except Exception as e:
            error_msg = str(e)
            logger.error(f"draft_pick_timer loop error: {e}")
        try:
            await db.draft_pick_timer_runs.update_one(
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
            pass
        await asyncio.sleep(interval_seconds)
