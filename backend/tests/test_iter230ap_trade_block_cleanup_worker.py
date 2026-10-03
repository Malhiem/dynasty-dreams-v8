"""Iter 230ap — Trade-block cleanup worker tests."""
from __future__ import annotations

import os
import sys

import pytest
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.trade_block_cleanup_worker import run_once


def _db():
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[
        os.environ.get("DB_NAME", os.environ["DB_NAME"])
    ]


@pytest.mark.asyncio
async def test_backfills_missing_name_from_players_collection():
    db = _db()
    # Seed a player + a trade_block row with name=None pointing at it.
    player_id = ObjectId()
    await db.players.insert_one({
        "_id": player_id, "name": "Iter230ap Tester", "position": "C",
        "team": "TST", "age": 27,
        "nhl_id": f"iter230ap_{player_id}",
        "season_stats": {"games_played": 60, "goals": 25, "assists": 30,
                         "points": 55, "plus_minus": 5, "fantasy_points": 88.4},
    })
    row_id = ObjectId()
    await db.trade_block.insert_one({
        "_id": row_id,
        "item_type": "player",
        "player_id": str(player_id),
        "name": None,           # ← stale legacy state
        "looking_for": ["D"],
        "owner_id": "fake-owner",
        "league_id": "fake-league",
    })
    try:
        counts = await run_once(db)
        assert counts["backfilled"] >= 1

        refreshed = await db.trade_block.find_one({"_id": row_id})
        assert refreshed["name"] == "Iter230ap Tester"
        assert refreshed["position"] == "C"
        assert refreshed["nhl_team"] == "TST"
        assert refreshed["points"] == 55
        assert refreshed["age"] == 27
        assert refreshed["fantasy_points"] == 88.4
    finally:
        await db.trade_block.delete_one({"_id": row_id})
        await db.players.delete_one({"_id": player_id})


@pytest.mark.asyncio
async def test_prunes_orphan_row_when_player_no_longer_exists():
    db = _db()
    missing_player_id = ObjectId()  # Never inserted
    row_id = ObjectId()
    await db.trade_block.insert_one({
        "_id": row_id,
        "item_type": "player",
        "player_id": str(missing_player_id),
        "name": None,
        "looking_for": [],
        "owner_id": "fake-owner",
        "league_id": "fake-league",
    })
    try:
        counts = await run_once(db)
        assert counts["pruned"] >= 1
        assert await db.trade_block.find_one({"_id": row_id}) is None
    finally:
        await db.trade_block.delete_one({"_id": row_id})


@pytest.mark.asyncio
async def test_leaves_well_formed_rows_alone():
    """Rows that already have a `name` populated must not be touched
    even if they reference a player. Avoids re-running stat backfill
    on every pass."""
    db = _db()
    player_id = ObjectId()
    await db.players.insert_one({
        "_id": player_id, "name": "Iter230ap NewName", "position": "LW",
        "team": "NEW",
        "nhl_id": f"iter230ap_well_{player_id}",
    })
    row_id = ObjectId()
    await db.trade_block.insert_one({
        "_id": row_id,
        "item_type": "player",
        "player_id": str(player_id),
        "name": "Iter230ap PreservedName",   # already populated
        "position": "RW",
        "nhl_team": "OLD",
        "looking_for": [],
        "owner_id": "fake-owner",
        "league_id": "fake-league",
    })
    try:
        await run_once(db)
        unchanged = await db.trade_block.find_one({"_id": row_id})
        assert unchanged["name"] == "Iter230ap PreservedName"
        assert unchanged["position"] == "RW"
        assert unchanged["nhl_team"] == "OLD"
    finally:
        await db.trade_block.delete_one({"_id": row_id})
        await db.players.delete_one({"_id": player_id})


@pytest.mark.asyncio
async def test_prunes_row_with_no_player_id_at_all():
    """A row marked `item_type=player` with no name AND no player_id
    is unrecoverable — prune it."""
    db = _db()
    row_id = ObjectId()
    await db.trade_block.insert_one({
        "_id": row_id,
        "item_type": "player",
        "name": None,
        # no player_id
        "looking_for": [],
        "owner_id": "fake-owner",
        "league_id": "fake-league",
    })
    try:
        counts = await run_once(db)
        assert counts["pruned"] >= 1
        assert await db.trade_block.find_one({"_id": row_id}) is None
    finally:
        await db.trade_block.delete_one({"_id": row_id})


@pytest.mark.asyncio
async def test_backfills_pick_name_from_year_and_round():
    db = _db()
    row_id = ObjectId()
    await db.trade_block.insert_one({
        "_id": row_id,
        "item_type": "pick",
        "name": None,
        "pick_year": 2027,
        "pick_round": 1,
        "pick_number": 4,
        "owner_id": "fake-owner",
        "league_id": "fake-league",
    })
    try:
        counts = await run_once(db)
        assert counts["backfilled"] >= 1
        refreshed = await db.trade_block.find_one({"_id": row_id})
        assert refreshed["name"] == "2027 R1 #4"
        assert refreshed["position"] == "PICK"
    finally:
        await db.trade_block.delete_one({"_id": row_id})


@pytest.mark.asyncio
async def test_prunes_pick_row_with_no_year_or_round():
    db = _db()
    row_id = ObjectId()
    await db.trade_block.insert_one({
        "_id": row_id,
        "item_type": "pick",
        "name": None,
        # no pick_year / pick_round
        "owner_id": "fake-owner",
        "league_id": "fake-league",
    })
    try:
        counts = await run_once(db)
        assert counts["pruned"] >= 1
        assert await db.trade_block.find_one({"_id": row_id}) is None
    finally:
        await db.trade_block.delete_one({"_id": row_id})
