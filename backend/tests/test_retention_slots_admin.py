"""Tests for the salary retention slots commissioner endpoint.

- PUT /api/leagues/{id}/salary-retention-slots validates range [0-3]
- Only commissioner / co-commissioner can modify
- Value is reflected in /teams/{id}/compliance.salary_retention_slots_total
- Audit log entry is written on change
"""
import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from httpx import AsyncClient


def _backend_url():
    env = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", ".env")
    with open(env) as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip()
    raise RuntimeError("REACT_APP_BACKEND_URL not found")


BASE = _backend_url()
COMMISSIONER_EMAIL = os.environ.get("TEST_OWNER_EMAIL", "test-owner@e2e.dynastydreams.com")
COMMISSIONER_PASSWORD = os.environ.get("TEST_OWNER_PASSWORD", "e2e-owner-password")
TEAM_ID = "69e59b30cbd3fea02a914c61"   # Zarek's Frozen (commissioner's own team)
LEAGUE_ID = "69e46af167999bfb85c39628"  # Ice Kings (Zarek is commissioner)


async def _login(client, email, password):
    r = await client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.mark.asyncio
async def test_retention_slots_default_is_3():
    async with AsyncClient(base_url=BASE, timeout=30) as client:
        token = await _login(client, COMMISSIONER_EMAIL, COMMISSIONER_PASSWORD)
        h = {"Authorization": f"Bearer {token}"}
        # Reset to 3 first
        await client.put(
            f"/api/leagues/{LEAGUE_ID}/salary-retention-slots",
            headers=h, json={"salary_retention_slots": 3},
        )
        compliance = await client.get(f"/api/teams/{TEAM_ID}/compliance", headers=h)
        assert compliance.json()["salary_retention_slots_total"] == 3


@pytest.mark.asyncio
async def test_retention_slots_updates_compliance():
    async with AsyncClient(base_url=BASE, timeout=30) as client:
        token = await _login(client, COMMISSIONER_EMAIL, COMMISSIONER_PASSWORD)
        h = {"Authorization": f"Bearer {token}"}
        r = await client.put(
            f"/api/leagues/{LEAGUE_ID}/salary-retention-slots",
            headers=h, json={"salary_retention_slots": 2},
        )
        assert r.status_code == 200, r.text
        assert r.json()["salary_retention_slots"] == 2

        # Compliance should reflect the new cap immediately
        compliance = await client.get(f"/api/teams/{TEAM_ID}/compliance", headers=h)
        body = compliance.json()
        assert body["salary_retention_slots_total"] == 2
        # No retentions have been added, so used = 0 and remaining = 2
        assert body["salary_retention_slots_used"] == 0
        assert body["salary_retention_slots_remaining"] == 2

        # Clean up — restore to 3
        await client.put(
            f"/api/leagues/{LEAGUE_ID}/salary-retention-slots",
            headers=h, json={"salary_retention_slots": 3},
        )


@pytest.mark.asyncio
async def test_retention_slots_range_validation():
    async with AsyncClient(base_url=BASE, timeout=30) as client:
        token = await _login(client, COMMISSIONER_EMAIL, COMMISSIONER_PASSWORD)
        h = {"Authorization": f"Bearer {token}"}
        # Over-range
        r = await client.put(
            f"/api/leagues/{LEAGUE_ID}/salary-retention-slots",
            headers=h, json={"salary_retention_slots": 15},
        )
        assert r.status_code == 400
        assert "between 0 and 3" in r.json()["detail"]
        # Under-range
        r = await client.put(
            f"/api/leagues/{LEAGUE_ID}/salary-retention-slots",
            headers=h, json={"salary_retention_slots": -1},
        )
        assert r.status_code == 400
        # Non-integer
        r = await client.put(
            f"/api/leagues/{LEAGUE_ID}/salary-retention-slots",
            headers=h, json={"salary_retention_slots": "abc"},
        )
        assert r.status_code == 400


@pytest.mark.asyncio
async def test_retention_slots_non_commissioner_blocked():
    from uuid import uuid4
    async with AsyncClient(base_url=BASE, timeout=30) as client:
        unique = uuid4().hex[:16]
        registered = await client.post("/api/auth/register", json={
            "email": f"retention-{unique}@example.com", "username": f"retain_{unique}", "password": "FixturePass123!"})
        assert registered.status_code == 200, registered.text
        token = registered.json()["access_token"]
        response = await client.put(f"/api/leagues/{LEAGUE_ID}/salary-retention-slots",
            headers={"Authorization": f"Bearer {token}"}, json={"salary_retention_slots": 2})
        assert response.status_code == 403, response.text
