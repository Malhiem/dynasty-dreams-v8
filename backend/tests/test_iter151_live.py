"""Iter 151 — live HTTP checks against the preview env for the new
roster-truncated response shape (scoring categories + per-player buckets)."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://dynasty-preview.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = "admin@dynastydreams.com"
ADMIN_PASSWORD = "Admin123!"
ICE_BREAKERS_TEAM_ID = "69e59b33cbd3fea02a914c7b"
DEMO_LEAGUE_ID = "69e46af167999bfb85c39629"


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:300]}"
    token = r.json().get("access_token") or r.json().get("token")
    if token:
        s.headers["Authorization"] = f"Bearer {token}"
    return s


def test_roster_truncated_returns_scoring_arrays(session):
    r = session.get(f"{BASE_URL}/api/teams/{ICE_BREAKERS_TEAM_ID}/roster-truncated", params={"stat_filter": "regular"})
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    assert body["team_id"] == ICE_BREAKERS_TEAM_ID
    assert body["stat_filter"] == "regular"
    assert "players" in body and isinstance(body["players"], list) and len(body["players"]) > 0
    # NEW: scoring categories as lists of stat keys
    assert "scoring" in body, "missing scoring block"
    sc = body["scoring"]
    assert isinstance(sc.get("skater"), list), f"skater not a list: {sc.get('skater')!r}"
    assert isinstance(sc.get("goalie"), list), f"goalie not a list: {sc.get('goalie')!r}"
    # Expected demo league skater + goalie cats
    expected_skater = {"goals", "assists", "plus_minus", "penalty_minutes", "power_play_points", "shots"}
    expected_goalie = {"wins", "losses", "saves", "goals_against", "shutouts"}
    assert expected_skater.issubset(set(sc["skater"])), f"skater missing keys: got {sc['skater']}"
    assert expected_goalie.issubset(set(sc["goalie"])), f"goalie missing keys: got {sc['goalie']}"


def test_roster_truncated_players_have_stats_bucket(session):
    r = session.get(f"{BASE_URL}/api/teams/{ICE_BREAKERS_TEAM_ID}/roster-truncated", params={"stat_filter": "regular"})
    assert r.status_code == 200
    players = r.json()["players"]
    # Every player should have a stats dict with at least one of the skater keys (or goalie keys)
    for p in players:
        assert "stats" in p, f"player missing stats: {p.get('name')}"
        assert isinstance(p["stats"], dict)
    # At least one player has goals
    assert any("goals" in p["stats"] for p in players if p.get("position") != "G"), "no skater had goals stat"


def test_goalie_present_on_ice_breakers(session):
    r = session.get(f"{BASE_URL}/api/teams/{ICE_BREAKERS_TEAM_ID}/roster-truncated", params={"stat_filter": "regular"})
    assert r.status_code == 200
    players = r.json()["players"]
    goalies = [p for p in players if p.get("position") == "G"]
    assert len(goalies) >= 1, f"Ice Breakers should have at least 1 goalie, got {len(goalies)}"


def test_stat_buckets_produce_different_values(session):
    """Switching stat_filter must change FP for the same player across at least 3 of the 5 buckets."""
    buckets = ["season", "regular", "playoffs", "l30", "l7"]
    fp_by_player = {}
    for b in buckets:
        r = session.get(f"{BASE_URL}/api/teams/{ICE_BREAKERS_TEAM_ID}/roster-truncated", params={"stat_filter": b})
        assert r.status_code == 200, f"{b}: {r.status_code}"
        for p in r.json()["players"]:
            fp_by_player.setdefault(p["id"], {})[b] = p.get("fantasy_points")
    # Pick a player who isn't a goalie with the most distinct values
    best_distinct = 0
    for pid, fps in fp_by_player.items():
        distinct = len(set(fps.values()))
        best_distinct = max(best_distinct, distinct)
    assert best_distinct >= 3, f"No player had >=3 distinct FP across buckets. Sample: {list(fp_by_player.items())[:2]}"


def test_all_five_stat_filters_accepted(session):
    for b in ["season", "regular", "playoffs", "l30", "l7"]:
        r = session.get(f"{BASE_URL}/api/teams/{ICE_BREAKERS_TEAM_ID}/roster-truncated", params={"stat_filter": b})
        assert r.status_code == 200, f"{b} returned {r.status_code}"
        assert r.json()["stat_filter"] == b
