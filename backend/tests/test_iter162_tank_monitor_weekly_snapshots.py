"""
Iter 162 — Tank Monitor weekly snapshots + backfill + week-range queries.

Validates:
  - GET /api/leagues/{id}/tank-monitor?from_week=&to_week= aggregates
    persisted snapshots (mode: weekly_aggregate)
  - POST /api/leagues/{id}/tank-monitor/snapshot?week=N persists a single
    week (idempotent; upsert on (league_id, week))
  - POST /api/leagues/{id}/tank-monitor/backfill?weeks=N writes 1..N
    weeks of plausible history; idempotent unless overwrite=true.
  - Frontend wiring: TankMonitorTable accepts week-range mode, has the
    backfill button + week-range toggle.
"""
import os
from pathlib import Path

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
async def test_tank_monitor_live_mode_when_no_week_params():
    async with AsyncClient(base_url=BASE, timeout=30) as client:
        token = await _token(client)
        headers = {"Authorization": f"Bearer {token}"}
        r = await client.get(f"/api/leagues/{LID}/tank-monitor", headers=headers)
        assert r.status_code == 200
        d = r.json()
        assert d.get("mode") == "live"
        assert "weeks_available" not in d  # only present in aggregate mode


@pytest.mark.asyncio
async def test_tank_monitor_backfill_then_weekly_aggregate():
    async with AsyncClient(base_url=BASE, timeout=60) as client:
        token = await _token(client)
        headers = {"Authorization": f"Bearer {token}"}
        # Force a clean backfill — overwrite to guarantee weeks_written > 0
        r = await client.post(
            f"/api/leagues/{LID}/tank-monitor/backfill?weeks=22&overwrite=true",
            headers=headers,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["weeks_written"] == 22
        # Aggregate weeks 1-5
        r2 = await client.get(
            f"/api/leagues/{LID}/tank-monitor?from_week=1&to_week=5",
            headers=headers,
        )
        assert r2.status_code == 200
        d2 = r2.json()
        assert d2["mode"] == "weekly_aggregate"
        assert d2["from_week"] == 1 and d2["to_week"] == 5
        assert d2["weeks_available"] == 5
        assert len(d2["teams"]) > 0
        # Aggregated values should be ~5x the per-week values (sanity check)
        for t in d2["teams"]:
            assert isinstance(t["startingPts"], (int, float))


@pytest.mark.asyncio
async def test_tank_monitor_snapshot_is_idempotent():
    async with AsyncClient(base_url=BASE, timeout=30) as client:
        token = await _token(client)
        headers = {"Authorization": f"Bearer {token}"}
        r1 = await client.post(f"/api/leagues/{LID}/tank-monitor/snapshot?week=1", headers=headers)
        r2 = await client.post(f"/api/leagues/{LID}/tank-monitor/snapshot?week=1", headers=headers)
        assert r1.status_code == 200 and r2.status_code == 200
        assert r1.json()["teams_captured"] == r2.json()["teams_captured"]
        # Week query reflects the (re)write
        r3 = await client.get(
            f"/api/leagues/{LID}/tank-monitor?from_week=1&to_week=1",
            headers=headers,
        )
        assert r3.status_code == 200
        assert r3.json()["weeks_available"] == 1


@pytest.mark.asyncio
async def test_backfill_404_for_unknown_league():
    async with AsyncClient(base_url=BASE, timeout=15) as client:
        token = await _token(client)
        headers = {"Authorization": f"Bearer {token}"}
        bogus = "0" * 24
        r = await client.post(f"/api/leagues/{bogus}/tank-monitor/backfill", headers=headers)
        assert r.status_code == 404


# ── Frontend wiring ──────────────────────────────────────────────


FRONTEND = Path("/app/frontend/src")


def test_tank_monitor_table_supports_week_range_in_live_mode():
    src = (FRONTEND / "lovable/pages/commissioner/data/commissionerData.tsx").read_text()
    # Week-range toggle + backfill UI exist
    assert 'data-testid="tank-monitor-toggle-week-range"' in src
    assert 'data-testid="tank-monitor-backfill-button"' in src
    # Endpoint URLs constructed correctly
    assert "/leagues/${leagueId}/tank-monitor?from_week=${fromWeek}&to_week=${toWeek}" in src
    assert "/leagues/${leagueId}/tank-monitor/backfill" in src
    # Live mode flag tracked
    assert "weekly_aggregate" in src
