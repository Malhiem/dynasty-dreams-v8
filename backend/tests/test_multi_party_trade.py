"""End-to-end tests for the multi-party (3+ team) trade flow.

Covers:
    * Creation: validates parties, league membership, proposer auto-accept.
    * Accept flow: each non-proposer must accept; auto-execute on final accept.
    * Reject flow: any party rejecting the trade kills it.
    * Execution routing: assets flow correctly across all parties via to_team_id
      and via auto-routing through matching `receives` entries.
    * Backwards compat: existing 2-party POST /api/trades still works.

Run: pytest -xvs /app/backend/tests/test_multi_party_trade.py
"""
import asyncio
import os
import pytest
import requests
from dotenv import dotenv_values
from motor.motor_asyncio import AsyncIOMotorClient
from passlib.context import CryptContext

ENV = dotenv_values("/app/backend/.env")
FRONTEND_ENV = dotenv_values("/app/frontend/.env")
API_URL = (FRONTEND_ENV.get("REACT_APP_BACKEND_URL") or "").rstrip("/") + "/api"
MONGO_URL = ENV["MONGO_URL"]
DB_NAME = ENV["DB_NAME"]
PWD_CTX = CryptContext(schemes=["bcrypt"], deprecated="auto")


@pytest.fixture(scope="module")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


async def _setup_three_user_league():
    """Create three users + a league with three teams owned by each user.
    Returns dict of users with tokens, team_ids, league_id, and three players
    seeded onto each roster."""
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]

    # Use stable test emails so the seed is idempotent
    USERS = [
        {"email": "tri_user_a@test.com", "password": "TriTest1!", "username": "TriUserA"},
        {"email": "tri_user_b@test.com", "password": "TriTest1!", "username": "TriUserB"},
        {"email": "tri_user_c@test.com", "password": "TriTest1!", "username": "TriUserC"},
    ]
    user_ids = []
    for u in USERS:
        existing = await db.users.find_one({"email": u["email"]})
        if existing:
            await db.users.update_one(
                {"_id": existing["_id"]},
                {"$set": {
                    "password_hash": PWD_CTX.hash(u["password"]),
                    "failed_login_attempts": 0, "lockout_until": None, "is_active": True,
                }},
            )
            user_ids.append(str(existing["_id"]))
        else:
            from bson import ObjectId
            from datetime import datetime, timezone
            uid = ObjectId()
            await db.users.insert_one({
                "_id": uid, "email": u["email"],
                "password_hash": PWD_CTX.hash(u["password"]),
                "username": u["username"], "name": u["username"],
                "role": "user",
                "created_at": datetime.now(timezone.utc),
            })
            user_ids.append(str(uid))

    # Find or create a league owned by user A
    league = await db.leagues.find_one({"name": "Multi-Party Trade Test League"})
    if not league:
        from bson import ObjectId
        lid = ObjectId()
        league_doc = {
            "_id": lid,
            "name": "Multi-Party Trade Test League",
            "format": "head_to_head",
            "league_type": "redraft",
            "scoring_format": "head_to_head",
            "team_size": 8, "max_teams": 8, "current_teams": 3,
            "commissioner_id": user_ids[0], "co_commissioners": [],
            "is_private": True,
        }
        await db.leagues.insert_one(league_doc)
        league = league_doc

    league_id = str(league["_id"])

    # Create three teams (one per user)
    team_docs = []
    for i, u_id in enumerate(user_ids):
        existing_team = await db.teams.find_one({"league_id": league_id, "owner_id": u_id})
        if not existing_team:
            from bson import ObjectId
            t = {
                "_id": ObjectId(),
                "league_id": league_id, "owner_id": u_id,
                "name": f"Tri Team {chr(65+i)}",  # A, B, C
                "logo_abbr": f"T{chr(65+i)}",
                "roster": [], "wins": 0, "losses": 0, "ties": 0, "points_for": 0,
            }
            await db.teams.insert_one(t)
            team_docs.append(t)
        else:
            team_docs.append(existing_team)

    # Pick three different player ids and seed one onto each team's roster
    players = await db.players.find({}).limit(6).to_list(6)
    assert len(players) >= 3, "Need at least 3 players seeded in DB for this test"

    # Reset rosters cleanly for the test
    for i, t in enumerate(team_docs):
        await db.teams.update_one(
            {"_id": t["_id"]},
            {"$set": {"roster": [str(players[i]["_id"])]}},
        )
        team_docs[i]["roster"] = [str(players[i]["_id"])]

    client.close()

    # Login each user via API to get tokens
    sessions = []
    for u in USERS:
        r = requests.post(
            f"{API_URL}/auth/login",
            json={"email": u["email"], "password": u["password"]},
            timeout=10,
        )
        assert r.status_code == 200, f"Login failed for {u['email']}: {r.text}"
        sessions.append({"email": u["email"], "token": r.json()["access_token"]})

    return {
        "users": [
            {**s, "team_id": str(team_docs[i]["_id"]),
             "team_name": team_docs[i]["name"],
             "player_id": str(players[i]["_id"]),
             "player_name": players[i].get("name")}
            for i, s in enumerate(sessions)
        ],
        "league_id": league_id,
    }


