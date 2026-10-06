"""Iter 232M — Counter offers + lock-aware trade execution.

Covers:
- respond_to_trade_proposal(action="counter") creates a new proposed
  trade going the other way, marks the original `countered`, and stamps
  `countered_by_trade_id` / `countered_from` / `counter_thread_root`.
- _execute_trade defers when the league lineup lock is currently active
  and stamps `defer_reason=matchup_locked` + `defer_next_unlock`.
- _execute_trade clears the defer flags on the next successful run
  after the lock lifts.
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone, timedelta

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
    db = client[os.environ.get("DB_NAME", os.environ["DB_NAME"])]
    yield db
    client.close()


class _FakeRequest:
    """Minimal Request stand-in — the endpoint only calls `await request.json()`."""
    def __init__(self, body):
        self._body = body
    async def json(self):
        return self._body


# ─── (b) Defer during matchup lock ──────────────────────────────
@pytest.mark.asyncio
async def test_execute_trade_defers_when_lineup_locked(monkeypatch, db):
    from services import trade_engine
    trade_engine._deps["db"] = db

    league_id = str(ObjectId())
    await db.leagues.insert_one({
        "_id": ObjectId(league_id), "name": "iter232M lock",
        "roster_lock_type": "daily", "lineup_lock_minutes_before": 30,
    })
    trade_doc = {
        "_id": ObjectId(), "league_id": league_id,
        "proposer_team_id": str(ObjectId()), "target_team_id": str(ObjectId()),
        "status": "pending",
    }
    await db.trades.insert_one(trade_doc)

    from utils import lineup_lock as ll_mod
    monkeypatch.setattr(
        ll_mod, "evaluate_lineup_lock",
        lambda league, **kw: {
            "locked": True,
            "next_unlock_iso": (datetime.now(timezone.utc) + timedelta(hours=6)).isoformat(),
            "reason": "test",
        },
    )
    result = await trade_engine._execute_trade(trade_doc)
    assert result["executed"] is False
    assert result["deferred"] is True
    assert result["reason"] == "matchup_locked"

    stored = await db.trades.find_one({"_id": trade_doc["_id"]})
    assert stored["defer_reason"] == "matchup_locked"
    assert stored.get("defer_next_unlock")

    await db.leagues.delete_one({"_id": ObjectId(league_id)})
    await db.trades.delete_one({"_id": trade_doc["_id"]})


@pytest.mark.asyncio
async def test_execute_trade_clears_defer_when_lock_lifts(monkeypatch, db):
    from services import trade_engine
    trade_engine._deps["db"] = db

    league_id = str(ObjectId())
    await db.leagues.insert_one({"_id": ObjectId(league_id), "name": "iter232M clear"})
    trade_doc = {
        "_id": ObjectId(), "league_id": league_id,
        "proposer_team_id": str(ObjectId()), "target_team_id": str(ObjectId()),
        "status": "pending",
        "defer_reason": "matchup_locked",
        "defer_next_unlock": "2026-03-01T00:00:00+00:00",
    }
    await db.trades.insert_one(trade_doc)

    from utils import lineup_lock as ll_mod
    monkeypatch.setattr(ll_mod, "evaluate_lineup_lock", lambda league, **kw: {"locked": False})

    try:
        await trade_engine._execute_trade(trade_doc)
    except Exception:
        pass  # Rosters are invalid; we only care about the defer-clear.
    stored = await db.trades.find_one({"_id": trade_doc["_id"]})
    assert "defer_reason" not in stored
    assert "defer_next_unlock" not in stored

    await db.leagues.delete_one({"_id": ObjectId(league_id)})
    await db.trades.delete_one({"_id": trade_doc["_id"]})


# ─── (a) Counter action creates a linked reverse proposal ──────
@pytest.mark.asyncio
async def test_counter_action_creates_reverse_proposal(db):
    from routes import trades as trades_router

    league_id = str(ObjectId())
    proposer_uid = f"iter232M-p-{uuid.uuid4().hex[:6]}"
    target_uid = f"iter232M-t-{uuid.uuid4().hex[:6]}"
    proposer_tid = ObjectId()
    target_tid = ObjectId()
    await db.leagues.insert_one({"_id": ObjectId(league_id), "trade_review_period_hours": 24})
    await db.teams.insert_many([
        {"_id": proposer_tid, "league_id": league_id, "owner_id": proposer_uid,
         "name": "Prop Team", "co_owner_ids": []},
        {"_id": target_tid, "league_id": league_id, "owner_id": target_uid,
         "name": "Targ Team", "co_owner_ids": []},
    ])
    trade_id = ObjectId()
    await db.trades.insert_one({
        "_id": trade_id, "league_id": league_id,
        "proposer_team_id": str(proposer_tid), "proposer_team_name": "Prop Team",
        "proposer_id": proposer_uid,
        "target_team_id": str(target_tid), "target_team_name": "Targ Team",
        "target_owner_id": target_uid,
        "assets_offered": [], "assets_requested": [],
        "status": "proposed",
        "votes": {"approve": 0, "veto": 0, "voters": []},
        "submitted_at": datetime.now(timezone.utc).isoformat(),
        "_review_period_hours": 24,
    })

    trades_router._deps["db"] = db
    async def _fake_user(request): return {"_id": target_uid, "email": "t@t"}
    trades_router._deps["get_current_user"] = _fake_user
    async def _noop(*a, **kw): return None
    trades_router._deps["broadcast_to_room"] = _noop
    trades_router._deps["create_notification"] = _noop

    resp = await trades_router.respond_to_trade_proposal(
        str(trade_id),
        _FakeRequest({
            "action": "counter",
            "assets_offered": [{"asset_type": "pick", "pick_year": 2027, "pick_round": 2}],
            "assets_requested": [{"asset_type": "pick", "pick_year": 2028, "pick_round": 1}],
            "message": "How about this instead?",
        }),
    )
    assert resp["status"] == "countered"
    counter_id = resp["counter_trade_id"]

    original = await db.trades.find_one({"_id": trade_id})
    assert original["status"] == "countered"
    assert original["countered_by_trade_id"] == counter_id

    counter = await db.trades.find_one({"_id": ObjectId(counter_id)})
    assert counter["status"] == "proposed"
    assert counter["countered_from"] == str(trade_id)
    assert counter["counter_thread_root"] == str(trade_id)
    assert counter["counter_depth"] == 1
    assert counter["proposer_team_id"] == str(target_tid)
    assert counter["target_team_id"] == str(proposer_tid)
    assert counter["message"] == "How about this instead?"

    await db.leagues.delete_one({"_id": ObjectId(league_id)})
    await db.teams.delete_many({"_id": {"$in": [proposer_tid, target_tid]}})
    await db.trades.delete_many({"_id": {"$in": [trade_id, ObjectId(counter_id)]}})


@pytest.mark.asyncio
async def test_counter_requires_at_least_one_asset(db):
    from fastapi import HTTPException
    from routes import trades as trades_router

    league_id = str(ObjectId())
    proposer_tid = ObjectId()
    target_tid = ObjectId()
    target_uid = f"iter232M-eu-{uuid.uuid4().hex[:6]}"
    await db.leagues.insert_one({"_id": ObjectId(league_id), "trade_review_period_hours": 24})
    await db.teams.insert_many([
        {"_id": proposer_tid, "league_id": league_id, "owner_id": "prop", "name": "P", "co_owner_ids": []},
        {"_id": target_tid, "league_id": league_id, "owner_id": target_uid, "name": "T", "co_owner_ids": []},
    ])
    trade_id = ObjectId()
    await db.trades.insert_one({
        "_id": trade_id, "league_id": league_id,
        "proposer_team_id": str(proposer_tid), "target_team_id": str(target_tid),
        "proposer_id": "prop", "target_owner_id": target_uid,
        "status": "proposed", "assets_offered": [], "assets_requested": [],
        "_review_period_hours": 24,
    })
    trades_router._deps["db"] = db
    async def _fake_user2(request): return {"_id": target_uid, "email": "t@t"}
    trades_router._deps["get_current_user"] = _fake_user2
    async def _noop(*a, **kw): return None
    trades_router._deps["broadcast_to_room"] = _noop
    trades_router._deps["create_notification"] = _noop

    with pytest.raises(HTTPException) as excinfo:
        await trades_router.respond_to_trade_proposal(
            str(trade_id),
            _FakeRequest({"action": "counter", "assets_offered": [], "assets_requested": []}),
        )
    assert excinfo.value.status_code == 400
    assert "at least one" in excinfo.value.detail.lower()

    await db.leagues.delete_one({"_id": ObjectId(league_id)})
    await db.teams.delete_many({"_id": {"$in": [proposer_tid, target_tid]}})
    await db.trades.delete_one({"_id": trade_id})
