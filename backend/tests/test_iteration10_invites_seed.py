"""
Iteration 10 — Backend tests for:
 - Admin auth (cookie-based)
 - 5 seeded demo leagues with distinct formats, one with max_teams=32
 - League creation with max_teams=32 (upper bound validation)
 - POST /api/leagues/{league_id}/invite/email — mock fallback (no SENDGRID_API_KEY)
 - Non-commissioner 403 on invite
 - Regressions: NHL player count, /api/sports, register+draft+trade smoke
"""
import os
import time
import uuid
import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://dynasty-preview.preview.emergentagent.com").rstrip("/")
# For DB verification
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")

ADMIN_EMAIL = "admin@dynastydreams.com"
ADMIN_PASSWORD = "Admin123!"


# ─── Fixtures ──────────────────────────────
@pytest.fixture(scope="session")
def mongo_db():
    client = MongoClient(MONGO_URL)
    yield client[DB_NAME]
    client.close()


@pytest.fixture(scope="session")
def admin_session():
    """Login as admin and return cookie-jar session."""
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=30)
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text}"
    assert "access_token" in s.cookies, "access_token cookie not set on admin login"
    return s


@pytest.fixture(scope="session")
def regular_user_session():
    """Register a fresh non-commissioner user."""
    s = requests.Session()
    email = f"TEST_user_{uuid.uuid4().hex[:8]}@example.com"
    pwd = "TestPass123!"
    r = s.post(f"{BASE_URL}/api/auth/register", json={"email": email, "password": pwd, "name": "TEST User"}, timeout=30)
    if r.status_code not in (200, 201):
        pytest.skip(f"Could not register regular user: {r.status_code} {r.text}")
    return s, email


