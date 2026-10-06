"""Iter 85 — Lineup-warning regression.

The frontend `PlayerRoster.tsx` renders a yellow chip next to a player's name
whenever the backend's `POST /teams/{id}/lineup` response includes a warning
for that player. The hottest production trigger is `min_games_played` — a
starter with too few NHL games for the league's setting.

These tests pin the contract end-to-end so a regression on the warning
payload (key name, player_id presence, message string) breaks loudly.
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
async def test_min_games_played_emits_warning_per_starter():
    """When `min_games_played` is set and a starter has fewer GP than the
    threshold, the lineup save succeeds (200) but the response embeds a
    `min_games_played` warning entry naming that player — which is what the
    PlayerRoster.tsx yellow chip keys off of.
    """
    mongo = AsyncIOMotorClient(_env("MONGO_URL"))
    db = mongo[_env("DB_NAME")]
    try:
        # ── Setup: force min_games_played to a very high number so every
        # starter on the test user's roster trips it.
        before = await db.leagues.find_one({"_id": ObjectId(LID)})
        orig_min = before.get("min_games_played")
        orig_allow_illegal = before.get("allow_illegal_rosters")
        await db.leagues.update_one(
            {"_id": ObjectId(LID)},
            {"$set": {"min_games_played": 9999, "allow_illegal_rosters": True}},
        )
        try:
            async with AsyncClient(base_url=BASE, timeout=20) as client:
                token = await _login(client)
                h = {"Authorization": f"Bearer {token}"}
                me = (await client.get("/api/auth/me", headers=h)).json()
                teams = (await client.get(f"/api/teams?league_id={LID}", headers=h)).json()
                mine = next(t for t in teams if t["owner_id"] == me["id"])
                roster = mine.get("roster") or []
                if len(roster) < 2:
                    pytest.skip("user has insufficient roster")

                # Put first two roster slots into the starting forward
                # section so they trip the min_games_played check.
                lineup = {
                    str(roster[0]): {"section": "forward", "slot": "C"},
                    str(roster[1]): {"section": "forward", "slot": "LW"},
                }
                r = await client.post(
                    f"/api/teams/{mine['id']}/lineup",
                    headers=h,
                    json={"lineup": lineup},
                )
                assert r.status_code == 200, r.text
                body = r.json()
                assert body["saved"] is True
                warnings = body.get("warnings") or []
                # Every starter is below 9999 GP, so we expect at least one
                # per-player warning.
                gp_warnings = [w for w in warnings if w.get("code") == "min_games_played"]
                assert len(gp_warnings) >= 1, warnings
                # Contract: each warning has a player_id + message — these
                # are exactly what PlayerRoster.tsx groups by to render the
                # yellow chip + tooltip.
                for w in gp_warnings:
                    assert w.get("player_id"), w
                    assert w.get("message") and "GP" in w["message"], w
        finally:
            restore = {}
            if orig_min is not None:
                restore["min_games_played"] = orig_min
            else:
                restore["min_games_played"] = 0
            restore["allow_illegal_rosters"] = (
                orig_allow_illegal if orig_allow_illegal is not None else False
            )
            await db.leagues.update_one({"_id": ObjectId(LID)}, {"$set": restore})
    finally:
        mongo.close()


@pytest.mark.asyncio
async def test_min_games_played_zero_emits_no_warning():
    """When `min_games_played` is 0 (disabled), no per-player warnings should
    appear — the chip should NEVER render in that league."""
    mongo = AsyncIOMotorClient(_env("MONGO_URL"))
    db = mongo[_env("DB_NAME")]
    try:
        before = await db.leagues.find_one({"_id": ObjectId(LID)})
        orig_min = before.get("min_games_played")
        await db.leagues.update_one(
            {"_id": ObjectId(LID)},
            {"$set": {"min_games_played": 0}},
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
                    json={"lineup": {str(roster[0]): {"section": "forward", "slot": "C"}}},
                )
                assert r.status_code == 200, r.text
                warnings = r.json().get("warnings") or []
                gp_warnings = [w for w in warnings if w.get("code") == "min_games_played"]
                assert gp_warnings == [], gp_warnings
        finally:
            await db.leagues.update_one(
                {"_id": ObjectId(LID)},
                {"$set": {"min_games_played": orig_min if orig_min is not None else 0}},
            )
    finally:
        mongo.close()
