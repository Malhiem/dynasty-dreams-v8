"""
Iter 169 — Two paired UX improvements.

(A) Roster page (`TeamDraftPicks.tsx`) now surfaces the conditional-pick
    asterisk that previously only existed in the Draft Room.

(B) The live scoring worker hooks `_take_weekly_tank_snapshots(db)` into
    every poll tick. It writes a new row to `tank_monitor_weekly` per
    league when ≥ 7 days have passed since the last snapshot, so the
    Tank Monitor week-range filter now accrues real historical data
    without anyone calling `/backfill`.
"""
import os
from pathlib import Path

import pytest
from httpx import AsyncClient


def _backend_url():
    env = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", ".env")
    with open(env) as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip()


BASE = _backend_url()
LID = "69e46af167999bfb85c39628"


async def _tok(client, email, password):
    r = await client.post("/api/auth/login", json={"email": email, "password": password})
    return r.json()["access_token"]


# ── (A) Roster page conditional asterisk ──


def test_team_draft_picks_marks_conditional_protection():
    src = Path("/app/frontend/src/lovable/components/dashboard/TeamDraftPicks.tsx").read_text()
    # Hydrated DraftPick carries a _isConditional flag from pending_protections
    assert "_isConditional: (p.pending_protections || []).length > 0" in src
    # Asterisk rendered with the tooltip explaining the clause
    assert 'roster-pick-conditional-${pick.year}-${pick.round}' in src
    assert "Conditional protection — locked from re-trade" in src


# ── (B) Worker hook ──


def test_live_scoring_worker_hooks_weekly_tank_snapshots():
    src = Path("/app/backend/live_scoring_worker.py").read_text()
    # Helper exists
    assert "async def _take_weekly_tank_snapshots(db) -> int" in src
    # 7-day gate
    assert "week_ago = now - timedelta(days=7)" in src
    # Worker loop calls it every tick
    assert "await _take_weekly_tank_snapshots(db)" in src
    # Auto-captured flag persisted so we can distinguish from /backfill rows
    assert '"auto_captured": True' in src
    # Re-uses the monitors helper so values match the live endpoint
    assert "from routes.monitors import _current_tank_rows" in src


@pytest.mark.asyncio
async def test_auto_snapshot_visible_via_weekly_aggregate_endpoint():
    """Sanity check that the auto-captured rows surface through the
    `/tank-monitor?from_week=1&to_week=1` aggregation API — confirming
    the worker writes to the same collection the endpoint reads from."""
    async with AsyncClient(base_url=BASE, timeout=30) as client:
        token = await _tok(client, "admin@dynastydreams.com", "Admin123!")
        h = {"Authorization": f"Bearer {token}"}
        # The worker should have populated week 1 on startup
        r = await client.get(f"/api/leagues/{LID}/tank-monitor?from_week=1&to_week=1", headers=h)
        assert r.status_code == 200
        d = r.json()
        assert d["mode"] == "weekly_aggregate"
        assert d["weeks_available"] >= 1, "Auto-snapshot worker should have populated week 1"
        assert len(d["teams"]) > 0
