"""Iter 232N.52 — Commissioner-overrides feed endpoint tests.

Covers `GET /api/leagues/{league_id}/commissioner-overrides`:

  1. Outsider (no team in league, not admin) rejected 403.
  2. Team owner (regular member) CAN read the feed — this is a
     transparency surface, not privileged.
  3. Platform admin CAN read on any league.
  4. Feed merges pick_undo (from `draft_undo_audit`) + owner_ping
     (from `commissioner_pings`) sorted by timestamp DESC.
  5. Undo event carries pick_number / player_name / cascade /
     on_the_clock_after in `detail`.
  6. Ping event carries target_name / target_team_name /
     channels_fired in `detail`.
  7. `limit` param bounds results (server-capped at 100).
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone, timedelta

import pytest
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _db():
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[
        os.environ.get("DB_NAME", os.environ["DB_NAME"])
    ]


def _wire_deps(db, caller):
    from routes import draft_ops as m
    m._deps.update({"db": db})

    async def _fake_get_user(_request):
        return caller
    m._deps["get_current_user"] = _fake_get_user


async def _seed_user(db, prefix, role="user"):
    uid = ObjectId()
    await db.users.insert_one({
        "_id": uid,
        "email": f"{prefix}_{str(uid)[:6]}@iter232n52.test",
        "name": f"iter232n52 {prefix}",
        "username": f"{prefix}_{str(uid)[:6]}",
        "role": role,
    })
    return str(uid)


async def _seed_league(db, commissioner_uid, member_uid=None):
    league_id = ObjectId()
    await db.leagues.insert_one({
        "_id": league_id,
        "name": "Iter232N52 league",
        "commissioner_id": commissioner_uid,
        "status": "active",
    })
    if member_uid:
        tid = ObjectId()
        await db.teams.insert_one({
            "_id": tid, "name": "member team",
            "league_id": str(league_id),
            "owner_id": member_uid,
            "co_owner_ids": [],
        })
    return str(league_id)


async def _cleanup(db, league_id, uids):
    await db.leagues.delete_one({"_id": ObjectId(league_id)})
    await db.teams.delete_many({"league_id": league_id})
    await db.draft_undo_audit.delete_many({"league_id": league_id})
    await db.commissioner_pings.delete_many({"league_id": league_id})
    await db.users.delete_many({"_id": {"$in": [ObjectId(u) for u in uids]}})


@pytest.mark.asyncio
async def test_overrides_rejects_outsider():
    from routes.draft_ops import list_commissioner_overrides
    from fastapi import HTTPException

    db = _db()
    commish = await _seed_user(db, "commish")
    league_id = await _seed_league(db, commish)
    outsider = await _seed_user(db, "outsider", role="user")
    _wire_deps(db, {"_id": outsider, "role": "user"})

    try:
        with pytest.raises(HTTPException) as exc:
            await list_commissioner_overrides(league_id, None, limit=30)
        assert exc.value.status_code == 403
    finally:
        await _cleanup(db, league_id, [commish, outsider])


@pytest.mark.asyncio
async def test_overrides_readable_by_team_owner():
    """Regular league members (team owners who aren't commissioners)
    can read the transparency feed."""
    from routes.draft_ops import list_commissioner_overrides

    db = _db()
    commish = await _seed_user(db, "commish")
    member = await _seed_user(db, "member")
    league_id = await _seed_league(db, commish, member_uid=member)
    _wire_deps(db, {"_id": member, "role": "user"})

    try:
        result = await list_commissioner_overrides(league_id, None, limit=30)
        assert result["league_id"] == league_id
        assert result["count"] == 0
        assert result["events"] == []
    finally:
        await _cleanup(db, league_id, [commish, member])


@pytest.mark.asyncio
async def test_overrides_merged_and_sorted():
    from routes.draft_ops import list_commissioner_overrides

    db = _db()
    commish = await _seed_user(db, "commish")
    target = await _seed_user(db, "target")
    league_id = await _seed_league(db, commish, member_uid=target)
    _wire_deps(db, {"_id": commish, "role": "user"})

    now = datetime.now(timezone.utc)
    # Seed a pick_undo (older)
    await db.draft_undo_audit.insert_one({
        "draft_id": "d1", "league_id": league_id,
        "pick_number": 5, "cascade": False, "removed_count": 1,
        "removed_picks": [{
            "overall": 5, "team": "AAA",
            "player": {"name": "Undone Player"},
        }],
        "commissioner_id": commish, "commissioner_name": "TheCommish",
        "reason": "misclick",
        "undone_at": (now - timedelta(minutes=10)).isoformat(),
        "on_the_clock_after": "AAA",
    })
    # Seed a ping (newer)
    await db.commissioner_pings.insert_one({
        "league_id": league_id, "draft_id": "d1",
        "commissioner_id": commish,
        "target_user_id": target, "target_team_name": "Their Team",
        "custom_message": "Come pick already",
        "channels_fired": ["in_app", "email", "socket"],
        "created_at": (now - timedelta(minutes=1)).isoformat(),
    })

    try:
        result = await list_commissioner_overrides(league_id, None, limit=30)
        assert result["count"] == 2
        assert result["events"][0]["type"] == "owner_ping"  # newer
        assert result["events"][1]["type"] == "pick_undo"

        ping = result["events"][0]
        assert ping["detail"]["target_team_name"] == "Their Team"
        assert set(ping["detail"]["channels_fired"]) == {"in_app", "email", "socket"}
        assert ping["reason"] == "Come pick already"
        assert ping["commissioner"]["id"] == commish

        undo = result["events"][1]
        assert undo["detail"]["pick_number"] == 5
        assert undo["detail"]["player_name"] == "Undone Player"
        assert undo["detail"]["cascade"] is False
        assert undo["detail"]["on_the_clock_after"] == "AAA"
        assert undo["reason"] == "misclick"
        assert undo["commissioner"]["name"] == "TheCommish"
    finally:
        await _cleanup(db, league_id, [commish, target])


@pytest.mark.asyncio
async def test_overrides_platform_admin_can_read_any_league():
    from routes.draft_ops import list_commissioner_overrides

    db = _db()
    commish = await _seed_user(db, "commish")
    admin = await _seed_user(db, "platform_admin", role="admin")
    league_id = await _seed_league(db, commish)
    _wire_deps(db, {"_id": admin, "role": "admin"})

    try:
        result = await list_commissioner_overrides(league_id, None, limit=30)
        assert result["league_id"] == league_id
    finally:
        await _cleanup(db, league_id, [commish, admin])


@pytest.mark.asyncio
async def test_overrides_limit_bounded():
    from routes.draft_ops import list_commissioner_overrides

    db = _db()
    commish = await _seed_user(db, "commish")
    league_id = await _seed_league(db, commish)
    _wire_deps(db, {"_id": commish, "role": "user"})

    now = datetime.now(timezone.utc)
    # 15 undo events
    for i in range(15):
        await db.draft_undo_audit.insert_one({
            "draft_id": "d1", "league_id": league_id,
            "pick_number": i + 1, "removed_count": 1, "cascade": False,
            "removed_picks": [{"overall": i + 1, "team": "AAA"}],
            "commissioner_id": commish, "commissioner_name": "TheCommish",
            "undone_at": (now - timedelta(seconds=i)).isoformat(),
        })

    try:
        result = await list_commissioner_overrides(league_id, None, limit=5)
        assert result["count"] == 5
        # Newest first — pick_number 1 was undone MOST recently by our
        # seed (smallest delta from now).
        assert result["events"][0]["detail"]["pick_number"] == 1
    finally:
        await _cleanup(db, league_id, [commish])
