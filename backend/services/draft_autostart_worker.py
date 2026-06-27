"""Iter 230ao — Draft auto-start worker.

Boots any draft whose `scheduled_time` has elapsed but is still in
`status: "scheduled"`. Without this worker, the draft only auto-starts
when a manager has the Draft Room page open (via the frontend
countdown hook that calls POST /drafts/{id}/start at 0:00). This worker
covers the offline case — the draft kicks off even if nobody is
watching, fires the pick #1 / pick #2 notifications, and is ready for
picks via the live channel.

Implementation notes:
  • Re-uses `routes.drafts.start_draft` to keep the start path single-
    source-of-truth (refreshes team_abbrs, broadcasts, notifies). We
    invoke the underlying logic by importing the deps and bypassing
    the FastAPI request layer.
  • Polls every 60 seconds — short enough that a draft scheduled to
    start at HH:MM:00 actually starts within ~1 minute, long enough
    not to thrash the DB.
  • Picks up drafts up to 24h after the scheduled time so we don't
    accidentally boot a draft that was meant to be cancelled / wiped.
"""
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from bson import ObjectId

logger = logging.getLogger("draft_autostart_worker")

# Don't auto-start drafts whose scheduled_time is more than this far
# in the past — likely abandoned / cancelled.
MAX_LATE_WINDOW = timedelta(hours=24)


def _parse_iso(value) -> Optional[datetime]:
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


async def _start_one(db, draft_doc) -> bool:
    """Boot a single draft using the same logic as the public
    `start_draft` endpoint. Returns True when the draft was booted in
    this pass (so the caller can count it)."""
    try:
        from routes import drafts as drafts_routes
        from routes.notification_events import (
            EVT_DRAFT_YOUR_TURN, EVT_DRAFT_ON_DECK,
        )

        draft_id = str(draft_doc["_id"])

        # Refresh team_abbrs/team_map from the CURRENT league teams in
        # case the draft was created before all teams joined.
        fresh_teams = await db.teams.find(
            {"league_id": draft_doc["league_id"]}
        ).to_list(200)
        if fresh_teams and len(fresh_teams) > len(draft_doc.get("team_abbrs") or []):
            team_abbrs, team_map = drafts_routes._abbrs_with_dedup(fresh_teams)
        else:
            team_abbrs = draft_doc.get("team_abbrs") or []
            team_map = draft_doc.get("team_map") or {}

        await db.drafts.update_one(
            {"_id": ObjectId(draft_id), "status": "scheduled"},
            {"$set": {
                "status": "active",
                "draft_started": True,
                "early_start": False,
                "current_pick": 1,
                "started_at": datetime.now(timezone.utc).isoformat(),
                "current_pick_started_at": datetime.now(timezone.utc).isoformat(),
                "team_abbrs": team_abbrs,
                "team_map": team_map,
            }}
        )

        # System chat note
        system_msg = {
            "id": f"sys-autostart-{datetime.now(timezone.utc).timestamp()}",
            "type": "pick",
            "sender": "System",
            "text": "Draft has started automatically (scheduled time reached). Timer is running.",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        await db.drafts.update_one(
            {"_id": ObjectId(draft_id)},
            {"$push": {"chat_messages": system_msg}},
        )

        # Broadcast over the draft room channel so any live clients
        # update immediately.
        try:
            await drafts_routes._broadcast(
                f"draft_{draft_id}", "draft_started",
                {
                    "draft_id": draft_id,
                    "early_start": False,
                    "team_abbrs": team_abbrs,
                    "on_the_clock": team_abbrs[0] if team_abbrs else None,
                    "auto_started": True,
                },
            )
            await drafts_routes._broadcast(
                f"draft_{draft_id}", "draft_chat", system_msg,
            )
        except Exception as e:
            logger.debug(f"draft auto-start broadcast skipped: {e}")

        # Fire pick #1 / pick #2 notifications — same flow as
        # start_draft, just inlined so we don't need to mock a Request.
        try:
            picks_to_notify = [
                (EVT_DRAFT_YOUR_TURN, 1, "You're on the clock!",
                 "Pick #1 — make your selection."),
                (EVT_DRAFT_ON_DECK, 2, "On deck",
                 "Pick #2 — you're up next."),
            ]
            league_id_str = str(draft_doc["league_id"])
            for (event, pick_no, title, body) in picks_to_notify:
                if pick_no > len(team_abbrs):
                    continue
                abbr = team_abbrs[pick_no - 1]
                team_id = (team_map.get(abbr) or {}).get("id")
                if not team_id:
                    continue
                team = await db.teams.find_one(
                    {"_id": ObjectId(team_id)},
                    {"owner_id": 1, "co_owner_ids": 1, "name": 1},
                )
                if not team:
                    continue
                owners = [team.get("owner_id")] + list(team.get("co_owner_ids") or [])
                for uid in [u for u in owners if u]:
                    await drafts_routes.create_notification(
                        uid, event, title, body, league_id_str, "/draft-room",
                    )
        except Exception as e:
            logger.debug(f"draft auto-start notify skipped: {e}")

        return True
    except Exception as e:
        logger.error(f"draft auto-start failed for {draft_doc.get('_id')}: {e}")
        return False


async def run_once(db) -> dict:
    """Single pass: find scheduled drafts whose start time has elapsed
    (within the MAX_LATE_WINDOW) and boot them. Returns a counts dict
    for observability."""
    now = datetime.now(timezone.utc)
    earliest = now - MAX_LATE_WINDOW

    counts = {"checked": 0, "started": 0, "skipped": 0}

    async for draft in db.drafts.find({"status": "scheduled"}):
        counts["checked"] += 1
        sched = _parse_iso(draft.get("scheduled_time"))
        if not sched:
            counts["skipped"] += 1
            continue
        if sched > now:
            continue  # not due yet
        if sched < earliest:
            # Stale — too far in the past, skip to avoid resurrecting
            # cancelled drafts.
            counts["skipped"] += 1
            continue
        ok = await _start_one(db, draft)
        if ok:
            counts["started"] += 1

    return counts


async def draft_autostart_loop(db, interval_seconds: int = 60):
    """Long-running asyncio task. Sleeps `interval_seconds` between
    passes (default 60s). Heartbeats to `draft_autostart_runs/_id=latest`
    every pass for admin observability."""
    while True:
        started_at = datetime.now(timezone.utc)
        counts = {"checked": 0, "started": 0, "skipped": 0}
        error_msg: Optional[str] = None
        try:
            counts = await run_once(db)
            if counts.get("started", 0):
                logger.info(f"draft_autostart_worker: started {counts['started']} drafts")
        except Exception as e:
            error_msg = str(e)
            logger.error(f"draft_autostart loop error: {e}")
        try:
            await db.draft_autostart_runs.update_one(
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
