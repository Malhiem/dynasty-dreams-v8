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


async def _apply_hibernation_grace(db, now: datetime, interval_seconds: int) -> int:
    """Iter 232N.48 — Compensate for worker hibernation.

    Preview / auto-scaled backends occasionally sleep (K8s scale-to-zero,
    container restart, deploy). While the worker is asleep, no auto-pick
    can fire — so when the clock resumes, any draft whose deadline
    quietly elapsed *inside* the sleep window would previously auto-pick
    immediately on wake, punishing the on-clock manager for downtime
    they didn't cause.

    Detection: read the last `draft_pick_timer_runs.latest` heartbeat.
    If `now - finished_at > 3 × interval_seconds`, the worker was
    effectively down for `gap` seconds. For every active draft whose
    `current_pick_started_at` plus `time_per_pick + 3s` grace falls
    inside `[finished_at, now]`, push `current_pick_started_at` forward
    by `gap` so the manager gets their full remaining window fresh.

    Returns the number of drafts whose clocks were corrected. Safe to
    call every tick — no-ops when the previous tick was recent.
    """
    latest = await db.draft_pick_timer_runs.find_one({"_id": "latest"})
    if not latest:
        return 0
    last_finished = _parse_iso(latest.get("finished_at"))
    if not last_finished:
        return 0
    gap = (now - last_finished).total_seconds()
    # Only correct after a meaningful gap. 3× the interval catches real
    # hibernation while ignoring the routine ~15s cadence.
    if gap <= interval_seconds * 3:
        return 0

    corrected = 0
    async for draft in db.drafts.find({"status": "active"}):
        started = _parse_iso(draft.get("current_pick_started_at"))
        if not started:
            continue
        if draft.get("timer_paused"):
            continue
        pick_time = int(
            draft.get("time_per_pick")
            or draft.get("pick_time_seconds")
            or 60
        )
        deadline_ts = started.timestamp() + pick_time + 3
        # Only correct clocks whose deadline fell INSIDE the downtime
        # window. A clock whose deadline was already past *before* the
        # worker went down is a genuine expiry and should still fire.
        if not (last_finished.timestamp() <= deadline_ts <= now.timestamp()):
            continue
        # Push the clock forward by exactly the downtime so the manager
        # loses zero seconds of their window.
        new_started_dt = started + (now - last_finished)
        # Cap the shift at `now` so we never set the clock in the
        # future (defensive; a bug elsewhere shouldn't push clocks into
        # tomorrow).
        if new_started_dt > now:
            new_started_dt = now
        await db.drafts.update_one(
            {"_id": draft["_id"], "status": "active"},
            {"$set": {
                "current_pick_started_at": new_started_dt.isoformat(),
                "last_hibernation_correction": {
                    "at": now.isoformat(),
                    "gap_seconds": int(gap),
                    "original_started_at": started.isoformat(),
                },
            }},
        )
        corrected += 1
        logger.warning(
            f"draft_pick_timer_worker: hibernation grace applied to draft "
            f"{draft['_id']} (gap={int(gap)}s, pushed clock by {int(gap)}s)"
        )
    return corrected


