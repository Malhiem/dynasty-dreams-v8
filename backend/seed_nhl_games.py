"""Seed `games` collection + `player_game_logs` collection from NHL API.

Pulls the last `LOOKBACK_DAYS` days of completed NHL games and persists:
  - games: {nhl_game_id, date, season, home_team, away_team, home_score, away_score, state}
  - player_game_logs: {player_id (our _id), nhl_player_id, nhl_game_id, date, goals, assists, plus_minus, sog, hits, blocks, ppg, shg, fow, toi, pim}

Re-running is idempotent (upsert by `nhl_game_id` and `(nhl_player_id, nhl_game_id)`).

This is what unlocks accurate timeframe filtering on the Players page (Last 7d,
14d, 30d, 60d, 90d, today).
"""
import asyncio
from datetime import datetime, timezone, timedelta, date as date_cls

from nhlpy import NHLClient
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import dotenv_values

LOOKBACK_DAYS = 30


def _to_iso(d) -> str | None:
    if isinstance(d, str):
        return d
    if isinstance(d, (datetime, date_cls)):
        return d.isoformat()
    return None


async def main() -> None:
    env = dotenv_values("/app/backend/.env")
    mongo = AsyncIOMotorClient(env["MONGO_URL"])
    db = mongo[env["DB_NAME"]]
    nhl = NHLClient()

    # nhl_id -> our player _id
    nhl_to_local: dict[int, str] = {}
    async for p in db.players.find({"nhl_id": {"$ne": None}}, {"nhl_id": 1}):
        nhl_to_local[int(p["nhl_id"])] = str(p["_id"])
    print(f"Mapped {len(nhl_to_local)} players")

    # Walk back day-by-day
    today = datetime.now(timezone.utc).date()
    games_upserted = 0
    logs_upserted = 0
    for d in range(LOOKBACK_DAYS):
        target = today - timedelta(days=d)
        try:
            sched = nhl.schedule.daily_schedule(date=target.isoformat())
        except Exception as e:
            print(f"  {target}: schedule fetch failed: {e}")
            continue
        games = sched.get("games", [])
        if not games:
            continue
        for g in games:
            state = g.get("gameState")
            if state not in ("OFF", "FINAL"):
                continue
            gid = g.get("id")
            home = g.get("homeTeam", {}) or {}
            away = g.get("awayTeam", {}) or {}
            game_doc = {
                "nhl_game_id": gid,
                "season": g.get("season"),
                "game_type": g.get("gameType"),
                "date": target.isoformat(),
                "date_dt": datetime.combine(target, datetime.min.time(), tzinfo=timezone.utc),
                "state": state,
                "home_team_abbr": home.get("abbrev"),
                "home_team_score": home.get("score"),
                "away_team_abbr": away.get("abbrev"),
                "away_team_score": away.get("score"),
                "venue": (g.get("venue") or {}).get("default"),
            }
            await db.games.update_one({"nhl_game_id": gid}, {"$set": game_doc}, upsert=True)
            games_upserted += 1

            # Per-player stats from boxscore
            try:
                box = nhl.game_center.boxscore(gid)
            except Exception as e:
                print(f"  game {gid} boxscore failed: {e}")
                continue
            ps = box.get("playerByGameStats") or {}
            for side_key, team_abbr in (("homeTeam", home.get("abbrev")), ("awayTeam", away.get("abbrev"))):
                side = ps.get(side_key) or {}
                for group in ("forwards", "defense", "goalies"):
                    for sp in side.get(group, []) or []:
                        nhl_pid = sp.get("playerId")
                        local_pid = nhl_to_local.get(int(nhl_pid)) if nhl_pid else None
                        if not local_pid:
                            continue
                        log_doc = {
                            "player_id": local_pid,
                            "nhl_player_id": int(nhl_pid),
                            "nhl_game_id": gid,
                            "team_abbr": team_abbr,
                            "date": target.isoformat(),
                            "date_dt": game_doc["date_dt"],
                            "position": sp.get("position"),
                            "goals": sp.get("goals", 0) or 0,
                            "assists": sp.get("assists", 0) or 0,
                            "points": (sp.get("goals") or 0) + (sp.get("assists") or 0),
                            "plus_minus": sp.get("plusMinus", 0) or 0,
                            "pim": sp.get("pim", 0) or 0,
                            "hits": sp.get("hits", 0) or 0,
                            "blocks": sp.get("blockedShots", 0) or 0,
                            "ppg": sp.get("powerPlayGoals", 0) or 0,
                            "shg": sp.get("shortHandedGoals", 0) or 0,
                            "sog": sp.get("sog", 0) or 0,
                            "fow_pct": sp.get("faceoffWinningPctg") or 0,
                            "toi": sp.get("toi"),
                            "shifts": sp.get("shifts"),
                            "giveaways": sp.get("giveaways"),
                            "takeaways": sp.get("takeaways"),
                        }
                        await db.player_game_logs.update_one(
                            {"nhl_player_id": int(nhl_pid), "nhl_game_id": gid},
                            {"$set": log_doc}, upsert=True,
                        )
                        logs_upserted += 1
        if d % 5 == 4:
            print(f"  ...processed {d+1} days; games={games_upserted}, logs={logs_upserted}")

    # Helpful indexes
    await db.player_game_logs.create_index([("player_id", 1), ("date_dt", -1)])
    await db.player_game_logs.create_index([("nhl_player_id", 1), ("nhl_game_id", 1)], unique=True)
    await db.games.create_index([("nhl_game_id", 1)], unique=True)
    await db.games.create_index([("date_dt", -1)])

    print(f"DONE — games upserted: {games_upserted}, player_game_logs upserted: {logs_upserted}")


if __name__ == "__main__":
    asyncio.run(main())
