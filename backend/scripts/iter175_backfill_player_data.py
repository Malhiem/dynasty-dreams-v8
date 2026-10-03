"""Iter 175 — Backfill `birth_date` + `career_games_played` for every
player with an `nhl_id`. Uses the public NHL stats endpoint
`https://api-web.nhle.com/v1/player/{id}/landing` (no auth) and
batches gently to stay polite.

This unlocks accurate `age` resolution in `/api/roster/{id}/detail`
and accurate `minor_eligible` classification on the team page
(Iter 173 → Iter 175 evolution: prospect-only → age-AND-career-GP).

Usage:
    python -m scripts.iter175_backfill_player_data
    python -m scripts.iter175_backfill_player_data --limit 50
    python -m scripts.iter175_backfill_player_data --force   # re-run even if already filled
"""
import argparse
import asyncio
import os
from datetime import datetime, timezone

import httpx
from bson import ObjectId
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")

NHL_LANDING = "https://api-web.nhle.com/v1/player/{nhl_id}/landing"
TIMEOUT = httpx.Timeout(8.0, connect=4.0)
HEADERS = {"User-Agent": "DynastyDreams/iter175 (+contact@dynastydreams)"}


def _age_from_birth_date(bd_str: str | None) -> int | None:
    if not bd_str:
        return None
    try:
        bd = datetime.fromisoformat(bd_str.split("T")[0])
        today = datetime.now(timezone.utc).replace(tzinfo=None)
        years = today.year - bd.year - ((today.month, today.day) < (bd.month, bd.day))
        return years
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


async def _process_batch(db, client, players: list, force: bool) -> int:
    updated = 0
    for p in players:
        nhl_id = p.get("nhl_id")
        if not nhl_id:
            continue
        # Skip already-backfilled rows unless --force is set.
        if not force and p.get("birth_date") and p.get("career_games_played") is not None:
            continue
        landing = await _fetch_player(client, int(nhl_id))
        if not landing:
            continue
        bd = landing.get("birthDate")
        career_gp = (
            landing.get("careerTotals", {})
            .get("regularSeason", {})
            .get("gamesPlayed")
        )
        age = _age_from_birth_date(bd)
        update_fields = {}
        if bd:
            update_fields["birth_date"] = bd
        if age is not None:
            update_fields["age"] = age
        if career_gp is not None:
            update_fields["career_games_played"] = int(career_gp)
        # Surface birth country + position for future expansions.
        if landing.get("birthCountry"):
            update_fields["birth_country"] = landing.get("birthCountry")
        if not update_fields:
            continue
        update_fields["nhl_data_synced_at"] = datetime.now(timezone.utc)
        await db.players.update_one({"_id": p["_id"]}, {"$set": update_fields})
        updated += 1
    return updated


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="Only process N players (debug)")
    parser.add_argument("--force", action="store_true", help="Re-fetch even if already backfilled")
    parser.add_argument("--concurrency", type=int, default=8,
                        help="Parallel HTTP requests per batch")
    args = parser.parse_args()

    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]

    query = {
        # Real NHL IDs only (synthetic prospect IDs are negative).
        "nhl_id": {"$exists": True, "$ne": None, "$gt": 0},
        # Skip prospects — their amateur leagues don't surface in the
        # NHL stats API and their minor-eligibility is implicit.
        "player_type": {"$ne": "prospect"},
    }
    if not args.force:
        # Only fetch rows that are actually missing the data we care about.
        query["$or"] = [
            {"birth_date": {"$in": [None, ""]}},
            {"birth_date": {"$exists": False}},
            {"career_games_played": {"$in": [None]}},
            {"career_games_played": {"$exists": False}},
        ]

    total = await db.players.count_documents(query)
    if args.limit:
        total = min(total, args.limit)
    print(f"Backfilling {total} player(s) from NHL stats API…")

    fetched = 0
    cursor = db.players.find(query).limit(args.limit) if args.limit else db.players.find(query)
    async with httpx.AsyncClient(headers=HEADERS, timeout=TIMEOUT) as http:
        batch: list = []
        async for p in cursor:
            batch.append(p)
            if len(batch) >= args.concurrency:
                fetched += await _process_batch(db, http, batch, args.force)
                if fetched % 50 == 0:
                    print(f"  …{fetched}/{total} done")
                batch = []
        if batch:
            fetched += await _process_batch(db, http, batch, args.force)

    print(f"\n== Iter 175 backfill complete ==")
    print(f"Players updated with birth_date / career_games_played / age: {fetched}")


if __name__ == "__main__":
    asyncio.run(main())
