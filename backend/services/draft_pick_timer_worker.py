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

    now = datetime.now(timezone.utc)
    counts = {"checked": 0, "expired": 0, "picked": 0, "skipped": 0, "errors": 0}

    query: dict = {"status": "active"}
    if draft_ids_filter is not None:
        query["_id"] = {"$in": [ObjectId(d) for d in draft_ids_filter]}

    async for draft in db.drafts.find(query):
        counts["checked"] += 1
        if draft.get("timer_paused"):
            counts["skipped"] += 1
            continue
        if (draft.get("missed_pick_action") or "auto-best") == "defer-to-user":
            # Don't auto-pick when the league configured the timer to
            # defer to the owner's dialog choice.
            counts["skipped"] += 1
            continue
        started = _parse_iso(draft.get("current_pick_started_at"))
        if not started:
            counts["skipped"] += 1
            continue
        pick_time = int(draft.get("pick_time_seconds") or 60)
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
