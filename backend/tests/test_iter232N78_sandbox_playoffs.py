"""Iter 232N.78 — Sandbox seed-playoffs pytest suite.

Covers the auto-advance-to-playoffs flow:
  1. Refuses when regular season < min_week (default 17).
  2. Happy path: after simulating through Week 17, seeding a bracket
     produces a champion, round-by-round matchups, and stamps the
     league doc with the crowning info.
  3. Bracket size rounds down to nearest power of two.
  4. Replaying the seed is idempotent: prior playoff docs get wiped
     and a fresh (deterministic) bracket lands.
  5. Reset-simulation wipes both regular-season sandbox matchups AND
     playoff matchups + unsets the champion pointer.
"""
from __future__ import annotations

import math
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
        os.environ.get("DB_NAME", "test_database")
    ]


class _StubReq:
    def __init__(self):
        self.headers = {}
        self.cookies = {}


async def _seed_admin(db):
    uid = ObjectId()
    await db.users.insert_one({
        "_id": uid, "email": f"n78_{str(uid)[:6]}@iter.test",
        "name": "N78 admin", "role": "admin",
    })
    return str(uid)


def _wire(user_id):
    from routes import admin_test_sandbox as m
    db = _db()
    async def _fake_user(_r):
        return await db.users.find_one({"_id": ObjectId(user_id)})
    m._deps["db"] = db
    m._deps["get_current_user"] = _fake_user


async def _seed_sandbox(db, num_teams=8, is_sandbox=True, with_draft=True):
    league_id = ObjectId()
    await db.leagues.insert_one({
        "_id": league_id, "name": "N78 Sandbox Playoffs League",
        "is_test_sandbox": is_sandbox,
    })
    team_ids = []
    for i in range(num_teams):
        tid = ObjectId()
        await db.teams.insert_one({
            "_id": tid, "league_id": str(league_id),
            "name": f"N78 Team {i}",
            "created_at": datetime.now(timezone.utc),
        })
        team_ids.append(str(tid))
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
    await db.league_seasons.delete_many({"league_id": league_id})
    await db.users.delete_one({"_id": ObjectId(admin_id)})


async def _sim_through(m, league_id, target_week):
    """Simulate weeks 1 through target_week (inclusive) sequentially."""
    for wk in range(1, target_week + 1):
        await m.sandbox_simulate_week(
            league_id, m.SimulateWeekRequest(week=wk), _StubReq(),
        )


# ── Gate: too-early seeding is refused ─────────────────────────────

@pytest.mark.asyncio
async def test_seed_playoffs_refuses_before_min_week():
    from routes import admin_test_sandbox as m
    db = _db()
    admin_id = await _seed_admin(db)
    _wire(admin_id)
    league_id, _ = await _seed_sandbox(db, num_teams=8)

    # Only simulate 3 weeks, well below the default min_week=17.
    await _sim_through(m, league_id, 3)
    with pytest.raises(HTTPException) as exc:
        await m.sandbox_seed_playoffs(
            league_id, m.SeedPlayoffsRequest(), _StubReq(),
        )
    assert exc.value.status_code == 400
    assert "week" in exc.value.detail.lower()

    await _cleanup(db, league_id, admin_id)


# ── Refuses on non-sandbox leagues ─────────────────────────────────

@pytest.mark.asyncio
async def test_seed_playoffs_refuses_non_sandbox_league():
    from routes import admin_test_sandbox as m
    db = _db()
    admin_id = await _seed_admin(db)
    _wire(admin_id)
    league_id, _ = await _seed_sandbox(db, num_teams=8, is_sandbox=False, with_draft=False)
    with pytest.raises(HTTPException) as exc:
        await m.sandbox_seed_playoffs(
            league_id, m.SeedPlayoffsRequest(min_week=1), _StubReq(),
        )
    assert exc.value.status_code == 400
    assert "sandbox" in exc.value.detail.lower()
    await _cleanup(db, league_id, admin_id)


# ── Happy path: seed bracket + crown champion ──────────────────────

