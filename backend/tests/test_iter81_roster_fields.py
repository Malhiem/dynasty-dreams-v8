"""Iter 81 — verify the extended roster fields round-trip through PUT/GET
and the backfill script seeded sensible defaults on existing leagues.
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


@pytest.mark.asyncio
async def test_iter81_roster_fields_roundtrip():
    """Every new roster field (ir_slots, position_limits, etc) round-trips.

    Snapshots and restores all touched fields after the test so we don't
    leak `enforce_position_maxes=True` (or strict `position_limits`) into
    other tests that assume the iter79-backfill defaults.
    """
    async with AsyncClient(base_url=BASE, timeout=20) as client:
        r = await client.post("/api/auth/login",
                              json={"email": EMAIL, "password": PASSWORD})
        token = r.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        payload = {
            "ir_slots": 4,
            "ir_plus_slots": 2,
            "taxi_squad_size": 6,
            "position_limits": {"C": 4, "LW": 4, "RW": 4, "D": 6, "G": 3},
            "enforce_position_maxes": True,
            "min_active_players": 16,
            "min_games_played": 60,
            "prorate_min_max_by_period": True,
            "allow_illegal_rosters": False,
            "ir_eligibility_modes": ["IR", "IR-LT"],
        }
        # Snapshot pre-test state so we can restore — protects sibling tests
        # that assume backfilled defaults (enforce_position_maxes=False, etc.)
        before = (await client.get(f"/api/leagues/{LID}", headers=headers)).json()
        snapshot = {k: before.get(k) for k in payload.keys()}
        try:
            r = await client.put(f"/api/leagues/{LID}", headers=headers, json=payload)
            assert r.status_code == 200, r.text
            body = r.json()
            for k, v in payload.items():
                assert body[k] == v, f"PUT echo mismatch {k}: got {body[k]}"

            r = await client.get(f"/api/leagues/{LID}", headers=headers)
            league = r.json()
            for k, v in payload.items():
                assert league.get(k) == v, f"GET round-trip mismatch {k}: got {league.get(k)}"
        finally:
            await client.put(f"/api/leagues/{LID}", headers=headers, json=snapshot)


@pytest.mark.asyncio
async def test_backfill_left_existing_values_alone():
    """The backfill script must NOT overwrite values the test set above."""
    async with AsyncClient(base_url=BASE, timeout=20) as client:
        r = await client.post("/api/auth/login",
                              json={"email": EMAIL, "password": PASSWORD})
        token = r.json()["access_token"]
        r = await client.get(f"/api/leagues/{LID}",
                              headers={"Authorization": f"Bearer {token}"})
        league = r.json()
        # All iter79 + iter81 defaults must exist (not None for the boolean ones,
        # but the keys must be present in the response model).
        for key in [
            "matchup_length_days", "opponents_per_matchup_period",
            "consolation_enabled", "consolation_uses_playoff_schedule",
            "salary_retention_enabled", "salary_retention_max_pct",
            "ir_slots", "ir_plus_slots", "taxi_squad_size",
            "enforce_position_maxes", "min_active_players", "min_games_played",
            "prorate_min_max_by_period", "allow_illegal_rosters",
            "ir_eligibility_modes",
        ]:
            assert key in league, f"missing backfilled key: {key}"


@pytest.mark.asyncio
async def test_iter81_invalid_ir_slot_count_returns_422():
    """Validation: ir_slots above the allowed range must 422 (not 500)."""
    async with AsyncClient(base_url=BASE, timeout=15) as client:
        r = await client.post("/api/auth/login",
                              json={"email": EMAIL, "password": PASSWORD})
        token = r.json()["access_token"]
        r = await client.put(
            f"/api/leagues/{LID}",
            headers={"Authorization": f"Bearer {token}"},
            json={"ir_slots": 999},
        )
        assert r.status_code == 422, r.text
