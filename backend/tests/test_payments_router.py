"""Focused unit tests for the new payments router (iter 98).

These cover the validation surface (which doesn't require a real Stripe
key). The actual StripeCheckout calls would hit a network — we stub
those out via dep injection.
"""
import os
import sys
from datetime import datetime, timezone

import pytest
from bson import ObjectId

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from routes import payments as payments_routes  # noqa: E402

from tests.router_test_utils import isolated_router_app  # noqa: E402


@pytest.mark.asyncio
async def test_create_400_for_invalid_package_type():
    async with isolated_router_app(payments_routes) as ctx:
        payments_routes._deps["_safe_object_id"] = lambda v, l="id": ObjectId(v)
        payments_routes._deps["log_activity"] = lambda *a, **kw: None
        r = await ctx.client.post(
            "/api/payments/create",
            json={"package_type": "bogus", "origin_url": "https://x.com"},
        )
        assert r.status_code == 400
        assert "Invalid package" in r.json()["detail"]


@pytest.mark.asyncio
async def test_create_400_for_league_fee_without_amount():
    """A league without `entry_fee` configured shouldn't be billable."""
    async with isolated_router_app(payments_routes) as ctx:
        payments_routes._deps["_safe_object_id"] = lambda v, l="id": ObjectId(v)
        payments_routes._deps["log_activity"] = lambda *a, **kw: None
        league_res = await ctx.db.leagues.insert_one({"name": "L"})
        r = await ctx.client.post(
            "/api/payments/create",
            json={
                "package_type": "league_fee",
                "league_id": str(league_res.inserted_id),
                "origin_url": "https://x.com",
            },
        )
        assert r.status_code == 400
        assert "no entry fee" in r.json()["detail"]


@pytest.mark.asyncio
async def test_create_403_for_league_premium_non_commish():
    async with isolated_router_app(payments_routes) as ctx:
        payments_routes._deps["_safe_object_id"] = lambda v, l="id": ObjectId(v)
        payments_routes._deps["log_activity"] = lambda *a, **kw: None
        league_res = await ctx.db.leagues.insert_one({
            "name": "L", "commissioner_id": "OTHER_USER",
        })
        r = await ctx.client.post(
            "/api/payments/create",
            json={
                "package_type": "league_premium",
                "league_id": str(league_res.inserted_id),
                "origin_url": "https://x.com",
            },
        )
        assert r.status_code == 403


@pytest.mark.asyncio
async def test_create_400_for_league_premium_already_premium():
    async with isolated_router_app(payments_routes) as ctx:
        payments_routes._deps["_safe_object_id"] = lambda v, l="id": ObjectId(v)
        payments_routes._deps["log_activity"] = lambda *a, **kw: None
        league_res = await ctx.db.leagues.insert_one({
            "name": "L", "commissioner_id": "test_user_0001", "premium": True,
        })
        r = await ctx.client.post(
            "/api/payments/create",
            json={
                "package_type": "league_premium",
                "league_id": str(league_res.inserted_id),
                "origin_url": "https://x.com",
            },
        )
        assert r.status_code == 400
        assert "already premium" in r.json()["detail"]


@pytest.mark.asyncio
async def test_status_404_for_unknown_session():
    async with isolated_router_app(payments_routes) as ctx:
        payments_routes._deps["_safe_object_id"] = lambda v, l="id": ObjectId(v)
        payments_routes._deps["log_activity"] = lambda *a, **kw: None
        r = await ctx.client.get("/api/payments/status/no-such-session")
        assert r.status_code == 404


@pytest.mark.asyncio
async def test_status_403_for_other_users_session():
    async with isolated_router_app(payments_routes) as ctx:
        payments_routes._deps["_safe_object_id"] = lambda v, l="id": ObjectId(v)
        payments_routes._deps["log_activity"] = lambda *a, **kw: None
        await ctx.db.payment_transactions.insert_one({
            "session_id": "sess_other",
            "user_id": "someone_else",
            "email": "x@y.com",
            "amount": 9.99,
            "payment_status": "pending",
        })
        r = await ctx.client.get("/api/payments/status/sess_other")
        assert r.status_code == 403


def test_payment_packages_catalogue_shape():
    """Sanity check: the catalogue is the single source of truth and must
    be wired before any handler can run."""
    pkgs = payments_routes.PAYMENT_PACKAGES
    assert "premium_monthly" in pkgs
    assert "premium_yearly" in pkgs
    assert "league_fee" in pkgs
    assert "league_premium" in pkgs
    # Prices are floats (never strings — Stripe Checkout requires numerics)
    for pkg in pkgs.values():
        assert isinstance(pkg["amount"], (int, float))
        assert isinstance(pkg["name"], str)


def test_league_premium_features_shape():
    features = payments_routes.LEAGUE_PREMIUM_FEATURES
    # Each row is a dict with id/name/description
    assert all({"id", "name", "description"} <= set(f.keys()) for f in features)
    assert {"salary_cap", "contracts"} <= {f["id"] for f in features}
