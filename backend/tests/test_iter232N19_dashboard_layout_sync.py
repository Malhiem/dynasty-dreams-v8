"""Iter 232N.19 — Cross-device dashboard layout sync.

Verifies:
  (1) GET /users/me/dashboard-layout returns empty state for a fresh user.
  (2) PATCH persists the widget_order and returns the cleaned list.
  (3) GET after PATCH returns exactly what was saved (round-trip).
  (4) PATCH rejects non-list bodies (400).
  (5) PATCH rejects over-length payloads (>32 entries) (400).
  (6) PATCH silently drops empty/non-string ids and ids >64 chars.
"""
from __future__ import annotations

import asyncio
import os
import sys

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


class R:
    pass


async def _seed_user(db) -> str:
    """Insert a minimal user doc and return the string id."""
    r = await db.users.insert_one({
        "username": "layout-user",
        "email": "layout-user@example.com",
        "password_hash": "x",
    })
    return str(r.inserted_id)


async def _setup_users_route(db, user_id: str):
    from routes import users as users_routes

    async def _fake_user(_request):
        return {"_id": user_id}

    users_routes.setup({"db": db, "get_current_user": _fake_user})


@pytest.mark.asyncio
async def test_layout_get_returns_empty_for_fresh_user(db):
    from routes.users import get_my_dashboard_layout
    user_id = await _seed_user(db)
    await _setup_users_route(db, user_id)
    try:
        res = await get_my_dashboard_layout(request=R())
        assert res == {"widget_order": [], "updated_at": None}
    finally:
        await db.users.delete_one({"_id": ObjectId(user_id)})


@pytest.mark.asyncio
async def test_layout_patch_persists_and_get_round_trips(db):
    from routes.users import get_my_dashboard_layout, patch_my_dashboard_layout
    user_id = await _seed_user(db)
    await _setup_users_route(db, user_id)
    try:
        order = ["my-leagues", "pending-trades", "week-at-a-glance"]
        patched = await patch_my_dashboard_layout(
            payload={"widget_order": order}, request=R(),
        )
        assert patched["widget_order"] == order
        assert patched["updated_at"]
        got = await get_my_dashboard_layout(request=R())
        assert got["widget_order"] == order
        assert got["updated_at"] is not None
    finally:
        await db.users.delete_one({"_id": ObjectId(user_id)})


@pytest.mark.asyncio
async def test_layout_patch_rejects_non_list_body(db):
    from routes.users import patch_my_dashboard_layout
    user_id = await _seed_user(db)
    await _setup_users_route(db, user_id)
    try:
        with pytest.raises(HTTPException) as exc:
            await patch_my_dashboard_layout(
                payload={"widget_order": "nope"}, request=R(),
            )
        assert exc.value.status_code == 400
    finally:
        await db.users.delete_one({"_id": ObjectId(user_id)})


@pytest.mark.asyncio
async def test_layout_patch_rejects_over_length_payload(db):
    from routes.users import patch_my_dashboard_layout
    user_id = await _seed_user(db)
    await _setup_users_route(db, user_id)
    try:
        too_long = [f"w-{i}" for i in range(40)]
        with pytest.raises(HTTPException) as exc:
            await patch_my_dashboard_layout(
                payload={"widget_order": too_long}, request=R(),
            )
        assert exc.value.status_code == 400
    finally:
        await db.users.delete_one({"_id": ObjectId(user_id)})


@pytest.mark.asyncio
async def test_layout_patch_drops_bad_entries(db):
    from routes.users import patch_my_dashboard_layout
    user_id = await _seed_user(db)
    await _setup_users_route(db, user_id)
    try:
        payload = {"widget_order": [
            "my-leagues",   # keep
            "",             # drop — empty after strip
            "   ",          # drop — whitespace-only
            42,             # drop — non-string
            "x" * 65,       # drop — over 64 chars
            "pending-trades",  # keep
        ]}
        res = await patch_my_dashboard_layout(payload=payload, request=R())
        assert res["widget_order"] == ["my-leagues", "pending-trades"]
    finally:
        await db.users.delete_one({"_id": ObjectId(user_id)})
