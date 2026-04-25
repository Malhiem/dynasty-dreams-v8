"""
Iteration 20 — Backend refactor non-regression + mobile-friendly auth.

Covers:
  * routes/awards.py     : PUT /leagues/{id}/teams/{id}/awards (incl. new conference_winner, consolation_won),
                           GET/PUT /leagues/{id}/consolation-prize, GET /leagues/{id}/team-rewards
  * routes/drafts.py     : GET /drafts/{league_id}/picks
  * routes/matchups.py   : GET /matchups/{league_id}, GET current-week, GET results
  * Mobile auth contract : /auth/login + /auth/register return access_token + refresh_token in body
                           /auth/me with Bearer header (no cookies)
                           /auth/refresh with Bearer header
  * Non-regression       : /api/u/chriszarek aggregate trophies payload
"""
import os
import uuid
import requests
import pytest

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@dynastydreams.com"
ADMIN_PASSWORD = "Admin123!"
CHRIS_EMAIL = "chriszarek@gmail.com"
CHRIS_PASSWORD = "Chris2026!"


# ---- fixtures ---------------------------------------------------
@pytest.fixture(scope="module")
def bare_session():
    return requests.Session()


def _login_body(email, password):
    """Login WITHOUT cookie-jar — pure body tokens (mobile flow)."""
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    return r


@pytest.fixture(scope="module")
def admin_tokens():
    r = _login_body(ADMIN_EMAIL, ADMIN_PASSWORD)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    data = r.json()
    assert data.get("access_token"), "access_token missing in admin login response"
    assert data.get("refresh_token"), "refresh_token missing in admin login response"
    return data


@pytest.fixture(scope="module")
def chris_tokens():
    r = _login_body(CHRIS_EMAIL, CHRIS_PASSWORD)
    if r.status_code != 200:
        pytest.skip(f"chriszarek login failed: {r.status_code} {r.text}")
    return r.json()


@pytest.fixture(scope="module")
def chris_league_team(admin_tokens):
    """Find a commissioned league (admin is commissioner of seed leagues) and return (league_id, first_team_id)."""
    headers = {"Authorization": f"Bearer {admin_tokens['access_token']}"}
    r = requests.get(f"{API}/leagues", headers=headers, timeout=30)
    assert r.status_code == 200, r.text
    leagues = r.json()
    me_id = admin_tokens["id"]
    commissioned = [lg for lg in leagues if lg.get("commissioner_id") == me_id]
    if not commissioned:
        pytest.skip("admin is not commissioner of any league — can't run commissioner tests")
    league = commissioned[0]
    league_id = league["id"]
    r2 = requests.get(f"{API}/teams?league_id={league_id}", headers=headers, timeout=30)
    assert r2.status_code == 200, r2.text
    teams = r2.json()
    if not teams:
        pytest.skip("no teams in league")
    return league_id, teams[0]["id"]


