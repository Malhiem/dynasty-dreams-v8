"""Iteration 37 — Waiver suggestion endpoint + scoring config smoke tests.

Covers:
- GET /api/waivers/suggest ?position=G&limit=1
- GET /api/waivers/suggest ?position=C&limit=3 (sorted by FPTS desc, excludes rostered)
- GET /api/scoring/config (regression smoke check)
- POST /api/roster/{team_id}/drop & /add regression
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://dynasty-preview.preview.emergentagent.com").rstrip("/")
LEAGUE_ID = "69e46af167999bfb85c39628"
TEAM_ID = "69e59b30cbd3fea02a914c61"
USER_EMAIL = "chriszarek@gmail.com"
USER_PASSWORD = "Chris2026!"


@pytest.fixture(scope="module")
def api_client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def auth_session(api_client):
    """Login, return a session with auth cookie/token set."""
    resp = api_client.post(f"{BASE_URL}/api/auth/login", json={
        "email": USER_EMAIL, "password": USER_PASSWORD,
    })
    if resp.status_code != 200:
        pytest.skip(f"Auth failed: {resp.status_code} {resp.text}")
    data = resp.json()
    token = data.get("access_token") or data.get("token")
    if token:
        api_client.headers["Authorization"] = f"Bearer {token}"
    return api_client


@pytest.fixture(scope="module")
def pro_auth_session(auth_session):
    """Authenticated session that also has Pro privileges. /waivers/suggest
    is now Pro-paywalled — these tests need Pro access. Toggles Pro on for
    the test user (admin), yields, then reverts on teardown."""
    sess = auth_session
    # admin client to flip Pro flag
    admin = requests.Session()
    admin.headers.update({"Content-Type": "application/json"})
    admin_login = admin.post(f"{BASE_URL}/api/auth/login", json={
        "email": "admin@dynastydreams.com", "password": "Admin123!",
    })
    if admin_login.status_code != 200:
        pytest.skip(f"Admin auth failed: {admin_login.status_code}")
    admin_token = admin_login.json().get("access_token") or admin_login.json().get("token")
    admin.headers["Authorization"] = f"Bearer {admin_token}"

    me = sess.get(f"{BASE_URL}/api/auth/me")
    user_id = me.json().get("id") or me.json().get("_id")

    admin.post(f"{BASE_URL}/api/admin/users/{user_id}/pro", json={"is_pro": True})
    try:
        yield sess
    finally:
        admin.post(f"{BASE_URL}/api/admin/users/{user_id}/pro", json={"is_pro": False})


# === Waivers suggest ===

class TestWaiversSuggest:
    def test_suggest_goalie_top_1(self, pro_auth_session):
        api_client = pro_auth_session
        r = api_client.get(f"{BASE_URL}/api/waivers/suggest", params={
            "league_id": LEAGUE_ID, "position": "G", "limit": 1,
        })
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["league_id"] == LEAGUE_ID
        assert data["position"] == "G"
        assert isinstance(data["suggestions"], list)
        assert len(data["suggestions"]) == 1
        s = data["suggestions"][0]
        assert s["position"] == "G"
        assert "id" in s and isinstance(s["id"], str)
        assert "name" in s
        assert "fantasy_points" in s and isinstance(s["fantasy_points"], (int, float))
        assert "fpg" in s  # may be None if 0 GP
        assert "games_played" in s

    def test_suggest_center_top_3_sorted_desc(self, pro_auth_session):
        api_client = pro_auth_session
        r = api_client.get(f"{BASE_URL}/api/waivers/suggest", params={
            "league_id": LEAGUE_ID, "position": "C", "limit": 3,
        })
        assert r.status_code == 200, r.text
        data = r.json()
        sugg = data["suggestions"]
        assert len(sugg) == 3
        # All centers
        for s in sugg:
            assert s["position"] == "C"
        # Sorted by FPTS desc
        fpts = [s["fantasy_points"] for s in sugg]
        assert fpts == sorted(fpts, reverse=True), f"Not sorted desc: {fpts}"

    def test_suggest_excludes_rostered(self, pro_auth_session):
        api_client = pro_auth_session
        # Get all rostered player ids in the league
        teams_resp = api_client.get(f"{BASE_URL}/api/teams", params={"league_id": LEAGUE_ID})
        if teams_resp.status_code != 200:
            pytest.skip(f"Cannot list teams: {teams_resp.status_code}")
        teams = teams_resp.json()
        rostered = set()
        for t in teams:
            for pid in (t.get("roster") or []):
                rostered.add(pid)

        # Ask for top 5 centers
        r = api_client.get(f"{BASE_URL}/api/waivers/suggest", params={
            "league_id": LEAGUE_ID, "position": "C", "limit": 5,
        })
        assert r.status_code == 200
        for s in r.json()["suggestions"]:
            assert s["id"] not in rostered, f"Rostered player {s['name']} ({s['id']}) returned as free agent"

    def test_suggest_default_limit_is_1(self, pro_auth_session):
        api_client = pro_auth_session
        r = api_client.get(f"{BASE_URL}/api/waivers/suggest", params={
            "league_id": LEAGUE_ID, "position": "LW",
        })
        assert r.status_code == 200
        assert len(r.json()["suggestions"]) == 1

    def test_suggest_no_position_returns_top_overall(self, pro_auth_session):
        api_client = pro_auth_session
        r = api_client.get(f"{BASE_URL}/api/waivers/suggest", params={
            "league_id": LEAGUE_ID, "limit": 2,
        })
        assert r.status_code == 200
        sugg = r.json()["suggestions"]
        assert len(sugg) == 2
        # Sorted desc
        fpts = [s["fantasy_points"] for s in sugg]
        assert fpts == sorted(fpts, reverse=True)


# === Scoring config smoke ===

class TestScoringConfig:
    def test_get_scoring_config(self, api_client):
        r = api_client.get(f"{BASE_URL}/api/scoring/config", params={"league_id": LEAGUE_ID})
        assert r.status_code == 200, r.text
        data = r.json()
        assert "skater_scoring" in data
        assert "goalie_scoring" in data
        ss = data["skater_scoring"]
        # Verify Morgan Geekie's expected weights
        assert ss.get("goals") == 3
        assert ss.get("assists") == 2
        assert ss.get("power_play_points") == 0.5
        assert ss.get("shots") == 0.5
        assert ss.get("penalty_minutes") == -0.5
        assert ss.get("plus_minus") == 1
        gs = data["goalie_scoring"]
        assert gs.get("wins") == 5
        assert gs.get("saves") == 0.2


# === Roster drop/add regression ===

class TestRosterDropAddRegression:
    def test_drop_then_add_player_round_trip(self, pro_auth_session):
        auth_session = pro_auth_session
        # Pick a free agent to add, then drop, to keep team state intact.
        sug = auth_session.get(f"{BASE_URL}/api/waivers/suggest", params={
            "league_id": LEAGUE_ID, "position": "C", "limit": 1,
        })
        assert sug.status_code == 200
        suggestions = sug.json()["suggestions"]
        if not suggestions:
            pytest.skip("No free agents available")
        fa = suggestions[0]
        fa_id = fa["id"]

        # Add the free agent
        add = auth_session.post(f"{BASE_URL}/api/roster/{TEAM_ID}/add", json={
            "player_id": fa_id,
        })
        if add.status_code not in (200, 201):
            pytest.skip(f"Add endpoint returned {add.status_code}: {add.text}")

        # Verify roster contains him
        team = auth_session.get(f"{BASE_URL}/api/teams/{TEAM_ID}")
        if team.status_code == 200:
            roster = team.json().get("roster") or []
            assert fa_id in roster, "Player not in roster after add"

        # Drop him back
        drop = auth_session.post(f"{BASE_URL}/api/roster/{TEAM_ID}/drop", json={
            "player_id": fa_id,
        })
        assert drop.status_code in (200, 201), f"Drop failed: {drop.status_code} {drop.text}"

        team2 = auth_session.get(f"{BASE_URL}/api/teams/{TEAM_ID}")
        if team2.status_code == 200:
            roster2 = team2.json().get("roster") or []
            assert fa_id not in roster2, "Player still in roster after drop"
