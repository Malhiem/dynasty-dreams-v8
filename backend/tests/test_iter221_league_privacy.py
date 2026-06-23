"""
Iter 221 — League visibility / privacy hardening for GET /api/leagues.

Previously the default `GET /api/leagues` returned every public league in
the system, leaking leagues a user never joined. This test locks the new
behavior:

  • default (no flags)        → only leagues the caller is a member of
  • ?my_leagues=true          → identical to default (kept for compat)
  • ?discover=true            → public leagues caller has NOT joined
  • ?all=true (admins only)   → every league, ignored for non-admins
"""
from __future__ import annotations

import os
import uuid
import requests

API_URL = os.environ["REACT_APP_BACKEND_URL"]
ADMIN_EMAIL = "admin@dynastydreams.com"
ADMIN_PASS = "Admin123!"


def _login(email, password):
    r = requests.post(f"{API_URL}/api/auth/login",
                      json={"email": email, "password": password})
    r.raise_for_status()
    return r.json()["access_token"]


def _register_user():
    suffix = uuid.uuid4().hex[:8]
    email = f"iter221_{suffix}@example.com"
    username = f"iter221_{suffix}"
    requests.post(f"{API_URL}/api/auth/register", json={
        "email": email, "password": "TestPass123!",
        "username": username, "name": f"Iter221 {suffix}",
    }).raise_for_status()
    return email, _login(email, "TestPass123!")


def _create_league(token, *, private=False, name=None):
    H = {"Authorization": f"Bearer {token}"}
    r = requests.post(f"{API_URL}/api/leagues", headers=H, json={
        "name": name or ("iter221 league " + uuid.uuid4().hex[:6]),
        "format": "dynasty", "scoring_format": "head_to_head",
        "max_teams": 10, "draft_type": "snake", "roster_spots": 20,
        "is_private": private,
    })
    r.raise_for_status()
    return r.json()


def test_default_get_leagues_only_returns_membership():
    """User A creates league. User B (separate account) hits default GET /leagues
    and must NOT see league A."""
    _, token_a = _register_user()
    league_a = _create_league(token_a, private=False)

    _, token_b = _register_user()
    H_b = {"Authorization": f"Bearer {token_b}"}

    r = requests.get(f"{API_URL}/api/leagues", headers=H_b)
    assert r.status_code == 200, r.text
    ids = [l["id"] for l in r.json()]
    assert league_a["id"] not in ids, (
        f"Privacy leak: user B sees league A in default response: {ids}"
    )


def test_my_leagues_returns_only_user_leagues():
    _, token_a = _register_user()
    league_a = _create_league(token_a)
    H_a = {"Authorization": f"Bearer {token_a}"}

    r = requests.get(f"{API_URL}/api/leagues?my_leagues=true", headers=H_a)
    assert r.status_code == 200
    ids = [l["id"] for l in r.json()]
    assert league_a["id"] in ids


def test_discover_returns_public_leagues_user_not_joined():
    _, token_a = _register_user()
    public_league = _create_league(token_a, private=False)
    private_league = _create_league(token_a, private=True)

    _, token_b = _register_user()
    H_b = {"Authorization": f"Bearer {token_b}"}

    r = requests.get(f"{API_URL}/api/leagues?discover=true", headers=H_b)
    assert r.status_code == 200, r.text
    ids = [l["id"] for l in r.json()]
    assert public_league["id"] in ids, "discover should expose public leagues"
    assert private_league["id"] not in ids, "discover must hide private leagues"


def test_discover_hides_already_joined_leagues():
    _, token_a = _register_user()
    league_a = _create_league(token_a, private=False)
    H_a = {"Authorization": f"Bearer {token_a}"}

    # User A is commissioner → discover should NOT re-suggest their own league
    r = requests.get(f"{API_URL}/api/leagues?discover=true", headers=H_a)
    assert r.status_code == 200
    ids = [l["id"] for l in r.json()]
    assert league_a["id"] not in ids


def test_admin_all_flag_returns_every_league():
    _, token_user = _register_user()
    user_league = _create_league(token_user, private=True)

    admin_token = _login(ADMIN_EMAIL, ADMIN_PASS)
    H = {"Authorization": f"Bearer {admin_token}"}
    r = requests.get(f"{API_URL}/api/leagues?all=true", headers=H)
    assert r.status_code == 200, r.text
    ids = [l["id"] for l in r.json()]
    assert user_league["id"] in ids, "admin?all=true must see every league"


def test_non_admin_all_flag_falls_back_to_membership():
    """Regular user passing all=true must NOT escalate to admin view."""
    _, token_a = _register_user()
    league_a = _create_league(token_a, private=False)

    _, token_b = _register_user()
    H_b = {"Authorization": f"Bearer {token_b}"}
    r = requests.get(f"{API_URL}/api/leagues?all=true", headers=H_b)
    assert r.status_code == 200
    ids = [l["id"] for l in r.json()]
    assert league_a["id"] not in ids, (
        "non-admin sent all=true and was leaked another user's league"
    )
