"""Seed 5 demo leagues — one for each core fantasy game format.

Covers the formats requested by the user:
  1. Head-to-Head (H2H, Redraft)
  2. Rotisserie (Roto)
  3. Dynasty (with salary cap)
  4. Keeper
  5. Best Ball

All leagues allow up to 32 teams and use the admin user as commissioner.
Run with:  python seed_demo_leagues.py
"""
import asyncio
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@dynastydreams.com")

DEMO_LEAGUES = [
    {
        "name": "Ice Kings Head-to-Head",
        "sport": "nhl",
        "format": "redraft",
        "scoring_format": "head_to_head",
        "max_teams": 12,
        "salary_cap_enabled": False,
        "salary_cap": None,
        "draft_type": "snake",
        "roster_spots": 20,
        "keepers_allowed": 0,
        "entry_fee": 50.0,
        "is_private": False,
    },
    {
        "name": "Stat Chasers Roto",
        "sport": "nhl",
        "format": "redraft",
        "scoring_format": "rotisserie",
        "max_teams": 14,
        "salary_cap_enabled": False,
        "salary_cap": None,
        "draft_type": "snake",
        "roster_spots": 22,
        "keepers_allowed": 0,
        "entry_fee": 25.0,
        "is_private": False,
    },
    {
        "name": "Frozen Dynasty",
        "sport": "nhl",
        "format": "dynasty",
        "scoring_format": "head_to_head",
        "max_teams": 16,
        "salary_cap_enabled": True,
        "salary_cap": 95500000.0,
        "draft_type": "auction",
        "roster_spots": 28,
        "keepers_allowed": 10,
        "entry_fee": 100.0,
        "is_private": False,
    },
    {
        "name": "Perennial Keepers",
        "sport": "nhl",
        "format": "keeper",
        "scoring_format": "head_to_head",
        "max_teams": 12,
        "salary_cap_enabled": False,
        "salary_cap": None,
        "draft_type": "snake",
        "roster_spots": 22,
        "keepers_allowed": 4,
        "entry_fee": 75.0,
        "is_private": False,
    },
    {
        "name": "Set-and-Forget Best Ball",
        "sport": "nhl",
        "format": "best_ball",
        "scoring_format": "total_points",
        "max_teams": 32,
        "salary_cap_enabled": False,
        "salary_cap": None,
        "draft_type": "snake",
        "roster_spots": 25,
        "keepers_allowed": 0,
        "entry_fee": 20.0,
        "is_private": False,
    },
]


async def main():
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]

    admin = await db.users.find_one({"email": ADMIN_EMAIL})
    if not admin:
        raise RuntimeError(
            f"Admin user '{ADMIN_EMAIL}' not found. Start the backend once so it seeds the admin, then re-run this script."
        )
    admin_id = str(admin["_id"])
    admin_name = admin.get("name", "Commissioner")

    # Wipe previous demo leagues (idempotent re-runs)
    demo_names = [lg["name"] for lg in DEMO_LEAGUES]
    await db.leagues.delete_many({"name": {"$in": demo_names}})

    inserted = []
    for lg in DEMO_LEAGUES:
        doc = {
            **lg,
            "current_teams": 0,
            "commissioner_id": admin_id,
            "commissioner_name": admin_name,
            "invite_code": secrets.token_urlsafe(8),
            "status": "setup",
            "created_at": datetime.now(timezone.utc),
        }
        result = await db.leagues.insert_one(doc)
        inserted.append({
            "id": str(result.inserted_id),
            "name": doc["name"],
            "format": doc["format"],
            "scoring": doc["scoring_format"],
            "max_teams": doc["max_teams"],
            "invite_code": doc["invite_code"],
        })

    # Promote admin to commissioner role if they aren't already
    if admin.get("role") == "user":
        await db.users.update_one(
            {"_id": admin["_id"]}, {"$set": {"role": "commissioner"}}
        )

    print(f"Seeded {len(inserted)} demo leagues (commissioner: {admin_name}):")
    for lg in inserted:
        print(
            f"  • {lg['name']:34s} | {lg['format']:9s} | {lg['scoring']:14s} | "
            f"max={lg['max_teams']:2d} | code={lg['invite_code']} | id={lg['id']}"
        )
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
