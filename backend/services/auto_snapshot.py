"""
Iter 218 — Auto-snapshot hook.

Wraps the snapshot helper from `routes.roster_snapshots` and exposes a
fire-and-forget convenience that:
  1. Takes a snapshot of every passed team_id
  2. Tags the snapshot with the trigger event + relevant metadata
  3. Logs but never raises on failure (so a snapshot bug never blocks
     a trade-execute / waiver-process / draft-complete)
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from bson import ObjectId

log = logging.getLogger("auto-snapshot")


async def auto_snapshot(db, team_ids: list, *, trigger: str, metadata: dict | None = None) -> None:
    """Snapshot a batch of teams before a state-changing event."""
    if not team_ids:
        return
    valid_oids = []
    for tid in team_ids:
        try:
            valid_oids.append(ObjectId(str(tid)))
        except Exception:
            continue
    try:
        async for team in db.teams.find({"_id": {"$in": valid_oids}}):
            try:
                await db.roster_snapshots.insert_one({
                    "team_id": str(team["_id"]),
                    "league_id": team.get("league_id"),
                    "owner_id": team.get("owner_id"),
                    "taken_at": datetime.now(timezone.utc).isoformat(),
                    "taken_by": f"auto:{trigger}",
                    "reason": f"auto_pre_{trigger}",
                    "roster": team.get("roster") or [],
                    "lineup": team.get("lineup") or {},
                    "ir": team.get("ir") or [],
                    "taxi": team.get("taxi") or [],
                    "salary_cap_used_cents": team.get("salary_cap_used_cents"),
                    "faab_remaining": team.get("faab_remaining"),
                    "metadata": {"trigger": trigger, **(metadata or {})},
                })
            except Exception as e:
                log.warning(f"auto-snapshot insert failed for team {team.get('_id')}: {e}")
    except Exception as e:
        log.warning(f"auto-snapshot batch failed: {e}")
