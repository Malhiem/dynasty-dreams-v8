"""Iter 104: Emergency Roster Changes + Goalie Scoring league fields,
plus playoff-bracket persisted-matchup rendering (cross-referenced in
test_iter104_playoff_bracket_persisted.py).
"""
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
async def test_put_league_accepts_emergency_roster_changes_fields():
    async with AsyncClient(base_url=BASE, timeout=15) as client:
        token = await _token(client)
        headers = {"Authorization": f"Bearer {token}"}
        before = (await client.get(f"/api/leagues/{LID}", headers=headers)).json()

        r = await client.put(f"/api/leagues/{LID}", headers=headers, json={
            "emergency_changes_enabled": True,
            "emergency_changes_regular": 3,
            "emergency_changes_playoffs": 2,
            "emergency_eligibility": ["injured", "minors"],
        })
        assert r.status_code == 200, r.text
        out = r.json()
        assert out["emergency_changes_enabled"] is True
        assert out["emergency_changes_regular"] == 3
        assert out["emergency_changes_playoffs"] == 2
        assert out["emergency_eligibility"] == ["injured", "minors"]

        # Cleanup
        await client.put(f"/api/leagues/{LID}", headers=headers, json={
            "emergency_changes_enabled": before.get("emergency_changes_enabled"),
            "emergency_changes_regular": before.get("emergency_changes_regular"),
            "emergency_changes_playoffs": before.get("emergency_changes_playoffs"),
            "emergency_eligibility": before.get("emergency_eligibility"),
        })


@pytest.mark.asyncio
async def test_put_league_rejects_invalid_emergency_count():
    async with AsyncClient(base_url=BASE, timeout=15) as client:
        token = await _token(client)
        headers = {"Authorization": f"Bearer {token}"}
        # Exceeds ge=0, le=10
        r = await client.put(f"/api/leagues/{LID}", headers=headers,
                             json={"emergency_changes_regular": 99})
        assert r.status_code == 422


@pytest.mark.asyncio
async def test_put_league_accepts_goalie_scoring_fields():
    async with AsyncClient(base_url=BASE, timeout=15) as client:
        token = await _token(client)
        headers = {"Authorization": f"Bearer {token}"}
        before = (await client.get(f"/api/leagues/{LID}", headers=headers)).json()

        r = await client.put(f"/api/leagues/{LID}", headers=headers, json={
            "differentiate_goalie_scoring": True,
            "goalie_scoring_method": "best_x",
            "goalie_best_x_count": 5,
            "goalie_gp_limit_enabled": True,
            "goalie_gp_limit": 6,
            "goalie_gp_count_method": "average",
        })
        assert r.status_code == 200, r.text
        out = r.json()
        assert out["differentiate_goalie_scoring"] is True
        assert out["goalie_scoring_method"] == "best_x"
        assert out["goalie_best_x_count"] == 5
        assert out["goalie_gp_limit_enabled"] is True
        assert out["goalie_gp_limit"] == 6
        assert out["goalie_gp_count_method"] == "average"

        # Cleanup
        await client.put(f"/api/leagues/{LID}", headers=headers, json={
            "differentiate_goalie_scoring": before.get("differentiate_goalie_scoring"),
            "goalie_scoring_method": before.get("goalie_scoring_method"),
            "goalie_best_x_count": before.get("goalie_best_x_count"),
            "goalie_gp_limit_enabled": before.get("goalie_gp_limit_enabled"),
            "goalie_gp_limit": before.get("goalie_gp_limit"),
            "goalie_gp_count_method": before.get("goalie_gp_count_method"),
        })


@pytest.mark.asyncio
async def test_put_league_rejects_invalid_goalie_method_enum():
    async with AsyncClient(base_url=BASE, timeout=15) as client:
        token = await _token(client)
        headers = {"Authorization": f"Bearer {token}"}
        r = await client.put(f"/api/leagues/{LID}", headers=headers,
                             json={"goalie_scoring_method": "weighted_random"})
        assert r.status_code == 422
        r = await client.put(f"/api/leagues/{LID}", headers=headers,
                             json={"goalie_gp_count_method": "weighted"})
        assert r.status_code == 422
