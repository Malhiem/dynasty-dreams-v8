"""Iter 88 — Trade execution clears trade-block entries for the traded players.

Listing a player on the trade block expresses intent to shop them. Once the
deal closes, the listing is stale — the player is no longer on the original
team and the receiving team hasn't explicitly opted in to shop them. We
verify the two-team `_execute_trade` path here; the multi-party path uses the
same `db.trade_block.delete_many` so it's covered by inspection.
"""
import os
import sys

import pytest
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _env(key):
    p = os.path.join(os.path.dirname(__file__), "..", ".env")
    with open(p) as f:
        for line in f:
            line = line.strip()
            if line.startswith(f"{key}="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")


LID = "69e46af167999bfb85c39628"


@pytest.mark.asyncio
async def test_executed_trade_clears_trade_block_for_traded_players():
    mongo = AsyncIOMotorClient(_env("MONGO_URL"))
    db = mongo[_env("DB_NAME")]
    try:
        # ── Setup: pick two teams in the league that each have ≥1 roster
        # player, seed a trade-block listing for the first player from each
        # side, and assemble a trade swap.
        teams = await db.teams.find({"league_id": LID}).to_list(20)
        teams = [t for t in teams if (t.get("roster") or [])]
        if len(teams) < 2:
            pytest.skip("Not enough seeded teams with rosters")
        a, b = teams[0], teams[1]
        a_pid = a["roster"][0]
        b_pid = b["roster"][0]

        # Seed listings
        await db.trade_block.delete_many({
            "league_id": LID,
            "player_id": {"$in": [a_pid, b_pid]},
        })
        await db.trade_block.insert_many([
            {
                "item_type": "player", "looking_for": ["Best Offer"], "created_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
                "owner_id": a.get("owner_id") or "_", "owner_name": "owner_a",
                "league_id": LID, "team_id": str(a["_id"]),
                "player_id": a_pid, "name": "Test A", "position": "C",
            },
            {
                "item_type": "player", "looking_for": ["Best Offer"], "created_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
                "owner_id": b.get("owner_id") or "_", "owner_name": "owner_b",
                "league_id": LID, "team_id": str(b["_id"]),
                "player_id": b_pid, "name": "Test B", "position": "RW",
            },
        ])
        before = await db.trade_block.count_documents({
            "league_id": LID, "player_id": {"$in": [a_pid, b_pid]},
        })
        assert before == 2

        # Assemble a synthetic executed trade and call `_execute_trade` directly.
        # We import here so the test owns the module import cost.
        import logging
        from datetime import datetime, timezone
        from services import trade_engine
        previous_deps = dict(trade_engine._deps)
        async def broadcast(*args, **kwargs):
            pass
        trade_engine._deps.clear()
        trade_engine.setup({"db": db, "logger": logging.getLogger(__name__), "broadcast_to_room": broadcast})
        _execute_trade = trade_engine._execute_trade

        trade_doc = {
            "league_id": LID,
            "proposer_team_id": str(a["_id"]),
            "proposer_team_name": a["name"],
            "target_team_id": str(b["_id"]),
            "target_team_name": b["name"],
            "assets_offered": [{"asset_type": "player", "player_id": a_pid}],
            "assets_requested": [{"asset_type": "player", "player_id": b_pid}],
            "status": "accepted",
        }
        ins = await db.trades.insert_one(trade_doc)
        try:
            trade_doc["_id"] = ins.inserted_id
            result = await _execute_trade(trade_doc)
            assert result.get("executed") is True

            after = await db.trade_block.count_documents({
                "league_id": LID, "player_id": {"$in": [a_pid, b_pid]},
            })
            assert after == 0, "Trade-block listings should be cleared after the trade executes"
        finally:
            # Restore rosters + cleanup
            await db.teams.update_one({"_id": a["_id"]}, {"$set": {"roster": a.get("roster", [])}})
            await db.teams.update_one({"_id": b["_id"]}, {"$set": {"roster": b.get("roster", [])}})
            await db.trades.delete_one({"_id": ins.inserted_id})
            await db.trade_block.delete_many({"league_id": LID, "player_id": {"$in": [a_pid, b_pid]}})
            trade_engine._deps.clear()
            trade_engine._deps.update(previous_deps)
    finally:
        mongo.close()
