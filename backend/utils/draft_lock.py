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


async def get_locking_draft(db, league_id: str) -> Optional[dict]:
    """Returns the draft doc that's currently locking the FA pool for
    `league_id`, or ``None`` if pickups are open. Prefers `active` /
    `in_progress` drafts over merely `scheduled` ones so the message
    the caller renders matches the phase the league is actually in.
    """
    if not league_id:
        return None
    draft = await db.drafts.find_one({
        "league_id": league_id,
        "status": {"$in": ["active", "in_progress", "paused"]},
    })
    if draft:
        return draft
    return await db.drafts.find_one({
        "league_id": league_id,
        "status": "scheduled",
    })


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
