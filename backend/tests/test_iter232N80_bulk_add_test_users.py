"""Iter 232N.80 — Bulk-add test users/teams to a sandbox from the
setup wizard. Verifies:
  1. Non-sandbox leagues refuse the request (404).
  2. Happy path — count=N creates N users + N teams and increments the
     league's current_teams + max_teams counters.
  3. Existing team count offsets the index so team names don't collide.
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
        "_id": uid, "email": f"n80_{str(uid)[:6]}@iter.test",
        "name": "N80 admin", "role": "admin",
    })
    return str(uid)


def _wire(user_id):
    from routes import admin_test_sandbox as m
    db = _db()
    async def _fake_user(_r):
        return await db.users.find_one({"_id": ObjectId(user_id)})
    m._deps["db"] = db
    m._deps["get_current_user"] = _fake_user
    m._deps["hash_password"] = lambda p: f"hashed-{p}"


async def _seed_league(db, is_sandbox=True, existing_teams=1):
    league_id = ObjectId()
    await db.leagues.insert_one({
        "_id": league_id, "name": "N80 Bulk Add League",
        "is_test_sandbox": is_sandbox,
        "max_teams": existing_teams,
        "current_teams": existing_teams,
    })
    for i in range(existing_teams):
        await db.teams.insert_one({
            "league_id": str(league_id),
            "name": f"Pre-existing Team {i}",
            "created_at": datetime.now(timezone.utc),
            "is_test_team": True,
        })
    return str(league_id)


async def _cleanup(db, league_id, admin_id):
    await db.leagues.delete_one({"_id": ObjectId(league_id)})
    await db.teams.delete_many({"league_id": league_id})
    await db.users.delete_many({"test_league_hint": league_id})
    await db.users.delete_one({"_id": ObjectId(admin_id)})


# ── Refuses non-sandbox leagues ───────────────────────────────────

@pytest.mark.asyncio
async def test_bulk_add_refuses_non_sandbox():
    from routes import admin_test_sandbox as m
    db = _db()
    admin_id = await _seed_admin(db)
    _wire(admin_id)
    league_id = await _seed_league(db, is_sandbox=False, existing_teams=1)

    with pytest.raises(HTTPException) as exc:
        await m.bulk_add_test_users(
            league_id, m.BulkAddTestUsersRequest(count=3), _StubReq(),
        )
    assert exc.value.status_code == 404

    await _cleanup(db, league_id, admin_id)


# ── Happy path: creates N users + teams, bumps counters ──────────

@pytest.mark.asyncio
async def test_bulk_add_creates_users_and_teams():
    from routes import admin_test_sandbox as m
    db = _db()
    admin_id = await _seed_admin(db)
    _wire(admin_id)
    league_id = await _seed_league(db, is_sandbox=True, existing_teams=1)

    res = await m.bulk_add_test_users(
        league_id, m.BulkAddTestUsersRequest(count=5), _StubReq(),
    )
    assert res["ok"] is True
    assert res["added"] == 5
    assert res["new_team_count"] == 6   # 1 existing + 5 added
    assert len(res["teams"]) == 5

    # DB reflects the new teams.
    team_count = await db.teams.count_documents({"league_id": league_id})
    assert team_count == 6

    # League counters updated.
    lg = await db.leagues.find_one({"_id": ObjectId(league_id)})
    assert lg["current_teams"] == 6
    assert lg["max_teams"] >= 6

    await _cleanup(db, league_id, admin_id)


# ── Index offset: replays don't collide (append onto existing) ────

@pytest.mark.asyncio
async def test_bulk_add_appends_without_index_collision():
    from routes import admin_test_sandbox as m
    db = _db()
    admin_id = await _seed_admin(db)
    _wire(admin_id)
    league_id = await _seed_league(db, is_sandbox=True, existing_teams=2)

    r1 = await m.bulk_add_test_users(
        league_id, m.BulkAddTestUsersRequest(count=3), _StubReq(),
    )
    r2 = await m.bulk_add_test_users(
        league_id, m.BulkAddTestUsersRequest(count=2), _StubReq(),
    )
    assert r1["new_team_count"] == 5   # 2 + 3
    assert r2["new_team_count"] == 7   # 5 + 2

    # No two teams in the league share a name (i.e. the index offset
    # correctly avoided "Test User 3's Team" being created twice).
    names = [t["name"] async for t in db.teams.find({"league_id": league_id})]
    assert len(names) == len(set(names)) == 7

    await _cleanup(db, league_id, admin_id)
