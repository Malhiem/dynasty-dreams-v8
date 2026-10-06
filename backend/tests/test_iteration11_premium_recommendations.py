"""Iteration 11 backend tests — Dynasty Dreams Phase 11.

Tests:
  * League Premium metadata endpoint (GET /api/leagues/{id}/premium)
  * Stripe checkout creation for league_premium + legacy packages
  * Authorization (commissioner-only) and validation (400/404)
  * Simulated paid payment — directly mutates Mongo payment_status=paid and
    validates the status handler flips the league premium flag + logs activity
  * Recommendations endpoint — preference scoring, has_active_leagues flag,
    private/full leagues excluded
  * Regression: 5 demo leagues + admin auth still working
"""

import os
import time
import uuid
import pytest
import requests
from pymongo import MongoClient
from bson import ObjectId

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
# For mongo access we rely on backend MONGO_URL / DB_NAME
from dotenv import load_dotenv
load_dotenv("/app/backend/.env")
MONGO_URL = os.environ.get("MONGO_URL")
DB_NAME = os.environ.get("DB_NAME")

if not BASE_URL:
    pytest.skip("REACT_APP_BACKEND_URL missing", allow_module_level=True)

ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@e2e.dynastydreams.com")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "e2e-admin-password")


# ───────────────────────── Fixtures ─────────────────────────

@pytest.fixture(scope="module")
def mongo_db():
    client = MongoClient(MONGO_URL)
    yield client[DB_NAME]
    client.close()


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def other_user_session():
    """Create a fresh non-commissioner user and return a logged-in session."""
    s = requests.Session()
    email = f"TEST_other_{uuid.uuid4().hex[:6]}@example.com"
    password = "TestPass123!"
    r = s.post(f"{BASE_URL}/api/auth/register",
               json={"username": "fixture_" + uuid.uuid4().hex[:16], "email": email, "password": password,
                     "name": f"Tester {uuid.uuid4().hex[:4]}"})
    assert r.status_code in (200, 201), f"register failed: {r.status_code} {r.text}"
    # register typically auto-logs in; ensure cookie
    if "access_token" not in s.cookies:
        r2 = s.post(f"{BASE_URL}/api/auth/login",
                    json={"email": email, "password": password})
        assert r2.status_code == 200
    return s, email


@pytest.fixture(scope="module")
def admin_commissioner_league(admin_session, mongo_db):
    """Pick the first league where admin is commissioner."""
    me = admin_session.get(f"{BASE_URL}/api/auth/me").json()
    admin_id = me["id"]
    lg = mongo_db.leagues.find_one({"commissioner_id": admin_id, "premium": {"$ne": True}})
    assert lg, "Admin should have at least one non-premium league"
    return str(lg["_id"])


import pytest_asyncio
from types import SimpleNamespace

@pytest_asyncio.fixture
async def payment_provider_ctx(monkeypatch):
    from routes import payments
    from tests.router_test_utils import isolated_router_app
    state = {"payment_status": "unpaid"}
    captured = []
    session_id = "cs_fixture_" + uuid.uuid4().hex
    class Checkout:
        def __init__(self, **kwargs):
            pass
        async def create_checkout_session(self, request):
            captured.append(request)
            return SimpleNamespace(session_id=session_id, url="https://checkout.example.com/fixture")
        async def get_checkout_status(self, selected):
            assert selected == session_id
            return SimpleNamespace(status="complete", payment_status=state["payment_status"], amount_total=29.99, currency="usd")
    monkeypatch.setattr(payments, "PAYMENTS_DISABLED", False)
    monkeypatch.setattr(payments, "StripeCheckout", Checkout)
    monkeypatch.setattr(payments, "CheckoutSessionRequest", SimpleNamespace)
    user = {"_id": str(ObjectId()), "role": "admin", "email": ADMIN_EMAIL}
    async with isolated_router_app(payments, user=user) as ctx:
        lid = ObjectId()
        await ctx.db.leagues.insert_one({"_id": lid, "commissioner_id": user["_id"], "premium": False})
        yield ctx, state, str(lid), captured

