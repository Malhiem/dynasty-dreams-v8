"""Iter 84 — IR / IR+ / Taxi / Minors / Bench cap enforcement on lineup
saves. The lineup endpoint should reject oversized special sections with a
clear "Move N to another section" message.
"""
import os
import sys

import pytest
from httpx import AsyncClient
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _backend_url():
    p = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", ".env")
    with open(p) as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip()


def _env(key):
    p = os.path.join(os.path.dirname(__file__), "..", ".env")
    with open(p) as f:
        for line in f:
            line = line.strip()
            if line.startswith(f"{key}="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")


BASE = _backend_url()
EMAIL = os.environ.get("TEST_OWNER_EMAIL", "test-owner@e2e.dynastydreams.com")
PASSWORD = os.environ.get("TEST_OWNER_PASSWORD", "e2e-owner-password")
LID = "69e46af167999bfb85c39628"


async def _login(client):
    r = await client.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
    return r.json()["access_token"]


@pytest.mark.asyncio
async def test_ir_cap_blocks_oversized_lineup():
    """An IR section with 3 players when ir_slots=2 must 400 with a clear
    'Move 1 to another section' message."""
    mongo = AsyncIOMotorClient(_env("MONGO_URL"))
    db = mongo[_env("DB_NAME")]
    try:
        before = await db.leagues.find_one({"_id": ObjectId(LID)})
        orig_ir = before.get("ir_slots")
        await db.leagues.update_one(
            {"_id": ObjectId(LID)},
            {"$set": {"ir_slots": 2}},
        )
        try:
            async with AsyncClient(base_url=BASE, timeout=20) as client:
                token = await _login(client)
                h = {"Authorization": f"Bearer {token}"}
                me = (await client.get("/api/auth/me", headers=h)).json()
                teams = (await client.get(f"/api/teams?league_id={LID}", headers=h)).json()
                mine = next(t for t in teams if t["owner_id"] == me["id"])
                roster = mine.get("roster") or []
                if len(roster) < 3:
                    pytest.skip("not enough players to test IR cap")
                lineup = {
                    str(roster[0]): {"section": "ir", "slot": "IR1"},
                    str(roster[1]): {"section": "ir", "slot": "IR2"},
                    str(roster[2]): {"section": "ir", "slot": "IR3"},
                }
                r = await client.post(
                    f"/api/teams/{mine['id']}/lineup",
                    headers=h,
                    json={"lineup": lineup},
                )
                assert r.status_code == 400, r.text
                detail = r.json()["detail"]
                assert "IR" in detail and "3" in detail and "2" in detail, detail
                assert "Move 1" in detail, detail
        finally:
            await db.leagues.update_one(
                {"_id": ObjectId(LID)},
                {"$set": {"ir_slots": orig_ir if orig_ir is not None else 0}},
            )
    finally:
        mongo.close()


@pytest.mark.asyncio
async def test_taxi_disabled_blocks_use():
    """When taxi_squad_size=0, placing any player on taxi must 400 with a
    'Taxi Squad is disabled' message."""
    mongo = AsyncIOMotorClient(_env("MONGO_URL"))
    db = mongo[_env("DB_NAME")]
    try:
        before = await db.leagues.find_one({"_id": ObjectId(LID)})
        orig_taxi = before.get("taxi_squad_size")
        await db.leagues.update_one(
            {"_id": ObjectId(LID)},
            {"$set": {"taxi_squad_size": 0}},
        )
        try:
            async with AsyncClient(base_url=BASE, timeout=20) as client:
                token = await _login(client)
                h = {"Authorization": f"Bearer {token}"}
                me = (await client.get("/api/auth/me", headers=h)).json()
                teams = (await client.get(f"/api/teams?league_id={LID}", headers=h)).json()
                mine = next(t for t in teams if t["owner_id"] == me["id"])
                roster = mine.get("roster") or []
                if not roster:
                    pytest.skip("user has no roster")
                r = await client.post(
                    f"/api/teams/{mine['id']}/lineup",
                    headers=h,
                    json={"lineup": {str(roster[0]): {"section": "taxi", "slot": "T1"}}},
                )
                assert r.status_code == 400, r.text
                detail = r.json()["detail"]
                assert "Taxi" in detail and "disabled" in detail.lower(), detail
        finally:
            await db.leagues.update_one(
                {"_id": ObjectId(LID)},
                {"$set": {"taxi_squad_size": orig_taxi if orig_taxi is not None else 0}},
            )
    finally:
        mongo.close()


@pytest.mark.asyncio
async def test_ir_cap_at_limit_succeeds():
    """A lineup with exactly `ir_slots` players on IR saves cleanly."""
    mongo = AsyncIOMotorClient(_env("MONGO_URL"))
    db = mongo[_env("DB_NAME")]
    try:
        before = await db.leagues.find_one({"_id": ObjectId(LID)})
        orig_ir = before.get("ir_slots")
        await db.leagues.update_one(
            {"_id": ObjectId(LID)},
            {"$set": {"ir_slots": 3}},
        )
        try:
            async with AsyncClient(base_url=BASE, timeout=20) as client:
                token = await _login(client)
                h = {"Authorization": f"Bearer {token}"}
                me = (await client.get("/api/auth/me", headers=h)).json()
                teams = (await client.get(f"/api/teams?league_id={LID}", headers=h)).json()
                mine = next(t for t in teams if t["owner_id"] == me["id"])
                roster = mine.get("roster") or []
                if len(roster) < 3:
                    pytest.skip("not enough players")
                lineup = {
                    str(roster[0]): {"section": "ir", "slot": "IR1"},
                    str(roster[1]): {"section": "ir", "slot": "IR2"},
                    str(roster[2]): {"section": "ir", "slot": "IR3"},
                }
                r = await client.post(
                    f"/api/teams/{mine['id']}/lineup",
                    headers=h,
                    json={"lineup": lineup},
                )
                assert r.status_code == 200, r.text
        finally:
            await db.leagues.update_one(
                {"_id": ObjectId(LID)},
                {"$set": {"ir_slots": orig_ir if orig_ir is not None else 0}},
            )
    finally:
        mongo.close()
