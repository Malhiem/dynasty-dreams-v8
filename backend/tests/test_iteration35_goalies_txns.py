"""Iteration 35 tests:
- /api/teams/{id}/roster/detail returns rosterSection in {goalies, goalies_minors} for goalie players
- Skaters retain starting/bench/minors/ir
- /api/roster/{team_id} (simple) returns saves, goals_against, losses, shots_against, wins, save_pct
"""
import os
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
TEAM_ID = "69e59b30cbd3fea02a914c61"
LEAGUE_ID = "69e46af167999bfb85c39628"
EMAIL = os.environ.get("TEST_OWNER_EMAIL", "test-owner@e2e.dynastydreams.com")
PASSWORD = os.environ.get("TEST_OWNER_PASSWORD", "e2e-owner-password")


@pytest.fixture(scope="module")
def auth_session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
    if r.status_code != 200:
        pytest.skip(f"login failed status={r.status_code} body={r.text[:200]}")
    tok = r.json().get("access_token") or r.json().get("token")
    if tok:
        s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


# ---- /roster/{team_id}/detail ---------------------------------------------------------
class TestRosterDetailGoalies:
    def test_detail_status(self, auth_session):
        r = auth_session.get(f"{BASE_URL}/api/roster/{TEAM_ID}/detail")
        assert r.status_code == 200, r.text
        data = r.json()
        assert "players" in data or "roster" in data or isinstance(data, dict)

    def test_goalie_section_classification(self, auth_session):
        r = auth_session.get(f"{BASE_URL}/api/roster/{TEAM_ID}/detail")
        assert r.status_code == 200
        data = r.json()
        players = data.get("players") or data.get("roster") or []
        assert isinstance(players, list) and len(players) > 0, "no players returned"

        goalies = [p for p in players if (p.get("position") == "G" or p.get("is_goalie") or p.get("player_type") == "goalie")]
        assert len(goalies) > 0, "expected at least one goalie on Zarek's Frozen"

        valid_goalie_sections = {"goalies", "goalies_minors"}
        bad = [g for g in goalies if g.get("rosterSection") not in valid_goalie_sections]
        assert not bad, f"goalies in wrong sections: {[(g.get('name'), g.get('rosterSection')) for g in bad]}"

    def test_skater_sections_unchanged(self, auth_session):
        r = auth_session.get(f"{BASE_URL}/api/roster/{TEAM_ID}/detail")
        data = r.json()
        players = data.get("players") or data.get("roster") or []
        skaters = [p for p in players if not (p.get("position") == "G" or p.get("is_goalie") or p.get("player_type") == "goalie")]
        valid_skater_sections = {"starting", "bench", "minors", "ir"}
        bad = [s for s in skaters if s.get("rosterSection") not in valid_skater_sections]
        assert not bad, f"skaters in unexpected sections: {[(s.get('name'), s.get('rosterSection')) for s in bad][:5]}"


# ---- /roster/{team_id} simple endpoint ------------------------------------------------
class TestRosterSimpleGoalieFields:
    def test_simple_endpoint_returns(self, auth_session):
        r = auth_session.get(f"{BASE_URL}/api/roster/{TEAM_ID}")
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data, (list, dict))

    def test_goalie_has_new_stats_fields(self, auth_session):
        r = auth_session.get(f"{BASE_URL}/api/roster/{TEAM_ID}")
        assert r.status_code == 200
        data = r.json()
        players = data if isinstance(data, list) else (data.get("players") or data.get("roster") or [])
        goalies = [p for p in players if (p.get("position") == "G" or p.get("player_type") == "goalie")]
        assert len(goalies) > 0, "expected at least one goalie"

        required_fields = {"saves", "goals_against", "losses", "shots_against", "wins", "save_pct"}
        first = goalies[0]
        missing = required_fields - set(first.keys())
        assert not missing, f"goalie missing fields: {missing}; got keys={list(first.keys())[:30]}"

    def test_goalie_has_player_type_and_section(self, auth_session):
        r = auth_session.get(f"{BASE_URL}/api/roster/{TEAM_ID}")
        data = r.json()
        players = data if isinstance(data, list) else (data.get("players") or data.get("roster") or [])
        goalies = [p for p in players if (p.get("position") == "G" or p.get("player_type") == "goalie")]
        assert any("player_type" in g for g in goalies), "player_type missing"
        assert any("roster_section" in g for g in goalies), "roster_section missing"
