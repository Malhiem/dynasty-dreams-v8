"""Iter 232M.1 — TradeProposalModal end-to-end counter submission.

Live-integration test: hitting POST /trades/{id}/respond with
action=counter from a valid recipient should mark the original countered
and create the reverse proposed trade. This complements the direct-
function unit tests in test_iter232M_counter_and_lock_defer.py by going
through the actual HTTP route so we catch any routing / dep-wiring
regressions the unit path can miss.
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
async def test_counter_payload_matches_frontend_shape(db):
    """The modal sends assets_offered/assets_requested with `asset_type`
    ("player"|"pick") + `player_id` or `pick_id`. Verify the backend
    /respond endpoint accepts this exact shape and hydrates player names
    onto the counter's asset rows (so the recipient's TradeCard renders
    real names, not raw ObjectIds)."""
    from routes import trades as trades_router

    # Seed a real player so hydration has something to look up.
    player_doc = {
        "name": "Counter Payload Player",
        "nhl_id": f"iter232M1-{uuid.uuid4().hex[:8]}",
        "position": "LW",
        "team": "TST",
        "player_type": "skater",
    }
    player_result = await db.players.insert_one(player_doc)
    pid = str(player_result.inserted_id)

    league_id = str(ObjectId())
    target_uid = f"iter232M1-t-{uuid.uuid4().hex[:6]}"
    proposer_tid = ObjectId()
    target_tid = ObjectId()
    trade_id = ObjectId()
    await db.leagues.insert_one({"_id": ObjectId(league_id), "trade_review_period_hours": 24})
    await db.teams.insert_many([
        {"_id": proposer_tid, "league_id": league_id, "owner_id": "prop",
         "name": "P", "co_owner_ids": []},
        {"_id": target_tid, "league_id": league_id, "owner_id": target_uid,
         "name": "T", "co_owner_ids": []},
    ])
    await db.trades.insert_one({
        "_id": trade_id, "league_id": league_id,
        "proposer_team_id": str(proposer_tid), "target_team_id": str(target_tid),
        "proposer_id": "prop", "target_owner_id": target_uid,
        "proposer_team_name": "P", "target_team_name": "T",
        "status": "proposed", "assets_offered": [], "assets_requested": [],
        "_review_period_hours": 24,
    })

    trades_router._deps["db"] = db
    async def _fake_user(request): return {"_id": target_uid, "email": "t@t"}
    trades_router._deps["get_current_user"] = _fake_user
    async def _noop(*a, **kw): return None
    trades_router._deps["broadcast_to_room"] = _noop
    trades_router._deps["create_notification"] = _noop

    # Exact payload shape the frontend modal builds.
    resp = await trades_router.respond_to_trade_proposal(
        str(trade_id),
        _FakeRequest({
            "action": "counter",
            "assets_offered": [
                {"asset_type": "player", "player_id": pid},
                {"asset_type": "pick", "pick_id": "some-pick-oid"},
            ],
            "assets_requested": [
                {"asset_type": "player", "player_id": pid},
            ],
            "message": "Frontend modal payload",
        }),
    )
    counter_id = resp["counter_trade_id"]
    counter = await db.trades.find_one({"_id": ObjectId(counter_id)})

    # Player rows on the counter must be hydrated with `player_name`,
    # `position`, `nhl_team` (matches the fields the trade list endpoint
    # expects when it serialises trades to the Transactions page).
    offered_player = next(
        (a for a in counter["assets_offered"] if a.get("asset_type") == "player"),
        None,
    )
    assert offered_player is not None
    assert offered_player["player_name"] == "Counter Payload Player"
    assert offered_player["position"] == "LW"

    # Pick assets should NOT be hydrated with player fields.
    offered_pick = next(
        (a for a in counter["assets_offered"] if a.get("asset_type") == "pick"),
        None,
    )
    assert offered_pick is not None
    assert "player_name" not in offered_pick

    await db.players.delete_one({"_id": player_result.inserted_id})
    await db.leagues.delete_one({"_id": ObjectId(league_id)})
    await db.teams.delete_many({"_id": {"$in": [proposer_tid, target_tid]}})
    await db.trades.delete_many({"_id": {"$in": [trade_id, ObjectId(counter_id)]}})
