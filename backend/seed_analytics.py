"""Seed synthetic historical week_summaries so the Analytics page has rich data.

Generates:
  - Current season (2025-26): weeks 1..10 for every team in every league
  - Prior 4 seasons (2021-22 … 2024-25): full-season aggregates (26 weeks of realistic points)
Idempotent: uses league_id+season+week+team_id as upsert key, so re-running is safe.
"""
import asyncio
import os
import random
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()

CURRENT_SEASON = "2025-26"
HISTORICAL_SEASONS = ["2021-22", "2022-23", "2023-24", "2024-25"]
CURRENT_WEEKS = 10
HIST_WEEKS_PER_SEASON = 26


def gen_week_points(team_strength: float) -> float:
    """Team strength 0..1 → weekly fantasy points 200..320 with noise."""
    base = 210 + team_strength * 80
    noise = random.gauss(0, 18)
    return max(140.0, round(base + noise, 1))


async def main():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]

    leagues = await db.leagues.find({}).to_list(50)
    total_rows = 0

    for league in leagues:
        lid = str(league["_id"])
        teams = await db.teams.find({"league_id": lid}).to_list(50)
        if len(teams) < 2:
            continue

        # Assign each team a stable strength (seeded off team_id) so YoY is believable
        strengths = {str(t["_id"]): (hash(str(t["_id"])) % 1000) / 1000.0 for t in teams}

        # ─── Current season: per-week rows 1..N ────────────────────
        for week in range(1, CURRENT_WEEKS + 1):
            # Pair teams in random matchups for this synthetic week
            team_ids = list(strengths.keys())
            random.shuffle(team_ids)
            scores = {tid: gen_week_points(strengths[tid]) for tid in team_ids}
            for i in range(0, len(team_ids) - 1, 2):
                a, b = team_ids[i], team_ids[i + 1]
                if a not in scores or b not in scores:
                    continue
                a_name = next(t["name"] for t in teams if str(t["_id"]) == a)
                b_name = next(t["name"] for t in teams if str(t["_id"]) == b)
                pa_a, pa_b = scores[a], scores[b]
                win_a = pa_a > pa_b
                for tid, name, pf, pa, opp in (
                    (a, a_name, pa_a, pa_b, b),
                    (b, b_name, pa_b, pa_a, a),
                ):
                    doc = {
                        "league_id": lid, "season": CURRENT_SEASON, "week": week,
                        "team_id": tid, "team_name": name, "opponent_team_id": opp,
                        "points_for": pf, "points_against": pa,
                        "win": (pf > pa),
                        "loss": (pf < pa),
                        "tie": (pf == pa),
                        "matchup_id": f"synthetic_{lid}_{CURRENT_SEASON}_w{week}_{tid[:6]}",
                        "synthetic": True,
                    }
                    await db.week_summaries.update_one(
                        {"league_id": lid, "season": CURRENT_SEASON, "week": week, "team_id": tid},
                        {"$set": doc},
                        upsert=True,
                    )
                    total_rows += 1

        # ─── Historical seasons: aggregated per-week rows 1..26 ────
        for season in HISTORICAL_SEASONS:
            for week in range(1, HIST_WEEKS_PER_SEASON + 1):
                team_ids = list(strengths.keys())
                random.shuffle(team_ids)
                scores = {tid: gen_week_points(strengths[tid]) for tid in team_ids}
                for i in range(0, len(team_ids) - 1, 2):
                    a, b = team_ids[i], team_ids[i + 1]
                    if a not in scores or b not in scores:
                        continue
                    a_name = next(t["name"] for t in teams if str(t["_id"]) == a)
                    b_name = next(t["name"] for t in teams if str(t["_id"]) == b)
                    for tid, name, pf, pa, opp in (
                        (a, a_name, scores[a], scores[b], b),
                        (b, b_name, scores[b], scores[a], a),
                    ):
                        doc = {
                            "league_id": lid, "season": season, "week": week,
                            "team_id": tid, "team_name": name, "opponent_team_id": opp,
                            "points_for": pf, "points_against": pa,
                            "win": (pf > pa), "loss": (pf < pa), "tie": (pf == pa),
                            "matchup_id": f"synthetic_{lid}_{season}_w{week}_{tid[:6]}",
                            "synthetic": True,
                        }
                        await db.week_summaries.update_one(
                            {"league_id": lid, "season": season, "week": week, "team_id": tid},
                            {"$set": doc}, upsert=True,
                        )
                        total_rows += 1
        print(f"✔ {league['name']}: {len(teams)} teams × ({CURRENT_WEEKS} current + {len(HISTORICAL_SEASONS) * HIST_WEEKS_PER_SEASON} hist) weeks")

    print(f"\n🎉 Seeded {total_rows} week_summaries rows across {len(leagues)} leagues")


if __name__ == "__main__":
    asyncio.run(main())
