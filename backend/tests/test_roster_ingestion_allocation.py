"""Provider-only fixtures exercise the real importer and live allocation."""
import os
import uuid
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient
import pytest


@pytest.mark.asyncio
@pytest.mark.parametrize("scoring_format", ["h2h-points", "h2h-categories", "rotisserie"])
async def test_native_mongo_transfer_corrections_and_bench(monkeypatch, scoring_format):
    assert os.environ.get("ROSTER_TEST_ISOLATED") == "1"
    assert os.environ["DB_NAME"].startswith("roster_fixes_")
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"][:40] + "_" + uuid.uuid4().hex[:12]]
    import nhlpy
    from live_scoring_worker import run_once
    lid, a, b, pid = [ObjectId() for _ in range(4)]
    game = datetime.now(timezone.utc) - timedelta(days=3)
    transfer = game + timedelta(hours=1)
    goals = 1
    gids = [2026999101, 2026999102]
    class Provider:
        def __init__(self):
            self.schedule = SimpleNamespace(daily_schedule=lambda **kw: {"date": game.date().isoformat(), "games": [{"id": gid, "gameType": 2, "gameState": "FINAL"} for gid in gids]})
            self.game_center = SimpleNamespace(boxscore=lambda **kw: {"homeTeam": {"abbrev": "TOR"}, "playerByGameStats": {"homeTeam": {"forwards": [{"playerId": 990123, "name": {"default": "Allocation regression"}, "goals": goals, "assists": 0, "sog": 0, "toi": "20:00"}]}}})
    monkeypatch.setattr(nhlpy, "NHLClient", Provider)
    try:
        await db.leagues.insert_one({"_id": lid, "scoring_format": scoring_format})
        await db.scoring_configs.insert_one({"league_id": str(lid), "skater_scoring": {"goals": 7}})
        await db.players.insert_one({"_id": pid, "nhl_id": 990123, "name": "Allocation regression", "position": "C"})
        await db.teams.insert_many([{"_id": a, "league_id": str(lid), "roster": [], "lineup": {}}, {"_id": b, "league_id": str(lid), "roster": [str(pid)], "lineup": {str(pid): {"section": "bench", "slot": "BN"}}}])
        await db.player_ownership_periods.insert_many([{"player_id": str(pid), "league_id": str(lid), "team_id": str(a), "acquired_at": game - timedelta(days=1), "released_at": transfer}, {"player_id": str(pid), "league_id": str(lid), "team_id": str(b), "acquired_at": transfer, "released_at": None}])
        await db.lineup_status_periods.insert_many([{"player_id": str(pid), "league_id": str(lid), "team_id": str(a), "position": "forward", "started_at": game - timedelta(days=1), "ended_at": transfer}, {"player_id": str(pid), "league_id": str(lid), "team_id": str(b), "position": "bench", "started_at": transfer, "ended_at": None}])
        assert (await db.player_ownership_periods.find_one({}))["acquired_at"].tzinfo is None
        await db.games.insert_many([{"nhl_game_id": gid, "date": game.date().isoformat(), "start_time": (game + timedelta(hours=2 * index)).isoformat()} for index, gid in enumerate(gids)])
        for goals in (1, 2, 2):
            summary = await run_once(db)
            assert summary["games_processed"] == 2
            assert (await db.teams.find_one({"_id": a}))["live_points"] == 7 * goals
            assert (await db.teams.find_one({"_id": b}))["live_points"] == 0
            assert len((await db.players.find_one({"_id": pid}))["live_stats"]) == 2
    finally:
        await client.drop_database(db.name)
        client.close()
