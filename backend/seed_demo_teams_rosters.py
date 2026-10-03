"""Fill the 5 demo leagues to capacity with fake users, teams, and auto-drafted rosters.

For each league:
  - Creates (max_teams - current_teams) demo users (email: team{n}-{league_slug}@demo.dynastydreams.app)
  - Creates a team for each user
  - Auto-drafts rosters using a snake-style distribution from the top N available players
    so every team gets a balanced mix of positions.

Run:  python seed_demo_teams_rosters.py
Idempotent: if a league is already full, it skips it.
"""
import asyncio
import os
import re
import random
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

DEMO_PASSWORD = "Demo2026!"

TEAM_NAME_POOL = [
    "Frozen Phantoms", "Ice Breakers", "Slapshot Snipers", "Crease Crashers",
    "Blue Line Bruisers", "Hat Trick Heroes", "Power Play Predators", "Overtime Outlaws",
    "Top Shelf Titans", "Wrister Wolves", "Five-Hole Fighters", "Checkmate Chiefs",
    "Puck Pirates", "Zamboni Zealots", "Glass Breakers", "Shutout Sentinels",
    "Backcheck Bandits", "Wrap-Around Wranglers", "Breakaway Barons", "Biscuit Brigade",
    "Shinny Shamans", "Face-Off Freaks", "Dangle Dynasty", "Neutral Zone Ninjas",
    "Forecheck Falcons", "Penalty Kill Kings", "Rearguard Ravens", "Snipe Squad",
    "Chirp Champions", "Cellar Dwellers United", "Odd-Man Rush", "Short-Handed Heroes",
    "Gritty Gladiators", "High-Stick Hooligans", "Offensive Zone Oracles",
    "Peanut-Butter Passes", "Saucer Sages", "Bar Down Brigade", "Gordie Howe Hatrickers",
    "Wheelhouse Wanderers", "Toe-Drag Tigers", "Heel-Kick Hustlers", "One-Timer Outlaws",
    "Bender Boys", "Garbage Goal Gurus", "Dunk & Dangle", "Pond Pirates",
    "Bucket Brigade", "Mitts & Biscuits", "Zebra Whisperers",
]


