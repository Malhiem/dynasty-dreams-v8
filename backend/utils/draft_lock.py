"""Iter 232N.15 — Draft-lock guard for player pickups.

When a league has an `active` or `scheduled` draft, the free-agent /
waiver-claim flows must reject pickups so managers can't front-run the
draft pool. Kept in one place so `precheck_waiver_claim`,
`/roster/{team_id}/add`, and `/waivers/claim` never disagree about the
lock semantics.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId

_LOCKING_STATUSES = ("active", "scheduled", "in_progress", "paused")

# Iter 232N.70 — Signals that a draft doc represents a real, correctly
# configured draft (not an orphan / stub / leftover from an earlier
# test run). We require at least ONE of these before we let the doc
# lock the free-agent pool. This defends against the "why is there a
# draft running if no draft has been set?" bug in sandbox leagues
# where an old draft doc lingers with only `status=in_progress` and
# no timing or ordering signal.
_REAL_DRAFT_SIGNALS = (
    "scheduled_at", "scheduled_time", "clock_starts_at", "started_at",
    "on_the_clock_team_id", "current_team_id",
    "pick_order", "draft_order", "total_rounds",
)


def _looks_like_real_draft(draft: dict) -> bool:
    """True when the draft doc has at least one non-empty signal that
    a real draft has been configured. Rejects stub / orphan docs that
    were created outside the standard commissioner setup flow."""
    if not draft:
        return False
    for key in _REAL_DRAFT_SIGNALS:
        val = draft.get(key)
        if val is None:
            continue
        if isinstance(val, (list, dict, str)) and len(val) == 0:
            continue
        return True
    return False


async def get_locking_draft(db, league_id: str) -> Optional[dict]:
    """Returns the draft doc that's currently locking the FA pool for
    `league_id`, or ``None`` if pickups are open. Prefers `active` /
    `in_progress` drafts over merely `scheduled` ones so the message
    the caller renders matches the phase the league is actually in.

    Iter 232N.70 — Orphan draft docs (status=in_progress but no
    scheduling / pick_order / on_the_clock signal) are ignored so
    they don't spuriously block free-agent pickups in sandbox and
    otherwise-cleanly-configured leagues.
    """
    if not league_id:
        return None
    # Iter 232N.70 — Prefer active/in_progress/paused, then scheduled.
    # For each status band, iterate all matches and return the first
    # that looks like a real draft. Using `find_one` isn't enough: if
    # an orphan happens to sort first, we'd return None even when a
    # real draft exists in the same status band.
    active = await db.drafts.find({
        "league_id": league_id,
        "status": {"$in": ["active", "in_progress", "paused"]},
    }).to_list(50)
    for d in active:
        if _looks_like_real_draft(d):
            return d
    scheduled = await db.drafts.find({
        "league_id": league_id,
        "status": "scheduled",
    }).to_list(50)
    for d in scheduled:
        if _looks_like_real_draft(d):
            return d
    return None


def format_draft_lock_message(draft: dict) -> str:
    """Human-facing copy for the pickup toast + backend `detail`.
    Kept synchronous so the frontend precheck payload can splat the
    same string the 400 response would carry.
    """
    name = draft.get("name") or "the upcoming draft"
    status = (draft.get("status") or "").lower()
    if status in ("active", "in_progress", "paused"):
        return (
            f"This player isn't eligible for pickup while {name} is "
            f"in progress — try again after the draft wraps up."
        )
    # Scheduled path — surface the timestamp when we have one.
    scheduled_time = draft.get("scheduled_time") or draft.get("clock_starts_at")
    when = ""
    if scheduled_time:
        try:
            dt = (
                scheduled_time if isinstance(scheduled_time, datetime)
                else datetime.fromisoformat(str(scheduled_time).replace("Z", "+00:00"))
            )
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            when = f" (starts {dt.strftime('%b %-d, %-I:%M %p UTC')})"
        except Exception:
            pass
    return (
        f"This player isn't eligible for pickup until {name} has "
        f"completed{when}."
    )


async def assert_pickups_open(db, league_id: str) -> None:
    """Raise an HTTPException (400) if the league is draft-locked.
    Called from the mutation endpoints so both the direct-add and
    waiver-claim paths honour the same lockout.
    """
    from fastapi import HTTPException
    draft = await get_locking_draft(db, league_id)
    if draft is None:
        return
    raise HTTPException(
        status_code=400,
        detail=format_draft_lock_message(draft),
    )
