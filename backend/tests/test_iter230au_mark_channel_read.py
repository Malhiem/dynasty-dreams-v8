"""Iter 230au — `POST /api/chat/channels/{id}/mark-read` powers the
mobile swipe-right-on-channel gesture in the chat sidebar. Marks the
channel as read without forcing the caller to load the message list.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

import pytest
import requests
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

API_URL = os.environ["REACT_APP_BACKEND_URL"]


def _register_login():
    suffix = uuid.uuid4().hex[:6]
    email = f"iter230au_{suffix}@example.com"
    requests.post(
        f"{API_URL}/api/auth/register",
        json={"email": email, "password": "TestPass123!",
              "username": f"i230au_{suffix}", "name": "iter230au"},
    )
    r = requests.post(
        f"{API_URL}/api/auth/login",
        json={"email": email, "password": "TestPass123!"},
    )
    r.raise_for_status()
    body = r.json()
    return {"token": body["access_token"], "id": body["id"]}


def _h(t): return {"Authorization": f"Bearer {t}"}


@pytest.mark.asyncio
async def test_mark_channel_read_zeros_unread():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[
        os.environ.get("DB_NAME", "test_database")
    ]
    sender = _register_login()
    reader = _register_login()

    # Create a league + team for the reader so chat/unread counts the channel.
    r = requests.post(
        f"{API_URL}/api/leagues", headers=_h(reader["token"]),
        json={"name": f"Iter230au {uuid.uuid4().hex[:4]}",
              "format": "dynasty", "scoring_format": "head_to_head",
              "max_teams": 4, "draft_type": "snake", "roster_spots": 10},
    )
    r.raise_for_status()
    league_id = r.json()["id"]

    # Seed a channel + 3 messages from `sender`.
    chan_id = ObjectId()
    await db.chat_channels.insert_one({
        "_id": chan_id, "kind": "channel", "league_id": league_id,
        "name": "general", "created_at": datetime.now(timezone.utc),
    })
    for i in range(3):
        await db.chat_messages.insert_one({
            "_id": ObjectId(), "channel_id": str(chan_id),
            "user_id": sender["id"], "body": f"msg {i}",
            "created_at": datetime.now(timezone.utc),
        })

    try:
        # Reader is in the league via being commish → unread should be 3.
        unread = requests.get(f"{API_URL}/api/chat/unread",
                              headers=_h(reader["token"])).json()
        assert unread["unread"] == 3, unread

        # Hit the new mark-read endpoint.
        r = requests.post(
            f"{API_URL}/api/chat/channels/{chan_id}/mark-read",
            headers=_h(reader["token"]),
        )
        assert r.status_code == 200, r.text
        assert r.json()["channel_id"] == str(chan_id)

        # Unread should now be 0.
        unread2 = requests.get(f"{API_URL}/api/chat/unread",
                               headers=_h(reader["token"])).json()
        assert unread2["unread"] == 0, unread2
    finally:
        await db.chat_messages.delete_many({"channel_id": str(chan_id)})
        await db.chat_channels.delete_one({"_id": chan_id})
        await db.leagues.delete_one({"_id": ObjectId(league_id)})
        await db.teams.delete_many({"league_id": league_id})
        await db.chat_reads.delete_many({"channel_id": str(chan_id)})


@pytest.mark.asyncio
async def test_mark_channel_read_404_when_missing():
    user = _register_login()
    fake_id = str(ObjectId())
    r = requests.post(
        f"{API_URL}/api/chat/channels/{fake_id}/mark-read",
        headers=_h(user["token"]),
    )
    assert r.status_code == 404, r.text


@pytest.mark.asyncio
async def test_mark_channel_read_dm_participant_check():
    """Non-participants can't mark a DM channel as read."""
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[
        os.environ.get("DB_NAME", "test_database")
    ]
    alice = _register_login()
    bob = _register_login()
    carol = _register_login()

    dm_id = ObjectId()
    await db.chat_channels.insert_one({
        "_id": dm_id, "kind": "dm",
        "participants": [alice["id"], bob["id"]],
        "name": "Alice & Bob", "created_at": datetime.now(timezone.utc),
    })
    try:
        # Carol (not a participant) → 403
        r = requests.post(
            f"{API_URL}/api/chat/channels/{dm_id}/mark-read",
            headers=_h(carol["token"]),
        )
        assert r.status_code == 403, r.text

        # Alice (participant) → 200
        r = requests.post(
            f"{API_URL}/api/chat/channels/{dm_id}/mark-read",
            headers=_h(alice["token"]),
        )
        assert r.status_code == 200, r.text
    finally:
        await db.chat_channels.delete_one({"_id": dm_id})
        await db.chat_reads.delete_many({"channel_id": str(dm_id)})