def slugify(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", name.lower()).strip("-")
    return s[:24]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


async def get_or_create_user(db, email: str, name: str) -> str:
    existing = await db.users.find_one({"email": email})
    if existing:
        return str(existing["_id"])
    doc = {
        "email": email,
        "password_hash": hash_password(DEMO_PASSWORD),
        "name": name,
        "role": "user",
        "created_at": datetime.now(timezone.utc),
    }
    result = await db.users.insert_one(doc)
    return str(result.inserted_id)


async def pick_team_name(used: set) -> str:
    for pool_name in TEAM_NAME_POOL:
        if pool_name not in used:
            used.add(pool_name)
            return pool_name
    # Fallback — append a numeric suffix
    for i in range(1, 1000):
        candidate = f"Team {i}"
        if candidate not in used:
            used.add(candidate)
            return candidate
    return f"Team {random.randint(10000, 99999)}"


async def auto_draft(db, teams: list, roster_spots: int):
    """Snake-style distribute top players by total points across teams."""
    players = await db.players.find({"season": "2025-2026"}, {"_id": 1, "position": 1, "player_type": 1, "points": 1, "wins": 1}).sort("points", -1).to_list(5000)
    # Also sort goalies by wins (backup: if wins missing, stable order)
    skaters = [p for p in players if p.get("player_type") != "goalie" and p.get("position") != "G"]
    goalies = [p for p in players if p.get("player_type") == "goalie" or p.get("position") == "G"]
    # goalies already in points order but re-sort by wins then position tag
    goalies.sort(key=lambda p: p.get("wins", 0) or 0, reverse=True)

    n_teams = len(teams)
    # Composition per team: 2 goalies + remaining split (approx 4 D, rest F)
    goalies_per = 2
    d_per = 5
    f_per = max(0, roster_spots - goalies_per - d_per)

    defenders = [p for p in skaters if p.get("position") == "D"]
    forwards = [p for p in skaters if p.get("position") != "D"]

    def snake_allocate(pool, per_team):
        """Distribute `per_team` picks across teams in snake order."""
        rosters = [[] for _ in range(n_teams)]
        for rnd in range(per_team):
            order = range(n_teams) if rnd % 2 == 0 else range(n_teams - 1, -1, -1)
            for team_idx in order:
                if pool:
                    rosters[team_idx].append(pool.pop(0))
        return rosters

    f_rosters = snake_allocate(forwards, f_per)
    d_rosters = snake_allocate(defenders, d_per)
    g_rosters = snake_allocate(goalies, goalies_per)

    for i, team in enumerate(teams):
        combined = f_rosters[i] + d_rosters[i] + g_rosters[i]
        roster_ids = [str(p["_id"]) for p in combined]
        await db.teams.update_one(
            {"_id": ObjectId(team["_id"])},
            {"$set": {"roster": roster_ids, "drafted_at": datetime.now(timezone.utc)}},
        )


async def fill_league(db, league: dict):
    league_id = str(league["_id"])
    slug = slugify(league["name"])
    needed = league["max_teams"] - league.get("current_teams", 0)
    if needed <= 0:
        print(f"  ✓ {league['name']} already full ({league['current_teams']}/{league['max_teams']})")
        return

    used_team_names = set(t["name"] for t in await db.teams.find({"league_id": league_id}, {"name": 1, "_id": 0}).to_list(100))
    created_teams = []
    for i in range(needed):
        idx = league.get("current_teams", 0) + i + 1
        email = f"team{idx}-{slug}@demo.dynastydreams.app"
        name = f"Demo Owner {idx} · {league['name'][:22]}"
        user_id = await get_or_create_user(db, email, name)
        team_name = await pick_team_name(used_team_names)

        existing = await db.teams.find_one({"league_id": league_id, "owner_id": user_id})
        if existing:
            created_teams.append({"_id": str(existing["_id"]), "name": existing["name"]})
            continue

        team_doc = {
            "name": team_name,
            "league_id": league_id,
            "owner_id": user_id,
            "owner_name": name,
            "roster": [],
            "salary_used": 0.0,
            "wins": 0, "losses": 0, "ties": 0,
            "points_for": 0.0, "points_against": 0.0,
            "created_at": datetime.now(timezone.utc),
        }
        result = await db.teams.insert_one(team_doc)
        created_teams.append({"_id": str(result.inserted_id), "name": team_name})

    await db.leagues.update_one(
        {"_id": league["_id"]},
        {"$set": {"current_teams": league["max_teams"], "status": "active"}},
    )

    # Fetch all teams in this league and auto-draft
    all_teams = await db.teams.find({"league_id": league_id}).to_list(100)
    simplified = [{"_id": str(t["_id"]), "name": t["name"]} for t in all_teams]
    await auto_draft(db, simplified, league.get("roster_spots", 20))
    print(f"  ✓ {league['name']}: +{len(created_teams)} teams, {league['max_teams']} rosters drafted ({league.get('roster_spots', 20)} slots each)")


async def main():
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]

    leagues = await db.leagues.find({"name": {"$in": [
        "Ice Kings Head-to-Head", "Stat Chasers Roto", "Frozen Dynasty",
        "Perennial Keepers", "Set-and-Forget Best Ball"
    ]}}).to_list(10)

    if not leagues:
        print("No demo leagues found. Run seed_demo_leagues.py first.")
        return

    print(f"Filling {len(leagues)} leagues (demo password: {DEMO_PASSWORD})...")
    for lg in leagues:
        await fill_league(db, lg)

    # Final stats
    total_teams = await db.teams.count_documents({})
    total_users = await db.users.count_documents({})
    print(f"\nDone. Total users: {total_users}, total teams: {total_teams}")
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
