"""Iter 100: League Admin overhaul — validate the new league-update fields
(roster lock + lineup lock + NHL stats window + opponents/period) plus the
new `GET /api/nhl-season-bounds` endpoint and the playoff validation rules
the user requested.
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
EMAIL = "chriszarek@gmail.com"
PASSWORD = "Chris2026!"
LID = "69e46af167999bfb85c39628"


async def _token(client):
    r = await client.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
    return r.json()["access_token"]


@pytest.mark.asyncio
async def test_nhl_season_bounds_endpoint():
    async with AsyncClient(base_url=BASE, timeout=15) as client:
        r = await client.get("/api/nhl-season-bounds")
        assert r.status_code == 200
        d = r.json()
        assert d["season"] == "2025-26"
        assert len(d["weeks"]) >= 30  # NHL season + playoffs span ~38 weeks
        assert d["weeks"][0]["number"] == 1
        assert "start_date" in d["weeks"][0] and "end_date" in d["weeks"][0]


@pytest.mark.asyncio
async def test_put_league_accepts_new_roster_lock_fields():
    async with AsyncClient(base_url=BASE, timeout=15) as client:
        token = await _token(client)
        headers = {"Authorization": f"Bearer {token}"}

        # Snapshot current values to restore later
        before = await client.get(f"/api/leagues/{LID}", headers=headers)
        prev = before.json()

        payload = {
            "roster_lock_type": "semi_weekly",
            "roster_lock_day": "monday",
            "roster_lock_second_day": "thursday",
            "lineup_lock_minutes_before": 30,
            "playoff_roster_lock_override": True,
            "playoff_roster_lock_type": "weekly",
            "playoff_roster_lock_day": "tuesday",
            "playoff_lineup_lock_minutes_before": 60,
        }
        r = await client.put(f"/api/leagues/{LID}", headers=headers, json=payload)
        assert r.status_code == 200, r.text
        out = r.json()
        assert out["roster_lock_type"] == "semi_weekly"
        assert out["roster_lock_second_day"] == "thursday"
        assert out["lineup_lock_minutes_before"] == 30
        assert out["playoff_roster_lock_override"] is True
        assert out["playoff_lineup_lock_minutes_before"] == 60

        # Restore prior state
        restore = {k: prev.get(k) for k in payload.keys()}
        await client.put(f"/api/leagues/{LID}", headers=headers, json=restore)


@pytest.mark.asyncio
async def test_put_league_validates_lock_type_enum():
    async with AsyncClient(base_url=BASE, timeout=15) as client:
        token = await _token(client)
        headers = {"Authorization": f"Bearer {token}"}
        r = await client.put(
            f"/api/leagues/{LID}",
            headers=headers,
            json={"roster_lock_type": "bogus_cadence"},
        )
        assert r.status_code == 422


@pytest.mark.asyncio
async def test_put_league_rejects_playoff_starting_in_regular_season():
    """Playoffs must start AFTER the regular season ends — backend hard-validate."""
    async with AsyncClient(base_url=BASE, timeout=15) as client:
        token = await _token(client)
        headers = {"Authorization": f"Bearer {token}"}
        r = await client.put(
            f"/api/leagues/{LID}",
            headers=headers,
            json={"regular_season_weeks": 20, "playoff_start_week": 15},
        )
        assert r.status_code == 400
        assert "must start AFTER" in r.json()["detail"]


@pytest.mark.asyncio
async def test_put_league_rejects_insufficient_playoff_weeks_for_rounds():
    """Cannot award a champion when rounds > available playoff weeks."""
    async with AsyncClient(base_url=BASE, timeout=15) as client:
        token = await _token(client)
        headers = {"Authorization": f"Bearer {token}"}
        r = await client.put(
            f"/api/leagues/{LID}",
            headers=headers,
            # 1 week of playoffs but trying to run 3 rounds
            json={
                "regular_season_weeks": 18,
                "playoff_start_week": 19,
                "playoff_end_week": 19,
                "playoff_rounds": 3,
            },
        )
        assert r.status_code == 400
        assert "Cannot award a champion" in r.json()["detail"]


@pytest.mark.asyncio
async def test_put_league_rejects_too_few_teams_for_rounds():
    async with AsyncClient(base_url=BASE, timeout=15) as client:
        token = await _token(client)
        headers = {"Authorization": f"Bearer {token}"}
        r = await client.put(
            f"/api/leagues/{LID}",
            headers=headers,
            # 3 rounds requires >= 8 teams; sending 4
            json={
                "regular_season_weeks": 18,
                "playoff_start_week": 19,
                "playoff_end_week": 21,
                "playoff_rounds": 3,
                "playoff_teams": 4,
            },
        )
        assert r.status_code == 400
        assert "at least 8 playoff teams" in r.json()["detail"]


@pytest.mark.asyncio
async def test_put_league_accepts_opponents_per_period_and_stats_window():
    async with AsyncClient(base_url=BASE, timeout=15) as client:
        token = await _token(client)
        headers = {"Authorization": f"Bearer {token}"}
        before = await client.get(f"/api/leagues/{LID}", headers=headers)
        prev = before.json()

        r = await client.put(
            f"/api/leagues/{LID}",
            headers=headers,
            json={
                "opponents_per_matchup_period": 2,
                "stats_count_start_date": "2025-10-13",
                "stats_count_end_date": "2026-04-12",
            },
        )
        assert r.status_code == 200, r.text
        out = r.json()
        assert out["opponents_per_matchup_period"] == 2
        assert out["stats_count_start_date"] == "2025-10-13"
        assert out["stats_count_end_date"] == "2026-04-12"

        # Restore
        await client.put(
            f"/api/leagues/{LID}",
            headers=headers,
            json={
                "opponents_per_matchup_period": prev.get("opponents_per_matchup_period") or 1,
                "stats_count_start_date": prev.get("stats_count_start_date"),
                "stats_count_end_date": prev.get("stats_count_end_date"),
            },
        )
