"""One-shot script to backfill NHL bio + draft details on every player doc.

Run: `cd /app/backend && python seed_player_bio.py`

For each player with `nhl_id`, hits the public NHL API once and stores:
- height_inches, weight_pounds, birth_date, birth_city, birth_state,
  birth_country, headshot, draft_year/round/pick_in_round/overall/team_abbr,
  nhl_seasons (count of NHL regular-season rows in seasonTotals).

Idempotent — safe to re-run; uses `$set` so re-runs simply refresh the data
when the public API returns new info (e.g., a player's first NHL season).
"""
import asyncio
import os
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()


async def main():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    from nhlpy import NHLClient
    client = NHLClient()

    cursor = db.players.find({"nhl_id": {"$exists": True, "$ne": None}}, {"_id": 1, "nhl_id": 1, "name": 1})
    total = 0
    updated = 0
    failed = 0
    async for p in cursor:
        total += 1
        try:
            raw = client.stats.player_career_stats(player_id=int(p["nhl_id"]))
        except Exception as e:
            print(f"[{p.get('name')}] fetch failed: {e}")
            failed += 1
            continue
        if not raw:
            failed += 1
            continue

        def _default(v):
            return v.get("default") if isinstance(v, dict) else v

        seasons_nhl = [s for s in (raw.get("seasonTotals") or [])
                       if s.get("leagueAbbrev") == "NHL" and s.get("gameTypeId") == 2]
        d = raw.get("draftDetails") or {}
        update = {
            "height_inches": raw.get("heightInInches"),
            "weight_pounds": raw.get("weightInPounds"),
            "birth_date": raw.get("birthDate"),
            "birth_city": _default(raw.get("birthCity")),
            "birth_state": _default(raw.get("birthStateProvince")),
            "birth_country": raw.get("birthCountry"),
            "headshot": raw.get("headshot"),
            "draft_year": d.get("year"),
            "draft_round": d.get("round"),
            "draft_pick_in_round": d.get("pickInRound"),
            "draft_overall": d.get("overallPick"),
            "draft_team_abbr": d.get("teamAbbrev"),
            "nhl_seasons": len({s.get("season") for s in seasons_nhl}),
            "last_synced_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.players.update_one({"_id": p["_id"]}, {"$set": update})
        updated += 1
        if total % 50 == 0:
            print(f"  ... {total} processed, {updated} updated, {failed} failed")

    print(f"DONE — {total} players · {updated} enriched · {failed} failed")


if __name__ == "__main__":
    asyncio.run(main())