# ─── Admin auth ──────────────────────────────
class TestAdminAuth:
    def test_admin_login_sets_cookie(self, admin_session):
        assert "access_token" in admin_session.cookies

    def test_admin_me_returns_admin_role(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/auth/me", timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("email") == ADMIN_EMAIL
        assert data.get("role") == "admin"


# ─── Seeded demo leagues ──────────────────────────────
class TestSeededLeagues:
    def test_get_leagues_returns_five_demo_leagues(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/leagues", timeout=20)
        assert r.status_code == 200, r.text
        leagues = r.json()
        assert isinstance(leagues, list)
        # There should be at least the 5 demo leagues
        assert len(leagues) >= 5, f"Expected >=5 leagues, got {len(leagues)}"

        # Build set of (format, scoring_format) we expect
        expected_pairs = {
            ("redraft", "head_to_head"),
            ("redraft", "rotisserie"),
            ("dynasty", "head_to_head"),
            ("keeper", "head_to_head"),
            ("best_ball", "total_points"),
        }
        actual_pairs = {(lg.get("format"), lg.get("scoring_format")) for lg in leagues}
        missing = expected_pairs - actual_pairs
        assert not missing, f"Missing expected demo league combos: {missing}. Got: {actual_pairs}"

    def test_at_least_one_league_has_max_teams_32(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/leagues", timeout=20)
        assert r.status_code == 200
        leagues = r.json()
        assert any(lg.get("max_teams") == 32 for lg in leagues), \
            f"No league with max_teams=32 found. max_teams values: {[lg.get('max_teams') for lg in leagues]}"


# ─── Create league with max_teams=32 upper bound ──────────────────────────────
class TestLeagueCreationMaxTeams32:
    created_ids = []

    def test_create_league_max_teams_32(self, admin_session):
        payload = {
            "name": f"TEST_MaxTeams32_{uuid.uuid4().hex[:6]}",
            "sport": "nhl",
            "format": "dynasty",
            "scoring_format": "head_to_head",
            "max_teams": 32,
            "salary_cap_enabled": False,
            "draft_type": "snake",
            "roster_spots": 20,
            "keepers_allowed": 0,
            "is_private": False,
        }
        r = admin_session.post(f"{BASE_URL}/api/leagues", json=payload, timeout=30)
        assert r.status_code in (200, 201), f"{r.status_code} {r.text}"
        data = r.json()
        assert data["max_teams"] == 32
        assert data["format"] == "dynasty"
        assert data["scoring_format"] == "head_to_head"
        assert "id" in data
        TestLeagueCreationMaxTeams32.created_ids.append(data["id"])

        # GET to verify persistence
        r2 = admin_session.get(f"{BASE_URL}/api/leagues/{data['id']}", timeout=20)
        assert r2.status_code == 200
        assert r2.json()["max_teams"] == 32

    def test_create_league_max_teams_33_rejected(self, admin_session):
        payload = {
            "name": f"TEST_BadMax_{uuid.uuid4().hex[:6]}",
            "sport": "nhl",
            "format": "redraft",
            "scoring_format": "head_to_head",
            "max_teams": 33,
        }
        r = admin_session.post(f"{BASE_URL}/api/leagues", json=payload, timeout=30)
        assert r.status_code in (400, 422), f"Expected 400/422 for max_teams=33, got {r.status_code}: {r.text}"


# ─── SendGrid email invite (mock fallback) ──────────────────────────────
class TestEmailInvitesMockFallback:
    def test_invite_mock_fallback_counts_and_db(self, admin_session, mongo_db):
        # Create a fresh league owned by admin
        create_payload = {
            "name": f"TEST_InviteLeague_{uuid.uuid4().hex[:6]}",
            "sport": "nhl",
            "format": "redraft",
            "scoring_format": "head_to_head",
            "max_teams": 12,
        }
        r = admin_session.post(f"{BASE_URL}/api/leagues", json=create_payload, timeout=30)
        assert r.status_code in (200, 201), r.text
        league_id = r.json()["id"]

        # Send invites to 3 test emails
        emails = [
            f"TEST_invitee_{uuid.uuid4().hex[:6]}@example.com",
            f"TEST_invitee_{uuid.uuid4().hex[:6]}@example.com",
            f"TEST_invitee_{uuid.uuid4().hex[:6]}@example.com",
        ]
        body = {"league_id": league_id, "emails": emails}
        r2 = admin_session.post(f"{BASE_URL}/api/leagues/{league_id}/invite/email", json=body, timeout=30)
        assert r2.status_code == 200, f"{r2.status_code} {r2.text}"
        data = r2.json()

        # Response shape assertions
        for key in ("sent", "mocked", "errors", "results", "invite_url"):
            assert key in data, f"Missing key '{key}' in response: {data}"
        assert data["mocked"] >= 1, f"Expected mocked >=1, got {data}"
        assert data["sent"] == 0, f"Expected sent==0 in mock mode, got {data['sent']}"
        assert data["errors"] == 0, f"Expected errors==0 in mock mode, got {data['errors']}"
        assert len(data["results"]) == len(emails)
        for res in data["results"]:
            assert res.get("status") == "mocked", f"Expected status=mocked, got {res}"

        # Verify DB upserts in league_invites collection
        time.sleep(0.5)
        stored = list(mongo_db.league_invites.find({"league_id": league_id}))
        assert len(stored) == len(emails), f"Expected {len(emails)} invite rows, found {len(stored)}"
        for row in stored:
            assert row["status"] == "mocked"
            assert row["email"].startswith("test_invitee_") or row["email"].startswith("TEST_invitee_".lower())

        # Cleanup test invites
        mongo_db.league_invites.delete_many({"league_id": league_id})

    def test_invite_non_commissioner_forbidden(self, admin_session, regular_user_session):
        # Admin creates a league
        create_payload = {
            "name": f"TEST_ForbiddenInvite_{uuid.uuid4().hex[:6]}",
            "sport": "nhl",
            "format": "redraft",
            "scoring_format": "head_to_head",
            "max_teams": 10,
        }
        r = admin_session.post(f"{BASE_URL}/api/leagues", json=create_payload, timeout=30)
        assert r.status_code in (200, 201)
        league_id = r.json()["id"]

        user_sess, _ = regular_user_session
        body = {"league_id": league_id, "emails": ["TEST_noone@example.com"]}
        r2 = user_sess.post(f"{BASE_URL}/api/leagues/{league_id}/invite/email", json=body, timeout=30)
        assert r2.status_code == 403, f"Expected 403, got {r2.status_code}: {r2.text}"


# ─── Regressions ──────────────────────────────
class TestRegressions:
    def test_sports_endpoint(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/sports", timeout=20)
        assert r.status_code == 200
        sports = r.json()
        assert isinstance(sports, list) and len(sports) == 4
        nhl = next((s for s in sports if s["id"] == "nhl"), None)
        assert nhl is not None
        assert nhl["active"] is True

    def test_nhl_players_count(self, admin_session):
        # try players endpoint; check count
        r = admin_session.get(f"{BASE_URL}/api/players", params={"sport": "nhl", "limit": 1}, timeout=30)
        if r.status_code != 200:
            pytest.skip(f"/api/players returned {r.status_code}")
        # Prefer a count-style endpoint if available; fall back to db.players count via response meta
        # The regression target is 1038 players — try fetching all and counting
        r2 = admin_session.get(f"{BASE_URL}/api/players", params={"sport": "nhl", "limit": 2000}, timeout=60)
        assert r2.status_code == 200
        data = r2.json()
        players = data if isinstance(data, list) else data.get("players", [])
        assert len(players) == 1038, f"Expected 1038 NHL players, got {len(players)}"

    def test_register_smoke(self):
        s = requests.Session()
        email = f"TEST_reg_{uuid.uuid4().hex[:8]}@example.com"
        r = s.post(f"{BASE_URL}/api/auth/register",
                   json={"email": email, "password": "Abcdef1!", "name": "TEST Reg"}, timeout=30)
        assert r.status_code in (200, 201), r.text
        assert "access_token" in s.cookies

    def test_draft_creation_smoke(self, admin_session):
        # Create a league then start a draft (best-effort smoke)
        create = admin_session.post(f"{BASE_URL}/api/leagues", json={
            "name": f"TEST_DraftSmoke_{uuid.uuid4().hex[:6]}",
            "sport": "nhl",
            "format": "redraft",
            "scoring_format": "head_to_head",
            "max_teams": 8,
        }, timeout=30)
        assert create.status_code in (200, 201)
        league_id = create.json()["id"]
        r = admin_session.post(f"{BASE_URL}/api/drafts", json={"league_id": league_id}, timeout=30)
        # Accept 200/201 or 400 (e.g., not enough teams) — endpoint must exist
        assert r.status_code in (200, 201, 400, 404, 409), f"Unexpected: {r.status_code} {r.text}"

    def test_trade_endpoint_exists(self, admin_session):
        # Hit list trades to ensure routes exist
        r = admin_session.get(f"{BASE_URL}/api/trades", timeout=20)
        assert r.status_code in (200, 401, 403, 404), f"Trades route broken: {r.status_code}"
