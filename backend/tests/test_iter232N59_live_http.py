"""Live HTTP integration test for Iter 232N.59 admin test sandbox.

Covers real REST endpoints via REACT_APP_BACKEND_URL:
  - Auth admin login
  - GET /api/admin/test-sandbox/presets
  - POST /api/admin/test-sandbox/leagues (create sandbox)
  - GET /api/admin/test-sandbox/leagues
  - POST /api/admin/test-sandbox/leagues/{id}/add-test-user
  - GET /api/admin/test-sandbox/test-users
  - POST /api/auth/impersonate-start rejects non-test targets (403)
  - POST /api/auth/impersonate-start accepts test-account (200)
  - DELETE /api/admin/test-sandbox/leagues/{id} cascade
"""
from __future__ import annotations

import os
import pytest
import requests

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL",
    "https://dynasty-preview.preview.emergentagent.com",
).rstrip("/")
ADMIN_EMAIL = "admin@dynastydreams.com"
ADMIN_PASSWORD = "Admin123!"


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=15,
    )
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text[:200]}"
    return s


@pytest.fixture(scope="module")
def anon_session():
    return requests.Session()


def test_presets_admin_ok(admin_session):
    r = admin_session.get(f"{BASE_URL}/api/admin/test-sandbox/presets", timeout=10)
    assert r.status_code == 200, r.text[:200]
    data = r.json()
    keys = {p["key"] for p in data["presets"]}
    assert keys == {"nhl_redraft_12", "nhl_dynasty_16", "nhl_keeper_10"}
    assert data.get("shared_password")


def test_presets_anon_forbidden(anon_session):
    r = anon_session.get(f"{BASE_URL}/api/admin/test-sandbox/presets", timeout=10)
    assert r.status_code in (401, 403), r.status_code


# Track created sandbox for cleanup
_created = {}


def test_create_sandbox(admin_session):
    r = admin_session.post(
        f"{BASE_URL}/api/admin/test-sandbox/leagues",
        json={"preset_key": "nhl_redraft_12", "num_teams": 6},
        timeout=30,
    )
    assert r.status_code == 200, r.text[:300]
    data = r.json()
    assert data["num_teams"] == 6
    assert len(data["teams"]) == 6
    for t in data["teams"]:
        assert t["owner_email"].endswith("@sandbox.local")
    _created["league_id"] = data["league_id"]
    _created["teams"] = data["teams"]
    _created["password"] = data.get("user_password")


def test_create_rejects_over_cap(admin_session):
    r = admin_session.post(
        f"{BASE_URL}/api/admin/test-sandbox/leagues",
        json={"preset_key": "nhl_redraft_12", "num_teams": 21},
        timeout=15,
    )
    assert r.status_code in (400, 422), r.status_code


def test_list_leagues_contains_created(admin_session):
    r = admin_session.get(f"{BASE_URL}/api/admin/test-sandbox/leagues", timeout=15)
    assert r.status_code == 200
    ids = [x["id"] for x in r.json()["leagues"]]
    assert _created["league_id"] in ids


def test_add_user_bumps(admin_session):
    lid = _created["league_id"]
    r = admin_session.post(
        f"{BASE_URL}/api/admin/test-sandbox/leagues/{lid}/add-test-user",
        json={"name": "TEST_ExtraMgr"},
        timeout=15,
    )
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    assert body["name"] == "TEST_ExtraMgr"


def test_list_users_filter(admin_session):
    lid = _created["league_id"]
    r = admin_session.get(
        f"{BASE_URL}/api/admin/test-sandbox/test-users",
        params={"league_id": lid},
        timeout=15,
    )
    assert r.status_code == 200
    users = r.json()["users"]
    assert len(users) == 7  # 6 seeded + 1 added
    for u in users:
        assert u["league_id"] == lid


def test_impersonate_rejects_non_test_account(admin_session):
    # Try to impersonate the admin themselves (not a test account)
    me = admin_session.get(f"{BASE_URL}/api/auth/me", timeout=10).json()
    r = admin_session.post(
        f"{BASE_URL}/api/auth/impersonate-start",
        json={"target_user_id": me["id"], "reason": "neg-test"},
        timeout=10,
    )
    assert r.status_code == 403, f"Expected 403, got {r.status_code}: {r.text[:200]}"
    assert "test-sandbox" in r.text.lower() or "test_sandbox" in r.text.lower() or "sandbox" in r.text.lower()


def test_impersonate_accepts_test_account(admin_session):
    target_uid = _created["teams"][0]["owner_user_id"]
    r = admin_session.post(
        f"{BASE_URL}/api/auth/impersonate-start",
        json={"target_user_id": target_uid, "reason": "sandbox-test"},
        timeout=10,
    )
    assert r.status_code == 200, r.text[:300]
    # Now /auth/me should return the impersonated user
    me = admin_session.get(f"{BASE_URL}/api/auth/me", timeout=10).json()
    assert me["email"].endswith("@sandbox.local"), me.get("email")
    # Stop impersonation to restore admin identity
    admin_session.post(f"{BASE_URL}/api/auth/impersonate-stop", timeout=10)


def test_delete_cascade(admin_session):
    lid = _created["league_id"]
    r = admin_session.delete(
        f"{BASE_URL}/api/admin/test-sandbox/leagues/{lid}", timeout=30,
    )
    assert r.status_code == 200, r.text[:300]
    # verify gone
    r2 = admin_session.get(f"{BASE_URL}/api/admin/test-sandbox/leagues", timeout=15)
    ids = [x["id"] for x in r2.json()["leagues"]]
    assert lid not in ids
