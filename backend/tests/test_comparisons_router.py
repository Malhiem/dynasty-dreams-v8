"""Focused unit tests for `routes/comparisons.py`.

Covers the Pro paywall surface — `/users/me/pro-status` quota math, the
admin Pro-toggle (env-gated to ADMIN_EMAIL), and quota period rollover.

The `/comparisons/compare` endpoint depends on
`routes.players.get_player_historical_stats` which talks to the NHL API
and is covered by `test_compare_paywall.py`. We avoid duplicating that
heavy path here.
"""
import os
import sys

import pytest
from bson import ObjectId

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from routes import comparisons as comparisons_routes  # noqa: E402

from tests.router_test_utils import isolated_router_app  # noqa: E402


async def _seed_user(db, *, email="test@example.com", is_pro=False, used=0, period_key=None):
    """Insert a user doc. Comparisons router calls ObjectId(user["_id"]) so
    we have to use a real ObjectId-shaped id rather than the default
    test_user_0001 string.
    """
    oid = ObjectId()
    doc = {
        "_id": oid, "email": email, "name": "Tester", "is_pro": is_pro,
        "comparisons_used_this_month": used,
    }
    if period_key:
        doc["comparisons_period_key"] = period_key
    await db.users.insert_one(doc)
    return {"_id": str(oid), "id": str(oid), "email": email, "name": "Tester",
            "is_pro": is_pro, "comparisons_used_this_month": used,
            "comparisons_period_key": period_key}


@pytest.mark.asyncio
async def test_pro_status_default_user_has_full_quota():
    async with isolated_router_app(comparisons_routes) as ctx:
        user = await _seed_user(ctx.db)
        # Replace the stub user the harness installed with one whose _id is a real ObjectId
        ctx.user.update(user)
        comparisons_routes._deps["get_current_user"] = lambda _r: _async_return(user)

        r = await ctx.client.get("/api/users/me/pro-status")
        assert r.status_code == 200
        body = r.json()
        assert body["is_pro"] is False
        assert body["free_quota_per_month"] == 3
        assert body["comparisons_used_this_month"] == 0
        assert body["comparisons_remaining"] == 3


@pytest.mark.asyncio
async def test_pro_status_pro_user_unlimited():
    async with isolated_router_app(comparisons_routes) as ctx:
        user = await _seed_user(ctx.db, is_pro=True)
        comparisons_routes._deps["get_current_user"] = lambda _r: _async_return(user)
        r = await ctx.client.get("/api/users/me/pro-status")
        body = r.json()
        assert body["is_pro"] is True
        assert body["comparisons_remaining"] is None


@pytest.mark.asyncio
async def test_pro_status_rollover_resets_used_to_zero():
    """A user whose period_key is stale (e.g. last month) sees `used` reset to 0
    on the next call — this is `_ensure_quota`'s rollover behavior."""
    async with isolated_router_app(comparisons_routes) as ctx:
        user = await _seed_user(ctx.db, used=2, period_key="1999-01")
        comparisons_routes._deps["get_current_user"] = lambda _r: _async_return(user)
        r = await ctx.client.get("/api/users/me/pro-status")
        body = r.json()
        assert body["comparisons_used_this_month"] == 0
        assert body["comparisons_remaining"] == 3
        # The DB doc should now have the current period_key
        doc = await ctx.db.users.find_one({"_id": ObjectId(user["_id"])})
        assert doc["comparisons_used_this_month"] == 0


@pytest.mark.asyncio
async def test_admin_pro_toggle_non_admin_403():
    async with isolated_router_app(comparisons_routes) as ctx:
        target = await _seed_user(ctx.db, email="target@example.com")
        non_admin = await _seed_user(ctx.db, email="someone@else.com")
        comparisons_routes._deps["get_current_user"] = lambda _r: _async_return(non_admin)
        r = await ctx.client.post(
            f"/api/admin/users/{target['_id']}/pro",
            json={"is_pro": True},
        )
        assert r.status_code == 403


@pytest.mark.asyncio
async def test_admin_pro_toggle_admin_succeeds():
    async with isolated_router_app(comparisons_routes) as ctx:
        admin_email = os.environ.get("ADMIN_EMAIL", os.environ.get("ADMIN_EMAIL", "admin@e2e.dynastydreams.com"))
        admin = await _seed_user(ctx.db, email=admin_email)
        target = await _seed_user(ctx.db, email="target@example.com", is_pro=False)
        comparisons_routes._deps["get_current_user"] = lambda _r: _async_return(admin)

        r = await ctx.client.post(
            f"/api/admin/users/{target['_id']}/pro",
            json={"is_pro": True},
        )
        assert r.status_code == 200, r.text
        assert r.json()["is_pro"] is True
        doc = await ctx.db.users.find_one({"_id": ObjectId(target["_id"])})
        assert doc["is_pro"] is True


@pytest.mark.asyncio
async def test_admin_pro_toggle_invalid_user_id():
    async with isolated_router_app(comparisons_routes) as ctx:
        admin = await _seed_user(ctx.db, email=os.environ.get("ADMIN_EMAIL", os.environ.get("ADMIN_EMAIL", "admin@e2e.dynastydreams.com")))
        comparisons_routes._deps["get_current_user"] = lambda _r: _async_return(admin)
        r = await ctx.client.post(
            "/api/admin/users/not-a-real-id/pro",
            json={"is_pro": True},
        )
        assert r.status_code == 400


# ─── Helpers ────────────────────────────────────────────


async def _async_return(value):
    return value
