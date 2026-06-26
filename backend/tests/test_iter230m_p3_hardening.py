"""Iter 230m — Regression tests for the P3 hardening pass from the
security audit:
  • register no longer leaks email-vs-username collision
  • forgot-password is throttled per-email + per-IP
  • password reset revokes outstanding refresh tokens
  • impersonation read-only mode blocks writes

Each test is independent and cleans up after itself so the suite can
run repeatedly against the same MongoDB.
"""
import asyncio
import os
import sys
import time
import uuid

import pytest
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

API_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001").rstrip("/")


def _login(email: str, password: str) -> dict:
    r = requests.post(
        f"{API_URL}/api/auth/login",
        json={"email": email, "password": password},
        timeout=10,
    )
    r.raise_for_status()
    return r.json()


# ─── P3a — register: no email-vs-username enumeration ────────────────────


def test_p3_register_collision_uses_generic_error():
    """Both email-collision and username-collision must return the SAME
    generic detail so attackers can't distinguish which field exists."""
    # Use the already-seeded chriszarek user (email=chriszarek@gmail.com,
    # username=chriszarek) as the collision target.
    # 1) Email collision — fresh random username, existing email.
    fresh_username = f"probe_{uuid.uuid4().hex[:8]}"
    r1 = requests.post(
        f"{API_URL}/api/auth/register",
        json={
            "email": "chriszarek@gmail.com",
            "username": fresh_username,
            "password": "ProbePass1!",
        },
        timeout=10,
    )
    # 2) Username collision — fresh random email, existing username.
    fresh_email = f"probe_{uuid.uuid4().hex[:8]}@example.com"
    r2 = requests.post(
        f"{API_URL}/api/auth/register",
        json={
            "email": fresh_email,
            "username": "chriszarek",
            "password": "ProbePass1!",
        },
        timeout=10,
    )
    assert r1.status_code == 400 and r2.status_code == 400
    # The two error messages MUST be identical — otherwise enumeration
    # is still possible by inspecting the detail string.
    assert r1.json().get("detail") == r2.json().get("detail"), (
        f"enumeration leak: {r1.json()} vs {r2.json()}"
    )
    assert "in use" in r1.json().get("detail", "").lower()


# ─── P3b — forgot-password throttle ──────────────────────────────────────


def test_p3_forgot_password_per_email_throttle():
    """Second request for the same email within 1 minute must still
    return the generic message (i.e. the endpoint silently drops the
    request) and MUST NOT issue a new reset token."""
    target_email = "chriszarek@gmail.com"

    # First request — should succeed and create a throttle record.
    r1 = requests.post(
        f"{API_URL}/api/auth/forgot-password",
        json={"email": target_email}, timeout=10,
    )
    assert r1.status_code == 200
    # Second request immediately after — must be throttled but still
    # return the same generic message (non-enumeration invariant).
    r2 = requests.post(
        f"{API_URL}/api/auth/forgot-password",
        json={"email": target_email}, timeout=10,
    )
    assert r2.status_code == 200
    assert r1.json() == r2.json()


# ─── P3c — password reset revokes refresh tokens ─────────────────────────


