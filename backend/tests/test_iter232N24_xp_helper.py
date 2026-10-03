"""Iter 232N.24 — XP toast helper + level snapshot correctness."""
from __future__ import annotations

import os
import pytest
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId

from utils.xp import level_from_xp, compute_user_xp, emit_xp_gain, XP_DELTAS


@pytest.fixture
async def db():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    d = client[os.environ.get("DB_NAME", "dynasty_dreams")]
    yield d
    client.close()


def test_level_from_xp_bench_warmer():
    """0-149 XP → level 1 (Bench Warmer)."""
    snap = level_from_xp(0)
    assert snap["level"] == 1
    assert snap["title"] == "Bench Warmer"
    assert snap["xp_in_level"] == 0
    assert snap["xp_required_for_next"] == 150

    snap = level_from_xp(149)
    assert snap["level"] == 1
    assert snap["xp_in_level"] == 149


def test_level_from_xp_ramp_up():
    """XP accumulates → level rises → title flips at cutoffs."""
    # Level 1 costs 150, Level 2 costs 200, Level 3 costs 250 …
    # 150+200 = 350 XP → exactly at start of level 3
    snap = level_from_xp(350)
    assert snap["level"] == 3
    assert snap["xp_in_level"] == 0
    assert snap["title"] == "Bench Warmer"  # levels 1-5


def test_level_from_xp_level_6_flip_title():
    """Level 6 → title flips to Rink Regular."""
    # sum(100+lvl*50 for lvl in 1..5) = 150+200+250+300+350 = 1250
    snap = level_from_xp(1250)
    assert snap["level"] == 6
    assert snap["title"] == "Rink Regular"


def test_xp_deltas_locked_to_users_formula():
    """XP_DELTAS must match the per-action multipliers in users.py."""
    assert XP_DELTAS["trade_accepted"] == 25
    assert XP_DELTAS["matchup_won"] == 20
    assert XP_DELTAS["waiver_claim_won"] == 5
    assert XP_DELTAS["draft_completed"] == 40


@pytest.mark.asyncio
async def test_emit_xp_gain_broadcasts_to_user_room(db):
    """emit_xp_gain calls broadcast_fn with user room + xp_awarded event."""
    calls = []

    async def fake_broadcast(room, event, payload):
        calls.append((room, event, payload))

    # Seed a real user + team so compute_user_xp doesn't zero out
    uid = ObjectId()
    tid = ObjectId()
    await db.users.insert_one({"_id": uid, "email": f"xp_{uid}@test.local"})
    await db.teams.insert_one({
        "_id": tid, "owner_id": uid, "wins": 3,
        "points_for": 100.0, "live_points": 0.0,
    })

    try:
        payload = await emit_xp_gain(
            db, uid,
            source="trade_accepted",
            broadcast_fn=fake_broadcast,
            meta={"trade_id": "abc"},
        )
        assert payload is not None
        assert payload["delta"] == 25  # trade_accepted default
        assert payload["source"] == "trade_accepted"
        assert payload["meta"] == {"trade_id": "abc"}
        assert payload["level"] >= 1
        assert "title" in payload
        assert "xp_to_next_level" in payload
        assert len(calls) == 1
        room, event, sent = calls[0]
        assert room == f"user_{uid}"
        assert event == "xp_awarded"
        assert sent["delta"] == 25
    finally:
        await db.users.delete_one({"_id": uid})
        await db.teams.delete_one({"_id": tid})


@pytest.mark.asyncio
async def test_emit_xp_gain_no_broadcast_when_fn_missing(db):
    """No broadcast_fn → return None + never raises."""
    uid = ObjectId()
    result = await emit_xp_gain(
        db, uid, source="trade_accepted", broadcast_fn=None,
    )
    assert result is None


@pytest.mark.asyncio
async def test_emit_xp_gain_skips_zero_delta(db):
    """Unknown source with no explicit delta → skip broadcast."""
    calls = []

    async def fake_broadcast(*args):
        calls.append(args)

    uid = ObjectId()
    result = await emit_xp_gain(
        db, uid, source="unknown_source", broadcast_fn=fake_broadcast,
    )
    assert result is None
    assert calls == []


@pytest.mark.asyncio
async def test_compute_user_xp_zero_for_empty_user(db):
    """User with no teams / trades / drafts / claims returns 0 XP."""
    uid = ObjectId()
    xp = await compute_user_xp(db, uid)
    assert xp == 0
