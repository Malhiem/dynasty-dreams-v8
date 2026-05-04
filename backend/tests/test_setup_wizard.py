"""Tests for Setup Wizard backend endpoints:
  POST /api/leagues/{id}/setup-complete
  POST /api/leagues/{id}/setup-reset
And LeagueResponse now includes `setup_wizard_complete`.
"""
import os
import uuid

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
    body = r.json()
    s.headers.update({"Authorization": f"Bearer {body['access_token']}"})
    return s


def _pick_commish_league(s):
    me = s.get(f"{BASE_URL}/api/auth/me").json()
    leagues = s.get(f"{BASE_URL}/api/leagues?my_leagues=true").json()
    for l in leagues:
        if l.get("commissioner_id") == me["id"]:
            return l["id"]
    return leagues[0]["id"]


def test_league_response_exposes_setup_wizard_flag():
    s = _login(COMMISH_EMAIL, COMMISH_PASS)
    lid = _pick_commish_league(s)
    r = s.get(f"{BASE_URL}/api/leagues/{lid}")
    assert r.status_code == 200
    body = r.json()
    assert "setup_wizard_complete" in body
    assert isinstance(body["setup_wizard_complete"], bool)


def test_setup_complete_flips_flag():
    s = _login(COMMISH_EMAIL, COMMISH_PASS)
    lid = _pick_commish_league(s)

    # Reset first (to ensure a clean slate)
    s.post(f"{BASE_URL}/api/leagues/{lid}/setup-reset")
    before = s.get(f"{BASE_URL}/api/leagues/{lid}").json()
    assert before["setup_wizard_complete"] is False

    r = s.post(f"{BASE_URL}/api/leagues/{lid}/setup-complete")
    assert r.status_code == 200, r.text
    assert r.json()["setup_wizard_complete"] is True

    after = s.get(f"{BASE_URL}/api/leagues/{lid}").json()
    assert after["setup_wizard_complete"] is True


def test_setup_reset_restores_flag():
    s = _login(COMMISH_EMAIL, COMMISH_PASS)
    lid = _pick_commish_league(s)

    # Mark complete first
    s.post(f"{BASE_URL}/api/leagues/{lid}/setup-complete")
    complete = s.get(f"{BASE_URL}/api/leagues/{lid}").json()
    assert complete["setup_wizard_complete"] is True

    r = s.post(f"{BASE_URL}/api/leagues/{lid}/setup-reset")
    assert r.status_code == 200
    assert r.json()["setup_wizard_complete"] is False

    reset = s.get(f"{BASE_URL}/api/leagues/{lid}").json()
    assert reset["setup_wizard_complete"] is False


def test_setup_complete_commissioner_only():
    """Stranger can't complete/reset someone else's league setup."""
    suffix = uuid.uuid4().hex[:8]
    stranger = requests.Session()
    stranger.headers.update({"Content-Type": "application/json"})
    reg = stranger.post(f"{BASE_URL}/api/auth/register", json={
        "email": f"wiz_stranger_{suffix}@example.com",
        "username": f"wiz_stranger_{suffix}",
        "password": "Stranger123!",
        "name": "Stranger",
    })
    assert reg.status_code in (200, 201)
    stranger.headers.update({"Authorization": f"Bearer {reg.json()['access_token']}"})

    commish = _login(COMMISH_EMAIL, COMMISH_PASS)
    lid = _pick_commish_league(commish)

    r = stranger.post(f"{BASE_URL}/api/leagues/{lid}/setup-complete")
    assert r.status_code == 403

    r2 = stranger.post(f"{BASE_URL}/api/leagues/{lid}/setup-reset")
    assert r2.status_code == 403
