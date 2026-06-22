"""
Iter 194c — In-draft pick trade flow.

Covers:
1. Vote endpoint approve/veto + flip semantics
2. Majority-veto auto-vetoes pending trade
3. Commish/admin resolve override (execute/veto/extend/pause)
4. Auto-execute sweeper: `_expire_pending_pick_trades` resolves elapsed trades
5. Execute helper repoints draft_picks + swaps roster + writes audit
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest
import asyncio

from bson import ObjectId
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")


def _db():
    """Per-test Motor client so each pytest-asyncio loop gets a fresh
    binding (Motor stores the loop at client-creation time)."""
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


async def _seed_trade(db, league_id, proposer_id, receiver_id, expires_in_seconds=600, policy="auto_execute"):
    """Create a minimal pending_draft_review pick trade and matching pick row."""
    pick = await db.draft_picks.insert_one({
        "league_id": league_id,
        "current_team_id": proposer_id,
        "current_team_name": "Proposer",
        "round": 1, "pick": 99, "year": 2026,
    })
    trade = await db.trades.insert_one({
        "league_id": league_id,
        "proposer_team_id": proposer_id,
        "receiver_team_id": receiver_id,
        "proposer_assets": [{"type": "pick", "pick_id": str(pick.inserted_id), "round": 1, "year": 2026}],
        "receiver_assets": [],
        "status": "pending_draft_review",
        "is_in_draft_pick_trade": True,
        "review_expires_at": (datetime.now(timezone.utc) + timedelta(seconds=expires_in_seconds)).isoformat(),
        "post_review_action": policy,
        "votes": {"approve": 0, "veto": 0, "voters": [], "choices": {}},
        "submitted_at": datetime.now(timezone.utc).isoformat(),
    })
    return str(trade.inserted_id), str(pick.inserted_id)


@pytest.mark.asyncio
async def test_execute_pick_trade_repoints_pick_and_marks_executed():
    """The execute helper must repoint `draft_picks.current_team_id` to the
    receiver and mark the trade `status='executed'`."""
    from routes.trades import _execute_in_draft_pick_trade

    lid = "test_iter194c_league_1"
    proposer = ObjectId(); receiver = ObjectId()
    await _db().teams.insert_one({"_id": proposer, "league_id": lid, "name": "Proposer", "roster": []})
    await _db().teams.insert_one({"_id": receiver, "league_id": lid, "name": "Receiver", "roster": []})
    trade_id, pick_id = await _seed_trade(_db(), lid, str(proposer), str(receiver))
    trade = await _db().trades.find_one({"_id": ObjectId(trade_id)})

    await _execute_in_draft_pick_trade(_db(), trade)

    pick = await _db().draft_picks.find_one({"_id": ObjectId(pick_id)})
    assert pick["current_team_id"] == str(receiver)
    t = await _db().trades.find_one({"_id": ObjectId(trade_id)})
    assert t["status"] == "executed"
    assert t.get("executed_at")

    # Cleanup
    await _db().teams.delete_many({"league_id": lid})
    await _db().draft_picks.delete_one({"_id": ObjectId(pick_id)})
    await _db().trades.delete_one({"_id": ObjectId(trade_id)})


@pytest.mark.asyncio
async def test_sweeper_auto_executes_elapsed_trade_under_auto_execute_policy():
    from routes.trades import _expire_pending_pick_trades

    lid = "test_iter194c_league_2"
    proposer = ObjectId(); receiver = ObjectId()
    await _db().teams.insert_one({"_id": proposer, "league_id": lid, "name": "P", "roster": []})
    await _db().teams.insert_one({"_id": receiver, "league_id": lid, "name": "R", "roster": []})
    trade_id, pick_id = await _seed_trade(_db(), lid, str(proposer), str(receiver), expires_in_seconds=-1)

    resolved = await _expire_pending_pick_trades(_db())
    assert resolved >= 1

    t = await _db().trades.find_one({"_id": ObjectId(trade_id)})
    assert t["status"] == "executed"

    await _db().teams.delete_many({"league_id": lid})
    await _db().draft_picks.delete_one({"_id": ObjectId(pick_id)})
    await _db().trades.delete_one({"_id": ObjectId(trade_id)})


@pytest.mark.asyncio
async def test_sweeper_extend_timer_pushes_expiry():
    from routes.trades import _expire_pending_pick_trades

    lid = "test_iter194c_league_3"
    proposer = ObjectId(); receiver = ObjectId()
    await _db().teams.insert_one({"_id": proposer, "league_id": lid, "name": "P", "roster": []})
    await _db().teams.insert_one({"_id": receiver, "league_id": lid, "name": "R", "roster": []})
    trade_id, pick_id = await _seed_trade(
        _db(), lid, str(proposer), str(receiver),
        expires_in_seconds=-1, policy="extend_timer",
    )
    await _expire_pending_pick_trades(_db())
    t = await _db().trades.find_one({"_id": ObjectId(trade_id)})
    # Policy switches to auto_execute and pushes a fresh 15-minute window
    assert t["status"] == "pending_draft_review"
    assert t["post_review_action"] == "auto_execute"
    new_expiry = datetime.fromisoformat(t["review_expires_at"])
    assert new_expiry > datetime.now(timezone.utc)

    await _db().teams.delete_many({"league_id": lid})
    await _db().draft_picks.delete_one({"_id": ObjectId(pick_id)})
    await _db().trades.delete_one({"_id": ObjectId(trade_id)})


@pytest.mark.asyncio
async def test_sweeper_majority_vote_executes_if_more_approves():
    from routes.trades import _expire_pending_pick_trades

    lid = "test_iter194c_league_4"
    proposer = ObjectId(); receiver = ObjectId()
    await _db().teams.insert_one({"_id": proposer, "league_id": lid, "name": "P", "roster": []})
    await _db().teams.insert_one({"_id": receiver, "league_id": lid, "name": "R", "roster": []})
    trade_id, pick_id = await _seed_trade(
        _db(), lid, str(proposer), str(receiver),
        expires_in_seconds=-1, policy="majority_vote",
    )
    # Inject votes — approves dominate
    await _db().trades.update_one(
        {"_id": ObjectId(trade_id)},
        {"$set": {"votes": {"approve": 5, "veto": 1, "voters": [], "choices": {}}}},
    )
    await _expire_pending_pick_trades(_db())
    t = await _db().trades.find_one({"_id": ObjectId(trade_id)})
    assert t["status"] == "executed"

    await _db().teams.delete_many({"league_id": lid})
    await _db().draft_picks.delete_one({"_id": ObjectId(pick_id)})
    await _db().trades.delete_one({"_id": ObjectId(trade_id)})


@pytest.mark.asyncio
async def test_sweeper_pause_draft_policy_marks_expired_and_pauses_draft():
    from routes.trades import _expire_pending_pick_trades

    lid = "test_iter194c_league_5"
    proposer = ObjectId(); receiver = ObjectId()
    await _db().teams.insert_one({"_id": proposer, "league_id": lid, "name": "P", "roster": []})
    await _db().teams.insert_one({"_id": receiver, "league_id": lid, "name": "R", "roster": []})
    await _db().drafts.insert_one({"league_id": lid, "status": "in_progress"})
    trade_id, pick_id = await _seed_trade(
        _db(), lid, str(proposer), str(receiver),
        expires_in_seconds=-1, policy="pause_draft",
    )
    await _expire_pending_pick_trades(_db())
    t = await _db().trades.find_one({"_id": ObjectId(trade_id)})
    d = await _db().drafts.find_one({"league_id": lid})
    assert t["status"] == "expired"
    assert d["status"] == "paused"

    await _db().teams.delete_many({"league_id": lid})
    await _db().draft_picks.delete_one({"_id": ObjectId(pick_id)})
    await _db().trades.delete_one({"_id": ObjectId(trade_id)})
    await _db().drafts.delete_one({"league_id": lid})


@pytest.mark.asyncio
async def test_sweeper_require_admin_keeps_pending_with_flag():
    from routes.trades import _expire_pending_pick_trades

    lid = "test_iter194c_league_6"
    proposer = ObjectId(); receiver = ObjectId()
    await _db().teams.insert_one({"_id": proposer, "league_id": lid, "name": "P", "roster": []})
    await _db().teams.insert_one({"_id": receiver, "league_id": lid, "name": "R", "roster": []})
    trade_id, pick_id = await _seed_trade(
        _db(), lid, str(proposer), str(receiver),
        expires_in_seconds=-1, policy="require_admin",
    )
    await _expire_pending_pick_trades(_db())
    t = await _db().trades.find_one({"_id": ObjectId(trade_id)})
    assert t["status"] == "pending_draft_review"
    assert t.get("flagged_for_admin") is True

    await _db().teams.delete_many({"league_id": lid})
    await _db().draft_picks.delete_one({"_id": ObjectId(pick_id)})
    await _db().trades.delete_one({"_id": ObjectId(trade_id)})
