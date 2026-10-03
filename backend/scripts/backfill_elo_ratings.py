"""Backfill ELO ratings retroactively for every completed matchup.

Resets all teams to START_RATING (1500), then walks every completed
matchup chronologically and applies the ELO update via
`routes.ratings.apply_matchup_elo`.

Idempotent: clears `rating_history` + `peak_rating` + the `elo_applied`
flag on every matchup before recomputing, so re-running produces the
same final state.

Usage:
    python -m scripts.backfill_elo_ratings
"""
import asyncio
import os
import sys

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def main():
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
    mongo_url = os.environ["MONGO_URL"]
    db_name = os.environ["DB_NAME"]
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    from routes import ratings as ratings_mod

    def _safe_object_id(s, _):
        from bson import ObjectId
        return ObjectId(s)

    async def _get_user_unused(_request):  # not needed by apply_matchup_elo
        return None

    ratings_mod.setup({
        "db": db, "get_current_user": _get_user_unused,
        "_safe_object_id": _safe_object_id,
    })

    # 1) Reset every team
    await db.teams.update_many({}, {
        "$set": {"rating": ratings_mod.START_RATING, "peak_rating": ratings_mod.START_RATING},
        "$unset": {"rating_history": "", "rating_updated_at": ""},
    })
    print(f"Reset ratings on {await db.teams.count_documents({})} teams to {ratings_mod.START_RATING}")

    # 2) Clear elo_applied so we walk every matchup again
    await db.matchups.update_many({}, {"$unset": {"elo_applied": "", "elo_home_delta": "", "elo_away_delta": ""}})

    # 3) Walk every completed matchup ordered by simulated_at (ISO string sorts lexicographically)
    cursor = db.matchups.find(
        {"status": "completed", "winner": {"$exists": True}},
    ).sort([("simulated_at", 1), ("week", 1), ("_id", 1)])

    applied = 0
    skipped = 0
    async for m in cursor:
        if not m.get("home_team_id") or not m.get("away_team_id"):
            skipped += 1
            continue
        try:
            await ratings_mod.apply_matchup_elo(m["league_id"], m)
            applied += 1
        except Exception as ex:
            print(f"  skip matchup {m.get('_id')}: {ex}")
            skipped += 1

    print(f"Applied ELO to {applied} matchups ({skipped} skipped)")
    # 4) Quick sanity: top 5 ratings + percentile of top
    top = await db.teams.find({}, {"name": 1, "rating": 1, "peak_rating": 1}).sort("rating", -1).limit(5).to_list(5)
    for t in top:
        print(f"  {t.get('name'):30s}  rating={t.get('rating', 0):.1f}  peak={t.get('peak_rating', 0):.1f}")

    client.close()


if __name__ == "__main__":
    asyncio.run(main())
