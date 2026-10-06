"""Iter 232N.29 — League Home layout sync endpoints (integration test
against the live-running preview server so we don't have to boot FastAPI
lifespan events inside pytest)."""
from __future__ import annotations

import os
import pytest
from bson import ObjectId
import httpx

# Preview URL is stored in the frontend .env; parsing it here keeps this
# test env-agnostic.
def _base_url() -> str:
    frontend_env = "/app/frontend/.env"
    with open(frontend_env) as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip()
    raise RuntimeError("REACT_APP_BACKEND_URL missing from frontend/.env")


BASE = _base_url()


@pytest.fixture
def token():
    email = f"lh_layout_{ObjectId()}@example.com"
    reg = httpx.post(
        f"{BASE}/api/auth/register",
        json={"email": email, "password": "Passw0rd!", "username": f"lh_{str(ObjectId())[-12:]}"[:20]},
        timeout=30.0,
    )
    assert reg.status_code in (200, 201), reg.text
    tok = reg.json().get("access_token") or reg.json().get("token")
    assert tok, reg.text
    yield tok


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_get_returns_empty_layout_before_any_patch(token):
    league_id = str(ObjectId())
    res = httpx.get(f"{BASE}/api/users/me/league-home-layout/{league_id}", headers=_auth(token), timeout=30.0)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["league_id"] == league_id
    assert body["widget_order"] == []
    assert body["visibility"] == {}


def test_patch_persists_order_and_visibility(token):
    league_id = str(ObjectId())
    payload = {
        "widget_order": ["quick_actions", "pending_trades", "matchups"],
        "visibility": {"matchups": True, "top_trade_block": False},
    }
    patch_res = httpx.patch(f"{BASE}/api/users/me/league-home-layout/{league_id}", json=payload, headers=_auth(token), timeout=30.0)
    assert patch_res.status_code == 200, patch_res.text
    assert patch_res.json()["widget_order"] == payload["widget_order"]
    get_res = httpx.get(f"{BASE}/api/users/me/league-home-layout/{league_id}", headers=_auth(token), timeout=30.0)
    assert get_res.status_code == 200
    assert get_res.json()["widget_order"] == payload["widget_order"]
    assert get_res.json()["visibility"] == payload["visibility"]


def test_patch_scoped_per_league(token):
    league_a = str(ObjectId())
    league_b = str(ObjectId())
    httpx.patch(f"{BASE}/api/users/me/league-home-layout/{league_a}", json={"widget_order": ["a1", "a2"]}, headers=_auth(token), timeout=30.0)
    httpx.patch(f"{BASE}/api/users/me/league-home-layout/{league_b}", json={"widget_order": ["b1", "b2", "b3"]}, headers=_auth(token), timeout=30.0)
    a = httpx.get(f"{BASE}/api/users/me/league-home-layout/{league_a}", headers=_auth(token), timeout=30.0)
    b = httpx.get(f"{BASE}/api/users/me/league-home-layout/{league_b}", headers=_auth(token), timeout=30.0)
    assert a.json()["widget_order"] == ["a1", "a2"]
    assert b.json()["widget_order"] == ["b1", "b2", "b3"]


def test_patch_rejects_non_list_widget_order(token):
    league_id = str(ObjectId())
    res = httpx.patch(
        f"{BASE}/api/users/me/league-home-layout/{league_id}",
        json={"widget_order": "not-a-list"},
        headers=_auth(token), timeout=30.0,
    )
    assert res.status_code == 400


def test_patch_partial_visibility_only(token):
    league_id = str(ObjectId())
    res = httpx.patch(
        f"{BASE}/api/users/me/league-home-layout/{league_id}",
        json={"visibility": {"quick_actions": False}},
        headers=_auth(token), timeout=30.0,
    )
    assert res.status_code == 200
    assert res.json()["visibility"] == {"quick_actions": False}
    get_res = httpx.get(f"{BASE}/api/users/me/league-home-layout/{league_id}", headers=_auth(token), timeout=30.0)
    assert get_res.json()["widget_order"] == []
    assert get_res.json()["visibility"] == {"quick_actions": False}


def test_patch_requires_auth():
    league_id = str(ObjectId())
    res = httpx.patch(
        f"{BASE}/api/users/me/league-home-layout/{league_id}",
        json={"widget_order": ["quick_actions"]},
        timeout=30.0,
    )
    assert res.status_code in (401, 403)
