"""Iter 175 — Daily player-data backfill worker.

Re-runs the Iter 175 NHL stats backfill once every 24h so that:
  • New NHL call-ups picked up by ingestion get their birth_date +
    career_games_played populated within a day.
  • Career-GP rolls forward each game day so minor-eligibility tracks
    real activity (a 21-year-old who crosses 25 career GP flips from
    minor-eligible → ineligible without any human intervention).
  • Birthdays roll over (a 22-year-old aging into 23 stops being
    minor-eligible).

Wraps the script's core logic but keeps it idempotent: only rows
missing data OR with stale `nhl_data_synced_at` (> 24h ago) are
fetched. Errors during a single iteration never bring down the
worker — we log and retry on the next tick.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone

import httpx

logger = logging.getLogger("player_data_backfill")

DEFAULT_INTERVAL_SEC = 24 * 60 * 60  # 24h
DEFAULT_STALE_AFTER = timedelta(days=1)
NHL_LANDING = "https://api-web.nhle.com/v1/player/{nhl_id}/landing"
TIMEOUT = httpx.Timeout(8.0, connect=4.0)
HEADERS = {"User-Agent": "DynastyDreams/iter175-worker (+contact@dynastydreams)"}

# How many concurrent NHL API requests to fire at once. Keep modest
# (the public endpoint is rate-friendly but not infinitely so) and
# allow override via env for ops tuning.
DEFAULT_CONCURRENCY = int(os.environ.get("PLAYER_DATA_BACKFILL_CONCURRENCY", "8"))


def _age_from_birth_date(bd_str: str | None) -> int | None:
    if not bd_str:
        return None
    try:
        bd = datetime.fromisoformat(bd_str.split("T")[0])
        today = datetime.now(timezone.utc).replace(tzinfo=None)
        return today.year - bd.year - ((today.month, today.day) < (bd.month, bd.day))
    except Exception:
        return None


async def _fetch_player(client: httpx.AsyncClient, nhl_id: int) -> dict | None:
    try:
        r = await client.get(NHL_LANDING.format(nhl_id=nhl_id), timeout=TIMEOUT)
        if r.status_code != 200:
            return None
        return r.json()
    except Exception:
        return None


async def _process_player(http, db, p: dict) -> bool:
    nhl_id = p.get("nhl_id")
    if not nhl_id or int(nhl_id) <= 0:
        return False
    landing = await _fetch_player(http, int(nhl_id))
    if not landing:
        return False
    bd = landing.get("birthDate")
    career_gp = (
        landing.get("careerTotals", {})
        .get("regularSeason", {})
        .get("gamesPlayed")
    )
    update_fields: dict = {}
    if bd:
        update_fields["birth_date"] = bd
    age = _age_from_birth_date(bd)
    if age is not None:
        update_fields["age"] = age
    if career_gp is not None:
        update_fields["career_games_played"] = int(career_gp)
    if landing.get("birthCountry"):
        update_fields["birth_country"] = landing.get("birthCountry")
    if not update_fields:
        return False
    update_fields["nhl_data_synced_at"] = datetime.now(timezone.utc)
    await db.players.update_one({"_id": p["_id"]}, {"$set": update_fields})
    return True


async def backfill_once(
    db,
    stale_after: timedelta = DEFAULT_STALE_AFTER,
    concurrency: int = DEFAULT_CONCURRENCY,
) -> dict:
    """Iterate every NHL player that's missing data OR whose sync is
    older than ``stale_after``. Returns a small summary dict for the
    log line / metrics."""
    cutoff = datetime.now(timezone.utc) - stale_after
    query = {
        # Real NHL IDs only — synthetic prospect IDs are negative.
        "nhl_id": {"$exists": True, "$ne": None, "$gt": 0},
        "player_type": {"$ne": "prospect"},
        "$or": [
            # Anything missing the backfilled fields.
            {"birth_date": {"$in": [None, ""]}},
            {"birth_date": {"$exists": False}},
            {"career_games_played": {"$in": [None]}},
            {"career_games_played": {"$exists": False}},
            # Or anything that hasn't synced in `stale_after`.
            {"nhl_data_synced_at": {"$exists": False}},
            {"nhl_data_synced_at": {"$lt": cutoff}},
        ],
    }
    total = await db.players.count_documents(query)
    if total == 0:
        logger.info("backfill skipped: nothing stale")
        return {"checked": 0, "updated": 0}

    updated = 0
    sem = asyncio.Semaphore(concurrency)

    async def _worker(p):
        nonlocal updated
        async with sem:
            try:
                if await _process_player(http, db, p):
                    updated += 1
            except Exception:
                # One bad row never breaks the loop.
                pass

    async with httpx.AsyncClient(headers=HEADERS, timeout=TIMEOUT) as http:
        tasks = []
        async for p in db.players.find(query):
            tasks.append(asyncio.create_task(_worker(p)))
            if len(tasks) >= concurrency * 25:
                # Drain every so often so we don't pile up too much.
                await asyncio.gather(*tasks, return_exceptions=True)
                tasks = []
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    logger.info("backfill done: %d updated / %d checked", updated, total)
    return {"checked": total, "updated": updated}


async def player_data_backfill_loop(
    db,
    interval_sec: int = DEFAULT_INTERVAL_SEC,
):
    """Run backfill_once forever on the given interval. Cancelled
    cleanly on FastAPI shutdown."""
    logger.info("Player-data backfill worker started (interval=%ds)", interval_sec)
    # First pass on boot — but defer 60s so the rest of the app is up.
    await asyncio.sleep(60)
    while True:
        try:
            await backfill_once(db)
            await asyncio.sleep(interval_sec)
        except asyncio.CancelledError:
            logger.info("player-data backfill loop cancelled")
            raise
        except Exception as e:
            logger.exception("player-data backfill iteration failed: %s", e)
            # Don't tight-loop on persistent errors.
            await asyncio.sleep(300)
