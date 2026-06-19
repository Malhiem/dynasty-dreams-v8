"""Iter 182 — Backfill prior-season + playoffs stats into the
`player_season_stats` collection so the /players + /waivers
timeframe dropdown (iter 182) can serve real numbers for
2024-25 Regular, 2024 Playoffs, 2023-24 Regular, and 2023 Playoffs.

Data source: NHL stats API season-totals payload, the same endpoint
the iter 175 backfill already uses. Each player record's `featuredStats`
+ `seasonTotals` array carries one row per (season, gameType) pair.

Storage schema (collection: `player_season_stats`):
  {
    player_id: str(ObjectId),          # mongo _id of the player row
    nhl_id:    int,                    # NHL player id (FK)
    season:    "2024-25" | "2023-24",
    season_type: "regular" | "playoffs",
    games_played: int,
    goals: int, assists: int, points: int,
    plus_minus: int,
    sog: int, ppg: int, shg: int,
    hits: int, blocks: int,
    synced_at: datetime UTC,
  }

The script is idempotent — upserts by (player_id, season, season_type).

Usage:
    python -m scripts.iter182_backfill_season_stats
    python -m scripts.iter182_backfill_season_stats --limit 100
    python -m scripts.iter182_backfill_season_stats --force
"""
import argparse
import asyncio
import os
from datetime import datetime, timezone

import httpx
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")

NHL_LANDING = "https://api-web.nhle.com/v1/player/{nhl_id}/landing"
TIMEOUT = httpx.Timeout(10.0, connect=4.0)
HEADERS = {"User-Agent": "DynastyDreams/iter182 (+contact@dynastydreams)"}

# (NHL season code → frontend season slug). NHL stats API encodes
# 2024-25 as `20242025`, 2023-24 as `20232024`. Game type 2 = regular,
# 3 = playoffs.
SEASON_MAP = {
    20242025: "2024-25",
    20232024: "2023-24",
}
GAME_TYPE_MAP = {2: "regular", 3: "playoffs"}


async def _fetch_player(client: httpx.AsyncClient, nhl_id: int) -> dict | None:
    try:
        r = await client.get(NHL_LANDING.format(nhl_id=nhl_id))
        if r.status_code != 200:
            return None
        return r.json()
    except Exception:
        return None


def _rows_from_landing(landing: dict, player_id: str, nhl_id: int) -> list[dict]:
    """Extract one row per (season, season_type) pair we care about.

    Iter 182.1 fix — NHL `seasonTotals` may contain multiple rows
    per (season, gameType) when a player:
      • Was traded mid-season (one row per team).
      • Played for a non-NHL league in the off-season (e.g. KHL,
        IIHF World Championship — these have `leagueAbbrev != "NHL"`).
    The original last-wins upsert silently overwrote McDavid's real
    NHL 82-game row with his 4-game international tournament row.
    Fix: filter to `leagueAbbrev == "NHL"` first, then sum any
    remaining multi-team rows so a mid-season trade still shows the
    full year's stats.
    """
    bucket: dict[tuple[str, str], dict] = {}
    for st in (landing.get("seasonTotals") or []):
        season_code = st.get("season")
        gt = st.get("gameTypeId")
        league_abbr = (st.get("leagueAbbrev") or "").upper()
        if season_code not in SEASON_MAP or gt not in GAME_TYPE_MAP:
            continue
        # Only NHL stats count — international / minor-league rows
        # would otherwise overwrite the canonical NHL row.
        if league_abbr != "NHL":
            continue
        key = (SEASON_MAP[season_code], GAME_TYPE_MAP[gt])
        row = bucket.get(key)
        if row is None:
            row = {
                "player_id": player_id,
                "nhl_id": nhl_id,
                "season": key[0],
                "season_type": key[1],
                "games_played": 0,
                "goals": 0,
                "assists": 0,
                "points": 0,
                "plus_minus": 0,
                "sog": 0,
                "ppg": 0,
                "shg": 0,
                "hits": 0,
                "blocks": 0,
                "synced_at": datetime.now(timezone.utc),
            }
            bucket[key] = row
        # Aggregate (mid-season trade across two NHL teams = 2 rows).
        row["games_played"] += int(st.get("gamesPlayed") or 0)
        row["goals"] += int(st.get("goals") or 0)
        row["assists"] += int(st.get("assists") or 0)
        row["points"] += int(st.get("points") or 0)
        row["plus_minus"] += int(st.get("plusMinus") or 0)
        row["sog"] += int(st.get("shots") or 0)
        row["ppg"] += int(st.get("powerPlayGoals") or 0)
        row["shg"] += int(st.get("shorthandedGoals") or 0)
        row["hits"] += int(st.get("hits") or 0)
        row["blocks"] += int(st.get("blockedShots") or 0)
    return list(bucket.values())


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--force", action="store_true",
                        help="Re-fetch even if rows already exist")
    parser.add_argument("--concurrency", type=int, default=8)
    args = parser.parse_args()

    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]

    # Skip prospects (negative synthetic nhl_id) — their amateur
    # stats aren't in the NHL season-totals endpoint.
    query = {
        "nhl_id": {"$exists": True, "$ne": None, "$gt": 0},
        "player_type": {"$ne": "prospect"},
    }
    total = await db.players.count_documents(query)
    if args.limit:
        total = min(total, args.limit)
    print(f"Iter 182: pulling prior-season stats for {total} player(s)…")

    # Ensure compound index for upsert performance + lookups.
    await db.player_season_stats.create_index(
        [("player_id", 1), ("season", 1), ("season_type", 1)],
        unique=True,
    )
    await db.player_season_stats.create_index(
        [("season", 1), ("season_type", 1)],
    )

    cursor = db.players.find(query)
    if args.limit:
        cursor = cursor.limit(args.limit)

    fetched = 0
    inserts = 0
    async with httpx.AsyncClient(headers=HEADERS, timeout=TIMEOUT) as http:
        async for p in cursor:
            pid = str(p["_id"])
            if not args.force:
                # Skip players we've already cached BOTH seasons for.
                have = await db.player_season_stats.count_documents(
                    {"player_id": pid, "season": {"$in": list(SEASON_MAP.values())}}
                )
                if have >= 2:
                    continue
            landing = await _fetch_player(http, int(p["nhl_id"]))
            if not landing:
                continue
            rows = _rows_from_landing(landing, pid, int(p["nhl_id"]))
            for row in rows:
                await db.player_season_stats.update_one(
                    {
                        "player_id": row["player_id"],
                        "season": row["season"],
                        "season_type": row["season_type"],
                    },
                    {"$set": row},
                    upsert=True,
                )
            inserts += len(rows)
            fetched += 1
            if fetched % 25 == 0:
                print(f"  …{fetched}/{total} done, {inserts} rows upserted")

    print(f"\n== Iter 182 season-stats backfill complete ==")
    print(f"Players processed: {fetched}, season-rows upserted: {inserts}")


if __name__ == "__main__":
    asyncio.run(main())
