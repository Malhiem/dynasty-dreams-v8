"""Iter 232M.4 — Per-thread mute toggle.

Verifies:
- GET  /trades/{id}/thread/mute-state returns {muted: false} initially.
- POST /trades/{id}/thread/mute {muted: true} upserts a mute row.
- GET  /trades/{id}/thread/mute-state after mute returns {muted: true}
  when queried from ANY step in the same chain (the mute is keyed on
  thread_root_id, not on any specific step).
- POST /trades/{id}/thread/mute {muted: false} deletes the row.
- Fanout notifications skip muted users on subsequent responses.
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone

import pytest
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


@pytest.fixture()
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture()
async def db():
    client = AsyncIOMotorClient(os.environ.get("MONGO_URL"))
    db = client[os.environ.get("DB_NAME", "test_database")]
    yield db
    client.close()


class _FakeRequest:
    def __init__(self, body):
        self._body = body
    async def json(self):
        return self._body


@pytest.mark.asyncio
async def test_mute_toggle_persists_by_thread_root(db):
    from routes import trades as trades_router
    trades_router._deps["db"] = db

    # Seed a two-step counter chain so we can prove mute-by-root is
    # honoured no matter which step the user hits.
    league_id = str(ObjectId())
    root_id = ObjectId()
    counter_id = ObjectId()
    uid = f"iter232M4-u-{uuid.uuid4().hex[:6]}"
    now = datetime.now(timezone.utc).isoformat()
    await db.trades.insert_many([
        {"_id": root_id, "league_id": league_id,
         "proposer_id": "p", "target_owner_id": "t",
         "status": "countered", "submitted_at": now},
        {"_id": counter_id, "league_id": league_id,
         "counter_thread_root": str(root_id), "counter_depth": 1,
         "countered_from": str(root_id),
         "proposer_id": "t", "target_owner_id": "p",
         "status": "proposed", "submitted_at": now},
    ])

    async def _fake_user(request): return {"_id": uid, "email": "u@u"}
    trades_router._deps["get_current_user"] = _fake_user

    # Initial state — not muted.
    resp = await trades_router.get_thread_mute_state(str(root_id), _FakeRequest({}))
    assert resp == {"thread_root_id": str(root_id), "muted": False}

    # Mute via the counter step. Reads should show muted from BOTH steps.
    await trades_router.toggle_thread_mute(str(counter_id), _FakeRequest({"muted": True}))
    for step_id in (str(root_id), str(counter_id)):
        r = await trades_router.get_thread_mute_state(step_id, _FakeRequest({}))
        assert r["muted"] is True, f"mute not honoured when queried from {step_id}"
        assert r["thread_root_id"] == str(root_id)

    # Un-mute via the root step.
    await trades_router.toggle_thread_mute(str(root_id), _FakeRequest({"muted": False}))
    r = await trades_router.get_thread_mute_state(str(counter_id), _FakeRequest({}))
    assert r["muted"] is False

    # Cleanup
    await db.trades.delete_many({"_id": {"$in": [root_id, counter_id]}})
    await db.trade_thread_mutes.delete_many({"thread_root_id": str(root_id)})


@pytest.mark.asyncio
async def test_fanout_skips_muted_users(db):
    """A muted user should NOT receive a fanout notification on the next
    accept/reject/counter in the thread."""
    from routes import trades as trades_router

    league_id = str(ObjectId())
    proposer_tid = ObjectId()
    target_tid = ObjectId()
    proposer_uid = f"iter232M4-p-{uuid.uuid4().hex[:6]}"
    target_uid = f"iter232M4-t-{uuid.uuid4().hex[:6]}"
    bystander_uid = f"iter232M4-x-{uuid.uuid4().hex[:6]}"
    await db.leagues.insert_one({"_id": ObjectId(league_id), "trade_review_period_hours": 24})
    await db.teams.insert_many([
        {"_id": proposer_tid, "league_id": league_id, "owner_id": proposer_uid,
         "name": "P", "co_owner_ids": []},
        {"_id": target_tid, "league_id": league_id, "owner_id": target_uid,
         "name": "T", "co_owner_ids": []},
    ])
    root_id = ObjectId()
    now = datetime.now(timezone.utc).isoformat()
    await db.trades.insert_one({
        "_id": root_id, "league_id": league_id,
        "proposer_team_id": str(proposer_tid), "proposer_team_name": "P",
        "proposer_id": proposer_uid,
        "target_team_id": str(target_tid), "target_team_name": "T",
        "target_owner_id": target_uid,
        "assets_offered": [], "assets_requested": [],
        "status": "proposed", "submitted_at": now,
        "_review_period_hours": 24,
        "votes": {"approve": 0, "veto": 0, "voters": []},
    })
    # Synthetic bystander step to make the fanout non-trivial.
    await db.trades.insert_one({
        "_id": ObjectId(), "league_id": league_id,
        "counter_thread_root": str(root_id), "counter_depth": -1,
        "proposer_id": bystander_uid, "target_owner_id": bystander_uid,
        "status": "cancelled", "submitted_at": now,
    })

    # Bystander mutes the thread BEFORE the target acts.
    await db.trade_thread_mutes.insert_one({
        "thread_root_id": str(root_id), "user_id": bystander_uid,
        "muted_at": now,
    })

    # Wire deps + capture notifications.
    trades_router._deps["db"] = db
    async def _fake_target(request): return {"_id": target_uid, "email": "t@t"}
    trades_router._deps["get_current_user"] = _fake_target
    async def _noop(*a, **kw): return None
    trades_router._deps["broadcast_to_room"] = _noop
    notified: list = []
    async def _capture(user_id, kind, title, body, league_id, link):
        notified.append(user_id)
    trades_router._deps["create_notification"] = _capture

    # Target rejects — bystander should NOT be in the fanout recipients
    # because they muted; original proposer still gets their direct notify.
    await trades_router.respond_to_trade_proposal(
        str(root_id), _FakeRequest({"action": "reject", "reason": "pass"}),
    )
    assert proposer_uid in notified
    assert bystander_uid not in notified, f"muted bystander was notified: {notified}"

    # Cleanup
    await db.leagues.delete_one({"_id": ObjectId(league_id)})
    await db.teams.delete_many({"_id": {"$in": [proposer_tid, target_tid]}})
    await db.trades.delete_many({
        "$or": [{"_id": root_id}, {"counter_thread_root": str(root_id)}],
    })
    await db.trade_thread_mutes.delete_many({"thread_root_id": str(root_id)})
