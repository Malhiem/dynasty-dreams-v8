"""Iter 103: GET /leagues/{id}/lock-status endpoint."""
import os
import pytest
from httpx import AsyncClient


def _backend_url():
    env_path = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", ".env")
    with open(env_path) as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip()
    raise RuntimeError("REACT_APP_BACKEND_URL not found")


BASE = _backend_url()
EMAIL = os.environ.get("TEST_OWNER_EMAIL", "test-owner@e2e.dynastydreams.com")
PASSWORD = os.environ.get("TEST_OWNER_PASSWORD", "e2e-owner-password")
LID = "69e46af167999bfb85c39628"


async def _token(client):
    r = await client.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
    return r.json()["access_token"]


@pytest.mark.asyncio
async def test_lock_status_endpoint_returns_evaluator_shape():
    async with AsyncClient(base_url=BASE, timeout=15) as client:
        token = await _token(client)
        headers = {"Authorization": f"Bearer {token}"}
        r = await client.get(f"/api/leagues/{LID}/lock-status", headers=headers)
        assert r.status_code == 200, r.text
        d = r.json()
        # The exact lock state depends on the wall clock; just assert shape.
        assert d["league_id"] == LID
        assert "locked" in d
        assert "scope" in d
        assert d["scope"] in ("regular", "playoff")
        assert "cadence" in d


@pytest.mark.asyncio
async def test_lock_status_endpoint_honors_week_query():
    async with AsyncClient(base_url=BASE, timeout=15) as client:
        token = await _token(client)
        headers = {"Authorization": f"Bearer {token}"}
        # Configure playoff lock override to be picked up by ?week=20 (in playoff range)
        league = (await client.get(f"/api/leagues/{LID}", headers=headers)).json()
        await client.put(f"/api/leagues/{LID}", headers=headers, json={
            "roster_lock_type": "daily",
            "lineup_lock_minutes_before": 0,
            "playoff_roster_lock_override": True,
            "playoff_roster_lock_type": "weekly",
            "playoff_roster_lock_day": "monday",
            "playoff_lineup_lock_minutes_before": 0,
        })
        r_reg = await client.get(f"/api/leagues/{LID}/lock-status?week=10", headers=headers)
        r_po = await client.get(f"/api/leagues/{LID}/lock-status?week=20", headers=headers)
        assert r_reg.status_code == 200 and r_po.status_code == 200
        assert r_reg.json()["scope"] == "regular"
        assert r_po.json()["scope"] == "playoff"

        # Restore
        await client.put(f"/api/leagues/{LID}", headers=headers, json={
            "roster_lock_type": league.get("roster_lock_type"),
            "lineup_lock_minutes_before": league.get("lineup_lock_minutes_before"),
            "playoff_roster_lock_override": league.get("playoff_roster_lock_override"),
            "playoff_roster_lock_type": league.get("playoff_roster_lock_type"),
            "playoff_roster_lock_day": league.get("playoff_roster_lock_day"),
            "playoff_lineup_lock_minutes_before": league.get("playoff_lineup_lock_minutes_before"),
        })
