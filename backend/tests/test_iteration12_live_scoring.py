"""Iteration 12 — Dynasty Dreams Phase 12 live-scoring + demo seed tests.

Covers:
  - GET /api/live-scoring summary shape + non-empty games
  - POST /api/live-scoring/refresh forces a poll and returns <15s
  - GET /api/live-scoring/league/{league_id} returns leaderboard
  - GET /api/live-scoring/team/{team_id} returns per-player stat lines
  - Sanity regression: 5 demo leagues full (current_teams == max_teams)
  - DB sanity: 86 teams total, 1038 players unchanged
  - Malformed IDs return HTTP 400 via _safe_object_id
"""
from tests.live_snapshot_fixture import live_snapshot_inputs
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@e2e.dynastydreams.com")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "e2e-admin-password")

EXPECTED_LEAGUES = {
    "Ice Kings Head-to-Head":     {"format": "redraft",   "scoring_format": "head_to_head", "max_teams": 12},
    "Stat Chasers Roto":          {"format": "redraft",   "scoring_format": "rotisserie",   "max_teams": 14},
    "Frozen Dynasty":             {"format": "dynasty",   "scoring_format": "head_to_head", "max_teams": 16},
    "Perennial Keepers":          {"format": "keeper",    "scoring_format": "head_to_head", "max_teams": 12},
    "Set-and-Forget Best Ball":   {"format": "best_ball", "scoring_format": "total_points", "max_teams": 32},
}


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=15)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
    return s


@pytest.fixture(scope="module")
def leagues(client):
    r = client.get(f"{BASE_URL}/api/leagues", timeout=15)
    assert r.status_code == 200
    data = r.json()
    lst = data if isinstance(data, list) else data.get("leagues", [])
    by_name = {lg["name"]: lg for lg in lst}
    return by_name


# ── Demo league regression ────────────────────────────────────────────────
class TestDemoLeagueRegression:
    def test_five_demo_leagues_exist(self, leagues):
        for name in EXPECTED_LEAGUES:
            assert name in leagues, f"missing demo league: {name}"

    def test_leagues_full_and_correct_format(self, leagues):
        for name, expected in EXPECTED_LEAGUES.items():
            lg = leagues[name]
            assert lg["format"] == expected["format"], f"{name} format"
            assert lg["scoring_format"] == expected["scoring_format"], f"{name} scoring"
            assert lg["max_teams"] == expected["max_teams"], f"{name} max_teams"
            assert lg["current_teams"] == expected["max_teams"], (
                f"{name} should be full: {lg['current_teams']}/{lg['max_teams']}")

    def test_all_have_admin_commissioner(self, leagues, client):
        me = client.get(f"{BASE_URL}/api/auth/me", timeout=15).json()
        admin_id = me["id"]
        for name in EXPECTED_LEAGUES:
            assert leagues[name]["commissioner_id"] == admin_id or admin_id in leagues[name].get("co_commissioners", []), f"{name} commissioner access mismatch"


# ── Live Scoring GET summary ──────────────────────────────────────────────
class TestLiveScoringSummary:
    def test_summary_shape(self, client):
        r = client.get(f"{BASE_URL}/api/live-scoring", timeout=15)
        assert r.status_code == 200
        d = r.json()
        for k in ("date", "games", "games_processed", "players_updated", "playoff_games", "polled_at"):
            assert k in d, f"missing key {k} in {list(d.keys())}"
        assert isinstance(d["games"], list)

    def test_summary_has_games(self, client):
        r = client.get(f"{BASE_URL}/api/live-scoring", timeout=15)
        d = r.json()
        assert d["games_processed"] >= 1, f"expected >=1 game, got {d['games_processed']}"
        assert len(d["games"]) >= 1

    def test_game_dict_fields(self, client):
        r = client.get(f"{BASE_URL}/api/live-scoring", timeout=15)
        g = r.json()["games"][0]
        for k in ("id", "state", "type", "is_playoff", "away", "home", "away_score", "home_score"):
            assert k in g, f"missing key {k} in game {g}"
        assert isinstance(g["is_playoff"], bool)


