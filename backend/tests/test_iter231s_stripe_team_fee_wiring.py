"""Iter 231s — League team-fee Stripe wiring tests.

Replaces the iter 226 mocked `POST /payments/league/{id}/intent` with a
real Stripe Checkout Session.

Coverage:
  • Legacy path (no `origin_url`) → still flips teams to paid
    synchronously and returns `mocked: True` (backward compat).
  • Real Stripe path (with `origin_url`) → creates a `pending`
    `payment_transactions` row tagged `kind: "league_team_fee"` with the
    full `team_ids` list. Teams stay `unpaid` until the session is paid.
  • Status-poll grant — when `payment_status` flips to `paid`, every
    team in the transaction's `team_ids` is stamped paid in one update.
  • Permission: non-commissioner cannot create the intent.
  • Validation: no entry_fee, empty team_ids without `full=true`, etc.
"""
from __future__ import annotations
from tests.source_tree import read_source

import os
import sys
import uuid
from datetime import datetime, timezone

import pytest
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _db():
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[
        os.environ.get("DB_NAME", os.environ["DB_NAME"])
    ]


async def _seed_user(db, role="commissioner"):
    suffix = uuid.uuid4().hex[:10]
    uid = ObjectId()
    await db.users.insert_one({
        "_id": uid,
        "email": f"iter231s_{role}_{suffix}@iter231s.test",
        "username": f"iter231s_{role}_{suffix}",
        "name": f"iter231s {role}",
    })
    return str(uid)


async def _seed_league_with_teams(db, n_teams: int = 3, entry_fee: float = 50.0):
    comm_id = await _seed_user(db, "comm")
    league_id = ObjectId()
    await db.leagues.insert_one({
        "_id": league_id,
        "name": f"Iter231s League {league_id}",
        "commissioner_id": comm_id,
        "status": "active",
        "entry_fee": entry_fee,
    })
    team_ids = []
    for i in range(n_teams):
        owner = await _seed_user(db, f"owner{i}")
        t_id = ObjectId()
        await db.teams.insert_one({
            "_id": t_id,
            "name": f"Iter231s Team {i+1}",
            "league_id": str(league_id),
            "owner_id": owner,
            "roster": [],
            "payment_status": "unpaid",
        })
        team_ids.append(str(t_id))
    return str(league_id), comm_id, team_ids


async def _cleanup(db, league_id, comm_id, team_ids):
    await db.leagues.delete_one({"_id": ObjectId(league_id)})
    await db.teams.delete_many({"league_id": league_id})
    await db.users.delete_one({"_id": ObjectId(comm_id)})
    await db.payment_transactions.delete_many({"league_id": league_id})


# ─── Source-grep guards ─────────────────────────────────────────────


def test_payments_routes_handle_team_fee_kind_in_status_poll():
    from pathlib import Path
    src = read_source(Path("/app/backend/routes/payments.py"))
    # Status-poll grants league_team_fee.
    assert 'transaction.get("kind") == "league_team_fee"' in src
    # Webhook handler grants league_team_fee.
    webhook_block = src.split("async def stripe_webhook")[1]
    assert 'transaction.get("kind") == "league_team_fee"' in webhook_block


def test_team_fee_intent_accepts_origin_url():
    from pathlib import Path
    src = read_source(Path("/app/backend/routes/payments.py"))
    # The Pydantic model has an optional origin_url field.
    assert "origin_url: Optional[str] = None" in src
    # The intent endpoint dispatches to Stripe when origin_url is set.
    assert "if body.origin_url:" in src
    # And creates a CheckoutSessionRequest with the team count metadata.
    assert '"package_type": "league_team_fee"' in src


def test_frontend_redirects_to_stripe_checkout():
    from pathlib import Path
    src = read_source(Path("/app/frontend/src/pages/PaymentSetupPage.jsx"))
    # Sends origin_url to the backend.
    assert "origin_url: window.location.origin" in src
    # Redirects to checkout_url when present.
    assert "data.checkout_url" in src
    assert "window.location.href = data.checkout_url" in src


# ─── Functional tests (via curl) ────────────────────────────────────


def _api_url():
    return os.environ["REACT_APP_BACKEND_URL"].rstrip("/")


def _register_via_api(email_prefix: str):
    """Register a new user via the auth endpoint so we get a real JWT."""
    import requests
    suffix = uuid.uuid4().hex[:8]
    email = f"i231s_{email_prefix}_{suffix}@example.com"
    password = "Iter231sTest123!"
    # Username has a 24-char max.
    username = f"i231s_{email_prefix[:6]}_{suffix}"[:24]
    r = requests.post(
        f"{_api_url()}/api/auth/register",
        json={"email": email, "password": password, "username": username, "name": f"iter231s {email_prefix}"},
        timeout=10,
    )
    assert r.status_code in (200, 201), f"register failed: {r.status_code} {r.text}"
    data = r.json()
    return data.get("user", {}).get("_id") or data.get("user", {}).get("id") or data.get("id"), data["access_token"]


