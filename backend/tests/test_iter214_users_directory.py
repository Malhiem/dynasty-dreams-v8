"""
Iter 214 — Admin Users directory + per-user identity / security drilldown.

Verifies:
1. /admin/platform/users — auth gating + payload shape + search + pagination
2. /admin/platform/users/{user_id} — identity & security drilldown payload
"""
from __future__ import annotations

import os
import requests

API_URL = os.environ["REACT_APP_BACKEND_URL"]
ADMIN_EMAIL = "admin@dynastydreams.com"
ADMIN_PASS = "Admin123!"
USER_EMAIL = "chriszarek@gmail.com"
USER_PASS = "Chris2026!"


def _login(email, password) -> str:
    r = requests.post(f"{API_URL}/api/auth/login", json={"email": email, "password": password})
    r.raise_for_status()
    return r.json()["access_token"]


def _admin_headers() -> dict:
    return {"Authorization": f"Bearer {_login(ADMIN_EMAIL, ADMIN_PASS)}"}


# ── /users — list ──

def test_users_unauth_returns_401():
    r = requests.get(f"{API_URL}/api/admin/platform/users")
    assert r.status_code == 401


def test_users_non_admin_returns_403():
    headers = {"Authorization": f"Bearer {_login(USER_EMAIL, USER_PASS)}"}
    r = requests.get(f"{API_URL}/api/admin/platform/users", headers=headers)
    assert r.status_code == 403


def test_users_admin_list_shape_and_pagination():
    r = requests.get(
        f"{API_URL}/api/admin/platform/users?limit=5",
        headers=_admin_headers(),
    )
    assert r.status_code == 200, r.text
    d = r.json()
    for key in ("total", "skip", "limit", "users"):
        assert key in d, f"missing key {key}"
    assert d["limit"] == 5
    assert isinstance(d["users"], list)
    assert len(d["users"]) <= 5
    if d["users"]:
        u = d["users"][0]
        for k in (
            "id", "email", "username", "role", "status",
            "created_at", "email_verified", "two_factor_enabled",
        ):
            assert k in u, f"user missing key {k}"


def test_users_admin_search_filter():
    r = requests.get(
        f"{API_URL}/api/admin/platform/users?q=admin@dynastydreams",
        headers=_admin_headers(),
    )
    assert r.status_code == 200
    d = r.json()
    emails = [u["email"] for u in d["users"]]
    assert any("admin@dynastydreams" in (e or "") for e in emails), emails


# ── /users/{id} — detail drilldown ──

def test_user_detail_non_admin_returns_403():
    headers = {"Authorization": f"Bearer {_login(USER_EMAIL, USER_PASS)}"}
    # Use the admin's own ID (looking up first user that matches admin email)
    list_r = requests.get(
        f"{API_URL}/api/admin/platform/users?q=admin@dynastydreams",
        headers=_admin_headers(),
    )
    uid = list_r.json()["users"][0]["id"]
    r = requests.get(f"{API_URL}/api/admin/platform/users/{uid}", headers=headers)
    assert r.status_code == 403


def test_user_detail_admin_shape():
    list_r = requests.get(
        f"{API_URL}/api/admin/platform/users?q=admin@dynastydreams",
        headers=_admin_headers(),
    )
    uid = list_r.json()["users"][0]["id"]
    r = requests.get(
        f"{API_URL}/api/admin/platform/users/{uid}", headers=_admin_headers(),
    )
    assert r.status_code == 200, r.text
    d = r.json()
    # Identity core
    for k in (
        "id", "username", "email", "email_verified", "phone", "phone_verified",
        "auth_method", "password_hash_present", "linked_sso_accounts", "role",
        "status", "created_at", "username_change_history",
    ):
        assert k in d, f"missing identity key {k}"
    # Security
    for k in (
        "last_login_at", "login_history", "failed_login_attempts",
        "lockout_until", "two_factor_enabled", "two_factor_method",
        "password_reset_history", "active_sessions", "recovery_email",
        "security_questions_set",
    ):
        assert k in d, f"missing security key {k}"
    # Login history populated for the admin (we logged in to call this test)
    assert isinstance(d["login_history"], list)


def test_user_detail_bad_id_returns_400():
    r = requests.get(
        f"{API_URL}/api/admin/platform/users/not-an-oid", headers=_admin_headers(),
    )
    assert r.status_code == 400


def test_user_detail_unknown_id_returns_404():
    r = requests.get(
        f"{API_URL}/api/admin/platform/users/000000000000000000000000",
        headers=_admin_headers(),
    )
    assert r.status_code == 404
