"""Iter 150 — Live HTTP tests against preview URL for roster-truncated + admin seed."""
import os
import requests
import pytest

BASE_URL = "https://dynasty-preview.preview.emergentagent.com"
LEAGUE_ID = "69e46af167999bfb85c39629"
TEAM_ID = "69e59b33cbd3fea02a914c7b"  # Ice Breakers
ADMIN_USER_ID = "69dc63e232b1b7aac227c0a3"


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": "admin@dynastydreams.com", "password": "Admin123!"},
        timeout=20,
    )
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text[:200]}"
    return s


def test_admin_seeded_as_ice_breakers_owner(admin_session):
    """Admin user must be owner of Ice Breakers in the demo league."""
    r = admin_session.get(f"{BASE_URL}/api/teams", params={"league_id": LEAGUE_ID}, timeout=20)
    assert r.status_code == 200, r.text[:300]
    teams = r.json()
    assert isinstance(teams, list) and len(teams) > 0
    ice = next((t for t in teams if t.get("id") == TEAM_ID or t.get("_id") == TEAM_ID), None)
    assert ice is not None, f"Ice Breakers (team {TEAM_ID}) not found in league {LEAGUE_ID}"
    assert ice.get("owner_id") == ADMIN_USER_ID, (
        f"Ice Breakers owner_id is {ice.get('owner_id')}, expected {ADMIN_USER_ID}"
    )
    assert "Ice Breakers" in (ice.get("name") or ""), f"Team name unexpected: {ice.get('name')}"


def test_roster_truncated_default_returns_ten_players(admin_session):
    r = admin_session.get(
        f"{BASE_URL}/api/teams/{TEAM_ID}/roster-truncated", timeout=20
    )
    assert r.status_code == 200, r.text[:400]
    data = r.json()
    assert data.get("team_id") == TEAM_ID
    assert data.get("stat_filter") in ("season", None) or data.get("stat_filter") == "season"
    players = data.get("players")
    assert isinstance(players, list) and len(players) >= 10, f"Got {len(players) if isinstance(players, list) else 'N/A'} players"
    # Shape assertions on first row
    p0 = players[0]
    for k in ("id", "name", "position", "fantasy_points", "fp_per_game", "cap_hit", "games_played"):
        assert k in p0, f"Missing key '{k}' in player row: {p0}"
    # Sorted desc by fantasy_points
    fps = [float(p.get("fantasy_points") or 0) for p in players]
    assert fps == sorted(fps, reverse=True), f"Players not sorted by fantasy_points desc: {fps}"


@pytest.mark.parametrize("flt", ["season", "regular", "playoffs", "l30", "l7"])
def test_roster_truncated_all_stat_filters(admin_session, flt):
    r = admin_session.get(
        f"{BASE_URL}/api/teams/{TEAM_ID}/roster-truncated",
        params={"stat_filter": flt},
        timeout=20,
    )
    assert r.status_code == 200, f"{flt}: {r.status_code} {r.text[:200]}"
    data = r.json()
    assert data.get("stat_filter") == flt
    assert isinstance(data.get("players"), list)


def test_roster_truncated_invalid_team_404(admin_session):
    r = admin_session.get(
        f"{BASE_URL}/api/teams/000000000000000000000000/roster-truncated", timeout=20
    )
    assert r.status_code in (404, 400), f"Unexpected status {r.status_code}: {r.text[:200]}"
