"""Auth hardening regressions using fresh users in an isolated API database."""
import os
import time
import uuid
from datetime import datetime, timezone

import jwt

import requests
from bson import ObjectId

from security_http_fixtures import API_URL, PASSWORD, security_db, security_users


def test_p3_register_collision_uses_generic_error(security_users):
    user = security_users()
    responses = []
    for email, username in [(user["email"], f"probe_{uuid.uuid4().hex[:12]}"),
                            (f"probe_{uuid.uuid4().hex[:12]}@example.com", user["username"]),
                            (user["email"], user["username"])]:
        r = requests.post(f"{API_URL}/api/auth/register", json={
            "email": email, "username": username, "password": PASSWORD,
        }, timeout=10)
        assert r.status_code == 400, r.text
        responses.append(r.json())
    assert responses[0] == responses[1] == responses[2]
    assert "in use" in responses[0].get("detail", "").lower()


def test_p3_forgot_password_per_email_throttle(security_users, security_db):
    user = security_users()
    r1 = requests.post(f"{API_URL}/api/auth/forgot-password", json={"email": user["email"]}, timeout=10)
    assert r1.status_code == 200, r1.text
    before = list(security_db.password_reset_tokens.find({"user_id": user["id"]}))
    assert len(before) == 1, "First request must actually issue a reset token"
    r2 = requests.post(f"{API_URL}/api/auth/forgot-password", json={"email": user["email"]}, timeout=10)
    assert r2.status_code == 200, r2.text
    assert r1.json() == r2.json()
    assert list(security_db.password_reset_tokens.find({"user_id": user["id"]})) == before


def test_p3_password_reset_revokes_refresh_tokens(security_users, security_db):
    user = security_users()
    response = requests.post(f"{API_URL}/api/auth/forgot-password", json={"email": user["email"]}, timeout=10)
    assert response.status_code == 200, response.text
    token = security_db.password_reset_tokens.find_one({"user_id": user["id"], "used": False})
    assert token, "Expected a reset token in the API's database"
    # JWT iat is integer seconds; cross that boundary before changing the password.
    time.sleep(1.1)
    password = "SecurityRotated2026!"
    response = requests.post(f"{API_URL}/api/auth/reset-password", json={
        "token": token["token"], "new_password": password,
    }, timeout=10)
    assert response.status_code == 200, response.text
    response = requests.post(f"{API_URL}/api/auth/refresh", headers={
        "Authorization": f"Bearer {user['refresh_token']}"}, timeout=10)
    assert response.status_code == 401, response.text
    assert "revoked" in response.json().get("detail", "").lower()
    login = requests.post(f"{API_URL}/api/auth/login", json={"email": user["email"], "password": password}, timeout=10)
    assert login.status_code == 200, login.text
    fresh = requests.post(f"{API_URL}/api/auth/refresh", headers={
        "Authorization": f"Bearer {login.json()['refresh_token']}"}, timeout=10)
    assert fresh.status_code == 200, fresh.text


def test_p3_impersonation_read_only_blocks_writes(security_users):
    user = security_users()
    # Exercise the read-only token mode directly with the isolated stack's key.
    token = jwt.encode({"sub": user["id"], "type": "impersonation", "mode": "read_only",
                        "exp": time.time() + 60}, os.environ["JWT_SECRET"], algorithm="HS256")
    headers = {"Authorization": f"Bearer {token}"}
    read = requests.get(f"{API_URL}/api/auth/me", headers=headers, timeout=10)
    assert read.status_code == 200, read.text
    assert read.json()["id"] == user["id"]
    write = requests.put(f"{API_URL}/api/notifications/preferences/quiet-hours",
                         headers=headers, json={"enabled": False}, timeout=10)
    assert write.status_code == 403, write.text
    assert "read-only" in write.json().get("detail", "").lower()


def test_p3_sandbox_impersonation_requires_test_account(security_users, security_db):
    user = security_users()
    ordinary = requests.post(f"{API_URL}/api/auth/impersonate-start", headers=user["headers"],
                             json={"target_user_id": user["id"]}, timeout=10)
    assert ordinary.status_code == 403, ordinary.text
    with requests.Session() as session:
        login = session.post(f"{API_URL}/api/auth/login", json={
            "email": os.environ["ADMIN_EMAIL"], "password": os.environ["ADMIN_PASSWORD"],
        }, timeout=10)
        assert login.status_code == 200, login.text
        payload = {"target_user_id": user["id"], "reason": "isolated security regression"}
        denied = session.post(f"{API_URL}/api/auth/impersonate-start", json=payload, timeout=10)
        assert denied.status_code == 403, denied.text
        security_db.users.update_one({"_id": ObjectId(user["id"])}, {"$set": {"is_test_account": True}})
        imp = session.post(f"{API_URL}/api/auth/impersonate-start", json=payload, timeout=10)
        assert imp.status_code == 200, imp.text
        assert imp.json()["mode"] == "sandbox"
        try:
            read = session.get(f"{API_URL}/api/auth/me", timeout=10)
            assert read.status_code == 200, read.text
            assert read.json()["id"] == user["id"]
            write = session.put(f"{API_URL}/api/notifications/preferences/quiet-hours", json={"enabled": False}, timeout=10)
            assert write.status_code == 200, write.text
        finally:
            session.post(f"{API_URL}/api/auth/impersonate-stop", timeout=10)


def test_p3_refresh_tokens_within_same_second(security_users, security_db):
    user = security_users()
    base = int(time.time()) - 2
    changed = datetime.fromtimestamp(base + 0.5, timezone.utc)
    # New ISO timestamps preserve precision; old Mongo datetime records remain valid.
    for stored in [changed.isoformat(), changed]:
        security_db.users.update_one({"_id": ObjectId(user["id"])}, {"$set": {"password_changed_at": stored}})
        for issued_at, expected in [(base + 0.25, 401), (base + 0.75, 200), (base, 401), (None, 401)]:
            payload = {"sub": user["id"], "type": "refresh", "exp": time.time() + 60}
            if issued_at is not None:
                payload["iat"] = issued_at
            token = jwt.encode(payload, os.environ["JWT_SECRET"], algorithm="HS256")
            response = requests.post(f"{API_URL}/api/auth/refresh", headers={"Authorization": f"Bearer {token}"}, timeout=10)
            assert response.status_code == expected, response.text