# =================================================================
#  Mobile-auth contract
# =================================================================
class TestMobileAuthContract:
    def test_login_returns_tokens_in_body(self):
        r = _login_body(ADMIN_EMAIL, ADMIN_PASSWORD)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "access_token" in data and "refresh_token" in data
        assert isinstance(data["access_token"], str) and len(data["access_token"]) > 100
        assert isinstance(data["refresh_token"], str) and len(data["refresh_token"]) > 100
        assert data.get("email") == ADMIN_EMAIL

    def test_register_returns_tokens_in_body(self):
        suffix = uuid.uuid4().hex[:8]
        email = f"test_iter20_{suffix}@example.com"
        r = requests.post(f"{API}/auth/register", json={
            "email": email, "password": "TestPass123!",
            "name": "Iter20 Mobile Test",
            "username": f"iter20_{suffix}",
        }, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("access_token") and len(data["access_token"]) > 100
        assert data.get("refresh_token") and len(data["refresh_token"]) > 100

    def test_me_with_bearer_only(self, admin_tokens):
        # Use a fresh requests.get (no cookies) — only Bearer header
        r = requests.get(
            f"{API}/auth/me",
            headers={"Authorization": f"Bearer {admin_tokens['access_token']}"},
            timeout=30,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("email") == ADMIN_EMAIL
        assert data.get("id")

    def test_me_without_any_auth_rejected(self):
        r = requests.get(f"{API}/auth/me", timeout=30)
        assert r.status_code == 401

    def test_refresh_with_bearer_header(self, admin_tokens):
        # Mobile flow: POST /auth/refresh with Authorization: Bearer <refresh_token>, NO cookies
        r = requests.post(
            f"{API}/auth/refresh",
            headers={"Authorization": f"Bearer {admin_tokens['refresh_token']}"},
            timeout=30,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("access_token") and len(data["access_token"]) > 100
        # New access token must work on /me
        r2 = requests.get(
            f"{API}/auth/me",
            headers={"Authorization": f"Bearer {data['access_token']}"},
            timeout=30,
        )
        assert r2.status_code == 200


# =================================================================
#  routes/awards.py — non-regression (incl. new conference_winner/consolation_won)
# =================================================================
class TestAwardsRouter:
    def test_put_awards_requires_auth(self, chris_league_team):
        league_id, team_id = chris_league_team
        r = requests.put(
            f"{API}/leagues/{league_id}/teams/{team_id}/awards",
            json={"conference_winner": True}, timeout=30,
        )
        assert r.status_code == 401

    def test_put_awards_with_conference_and_consolation(self, admin_tokens, chris_league_team):
        league_id, team_id = chris_league_team
        headers = {"Authorization": f"Bearer {admin_tokens['access_token']}"}

        # Set both new-style flags TRUE
        r = requests.put(
            f"{API}/leagues/{league_id}/teams/{team_id}/awards",
            headers=headers,
            json={"conference_winner": True, "consolation_won": True},
            timeout=30,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["team_id"] == team_id
        assert data["conference_winner_at"] is not None
        assert data["consolation_won_at"] is not None
        assert any("conference_winner_at set" in c for c in data["changes"])
        assert any("consolation_won_at set" in c for c in data["changes"])
        assert "unlocked_trades" in data

        # Clear them (False) — critical for test_trade_flow.py which asserts on championship clean state
        r2 = requests.put(
            f"{API}/leagues/{league_id}/teams/{team_id}/awards",
            headers=headers,
            json={"conference_winner": False, "consolation_won": False,
                  "championship_won": False, "division_winner": False},
            timeout=30,
        )
        assert r2.status_code == 200, r2.text
        data2 = r2.json()
        assert data2["conference_winner_at"] is None
        assert data2["consolation_won_at"] is None

    def test_get_consolation_prize_public(self, chris_league_team):
        league_id, _ = chris_league_team
        r = requests.get(f"{API}/leagues/{league_id}/consolation-prize", timeout=30)
        assert r.status_code == 200
        assert r.json()["league_id"] == league_id

    def test_put_consolation_prize_commissioner(self, admin_tokens, chris_league_team):
        league_id, _ = chris_league_team
        headers = {"Authorization": f"Bearer {admin_tokens['access_token']}"}
        prize = {
            "type": "draft_lottery_boost",
            "description": "Move up 3 slots in 2027 R1",
            "lottery_boost_spots": 3,
        }
        r = requests.put(
            f"{API}/leagues/{league_id}/consolation-prize",
            headers=headers, json={"prize": prize}, timeout=30,
        )
        assert r.status_code == 200, r.text
        assert r.json()["consolation_prize"]["type"] == "draft_lottery_boost"
        assert r.json()["consolation_prize"]["lottery_boost_spots"] == 3

        # Read-back
        r2 = requests.get(f"{API}/leagues/{league_id}/consolation-prize", timeout=30)
        assert r2.status_code == 200
        assert r2.json()["consolation_prize"]["lottery_boost_spots"] == 3

    def test_team_rewards_shape(self, chris_league_team):
        league_id, _ = chris_league_team
        r = requests.get(f"{API}/leagues/{league_id}/team-rewards", timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["league_id"] == league_id
        assert isinstance(data["rewards"], list)
        # Confirm no ObjectId leak
        for rw in data["rewards"]:
            assert isinstance(rw.get("_id"), str) or "_id" not in rw


# =================================================================
#  routes/drafts.py
# =================================================================
class TestDraftsRouter:
    def test_get_draft_picks(self, chris_league_team):
        league_id, _ = chris_league_team
        r = requests.get(f"{API}/drafts/{league_id}/picks", timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        # Can be a list or dict — only assert it is a valid JSON payload
        assert data is not None


# =================================================================
#  routes/matchups.py — non-regression
# =================================================================
class TestMatchupsRouter:
    def test_list_matchups(self, chris_league_team):
        league_id, _ = chris_league_team
        r = requests.get(f"{API}/matchups/{league_id}", timeout=30)
        assert r.status_code == 200, r.text
        assert isinstance(r.json(), list)

    def test_current_week(self, chris_league_team):
        league_id, _ = chris_league_team
        r = requests.get(f"{API}/matchups/{league_id}/current-week", timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "week" in data or "matchups" in data or isinstance(data, list)

    def test_results(self, chris_league_team):
        league_id, _ = chris_league_team
        r = requests.get(f"{API}/matchups/{league_id}/results?week=1", timeout=30)
        assert r.status_code == 200, r.text


# =================================================================
#  Non-regression: /api/u/chriszarek aggregate
# =================================================================
class TestUserProfileAggregate:
    def test_chriszarek_roll_up(self):
        r = requests.get(f"{API}/u/chriszarek", timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        stats = data.get("stats", {})
        for k in [
            "championships_won",
            "conference_titles",
            "division_titles",
            "consolations_won",
            "playoff_appearances",
        ]:
            assert k in stats, f"missing aggregate field in stats: {k}"
            assert isinstance(stats[k], int), f"{k} should be int, got {type(stats[k])}"
        # Permanent trophies / teams with award timestamps
        assert "teams" in data
        for t in data["teams"]:
            for ts_field in (
                "championship_won_at", "division_winner_at",
                "conference_winner_at", "consolation_won_at",
                "playoffs_reached_at",
            ):
                assert ts_field in t, f"team missing {ts_field}"
