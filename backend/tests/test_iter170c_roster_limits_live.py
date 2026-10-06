"""Iter 170c — Live HTTP integration tests for the new roster-limits endpoints."""
import os
import pytest
import requests

API_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://dynasty-preview.preview.emergentagent.com")
LEAGUE_ID = "69e46af167999bfb85c39628"  # Ice Kings Head-to-Head (Chris Zarek's league)

ADMIN_EMAIL = os.environ.get("TEST_OWNER_EMAIL", "test-owner@e2e.dynastydreams.com")
ADMIN_PASSWORD = os.environ.get("TEST_OWNER_PASSWORD", "e2e-owner-password")


def _token():
    r = requests.post(f"{API_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=10)
    r.raise_for_status()
    data = r.json()
    return data.get("access_token") or data.get("token")


@pytest.fixture(scope="module")
def token():
    return _token()


def test_get_roster_limits_returns_defaults_plus_persisted(token):
    r = requests.get(f"{API_URL}/api/leagues/{LEAGUE_ID}/roster-limits",
                     headers={"Authorization": f"Bearer {token}"}, timeout=10)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["league_id"] == LEAGUE_ID
    for key in ("starting_skaters", "starting_goalies", "bench", "ir", "minors"):
        assert key in data["roster_limits"]
        assert key in data["defaults"]


def test_put_roster_limits_persists_and_diff(token):
    headers = {"Authorization": f"Bearer {token}"}
    # Round-trip change
    r1 = requests.put(f"{API_URL}/api/leagues/{LEAGUE_ID}/roster-limits",
                      headers=headers, json={"bench": 7}, timeout=10)
    assert r1.status_code == 200, r1.text
    body1 = r1.json()
    assert body1["roster_limits"]["bench"] == 7
    assert body1["changed"] is True
    assert body1["diff"]["bench"]["to"] == 7

    # Read-back
    r2 = requests.get(f"{API_URL}/api/leagues/{LEAGUE_ID}/roster-limits", headers=headers, timeout=10)
    assert r2.json()["roster_limits"]["bench"] == 7

    # Restore to default
    r3 = requests.put(f"{API_URL}/api/leagues/{LEAGUE_ID}/roster-limits",
                      headers=headers, json={"bench": 6}, timeout=10)
    assert r3.status_code == 200, r3.text
    assert r3.json()["roster_limits"]["bench"] == 6


def test_put_roster_limits_rejects_out_of_range(token):
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.put(f"{API_URL}/api/leagues/{LEAGUE_ID}/roster-limits",
                     headers=headers, json={"bench": 99}, timeout=10)
    assert r.status_code == 400
    assert "between 0 and 50" in r.text


def test_put_roster_limits_rejects_non_integer(token):
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.put(f"{API_URL}/api/leagues/{LEAGUE_ID}/roster-limits",
                     headers=headers, json={"bench": "five"}, timeout=10)
    assert r.status_code == 400
    assert "must be an integer" in r.text


def test_get_roster_limits_unknown_league_404(token):
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.get(f"{API_URL}/api/leagues/000000000000000000000000/roster-limits",
                     headers=headers, timeout=10)
    assert r.status_code == 404
