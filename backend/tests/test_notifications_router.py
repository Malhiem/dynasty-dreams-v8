"""Focused unit tests for `routes/notifications.py`.

Covers list / count / mark-read / mark-all-read against an ephemeral test
database. Each test runs in isolation and the database is dropped on exit.
"""
import os
import sys
from datetime import datetime, timezone

import pytest
from bson import ObjectId

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from routes import notifications as notifications_routes  # noqa: E402

from tests.router_test_utils import isolated_router_app  # noqa: E402


async def _seed_notif(db, *, user_id="test_user_0001", read=False, title="N"):
    """Insert a notification doc and return its string id."""
    res = await db.notifications.insert_one({
        "user_id": user_id,
        "type": "trade_proposal",
        "title": title,
        "message": "test message",
        "read": read,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return str(res.inserted_id)


@pytest.mark.asyncio
async def test_list_returns_empty_when_no_notifications():
    async with isolated_router_app(notifications_routes) as ctx:
        r = await ctx.client.get("/api/notifications")
        assert r.status_code == 200
        assert r.json() == []


@pytest.mark.asyncio
async def test_list_only_returns_current_user_notifications():
    async with isolated_router_app(notifications_routes) as ctx:
        await _seed_notif(ctx.db, user_id="test_user_0001", title="Mine")
        await _seed_notif(ctx.db, user_id="other_user", title="Theirs")
        r = await ctx.client.get("/api/notifications")
        body = r.json()
        assert len(body) == 1
        assert body[0]["title"] == "Mine"


@pytest.mark.asyncio
async def test_list_unread_only_filter():
    async with isolated_router_app(notifications_routes) as ctx:
        await _seed_notif(ctx.db, read=False, title="Unread")
        await _seed_notif(ctx.db, read=True, title="Read")
        r = await ctx.client.get("/api/notifications?unread_only=true")
        body = r.json()
        assert len(body) == 1
        assert body[0]["title"] == "Unread"


@pytest.mark.asyncio
async def test_unread_count():
    async with isolated_router_app(notifications_routes) as ctx:
        await _seed_notif(ctx.db, read=False)
        await _seed_notif(ctx.db, read=False)
        await _seed_notif(ctx.db, read=True)
        # plus one belonging to another user — must be excluded
        await _seed_notif(ctx.db, user_id="other_user", read=False)
        r = await ctx.client.get("/api/notifications/count")
        assert r.status_code == 200
        assert r.json() == {"count": 2}


@pytest.mark.asyncio
async def test_mark_single_read():
    async with isolated_router_app(notifications_routes) as ctx:
        nid = await _seed_notif(ctx.db, read=False)
        r = await ctx.client.post(f"/api/notifications/{nid}/read")
        assert r.status_code == 200
        doc = await ctx.db.notifications.find_one({"_id": ObjectId(nid)})
        assert doc["read"] is True


@pytest.mark.asyncio
async def test_mark_single_read_does_not_affect_other_users():
    async with isolated_router_app(notifications_routes) as ctx:
        other_nid = await _seed_notif(ctx.db, user_id="other_user", read=False)
        # The endpoint matches `user_id=user[_id]` — so this should be a no-op.
        r = await ctx.client.post(f"/api/notifications/{other_nid}/read")
        assert r.status_code == 200
        # The other user's notification stays unread.
        doc = await ctx.db.notifications.find_one({"_id": ObjectId(other_nid)})
        assert doc["read"] is False


@pytest.mark.asyncio
async def test_mark_all_read():
    async with isolated_router_app(notifications_routes) as ctx:
        await _seed_notif(ctx.db, read=False)
        await _seed_notif(ctx.db, read=False)
        await _seed_notif(ctx.db, user_id="other_user", read=False)  # must not be touched
        r = await ctx.client.post("/api/notifications/read-all")
        assert r.status_code == 200
        body = r.json()
        assert "2" in body["message"]
        # Confirm only test_user's notifs flipped
        unread_mine = await ctx.db.notifications.count_documents({
            "user_id": "test_user_0001", "read": False,
        })
        assert unread_mine == 0
        unread_other = await ctx.db.notifications.count_documents({
            "user_id": "other_user", "read": False,
        })
        assert unread_other == 1
