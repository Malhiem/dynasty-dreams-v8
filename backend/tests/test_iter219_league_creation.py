"""
Iter 219 — H2H matchups_per_week + create-league auto-team bug + empty-league sweep.
"""
from __future__ import annotations

import os
import uuid
import requests

API_URL = os.environ["REACT_APP_BACKEND_URL"]
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@e2e.dynastydreams.com")
ADMIN_PASS = os.environ.get("ADMIN_PASSWORD", "e2e-admin-password")


def _login(email, password):
    r = requests.post(f"{API_URL}/api/auth/login", json={"email": email, "password": password})
    r.raise_for_status()
    return r.json()["access_token"]


def _make_user():
    suffix = uuid.uuid4().hex[:8]
    email = f"iter219_{suffix}@example.com"
    username = f"iter219_{suffix}"
    requests.post(f"{API_URL}/api/auth/register",
                  json={"email": email, "password": "TestPass123!",
                        "username": username, "name": f"Iter219 {suffix}"}).raise_for_status()
    token = _login(email, "TestPass123!")
    return email, token


def test_create_league_autocreates_commissioner_team_and_sets_count():
    """Bug fix: creating a league must auto-add the commissioner as a
    team owner and set `current_teams=1`."""
    _, token = _make_user()
    H = {"Authorization": f"Bearer {token}"}
    r = requests.post(f"{API_URL}/api/leagues", headers=H, json={
        "name": "iter219 league " + uuid.uuid4().hex[:6],
        "format": "dynasty", "scoring_format": "head_to_head",
        "max_teams": 10, "draft_type": "snake", "roster_spots": 20,
    })
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["current_teams"] == 1
    assert d["commissioner_id"]
    # Verify a team exists for this user in the new league
    teams_r = requests.get(f"{API_URL}/api/teams?league_id={d['id']}", headers=H)
    assert teams_r.status_code == 200
    teams = teams_r.json() if isinstance(teams_r.json(), list) else teams_r.json().get("teams", [])
    assert len(teams) >= 1
    # The commissioner is also the owner of at least one team in this league
    me = requests.get(f"{API_URL}/api/auth/me", headers=H).json()
    assert any(t.get("owner_id") == me["id"] for t in teams)


def test_h2h_matchups_per_week_valid_accepted():
    _, token = _make_user()
    H = {"Authorization": f"Bearer {token}"}
    r = requests.post(f"{API_URL}/api/leagues", headers=H, json={
        "name": "iter219 mpw3 " + uuid.uuid4().hex[:6],
        "format": "dynasty", "scoring_format": "head_to_head",
        "max_teams": 8, "draft_type": "snake", "roster_spots": 20,
        "matchups_per_week": 3,
    })
    assert r.status_code == 200, r.text
    assert r.json().get("matchups_per_week") == 3


def test_h2h_matchups_per_week_too_high_rejected():
    """For an 8-team H2H league, 12 matchups/week must 400 (max = 7)."""
    _, token = _make_user()
    H = {"Authorization": f"Bearer {token}"}
    r = requests.post(f"{API_URL}/api/leagues", headers=H, json={
        "name": "iter219 too-high " + uuid.uuid4().hex[:6],
        "format": "dynasty", "scoring_format": "head_to_head",
        "max_teams": 8, "draft_type": "snake", "roster_spots": 20,
        "matchups_per_week": 12,
    })
    assert r.status_code == 400
    assert "matchups_per_week" in r.text.lower()


def test_non_h2h_matchups_per_week_forced_to_one():
    """For a roto (non-H2H) league, the field is ignored and stored as 1."""
    _, token = _make_user()
    H = {"Authorization": f"Bearer {token}"}
    r = requests.post(f"{API_URL}/api/leagues", headers=H, json={
        "name": "iter219 roto " + uuid.uuid4().hex[:6],
        "format": "dynasty", "scoring_format": "rotisserie",
        "max_teams": 10, "draft_type": "snake", "roster_spots": 20,
        "matchups_per_week": 5,
    })
    assert r.status_code == 200, r.text
    # Stored as 1 because scoring is not H2H
    assert r.json().get("matchups_per_week") == 1
