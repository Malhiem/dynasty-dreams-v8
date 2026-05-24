"""Iter 106: emergency-swap budget endpoint + per-day goalie lock endpoint
+ emergency_changes_scope field round-trip."""
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
EMAIL = "chriszarek@gmail.com"
PASSWORD = "Chris2026!"
LID = "69e46af167999bfb85c39628"


async def _token(client):
    r = await client.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
    return r.json()["access_token"]


async def _first_team(client, headers):
    r = await client.get(f"/api/teams?league_id={LID}", headers=headers)
    return r.json()[0]["id"]


@pytest.mark.asyncio
async def test_emergency_swap_budget_returns_disabled_when_league_off():
    async with AsyncClient(base_url=BASE, timeout=15) as client:
        token = await _token(client)
        headers = {"Authorization": f"Bearer {token}"}
        team_id = await _first_team(client, headers)
        # Ensure emergency is off
        before = (await client.get(f"/api/leagues/{LID}", headers=headers)).json()
        await client.put(f"/api/leagues/{LID}", headers=headers,
                         json={"emergency_changes_enabled": False})

        r = await client.get(f"/api/teams/{team_id}/emergency-swap-budget", headers=headers)
        assert r.status_code == 200
        d = r.json()
        assert d["enabled"] is False
        assert d["budget"] == 0
        assert d["used"] == 0
        assert d["remaining"] == 0
        # Restore
        await client.put(f"/api/leagues/{LID}", headers=headers, json={
            "emergency_changes_enabled": before.get("emergency_changes_enabled"),
        })


@pytest.mark.asyncio
async def test_emergency_swap_budget_per_season_scope():
    async with AsyncClient(base_url=BASE, timeout=15) as client:
        token = await _token(client)
        headers = {"Authorization": f"Bearer {token}"}
        team_id = await _first_team(client, headers)
        before = (await client.get(f"/api/leagues/{LID}", headers=headers)).json()
        # Configure per-season
        await client.put(f"/api/leagues/{LID}", headers=headers, json={
            "emergency_changes_enabled": True,
            "emergency_changes_regular": 5,
            "emergency_changes_playoffs": 2,
            "emergency_changes_scope": "per_season",
        })
        r = await client.get(f"/api/teams/{team_id}/emergency-swap-budget", headers=headers)
        assert r.status_code == 200
        d = r.json()
        assert d["enabled"] is True
        assert d["scope"] == "per_season"
        assert d["scope_label"] == "this season"
        # Budget reflects either regular or playoff based on current week
        assert d["budget"] in (5, 2)
        # Cleanup
        await client.put(f"/api/leagues/{LID}", headers=headers, json={
            "emergency_changes_enabled": before.get("emergency_changes_enabled"),
            "emergency_changes_regular": before.get("emergency_changes_regular"),
            "emergency_changes_playoffs": before.get("emergency_changes_playoffs"),
            "emergency_changes_scope": before.get("emergency_changes_scope"),
        })


@pytest.mark.asyncio
async def test_emergency_swap_budget_per_week_scope_uses_week_field():
    async with AsyncClient(base_url=BASE, timeout=15) as client:
        token = await _token(client)
        headers = {"Authorization": f"Bearer {token}"}
        team_id = await _first_team(client, headers)
        before = (await client.get(f"/api/leagues/{LID}", headers=headers)).json()
        await client.put(f"/api/leagues/{LID}", headers=headers, json={
            "emergency_changes_enabled": True,
            "emergency_changes_regular": 3,
            "emergency_changes_playoffs": 1,
            "emergency_changes_scope": "per_week",
        })
        r = await client.get(f"/api/teams/{team_id}/emergency-swap-budget", headers=headers)
        assert r.status_code == 200
        d = r.json()
        assert d["enabled"] is True
        assert d["scope"] == "per_week"
        assert d["scope_label"] == "this week"
        # Cleanup
        await client.put(f"/api/leagues/{LID}", headers=headers, json={
            "emergency_changes_enabled": before.get("emergency_changes_enabled"),
            "emergency_changes_regular": before.get("emergency_changes_regular"),
            "emergency_changes_playoffs": before.get("emergency_changes_playoffs"),
            "emergency_changes_scope": before.get("emergency_changes_scope"),
        })


@pytest.mark.asyncio
async def test_put_league_validates_emergency_scope_enum():
    async with AsyncClient(base_url=BASE, timeout=15) as client:
        token = await _token(client)
        headers = {"Authorization": f"Bearer {token}"}
        r = await client.put(f"/api/leagues/{LID}", headers=headers,
                             json={"emergency_changes_scope": "biennial"})
        assert r.status_code == 422


@pytest.mark.asyncio
async def test_goalie_daily_lock_writer_persists_map():
    async with AsyncClient(base_url=BASE, timeout=15) as client:
        token = await _token(client)
        headers = {"Authorization": f"Bearer {token}"}
        team_id = await _first_team(client, headers)
        r = await client.put(f"/api/teams/{team_id}/goalie-daily-lock", headers=headers, json={
            "lock_map": {
                "2026-04-08": "player_x",
                "2026-04-10": "player_y",
                "bogus_date": "ignored",
                "2026-04-09": "",  # blank should be filtered out
            },
        })
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["count"] == 2
        assert d["lock_map"] == {
            "2026-04-08": "player_x",
            "2026-04-10": "player_y",
        }
        # Reset
        await client.put(f"/api/teams/{team_id}/goalie-daily-lock", headers=headers,
                         json={"lock_map": {}})


@pytest.mark.asyncio
async def test_goalie_daily_lock_writer_rejects_invalid_body():
    async with AsyncClient(base_url=BASE, timeout=15) as client:
        token = await _token(client)
        headers = {"Authorization": f"Bearer {token}"}
        team_id = await _first_team(client, headers)
        r = await client.put(f"/api/teams/{team_id}/goalie-daily-lock", headers=headers,
                             json={"lock_map": "not_an_object"})
        assert r.status_code == 400
