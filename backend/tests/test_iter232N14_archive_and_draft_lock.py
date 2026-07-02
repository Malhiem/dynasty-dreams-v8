"""Iter 232N.14 + 232N.15 — Per-user chat archive + player pickup draft lock.

Chat archive (232N.14):
  (1) `POST /chat/channels/{id}/archive` adds a chat_archives row.
  (2) `list_channels` hides archived rows unless `?show_archived=true`.
  (3) Archived channels drop out of the `/chat/unread` aggregate.
  (4) `DELETE /chat/channels/{id}/archive` reverses the state.
  (5) Archive is per-user — one manager archiving doesn't affect others.

Player pickup draft lock (232N.15):
  (6) `precheck_waiver_claim` returns a `draft_lock` payload +
      `draft_locked` blocker when the league has an active/scheduled draft.
  (7) `assert_pickups_open` raises HTTP 400 with the friendly message.
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone, timedelta

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
    d = client[os.environ.get("DB_NAME", "test_database")]
    yield d
    client.close()


class R:  # minimal Request stub
    pass


async def _setup_chat(db, user_id: str):
    from routes import chat as chat_routes

    async def _fake_user(_request):
        return {"_id": user_id}

    chat_routes.setup({"db": db, "get_current_user": _fake_user})


async def _seed_league_with_member(db, user_id: str) -> str:
    league_id = str(ObjectId())
    await db.leagues.insert_one({
        "_id": ObjectId(league_id),
        "name": "Archive Test League",
        "commissioner_id": user_id,
        "members": [user_id],
    })
    return league_id


# ─── Chat archive tests ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_archive_hides_channel_from_list_and_unarchive_restores(db):
    from routes.chat import archive_channel, unarchive_channel, list_channels
    user_id = str(ObjectId())
    await _setup_chat(db, user_id)
    league_id = await _seed_league_with_member(db, user_id)

    chan_id = str(ObjectId())
    await db.chat_channels.insert_one({
        "_id": ObjectId(chan_id),
        "league_id": league_id,
        "kind": "channel",
        "name": "test-arch",
        "participants": [],
        "created_at": datetime.now(timezone.utc),
        "is_default": False,
    })
    try:
        # Baseline — channel is visible.
        r_before = await list_channels(league_id=league_id, request=R())
        names = [c["name"] for c in r_before["channels"] if c["name"] == "test-arch"]
        assert names, "channel should be visible before archive"

        # Archive it.
        res = await archive_channel(channel_id=chan_id, request=R())
        assert res == {"archived": True, "channel_id": chan_id}

        # Now hidden by default…
        r_hidden = await list_channels(league_id=league_id, request=R())
        assert not any(c["name"] == "test-arch" for c in r_hidden["channels"])

        # …but revealed when `show_archived=True`, with `archived: true`.
        r_shown = await list_channels(
            league_id=league_id, request=R(), show_archived=True,
        )
        matched = [c for c in r_shown["channels"] if c["name"] == "test-arch"]
        assert matched and matched[0]["archived"] is True

        # Unarchive brings it back to the default listing.
        await unarchive_channel(channel_id=chan_id, request=R())
        r_after = await list_channels(league_id=league_id, request=R())
        assert any(c["name"] == "test-arch" for c in r_after["channels"])
    finally:
        await db.chat_channels.delete_one({"_id": ObjectId(chan_id)})
        await db.chat_archives.delete_many({"channel_id": chan_id})
        await db.leagues.delete_one({"_id": ObjectId(league_id)})


@pytest.mark.asyncio
async def test_archive_is_per_user(db):
    """User A archiving must not hide the channel for User B."""
    from routes.chat import archive_channel, list_channels
    user_a = str(ObjectId())
    user_b = str(ObjectId())
    league_id = str(ObjectId())
    await db.leagues.insert_one({
        "_id": ObjectId(league_id),
        "name": "PerUser League",
        "commissioner_id": user_a,
        "members": [user_a, user_b],
    })
    # `_is_league_member` requires each user to own (or co-own) a team.
    ta = await db.teams.insert_one({
        "league_id": league_id, "owner_id": user_a, "name": "TA", "roster": [],
    })
    tb = await db.teams.insert_one({
        "league_id": league_id, "owner_id": user_b, "name": "TB", "roster": [],
    })
    chan_id = str(ObjectId())
    await db.chat_channels.insert_one({
        "_id": ObjectId(chan_id),
        "league_id": league_id, "kind": "channel", "name": "shared",
        "participants": [], "created_at": datetime.now(timezone.utc),
    })
    try:
        # A archives.
        await _setup_chat(db, user_a)
        await archive_channel(channel_id=chan_id, request=R())
        # B still sees the channel.
        await _setup_chat(db, user_b)
        r_b = await list_channels(league_id=league_id, request=R())
        assert any(c["name"] == "shared" for c in r_b["channels"])
    finally:
        await db.chat_channels.delete_one({"_id": ObjectId(chan_id)})
        await db.chat_archives.delete_many({"channel_id": chan_id})
        await db.teams.delete_many({"_id": {"$in": [ta.inserted_id, tb.inserted_id]}})
        await db.leagues.delete_one({"_id": ObjectId(league_id)})


@pytest.mark.asyncio
async def test_archive_excludes_channel_from_unread_badge(db):
    from routes.chat import archive_channel, total_unread
    user_id = str(ObjectId())
    await _setup_chat(db, user_id)
    league_id = str(ObjectId())
    await db.leagues.insert_one({
        "_id": ObjectId(league_id), "name": "L", "members": [user_id],
        "commissioner_id": user_id,
    })
    # Seed a team so the user shows up as a "member" for `/chat/unread`.
    await db.teams.insert_one({
        "league_id": league_id, "owner_id": user_id, "name": "T", "roster": [],
    })
    chan_id = str(ObjectId())
    await db.chat_channels.insert_one({
        "_id": ObjectId(chan_id),
        "league_id": league_id, "kind": "channel", "name": "spam",
        "participants": [], "created_at": datetime.now(timezone.utc),
    })
    # Seed an unread message from another user.
    other = str(ObjectId())
    await db.chat_messages.insert_one({
        "channel_id": chan_id, "user_id": other, "text": "hey",
        "created_at": datetime.now(timezone.utc),
    })
    try:
        before = await total_unread(request=R())
        assert before["unread"] >= 1
        await archive_channel(channel_id=chan_id, request=R())
        after = await total_unread(request=R())
        # The archived channel's unread contribution is gone.
        assert after["unread"] == before["unread"] - 1
    finally:
        await db.chat_channels.delete_one({"_id": ObjectId(chan_id)})
        await db.chat_messages.delete_many({"channel_id": chan_id})
        await db.chat_archives.delete_many({"channel_id": chan_id})
        await db.teams.delete_many({"league_id": league_id})
        await db.leagues.delete_one({"_id": ObjectId(league_id)})


# ─── Draft-lock tests (232N.15) ──────────────────────────────────

@pytest.mark.asyncio
async def test_draft_lock_helper_returns_active_over_scheduled(db):
    from utils.draft_lock import get_locking_draft
    league_id = str(ObjectId())
    # Scheduled first (older) + active later — helper should prefer active.
    sched = await db.drafts.insert_one({
        "league_id": league_id, "status": "scheduled",
        "name": "Sched", "scheduled_time": "2027-01-01T00:00:00Z",
    })
    active = await db.drafts.insert_one({
        "league_id": league_id, "status": "active",
        "name": "Active", "scheduled_time": "2026-01-01T00:00:00Z",
    })
    try:
        d = await get_locking_draft(db, league_id)
        assert d is not None and d["_id"] == active.inserted_id
    finally:
        await db.drafts.delete_many({"_id": {"$in": [sched.inserted_id, active.inserted_id]}})


@pytest.mark.asyncio
async def test_draft_lock_helper_returns_none_when_no_locking_draft(db):
    from utils.draft_lock import get_locking_draft
    league_id = str(ObjectId())
    # Completed drafts don't lock the pool.
    r = await db.drafts.insert_one({
        "league_id": league_id, "status": "completed", "name": "Done",
    })
    try:
        d = await get_locking_draft(db, league_id)
        assert d is None
    finally:
        await db.drafts.delete_one({"_id": r.inserted_id})


@pytest.mark.asyncio
async def test_assert_pickups_open_raises_when_locked(db):
    from utils.draft_lock import assert_pickups_open
    league_id = str(ObjectId())
    r = await db.drafts.insert_one({
        "league_id": league_id, "status": "scheduled",
        "name": "Upcoming Draft",
        "scheduled_time": "2027-05-01T12:00:00Z",
    })
    try:
        with pytest.raises(HTTPException) as exc:
            await assert_pickups_open(db, league_id)
        assert exc.value.status_code == 400
        assert "Upcoming Draft" in exc.value.detail
        assert "eligible" in exc.value.detail
    finally:
        await db.drafts.delete_one({"_id": r.inserted_id})


@pytest.mark.asyncio
async def test_assert_pickups_open_noop_when_no_locking_draft(db):
    from utils.draft_lock import assert_pickups_open
    league_id = str(ObjectId())
    # Should silently return.
    await assert_pickups_open(db, league_id)
