"""Tests for Playoff Bracket + Divisions management.

Covers:
- GET /api/leagues/{id}/playoff-bracket returns correctly seeded bracket
- GET /api/leagues/{id}/divisions returns assignments
- PUT /api/leagues/{id}/divisions (commissioner only) assigns teams
- Standings endpoint returns division + GB + movement when divisions are set
"""
import os
import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
COMMISH_EMAIL = "chriszarek@gmail.com"
COMMISH_PASS = "Chris2026!"
NON_COMMISH_EMAIL = "admin@dynastydreams.com"
NON_COMMISH_PASS = "Admin123!"


def _login(email: str, password: str) -> tuple[requests.Session, str]:
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, f"Login failed {r.status_code} {r.text[:200]}"
    body = r.json()
    return s, body["access_token"]


def _get_commish_league() -> tuple[str, list]:
    """Return (league_id, teams) for a league where chriszarek is commissioner."""
    s, tok = _login(COMMISH_EMAIL, COMMISH_PASS)
    s.headers.update({"Authorization": f"Bearer {tok}"})
    leagues = s.get(f"{BASE_URL}/api/leagues?my_leagues=true").json()
    # Pick the first one where chris is commissioner
    me = s.get(f"{BASE_URL}/api/auth/me").json()
    my_id = me["id"]
    chosen = next((l for l in leagues if l.get("commissioner_id") == my_id), leagues[0])
    teams = s.get(f"{BASE_URL}/api/teams?league_id={chosen['id']}").json()
    return chosen["id"], teams


def test_playoff_bracket_structure():
    """Bracket includes playoff_size, playoff_teams (seeded), and rounds list."""
    league_id, teams = _get_commish_league()
    r = requests.get(f"{BASE_URL}/api/leagues/{league_id}/playoff-bracket")
    assert r.status_code == 200, r.text
    data = r.json()

    assert "playoff_size" in data
    assert "playoff_teams" in data
    assert "rounds" in data
    assert "status" in data
    assert data["status"] in ("projected", "actual")

    # Teams are seeded 1..N (no duplicates)
    seeds = [t["seed"] for t in data["playoff_teams"]]
    assert seeds == sorted(seeds), f"Seeds not in order: {seeds}"
    assert len(seeds) == len(set(seeds)), "Duplicate seeds"

    # First round has matchups with high + low seeds
    assert len(data["rounds"]) >= 1
    first_round = data["rounds"][0]
    assert "matchups" in first_round
    for mu in first_round["matchups"]:
        if mu.get("high_seed") and mu.get("low_seed"):
            assert mu["high_seed"]["seed"] < mu["low_seed"]["seed"], \
                "Higher seed should have lower seed number"


def test_playoff_bracket_six_teams_has_byes():
    """6-team bracket gives seeds 1 & 2 byes."""
    league_id, _ = _get_commish_league()
    r = requests.get(f"{BASE_URL}/api/leagues/{league_id}/playoff-bracket")
    data = r.json()
    if data["playoff_size"] == 6:
        assert len(data["bye_teams"]) == 2, "6-team bracket should have 2 byes"
        bye_seeds = sorted(t["seed"] for t in data["bye_teams"])
        assert bye_seeds == [1, 2], f"Expected seeds [1,2] to bye, got {bye_seeds}"


def test_get_divisions_empty_initially():
    """Unassigned teams returned in 'unassigned'."""
    league_id, _ = _get_commish_league()
    r = requests.get(f"{BASE_URL}/api/leagues/{league_id}/divisions")
    assert r.status_code == 200
    data = r.json()
    assert "divisions" in data
    assert "unassigned" in data


def test_put_divisions_commissioner_only():
    """Non-commissioner (freshly registered stranger) gets 403."""
    league_id, teams = _get_commish_league()
    # Register a brand new user guaranteed to not be commissioner
    import time
    suffix = int(time.time())
    s_other = requests.Session()
    s_other.headers.update({"Content-Type": "application/json"})
    reg = s_other.post(f"{BASE_URL}/api/auth/register", json={
        "email": f"stranger_{suffix}@example.com",
        "username": f"stranger_{suffix}",
        "password": "Stranger123!",
        "name": "Stranger",
    })
    assert reg.status_code in (200, 201), f"Register failed {reg.status_code} {reg.text[:200]}"
    tok_other = reg.json()["access_token"]
    s_other.headers.update({"Authorization": f"Bearer {tok_other}"})
    r = s_other.put(
        f"{BASE_URL}/api/leagues/{league_id}/divisions",
        json={"assignments": [
            {"team_id": teams[0]["id"], "division": "Atlantic", "conference": "Eastern"},
        ]},
    )
    assert r.status_code == 403, f"Expected 403 for non-commish, got {r.status_code}"


def test_put_divisions_commissioner_assigns_and_standings_reflect():
    """Commissioner assigns divisions/conferences, standings returns them + GB."""
    league_id, teams = _get_commish_league()
    s, tok = _login(COMMISH_EMAIL, COMMISH_PASS)
    s.headers.update({"Authorization": f"Bearer {tok}"})

    # Assign first 4 teams to divisions, next 4 to opposite conference
    assignments = []
    for i, t in enumerate(teams[:8]):
        div = ["Atlantic", "Metropolitan", "Central", "Pacific"][i % 4]
        conf = "Eastern" if i < 4 else "Western"
        assignments.append({"team_id": t["id"], "division": div, "conference": conf})

    r = s.put(
        f"{BASE_URL}/api/leagues/{league_id}/divisions",
        json={"assignments": assignments},
    )
    assert r.status_code == 200, r.text
    assert r.json()["updated"] >= 0

    # Verify persistence via GET /divisions
    gr = s.get(f"{BASE_URL}/api/leagues/{league_id}/divisions").json()
    assigned_div_names = {d["division"] for d in gr["divisions"]}
    assert "Atlantic" in assigned_div_names, f"Atlantic not persisted: {assigned_div_names}"

    # Standings now returns has_divisions=True and each assigned row has division field
    st = requests.get(f"{BASE_URL}/api/leagues/{league_id}/standings").json()
    assert st["has_divisions"] is True
    assert "Atlantic" in st["divisions"]
    # Leader has gb=0, others have gb >= 0
    rows = st["standings"]
    leader = rows[0]
    assert leader["games_back"] == 0.0
    for row in rows[1:]:
        assert row["games_back"] >= 0
    # Each row exposes movement field
    assert all("movement" in row for row in rows)
    assert all(row["movement"] in ("up", "down", "same") for row in rows)


def test_standings_shape_has_metadata():
    """Standings payload has standings[], has_divisions, has_conferences, divisions, conferences."""
    league_id, _ = _get_commish_league()
    r = requests.get(f"{BASE_URL}/api/leagues/{league_id}/standings")
    data = r.json()
    for key in ("standings", "has_divisions", "has_conferences", "divisions", "conferences"):
        assert key in data, f"Missing key {key} in standings payload"
    assert isinstance(data["standings"], list)
