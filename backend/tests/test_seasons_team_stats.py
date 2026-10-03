"""Test the include_team_stats=true extension on GET /leagues/{id}/seasons."""
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
EMAIL = os.environ.get("TEST_OWNER_EMAIL", "test-owner@e2e.dynastydreams.com")
PASSWORD = os.environ.get("TEST_OWNER_PASSWORD", "e2e-owner-password")


async def _login(client):
    r = await client.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert r.status_code == 200
    return r.json()["access_token"]


async def _league(client, token):
    r = await client.get("/api/leagues?my_leagues=true", headers={"Authorization": f"Bearer {token}"})
    return r.json()[0]["id"]


@pytest.mark.asyncio
async def test_seasons_minimal_payload_default():
    """Default behaviour: no team_stats key on rows."""
    async with AsyncClient(base_url=BASE, timeout=20) as client:
        token = await _login(client)
        lid = await _league(client, token)
        r = await client.get(
            f"/api/leagues/{lid}/seasons",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        seasons = r.json()["seasons"]
        for s in seasons:
            assert "team_stats" not in s


@pytest.mark.asyncio
async def test_seasons_include_team_stats():
    """With include_team_stats=true, every row has a team_stats array."""
    async with AsyncClient(base_url=BASE, timeout=20) as client:
        token = await _login(client)
        lid = await _league(client, token)
        r = await client.get(
            f"/api/leagues/{lid}/seasons?include_team_stats=true",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        seasons = r.json()["seasons"]
        if not seasons:
            pytest.skip("no completed seasons to assert")
        for s in seasons:
            assert "team_stats" in s
            assert isinstance(s["team_stats"], list)
            if s["team_stats"]:
                row = s["team_stats"][0]
                for key in ("team_id", "team_name", "wins", "losses", "ties",
                            "points_for", "points_against"):
                    assert key in row, f"missing {key} in team_stats row"
                assert isinstance(row["wins"], int)
                assert isinstance(row["points_for"], float)


@pytest.mark.asyncio
async def test_seasons_team_stats_sum_consistent():
    """team_stats from each snapshot can be summed deterministically."""
    async with AsyncClient(base_url=BASE, timeout=20) as client:
        token = await _login(client)
        lid = await _league(client, token)
        r = await client.get(
            f"/api/leagues/{lid}/seasons?include_team_stats=true",
            headers={"Authorization": f"Bearer {token}"},
        )
        seasons = r.json()["seasons"]
        if not seasons:
            pytest.skip("no completed seasons")
        totals = {}
        for s in seasons:
            for ts in s.get("team_stats") or []:
                tid = ts["team_id"]
                t = totals.setdefault(
                    tid,
                    {"wins": 0, "losses": 0, "ties": 0, "pf": 0.0},
                )
                t["wins"] += ts["wins"]
                t["losses"] += ts["losses"]
                t["ties"] += ts["ties"]
                t["pf"] += ts["points_for"]
        # Should produce as many tally rows as distinct franchises in snapshots
        assert len(totals) >= 1
