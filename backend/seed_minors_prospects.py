"""Populate teams' minors slots with prospects.

For every team, find the rostered players who are minors-eligible (low NHL GP
or young age per the league's rules) and persist a lineup entry that places
them in the minors section. This demonstrates roster compliance (each team
has its prospects in the minors).
"""
import asyncio
import os
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
from dotenv import load_dotenv

load_dotenv()


def _age_from_birthdate(bd):
    if not bd:
        return None
    try:
        if isinstance(bd, str):
            bd_dt = datetime.fromisoformat(bd.split("T")[0])
        else:
            bd_dt = bd
        return (datetime.now(timezone.utc).replace(tzinfo=None) - bd_dt).days // 365
    except Exception:
        return None


async def main():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    teams = await db.teams.find({}).to_list(500)
    print(f"Processing {len(teams)} teams")

    total_minors_set = 0
    for team in teams:
        league = await db.leagues.find_one({"_id": ObjectId(team["league_id"])})
        if not league:
            continue
        max_games = int(league.get("minors_max_career_games") or 25)
        max_age = int(league.get("minors_max_age") or 22)

        roster = team.get("roster") or []
        if not roster:
            continue
        try:
            obj_ids = [ObjectId(pid) for pid in roster]
        except Exception:
            obj_ids = []
        players = await db.players.find({"_id": {"$in": obj_ids}}).to_list(100)

        # Filter to minors-eligible
        eligible = []
        for p in players:
            gp = int(p.get("games_played") or 0)
            age = _age_from_birthdate(p.get("birth_date"))
            is_eligible = (gp <= max_games) or (age is not None and age <= max_age)
            if is_eligible and p.get("position") != "G":
                eligible.append((p, gp, age))

        # Sort by age ascending (youngest first), then GP ascending
        eligible.sort(key=lambda x: (x[2] if x[2] is not None else 99, x[1]))

        # Take top 6 prospects to place in minors
        chosen = eligible[:6]
        if not chosen:
            print(f"  {team['name']}: 0 eligible prospects on roster")
            continue

        # Merge with existing lineup
        lineup = (team.get("lineup") or {}).copy()
        for p, gp, age in chosen:
            pid = str(p["_id"])
            lineup[pid] = {"section": "minors", "slot": "MIN"}
        await db.teams.update_one(
            {"_id": team["_id"]},
            {"$set": {"lineup": lineup, "lineup_updated_at": datetime.now(timezone.utc)}},
        )
        names = [p["name"] for p, _, _ in chosen]
        total_minors_set += len(chosen)
        print(f"  {team['name']}: {len(chosen)} prospects → minors ({', '.join(names[:3])}{'…' if len(names) > 3 else ''})")

    print(f"\nDone. Set {total_minors_set} player→minors entries across {len(teams)} teams.")


if __name__ == "__main__":
    asyncio.run(main())