@pytest.mark.asyncio
async def test_seed_playoffs_happy_path_produces_champion():
    from routes import admin_test_sandbox as m
    db = _db()
    admin_id = await _seed_admin(db)
    _wire(admin_id)
    league_id, _ = await _seed_sandbox(db, num_teams=8)

    # Use min_week=3 so the test doesn't have to simulate 17 weeks.
    await _sim_through(m, league_id, 3)
    res = await m.sandbox_seed_playoffs(
        league_id, m.SeedPlayoffsRequest(min_week=3), _StubReq(),
    )
    assert res["ok"] is True
    # 8 teams → 3 rounds (QF → SF → F).
    assert res["num_playoff_teams"] == 8
    assert res["rounds_played"] == 3
    assert res["champion"] is not None
    assert len(res["seeds"]) == 8
    # QF has 4 games, SF 2, F 1 → 7 total playoff matchups persisted.
    stored = await db.matchups.count_documents({
        "league_id": league_id, "sandbox_playoff": True,
    })
    assert stored == 7

    # League doc stamps the champion pointer.
    lg = await db.leagues.find_one({"_id": ObjectId(league_id)})
    assert lg.get("sandbox_playoff_champion_team_id") == res["champion_team_id"]
    assert lg.get("sandbox_playoffs_seeded_at") is not None

    await _cleanup(db, league_id, admin_id)


# ── Bracket size floors to nearest power of two ────────────────────

@pytest.mark.asyncio
async def test_bracket_size_floors_to_power_of_two():
    from routes import admin_test_sandbox as m
    db = _db()
    admin_id = await _seed_admin(db)
    _wire(admin_id)
    # 6 teams, ask for 6 playoff spots → should floor to 4.
    league_id, _ = await _seed_sandbox(db, num_teams=6)
    await _sim_through(m, league_id, 3)
    res = await m.sandbox_seed_playoffs(
        league_id,
        m.SeedPlayoffsRequest(min_week=3, num_playoff_teams=6),
        _StubReq(),
    )
    assert res["num_playoff_teams"] == 4
    assert res["rounds_played"] == 2   # SF + F.
    assert math.log2(res["num_playoff_teams"]).is_integer()
    await _cleanup(db, league_id, admin_id)


# ── Idempotent replay: seed twice → fresh bracket, no duplicates ───

@pytest.mark.asyncio
async def test_seed_playoffs_is_idempotent_on_replay():
    from routes import admin_test_sandbox as m
    db = _db()
    admin_id = await _seed_admin(db)
    _wire(admin_id)
    league_id, _ = await _seed_sandbox(db, num_teams=8)
    await _sim_through(m, league_id, 3)

    r1 = await m.sandbox_seed_playoffs(
        league_id, m.SeedPlayoffsRequest(min_week=3), _StubReq(),
    )
    r2 = await m.sandbox_seed_playoffs(
        league_id, m.SeedPlayoffsRequest(min_week=3), _StubReq(),
    )
    # Still exactly 7 playoff matchups persisted (not 14).
    stored = await db.matchups.count_documents({
        "league_id": league_id, "sandbox_playoff": True,
    })
    assert stored == 7
    # Deterministic: same seeds + same rounds produce identical winners.
    assert r1["champion_team_id"] == r2["champion_team_id"]
    assert r1["bracket"] == r2["bracket"]
    await _cleanup(db, league_id, admin_id)


# ── Reset wipes playoff bracket + unsets champion pointer ──────────

@pytest.mark.asyncio
async def test_reset_simulation_wipes_playoff_bracket():
    from routes import admin_test_sandbox as m
    db = _db()
    admin_id = await _seed_admin(db)
    _wire(admin_id)
    league_id, _ = await _seed_sandbox(db, num_teams=8)
    await _sim_through(m, league_id, 3)
    await m.sandbox_seed_playoffs(
        league_id, m.SeedPlayoffsRequest(min_week=3), _StubReq(),
    )
    # Sanity — bracket exists pre-reset.
    pre = await db.matchups.count_documents({
        "league_id": league_id, "sandbox_playoff": True,
    })
    assert pre == 7

    await m.sandbox_reset_simulation(league_id, _StubReq())

    post = await db.matchups.count_documents({
        "league_id": league_id, "sandbox_playoff": True,
    })
    assert post == 0
    lg = await db.leagues.find_one({"_id": ObjectId(league_id)})
    assert lg.get("sandbox_playoff_champion_team_id") is None
    assert lg.get("sandbox_playoffs_seeded_at") is None
    assert lg.get("sandbox_last_sim_week") is None

    await _cleanup(db, league_id, admin_id)
