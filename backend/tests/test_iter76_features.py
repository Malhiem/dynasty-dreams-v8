"""Tests for league-structure enforcement, premium trial timer, and profile edit."""
import os
import sys

import pytest
from httpx import AsyncClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _backend_url():
    env_path = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", ".env")
    with open(env_path) as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip()
    raise RuntimeError("REACT_APP_BACKEND_URL not found")


BASE = _backend_url()
EMAIL = "chriszarek@gmail.com"
PASSWORD = "Chris2026!"
LID = "69e46af167999bfb85c39628"


async def _login(client):
    r = await client.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
    return r.json()["access_token"]


# ─── Division enforcement ────────────────────────────────────────────
@pytest.mark.asyncio
async def test_divisions_save_blocks_when_team_missing_conference():
    """Saving League Structure with a team missing a conference returns 400."""
    async with AsyncClient(base_url=BASE, timeout=20) as client:
        token = await _login(client)
        r = await client.put(
            f"/api/leagues/{LID}/divisions",
            headers={"Authorization": f"Bearer {token}"},
            json={"assignments": [{
                "team_id": "69e59b30cbd3fea02a914c61",
                "division": "Atlantic",
                "conference": "",
            }]},
        )
        assert r.status_code == 400
        detail = r.json()["detail"]
        assert detail["code"] == "incomplete_league_structure"
        assert detail["missing"]
        assert any(m["team_name"] for m in detail["missing"])


# ─── Premium trial timer ─────────────────────────────────────────────
@pytest.mark.asyncio
async def test_premium_trial_starts_when_cap_enabled():
    """Enabling salary cap starts the 14-day clock and sets trial_seconds_left."""
    async with AsyncClient(base_url=BASE, timeout=20) as client:
        token = await _login(client)
        # Enable cap
        r = await client.put(
            f"/api/leagues/{LID}/admin/cap-settings",
            headers={"Authorization": f"Bearer {token}"},
            json={"salary_cap_enabled": True, "salary_cap": 82500000,
                  "salary_retention_slots": 3, "minors_enabled": False},
        )
        assert r.status_code == 200
        status = r.json()["premium_status"]
        assert status["enabled_features"] == ["salary_cap"]
        assert status["paid"] is False
        assert status["trial_seconds_left"] is not None
        # Should be just under 14 days (some seconds will have elapsed)
        assert 0 < status["trial_seconds_left"] <= 14 * 86400

        # Confirm /premium-status reflects the same
        r = await client.get(
            f"/api/leagues/{LID}/premium-status",
            headers={"Authorization": f"Bearer {token}"},
        )
        status2 = r.json()
        assert status2["enabled_features"] == ["salary_cap"]
        assert status2["trial_seconds_left"] > 0

        # Cleanup — disable cap
        await client.put(
            f"/api/leagues/{LID}/admin/cap-settings",
            headers={"Authorization": f"Bearer {token}"},
            json={"salary_cap_enabled": False, "minors_enabled": False},
        )


@pytest.mark.asyncio
async def test_premium_trial_clears_when_all_features_off():
    async with AsyncClient(base_url=BASE, timeout=20) as client:
        token = await _login(client)
        # Toggle on then off
        await client.put(
            f"/api/leagues/{LID}/admin/cap-settings",
            headers={"Authorization": f"Bearer {token}"},
            json={"salary_cap_enabled": True, "salary_cap": 80000000},
        )
        r = await client.put(
            f"/api/leagues/{LID}/admin/cap-settings",
            headers={"Authorization": f"Bearer {token}"},
            json={"salary_cap_enabled": False, "minors_enabled": False},
        )
        status = r.json()["premium_status"]
        assert status["enabled_features"] == []
        assert status["trial_seconds_left"] is None


# ─── Profile edit ────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_profile_update_extended_fields():
    async with AsyncClient(base_url=BASE, timeout=20) as client:
        token = await _login(client)
        r = await client.put(
            "/api/users/me/profile",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "favourite_sport": "Hockey",
                "favourite_team": "Toronto Maple Leafs",
                "city": "Toronto",
                "province_state": "ON",
                "country": "Canada",
            },
        )
        assert r.status_code == 200
        u = r.json()["user"]
        assert u["favourite_sport"] == "Hockey"
        assert u["city"] == "Toronto"
        assert u["country"] == "Canada"

        # /auth/me reflects new fields
        r = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        me = r.json()
        assert me.get("favourite_sport") == "Hockey"
        assert me.get("city") == "Toronto"


@pytest.mark.asyncio
async def test_profile_username_uniqueness():
    async with AsyncClient(base_url=BASE, timeout=20) as client:
        token = await _login(client)
        # admin is taken; try to grab it
        r = await client.put(
            "/api/users/me/profile",
            headers={"Authorization": f"Bearer {token}"},
            json={"username": "admin"},
        )
        assert r.status_code == 409


@pytest.mark.asyncio
async def test_profile_invalid_username_rejected():
    async with AsyncClient(base_url=BASE, timeout=20) as client:
        token = await _login(client)
        r = await client.put(
            "/api/users/me/profile",
            headers={"Authorization": f"Bearer {token}"},
            json={"username": "no spaces allowed!"},
        )
        assert r.status_code == 422
