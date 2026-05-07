"""Backfill team_id on legacy db.trade_block rows.

Older trade_block items were inserted before the API required a team_id
field, so their rows have team_id=None. This script joins each row to a
team via owner_id+league_id and writes back the missing team_id.

Run once: python -m scripts.backfill_trade_block_team_id
Idempotent: rows that already have a team_id are skipped.
"""
import asyncio
import os
import sys

from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def main():
    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME")
    if not (mongo_url and db_name):
        from dotenv import load_dotenv
        load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
        mongo_url = os.environ.get("MONGO_URL")
        db_name = os.environ.get("DB_NAME")

    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    cursor = db.trade_block.find({"$or": [{"team_id": None}, {"team_id": {"$exists": False}}]})
    backfilled = 0
    skipped = 0
    async for row in cursor:
        owner_id = row.get("owner_id")
        league_id = row.get("league_id")
        if not owner_id or not league_id:
            skipped += 1
            continue
        team = await db.teams.find_one(
            {"owner_id": owner_id, "league_id": league_id},
            {"_id": 1},
        )
        if not team:
            skipped += 1
            continue
        await db.trade_block.update_one(
            {"_id": row["_id"]},
            {"$set": {"team_id": str(team["_id"])}},
        )
        backfilled += 1

    print(f"Backfilled team_id on {backfilled} trade_block rows ({skipped} skipped)")
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
