"""Add chriszarek@gmail.com as a team owner in all 5 demo leagues.

Each league is already at capacity — we re-assign the "team1-*" demo team
in each league to this user so the league stays full and the existing
auto-drafted roster transfers cleanly.

Run:  python seed_user_chriszarek.py
"""
import asyncio
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import bcrypt
from bson import ObjectId
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]

EMAIL = "chriszarek@gmail.com"
PASSWORD = "Chris2026!"
USERNAME = "chriszarek"
DISPLAY_NAME = "chriszarek"

DEMO_LEAGUE_NAMES = [
    "Ice Kings Head-to-Head",
    "Stat Chasers Roto",
    "Frozen Dynasty",
    "Perennial Keepers",
    "Set-and-Forget Best Ball",
]


def slugify(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", name.lower()).strip("-")
    return s[:24]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


async def ensure_user(db) -> str:
    existing = await db.users.find_one({"email": EMAIL})
    if existing:
        # Reset password, set username, refresh name to match
        await db.users.update_one(
            {"_id": existing["_id"]},
            {"$set": {
                "password_hash": hash_password(PASSWORD),
                "username": USERNAME,
                "name": DISPLAY_NAME,
            }},
        )
        return str(existing["_id"])
    doc = {
        "email": EMAIL,
        "password_hash": hash_password(PASSWORD),
        "username": USERNAME,
        "name": DISPLAY_NAME,
        "role": "user",
        "created_at": datetime.now(timezone.utc),
    }
    result = await db.users.insert_one(doc)
    return str(result.inserted_id)


async def assign_team_in_league(db, league: dict, user_id: str) -> dict:
    league_id = str(league["_id"])
    slug = slugify(league["name"])

    # If Chris already owns a team in this league, skip
    existing = await db.teams.find_one({"league_id": league_id, "owner_id": user_id})
    if existing:
        return {"league": league["name"], "team_id": str(existing["_id"]), "team_name": existing["name"], "action": "already-owned"}

    # Pick the first demo-seeded team in this league (team1-*) and take it over.
    # We identify it by looking at the owner user's email pattern.
    demo_owner = await db.users.find_one({"email": f"team1-{slug}@demo.dynastydreams.app"})
    if not demo_owner:
        # Fall back to any fake demo owner in this league
        candidate_team = await db.teams.find_one({"league_id": league_id}, sort=[("created_at", 1)])
        if not candidate_team:
            return {"league": league["name"], "error": "No teams in league to reassign"}
    else:
        candidate_team = await db.teams.find_one({"league_id": league_id, "owner_id": str(demo_owner["_id"])})
        if not candidate_team:
            candidate_team = await db.teams.find_one({"league_id": league_id}, sort=[("created_at", 1)])

    # Give the team a friendly name tied to Chris, keep the roster
    new_team_name = f"Zarek's {candidate_team['name'].split(' ')[0]}"
    await db.teams.update_one(
        {"_id": candidate_team["_id"]},
        {"$set": {
            "owner_id": user_id,
            "owner_name": DISPLAY_NAME,
            "name": new_team_name,
            "reassigned_at": datetime.now(timezone.utc),
        }},
    )
    return {
        "league": league["name"],
        "team_id": str(candidate_team["_id"]),
        "team_name": new_team_name,
        "roster_size": len(candidate_team.get("roster", [])),
        "action": "reassigned",
    }


async def main():
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]

    user_id = await ensure_user(db)
    print(f"User: {EMAIL} ({user_id}) · password: {PASSWORD}")

    leagues = await db.leagues.find({"name": {"$in": DEMO_LEAGUE_NAMES}}).to_list(10)
    if not leagues:
        print("No demo leagues found. Seed them first.")
        return

    print(f"\nAssigning team ownership across {len(leagues)} leagues...")
    for lg in leagues:
        res = await assign_team_in_league(db, lg, user_id)
        if "error" in res:
            print(f"  ✗ {res['league']}: {res['error']}")
        else:
            roster = res.get("roster_size", "?")
            print(f"  ✓ {res['league']:34s} → {res['team_name']} ({roster} players) [{res['action']}]")

    print(f"\nDone. Log in as {EMAIL} / {PASSWORD} to see the multi-league dashboard.")
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
