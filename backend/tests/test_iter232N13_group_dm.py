"""Iter 232N.13 — Group DM channels (3+ team threads).

Verifies:
  (1) `_ensure_group_dm` creates a fresh `group_dm` doc, backfills
      `group_key` scalar, and dedupes on re-invocation regardless of
      team_ids order.
  (2) `POST /api/chat/group-dm` requires 3+ teams (rejects 2).
  (3) `POST /api/chat/group-dm` requires the caller to include their
      own team (403 otherwise).
  (4) All teams must belong to the same league (400 otherwise).
  (5) The channel doc is visible to every participant via
      `list_channels` and gated to non-participants via
      `_require_channel_access`.
  (6) The migration lands the `uniq_group_dm_key_per_league` index.
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid

import pytest
from bson import ObjectId
from fastapi import HTTPException
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
    d = client[os.environ.get("DB_NAME", os.environ["DB_NAME"])]
    yield d
    client.close()


class R:
    """Minimal Request stub — chat.setup lets tests inject the user."""


async def _setup_chat(db, user_id: str):
    from routes import chat as chat_routes

    async def _fake_user(_request):
        return {"_id": user_id}

    chat_routes.setup({"db": db, "get_current_user": _fake_user})


async def _seed_team(db, league_id, owner_id):
    r = await db.teams.insert_one({
        "league_id": league_id,
        "owner_id": owner_id,
        "name": f"Team-{uuid.uuid4().hex[:6]}",
        "roster": [],
    })
    return str(r.inserted_id)


async def _seed_league(db, commissioner_id):
    league_id = str(ObjectId())
    await db.leagues.insert_one({
        "_id": ObjectId(league_id),
        "name": "Test League",
        "commissioner_id": commissioner_id,
        "members": [commissioner_id],
    })
    return league_id


@pytest.mark.asyncio
async def test_ensure_group_dm_creates_and_dedupes(db):
    from routes.chat import _ensure_group_dm, dedupe_dm_channels_and_create_index
    await dedupe_dm_channels_and_create_index(db)

    caller = str(ObjectId())
    league_id = await _seed_league(db, caller)
    ta = await _seed_team(db, league_id, caller)
    tb = await _seed_team(db, league_id, str(ObjectId()))
    tc = await _seed_team(db, league_id, str(ObjectId()))
    try:
        chan1 = await _ensure_group_dm(db, league_id, [ta, tb, tc], caller)
        assert chan1["kind"] == "group_dm"
        assert chan1["group_key"] == "|".join(sorted([ta, tb, tc]))
        assert set(chan1["team_ids"]) == {ta, tb, tc}
        assert " · " in chan1["name"]
        # Re-invoke with a different order → same doc.
        chan2 = await _ensure_group_dm(db, league_id, [tc, ta, tb], caller)
        assert chan2["_id"] == chan1["_id"]

        cnt = await db.chat_channels.count_documents({
            "league_id": league_id, "kind": "group_dm",
        })
        assert cnt == 1
    finally:
        await db.chat_channels.delete_many({"league_id": league_id})
        await db.teams.delete_many({"league_id": league_id})
        await db.leagues.delete_one({"_id": ObjectId(league_id)})


@pytest.mark.asyncio
async def test_ensure_group_dm_rejects_fewer_than_3_teams(db):
    from routes.chat import _ensure_group_dm
    caller = str(ObjectId())
    league_id = await _seed_league(db, caller)
    ta = await _seed_team(db, league_id, caller)
    tb = await _seed_team(db, league_id, str(ObjectId()))
    try:
        with pytest.raises(HTTPException) as exc:
            await _ensure_group_dm(db, league_id, [ta, tb], caller)
        assert exc.value.status_code == 400
    finally:
        await db.teams.delete_many({"league_id": league_id})
        await db.leagues.delete_one({"_id": ObjectId(league_id)})


@pytest.mark.asyncio
async def test_endpoint_requires_caller_to_own_a_participating_team(db):
    from routes.chat import create_group_dm
    caller = str(ObjectId())
    outsider = str(ObjectId())
    await _setup_chat(db, outsider)
    league_id = await _seed_league(db, caller)
    # Add outsider as a league member so they don't 403 on membership.
    await db.leagues.update_one(
        {"_id": ObjectId(league_id)}, {"$push": {"members": outsider}},
    )
    ta = await _seed_team(db, league_id, caller)
    tb = await _seed_team(db, league_id, str(ObjectId()))
    tc = await _seed_team(db, league_id, str(ObjectId()))
    try:
        # Outsider doesn't own any of the 3 teams → 403.
        with pytest.raises(HTTPException) as exc:
            await create_group_dm(
                payload={"league_id": league_id, "team_ids": [ta, tb, tc]},
                request=R(),
            )
        assert exc.value.status_code == 403
    finally:
        await db.chat_channels.delete_many({"league_id": league_id})
        await db.teams.delete_many({"league_id": league_id})
        await db.leagues.delete_one({"_id": ObjectId(league_id)})


@pytest.mark.asyncio
async def test_endpoint_rejects_cross_league_teams(db):
    from routes.chat import create_group_dm
    caller = str(ObjectId())
    await _setup_chat(db, caller)
    league_a = await _seed_league(db, caller)
    league_b = await _seed_league(db, caller)
    ta = await _seed_team(db, league_a, caller)
    tb = await _seed_team(db, league_a, str(ObjectId()))
    tc = await _seed_team(db, league_b, str(ObjectId()))  # wrong league
    try:
        with pytest.raises(HTTPException) as exc:
            await create_group_dm(
                payload={"league_id": league_a, "team_ids": [ta, tb, tc]},
                request=R(),
            )
        assert exc.value.status_code == 400
    finally:
        await db.chat_channels.delete_many({"league_id": {"$in": [league_a, league_b]}})
        await db.teams.delete_many({"league_id": {"$in": [league_a, league_b]}})
        await db.leagues.delete_many({"_id": {"$in": [ObjectId(league_a), ObjectId(league_b)]}})


@pytest.mark.asyncio
async def test_list_channels_gates_group_dm_to_participants(db):
    from routes.chat import _ensure_group_dm, list_channels
    caller = str(ObjectId())
    lurker = str(ObjectId())
    league_id = await _seed_league(db, caller)
    # Add lurker to league so `_require_league_member` passes.
    await db.leagues.update_one(
        {"_id": ObjectId(league_id)}, {"$push": {"members": lurker}},
    )
    ta = await _seed_team(db, league_id, caller)
    tb = await _seed_team(db, league_id, str(ObjectId()))
    tc = await _seed_team(db, league_id, str(ObjectId()))
    # lurker is NOT any of the group DM teams' owners.
    _ = await _seed_team(db, league_id, lurker)
    try:
        await _ensure_group_dm(db, league_id, [ta, tb, tc], caller)
        # Caller sees the group DM.
        await _setup_chat(db, caller)
        seen_caller = await list_channels(league_id=league_id, request=R())
        group_ids_caller = [c for c in seen_caller["channels"] if c["kind"] == "group_dm"]
        assert len(group_ids_caller) == 1
        # Lurker doesn't.
        await _setup_chat(db, lurker)
        seen_lurker = await list_channels(league_id=league_id, request=R())
        group_ids_lurker = [c for c in seen_lurker["channels"] if c["kind"] == "group_dm"]
        assert len(group_ids_lurker) == 0
    finally:
        await db.chat_channels.delete_many({"league_id": league_id})
        await db.teams.delete_many({"league_id": league_id})
        await db.leagues.delete_one({"_id": ObjectId(league_id)})


@pytest.mark.asyncio
async def test_migration_creates_group_dm_unique_index(db):
    from routes.chat import dedupe_dm_channels_and_create_index
    await dedupe_dm_channels_and_create_index(db)
    idxs = await db.chat_channels.index_information()
    assert "uniq_group_dm_key_per_league" in idxs
    info = idxs["uniq_group_dm_key_per_league"]
    assert info.get("unique") is True