def _h(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_multi_party_trade_full_flow():
    ctx = await _setup_three_user_league()
    users = ctx["users"]
    league_id = ctx["league_id"]
    A, B, C = users[0], users[1], users[2]

    # ── 1. Create a 3-way trade: A → B (player A), B → C (player B), C → A (player C)
    payload = {
        "league_id": league_id,
        "parties": [
            {"team_id": A["team_id"],
             "sends": [{"asset_type": "player", "player_id": A["player_id"], "to_team_id": B["team_id"]}],
             "receives": [{"asset_type": "player", "player_id": C["player_id"]}]},
            {"team_id": B["team_id"],
             "sends": [{"asset_type": "player", "player_id": B["player_id"], "to_team_id": C["team_id"]}],
             "receives": [{"asset_type": "player", "player_id": A["player_id"]}]},
            {"team_id": C["team_id"],
             "sends": [{"asset_type": "player", "player_id": C["player_id"], "to_team_id": A["team_id"]}],
             "receives": [{"asset_type": "player", "player_id": B["player_id"]}]},
        ],
        "message": "3-way swap",
    }
    r = requests.post(f"{API_URL}/trades/multi", json=payload, headers=_h(A["token"]), timeout=10)
    assert r.status_code == 200, r.text
    trade = r.json()
    assert trade["is_multi_party"] is True
    assert len(trade["parties"]) == 3
    assert trade["status"] == "pending"
    # Proposer auto-accepted
    proposer_idx = trade["proposer_party_index"]
    assert trade["parties"][proposer_idx]["accepted"] is True
    trade_id = trade["_id"]

    # ── 2. B accepts; trade still pending (C hasn't responded)
    r = requests.post(
        f"{API_URL}/trades/{trade_id}/party-respond",
        json={"action": "accept"}, headers=_h(B["token"]), timeout=10,
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "pending"
    assert r.json()["all_accepted"] is False

    # ── 3. Non-party user cannot respond
    # Login admin and try
    admin_login = requests.post(
        f"{API_URL}/auth/login",
        json={"email": ENV["ADMIN_EMAIL"], "password": ENV["ADMIN_PASSWORD"]},
        timeout=10,
    )
    assert admin_login.status_code == 200
    r = requests.post(
        f"{API_URL}/trades/{trade_id}/party-respond",
        json={"action": "accept"}, headers=_h(admin_login.json()["access_token"]), timeout=10,
    )
    assert r.status_code == 403, r.text

    # ── 4. C accepts → auto-executes
    r = requests.post(
        f"{API_URL}/trades/{trade_id}/party-respond",
        json={"action": "accept"}, headers=_h(C["token"]), timeout=10,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["all_accepted"] is True
    assert body["executed"] is True
    assert body["status"] == "executed"

    # ── 5. Verify rosters actually changed: each player ended up on the right team
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    from bson import ObjectId
    a_team = await db.teams.find_one({"_id": ObjectId(A["team_id"])})
    b_team = await db.teams.find_one({"_id": ObjectId(B["team_id"])})
    c_team = await db.teams.find_one({"_id": ObjectId(C["team_id"])})
    client.close()
    assert C["player_id"] in (a_team.get("roster") or []), "A should have C's player"
    assert A["player_id"] in (b_team.get("roster") or []), "B should have A's player"
    assert B["player_id"] in (c_team.get("roster") or []), "C should have B's player"
    # And original players left
    assert A["player_id"] not in (a_team.get("roster") or [])
    assert B["player_id"] not in (b_team.get("roster") or [])
    assert C["player_id"] not in (c_team.get("roster") or [])


@pytest.mark.asyncio
async def test_multi_party_trade_rejected_kills_trade():
    ctx = await _setup_three_user_league()
    users = ctx["users"]
    league_id = ctx["league_id"]
    A, B, C = users[0], users[1], users[2]

    # Reset rosters first (in case prior test executed)
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    from bson import ObjectId
    for u in users:
        await db.teams.update_one(
            {"_id": ObjectId(u["team_id"])},
            {"$set": {"roster": [u["player_id"]]}},
        )
    client.close()

    payload = {
        "league_id": league_id,
        "parties": [
            {"team_id": A["team_id"],
             "sends": [{"asset_type": "player", "player_id": A["player_id"], "to_team_id": B["team_id"]}],
             "receives": [{"asset_type": "player", "player_id": C["player_id"]}]},
            {"team_id": B["team_id"],
             "sends": [{"asset_type": "player", "player_id": B["player_id"], "to_team_id": C["team_id"]}],
             "receives": [{"asset_type": "player", "player_id": A["player_id"]}]},
            {"team_id": C["team_id"],
             "sends": [{"asset_type": "player", "player_id": C["player_id"], "to_team_id": A["team_id"]}],
             "receives": [{"asset_type": "player", "player_id": B["player_id"]}]},
        ],
    }
    r = requests.post(f"{API_URL}/trades/multi", json=payload, headers=_h(A["token"]), timeout=10)
    assert r.status_code == 200, r.text
    trade_id = r.json()["_id"]

    # B rejects
    r = requests.post(
        f"{API_URL}/trades/{trade_id}/party-respond",
        json={"action": "reject"}, headers=_h(B["token"]), timeout=10,
    )
    assert r.status_code == 200
    assert r.json()["status"] == "rejected"

    # Verify rosters NOT changed
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    a_team = await db.teams.find_one({"_id": ObjectId(A["team_id"])})
    client.close()
    assert A["player_id"] in (a_team.get("roster") or [])


@pytest.mark.asyncio
async def test_legacy_two_party_trade_still_works():
    """Existing /api/trades endpoint must continue to work for 2-team trades."""
    ctx = await _setup_three_user_league()
    A, B, _ = ctx["users"][0], ctx["users"][1], ctx["users"][2]
    league_id = ctx["league_id"]

    # Reset A and B rosters
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    from bson import ObjectId
    await db.teams.update_one({"_id": ObjectId(A["team_id"])}, {"$set": {"roster": [A["player_id"]]}})
    await db.teams.update_one({"_id": ObjectId(B["team_id"])}, {"$set": {"roster": [B["player_id"]]}})
    client.close()

    payload = {
        "league_id": league_id,
        "target_team_id": B["team_id"],
        "assets_offered": [{"asset_type": "player", "player_id": A["player_id"]}],
        "assets_requested": [{"asset_type": "player", "player_id": B["player_id"]}],
    }
    r = requests.post(f"{API_URL}/trades", json=payload, headers=_h(A["token"]), timeout=10)
    assert r.status_code == 200, r.text
    trade_id = r.json()["_id"]

    # B accepts via legacy endpoint
    r = requests.post(f"{API_URL}/trades/{trade_id}/accept", headers=_h(B["token"]), timeout=10)
    assert r.status_code == 200, r.text
    assert r.json()["executed"] is True