@pytest.fixture(scope="module", autouse=True)
def open_recommendation_inputs(_global_pollution_sweep, mongo_db):
    assert os.environ.get("TEST_SUITE_ISOLATED") == "1"
    inserted = mongo_db.leagues.insert_one({"name": "Fixture Frozen Match", "commissioner_id": str(ObjectId()),
        "format": "dynasty", "scoring_format": "head_to_head", "draft_type": "auction", "max_teams": 12,
        "current_teams": 0, "is_private": False, "sport": "nhl", "status": "drafting"})
    yield
    mongo_db.leagues.delete_one({"_id": inserted.inserted_id})


# ───────────────────────── 1. League Premium GET ─────────────────────────

class TestLeaguePremiumGet:
    def test_premium_metadata_fresh_league(self, admin_session, admin_commissioner_league):
        r = admin_session.get(f"{BASE_URL}/api/leagues/{admin_commissioner_league}/premium")
        assert r.status_code == 200
        data = r.json()
        assert data["premium"] is False
        assert data["price_usd"] == 29.99
        assert isinstance(data["features"], list) and len(data["features"]) == 6
        feature_ids = [f["id"] for f in data["features"]]
        assert set(feature_ids) == {
            "salary_cap", "contracts", "draft_scheduling",
            "minor_leagues", "custom_scoring", "activity_webhooks"
        }
        assert data["unlocked_features"] == []

    def test_premium_metadata_not_found(self, admin_session):
        fake_id = str(ObjectId())
        r = admin_session.get(f"{BASE_URL}/api/leagues/{fake_id}/premium")
        assert r.status_code == 404


# ───────────────────────── 2. Payments create ─────────────────────────

class TestPaymentsCreate:
    @pytest.mark.asyncio
    async def test_league_premium_success(self, payment_provider_ctx):
        ctx, state, lid, captured = payment_provider_ctx
        response = await ctx.client.post("/api/payments/create", json={"package_type": "league_premium", "league_id": lid, "origin_url": "https://example.com"})
        assert response.status_code == 200, response.text
        assert response.json()["url"].startswith("https://checkout.example.com/")
        assert captured[0].amount == 29.99
        transaction = await ctx.db.payment_transactions.find_one({"session_id": response.json()["session_id"]})
        assert transaction["payment_status"] == "pending"

    def test_league_premium_missing_league_id(self, admin_session):
        r = admin_session.post(f"{BASE_URL}/api/payments/create", json={
            "package_type": "league_premium",
            "origin_url": "https://example.com"
        })
        assert r.status_code == 400
        assert "league_id" in r.text.lower()

    def test_league_premium_non_commissioner_403(self, other_user_session, admin_commissioner_league):
        s, _email = other_user_session
        r = s.post(f"{BASE_URL}/api/payments/create", json={
            "package_type": "league_premium",
            "league_id": admin_commissioner_league,
            "origin_url": "https://example.com"
        })
        assert r.status_code == 403

    def test_league_premium_already_premium_400(self, admin_session, mongo_db):
        # Create a temp league that is already premium
        me = admin_session.get(f"{BASE_URL}/api/auth/me").json()
        doc = {
            "name": f"TEST_PremiumAlready_{uuid.uuid4().hex[:6]}",
            "commissioner_id": me["id"],
            "format": "dynasty", "scoring_format": "head_to_head", "draft_type": "snake",
            "max_teams": 12, "current_teams": 0, "is_private": False, "premium": True,
            "sport": "nhl", "status": "drafting"
        }
        ins = mongo_db.leagues.insert_one(doc)
        try:
            r = admin_session.post(f"{BASE_URL}/api/payments/create", json={
                "package_type": "league_premium",
                "league_id": str(ins.inserted_id),
                "origin_url": "https://example.com"
            })
            assert r.status_code == 400
            assert "already" in r.text.lower()
        finally:
            mongo_db.leagues.delete_one({"_id": ins.inserted_id})

    @pytest.mark.asyncio
    async def test_premium_monthly_still_works(self, payment_provider_ctx):
        ctx, state, lid, captured = payment_provider_ctx
        response = await ctx.client.post("/api/payments/create", json={"package_type": "premium_monthly", "origin_url": "https://example.com"})
        assert response.status_code == 200, response.text
        assert captured[0].amount == 9.99

    @pytest.mark.asyncio
    async def test_premium_yearly_still_works(self, payment_provider_ctx):
        ctx, state, lid, captured = payment_provider_ctx
        response = await ctx.client.post("/api/payments/create", json={"package_type": "premium_yearly", "origin_url": "https://example.com"})
        assert response.status_code == 200, response.text
        assert captured[0].amount == 79.99

    def test_invalid_package_type_400(self, admin_session):
        r = admin_session.post(f"{BASE_URL}/api/payments/create", json={
            "package_type": "nonsense",
            "origin_url": "https://example.com"
        })
        assert r.status_code == 400


