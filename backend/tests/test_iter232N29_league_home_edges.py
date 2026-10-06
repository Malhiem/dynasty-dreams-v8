"""Iter 232N.29 — edge-case validation for league-home-layout PATCH."""
from __future__ import annotations

import httpx
import pytest
from bson import ObjectId


def _base_url() -> str:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip()
    raise RuntimeError("REACT_APP_BACKEND_URL missing")


BASE = _base_url()


@pytest.fixture
def token():
    email = f"lh_edge_{ObjectId()}@example.com"
    reg = httpx.post(
        f"{BASE}/api/auth/register",
        json={"email": email, "password": "Passw0rd!", "username": f"lhe_{str(ObjectId())[-12:]}"[:20]},
        timeout=30.0,
    )
    assert reg.status_code in (200, 201), reg.text
    return reg.json().get("access_token") or reg.json().get("token")


def _auth(t): return {"Authorization": f"Bearer {t}"}


def test_accepts_32_widget_order(token):
    league = str(ObjectId())
    order = [f"w{i}" for i in range(32)]
    r = httpx.patch(f"{BASE}/api/users/me/league-home-layout/{league}", json={"widget_order": order}, headers=_auth(token), timeout=30.0)
    assert r.status_code == 200, r.text
    assert len(r.json()["widget_order"]) == 32


def test_rejects_more_than_32_widget_order(token):
    league = str(ObjectId())
    order = [f"w{i}" for i in range(33)]
    r = httpx.patch(f"{BASE}/api/users/me/league-home-layout/{league}", json={"widget_order": order}, headers=_auth(token), timeout=30.0)
    assert r.status_code == 400, r.text


def test_drops_non_string_ids(token):
    league = str(ObjectId())
    r = httpx.patch(f"{BASE}/api/users/me/league-home-layout/{league}", json={"widget_order": ["ok", 123, None, {"x": 1}, "also_ok"]}, headers=_auth(token), timeout=30.0)
    assert r.status_code == 200
    assert r.json()["widget_order"] == ["ok", "also_ok"]


def test_drops_ids_longer_than_64(token):
    league = str(ObjectId())
    long_id = "x" * 65
    r = httpx.patch(f"{BASE}/api/users/me/league-home-layout/{league}", json={"widget_order": ["good", long_id]}, headers=_auth(token), timeout=30.0)
    assert r.status_code == 200
    assert r.json()["widget_order"] == ["good"]


def test_visibility_32_cap(token):
    league = str(ObjectId())
    vis = {f"w{i}": True for i in range(33)}
    r = httpx.patch(f"{BASE}/api/users/me/league-home-layout/{league}", json={"visibility": vis}, headers=_auth(token), timeout=30.0)
    assert r.status_code == 400
