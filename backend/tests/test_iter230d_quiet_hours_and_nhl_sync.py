"""Iter 230d — Quiet Hours + per-league mute + NHL sync dispatcher tests."""
import os
import sys
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from motor.motor_asyncio import AsyncIOMotorClient

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
    return client[os.environ.get("DB_NAME", os.environ["DB_NAME"])]


async def _login(client, email, password):
    r = await client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.mark.asyncio
async def test_quiet_hours_set_and_validation():
    async with AsyncClient(base_url=BASE, timeout=20) as client:
        token = await _login(client, os.environ.get("TEST_OWNER_EMAIL", "test-owner@e2e.dynastydreams.com"), os.environ.get("TEST_OWNER_PASSWORD", "e2e-owner-password"))

        # 1. Enable + set window.
        r = await client.put(
            "/api/notifications/preferences/quiet-hours",
            headers={"Authorization": f"Bearer {token}"},
            json={"enabled": True, "start": "22:00", "end": "07:00", "timezone_offset_minutes": -300},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["quiet_hours"]["enabled"] is True
        assert body["quiet_hours"]["start"] == "22:00"
        assert body["quiet_hours"]["end"] == "07:00"
        assert body["quiet_hours"]["timezone_offset_minutes"] == -300

        # 2. GET reflects the change.
        r = await client.get(
            "/api/notifications/preferences",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        assert r.json()["quiet_hours"]["enabled"] is True

        # 3. Invalid time is rejected.
        r = await client.put(
            "/api/notifications/preferences/quiet-hours",
            headers={"Authorization": f"Bearer {token}"},
            json={"enabled": True, "start": "99:99", "end": "07:00"},
        )
        assert r.status_code == 422

        # 4. Disable.
        r = await client.put(
            "/api/notifications/preferences/quiet-hours",
            headers={"Authorization": f"Bearer {token}"},
            json={"enabled": False},
        )
        assert r.status_code == 200
        assert r.json()["quiet_hours"]["enabled"] is False


@pytest.mark.asyncio
async def test_per_league_mute_toggle():
    async with AsyncClient(base_url=BASE, timeout=20) as client:
        token = await _login(client, os.environ.get("TEST_OWNER_EMAIL", "test-owner@e2e.dynastydreams.com"), os.environ.get("TEST_OWNER_PASSWORD", "e2e-owner-password"))
        # Find a league chris is in.
        r = await client.get("/api/leagues?my_leagues=true", headers={"Authorization": f"Bearer {token}"})
        leagues = r.json()
        assert leagues
        target_id = leagues[0]["id"]

        # Mute
        r = await client.put(
            "/api/notifications/preferences/league-mute",
            headers={"Authorization": f"Bearer {token}"},
            json={"league_id": target_id, "muted": True},
        )
        assert r.status_code == 200, r.text
        assert target_id in r.json()["muted_league_ids"]

        # GET reflects
        r = await client.get(
            "/api/notifications/preferences",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert target_id in r.json()["muted_league_ids"]

        # Unmute
        r = await client.put(
            "/api/notifications/preferences/league-mute",
            headers={"Authorization": f"Bearer {token}"},
            json={"league_id": target_id, "muted": False},
        )
        assert r.status_code == 200
        assert target_id not in r.json()["muted_league_ids"]


@pytest.mark.asyncio
async def test_quiet_hours_blocks_in_app_via_helper():
    """Direct call to channel_enabled with quiet window active blocks in_app."""
    from routes.notification_preferences import channel_enabled, _is_in_quiet_window
    from routes import notification_preferences as np_mod

    db = _db_sync()
    # Tests run out-of-process from server.py — wire the helper's db dep
    # so the standalone helper call has something to query against.
    # Always reassign (don't setdefault) so each test starts with a fresh
    # Motor client bound to the active event loop.
    np_mod._deps["db"] = db

    user = await db.users.find_one({"email": os.environ.get("TEST_OWNER_EMAIL", "test-owner@e2e.dynastydreams.com")})
    assert user
    user_id = str(user["_id"])

    # Set quiet hours to cover the current local clock + force the
    # event under test to be non-critical so it doesn't bypass.
    now = datetime.now(timezone.utc)
    # 00:00 → 23:59 always covers "now" — use that to force the gate.
    await db.notification_preferences.update_one(
        {"user_id": user_id},
        {"$set": {
            "user_id": user_id,
            "quiet_hours": {
                "enabled": True,
                "start": "00:00",
                "end": "23:59",
                "timezone_offset_minutes": 0,
            },
            # Iter 230e — trade_proposed defaults critical=True now.
            # Force it OFF here so the quiet-hours gate is observed.
            "preferences.trade_proposed": {
                "in_app": True, "push": True, "email": True, "critical": False,
            },
        }},
        upsert=True,
    )
    try:
        # Sanity: _is_in_quiet_window returns True.
        assert _is_in_quiet_window({
            "enabled": True, "start": "00:00", "end": "23:59",
            "timezone_offset_minutes": 0,
        })
        # in_app is now blocked.
        assert (await channel_enabled(user_id, "trade_proposed", "in_app")) is False
        # push is blocked too.
        assert (await channel_enabled(user_id, "trade_proposed", "push")) is False
        # Email still gets through (digest channel).
        assert (await channel_enabled(user_id, "trade_proposed", "email")) is True
    finally:
        await db.notification_preferences.update_one(
            {"user_id": user_id},
            {"$set": {"quiet_hours": {"enabled": False, "start": "22:00", "end": "07:00", "timezone_offset_minutes": 0}}},
        )


@pytest.mark.asyncio
async def test_muted_league_blocks_all_channels():
    from routes.notification_preferences import channel_enabled
    from routes import notification_preferences as np_mod

    db = _db_sync()
    np_mod._deps["db"] = db
    user = await db.users.find_one({"email": os.environ.get("TEST_OWNER_EMAIL", "test-owner@e2e.dynastydreams.com")})
    user_id = str(user["_id"])
    league = await db.leagues.find_one({})
    league_id = str(league["_id"])

    await db.notification_preferences.update_one(
        {"user_id": user_id},
        {"$addToSet": {"muted_league_ids": league_id}},
        upsert=True,
    )
    try:
        for ch in ("in_app", "push", "email"):
            assert (await channel_enabled(user_id, "trade_proposed", ch, league_id)) is False
        # Non-muted league still passes.
        assert (await channel_enabled(user_id, "trade_proposed", "in_app", "different_league_id")) is True
    finally:
        await db.notification_preferences.update_one(
            {"user_id": user_id},
            {"$pull": {"muted_league_ids": league_id}},
        )


@pytest.mark.asyncio
async def test_nhl_sync_dispatcher_classifies_injury_transitions():
    """`apply_player_diff_and_notify` fires the right notification when
    a player's `injury_status` flips healthy → IR and back."""
    from services.nhl_sync_dispatcher import apply_player_diff_and_notify

    db = _db_sync()
    team = await db.teams.find_one({"roster": {"$exists": True, "$ne": []}})
    assert team
    player_id = team["roster"][0]
    original = await db.players.find_one({"_id": __import__("bson").ObjectId(player_id)})
    original_status = (original or {}).get("injury_status")

    calls: list = []

    async def recorder(user_id, event_id, title, body, league_id=None, link=None, reason=None):
        calls.append({"user_id": user_id, "event_id": event_id, "title": title})

    try:
        # Make sure baseline is healthy.
        await db.players.update_one(
            {"_id": __import__("bson").ObjectId(player_id)},
            {"$set": {"injury_status": "Healthy"}},
        )

        # 1. Healthy → IR fires "player_injured".
        summary = await apply_player_diff_and_notify(
            db, player_id=player_id,
            new_fields={"injury_status": "IR"},
            create_notification=recorder,
        )
        assert summary["updated"] is True
        assert "injured" in summary["transitions"]
        assert any(c["event_id"] == "player_injured" for c in calls)

        # 2. IR → Healthy fires "player_recovered".
        calls.clear()
        summary = await apply_player_diff_and_notify(
            db, player_id=player_id,
            new_fields={"injury_status": "Healthy"},
            create_notification=recorder,
        )
        assert "recovered" in summary["transitions"]
        assert any(c["event_id"] == "player_recovered" for c in calls)

        # 3. No-op (same value) → no notifications.
        calls.clear()
        summary = await apply_player_diff_and_notify(
            db, player_id=player_id,
            new_fields={"injury_status": "Healthy"},
            create_notification=recorder,
        )
        assert summary["updated"] is False
        assert calls == []
    finally:
        # Restore original injury_status.
        await db.players.update_one(
            {"_id": __import__("bson").ObjectId(player_id)},
            {"$set": {"injury_status": original_status}} if original_status is not None
            else {"$unset": {"injury_status": ""}},
        )


@pytest.mark.asyncio
async def test_nhl_sync_dispatcher_classifies_league_status_transitions():
    """league_status NHL → AHL fires sent_down; AHL → NHL fires called_up."""
    from services.nhl_sync_dispatcher import apply_player_diff_and_notify
    from bson import ObjectId

    db = _db_sync()
    team = await db.teams.find_one({"roster": {"$exists": True, "$ne": []}})
    assert team
    player_id = team["roster"][0]
    original = await db.players.find_one({"_id": ObjectId(player_id)})
    original_league_status = (original or {}).get("league_status")

    calls: list = []

    async def recorder(user_id, event_id, title, body, league_id=None, link=None, reason=None):
        calls.append(event_id)

    try:
        await db.players.update_one({"_id": ObjectId(player_id)}, {"$set": {"league_status": "NHL"}})

        # NHL → AHL.
        summary = await apply_player_diff_and_notify(
            db, player_id=player_id,
            new_fields={"league_status": "AHL"},
            create_notification=recorder,
        )
        assert "sent_down" in summary["transitions"]
        assert "player_sent_down" in calls

        # AHL → NHL.
        calls.clear()
        summary = await apply_player_diff_and_notify(
            db, player_id=player_id,
            new_fields={"league_status": "NHL"},
            create_notification=recorder,
        )
        assert "called_up" in summary["transitions"]
        assert "player_called_up" in calls
    finally:
        await db.players.update_one(
            {"_id": ObjectId(player_id)},
            {"$set": {"league_status": original_league_status}} if original_league_status is not None
            else {"$unset": {"league_status": ""}},
        )


@pytest.mark.asyncio
async def test_admin_diff_sync_endpoint():
    """Admin-only POST /api/admin/players/{id}/diff-sync — wraps the
    dispatcher and returns its summary."""
    async with AsyncClient(base_url=BASE, timeout=20) as client:
        admin_token = await _login(client, os.environ.get("ADMIN_EMAIL", "admin@e2e.dynastydreams.com"), os.environ.get("ADMIN_PASSWORD", "e2e-admin-password"))
        db = _db_sync()
        team = await db.teams.find_one({"roster": {"$exists": True, "$ne": []}})
        player_id = team["roster"][0]
        from bson import ObjectId
        original = await db.players.find_one({"_id": ObjectId(player_id)})
        orig_status = (original or {}).get("injury_status")

        try:
            await db.players.update_one({"_id": ObjectId(player_id)}, {"$set": {"injury_status": "Healthy"}})
            r = await client.post(
                f"/api/admin/players/{player_id}/diff-sync",
                headers={"Authorization": f"Bearer {admin_token}"},
                json={"fields": {"injury_status": "IR"}},
            )
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["updated"] is True
            assert "injured" in body["transitions"]
            assert body["notifications_sent"] >= 1

            # Non-admin → 403.
            chris_token = await _login(client, os.environ.get("TEST_OWNER_EMAIL", "test-owner@e2e.dynastydreams.com"), os.environ.get("TEST_OWNER_PASSWORD", "e2e-owner-password"))
            r = await client.post(
                f"/api/admin/players/{player_id}/diff-sync",
                headers={"Authorization": f"Bearer {chris_token}"},
                json={"fields": {"injury_status": "Healthy"}},
            )
            assert r.status_code == 403
        finally:
            await db.players.update_one(
                {"_id": ObjectId(player_id)},
                {"$set": {"injury_status": orig_status}} if orig_status is not None
                else {"$unset": {"injury_status": ""}},
            )
