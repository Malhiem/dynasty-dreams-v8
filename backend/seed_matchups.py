"""Generate round-robin matchup schedules for all seeded demo leagues.
Idempotent: skips leagues that already have matchups.
"""
import asyncio
import os
import random
from datetime import datetime, timezone
from itertools import cycle
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()


def generate_round_robin(team_ids):
    n = len(team_ids)
    if n < 2:
        return []
    teams = list(team_ids)
    if n % 2:
        teams.append(None)  # bye
    rounds = []
    for _ in range(len(teams) - 1):
        round_pairs = []
        for i in range(len(teams) // 2):
            a, b = teams[i], teams[len(teams) - 1 - i]
            if a is not None and b is not None:
                round_pairs.append((a, b))
        rounds.append(round_pairs)
        teams = [teams[0]] + [teams[-1]] + teams[1:-1]
    return rounds


async def main():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]

    leagues = await db.leagues.find({}).to_list(100)
    total_matchups = 0
    for league in leagues:
        lid = str(league["_id"])
        existing = await db.matchups.count_documents({"league_id": lid})
        if existing > 0:
            print(f"SKIP {league['name']} — {existing} matchups already")
            continue

        teams = await db.teams.find({"league_id": lid}).to_list(100)
        if len(teams) < 2:
            print(f"SKIP {league['name']} — need 2+ teams")
            continue

        team_ids = [str(t["_id"]) for t in teams]
        team_map = {str(t["_id"]): t["name"] for t in teams}
        num_weeks = league.get("regular_season_weeks", 18)
        scoring_format = league.get("scoring_format", "head_to_head")

        base = generate_round_robin(team_ids)
        schedule = []
        week = 1
        for round_pairs in cycle(base):
            if week > num_weeks:
                break
            shuffled = list(round_pairs)
            random.shuffle(shuffled)
            for home_id, away_id in shuffled:
                schedule.append({
                    "league_id": lid,
                    "week": week,
                    "home_team_id": home_id,
                    "home_team_name": team_map.get(home_id, ""),
                    "away_team_id": away_id,
                    "away_team_name": team_map.get(away_id, ""),
                    "home_score": 0,
                    "away_score": 0,
                    "status": "scheduled",
                    "winner": None,
                    "scoring_format": scoring_format,
                })
            week += 1

        if schedule:
            await db.matchups.insert_many(schedule)
            total_matchups += len(schedule)
            print(f"OK   {league['name']} — {len(schedule)} matchups across {num_weeks} weeks")

    # Mark week 1 of each league as completed with scores derived from live_points
    # so the current-week endpoint returns week 2 (first unplayed).
    # Actually leave all weeks as "scheduled" so current-week = 1.
    print(f"\nSeeded {total_matchups} total matchups")


if __name__ == "__main__":
    asyncio.run(main())
