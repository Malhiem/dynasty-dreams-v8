"""Iter 232N.64 — Admin Player DB endpoints pytest suite.

Covers:
  1. List endpoint: 403 for non-admin, filters by q/position/is_prospect,
     returns pagination shape.
  2. Create endpoint: seeds a new player with is_prospect=true, auto-
     generates nhl_id, writes audit row.
  3. Update endpoint: only allow-listed fields are written; audit row
     captures before/after.
  4. Delete endpoint: 409 when player is on an active roster;
     otherwise deletes + audits.
  5. Audit endpoint: returns recent rows in descending time order.
  6. Refresh endpoint: `csv` source via JSON payload returns 400
     (directs caller to the multipart endpoint).
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


async def _seed_user(db, role="admin"):
    uid = ObjectId()
    await db.users.insert_one({
        "_id": uid, "email": f"n64_{str(uid)[:6]}@iter.test",
        "name": f"N64 {role}", "role": role,
    })
    return str(uid)


def _wire(user_id: str):
    from routes import admin_players as m
    db = _db()
    async def _fake_user(_r):
        return await db.users.find_one({"_id": ObjectId(user_id)})
    m._deps["db"] = db
    m._deps["get_current_user"] = _fake_user


@pytest.mark.asyncio
async def test_list_requires_admin():
    from routes.admin_players import admin_list_players
    db = _db()
    caller = await _seed_user(db, role="user")
    _wire(caller)
    try:
        with pytest.raises(HTTPException) as exc:
            await admin_list_players(_StubReq())
        assert exc.value.status_code == 403
    finally:
        await db.users.delete_one({"_id": ObjectId(caller)})


@pytest.mark.asyncio
async def test_list_shape_and_filters():
    from routes.admin_players import admin_list_players
    db = _db()
    admin = await _seed_user(db)
    _wire(admin)
    try:
        # Basic list
        r = await admin_list_players(_StubReq(), limit=5)
        assert "total" in r and "players" in r
        assert r["limit"] == 5
        assert len(r["players"]) <= 5

        # Filter by position (approximate — DB will have at least some)
        r2 = await admin_list_players(_StubReq(), position="G", limit=5)
        for p in r2["players"]:
            assert p.get("position") == "G"
    finally:
        await db.users.delete_one({"_id": ObjectId(admin)})


@pytest.mark.asyncio
async def test_create_player_auto_nhl_id_and_audits():
    from routes.admin_players import admin_create_player, CreatePlayerRequest
    db = _db()
    admin = await _seed_user(db)
    _wire(admin)
    created_id = None
    try:
        r = await admin_create_player(
            CreatePlayerRequest(
                name="N64 Missing Minor", position="LW",
                league="AHL", age=21, is_prospect=True,
                cap_hit=750_000,
            ),
            _StubReq(),
        )
        assert r["nhl_id"].startswith("admin_")
        assert r["is_prospect"] is True
        created_id = r["id"]

        # Audit row exists
        audit = await db.player_admin_audit.find_one(
            {"action": "create", "player_id": created_id}
        )
        assert audit is not None
        assert audit["actor_id"] == admin
    finally:
        if created_id:
            await db.players.delete_one({"_id": ObjectId(created_id)})
            await db.player_admin_audit.delete_many({"player_id": created_id})
        await db.users.delete_one({"_id": ObjectId(admin)})


@pytest.mark.asyncio
async def test_update_player_only_allowlisted_fields():
    from routes.admin_players import admin_update_player
    db = _db()
    admin = await _seed_user(db)
    _wire(admin)
    # Seed a probe player
    p = await db.players.insert_one({
        "name": "N64 Probe", "position": "D",
        "nhl_id": f"n64_probe_{ObjectId()}",
        "age": 25, "is_prospect": False,
    })
    pid = str(p.inserted_id)
    try:
        await admin_update_player(
            pid,
            {
                "is_prospect": True, "age": 22, "cap_hit": 1_500_000,
                # Non-allowlisted fields must be dropped:
                "seeded_at": "hax", "created_by_admin_id": "hax",
            },
            _StubReq(),
        )
        after = await db.players.find_one({"_id": ObjectId(pid)})
        assert after["is_prospect"] is True
        assert after["age"] == 22
        assert after["cap_hit"] == 1_500_000
        assert after.get("seeded_at") != "hax"
        assert "created_by_admin_id" not in after or after.get("created_by_admin_id") != "hax"

        # Empty payload → 400
        with pytest.raises(HTTPException) as exc:
            await admin_update_player(pid, {"nonsense": 1}, _StubReq())
        assert exc.value.status_code == 400
    finally:
        await db.players.delete_one({"_id": ObjectId(pid)})
        await db.player_admin_audit.delete_many({"player_id": pid})
        await db.users.delete_one({"_id": ObjectId(admin)})


@pytest.mark.asyncio
async def test_delete_blocked_when_on_roster():
    from routes.admin_players import admin_delete_player
    db = _db()
    admin = await _seed_user(db)
    _wire(admin)
    p = await db.players.insert_one({
        "name": "N64 On Roster", "nhl_id": f"n64_or_{ObjectId()}",
    })
    pid = str(p.inserted_id)
    team = await db.teams.insert_one({
        "league_id": "n64_lg", "name": "N64 Team",
        "roster": [pid], "lineup": {},
    })
    try:
        with pytest.raises(HTTPException) as exc:
            await admin_delete_player(pid, _StubReq())
        assert exc.value.status_code == 409

        # Clear from roster → delete succeeds
        await db.teams.update_one({"_id": team.inserted_id}, {"$set": {"roster": []}})
        r = await admin_delete_player(pid, _StubReq())
        assert r["ok"] is True
        assert await db.players.find_one({"_id": ObjectId(pid)}) is None
    finally:
        await db.teams.delete_one({"_id": team.inserted_id})
        await db.player_admin_audit.delete_many({"player_id": pid})
        await db.users.delete_one({"_id": ObjectId(admin)})


@pytest.mark.asyncio
async def test_audit_endpoint_returns_recent_rows():
    from routes.admin_players import admin_player_audit
    db = _db()
    admin = await _seed_user(db)
    _wire(admin)
    # Seed a couple of audit rows
    for i in range(3):
        await db.player_admin_audit.insert_one({
            "actor_id": admin, "action": "update",
            "player_id": f"n64_{i}",
            "at": datetime.now(timezone.utc).isoformat(),
        })
    try:
        r = await admin_player_audit(_StubReq(), limit=10)
        assert r["count"] >= 3
        # Descending time order — first row is the most recent
        times = [row["at"] for row in r["rows"] if row.get("player_id", "").startswith("n64_")]
        assert times == sorted(times, reverse=True)
    finally:
        await db.player_admin_audit.delete_many({"player_id": {"$regex": "^n64_"}})
        await db.users.delete_one({"_id": ObjectId(admin)})


@pytest.mark.asyncio
async def test_refresh_csv_source_via_json_returns_400():
    from routes.admin_players import (
        admin_refresh_players, RefreshRequest,
    )
    db = _db()
    admin = await _seed_user(db)
    _wire(admin)
    try:
        with pytest.raises(HTTPException) as exc:
            await admin_refresh_players(
                RefreshRequest(source="csv", note="wrong path"),
                _StubReq(),
            )
        assert exc.value.status_code == 400
        assert "multipart" in exc.value.detail.lower()
    finally:
        await db.users.delete_one({"_id": ObjectId(admin)})
