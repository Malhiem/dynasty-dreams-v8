"""Seed league activity feed for demo leagues. Idempotent."""
import asyncio
import os
import random
from datetime import datetime, timezone, timedelta
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()


async def main():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]

    leagues = await db.leagues.find({}).to_list(100)
    total = 0
    now = datetime.now(timezone.utc)

    for league in leagues:
        lid = str(league["_id"])
        existing = await db.activity_feed.count_documents({"league_id": lid})
        if existing >= 9:
            print(f"SKIP {league['name']} — {existing} events already")
            continue

        teams = await db.teams.find({"league_id": lid}).to_list(100)

        events = [
            {"event_type": "league_created", "description": f"Commissioner created '{league['name']}'"},
            {"event_type": "settings_updated", "description": f"League settings finalized: {league.get('scoring_format', 'head_to_head')}, {len(teams)} teams"},
            {"event_type": "draft_scheduled", "description": "Draft scheduled for Week 0"},
            {"event_type": "rosters_locked", "description": "Initial rosters locked for Week 1"},
            {"event_type": "waiver_processed", "description": "Weekly waivers processed — 0 successful claims"},
            {"event_type": "chat", "description": "Welcome to the league! Good luck this season."},
            {"event_type": "stat_corrections", "description": "NHL stat corrections applied from last night's games"},
            {"event_type": "trade_deadline_reminder", "description": "Trade deadline is 4 weeks away"},
            {"event_type": "live_scoring_started", "description": "Live scoring has started for Week 1"},
        ]
        for t in teams[:6]:
            events.append({
                "event_type": "team_joined",
                "description": f"{t['owner_name']} joined as '{t['name']}'",
            })

        docs = []
        for i, ev in enumerate(events):
            docs.append({
                "league_id": lid,
                "event_type": ev["event_type"],
                "description": ev["description"],
                "message": ev["description"],
                "created_at": now - timedelta(hours=random.randint(1, 168)),
                "actor_id": None,
                "actor_name": "System",
            })
        if docs:
            await db.activity_feed.insert_many(docs)
            total += len(docs)
            print(f"OK {league['name']} — seeded {len(docs)} events")

    print(f"\nSeeded {total} total activity events")


if __name__ == "__main__":
    asyncio.run(main())
