"""HTTP ownership regression with a genuinely free disposable player."""
import os
import uuid
import pytest
import requests
from bson import ObjectId
from pymongo import MongoClient


def test_roster_add_drop_opens_and_closes_ownership():
    assert os.environ.get("TEST_SUITE_ISOLATED") == "1"
    base = os.environ["REACT_APP_BACKEND_URL"]
    assert base == "http://web"
    with requests.Session() as api, MongoClient(os.environ["MONGO_URL"]) as client:
        db = client[os.environ["DB_NAME"]]
        login = api.post(base + "/api/auth/login", json={"email": os.environ["ADMIN_EMAIL"], "password": os.environ["ADMIN_PASSWORD"]}, timeout=10)
        assert login.status_code == 200, login.text
        league = api.post(base + "/api/leagues", json={"name": "TEST_OwnershipSweep_" + uuid.uuid4().hex, "sport": "nhl", "format": "dynasty", "scoring_format": "head_to_head", "max_teams": 4, "salary_cap_enabled": False}, timeout=10)
        assert league.status_code == 200, league.text
        lid = league.json()["id"]
        team = db.teams.find_one({"league_id": lid, "owner_id": login.json()["id"]})
        assert team is not None
        tid = str(team["_id"])
        pid = db.players.insert_one({"name": "Ownership sweep player", "position": "C", "salary": 1_000_000}).inserted_id
        try:
            added = api.post(base + f"/api/roster/{tid}/add", json={"player_id": str(pid)}, timeout=10)
            assert added.status_code == 200, added.text
            query = {"league_id": lid, "team_id": tid, "player_id": str(pid)}
            periods = list(db.player_ownership_periods.find(query))
            assert len(periods) == 1
            assert periods[0].get("released_at") is None
            assert str(pid) in db.teams.find_one({"_id": team["_id"]})["roster"]
            dropped = api.post(base + f"/api/roster/{tid}/drop", json={"player_id": str(pid)}, timeout=10)
            assert dropped.status_code == 200, dropped.text
            periods = list(db.player_ownership_periods.find(query))
            assert len(periods) == 1
            assert periods[0].get("released_at") is not None
            assert str(pid) not in db.teams.find_one({"_id": team["_id"]})["roster"]
        finally:
            db.player_ownership_periods.delete_many({"league_id": lid})
            db.lineup_status_periods.delete_many({"league_id": lid})
            db.players.delete_one({"_id": pid})
            db.teams.delete_many({"league_id": lid})
            db.leagues.delete_one({"_id": ObjectId(lid)})
