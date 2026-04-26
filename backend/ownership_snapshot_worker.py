"""Daily ownership snapshot worker.

Writes one `ownership_snapshots` row per NHL player capturing the cross-DD
ownership at that moment. Runs forever on a configurable interval (default
24h). The Players page reads the most-recent row that's ≥ 7 days old to
compute `pct_change_7d`, so once 7+ days of natural history accumulate, the
% Change column is fully real (synthetic seed becomes redundant).

Idempotent within a single calendar day — keys by `snapshot_date` (YYYY-MM-DD)
so re-running never duplicates rows. Multiple invocations per day re-upsert
the same row (last write wins).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

logger = logging.getLogger("ownership_snapshots")

DEFAULT_INTERVAL_SEC = 24 * 60 * 60  # 24h


async def snapshot_once(db) -> dict:
    """Capture cross-DD ownership for every player. Idempotent per-day.

    Returns: {"date": "YYYY-MM-DD", "players": int, "rows_upserted": int}
    """
    now = datetime.now(timezone.utc)
    snapshot_date = now.strftime("%Y-%m-%d")

    total_teams = await db.teams.count_documents({})
    if total_teams == 0:
        logger.info("snapshot skipped: no teams in DB yet")
        return {"date": snapshot_date, "players": 0, "rows_upserted": 0}

    # Aggregate ownership in a single pipeline rather than N count_documents
    # calls. Each player rostered by ≥ 1 team produces a row; we'll fill in
    # zeros for the rest below.
    owned_counts: dict[str, int] = {}
    async for row in db.teams.aggregate([
        {"$unwind": {"path": "$roster", "preserveNullAndEmptyArrays": False}},
        {"$group": {"_id": "$roster", "count": {"$sum": 1}}},
    ]):
        owned_counts[str(row["_id"])] = int(row["count"])

    upserts = 0
    players_seen = 0
    async for p in db.players.find({}, {"_id": 1}):
        pid = str(p["_id"])
        players_seen += 1
        owned = owned_counts.get(pid, 0)
        pct = round(100 * owned / total_teams, 1) if total_teams else 0.0
        await db.ownership_snapshots.update_one(
            {"player_id": pid, "snapshot_date": snapshot_date},
            {"$set": {
                "player_id": pid,
                "snapshot_date": snapshot_date,
                "snapshot_at": now,
                "global_owned": owned,
                "global_total": total_teams,
                "global_pct": pct,
            }},
            upsert=True,
        )
        upserts += 1

    logger.info(
        "ownership snapshot %s: %d players × %d teams (%d rows upserted)",
        snapshot_date, players_seen, total_teams, upserts,
    )
    return {"date": snapshot_date, "players": players_seen, "rows_upserted": upserts}


async def ownership_snapshot_loop(db, interval_sec: int = DEFAULT_INTERVAL_SEC):
    """Run snapshot_once forever on the given interval. Cancelled cleanly on
    FastAPI shutdown."""
    logger.info("Ownership snapshot worker started (interval=%ds)", interval_sec)
    # Take a first snapshot immediately on boot — covers the case where the
    # process has just been restarted past midnight UTC.
    try:
        await snapshot_once(db)
    except Exception as e:
        logger.warning("initial ownership snapshot failed: %s", e)

    while True:
        try:
            await asyncio.sleep(interval_sec)
            await snapshot_once(db)
        except asyncio.CancelledError:
            logger.info("ownership snapshot loop cancelled")
            raise
        except Exception as e:
            logger.exception("ownership snapshot iteration failed: %s", e)
            # Don't tight-loop on persistent errors; retry on next tick.
            await asyncio.sleep(60)
