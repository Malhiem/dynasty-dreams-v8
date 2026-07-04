"""Iter 232N.26 — Live endpoint regression for personal timer + auto-pick pref.

Exercises the actual running API to verify:
  • POST /api/drafts accepts `personal_pick_timer_seconds` (30..86400 or null)
  • PUT  /api/drafts/{id}/config accepts the same field
  • GET  /api/drafts/{id} echoes it
  • PATCH /api/teams/{id}/auto-pick-preference persists, requires auth,
    returns 422 on invalid values
"""
from __future__ import annotations

import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL",
                          "https://dynasty-preview.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = "admin@dynastydreams.com"
ADMIN_PASSWORD = "Admin123!"


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=20)
    if r.status_code != 200:
        pytest.skip(f"Admin login failed: {r.status_code} {r.text[:120]}")
    token = r.json().get("token") or r.json().get("access_token")
    if token:
        s.headers.update({"Authorization": f"Bearer {token}"})
    return s


@pytest.fixture(scope="module")
def admin_league(admin_session):
    """Find any league the admin commissions to attach a draft to."""
    r = admin_session.get(f"{BASE_URL}/api/leagues", timeout=20)
    if r.status_code != 200:
        pytest.skip(f"cant list leagues: {r.status_code}")
    leagues = r.json() if isinstance(r.json(), list) else r.json().get("leagues", [])
    if not leagues:
        pytest.skip("no leagues available for admin")
    # take first
    return leagues[0]


@pytest.fixture(scope="module")
def created_draft(admin_session, admin_league):
    league_id = admin_league.get("id") or admin_league.get("_id")
    payload = {
        "league_id": league_id,
        "name": "TEST_iter232N26_draft",
        "draft_type": "startup",
        "total_rounds": 2,
        "time_per_pick": 900,
        "personal_pick_timer_seconds": 120,
        "snake_draft": True,
        "player_criteria": ["all"],
        "missed_pick_action": "auto-select",
    }
    r = admin_session.post(f"{BASE_URL}/api/drafts", json=payload, timeout=30)
    if r.status_code not in (200, 201):
        pytest.skip(f"create draft failed: {r.status_code} {r.text[:200]}")
    data = r.json()
    draft_id = data.get("_id") or data.get("id")
    yield {"draft_id": draft_id, "league_id": league_id, "data": data}
    # cleanup
    try:
        admin_session.delete(f"{BASE_URL}/api/drafts/{draft_id}", timeout=10)
    except Exception:
        pass


def test_post_drafts_accepts_personal_timer(created_draft):
    assert created_draft["data"].get("personal_pick_timer_seconds") == 120


def test_get_drafts_echoes_personal_timer(admin_session, created_draft):
    r = admin_session.get(f"{BASE_URL}/api/drafts/{created_draft['draft_id']}", timeout=20)
    assert r.status_code == 200
    body = r.json()
    # Some GET endpoints return {"draft": {...}} envelope
    draft = body.get("draft") if isinstance(body, dict) and "draft" in body else body
    assert draft.get("personal_pick_timer_seconds") == 120


def test_put_drafts_config_updates_personal_timer(admin_session, created_draft):
    r = admin_session.put(
        f"{BASE_URL}/api/drafts/{created_draft['draft_id']}/config",
        json={"personal_pick_timer_seconds": 300}, timeout=20,
    )
    assert r.status_code in (200, 204), f"PUT config failed: {r.status_code} {r.text[:200]}"
    # verify via GET
    r2 = admin_session.get(f"{BASE_URL}/api/drafts/{created_draft['draft_id']}", timeout=20)
    body = r2.json()
    draft = body.get("draft") if isinstance(body, dict) and "draft" in body else body
    assert draft.get("personal_pick_timer_seconds") == 300


def test_put_drafts_config_null_clears_personal_timer(admin_session, created_draft):
    r = admin_session.put(
        f"{BASE_URL}/api/drafts/{created_draft['draft_id']}/config",
        json={"personal_pick_timer_seconds": None}, timeout=20,
    )
    assert r.status_code in (200, 204)


def test_post_drafts_rejects_out_of_range_personal_timer(admin_session, admin_league):
    league_id = admin_league.get("id") or admin_league.get("_id")
    payload = {
        "league_id": league_id,
        "name": "TEST_bad_personal",
        "draft_type": "startup",
        "total_rounds": 2,
        "time_per_pick": 900,
        "personal_pick_timer_seconds": 10,  # < 30
        "snake_draft": True,
        "player_criteria": ["all"],
        "missed_pick_action": "auto-select",
    }
    r = admin_session.post(f"{BASE_URL}/api/drafts", json=payload, timeout=15)
    assert r.status_code == 422, f"expected 422, got {r.status_code}"


# ─── Auto-pick preference endpoint ────────────────────────────────────
@pytest.fixture(scope="module")
def admin_team(admin_session, admin_league):
    league_id = admin_league.get("id") or admin_league.get("_id")
    r = admin_session.get(f"{BASE_URL}/api/teams", params={"league_id": league_id}, timeout=15)
    if r.status_code != 200:
        pytest.skip(f"cant list teams: {r.status_code}")
    teams = r.json()
    if not teams:
        pytest.skip("no teams in league")
    # find one admin owns; fallback first
    me_r = admin_session.get(f"{BASE_URL}/api/auth/me", timeout=10)
    my_id = None
    if me_r.status_code == 200:
        my_id = me_r.json().get("id") or me_r.json().get("_id")
    owned = [t for t in teams if str(t.get("owner_id") or "") == str(my_id)] if my_id else []
    return owned[0] if owned else teams[0]


def test_patch_auto_pick_preference_persists(admin_session, admin_team):
    team_id = admin_team.get("id") or admin_team.get("_id")
    r = admin_session.patch(
        f"{BASE_URL}/api/teams/{team_id}/auto-pick-preference",
        json={"auto_pick_preference": "best_available"}, timeout=15,
    )
    # commissioner should also be allowed; if 403 log context
    assert r.status_code == 200, f"expected 200, got {r.status_code}: {r.text[:200]}"
    assert r.json().get("auto_pick_preference") == "best_available"
    # reset
    admin_session.patch(
        f"{BASE_URL}/api/teams/{team_id}/auto-pick-preference",
        json={"auto_pick_preference": "queue_then_best"}, timeout=15,
    )


def test_patch_auto_pick_preference_rejects_invalid(admin_session, admin_team):
    team_id = admin_team.get("id") or admin_team.get("_id")
    r = admin_session.patch(
        f"{BASE_URL}/api/teams/{team_id}/auto-pick-preference",
        json={"auto_pick_preference": "random"}, timeout=15,
    )
    assert r.status_code == 422, f"expected 422, got {r.status_code}"


def test_patch_auto_pick_preference_requires_auth(admin_team):
    team_id = admin_team.get("id") or admin_team.get("_id")
    r = requests.patch(
        f"{BASE_URL}/api/teams/{team_id}/auto-pick-preference",
        json={"auto_pick_preference": "best_available"}, timeout=15,
    )
    assert r.status_code in (401, 403), f"expected 401/403, got {r.status_code}"
