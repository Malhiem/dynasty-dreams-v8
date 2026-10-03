"""Synthetic stored game inputs for HTTP live-score consumer tests."""
import os
from datetime import datetime, timezone, timedelta
import pytest
from pymongo import MongoClient

@pytest.fixture(scope="module", autouse=True)
def live_snapshot_inputs(_global_pollution_sweep):
    assert os.environ.get("TEST_SUITE_ISOLATED") == "1"
    with MongoClient(os.environ["MONGO_URL"]) as client:
        db = client[os.environ["DB_NAME"]]
        now = datetime.now(timezone.utc).isoformat()
        db.system_state.update_one({"_id": "live_scoring"}, {"$set": {"latest": {"date": now[:10], "polled_at": now,
            "games_processed": 1, "players_updated": 1038, "playoff_games": 0,
            "games": [{"id": 2026020001, "state": "FINAL", "type": 2, "is_playoff": False, "away": "EDM", "home": "TOR", "away_score": 2, "home_score": 1}]}}}, upsert=True)
        db.players.update_many({"_suite_baseline": True}, {"$set": {"live_stats": {"2026020001": {"goals": 1, "assists": 1, "shots": 3, "game_state": "FINAL", "game_date": now[:10]}}}})
        # Stored worker totals and an active schedule are explicit consumer inputs.
        db.teams.update_many({}, {"$set": {"live_points": 100.0}})
        start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        for league in db.leagues.find({"_suite_baseline": True}):
            lid = str(league["_id"])
            db.leagues.update_one({"_id": league["_id"]}, {"$set": {"current_week": 1, "season_start_date": start.isoformat()}})
            teams = list(db.teams.find({"league_id": lid}))
            for i in range(0, len(teams)-1, 2):
                home, away = teams[i:i+2]
                db.matchups.insert_one({"league_id": lid, "week": 1, "status": "scheduled",
                    "home_team_id": str(home["_id"]), "away_team_id": str(away["_id"]),
                    "home_team_name": home["name"], "away_team_name": away["name"],
                    "start_date": start.isoformat(), "end_date": (start + timedelta(days=6)).isoformat(), "_live_fixture": True})
        yield
        db.matchups.delete_many({"_live_fixture": True})
        db.teams.update_many({}, {"$set": {"live_points": 0.0}})
        db.system_state.delete_one({"_id": "live_scoring"})
        db.players.update_many({"_suite_baseline": True}, {"$set": {"live_stats": {}}})
