"""Iter 232M.2 — GET /trades/{id}/thread returns the full counter chain
in depth order, keyed by counter_thread_root.
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


async def _seed_counter_chain(db, league_id, proposer_tid, target_tid, proposer_uid, target_uid):
    """Create Root → Counter #1 → Counter #2 through the real /respond
    endpoint so `counter_thread_root` and `counter_depth` get stamped by
    the same code the frontend hits."""
    from routes import trades as trades_router

    now = datetime.now(timezone.utc).isoformat()
    root_id = ObjectId()
    await db.trades.insert_one({
        "_id": root_id, "league_id": league_id,
        "proposer_team_id": str(proposer_tid),
        "proposer_team_name": "P", "proposer_id": proposer_uid,
        "target_team_id": str(target_tid),
        "target_team_name": "T", "target_owner_id": target_uid,
        "assets_offered": [], "assets_requested": [],
        "status": "proposed",
        "votes": {"approve": 0, "veto": 0, "voters": []},
        "submitted_at": now,
        "_review_period_hours": 24,
    })

    # ── Target counters (Counter #1)
    async def _fake_target(request): return {"_id": target_uid, "email": "t@t"}
    async def _fake_proposer(request): return {"_id": proposer_uid, "email": "p@p"}
    async def _noop(*a, **kw): return None

    trades_router._deps["db"] = db
    trades_router._deps["get_current_user"] = _fake_target
    trades_router._deps["broadcast_to_room"] = _noop
    trades_router._deps["create_notification"] = _noop

    r1 = await trades_router.respond_to_trade_proposal(
        str(root_id),
        _FakeRequest({"action": "counter",
                      "assets_offered": [{"asset_type": "pick", "pick_year": 2027, "pick_round": 3}],
                      "assets_requested": [{"asset_type": "pick", "pick_year": 2028, "pick_round": 2}]}),
    )
    counter1_id = r1["counter_trade_id"]

    # ── Original proposer counters back (Counter #2)
    trades_router._deps["get_current_user"] = _fake_proposer
    r2 = await trades_router.respond_to_trade_proposal(
        counter1_id,
        _FakeRequest({"action": "counter",
                      "assets_offered": [{"asset_type": "pick", "pick_year": 2027, "pick_round": 1}],
                      "assets_requested": [{"asset_type": "pick", "pick_year": 2028, "pick_round": 1}]}),
    )
    counter2_id = r2["counter_trade_id"]
    return str(root_id), counter1_id, counter2_id


@pytest.mark.asyncio
async def test_thread_returns_full_chain_in_depth_order(db):
    from routes import trades as trades_router

    league_id = str(ObjectId())
    proposer_tid = ObjectId()
    target_tid = ObjectId()
    proposer_uid = f"iter232M2-p-{uuid.uuid4().hex[:6]}"
    target_uid = f"iter232M2-t-{uuid.uuid4().hex[:6]}"
    await db.leagues.insert_one({"_id": ObjectId(league_id), "trade_review_period_hours": 24})
    await db.teams.insert_many([
        {"_id": proposer_tid, "league_id": league_id, "owner_id": proposer_uid,
         "name": "P", "co_owner_ids": []},
        {"_id": target_tid, "league_id": league_id, "owner_id": target_uid,
         "name": "T", "co_owner_ids": []},
    ])

    root_id, counter1_id, counter2_id = await _seed_counter_chain(
        db, league_id, proposer_tid, target_tid, proposer_uid, target_uid,
    )

    # Fetching /thread from ANY step should return the same 3-entry chain.
    for entry_id in (root_id, counter1_id, counter2_id):
        result = await trades_router.get_trade_thread(entry_id)
        assert result["root_id"] == root_id
        assert result["count"] == 3
        depths = [s["counter_depth"] for s in result["thread"]]
        assert depths == [0, 1, 2], f"depths not sorted: {depths} (queried from {entry_id})"
        # Root doc: proposer P → target T
        assert result["thread"][0]["id"] == root_id
        assert result["thread"][0]["proposer_team_name"] == "P"
        assert result["thread"][0]["target_team_name"] == "T"
        # Counter #1: target countered → proposer/target swapped
        assert result["thread"][1]["id"] == counter1_id
        assert result["thread"][1]["proposer_team_name"] == "T"
        assert result["thread"][1]["target_team_name"] == "P"
        # Counter #2: original proposer countered back → swapped again
        assert result["thread"][2]["id"] == counter2_id
        assert result["thread"][2]["proposer_team_name"] == "P"
        # The root's status should be countered now (superseded).
        assert result["thread"][0]["status"] == "countered"
        assert result["thread"][1]["status"] == "countered"
        # Newest one still open.
        assert result["thread"][2]["status"] == "proposed"

    # Cleanup
    await db.leagues.delete_one({"_id": ObjectId(league_id)})
    await db.teams.delete_many({"_id": {"$in": [proposer_tid, target_tid]}})
    await db.trades.delete_many({
        "_id": {"$in": [ObjectId(root_id), ObjectId(counter1_id), ObjectId(counter2_id)]},
    })


@pytest.mark.asyncio
async def test_thread_for_uncontested_trade_returns_single_entry(db):
    from routes import trades as trades_router
    trades_router._deps["db"] = db

    league_id = str(ObjectId())
    proposer_tid = ObjectId()
    target_tid = ObjectId()
    trade_id = ObjectId()
    await db.leagues.insert_one({"_id": ObjectId(league_id)})
    await db.teams.insert_many([
        {"_id": proposer_tid, "league_id": league_id, "owner_id": "p", "name": "P", "co_owner_ids": []},
        {"_id": target_tid, "league_id": league_id, "owner_id": "t", "name": "T", "co_owner_ids": []},
    ])
    await db.trades.insert_one({
        "_id": trade_id, "league_id": league_id,
        "proposer_team_id": str(proposer_tid), "target_team_id": str(target_tid),
        "proposer_team_name": "P", "target_team_name": "T",
        "proposer_id": "p", "target_owner_id": "t",
        "status": "proposed",
    })

    result = await trades_router.get_trade_thread(str(trade_id))
    assert result["count"] == 1
    assert result["root_id"] == str(trade_id)
    assert result["thread"][0]["counter_depth"] == 0

    await db.leagues.delete_one({"_id": ObjectId(league_id)})
    await db.teams.delete_many({"_id": {"$in": [proposer_tid, target_tid]}})
    await db.trades.delete_one({"_id": trade_id})