# ── Live Scoring refresh (manual poll) ────────────────────────────────────
class TestLiveScoringRefresh:
    def test_refresh_returns_and_is_fast(self, client):
        t0 = time.time()
        r = client.post(f"{BASE_URL}/api/live-scoring/refresh", timeout=20)
        elapsed = time.time() - t0
        assert r.status_code == 200, f"refresh failed {r.status_code}: {r.text[:200]}"
        assert elapsed < 15, f"refresh took {elapsed:.1f}s (>15s)"
        d = r.json()
        for k in ("date", "games", "games_processed", "players_updated", "playoff_games", "polled_at"):
            assert k in d


# ── League leaderboard ────────────────────────────────────────────────────
class TestLeagueLiveScoring:
    def test_ice_kings_leaderboard(self, client, leagues):
        league_id = leagues["Ice Kings Head-to-Head"]["id"]
        r = client.get(f"{BASE_URL}/api/live-scoring/league/{league_id}", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["league_id"] == league_id
        lb = d["leaderboard"]
        assert isinstance(lb, list) and len(lb) >= 1
        # required fields
        for row in lb:
            for k in ("team_id", "team_name", "owner_name", "live_points", "roster_count"):
                assert k in row
        # sorted desc
        pts = [r["live_points"] for r in lb]
        assert pts == sorted(pts, reverse=True), "leaderboard not sorted desc"
        # at least one team has live_points > 0
        assert any(r["live_points"] > 0 for r in lb), "no team has live_points > 0"

    def test_malformed_league_id_returns_400(self, client):
        r = client.get(f"{BASE_URL}/api/live-scoring/league/not-a-hex-id", timeout=15)
        assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text[:200]}"


# ── Team roster live scoring ──────────────────────────────────────────────
class TestTeamLiveScoring:
    def test_top_team_roster_has_fpts(self, client, leagues):
        league_id = leagues["Ice Kings Head-to-Head"]["id"]
        lb = client.get(f"{BASE_URL}/api/live-scoring/league/{league_id}", timeout=15).json()["leaderboard"]
        assert lb, "no leaderboard rows"
        top_team_id = lb[0]["team_id"]

        r = client.get(f"{BASE_URL}/api/live-scoring/team/{top_team_id}", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["team_id"] == top_team_id
        assert "team_name" in d and "live_points" in d and "players" in d
        assert isinstance(d["players"], list)
        if d["players"]:
            top = d["players"][0]
            for k in ("id", "nhl_id", "name", "team", "position", "is_goalie",
                      "goals", "assists", "shots", "saves", "goals_against",
                      "wins", "games", "fpts", "last_game_state"):
                assert k in top, f"missing {k} in player row"
            assert top["fpts"] > 0, f"top player fpts should be > 0, got {top['fpts']}"

    def test_malformed_team_id_returns_400(self, client):
        r = client.get(f"{BASE_URL}/api/live-scoring/team/zzzzz", timeout=15)
        assert r.status_code == 400, f"expected 400, got {r.status_code}"

    def test_nonexistent_team_returns_404(self, client):
        r = client.get(f"{BASE_URL}/api/live-scoring/team/000000000000000000000000", timeout=15)
        assert r.status_code == 404


# ── DB sanity via public endpoints ────────────────────────────────────────
class TestDbSanity:
    def test_total_teams_86(self, client, leagues):
        total = sum(lg["current_teams"] for lg in leagues.values())
        assert total == 86, f"expected 86 total teams across 5 demo leagues, got {total}"

    def test_players_unchanged_1038(self, client):
        # /api/sports returns NHL player_count
        r = client.get(f"{BASE_URL}/api/sports", timeout=15)
        assert r.status_code == 200
        nhl = next((s for s in r.json() if s["id"] == "nhl"), None)
        assert nhl is not None
        assert nhl["player_count"] == 1038, f"expected 1038 NHL players, got {nhl['player_count']}"
