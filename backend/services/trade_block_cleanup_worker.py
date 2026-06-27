"""Iter 230ap — Trade-Block hygiene worker.

Two cleanup passes, run on a 6-hour cadence:

  1. **Backfill missing names** — trade_block rows with `item_type ==
     "player"` whose `name` is null/missing/empty are looked up in the
     `players` collection. Hits are updated with name + position +
     nhl_team + season stats (matches what `POST /trade-block` writes
     on a fresh listing). Without this, the Trade Block UI shows
     "Unknown" cards for these stale rows.

  2. **Prune orphan rows** — trade_block rows whose `player_id` no
     longer resolves to any player (player was deleted / migrated) and
     where the backfill couldn't recover the name. Deletes the row so
     the UI doesn't render forever-broken "Unknown" entries.

A heartbeat is written to `db.trade_block_cleanup_runs/_id="latest"`
every pass for observability.
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId

logger = logging.getLogger("trade_block_cleanup_worker")


def _is_blank(value) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


async def run_once(db) -> dict:
    """Single pass — backfill missing names from the `players`
    collection and prune orphan rows whose player_id no longer
    resolves. Returns counts for the heartbeat."""
    counts = {"checked": 0, "backfilled": 0, "pruned": 0, "skipped": 0}

    # Step 1 — collect every row with a missing name (player + pick).
    broken_rows = []
    async for row in db.trade_block.find({
        "$or": [
            {"name": None},
            {"name": ""},
            {"name": {"$exists": False}},
        ],
    }):
        counts["checked"] += 1
        broken_rows.append(row)

    if not broken_rows:
        return counts

    # Iter 230ap — Pick-type rows: rebuild the name from year/round if
    # available; otherwise prune (completely broken row).
    player_rows = []
    for row in broken_rows:
        if row.get("item_type") == "pick":
            year = row.get("pick_year")
            rnd = row.get("pick_round")
            number = row.get("pick_number")
            if year and rnd:
                label = f"{year} R{rnd}"
                if number:
                    label += f" #{number}"
                await db.trade_block.update_one(
                    {"_id": row["_id"]},
                    {"$set": {"name": label, "position": "PICK"}},
                )
                counts["backfilled"] += 1
            else:
                # No usable metadata → prune.
                await db.trade_block.delete_one({"_id": row["_id"]})
                counts["pruned"] += 1
        else:
            player_rows.append(row)

    # Step 2 — batch-fetch player docs for the rows that have a
    # player_id. Hits → backfill. Misses → prune in step 3.
    candidate_pids = []
    for row in player_rows:
        pid = row.get("player_id")
        if not pid:
            continue
        try:
            candidate_pids.append(ObjectId(pid))
        except Exception:
            continue

    player_by_id: dict = {}
    if candidate_pids:
        cursor = db.players.find(
            {"_id": {"$in": candidate_pids}},
        )
        async for p in cursor:
            player_by_id[str(p["_id"])] = p

    for row in player_rows:
        pid = row.get("player_id")
        if not pid:
            # No player_id at all — can't recover. Prune it.
            await db.trade_block.delete_one({"_id": row["_id"]})
            counts["pruned"] += 1
            continue
        player = player_by_id.get(str(pid))
        if not player:
            # Orphan — referenced player no longer exists. Prune.
            await db.trade_block.delete_one({"_id": row["_id"]})
            counts["pruned"] += 1
            continue

        # Backfill — mirror what POST /trade-block writes for a fresh
        # listing so the row looks identical to one created today.
        season = player.get("season_stats") or {}
        gp = int(season.get("games_played") or player.get("games_played") or 0)
        update_set = {
            "name": player.get("name") or "Unknown",
            "position": player.get("position") or row.get("position") or "—",
            "nhl_team": player.get("team", row.get("nhl_team", "")),
            "games_played": gp,
            "goals": int(season.get("goals") or player.get("goals") or 0),
            "assists": int(season.get("assists") or player.get("assists") or 0),
            "points": int(season.get("points") or player.get("points") or 0),
            "plus_minus": int(season.get("plus_minus") or player.get("plus_minus") or 0),
        }
        fpts = float(player.get("fantasy_points") or season.get("fantasy_points") or 0)
        update_set["fantasy_points"] = round(fpts, 1)
        update_set["fantasy_ppg"] = round(fpts / gp, 2) if gp else 0.0
        # Iter 230ap — Also backfill age when present so the UI's "Age N"
        # chip renders correctly on the recovered card.
        if player.get("age") is not None:
            update_set["age"] = player["age"]

        await db.trade_block.update_one(
            {"_id": row["_id"]},
            {"$set": update_set},
        )
        counts["backfilled"] += 1

    return counts


async def trade_block_cleanup_loop(db, interval_seconds: int = 6 * 3600):
    """Long-running asyncio task. Runs `run_once` immediately on
    startup so existing broken rows are fixed without waiting for the
    first cadence tick, then every `interval_seconds` thereafter
    (default 6 hours)."""
    # First pass runs right away.
    first = True
    while True:
        started_at = datetime.now(timezone.utc)
        counts = {"checked": 0, "backfilled": 0, "pruned": 0, "skipped": 0}
        error: Optional[str] = None
        try:
            counts = await run_once(db)
            if counts.get("backfilled") or counts.get("pruned"):
                logger.info(
                    f"trade_block_cleanup: backfilled={counts['backfilled']} "
                    f"pruned={counts['pruned']}"
                )
        except Exception as e:
            error = str(e)
            logger.error(f"trade_block_cleanup loop error: {e}")
        try:
            await db.trade_block_cleanup_runs.update_one(
                {"_id": "latest"},
                {"$set": {
                    "_id": "latest",
                    "started_at": started_at.isoformat(),
                    "finished_at": datetime.now(timezone.utc).isoformat(),
                    "counts": counts,
                    "error": error,
                }},
                upsert=True,
            )
        except Exception:
            pass
        first = False  # noqa: F841 — keep for clarity / future "first pass only" logic
        await asyncio.sleep(interval_seconds)
