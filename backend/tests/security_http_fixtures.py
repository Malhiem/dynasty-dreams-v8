"""Fixtures for HTTP security regressions; use only a disposable API + Mongo stack.

MONGO_URL and DB_NAME must identify the running API's database. The user
registration probe below verifies that connection before database assertions.
"""
import os
import uuid

import pytest
import requests
from bson import ObjectId
from pymongo import MongoClient

API_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001").rstrip("/")
PASSWORD = "SecurityFixture2026!"


@pytest.fixture
def security_db(_global_pollution_sweep):
    assert os.environ.get("SECURITY_TEST_ISOLATED") == "1", "Run against a disposable stack with SECURITY_TEST_ISOLATED=1"
    client = MongoClient(os.environ["MONGO_URL"], serverSelectionTimeoutMS=3000)
    try:
        yield client[os.environ["DB_NAME"]]
    finally:
        client.close()


@pytest.fixture
def security_users(security_db):
    created = []
    def create():
        name = f"security_{uuid.uuid4().hex[:12]}"
        response = requests.post(f"{API_URL}/api/auth/register", json={
            "username": name, "email": f"{name}@example.com", "password": PASSWORD,
        }, timeout=10)
        assert response.status_code == 200, response.text
        user = {**response.json(), "username": name, "email": f"{name}@example.com"}
        created.append(user)
        assert security_db.users.find_one({"_id": ObjectId(user["id"])}), "MONGO_URL/DB_NAME do not match the API database"
        assert user.get("role") != "admin"
        user["headers"] = {"Authorization": f"Bearer {user['access_token']}"}
        return user
    try:
        yield create
    finally:
        for user in created:
            security_db.password_reset_tokens.delete_many({"user_id": user["id"]})
            security_db.password_reset_throttle.delete_many({"email": user["email"]})
            security_db.users.delete_one({"_id": ObjectId(user["id"])})


@pytest.fixture
def private_team(security_users, security_db):
    owner = security_users()
    response = requests.post(f"{API_URL}/api/leagues", headers=owner["headers"], json={
        "name": f"TEST_security_{uuid.uuid4().hex[:8]}", "sport": "nhl", "format": "dynasty",
        "scoring_format": "head_to_head", "max_teams": 8, "is_private": True,
    }, timeout=10)
    assert response.status_code == 200, response.text
    league_id = response.json()["id"]
    team = {"league_id": league_id, "name": "Security fixture team", "owner_id": owner["id"],
            "owner_name": owner["username"], "roster": [], "lineup": {}, "wins": 0, "losses": 0, "ties": 0,
            "points_for": 0, "points_against": 0}
    team_id = str(security_db.teams.insert_one(team).inserted_id)
    try:
        yield {"owner": owner, "id": team_id, "league_id": league_id}
    finally:
        security_db.teams.delete_many({"league_id": league_id})
        security_db.leagues.delete_one({"_id": ObjectId(league_id)})