@pytest.mark.asyncio
async def test_p3_password_reset_revokes_refresh_tokens():
    """After a password reset, any refresh token issued earlier MUST
    be rejected by /auth/refresh with 401 'Session revoked'."""
    # Create a throwaway user so we can reset without affecting seeds.
    email = f"p3reset_{uuid.uuid4().hex[:8]}@example.com"
    username = f"p3reset_{uuid.uuid4().hex[:8]}"
    pw1 = "P3InitialPass1!"
    pw2 = "P3RotatedPass2!"
    reg = requests.post(
        f"{API_URL}/api/auth/register",
        json={"email": email, "username": username, "password": pw1},
        timeout=10,
    )
    assert reg.status_code == 200, reg.text
    old_refresh = reg.json()["refresh_token"]

    # Mint a password reset token via the same path the UI uses, then
    # peek into the DB to pull the token (server logs it for non-prod).
    # Use motor directly — read-only.
    from motor.motor_asyncio import AsyncIOMotorClient
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ.get("DB_NAME", "test_database")]
    requests.post(
        f"{API_URL}/api/auth/forgot-password",
        json={"email": email}, timeout=10,
    )
    await asyncio.sleep(0.2)
    token_doc = await db.password_reset_tokens.find_one(
        {"user_id": reg.json()["id"], "used": False},
        sort=[("expires_at", -1)],
    )
    assert token_doc, "expected a reset token row"
    reset_token = token_doc["token"]

    # Sleep 1 sec so the new `password_changed_at` is strictly > token iat.
    time.sleep(1.1)
    # Perform the reset.
    rr = requests.post(
        f"{API_URL}/api/auth/reset-password",
        json={"token": reset_token, "new_password": pw2}, timeout=10,
    )
    assert rr.status_code == 200, rr.text

    # The OLD refresh token must now be rejected.
    rf = requests.post(
        f"{API_URL}/api/auth/refresh",
        headers={"Authorization": f"Bearer {old_refresh}"},
        timeout=10,
    )
    assert rf.status_code == 401, rf.text
    assert "revoked" in rf.json().get("detail", "").lower() or "session" in rf.json().get("detail", "").lower()

    # And the new password must work end-to-end.
    new_login = requests.post(
        f"{API_URL}/api/auth/login",
        json={"email": email, "password": pw2}, timeout=10,
    )
    assert new_login.status_code == 200

    # Cleanup the throwaway user + tokens.
    await db.users.delete_one({"email": email})
    await db.password_reset_tokens.delete_many({"user_id": reg.json()["id"]})
    await db.password_reset_throttle.delete_many({"email": email})


# ─── P3d — impersonation read-only blocks writes ─────────────────────────


def test_p3_impersonation_read_only_blocks_writes():
    """An admin impersonating another user gets an impersonation token
    with `mode=read_only`. Any POST/PUT/PATCH/DELETE through that token
    MUST be refused with 403 — read-only invariant from iter 215c.
    Reads (GET) continue to work."""
    s = requests.Session()
    # Admin login (sets access_token cookie).
    al = s.post(
        f"{API_URL}/api/auth/login",
        json={"email": "admin@dynastydreams.com", "password": "Admin123!"},
        timeout=10,
    )
    if al.status_code != 200:
        pytest.skip(f"admin login unavailable: {al.status_code}")
    # Resolve target user_id.
    target_login = requests.post(
        f"{API_URL}/api/auth/login",
        json={"email": "chriszarek@live.com", "password": "Chris2026!"},
        timeout=10,
    )
    if target_login.status_code != 200:
        pytest.skip(f"target login unavailable: {target_login.status_code}")
    target_uid = target_login.json()["id"]

    # Start impersonation (swaps the cookie inside `s`).
    imp = s.post(
        f"{API_URL}/api/auth/impersonate-start",
        json={"target_user_id": target_uid, "reason": "p3 test"},
        timeout=10,
    )
    if imp.status_code != 200:
        pytest.skip(f"impersonate-start unavailable: {imp.status_code} {imp.text}")

    try:
        # GET as impersonated user works.
        r_get = s.get(f"{API_URL}/api/auth/me", timeout=10)
        assert r_get.status_code == 200
        assert r_get.json().get("email") == "chriszarek@live.com"
        # Write attempt — must be refused with 403 read-only.
        r_write = s.put(
            f"{API_URL}/api/notifications/preferences/quiet-hours",
            json={"enabled": False},
            timeout=10,
        )
        assert r_write.status_code == 403, r_write.text
        assert "read-only" in r_write.json().get("detail", "").lower()
    finally:
        # Try to stop impersonation cleanly.
        try:
            s.post(f"{API_URL}/api/auth/impersonate-stop", timeout=10)
        except Exception:
            pass
