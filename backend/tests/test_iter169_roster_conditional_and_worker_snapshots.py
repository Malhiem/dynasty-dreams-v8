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
from tests.source_tree import read_source
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
    src = read_source(Path("/app/frontend/src/lovable/components/dashboard/TeamDraftPicks.tsx"))
    # Hydrated DraftPick carries a _isConditional flag from pending_protections
    assert "_isConditional: (p.pending_protections || []).length > 0" in src
    # Asterisk rendered with the tooltip explaining the clause
    assert 'roster-pick-conditional-${pick.year}-${pick.round}' in src
    assert "Conditional protection — locked from re-trade" in src


# ── (B) Worker hook ──


def test_live_scoring_worker_hooks_weekly_tank_snapshots():
    src = read_source(Path("/app/backend/live_scoring_worker.py"))
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
    from motor.motor_asyncio import AsyncIOMotorClient
    from routes import monitors, roster
    from server import calculate_fantasy_points
    from live_scoring_worker import _take_weekly_tank_snapshots
    mongo = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = mongo[os.environ["DB_NAME"]]
    old_deps = dict(monitors._deps)
    old_roster_deps = dict(roster._deps)
    try:
        # The E2E server disables worker loops; exercise this worker step explicitly.
        monitors.setup({"db": db})
        roster.setup({"db": db, "calculate_fantasy_points": calculate_fantasy_points})
        await db.tank_monitor_weekly.delete_many({"league_id": LID})
        assert await _take_weekly_tank_snapshots(db) >= 1
        snapshot = await db.tank_monitor_weekly.find_one({"league_id": LID, "week": 1})
        assert snapshot["auto_captured"] is True
        # A repeat tick within seven days must not append another snapshot.
        await _take_weekly_tank_snapshots(db)
        assert await db.tank_monitor_weekly.count_documents({"league_id": LID}) == 1
        async with AsyncClient(base_url=BASE, timeout=30) as client:
            token = await _tok(client, os.environ["ADMIN_EMAIL"], os.environ["ADMIN_PASSWORD"])
            response = await client.get(f"/api/leagues/{LID}/tank-monitor?from_week=1&to_week=1",
                headers={"Authorization": f"Bearer {token}"})
            assert response.status_code == 200
            data = response.json()
            assert data["mode"] == "weekly_aggregate"
            assert data["weeks_available"] >= 1 and len(data["teams"]) > 0
    finally:
        roster._deps.clear()
        roster._deps.update(old_roster_deps)
        monitors._deps.clear()
        monitors._deps.update(old_deps)
        await db.tank_monitor_weekly.delete_many({"league_id": LID})
        mongo.close()
