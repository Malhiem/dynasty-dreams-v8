"""Tests for Trophy Room endpoints (league-level + team-level)."""
import os

import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
COMMISH_EMAIL = "admin@dynastydreams.com"
COMMISH_PASS = "Admin123!"


def _login(email: str, password: str):
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text[:200]
    s.headers.update({"Authorization": f"Bearer {r.json()['access_token']}"})
    return s


def _pick_commish_league(s):
    me = s.get(f"{BASE_URL}/api/auth/me").json()
    leagues = s.get(f"{BASE_URL}/api/leagues?my_leagues=true").json()
    for l in leagues:
        if l.get("commissioner_id") == me["id"]:
            return l["id"]
    return leagues[0]["id"]


def test_league_trophy_room_shape():
    s = _login(COMMISH_EMAIL, COMMISH_PASS)
    lid = _pick_commish_league(s)

    # Ensure at least one snapshot exists
    s.post(f"{BASE_URL}/api/leagues/{lid}/complete-season", json={"season_year": 2017})

    r = requests.get(f"{BASE_URL}/api/leagues/{lid}/trophy-room")
    assert r.status_code == 200, r.text
    data = r.json()
    for key in ("league_id", "seasons", "team_banners", "hall_of_fame"):
        assert key in data
    assert isinstance(data["seasons"], list)
    assert isinstance(data["team_banners"], list)
    assert isinstance(data["hall_of_fame"], list)


def test_season_trophy_card_shape():
    s = _login(COMMISH_EMAIL, COMMISH_PASS)
    lid = _pick_commish_league(s)
    r = requests.get(f"{BASE_URL}/api/leagues/{lid}/trophy-room")
    data = r.json()
    if not data["seasons"]:
        pytest.skip("No seasons snapshotted yet")
    season = data["seasons"][0]
    for key in (
        "season_year", "champion", "presidents_trophy",
        "division_winners", "conference_winners",
        "season_mvp", "best_goalie", "best_defenseman",
    ):
        assert key in season


def test_team_banners_grouped_by_team():
    s = _login(COMMISH_EMAIL, COMMISH_PASS)
    lid = _pick_commish_league(s)
    r = requests.get(f"{BASE_URL}/api/leagues/{lid}/trophy-room")
    data = r.json()
    for tb in data["team_banners"]:
        assert "team_id" in tb
        assert "team_name" in tb
        assert "banners" in tb
        for b in tb["banners"]:
            assert b["type"] in {"championship", "presidents_trophy", "conference", "division", "consolation"}
            assert "year" in b


def test_team_trophy_room_shape():
    s = _login(COMMISH_EMAIL, COMMISH_PASS)
    lid = _pick_commish_league(s)
    teams = s.get(f"{BASE_URL}/api/teams?league_id={lid}").json()
    if not teams:
        pytest.skip("No teams")
    tid = teams[0]["id"]
    r = requests.get(f"{BASE_URL}/api/teams/{tid}/trophy-room")
    assert r.status_code == 200
    data = r.json()
    for key in ("team_id", "team_name", "league_id", "seasons_played", "banners", "individual_awards"):
        assert key in data


def test_team_trophy_room_invalid_id():
    r = requests.get(f"{BASE_URL}/api/teams/notavalidid/trophy-room")
    assert r.status_code == 400


def test_team_trophy_room_404():
    """Valid ObjectId format but no such team."""
    r = requests.get(f"{BASE_URL}/api/teams/000000000000000000000000/trophy-room")
    assert r.status_code == 404


def test_hall_of_fame_top_8():
    s = _login(COMMISH_EMAIL, COMMISH_PASS)
    lid = _pick_commish_league(s)
    r = requests.get(f"{BASE_URL}/api/leagues/{lid}/trophy-room")
    data = r.json()
    assert len(data["hall_of_fame"]) <= 8
    for legend in data["hall_of_fame"]:
        assert "player_id" in legend
        assert "player_name" in legend
        assert "trophies" in legend
        assert isinstance(legend["trophies"], list)
        # Each trophy entry must have label + year
        for t in legend["trophies"]:
            assert "label" in t
            assert "year" in t
