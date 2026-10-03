"""Iter 232N.62 — Draft-room cap view endpoint tests.

Covers:
  1. Non-cap league returns `salary_cap_enabled=false` + empty teams.
  2. Cap league returns one row per team with correct salary_used sums.
  3. Player without contract/cap_hit falls back to league's
     `default_rookie_aav` (or 950k default).
  4. `approaching` flag flips at 90% cap usage.
  5. `my_team_id` is set to the caller's team in the league.
  6. Unauthenticated caller gets 401.
  7. Nonexistent draft returns 404.
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


async def _seed(db, cap_enabled: bool, cap: int = 90_000_000,
                default_rookie_aav: int = 950_000):
    admin = ObjectId()
    await db.users.insert_one({
        "_id": admin, "email": f"n62_{str(admin)[:6]}@iter.test",
        "name": "N62 Admin", "role": "user",
        "created_at": datetime.now(timezone.utc),
    })
    lg = await db.leagues.insert_one({
        "name": "N62 League", "sport": "nhl",
        "salary_cap_enabled": cap_enabled,
        "salary_cap": cap if cap_enabled else None,
        "default_rookie_aav": default_rookie_aav,
        "commissioner_id": str(admin),
        "created_at": datetime.now(timezone.utc),
    })
    league_id = str(lg.inserted_id)
    t1 = await db.teams.insert_one({
        "league_id": league_id, "owner_id": str(admin),
        "name": "MyTeam", "roster": [], "lineup": {},
    })
    t2 = await db.teams.insert_one({
        "league_id": league_id, "owner_id": str(ObjectId()),
        "name": "OtherTeam", "roster": [], "lineup": {},
    })
    dr = await db.drafts.insert_one({
        "league_id": league_id, "status": "in_progress",
        "type": "entry", "current_pick": 1,
    })
    return {
        "admin_id": str(admin),
        "league_id": league_id,
        "draft_id": str(dr.inserted_id),
        "team1_id": str(t1.inserted_id),
        "team2_id": str(t2.inserted_id),
    }


def _wire(caller_id: str):
    from routes import draft_cap_view as m
    db = _db()
    async def _fake_user(_r):
        u = await db.users.find_one({"_id": ObjectId(caller_id)})
        return u
    m._deps["db"] = db
    m._deps["get_current_user"] = _fake_user
    return m


async def _cleanup(db, seed):
    await db.users.delete_many({"_id": ObjectId(seed["admin_id"])})
    await db.leagues.delete_one({"_id": ObjectId(seed["league_id"])})
    await db.teams.delete_many({"league_id": seed["league_id"]})
    await db.draft_picks.delete_many({"draft_id": seed["draft_id"]})
    await db.drafts.delete_one({"_id": ObjectId(seed["draft_id"])})


@pytest.mark.asyncio
async def test_non_cap_league_returns_disabled_shape():
    from routes.draft_cap_view import get_draft_cap_status
    db = _db()
    s = await _seed(db, cap_enabled=False)
    _wire(s["admin_id"])
    try:
        r = await get_draft_cap_status(s["draft_id"], _StubReq())
        assert r["salary_cap_enabled"] is False
        assert r["teams"] == []
        assert r["default_rookie_aav"] > 0
    finally:
        await _cleanup(db, s)


@pytest.mark.asyncio
async def test_cap_league_sums_picks_and_computes_percent():
    from routes.draft_cap_view import get_draft_cap_status
    db = _db()
    s = await _seed(db, cap_enabled=True, cap=10_000_000)
    _wire(s["admin_id"])
    # Insert two players with distinct AAVs and two picks for team1.
    p1 = await db.players.insert_one({
        "name": "Superstar", "position": "C",
        "nhl_id": f"n62_p1_{ObjectId()}",
        "contract": {"aav": 8_000_000},
    })
    p2 = await db.players.insert_one({
        "name": "Vet Depth", "position": "D",
        "nhl_id": f"n62_p2_{ObjectId()}",
        "cap_hit": 1_500_000,
    })
    await db.draft_picks.insert_one({
        "draft_id": s["draft_id"], "pick_number": 1,
        "team_id": s["team1_id"], "player_id": str(p1.inserted_id),
    })
    await db.draft_picks.insert_one({
        "draft_id": s["draft_id"], "pick_number": 2,
        "team_id": s["team1_id"], "player_id": str(p2.inserted_id),
    })
    try:
        r = await get_draft_cap_status(s["draft_id"], _StubReq())
        assert r["salary_cap_enabled"] is True
        my_team = next(t for t in r["teams"] if t["team_id"] == s["team1_id"])
        assert my_team["salary_used"] == 9_500_000
        assert my_team["remaining"] == 500_000
        assert my_team["percent_used"] == 95.0
        assert my_team["approaching"] is True
        assert my_team["over_cap"] is False
        assert my_team["picks_count"] == 2

        other = next(t for t in r["teams"] if t["team_id"] == s["team2_id"])
        assert other["salary_used"] == 0
        assert other["approaching"] is False
        assert r["my_team_id"] == s["team1_id"]
    finally:
        await db.players.delete_many({
            "_id": {"$in": [p1.inserted_id, p2.inserted_id]},
        })
        await _cleanup(db, s)


@pytest.mark.asyncio
async def test_unpriced_player_uses_default_rookie_aav():
    from routes.draft_cap_view import get_draft_cap_status
    db = _db()
    s = await _seed(db, cap_enabled=True, cap=10_000_000,
                    default_rookie_aav=1_000_000)
    _wire(s["admin_id"])
    p = await db.players.insert_one({
        "name": "Unpriced Rookie", "position": "LW",
        "nhl_id": f"n62_unpriced_{ObjectId()}",
    })  # no contract / cap_hit / salary
    await db.draft_picks.insert_one({
        "draft_id": s["draft_id"], "pick_number": 1,
        "team_id": s["team1_id"], "player_id": str(p.inserted_id),
    })
    try:
        r = await get_draft_cap_status(s["draft_id"], _StubReq())
        my_team = next(t for t in r["teams"] if t["team_id"] == s["team1_id"])
        assert my_team["salary_used"] == 1_000_000
    finally:
        await db.players.delete_one({"_id": p.inserted_id})
        await _cleanup(db, s)


@pytest.mark.asyncio
async def test_over_cap_flag_when_used_exceeds_cap():
    from routes.draft_cap_view import get_draft_cap_status
    db = _db()
    s = await _seed(db, cap_enabled=True, cap=5_000_000)
    _wire(s["admin_id"])
    p = await db.players.insert_one({
        "name": "OverCapPlayer",
        "nhl_id": f"n62_over_{ObjectId()}",
        "contract": {"aav": 7_000_000},
    })
    await db.draft_picks.insert_one({
        "draft_id": s["draft_id"], "pick_number": 1,
        "team_id": s["team1_id"], "player_id": str(p.inserted_id),
    })
    try:
        r = await get_draft_cap_status(s["draft_id"], _StubReq())
        my = next(t for t in r["teams"] if t["team_id"] == s["team1_id"])
        assert my["over_cap"] is True
        assert my["remaining"] == -2_000_000
    finally:
        await db.players.delete_one({"_id": p.inserted_id})
        await _cleanup(db, s)


@pytest.mark.asyncio
async def test_unauthenticated_401():
    from routes.draft_cap_view import get_draft_cap_status
    from routes import draft_cap_view as m
    m._deps["db"] = _db()
    async def _no_user(_r):
        return None
    m._deps["get_current_user"] = _no_user
    with pytest.raises(HTTPException) as exc:
        await get_draft_cap_status("6a0000000000000000000000", _StubReq())
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_nonexistent_draft_404():
    from routes.draft_cap_view import get_draft_cap_status
    db = _db()
    s = await _seed(db, cap_enabled=True)
    _wire(s["admin_id"])
    try:
        with pytest.raises(HTTPException) as exc:
            await get_draft_cap_status("6b0000000000000000000000", _StubReq())
        assert exc.value.status_code == 404
    finally:
        await _cleanup(db, s)
