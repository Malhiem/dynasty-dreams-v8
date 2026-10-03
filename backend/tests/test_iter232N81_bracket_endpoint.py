"""Iter 232N.81 — GET /playoff-bracket endpoint for the bracket
visualizer. Verifies:
  1. 404 for unknown league.
  2. 400 for non-sandbox league.
  3. Empty payload when nothing has been seeded yet.
  4. Happy path after seed — returns the rounds + champion.
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
        "_id": uid, "email": f"n81_{str(uid)[:6]}@iter.test",
        "name": "N81 admin", "role": "admin",
    })
    return str(uid)


def _wire(user_id):
    from routes import admin_test_sandbox as m
    db = _db()
    async def _fake_user(_r):
        return await db.users.find_one({"_id": ObjectId(user_id)})
    m._deps["db"] = db
    m._deps["get_current_user"] = _fake_user


async def _seed_sandbox(db, num_teams=8, is_sandbox=True):
    league_id = ObjectId()
    await db.leagues.insert_one({
        "_id": league_id, "name": "N81 Bracket League",
        "is_test_sandbox": is_sandbox,
    })
    for i in range(num_teams):
        await db.teams.insert_one({
            "_id": ObjectId(), "league_id": str(league_id),
            "name": f"N81 Team {i}",
            "created_at": datetime.now(timezone.utc),
        })
    if is_sandbox:
        await db.drafts.insert_one({
            "league_id": str(league_id), "status": "completed",
            "total_rounds": 20, "current_pick": 999,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        })
    return str(league_id)


async def _cleanup(db, league_id, admin_id):
    await db.leagues.delete_one({"_id": ObjectId(league_id)})
    await db.teams.delete_many({"league_id": league_id})
    await db.matchups.delete_many({"league_id": league_id})
    await db.drafts.delete_many({"league_id": league_id})
    await db.league_seasons.delete_many({"league_id": league_id})
    await db.users.delete_one({"_id": ObjectId(admin_id)})


# ── 404 for unknown league ────────────────────────────────────────

@pytest.mark.asyncio
async def test_bracket_404_for_unknown_league():
    from routes import admin_test_sandbox as m
    db = _db()
    admin_id = await _seed_admin(db)
    _wire(admin_id)
    with pytest.raises(HTTPException) as exc:
        await m.sandbox_playoff_bracket(str(ObjectId()), _StubReq())
    assert exc.value.status_code == 404
    await db.users.delete_one({"_id": ObjectId(admin_id)})


# ── 400 for non-sandbox league ────────────────────────────────────

@pytest.mark.asyncio
async def test_bracket_400_for_non_sandbox():
    from routes import admin_test_sandbox as m
    db = _db()
    admin_id = await _seed_admin(db)
    _wire(admin_id)
    league_id = await _seed_sandbox(db, num_teams=8, is_sandbox=False)
    with pytest.raises(HTTPException) as exc:
        await m.sandbox_playoff_bracket(league_id, _StubReq())
    assert exc.value.status_code == 400
    await _cleanup(db, league_id, admin_id)


# ── Empty when nothing has been seeded ────────────────────────────

@pytest.mark.asyncio
async def test_bracket_empty_before_seed():
    from routes import admin_test_sandbox as m
    db = _db()
    admin_id = await _seed_admin(db)
    _wire(admin_id)
    league_id = await _seed_sandbox(db, num_teams=8)
    res = await m.sandbox_playoff_bracket(league_id, _StubReq())
    assert res["seeded"] is False
    assert res["bracket"] == []
    assert res["rounds_played"] == 0
    assert res["champion"] is None
    await _cleanup(db, league_id, admin_id)


# ── Happy path: rounds sorted, champion identified ───────────────

@pytest.mark.asyncio
async def test_bracket_returns_full_tree_after_seed():
    from routes import admin_test_sandbox as m
    db = _db()
    admin_id = await _seed_admin(db)
    _wire(admin_id)
    league_id = await _seed_sandbox(db, num_teams=8)

    # Give every team enough sim to seed playoffs.
    for wk in (1, 2, 3):
        await m.sandbox_simulate_week(
            league_id, m.SimulateWeekRequest(week=wk), _StubReq(),
        )
    await m.sandbox_seed_playoffs(
        league_id, m.SeedPlayoffsRequest(min_week=3), _StubReq(),
    )

    res = await m.sandbox_playoff_bracket(league_id, _StubReq())
    assert res["seeded"] is True
    assert res["rounds_played"] == 3   # QF + SF + F
    assert len(res["bracket"]) == 7    # 4 + 2 + 1
    assert res["champion"] is not None
    # First round must have 4 games, second 2, third 1.
    by_round: dict[int, int] = {}
    for m_row in res["bracket"]:
        by_round[m_row["round"]] = by_round.get(m_row["round"], 0) + 1
    assert by_round == {1: 4, 2: 2, 3: 1}
    # Each row includes a valid winner/loser pair.
    for m_row in res["bracket"]:
        assert m_row["winner"] in (m_row["home"], m_row["away"])
        assert m_row["loser"] in (m_row["home"], m_row["away"])
        assert m_row["winner"] != m_row["loser"]
    await _cleanup(db, league_id, admin_id)
