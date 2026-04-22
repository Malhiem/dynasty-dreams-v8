"""Seed draft_picks for all leagues. Each team owns all rounds for the next N years.
Idempotent.
"""
import asyncio
import os
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()


YEARS = [2026, 2027, 2028]
ROUNDS = 5


async def main():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]

    total = 0
    for league in await db.leagues.find({}).to_list(100):
        lid = str(league["_id"])
        existing = await db.draft_picks.count_documents({"league_id": lid})
        if existing > 0:
            print(f"SKIP {league['name']} — {existing} picks already")
            continue

        teams = await db.teams.find({"league_id": lid}).to_list(100)
        docs = []
        for team in teams:
            tid = str(team["_id"])
            for year in YEARS:
                for rnd in range(1, ROUNDS + 1):
                    docs.append({
                        "league_id": lid,
                        "year": year,
                        "round": rnd,
                        "original_team_id": tid,
                        "original_team_name": team.get("name"),
                        "current_team_id": tid,
                        "current_team_name": team.get("name"),
                        "pick_number": None,  # unknown until draft order is set
                        "created_at": datetime.now(timezone.utc),
                    })
        if docs:
            await db.draft_picks.insert_many(docs)
            total += len(docs)
            print(f"OK {league['name']} — seeded {len(docs)} picks across {len(teams)} teams")

    print(f"\nSeeded {total} total draft picks")


if __name__ == "__main__":
    asyncio.run(main())
