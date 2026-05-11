"""Tests for iter 79 additions: extended league fields, validate-setup, and
better generate-schedule error messages.
"""
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


@pytest.mark.asyncio
async def test_league_update_accepts_new_iter79_fields():
    """All the new wizard fields round-trip via PUT → GET."""
    async with AsyncClient(base_url=BASE, timeout=20) as client:
        token = await _login(client)
        payload = {
            "salary_retention_enabled": True,
            "salary_retention_max_pct": 50,
            "salary_retention_slots": 3,
            "season_start_date": "2026-10-01",
            "season_end_date": "2027-04-15",
            "matchup_length_days": 7,
            "opponents_per_matchup_period": 1,
            "playoff_end_week": 22,
            "consolation_enabled": True,
            "consolation_start_week": 19,
            "consolation_end_week": 21,
            "consolation_uses_playoff_schedule": True,
        }
        r = await client.put(
            f"/api/leagues/{LID}",
            headers={"Authorization": f"Bearer {token}"},
            json=payload,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        for k, v in payload.items():
            assert body[k] == v, f"PUT {k}: expected {v}, got {body[k]}"

        # Round-trip via GET
        r = await client.get(f"/api/leagues/{LID}",
                              headers={"Authorization": f"Bearer {token}"})
        league = r.json()
        for k, v in payload.items():
            assert league.get(k) == v, f"GET {k}: got {league.get(k)}"


@pytest.mark.asyncio
async def test_validate_setup_returns_ok_for_seeded_league():
    """The seeded Ice Kings league has roster_spots + 12 teams → ok=True."""
    async with AsyncClient(base_url=BASE, timeout=20) as client:
        token = await _login(client)
        r = await client.post(
            f"/api/leagues/{LID}/validate-setup",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] is True
        assert body["teams_count"] >= 2
        assert body["issues"] == []


@pytest.mark.asyncio
async def test_generate_schedule_403_message_is_human_readable():
    """Non-commissioner generating schedule receives a clear 403 message."""
    async with AsyncClient(base_url=BASE, timeout=20) as client:
        token = await _login(client)
        # Find a league where chriszarek is neither commissioner nor co-commissioner
        r = await client.get("/api/leagues",
                              headers={"Authorization": f"Bearer {token}"})
        leagues = r.json()
        me = (await client.get("/api/auth/me",
                                headers={"Authorization": f"Bearer {token}"})).json()
        other = next(
            (
                l for l in leagues
                if l.get("commissioner_id") != me["id"]
                and me["id"] not in (l.get("co_commissioners") or [])
            ),
            None,
        )
        if not other:
            pytest.skip("no league where user isn't a commissioner")
        r = await client.post(
            "/api/matchups/generate-schedule",
            headers={"Authorization": f"Bearer {token}"},
            json={"league_id": other["id"], "num_weeks": 18},
        )
        assert r.status_code == 403, r.text
        detail = r.json()["detail"].lower()
        assert "commissioner" in detail
