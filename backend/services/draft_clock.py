"""Pick-clock rules shared by the draft timer worker and the auto-pick route.

There is exactly one answer to "has this pick's clock run out?". The timer
worker fires timeouts with it, and `POST /drafts/{id}/auto-pick` (called from a
member's browser when its countdown reaches zero) enforces it, so the two can
never disagree. Changing a rule here changes both.
"""
from __future__ import annotations

from datetime import datetime, timezone

# The worker waits a little past the deadline so a member's browser (which
# fires at its own countdown zero) gets the first shot at the auto-pick.
GRACE_SECONDS = 3
# A browser's countdown is computed from the server timestamp but compared
# against the client's own clock, so it can reach zero a moment before the
# server's deadline. The auto-pick route accepts requests this much early;
# it must NOT wait out the worker's grace or the browser's one request per
# pick would always be rejected.
BROWSER_CLOCK_SKEW_SECONDS = 2
DEFAULT_PICK_SECONDS = 60
# While any trade in the league is in one of these states, the tighter
# personal pick timer sits out (the league-wide clock still runs).
OPEN_TRADE_STATUSES = ("pending_review", "under_review", "pending_veto")


def parse_iso(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def base_pick_seconds(draft: dict) -> int:
    """`time_per_pick` is the canonical field set by `create_draft`;
    `pick_time_seconds` is the legacy alias some older drafts still carry.
    Honour both, in that order, before falling back to the default. (Ignoring
    `time_per_pick` once timed out a 4-hour-pick draft after 60 seconds.)"""
    return int(draft.get("time_per_pick") or draft.get("pick_time_seconds") or DEFAULT_PICK_SECONDS)


def personal_cap_seconds(draft: dict):
    """Per-pick personal timer cap in seconds, or None when disabled."""
    cap = draft.get("personal_pick_timer_seconds")
    try:
        return int(cap) if cap else None
    except (TypeError, ValueError):
        return None


async def trade_voting_pause_active(db, draft: dict) -> bool:
    """True when a trade in this league is under review and the personal timer
    should pause. Only relevant when a personal cap is configured."""
    league_id = draft.get("league_id")
    if not personal_cap_seconds(draft) or not league_id:
        return False
    try:
        return await db.trades.count_documents({
            "league_id": league_id,
            "status": {"$in": list(OPEN_TRADE_STATUSES)},
        }) > 0
    except Exception:
        return False


def effective_pick_seconds(draft: dict, trade_voting_pause: bool = False):
    """Returns (seconds, used_personal). The personal cap only wins when it is
    tighter than the main clock and no trade vote is pausing it."""
    pick_time = base_pick_seconds(draft)
    cap = personal_cap_seconds(draft)
    if cap and not trade_voting_pause and cap < pick_time:
        return cap, True
    return pick_time, False


def pick_clock_expired(draft: dict, now: datetime, trade_voting_pause: bool = False,
                       grace_seconds: float = GRACE_SECONDS) -> bool:
    """True once `current_pick_started_at + effective seconds + grace_seconds`
    has passed. The worker uses the default grace (+3s); the HTTP route passes
    a small negative value to tolerate browser clock skew. A draft with no
    running clock (no start timestamp) is never expired."""
    started = parse_iso(draft.get("current_pick_started_at"))
    if not started:
        return False
    seconds, _ = effective_pick_seconds(draft, trade_voting_pause)
    return now.timestamp() >= started.timestamp() + seconds + grace_seconds


async def is_within_clock_window(draft: dict, now: datetime) -> bool:
    """Iter 231y — Time-of-day clock window guard.

    A draft can optionally restrict its pick clock to a daily window
    (e.g. 9am-9pm in the league's local timezone) so timeouts don't
    fire overnight. Honours `clock_starts_at` / `clock_stops_at`
    (HH:MM strings) in `clock_timezone` (IANA name, default UTC).

    Returns True when no window is configured (legacy default) OR
    when `now` falls inside the configured window.
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
