"""
Iter 160 — Commissioner Monitor endpoints replace mock TankMonitor + RosterMonitor data.

Validates:
  - GET /api/leagues/{league_id}/tank-monitor returns per-team roster-section
    fantasy point splits (startingPts, benchPts, irPts, minorsPts).
  - GET /api/leagues/{league_id}/roster-monitor returns per-team roster
    snapshots with counts + violations and league-wide limits.
  - 404 for missing league IDs.

Also validates:
  - The frontend data module now accepts `leagueId` on both tables.
  - MonitorTabs forwards `leagueId` through to the tables.
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
LID = "69e46af167999bfb85c39628"  # Ice Kings Head-to-Head


async def _token(client):
    r = await client.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
    return r.json()["access_token"]


# ── Backend endpoint tests ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_tank_monitor_returns_per_team_split():
    async with AsyncClient(base_url=BASE, timeout=30) as client:
        token = await _token(client)
        headers = {"Authorization": f"Bearer {token}"}
        r = await client.get(f"/api/leagues/{LID}/tank-monitor", headers=headers)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["league_id"] == LID
        assert "league_name" in d
        teams = d.get("teams", [])
        assert isinstance(teams, list) and len(teams) > 0, "League should have ≥ 1 team"
        # Required schema per team
        for t in teams:
            assert "team_id" in t and t["team_id"]
            assert "team" in t and t["team"]
            for k in ("startingPts", "benchPts", "irPts", "minorsPts"):
                assert k in t, f"Missing {k}"
                assert isinstance(t[k], (int, float))


@pytest.mark.asyncio
async def test_roster_monitor_returns_counts_and_limits():
    async with AsyncClient(base_url=BASE, timeout=30) as client:
        token = await _token(client)
        headers = {"Authorization": f"Bearer {token}"}
        r = await client.get(f"/api/leagues/{LID}/roster-monitor", headers=headers)
        assert r.status_code == 200, r.text
        d = r.json()
        # Limits payload
        limits = d.get("limits", {})
        for k in ("starting_skaters", "starting_goalies", "bench", "ir", "minors"):
            assert k in limits, f"Missing limit: {k}"
        # Teams payload
        teams = d.get("teams", [])
        assert isinstance(teams, list) and len(teams) > 0
        for t in teams:
            assert "team_id" in t
            counts = t.get("counts", {})
            for slot in ("starting", "bench", "ir", "minors"):
                assert slot in counts, f"Missing count: {slot}"
            assert "violations" in t and isinstance(t["violations"], list)
            assert "players" in t and isinstance(t["players"], list)
            # Player shape (only check if there are any)
            if t["players"]:
                p = t["players"][0]
                for f in ("id", "name", "position", "slot", "fantasyPoints"):
                    assert f in p, f"Player missing field: {f}"
                assert p["slot"] in ("starting", "bench", "ir", "minors")


@pytest.mark.asyncio
async def test_monitors_return_404_for_unknown_league():
    async with AsyncClient(base_url=BASE, timeout=15) as client:
        token = await _token(client)
        headers = {"Authorization": f"Bearer {token}"}
        bogus = "0" * 24
        r1 = await client.get(f"/api/leagues/{bogus}/tank-monitor", headers=headers)
        r2 = await client.get(f"/api/leagues/{bogus}/roster-monitor", headers=headers)
        assert r1.status_code == 404
        assert r2.status_code == 404


# ── Static frontend wiring tests ────────────────────────────────────────


FRONTEND = Path("/app/frontend/src")


def _read(rel: str) -> str:
    return (FRONTEND / rel).read_text(encoding="utf-8")


def test_data_module_supports_league_id_prop():
    src = _read("lovable/pages/commissioner/data/commissionerData.tsx")
    # Both tables accept leagueId
    assert "export const TankMonitorTable = ({ leagueId }:" in src
    assert "leagueId }: { onAuditLog?: " in src or "leagueId?: string" in src
    # Live fetch wired
    assert "/leagues/${leagueId}/tank-monitor" in src
    assert "/leagues/${leagueId}/roster-monitor" in src
    # Live badge testids
    for tid in (
        "tank-monitor-live-badge",
        "tank-monitor-table",
        "roster-monitor-live-badge",
        "roster-monitor-table",
    ):
        assert f'data-testid="{tid}"' in src, f"Missing testid: {tid}"


def test_monitor_tabs_forward_league_id():
    src = _read("lovable/pages/commissioner/tabs/MonitorTabs.tsx")
    # Both tabs accept + forward leagueId
    assert "leagueId?: string" in src
    assert "leagueId={leagueId}" in src


def test_parent_passes_active_league_id():
    src = _read("lovable/pages/CommissionerSettings.tsx")
    assert "leagueId={activeLeague?.id}" in src


def test_backend_router_wired():
    server_src = Path("/app/backend/server.py").read_text()
    assert "monitors as monitors_routes" in server_src
    assert "monitors_routes.setup" in server_src
    assert "api_router.include_router(monitors_routes.router)" in server_src
