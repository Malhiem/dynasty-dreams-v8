"""Iter 230aq — `/api/chat/unread` must only count channels in
leagues where the user actually has membership (commissioner / team
owner / co-owner). Previously the endpoint scanned every chat_channel
in the DB and only filtered DMs by `participants`, so league-scoped
channels in unrelated leagues padded the sidebar badge with phantom
unread counts.
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timezone

import pytest
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient
import httpx

API_URL = os.environ["REACT_APP_BACKEND_URL"]
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def _register(client: httpx.AsyncClient, suffix: str):
    s = uuid.uuid4().hex[:6]
    email = f"iter230aq_{suffix}_{s}@example.com"
    await client.post(
        f"{API_URL}/api/auth/register",
        json={"email": email, "password": "TestPass123!",
              "username": f"i230aq_{suffix}_{s}"[:32],
              "name": f"iter230aq {suffix}"},
    )
    client.cookies.clear()
    r = await client.post(
        f"{API_URL}/api/auth/login",
        json={"email": email, "password": "TestPass123!"},
    )
    r.raise_for_status()
    client.cookies.clear()
    body = r.json()
    return {"email": email, "token": body["access_token"], "id": body["id"]}


def _h(t: str) -> dict:
    return {"Authorization": f"Bearer {t}"}


@pytest.mark.asyncio
async def test_chat_unread_ignores_channels_in_other_leagues():
    """User A creates a league + chat channel + posts messages.
    User B (in a totally separate league) hits `/chat/unread` and
    must see 0, NOT user A's messages."""
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[
        os.environ.get("DB_NAME", "test_database")
    ]
    async with httpx.AsyncClient(timeout=30.0) as client:
        user_a = await _register(client, "ua")
        user_b = await _register(client, "ub")

        # User A creates a league
        r = await client.post(
            f"{API_URL}/api/leagues", headers=_h(user_a["token"]),
            json={"name": f"Iter230aq A {uuid.uuid4().hex[:4]}",
                  "format": "dynasty", "scoring_format": "head_to_head",
                  "max_teams": 4, "draft_type": "snake", "roster_spots": 10},
        )
        r.raise_for_status()
        league_a_id = r.json()["id"]

        # Hand-create a chat channel inside user A's league (skip the
        # auto-creation flow since we only need a single channel for
        # the assertion) and seed 5 messages from user A.
        chan_id = ObjectId()
        await db.chat_channels.insert_one({
            "_id": chan_id,
            "kind": "channel",
            "league_id": league_a_id,
            "name": "general",
            "created_at": datetime.now(timezone.utc),
        })
        for i in range(5):
            await db.chat_messages.insert_one({
                "_id": ObjectId(),
                "channel_id": str(chan_id),
                "user_id": user_a["id"],
                "body": f"Iter230aq A message {i}",
                "created_at": datetime.now(timezone.utc),
            })

        # User B (no membership in user A's league) checks their badge
        try:
            r = await client.get(
                f"{API_URL}/api/chat/unread",
                headers=_h(user_b["token"]),
            )
            r.raise_for_status()
            payload = r.json()
            assert payload["unread"] == 0, payload
            # The channel itself must NOT appear in by_channel
            assert str(chan_id) not in payload["by_channel"], payload
        finally:
            await db.chat_messages.delete_many({"channel_id": str(chan_id)})
            await db.chat_channels.delete_one({"_id": chan_id})
            await db.leagues.delete_one({"_id": ObjectId(league_a_id)})
            await db.teams.delete_many({"league_id": league_a_id})


@pytest.mark.asyncio
async def test_chat_unread_does_count_channels_in_member_leagues():
    """Same scenario, but user B joins user A's league via team. Now
    `/chat/unread` MUST report the 5 unread messages."""
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[
        os.environ.get("DB_NAME", "test_database")
    ]
    async with httpx.AsyncClient(timeout=30.0) as client:
        user_a = await _register(client, "ua")
        user_b = await _register(client, "ub")

        r = await client.post(
            f"{API_URL}/api/leagues", headers=_h(user_a["token"]),
            json={"name": f"Iter230aq Member {uuid.uuid4().hex[:4]}",
                  "format": "dynasty", "scoring_format": "head_to_head",
                  "max_teams": 4, "draft_type": "snake", "roster_spots": 10},
        )
        r.raise_for_status()
        league_id = r.json()["id"]

        # Seed user B's membership directly (skip the join flow)
        await db.teams.insert_one({
            "_id": ObjectId(), "league_id": league_id,
            "owner_id": user_b["id"], "name": "Iter230aq B team",
            "roster": [],
        })

        chan_id = ObjectId()
        await db.chat_channels.insert_one({
            "_id": chan_id, "kind": "channel", "league_id": league_id,
            "name": "general", "created_at": datetime.now(timezone.utc),
        })
        for i in range(5):
            await db.chat_messages.insert_one({
                "_id": ObjectId(), "channel_id": str(chan_id),
                "user_id": user_a["id"],
                "body": f"member msg {i}",
                "created_at": datetime.now(timezone.utc),
            })

        try:
            r = await client.get(
                f"{API_URL}/api/chat/unread",
                headers=_h(user_b["token"]),
            )
            r.raise_for_status()
            payload = r.json()
            assert payload["unread"] == 5, payload
            assert payload["by_channel"].get(str(chan_id)) == 5
        finally:
            await db.chat_messages.delete_many({"channel_id": str(chan_id)})
            await db.chat_channels.delete_one({"_id": chan_id})
            await db.teams.delete_many({"league_id": league_id})
            await db.leagues.delete_one({"_id": ObjectId(league_id)})


@pytest.mark.asyncio
async def test_chat_unread_explicit_league_filter_zero_when_not_member():
    """Passing `?league_id=X` for a league the user isn't in must
    return zero (not leak that the league exists)."""
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[
        os.environ.get("DB_NAME", "test_database")
    ]
    async with httpx.AsyncClient(timeout=30.0) as client:
        user_a = await _register(client, "ua")
        user_b = await _register(client, "ub")

        r = await client.post(
            f"{API_URL}/api/leagues", headers=_h(user_a["token"]),
            json={"name": f"Iter230aq Filter {uuid.uuid4().hex[:4]}",
                  "format": "dynasty", "scoring_format": "head_to_head",
                  "max_teams": 4, "draft_type": "snake", "roster_spots": 10},
        )
        r.raise_for_status()
        league_id = r.json()["id"]

        chan_id = ObjectId()
        await db.chat_channels.insert_one({
            "_id": chan_id, "kind": "channel", "league_id": league_id,
            "name": "trades", "created_at": datetime.now(timezone.utc),
        })
        await db.chat_messages.insert_one({
            "_id": ObjectId(), "channel_id": str(chan_id),
            "user_id": user_a["id"], "body": "filter test",
            "created_at": datetime.now(timezone.utc),
        })

        try:
            r = await client.get(
                f"{API_URL}/api/chat/unread?league_id={league_id}",
                headers=_h(user_b["token"]),
            )
            r.raise_for_status()
            assert r.json()["unread"] == 0
        finally:
            await db.chat_messages.delete_many({"channel_id": str(chan_id)})
            await db.chat_channels.delete_one({"_id": chan_id})
            await db.leagues.delete_one({"_id": ObjectId(league_id)})
            await db.teams.delete_many({"league_id": league_id})
