"""Iter 231k — Smoke probes for routed endpoints after drafts.py extraction.

Verifies the new draft_queue.py and draft_auction.py routers are wired and
return 2xx/4xx (NOT 5xx) when invoked with a real auth session.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://dynasty-preview.preview.emergentagent.com").rstrip("/")
CREDS = {"email": "chriszarek@gmail.com", "password": "Chris2026!"}


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json=CREDS, timeout=15)
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text[:200]}"
    return s


def test_pending_trades_endpoint_smoke(session):
    r = session.get(f"{BASE_URL}/api/users/me/pending-trades", timeout=15)
    assert r.status_code == 200
    data = r.json()
    assert "awaiting_response" in data
    assert "in_review" in data
    assert isinstance(data["awaiting_response"], list)
    assert isinstance(data["in_review"], list)


def test_drafts_list_smoke(session):
    # Find a league for this user
    leagues = session.get(f"{BASE_URL}/api/leagues", timeout=15).json()
    assert isinstance(leagues, list) and len(leagues) > 0
    league_id = leagues[0]["id"]
    r = session.get(f"{BASE_URL}/api/drafts", params={"league_id": league_id}, timeout=15)
    assert r.status_code == 200


def test_team_draft_queue_smoke(session):
    # Find a team for this user
    leagues = session.get(f"{BASE_URL}/api/leagues", timeout=15).json()
    league_id = leagues[0]["id"]
    teams = session.get(f"{BASE_URL}/api/teams", params={"league_id": league_id}, timeout=15).json()
    if not teams:
        pytest.skip("No teams in league")
    # Pick first team owned by current user, fallback to first team
    me = session.get(f"{BASE_URL}/api/auth/me", timeout=15).json()
    my_uid = me.get("id")
    team = next((t for t in teams if t.get("owner_id") == my_uid), teams[0])
    team_id = team["id"]
    r = session.get(f"{BASE_URL}/api/teams/{team_id}/draft-queue", timeout=15)
    assert r.status_code in (200, 403, 404), f"unexpected status {r.status_code}: {r.text[:200]}"


def test_team_shortlist_smoke(session):
    leagues = session.get(f"{BASE_URL}/api/leagues", timeout=15).json()
    league_id = leagues[0]["id"]
    teams = session.get(f"{BASE_URL}/api/teams", params={"league_id": league_id}, timeout=15).json()
    if not teams:
        pytest.skip("No teams in league")
    me = session.get(f"{BASE_URL}/api/auth/me", timeout=15).json()
    my_uid = me.get("id")
    team = next((t for t in teams if t.get("owner_id") == my_uid), teams[0])
    team_id = team["id"]
    r = session.get(f"{BASE_URL}/api/teams/{team_id}/shortlist", timeout=15)
    assert r.status_code in (200, 403, 404), f"unexpected status {r.status_code}: {r.text[:200]}"


def test_auction_state_smoke(session):
    """auction/state should not 5xx; returns 200 if auction draft, 404 otherwise."""
    leagues = session.get(f"{BASE_URL}/api/leagues", timeout=15).json()
    league_id = leagues[0]["id"]
    drafts = session.get(f"{BASE_URL}/api/drafts", params={"league_id": league_id}, timeout=15).json()
    if not drafts:
        pytest.skip("No drafts in this league")
    draft_id = drafts[0].get("id") or drafts[0].get("_id")
    assert draft_id, f"draft has neither id nor _id: {list(drafts[0].keys())[:8]}"
    r = session.get(f"{BASE_URL}/api/drafts/{draft_id}/auction/state", timeout=15)
    # Snake draft → 400/404; auction draft → 200
    assert r.status_code in (200, 400, 404), f"unexpected status {r.status_code}: {r.text[:200]}"
    assert r.status_code < 500, f"5xx on auction state: {r.text[:200]}"
