"""Iter 232N.69 — Sandbox simulate-week pytest suite.

Covers the new admin-only, sandbox-only "one-click weekly matchup
simulation" flow layered on top of the 232N.59 sandbox generator:

  1. `POST /admin/test-sandbox/leagues/{id}/simulate-week` refuses non
     sandbox (real) leagues with 400, so we never mutate production
     data by accident.
  2. First call simulates Week 1 → generates matchup docs, updates
     team W/L/T + PF/PA, and returns `week=1`.
  3. Second call auto-picks Week 2 (previous_week + 1) — successive
     clicks build up a season.
  4. Re-running the SAME week is idempotent (replay flag true) — the
     prior week's team credits get rolled back and re-applied so the
     standings row still sums to a single game credit per team.
  5. Deterministic scoring: two independent runs of the same
     (league_id, week) produce identical scores (seeded RNG).
  6. `POST /admin/test-sandbox/leagues/{id}/reset-simulation` zeroes
     out every team + wipes every simulated matchup.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

import pytest
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient
from fastapi import HTTPException

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _db():
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[
        os.environ.get("DB_NAME", os.environ["DB_NAME"])
    ]


class _StubReq:
    def __init__(self):
        self.headers = {}
        self.cookies = {}


async def _seed_admin(db):
    uid = ObjectId()
    await db.users.insert_one({
        "_id": uid, "email": f"n69_{str(uid)[:6]}@iter.test",
        "name": "N69 admin", "role": "admin",
    })
    return str(uid)


def _wire(user_id):
    from routes import admin_test_sandbox as m
    db = _db()
    async def _fake_user(_r):
        return await db.users.find_one({"_id": ObjectId(user_id)})
    m._deps["db"] = db
    m._deps["get_current_user"] = _fake_user


async def _seed_sandbox(db, num_teams=4, is_sandbox=True, with_draft=True):
    league_id = ObjectId()
    await db.leagues.insert_one({
        "_id": league_id, "name": "N69 Sandbox League",
        "is_test_sandbox": is_sandbox,
    })
    team_ids = []
    for i in range(num_teams):
        tid = ObjectId()
        await db.teams.insert_one({
            "_id": tid, "league_id": str(league_id),
            "name": f"N69 Team {i}",
            "created_at": datetime.now(timezone.utc),
        })
        team_ids.append(str(tid))
    # Iter 232N.79 — simulate-week now requires a completed draft.
    # Seed a synthetic completed one so these tests still exercise the
    # matchup-sim path without needing the full draft flow.
    if with_draft and is_sandbox:
        await db.drafts.insert_one({
            "league_id": str(league_id),
            "status": "completed",
            "total_rounds": 20,
            "current_pick": 999,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        })
    return str(league_id), team_ids


async def _cleanup(db, league_id, admin_id):
    await db.leagues.delete_one({"_id": ObjectId(league_id)})
    await db.teams.delete_many({"league_id": league_id})
    await db.matchups.delete_many({"league_id": league_id})
    await db.drafts.delete_many({"league_id": league_id})
    await db.users.delete_one({"_id": ObjectId(admin_id)})


# ── Refusal on non-sandbox leagues ───────────────────────────────

@pytest.mark.asyncio
async def test_simulate_week_refuses_non_sandbox_league():
    from routes import admin_test_sandbox as m
    db = _db()
    admin_id = await _seed_admin(db)
    _wire(admin_id)
    league_id, _ = await _seed_sandbox(db, num_teams=4, is_sandbox=False, with_draft=False)
    with pytest.raises(HTTPException) as exc:
        await m.sandbox_simulate_week(
            league_id, m.SimulateWeekRequest(week=1), _StubReq(),
        )
    assert exc.value.status_code == 400
    assert "sandbox" in exc.value.detail.lower()
    await _cleanup(db, league_id, admin_id)


# ── Happy-path first sim ────────────────────────────────────────

@pytest.mark.asyncio
async def test_simulate_week_generates_matchups_and_updates_records():
    from routes import admin_test_sandbox as m
    db = _db()
    admin_id = await _seed_admin(db)
    _wire(admin_id)
    league_id, tids = await _seed_sandbox(db, num_teams=4)

    res = await m.sandbox_simulate_week(
        league_id, m.SimulateWeekRequest(week=1), _StubReq(),
    )
    assert res["ok"] is True
    assert res["week"] == 1
    # 4 teams → 2 matchups.
    assert len(res["matchups"]) == 2
    # Every team's records should sum to exactly 1 game.
    for team in res["teams"]:
        gp = (team["wins"] or 0) + (team["losses"] or 0) + (team["ties"] or 0)
        assert gp == 1, team

    # Matchup docs land in Mongo with sandbox_sim=True.
    stored = await db.matchups.count_documents({
        "league_id": league_id, "sandbox_sim": True, "week": 1,
    })
    assert stored == 2

    # sandbox_last_sim_week is stamped.
    lg = await db.leagues.find_one({"_id": ObjectId(league_id)})
    assert lg.get("sandbox_last_sim_week") == 1

    await _cleanup(db, league_id, admin_id)


# ── Auto-increment across calls ─────────────────────────────────

@pytest.mark.asyncio
async def test_successive_calls_advance_week_and_stack_records():
    from routes import admin_test_sandbox as m
    db = _db()
    admin_id = await _seed_admin(db)
    _wire(admin_id)
    league_id, _ = await _seed_sandbox(db, num_teams=4)

    r1 = await m.sandbox_simulate_week(
        league_id, m.SimulateWeekRequest(week=None), _StubReq(),
    )
    r2 = await m.sandbox_simulate_week(
        league_id, m.SimulateWeekRequest(week=None), _StubReq(),
    )
    r3 = await m.sandbox_simulate_week(
        league_id, m.SimulateWeekRequest(week=None), _StubReq(),
    )
    assert (r1["week"], r2["week"], r3["week"]) == (1, 2, 3)

    # After 3 weeks, every team should have played 3 games.
    for team in r3["teams"]:
        gp = (team["wins"] or 0) + (team["losses"] or 0) + (team["ties"] or 0)
        assert gp == 3, team

    await _cleanup(db, league_id, admin_id)


# ── Idempotent replay ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_replay_same_week_rolls_back_and_reapplies_once():
    from routes import admin_test_sandbox as m
    db = _db()
    admin_id = await _seed_admin(db)
    _wire(admin_id)
    league_id, _ = await _seed_sandbox(db, num_teams=4)

    a = await m.sandbox_simulate_week(
        league_id, m.SimulateWeekRequest(week=1), _StubReq(),
    )
    b = await m.sandbox_simulate_week(
        league_id, m.SimulateWeekRequest(week=1), _StubReq(),
    )
    assert a["replayed"] is False
    assert b["replayed"] is True

    # Every team should still be at exactly 1 game — not double-credited.
    for team in b["teams"]:
        gp = (team["wins"] or 0) + (team["losses"] or 0) + (team["ties"] or 0)
        assert gp == 1, team

    # Deterministic: replay produces identical scores.
    assert a["matchups"] == b["matchups"]

    await _cleanup(db, league_id, admin_id)


# ── Reset endpoint ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_reset_simulation_zeroes_teams_and_wipes_matchups():
    from routes import admin_test_sandbox as m
    db = _db()
    admin_id = await _seed_admin(db)
    _wire(admin_id)
    league_id, _ = await _seed_sandbox(db, num_teams=4)

    # Play three weeks so the reset has something to erase.
    for _ in range(3):
        await m.sandbox_simulate_week(
            league_id, m.SimulateWeekRequest(week=None), _StubReq(),
        )

    res = await m.sandbox_reset_simulation(league_id, _StubReq())
    assert res["ok"] is True
    assert res["matchups_deleted"] == 6   # 3 weeks × 2 matchups

    # Every team should be back to 0-0-0.
    teams = await db.teams.find({"league_id": league_id}).to_list(200)
    for t in teams:
        assert (t.get("wins") or 0) == 0
        assert (t.get("losses") or 0) == 0
        assert (t.get("ties") or 0) == 0
        assert (t.get("points_for") or 0) == 0
        assert (t.get("points_against") or 0) == 0

    # Next simulate resumes at Week 1 again.
    r = await m.sandbox_simulate_week(
        league_id, m.SimulateWeekRequest(week=None), _StubReq(),
    )
    assert r["week"] == 1

    await _cleanup(db, league_id, admin_id)


# ── Odd team count → BYE ────────────────────────────────────────

@pytest.mark.asyncio
async def test_odd_team_count_produces_bye():
    from routes import admin_test_sandbox as m
    db = _db()
    admin_id = await _seed_admin(db)
    _wire(admin_id)
    league_id, _ = await _seed_sandbox(db, num_teams=5)

    res = await m.sandbox_simulate_week(
        league_id, m.SimulateWeekRequest(week=1), _StubReq(),
    )
    byes = [m_ for m_ in res["matchups"] if m_["away"] == "BYE"]
    assert len(byes) == 1
    # 5 teams → 2 matchups + 1 BYE.
    non_bye = [m_ for m_ in res["matchups"] if m_["away"] != "BYE"]
    assert len(non_bye) == 2

    await _cleanup(db, league_id, admin_id)