def _team_owners_present_in_draft_room(draft_id: str, team: dict | None) -> bool:
    """Iter 232N.45 — Return True when at least one owner (or co-owner)
    of `team` currently has an authenticated Socket.IO session in the
    given draft room.

    Used by the pick-timer worker to decide whether a `defer-to-user`
    draft should auto-pick when its clock elapses: if nobody who could
    respond to the "make your pick" dialog is actually in the room, the
    worker fires an auto-pick so the draft doesn't stall forever waiting
    for an offline manager.

    Presence data lives in `server.connected_users`, populated on every
    `join_room` socket event. Imported lazily to avoid a circular
    import at module load time.
    """
    if not team:
        return False
    owner_ids = {team.get("owner_id"), *(team.get("co_owner_ids") or [])}
    owner_ids.discard(None)
    owner_ids = {str(u) for u in owner_ids}
    if not owner_ids:
        return False
    try:
        from server import connected_users  # noqa: WPS433 (runtime import)
    except Exception:
        return False
    room = f"draft_{draft_id}"
    for info in connected_users.values():
        if info.get("room_id") == room and str(info.get("user_id")) in owner_ids:
            return True
    return False


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
    counts = {"checked": 0, "expired": 0, "picked": 0, "skipped": 0, "errors": 0, "ownerless_picks": 0, "hibernation_corrections": 0}

    # Iter 232N.48 — Compensate for downtime BEFORE scanning drafts so
    # clocks pushed forward by the grace aren't immediately auto-picked
    # in the same tick.
    if draft_ids_filter is None:
        try:
            counts["hibernation_corrections"] = await _apply_hibernation_grace(db, now, 15)
        except Exception as e:
            logger.error(f"draft_pick_timer_worker hibernation grace failed: {e}")

    query: dict = {"status": "active"}
    if draft_ids_filter is not None:
        query["_id"] = {"$in": [ObjectId(d) for d in draft_ids_filter]}

    async for draft in db.drafts.find(query):
        counts["checked"] += 1
        if draft.get("timer_paused"):
            counts["skipped"] += 1
            continue

        if draft.get("salary_blocked"):
            counts["skipped"] += 1
            continue
        # Iter 231ad — Guard against zombie drafts with empty `team_abbrs`.
        # `get_team_for_pick` does `pick % len(team_abbrs)` which raises
        # ZeroDivisionError on empty arrays. Found 18 such drafts in the
        # preview DB throwing 'integer division or modulo by zero' every
        # 10s in the worker log. These are unusable drafts (no teams to
        # pick for) — skip them entirely and bump the error counter so
        # we can surface a fix-it-now alert.
        if not (draft.get("team_abbrs") or []):
            counts["skipped"] += 1
            counts["errors"] += 1
            logger.warning(
                f"draft_pick_timer_worker: draft {draft['_id']} has empty team_abbrs — skipping (zombie draft)."
            )
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

        # Iter 232N.45 — `defer-to-user` used to skip UNCONDITIONALLY,
        # which meant a draft would stall forever when the on-clock
        # manager was offline (no dialog to click). Now we auto-pick
        # ONLY when the pick clock has fully elapsed AND no owner or
        # co-owner of the on-clock team is currently in this draft's
        # Socket.IO room. If any owner is present, we still defer so
        # they can pick the response themselves.
        deferred_to_user = (draft.get("missed_pick_action") or "auto-best") == "defer-to-user"
        if deferred_to_user:
            if _team_owners_present_in_draft_room(str(draft["_id"]), on_clock_team):
                counts["skipped"] += 1
                continue
            # Owners are offline — fall through to the timer-expiry
            # check below. If the clock hasn't hit 0 yet we still
            # give them the full window to come back online.
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
        # Iter 232N.26 — Personal timer cap. Runs concurrently with the
        # main pick clock; whichever expires first triggers auto-pick.
        # Stored as an int (seconds) or None (feature disabled).
        personal_cap = draft.get("personal_pick_timer_seconds")
        try:
            personal_cap = int(personal_cap) if personal_cap else None
        except (TypeError, ValueError):
            personal_cap = None
        # Iter 232N.26 — Pause the personal timer while ANY trade in
        # this league is under review (pending vote / veto window).
        # The main pick clock is UNAFFECTED — commissioners can still
        # rely on the league-wide cap so the draft never stalls
        # forever. Only the tighter personal cap sits out.
        trade_voting_pause = False
        league_id = draft.get("league_id")
        if personal_cap and league_id:
            try:
                trade_voting_pause = await db.trades.count_documents({
                    "league_id": league_id,
                    "status": {"$in": ["pending_review", "under_review", "pending_veto"]},
                }) > 0
            except Exception:
                trade_voting_pause = False
        effective_seconds = pick_time
        used_personal = False
        if personal_cap and not trade_voting_pause and personal_cap < pick_time:
            effective_seconds = personal_cap
            used_personal = True
        # 3s grace so the worker isn't racing the frontend's own auto-pick.
        deadline = started.timestamp() + effective_seconds + 3
        if now.timestamp() < deadline:
            continue
        counts["expired"] += 1
        try:
            # Iter 232N.26 — Pass source="personal_timeout" when the
            # tighter cap is what fired so downstream analytics /
            # chat messages can distinguish it from a full-clock miss.
            # Iter 232N.45 — `defer_offline_timeout` when a
            # `defer-to-user` draft rolled over because the manager
            # was offline (no dialog could have been shown).
            if used_personal:
                fire_source = "personal_timeout"
            elif deferred_to_user:
                fire_source = "defer_offline_timeout"
            else:
                fire_source = source_default_for_timeout()
            await perform_one_auto_pick(str(draft["_id"]), source=fire_source)
            counts["picked"] += 1
        except Exception as e:
            counts["errors"] += 1
            logger.error(f"draft_pick_timer_worker auto-pick failed for {draft['_id']}: {e}")

    return counts


def source_default_for_timeout() -> str:
    """Iter 232N.26 — Wrapper so future hooks (rate limits, silent
    skip, etc.) have a single tunable audit source."""
    return "timeout"


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
