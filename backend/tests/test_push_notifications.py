"""Tests for Expo Push Notification registration + deactivation endpoints."""
import os
import uuid

import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")


def _register_stranger() -> requests.Session:
    suffix = uuid.uuid4().hex[:8]
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{BASE_URL}/api/auth/register", json={
        "email": f"push_user_{suffix}@example.com",
        "username": f"push_user_{suffix}",
        "password": "Stranger123!",
        "name": "Push User",
    })
    assert r.status_code in (200, 201), r.text[:200]
    s.headers.update({"Authorization": f"Bearer {r.json()['access_token']}"})
    return s


def test_register_push_token_valid_format():
    s = _register_stranger()
    r = s.post(f"{BASE_URL}/api/push/register-token", json={
        "expo_push_token": "ExponentPushToken[abc123xyz]",
        "platform": "ios",
        "device_name": "iPhone (test)",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["is_active"] is True
    assert body["platform"] == "ios"
    assert "token_id" in body


def test_register_push_token_invalid_format_rejected():
    s = _register_stranger()
    r = s.post(f"{BASE_URL}/api/push/register-token", json={
        "expo_push_token": "FCM_not_expo",
        "platform": "android",
    })
    assert r.status_code == 400


def test_register_push_token_requires_auth():
    r = requests.post(f"{BASE_URL}/api/push/register-token", json={
        "expo_push_token": "ExponentPushToken[auth_required]",
        "platform": "ios",
    })
    assert r.status_code in (401, 403)


def test_list_my_tokens():
    s = _register_stranger()
    s.post(f"{BASE_URL}/api/push/register-token", json={
        "expo_push_token": f"ExponentPushToken[{uuid.uuid4().hex}]",
        "platform": "android",
    })
    r = s.get(f"{BASE_URL}/api/push/my-tokens")
    assert r.status_code == 200
    body = r.json()
    assert body["active_count"] >= 1
    assert all("expo_push_token" not in t for t in body["tokens"]), \
        "Raw token MUST NOT be in list response"


def test_deactivate_token():
    s = _register_stranger()
    reg = s.post(f"{BASE_URL}/api/push/register-token", json={
        "expo_push_token": f"ExponentPushToken[{uuid.uuid4().hex}]",
        "platform": "ios",
    })
    token_id = reg.json()["token_id"]
    r = s.delete(f"{BASE_URL}/api/push/tokens/{token_id}")
    assert r.status_code == 200
    assert r.json()["deactivated"] is True

    listing = s.get(f"{BASE_URL}/api/push/my-tokens").json()
    assert all(t["id"] != token_id for t in listing["tokens"])


def test_cannot_deactivate_someone_elses_token():
    owner = _register_stranger()
    reg = owner.post(f"{BASE_URL}/api/push/register-token", json={
        "expo_push_token": f"ExponentPushToken[{uuid.uuid4().hex}]",
        "platform": "ios",
    })
    token_id = reg.json()["token_id"]

    attacker = _register_stranger()
    r = attacker.delete(f"{BASE_URL}/api/push/tokens/{token_id}")
    assert r.status_code == 404


def test_upsert_same_token_does_not_duplicate():
    """Registering the same token twice should NOT create duplicates."""
    s = _register_stranger()
    tok = f"ExponentPushToken[{uuid.uuid4().hex}]"
    s.post(f"{BASE_URL}/api/push/register-token", json={"expo_push_token": tok, "platform": "ios"})
    s.post(f"{BASE_URL}/api/push/register-token", json={"expo_push_token": tok, "platform": "ios"})
    listing = s.get(f"{BASE_URL}/api/push/my-tokens").json()
    count = sum(1 for _ in listing["tokens"])
    assert count == 1, f"Expected 1 token after upsert, got {count}"


def test_test_push_does_not_crash():
    """POST /push/test with no Expo keys shouldn't blow up even when no tokens exist."""
    s = _register_stranger()
    r = s.post(f"{BASE_URL}/api/push/test")
    assert r.status_code == 200
    assert r.json()["sent"] is True