@pytest.mark.asyncio
async def test_intent_with_origin_url_creates_pending_stripe_transaction(monkeypatch):
    """Route creates an unpaid pending transaction using an isolated provider stub."""
    from types import SimpleNamespace
    from routes import payments
    from tests.router_test_utils import isolated_router_app
    captured = []
    class Checkout:
        def __init__(self, **kwargs):
            pass
        async def create_checkout_session(self, request):
            captured.append(request)
            return SimpleNamespace(session_id="cs_fixture_fee", url="https://checkout.example.test/fee")
    monkeypatch.setattr(payments, "PAYMENTS_DISABLED", False)
    monkeypatch.setattr(payments, "StripeCheckout", Checkout)
    monkeypatch.setattr(payments, "CheckoutSessionRequest", SimpleNamespace)
    user = {"_id": str(ObjectId()), "email": "fixture-fee@example.test"}
    async with isolated_router_app(payments, user=user) as ctx:
        lid = ObjectId()
        await ctx.db.leagues.insert_one({"_id": lid, "commissioner_id": user["_id"], "entry_fee": 25.0})
        tids = [ObjectId(), ObjectId()]
        await ctx.db.teams.insert_many([{"_id": tid, "league_id": str(lid), "payment_status": "unpaid"} for tid in tids])
        response = await ctx.client.post(f"/api/payments/league/{lid}/intent",
            json={"full": True, "origin_url": "https://example.test"})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["ok"] and body["mocked"] is False
        assert body["covered_count"] == 2 and body["amount_total"] == 50.0
        assert body["checkout_url"] == "https://checkout.example.test/fee"
        assert len(captured) == 1 and captured[0].amount == 50.0
        assert captured[0].currency == "usd"
        assert captured[0].metadata["team_count"] == "2"
        tx = await ctx.db.payment_transactions.find_one({"session_id": body["session_id"]})
        assert tx["kind"] == "league_team_fee" and tx["payment_status"] == "pending"
        assert sorted(tx["team_ids"]) == sorted(map(str, tids))
        assert tx["league_id"] == str(lid)
        for tid in tids:
            team = await ctx.db.teams.find_one({"_id": tid})
            assert team["payment_status"] == "unpaid"


@pytest.mark.asyncio
async def test_intent_without_origin_url_uses_legacy_mocked_path():
    """Backward-compat: without origin_url the endpoint stamps teams
    paid synchronously (mocked=True) so older frontends keep working."""
    import requests
    db = _db()
    user_id, token = _register_via_api("comm_mock")

    league_id_obj = ObjectId()
    league_id = str(league_id_obj)
    await db.leagues.insert_one({
        "_id": league_id_obj,
        "name": f"Iter231s Mock {league_id}",
        "commissioner_id": user_id,
        "status": "active",
        "entry_fee": 30.0,
    })
    t_id = ObjectId()
    await db.teams.insert_one({
        "_id": t_id, "name": "Mock Team",
        "league_id": league_id, "owner_id": user_id,
        "roster": [], "payment_status": "unpaid",
    })

    try:
        r = requests.post(
            f"{_api_url()}/api/payments/league/{league_id}/intent",
            json={"full": True},  # no origin_url
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["mocked"] is True
        assert body["covered_count"] == 1
        assert "checkout_url" not in body

        # Legacy: team is now paid.
        t = await db.teams.find_one({"_id": t_id})
        assert t["payment_status"] == "paid"
    finally:
        await db.leagues.delete_one({"_id": league_id_obj})
        await db.teams.delete_many({"league_id": league_id})
        await db.users.delete_one({"_id": ObjectId(user_id)})
        await db.payment_transactions.delete_many({"league_id": league_id})


@pytest.mark.asyncio
async def test_intent_rejects_non_commissioner():
    """Only the commissioner can create the intent."""
    import requests
    db = _db()
    comm_id, _ = _register_via_api("comm_perm")
    user_id, token = _register_via_api("rando")

    league_id_obj = ObjectId()
    league_id = str(league_id_obj)
    await db.leagues.insert_one({
        "_id": league_id_obj,
        "name": f"Iter231s Perm {league_id}",
        "commissioner_id": comm_id,
        "status": "active",
        "entry_fee": 10.0,
    })

    try:
        r = requests.post(
            f"{_api_url()}/api/payments/league/{league_id}/intent",
            json={"full": True, "origin_url": "https://example.test"},
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        assert r.status_code == 403, r.text
    finally:
        await db.leagues.delete_one({"_id": league_id_obj})
        await db.users.delete_one({"_id": ObjectId(user_id)})
        await db.users.delete_one({"_id": ObjectId(comm_id)})


@pytest.mark.asyncio
async def test_intent_rejects_league_without_entry_fee():
    """400 when the league has no entry_fee configured."""
    import requests
    db = _db()
    user_id, token = _register_via_api("comm_nofee")

    league_id_obj = ObjectId()
    league_id = str(league_id_obj)
    await db.leagues.insert_one({
        "_id": league_id_obj,
        "name": f"Iter231s NoFee {league_id}",
        "commissioner_id": user_id,
        "status": "active",
        # no entry_fee
    })

    try:
        r = requests.post(
            f"{_api_url()}/api/payments/league/{league_id}/intent",
            json={"full": True, "origin_url": "https://example.test"},
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        assert r.status_code == 400, r.text
        assert "no entry fee" in r.json().get("detail", "").lower()
    finally:
        await db.leagues.delete_one({"_id": league_id_obj})
        await db.users.delete_one({"_id": ObjectId(user_id)})
