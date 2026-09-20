"""Deterministic test: fresh playoff totals must use only playoff-period stats.

Scenario
--------
League  : condensed_roto, playoff_roto_fresh_totals=True, weeks 19-21
Player  : season_stats.goals = 200, period_stats.19.goals = 2
Expected: standings returns goals = 2 for that team (NOT 200).
"""
import os
import pytest
import pymongo
from bson import ObjectId

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")

@pytest.fixture(scope="module")
def db():
    client = pymongo.MongoClient(MONGO_URL)
    return client[DB_NAME]


@pytest.fixture(scope="module")
def league_id(db):
    """Find (or create) a condensed_roto league with fresh totals."""
    league = db.leagues.find_one({
        "playoff_format": "condensed_roto",
        "playoff_roto_fresh_totals": True,
    })
    if league:
        return str(league["_id"])
    pytest.skip("No condensed_roto league with fresh_totals found")


@pytest.fixture(scope="module")
def team_and_player(db, league_id):
    team = db.teams.find_one({"league_id": league_id})
    assert team and team.get("roster"), "Need a team with roster"
    pid = team["roster"][0]
    return str(team["_id"]), pid


@pytest.fixture(autouse=True)
def seed_and_cleanup(db, team_and_player):
    _, pid = team_and_player
    oid = ObjectId(pid)
    # Save original
    orig = db.players.find_one({"_id": oid})
    orig_season = (orig.get("season_stats") or {}).get("goals", 0)
    orig_ps = orig.get("period_stats") or {}

    # Seed deterministic values
    db.players.update_one({"_id": oid}, {"$set": {
        "season_stats.goals": 200,
        "period_stats.19.goals": 2,
        "period_stats.20.goals": 0,
        "period_stats.21.goals": 0,
    }})
    yield
    # Restore
    db.players.update_one({"_id": oid}, {"$set": {
        "season_stats.goals": orig_season,
        "period_stats": orig_ps,
    }})


def test_standings_use_playoff_period_stats(db, league_id, team_and_player):
    """GET /roto/standings must return playoff-period sum, not season_stats."""
    import requests
    api = os.popen("grep REACT_APP_BACKEND_URL /app/frontend/.env | cut -d '=' -f2").read().strip()
    token = requests.post(f"{api}/api/auth/login", json={
        "email": "admin@dynastydreams.com", "password": "Admin123!",
    }).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    resp = requests.get(f"{api}/api/leagues/{league_id}/roto/standings", headers=headers)
    assert resp.status_code == 200
    data = resp.json()

    # Metadata
    assert data.get("fresh_totals") is True
    assert data.get("periods") == [19, 20, 21]

    # Goals for our team must be 2 (playoff sum), NOT 200 (season)
    tid, _ = team_and_player
    goals_cat = next(c for c in data["categories"] if c["key"] == "goals")
    goals_val = goals_cat["team_stats"].get(tid, -1)
    assert goals_val == 2.0, f"Expected 2 (playoff sum), got {goals_val}"
