"""Iter 232N.12 — Chat channel dedup + atomic upserts + unique indexes.

Verifies:
  (1) `_ensure_dm_channel` is race-safe — concurrent invocations for
      the same team pair produce ONE channel, not two.
  (2) `_ensure_default_channels` is race-safe — concurrent invocations
      for the same league don't multiply the default channel rows.
  (3) The startup migration merges historical duplicate DM/default rows
      onto the oldest survivor, re-parents messages/reads/mutes, and
      lands the unique partial indexes.
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
    d = client[os.environ.get("DB_NAME", "test_database")]
    yield d
    client.close()


async def _seed_team(db, league_id: str, owner_id: str):
    r = await db.teams.insert_one({
        "league_id": league_id,
        "owner_id": owner_id,
        "name": f"Team {uuid.uuid4().hex[:6]}",
        "roster": [],
    })
    return str(r.inserted_id)


@pytest.mark.asyncio
async def test_ensure_dm_channel_is_race_safe(db):
    from routes.chat import _ensure_dm_channel, dedupe_dm_channels_and_create_index
    # Ensure the unique index is in place (idempotent).
    await dedupe_dm_channels_and_create_index(db)

    league_id = str(ObjectId())
    ta = await _seed_team(db, league_id, str(ObjectId()))
    tb = await _seed_team(db, league_id, str(ObjectId()))

    try:
        # Fire many concurrent calls (both orderings) to simulate two
        # participants opening chat at the same time from opposite ends.
        results = await asyncio.gather(*[
            _ensure_dm_channel(db, league_id, ta, tb) for _ in range(8)
        ] + [
            _ensure_dm_channel(db, league_id, tb, ta) for _ in range(8)
        ])
        ids = {r["_id"] for r in results}
        assert len(ids) == 1, f"expected 1 DM channel, got {len(ids)}: {ids}"

        # DB should agree.
        count = await db.chat_channels.count_documents({
            "league_id": league_id, "kind": "dm",
        })
        assert count == 1
    finally:
        await db.chat_channels.delete_many({"league_id": league_id})
        await db.teams.delete_many({"league_id": league_id})


@pytest.mark.asyncio
async def test_ensure_default_channels_is_race_safe(db):
    from routes.chat import _ensure_default_channels, dedupe_dm_channels_and_create_index
    await dedupe_dm_channels_and_create_index(db)

    league_id = str(ObjectId())
    try:
        await asyncio.gather(*[
            _ensure_default_channels(db, league_id) for _ in range(6)
        ])
        # Exactly 3 default channels — general, trades, trash-talk.
        count = await db.chat_channels.count_documents({
            "league_id": league_id, "kind": "channel", "is_default": True,
        })
        assert count == 3, f"expected 3 default channels, got {count}"
        # And the names are the expected set.
        names = set()
        async for c in db.chat_channels.find({"league_id": league_id, "kind": "channel"}):
            names.add(c.get("name"))
        assert names == {"general", "trades", "trash-talk"}
    finally:
        await db.chat_channels.delete_many({"league_id": league_id})


@pytest.mark.asyncio
async def test_dedupe_migration_merges_dupes_and_reparents_messages(db):
    """Simulate the historical race by directly inserting two DM rows
    for the same pair, plus a message on the newer one; run the
    migration and assert the older survives + owns the message."""
    from routes.chat import dedupe_dm_channels_and_create_index
    # Priming index in case first run in this test DB.
    await dedupe_dm_channels_and_create_index(db)

    league_id = str(ObjectId())
    ta = await _seed_team(db, league_id, str(ObjectId()))
    tb = await _seed_team(db, league_id, str(ObjectId()))
    pair = sorted([ta, tb])

    # Suspend the unique index so we can seed duplicates deliberately.
    try:
        await db.chat_channels.drop_index("uniq_dm_pair_key_per_league")
    except Exception:
        pass

    now = datetime.now(timezone.utc)
    older = await db.chat_channels.insert_one({
        "league_id": league_id, "kind": "dm", "team_pair": pair,
        "name": "older", "participants": [], "created_at": now - timedelta(hours=2),
    })
    newer = await db.chat_channels.insert_one({
        "league_id": league_id, "kind": "dm", "team_pair": pair,
        "name": "newer", "participants": [], "created_at": now,
    })
    msg = await db.chat_messages.insert_one({
        "channel_id": str(newer.inserted_id),
        "user_id": str(ObjectId()), "text": "hello", "created_at": now,
    })

    try:
        stats = await dedupe_dm_channels_and_create_index(db)
        assert stats["pairs_merged"] >= 1
        assert stats["channels_deleted"] >= 1
        # Survivor is the older channel.
        remaining = await db.chat_channels.find({
            "league_id": league_id, "kind": "dm",
        }).to_list(10)
        assert len(remaining) == 1
        assert remaining[0]["_id"] == older.inserted_id
        assert remaining[0].get("dm_pair_key") == "|".join(pair)
        # Message is now on the survivor.
        msg_doc = await db.chat_messages.find_one({"_id": msg.inserted_id})
        assert msg_doc["channel_id"] == str(older.inserted_id)
    finally:
        await db.chat_channels.delete_many({"league_id": league_id})
        await db.chat_messages.delete_one({"_id": msg.inserted_id})
        await db.teams.delete_many({"league_id": league_id})