# ───────────────────────── 3. Simulated paid flow ─────────────────────────

class TestSimulatedPaidFlow:
    @pytest.mark.asyncio
    async def test_mutate_to_paid_flips_premium(self, payment_provider_ctx):
        ctx, state, lid, captured = payment_provider_ctx
        response = await ctx.client.post("/api/payments/create", json={"package_type": "league_premium", "league_id": lid, "origin_url": "https://example.com"})
        assert response.status_code == 200, response.text
        session_id = response.json()["session_id"]
        assert (await ctx.db.leagues.find_one({"_id": ObjectId(lid)}))["premium"] is False
        state["payment_status"] = "paid"
        for _ in range(2):
            paid = await ctx.client.get(f"/api/payments/status/{session_id}")
            assert paid.status_code == 200, paid.text
            assert paid.json()["payment_status"] == "paid"
        league = await ctx.db.leagues.find_one({"_id": ObjectId(lid)})
        assert league["premium"] is True and len(league["premium_features"]) == 6
        assert len([call for call in ctx.activity_calls if call["event_type"] == "league_premium_unlocked"]) == 1


# ───────────────────────── 4. Recommendations ─────────────────────────

class TestRecommendations:
    def test_any_any_any_returns_open_leagues(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/recommendations/leagues",
                              params={"commitment": "any", "scoring": "any", "draft_style": "any"})
        assert r.status_code == 200
        body = r.json()
        assert "recommendations" in body
        assert "has_active_leagues" in body
        assert body["preferences"] == {"commitment": "any", "scoring": "any", "draft_style": "any"}
        # Every returned league must have room
        for rec in body["recommendations"]:
            if not rec.get("is_own"):
                assert rec["current_teams"] < rec["max_teams"]

    def test_hardcore_head_to_head_auction_ranks_frozen_dynasty_top(self, admin_session, mongo_db):
        # Make sure a "Frozen Dynasty" style league exists
        existing = mongo_db.leagues.find_one({"name": "Fixture Frozen Match"})
        cleanup_needed = False
        if not existing:
            # Seed one for the test
            me = admin_session.get(f"{BASE_URL}/api/auth/me").json()
            mongo_db.leagues.insert_one({
                "name": "Frozen Dynasty",
                "commissioner_id": me["id"],
                "format": "dynasty", "scoring_format": "head_to_head", "draft_type": "auction",
                "max_teams": 12, "current_teams": 0, "is_private": False,
                "sport": "nhl", "status": "drafting"
            })
            cleanup_needed = True

        try:
            r = admin_session.get(f"{BASE_URL}/api/recommendations/leagues",
                                  params={"commitment": "hardcore", "scoring": "head_to_head",
                                          "draft_style": "auction"})
            assert r.status_code == 200
            recs = r.json()["recommendations"]
            # First non-own rec should be Frozen Dynasty with score 100 (40+30+20+10)
            non_own = [r_ for r_ in recs if not r_.get("is_own")]
            assert non_own, "Expected at least one non-own recommendation"
            top = non_own[0]
            assert top["name"] == "Fixture Frozen Match", f"Top was {top['name']}"
            assert top["match_score"] == 100
            reason = top["match_reason"].lower()
            assert "hardcore" in reason
            assert "head to head" in reason
            assert "auction" in reason
        finally:
            if cleanup_needed:
                mongo_db.leagues.delete_one({"name": "Frozen Dynasty"})

    def test_user_own_league_first_and_has_active_flag(self, admin_session, mongo_db):
        """Create a fresh user, join them to a league, verify has_active_leagues=true
        and their league is ranked first with is_own=true."""
        s = requests.Session()
        email = f"TEST_own_{uuid.uuid4().hex[:6]}@example.com"
        pwd = "TestPass123!"
        reg = s.post(f"{BASE_URL}/api/auth/register", json={"username": "fixture_" + uuid.uuid4().hex[:16],
            "email": email, "password": pwd,
            "name": f"Own Tester {uuid.uuid4().hex[:4]}"
        })
        assert reg.status_code in (200, 201)
        # ensure logged in
        if "access_token" not in s.cookies:
            lg_r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": pwd})
            assert lg_r.status_code == 200
        me = s.get(f"{BASE_URL}/api/auth/me").json()
        user_id = me["id"]

        # Find an open league with room
        lg = mongo_db.leagues.find_one({
            "is_private": {"$ne": True},
            "$expr": {"$lt": ["$current_teams", "$max_teams"]}
        })
        assert lg, "Need an open league for this test"
        league_id = str(lg["_id"])

        # Insert a team for this user in that league directly (shortcut)
        team_id = mongo_db.teams.insert_one({
            "name": f"TEST_team_{uuid.uuid4().hex[:6]}",
            "owner_id": user_id,
            "owner_name": me.get("username", "tester"),
            "league_id": league_id,
            "roster": [],
        }).inserted_id

        try:
            r = s.get(f"{BASE_URL}/api/recommendations/leagues")
            assert r.status_code == 200
            body = r.json()
            assert body["has_active_leagues"] is True
            recs = body["recommendations"]
            assert recs[0]["is_own"] is True
            assert recs[0]["id"] == league_id
            assert recs[0]["match_score"] == 100
        finally:
            mongo_db.teams.delete_one({"_id": team_id})

    def test_excludes_private_and_full_leagues(self, admin_session, mongo_db):
        me = admin_session.get(f"{BASE_URL}/api/auth/me").json()
        # Create a private league and a full league
        priv = mongo_db.leagues.insert_one({
            "name": f"TEST_Private_{uuid.uuid4().hex[:6]}",
            "commissioner_id": me["id"], "format": "dynasty",
            "scoring_format": "head_to_head", "draft_type": "snake",
            "max_teams": 12, "current_teams": 0, "is_private": True,
            "sport": "nhl",
        }).inserted_id
        full = mongo_db.leagues.insert_one({
            "name": f"TEST_Full_{uuid.uuid4().hex[:6]}",
            "commissioner_id": me["id"], "format": "dynasty",
            "scoring_format": "head_to_head", "draft_type": "snake",
            "max_teams": 12, "current_teams": 12, "is_private": False,
            "sport": "nhl",
        }).inserted_id
        try:
            r = admin_session.get(f"{BASE_URL}/api/recommendations/leagues",
                                  params={"limit": 20})
            assert r.status_code == 200
            names = [rec["name"] for rec in r.json()["recommendations"] if not rec.get("is_own")]
            assert not any(n.startswith("TEST_Private_") for n in names)
            assert not any(n.startswith("TEST_Full_") for n in names)
        finally:
            mongo_db.leagues.delete_one({"_id": priv})
            mongo_db.leagues.delete_one({"_id": full})


# ───────────────────────── 5. Regression ─────────────────────────

class TestRegression:
    def test_admin_login_still_works(self):
        s = requests.Session()
        r = s.post(f"{BASE_URL}/api/auth/login",
                   json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        assert r.status_code == 200
        assert "access_token" in s.cookies

    def test_leagues_listing(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/leagues")
        assert r.status_code == 200
        leagues = r.json()
        assert isinstance(leagues, list)
        assert len(leagues) >= 5, f"Expected 5+ demo leagues, got {len(leagues)}"
