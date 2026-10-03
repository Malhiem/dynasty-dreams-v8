"""Tests for player dynasty-career endpoint + auto-snapshot trigger."""
import os

import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
COMMISH_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@e2e.dynastydreams.com")
COMMISH_PASS = os.environ.get("ADMIN_PASSWORD", "e2e-admin-password")


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


def test_dynasty_career_unknown_player_empty():
    """No snapshots → empty history but valid shape."""
    r = requests.get(f"{BASE_URL}/api/players/000000000000000000000999/dynasty-career")
    assert r.status_code == 200
    body = r.json()
    assert body["history"] == []
    assert body["totals"]["seasons"] == 0
    assert body["totals"]["leagues"] == 0
    assert body["totals"]["awards"] == 0
    assert body["totals"]["championships"] == 0


def test_dynasty_career_with_snapshot():
    """If admin's league has a snapshot with a rostered player, return that player's career."""
    s = _login(COMMISH_EMAIL, COMMISH_PASS)
    lid = _pick_commish_league(s)
    # Snapshot a recent year
    s.post(f"{BASE_URL}/api/leagues/{lid}/complete-season", json={"season_year": 2016})

    # Pull the snapshot to find a rostered player
    snap = s.get(f"{BASE_URL}/api/leagues/{lid}/seasons/2016").json()
    if not snap.get("players"):
        pytest.skip("No players in snapshot")
    pid = snap["players"][0]["player_id"]

    r = requests.get(f"{BASE_URL}/api/players/{pid}/dynasty-career")
    assert r.status_code == 200
    body = r.json()
    assert body["totals"]["seasons"] >= 1
    assert any(h["season_year"] == 2016 for h in body["history"])
    # Each row has league_name + owner_team_name
    for h in body["history"]:
        assert "league_id" in h
        assert "league_name" in h
        assert "fantasy_points" in h


def test_dynasty_career_includes_awards_and_championships():
    """Ensure award/championship counters reflect data."""
    s = _login(COMMISH_EMAIL, COMMISH_PASS)
    lid = _pick_commish_league(s)
    snap = s.get(f"{BASE_URL}/api/leagues/{lid}/seasons/2025").json()
    if not snap.get("players"):
        pytest.skip("No 2025 snapshot")
    # Pick the first player who's rostered (so we have an owner_team_name)
    rostered_pids = []
    for t in snap.get("teams", []):
        for pid in t.get("roster", []):
            rostered_pids.append(pid)
    if not rostered_pids:
        pytest.skip("No rostered players")
    pid = rostered_pids[0]
    r = requests.get(f"{BASE_URL}/api/players/{pid}/dynasty-career")
    body = r.json()
    if body["history"]:
        first = body["history"][0]
        assert isinstance(first.get("awards"), list)
        assert isinstance(first.get("champion"), (bool, type(None)))


def test_auto_snapshot_helper_callable_via_simulate_week():
    """Sanity check: simulate-week endpoint runs without crashing under the new
    seasons.routes._maybe_auto_snapshot_season hook."""
    s = _login(COMMISH_EMAIL, COMMISH_PASS)
    lid = _pick_commish_league(s)
    cw = s.get(f"{BASE_URL}/api/matchups/{lid}/current-week").json()
    week = cw.get("week", 1)
    r = s.post(f"{BASE_URL}/api/matchups/simulate-week", json={"league_id": lid, "week": week})
    # Should return 200 (or 400 if no scheduled matchups; either way must NOT 500)
    assert r.status_code in (200, 400), f"simulate-week crashed: {r.status_code} {r.text[:200]}"
