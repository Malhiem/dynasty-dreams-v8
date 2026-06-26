"""Iter 230e — Critical override + NHL roster sync worker tests."""
import os
import sys
from datetime import datetime, timezone
from unittest.mock import patch, AsyncMock

import pytest
from httpx import AsyncClient
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _backend_url():
    env_path = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", ".env")
    with open(env_path) as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip()
    raise RuntimeError("REACT_APP_BACKEND_URL not found")


BASE = _backend_url()


def _db_sync():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    return client[os.environ.get("DB_NAME", "test_database")]


async def _login(client, email, password):
    r = await client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


# ── Critical override ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_critical_default_set_includes_top_events():
    """The default preferences seed marks the highest-stakes events as
    critical=True so users get them through Quiet Hours out of the box."""
    async with AsyncClient(base_url=BASE, timeout=20) as client:
        token = await _login(client, "chriszarek@gmail.com", "Chris2026!")
        # Reset to factory defaults.
        await client.post("/api/notifications/preferences/reset", headers={"Authorization": f"Bearer {token}"})
        r = await client.get("/api/notifications/preferences", headers={"Authorization": f"Bearer {token}"})
        body = r.json()
        # Trade proposed should be critical by default.
        assert body["preferences"]["trade_proposed"]["critical"] is True
        # Draft your turn too.
        assert body["preferences"]["draft_your_turn"]["critical"] is True
        # Low-stakes events default critical=False.
        assert body["preferences"]["league_chat_message"]["critical"] is False
        assert body["preferences"]["trade_block_updated"]["critical"] is False


@pytest.mark.asyncio
async def test_critical_toggle_round_trips():
    async with AsyncClient(base_url=BASE, timeout=20) as client:
        token = await _login(client, "chriszarek@gmail.com", "Chris2026!")
        # Toggle critical OFF for trade_proposed.
        r = await client.put(
            "/api/notifications/preferences",
            headers={"Authorization": f"Bearer {token}"},
            json={"event_id": "trade_proposed", "critical": False},
        )
        assert r.status_code == 200
        assert r.json()["preferences"]["critical"] is False

        r = await client.get("/api/notifications/preferences", headers={"Authorization": f"Bearer {token}"})
        assert r.json()["preferences"]["trade_proposed"]["critical"] is False

        # Restore.
        await client.post("/api/notifications/preferences/reset", headers={"Authorization": f"Bearer {token}"})


@pytest.mark.asyncio
async def test_critical_overrides_quiet_hours():
    """When critical=True, channel_enabled returns True even inside the
    user's quiet window; when critical=False it still returns False."""
    from routes.notification_preferences import channel_enabled
    from routes import notification_preferences as np_mod

    db = _db_sync()
    np_mod._deps["db"] = db

    user = await db.users.find_one({"email": "chriszarek@gmail.com"})
    user_id = str(user["_id"])

    # Set always-on quiet window AND mark trade_proposed critical=True,
    # trade_block_updated critical=False.
    await db.notification_preferences.update_one(
        {"user_id": user_id},
        {"$set": {
            "user_id": user_id,
            "quiet_hours": {"enabled": True, "start": "00:00", "end": "23:59", "timezone_offset_minutes": 0},
            "preferences.trade_proposed": {"in_app": True, "push": True, "email": True, "critical": True},
            "preferences.trade_block_updated": {"in_app": True, "push": True, "email": True, "critical": False},
        }},
        upsert=True,
    )

    try:
        # Critical event bypasses quiet hours.
        assert (await channel_enabled(user_id, "trade_proposed", "in_app")) is True
        assert (await channel_enabled(user_id, "trade_proposed", "push")) is True
        # Non-critical event still blocked by quiet hours.
        assert (await channel_enabled(user_id, "trade_block_updated", "in_app")) is False
        assert (await channel_enabled(user_id, "trade_block_updated", "push")) is False
        # Email always passes regardless of critical (acts as digest).
        assert (await channel_enabled(user_id, "trade_block_updated", "email")) is True
    finally:
        # Restore.
        await db.notification_preferences.update_one(
            {"user_id": user_id},
            {"$set": {
                "quiet_hours": {"enabled": False, "start": "22:00", "end": "07:00", "timezone_offset_minutes": 0},
            }},
        )


# ── NHL roster sync worker ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_nhl_roster_sync_diff_routes_through_dispatcher():
    """When a player's `current_team_abbrev` flips between NHL and AHL,
    the worker calls apply_player_diff_and_notify which fires the right
    transition notifications."""
    from services import nhl_roster_sync_worker as worker_mod

    db = _db_sync()
    # Seed a fixture player that exists today.
    team = await db.teams.find_one({"roster": {"$exists": True, "$ne": []}})
    player_id = team["roster"][0]
    player = await db.players.find_one({"_id": ObjectId(player_id)})
    original_nhl_id = player.get("nhl_id")
    original_league = player.get("league_status")
    original_team_abbrev = player.get("current_team_abbrev")

    try:
        # Force a known nhl_id + starting league state.
        await db.players.update_one(
            {"_id": ObjectId(player_id)},
            {"$set": {
                "nhl_id": 9999001,
                "current_team_abbrev": "AHL",
                "league_status": "AHL",
            }},
        )

        # Mock the NHL HTTP layer to return our fake roster.
        async def fake_team_codes(http):
            return ["TOR"]

        async def fake_team_roster(http, team_code):
            return [{
                "nhl_id": 9999001,
                "team_code": "TOR",
                "raw": {},
            }]

        calls: list = []

        async def recorder(user_id, event_id, title, body, league_id=None, link=None, reason=None):
            calls.append(event_id)

        with patch.object(worker_mod, "_fetch_team_codes", fake_team_codes), \
             patch.object(worker_mod, "_fetch_team_roster", fake_team_roster):
            counts = await worker_mod.sync_once(db, create_notification=recorder)

        # NHL roster sees the player → called_up transition fires.
        assert counts["nhl_players_seen"] == 1
        assert counts["team_changes"] >= 1
        assert "player_called_up" in calls

        # Now flip the mock so the player vanishes from NHL rosters; the
        # next pass should send them down.
        async def fake_team_roster_empty(http, team_code):
            return []

        calls.clear()
        with patch.object(worker_mod, "_fetch_team_codes", fake_team_codes), \
             patch.object(worker_mod, "_fetch_team_roster", fake_team_roster_empty):
            counts2 = await worker_mod.sync_once(db, create_notification=recorder)

        assert "player_sent_down" in calls
        assert counts2["team_changes"] >= 1
    finally:
        # Restore original player state.
        restore = {}
        if original_nhl_id is not None:
            restore["nhl_id"] = original_nhl_id
        if original_league is not None:
            restore["league_status"] = original_league
        if original_team_abbrev is not None:
            restore["current_team_abbrev"] = original_team_abbrev
        if restore:
            await db.players.update_one(
                {"_id": ObjectId(player_id)},
                {"$set": restore},
            )


@pytest.mark.asyncio
async def test_nhl_roster_sync_safe_on_empty_response():
    """If the NHL API returns nothing (outage), the worker MUST NOT mark
    every player as sent_down."""
    from services import nhl_roster_sync_worker as worker_mod

    db = _db_sync()

    async def fake_team_codes(http):
        return []

    calls: list = []

    async def recorder(*a, **kw):
        calls.append(a[1] if len(a) > 1 else None)

    with patch.object(worker_mod, "_fetch_team_codes", fake_team_codes):
        counts = await worker_mod.sync_once(db, create_notification=recorder)

    assert counts["nhl_players_seen"] == 0
    assert counts["team_changes"] == 0
    assert calls == []
