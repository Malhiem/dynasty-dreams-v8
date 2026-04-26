"""One-shot seed for ownership snapshots and player news.

Why?
    - The Players page has a "% Change" column that compares current
      cross-DD ownership to a 7-day-ago snapshot. We need at least one
      row in `ownership_snapshots` dated >= 7 days ago for the column to
      render meaningful values.
    - The Players page also shows a news signal-strength icon based on
      news doc age (0-7d green, 7-21d orange, 21-35d red). We seed a
      handful of synthetic news items spread across those age bands.

Idempotent. Re-running is safe.
"""
import asyncio
import random
from datetime import datetime, timezone, timedelta
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import dotenv_values
from bson import ObjectId


async def main():
    env = dotenv_values('/app/backend/.env')
    client = AsyncIOMotorClient(env['MONGO_URL'])
    db = client[env['DB_NAME']]

    now = datetime.now(timezone.utc)
    snapshot_at = now - timedelta(days=7, hours=2)

    # 1. Ownership snapshots — capture global ownership for every player as
    # of 7 days ago. Use slightly perturbed values so % change isn't always 0.
    total_teams = await db.teams.count_documents({})
    print(f"global team count: {total_teams}")

    bulk_ops = []
    inserted = 0
    rng = random.Random(42)
    async for p in db.players.find({}, {"_id": 1}):
        pid = str(p["_id"])
        global_owned = await db.teams.count_documents({"roster": pid})
        if total_teams == 0:
            continue
        current_pct = round(100 * global_owned / total_teams, 1)
        # Synthesize 7-day-old pct slightly different so the % Change column
        # populates with realistic variation. Real production: replace with
        # the actual nightly snapshot job.
        delta = rng.uniform(-3.5, 3.5)
        snap_pct = max(0, round(current_pct - delta, 1))
        snap_owned = max(0, int(round(snap_pct * total_teams / 100)))

        existing = await db.ownership_snapshots.find_one({
            "player_id": pid,
            "snapshot_date": snapshot_at.strftime("%Y-%m-%d"),
        })
        if existing:
            continue
        await db.ownership_snapshots.insert_one({
            "player_id": pid,
            "snapshot_date": snapshot_at.strftime("%Y-%m-%d"),
            "snapshot_at": snapshot_at,
            "global_owned": snap_owned,
            "global_total": total_teams,
            "global_pct": snap_pct,
        })
        inserted += 1
    print(f"ownership_snapshots inserted: {inserted}")

    # 2. Player news — seed three age bands so all signal-strength colors render
    # (green ≤7d, orange 7-21d, red 21-35d). Cover top scorers + a sampling.
    headlines = [
        "{name} cleared concussion protocol, returns tonight",
        "{name} breaks franchise scoring record",
        "Coach: {name} will play through minor injury",
        "{name} skating in non-contact jersey; day-to-day",
        "Trade rumors: {name} drawing interest from contenders",
        "{name} signs 8-year extension worth $9.5M AAV",
        "{name}'s line shuffled following recent slump",
        "{name} hits 1000-game milestone in next outing",
    ]
    age_buckets = [3, 5, 12, 18, 26, 32]  # mix of bands

    top_players = await db.players.find().sort("points", -1).limit(40).to_list(40)
    print(f"top players for news seed: {len(top_players)}")

    news_inserted = 0
    for i, pl in enumerate(top_players):
        pid = str(pl["_id"])
        existing = await db.player_news.find_one({"player_id": pid})
        if existing:
            continue
        age_days = age_buckets[i % len(age_buckets)]
        published_at = now - timedelta(days=age_days, hours=rng.randint(0, 18))
        await db.player_news.insert_one({
            "player_id": pid,
            "headline": headlines[i % len(headlines)].format(name=pl.get("name", "Player")),
            "url": f"https://nhl.example/news/{pid}",
            "source": "Dynasty Dreams Newswire",
            "published_at": published_at,
        })
        news_inserted += 1
    print(f"player_news inserted: {news_inserted}")
    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
