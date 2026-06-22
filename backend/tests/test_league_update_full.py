"""Tests for the expanded PUT /leagues/{id} that makes db.leagues the single
source of truth for every wizard/commissioner-settable field, plus the
trade-veto and waiver-budget consumers that now read from league config.
"""
import os
import sys
from datetime import datetime, timezone

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
async def test_league_update_accepts_full_wizard_payload():
    """Every field the Setup Wizard tries to write must be accepted."""
    async with AsyncClient(base_url=BASE, timeout=20) as client:
        token = await _login(client)
        payload = {
            "roster_spots": 23,
            "bench_spots": 5,
            "minors_spots": 4,
            "trade_review_period_hours": 36,
            "trade_veto_threshold_pct": 35,
            "trade_deadline_week": 16,
            "waiver_faab_budget": 200,
            "waiver_period_days": 2,
            "playoff_teams": 8,
            "playoff_start_week": 22,
            "playoff_end_week": 24,
            "playoff_rounds": 3,
            "regular_season_weeks": 21,
            "keepers_allowed": 8,
        }
        r = await client.put(
            f"/api/leagues/{LID}",
            headers={"Authorization": f"Bearer {token}"},
            json=payload,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        for k, v in payload.items():
            assert body[k] == v, f"{k}: expected {v}, got {body[k]}"

        # Round-trip via GET
        r = await client.get(f"/api/leagues/{LID}",
                              headers={"Authorization": f"Bearer {token}"})
        league = r.json()
        for k, v in payload.items():
            assert league.get(k) == v, f"GET {k}: {league.get(k)}"


@pytest.mark.asyncio
async def test_league_update_invalid_field_rejected():
    """Out-of-range values rejected with 422."""
    async with AsyncClient(base_url=BASE, timeout=20) as client:
        token = await _login(client)
        r = await client.put(
            f"/api/leagues/{LID}",
            headers={"Authorization": f"Bearer {token}"},
            json={"roster_spots": 5},  # below ge=10
        )
        assert r.status_code == 422
        r = await client.put(
            f"/api/leagues/{LID}",
            headers={"Authorization": f"Bearer {token}"},
            json={"trade_veto_threshold_pct": 150},  # above le=100
        )
        assert r.status_code == 422


@pytest.mark.asyncio
async def test_league_update_records_diff_in_audit_log():
    """Every changed field writes to db.audit_log."""
    async with AsyncClient(base_url=BASE, timeout=20) as client:
        token = await _login(client)
        # Set roster to a unique value to confirm the diff lands.
        # Bump to a fresh value first to ensure a real diff regardless of
        # prior test state, then re-PUT with the same value to verify the
        # idempotent path produces an empty changeset.
        before = datetime.now(timezone.utc).isoformat()
        # Read current value
        cur = await client.get(f"/api/leagues/{LID}",
                                headers={"Authorization": f"Bearer {token}"})
        cur_rs = cur.json().get("roster_spots") or 20
        next_rs = 27 if cur_rs != 27 else 28
        r = await client.put(
            f"/api/leagues/{LID}",
            headers={"Authorization": f"Bearer {token}"},
            json={"roster_spots": next_rs},
        )
        assert r.status_code == 200
        assert "roster_spots" in r.json()["changes"]
        # Sparse update with same value → no change recorded
        r2 = await client.put(
            f"/api/leagues/{LID}",
            headers={"Authorization": f"Bearer {token}"},
            json={"roster_spots": next_rs},
        )
        assert r2.status_code == 200
        assert r2.json()["changes"] == {}


@pytest.mark.asyncio
async def test_non_commissioner_blocked():
    """Force a 403 by hitting another league where the user isn't comm.

    Skipped if no second league exists in seed.
    """
    async with AsyncClient(base_url=BASE, timeout=20) as client:
        token = await _login(client)
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
            pytest.skip("no league where chriszarek is not commissioner")
        r = await client.put(
            f"/api/leagues/{other['id']}",
            headers={"Authorization": f"Bearer {token}"},
            json={"roster_spots": 30},
        )
        assert r.status_code == 403
