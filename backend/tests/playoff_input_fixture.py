"""Explicit bracket inputs and commissioner actions for legacy playoff regressions."""
import os
from datetime import datetime, timezone
import pytest
import requests
from bson import ObjectId
from pymongo import MongoClient
from tests.http_test_auth import test_admin_headers

@pytest.fixture(scope="module", autouse=True)
def playoff_inputs(_global_pollution_sweep, request):
    assert os.environ.get("TEST_SUITE_ISOLATED") == "1"
    api = os.environ["REACT_APP_BACKEND_URL"] + "/api"
    lid = "69e46af167999bfb85c39628"
    login = requests.post(api + "/auth/login", json={"email": os.environ.get("TEST_OWNER_EMAIL", "test-owner@e2e.dynastydreams.com"),
        "password": os.environ.get("TEST_OWNER_PASSWORD", "e2e-owner-password")})
    assert login.status_code == 200, login.text
    headers = {"Authorization": "Bearer " + login.json()["access_token"]}
    with MongoClient(os.environ["MONGO_URL"]) as client:
        db = client[os.environ["DB_NAME"]]
        db.leagues.update_one({"_id": ObjectId(lid)}, {"$set": {"setup_wizard_complete": True, "salary_cap_enabled": False}})
        for i, team in enumerate(db.teams.find({"league_id": lid})):
            db.teams.update_one({"_id": team["_id"]}, {"$set": {"division": "North" if i % 2 else "South"}})
        draft = db.drafts.insert_one({"league_id": lid, "status": "scheduled", "total_rounds": 5,
            "scheduled_time": datetime.now(timezone.utc).isoformat(), "_playoff_fixture": True})
        bracket = requests.get(f"{api}/leagues/{lid}/playoff-bracket", headers=test_admin_headers()).json()
        for match in bracket["rounds"][0]["matchups"]:
            home, away = match["high_seed"], match["low_seed"]
            db.matchups.insert_one({"league_id": lid, "week": 19, "is_playoff": True, "bracket_round": 1,
                "status": "scheduled", "home_team_id": home["team_id"], "away_team_id": away["team_id"],
                "home_team_name": home["team_name"], "away_team_name": away["team_name"],
                "home_score": 0, "away_score": 0, "_playoff_fixture": True})
        if "197" in request.module.__name__:
            # Produce a decided final via the actual advancement endpoint.
            for round_index in range(3):
                bracket = requests.get(f"{api}/leagues/{lid}/playoff-bracket", headers=test_admin_headers()).json()
                for match in bracket["rounds"][round_index]["matchups"]:
                    winner = match.get("home_team_id") or (match.get("high_seed") or {})["team_id"]
                    response = requests.post(f"{api}/leagues/{lid}/playoffs/mark-winner", headers=headers,
                        json={"matchup_id": match["matchup_id"], "winner_team_id": winner})
                    assert response.status_code == 200, response.text
        yield
        db.drafts.delete_one({"_id": draft.inserted_id})
        db.matchups.delete_many({"league_id": lid, "is_playoff": True})
