"""Phase 21: verify that PUT /awards with championship_won triggers conditional trades.

Strategy: insert a minimal accepted conditional trade doc directly into MongoDB
between Zarek's Frozen and another Ice Kings team, with a team_level 'won_championship' condition
with operator 'eq', threshold 1, subject='offered'. Then PUT awards → expect unlocked_trades>=1
and the trade status to be 'executed'.
"""
import os
import asyncio
import pytest
from datetime import datetime, timezone
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://dynasty-preview.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"
MONGO_URL = "mongodb://localhost:27017"
DB_NAME = "test_database"

CHRIS_EMAIL = "chriszarek@gmail.com"
CHRIS_PASS = "Chris2026!"
ICE_KINGS_ID = "69e46af167999bfb85c39628"
ZAREK_TEAM_ID = "69e59b30cbd3fea02a914c61"


@pytest.mark.asyncio
async def test_conditional_trade_unlocked_on_championship():
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]

    # Pick a second team in the league
    other = await db.teams.find_one({"league_id": ICE_KINGS_ID, "_id": {"$ne": ObjectId(ZAREK_TEAM_ID)}})
    assert other, "need at least 2 teams in Ice Kings"
    other_id = str(other["_id"])

    # Cleanup any prior seeded trade
    await db.trades.delete_many({"_tag": "PHASE21_TRIGGER_TEST"})

    # Ensure Zarek's Frozen has NO championship_won_at
    await db.teams.update_one({"_id": ObjectId(ZAREK_TEAM_ID)}, {"$unset": {"championship_won_at": ""}})

    trade_doc = {
        "league_id": ICE_KINGS_ID,
        "proposer_team_id": ZAREK_TEAM_ID,
        "target_team_id": other_id,
        "offered_assets": [],
        "requested_assets": [],
        "status": "accepted",
        "conditional": True,
        "conditions": [{
            "subject": "offered",
            "subject_type": "team",
            "metric": "won_championship",
            "operator": "eq",
            "threshold": 1,
        }],
        "created_at": datetime.now(timezone.utc),
        "_tag": "PHASE21_TRIGGER_TEST",
    }
    ins = await db.trades.insert_one(trade_doc)
    trade_id = ins.inserted_id

    try:
        # Login as chris and PUT championship_won=True
        s = requests.Session()
        r = s.post(f"{API}/auth/login", json={"email": CHRIS_EMAIL, "password": CHRIS_PASS}, timeout=20)
        assert r.status_code == 200

        r2 = s.put(
            f"{API}/leagues/{ICE_KINGS_ID}/teams/{ZAREK_TEAM_ID}/awards",
            json={"championship_won": True},
            timeout=30,
        )
        assert r2.status_code == 200, r2.text
        body = r2.json()
        assert body.get("championship_won_at") is not None
        assert body.get("unlocked_trades", 0) >= 1, f"expected unlocked_trades>=1, got {body}"

        # Verify trade status is now 'executed'
        doc = await db.trades.find_one({"_id": trade_id})
        assert doc is not None
        assert doc.get("status") == "executed", f"trade status={doc.get('status')}"
    finally:
        # Cleanup - clear the champion flag and remove seeded trade
        await db.trades.delete_one({"_id": trade_id})
        s2 = requests.Session()
        s2.post(f"{API}/auth/login", json={"email": CHRIS_EMAIL, "password": CHRIS_PASS}, timeout=20)
        s2.put(f"{API}/leagues/{ICE_KINGS_ID}/teams/{ZAREK_TEAM_ID}/awards", json={"championship_won": False}, timeout=20)
        client.close()
