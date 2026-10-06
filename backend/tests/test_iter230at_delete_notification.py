"""Iter 230at — DELETE /api/notifications/{id} powers the mobile
swipe-left-to-dismiss gesture in NotificationsPanel."""
from __future__ import annotations

import os
import uuid

import pytest
import requests
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

API_URL = os.environ["REACT_APP_BACKEND_URL"]


def _register_login():
    suffix = uuid.uuid4().hex[:6]
    email = f"iter230at_{suffix}@example.com"
    requests.post(
        f"{API_URL}/api/auth/register",
        json={"email": email, "password": "TestPass123!",
              "username": f"i230at_{suffix}", "name": f"iter230at {suffix}"},
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
async def test_delete_notification_owner_only():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[
        os.environ.get("DB_NAME", os.environ["DB_NAME"])
    ]
    alice = _register_login()
    bob = _register_login()

    notif = {
        "user_id": alice["id"],
        "type": "draft_your_turn",
        "title": "T",
        "message": "M",
        "read": False,
        "created_at": "2026-06-27T00:00:00+00:00",
    }
    result = await db.notifications.insert_one(notif)
    nid = str(result.inserted_id)

    try:
        # Bob can't delete Alice's notification → 404
        r = requests.delete(
            f"{API_URL}/api/notifications/{nid}", headers=_h(bob["token"]),
        )
        assert r.status_code == 404, r.text
        # Still exists
        assert await db.notifications.find_one({"_id": ObjectId(nid)}) is not None

        # Alice can delete it → 200
        r = requests.delete(
            f"{API_URL}/api/notifications/{nid}", headers=_h(alice["token"]),
        )
        assert r.status_code == 200, r.text
        assert await db.notifications.find_one({"_id": ObjectId(nid)}) is None
    finally:
        await db.notifications.delete_many({"_id": ObjectId(nid)})


@pytest.mark.asyncio
async def test_delete_notification_404_when_missing():
    alice = _register_login()
    fake_id = str(ObjectId())
    r = requests.delete(
        f"{API_URL}/api/notifications/{fake_id}", headers=_h(alice["token"]),
    )
    assert r.status_code == 404, r.text


@pytest.mark.asyncio
async def test_delete_notification_requires_auth():
    fake_id = str(ObjectId())
    r = requests.delete(f"{API_URL}/api/notifications/{fake_id}")
    assert r.status_code in (401, 403)
