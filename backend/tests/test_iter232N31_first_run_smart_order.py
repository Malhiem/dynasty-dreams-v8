"""Iter 232N.31 — first_run_completed flag on League Home layout."""
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
    email = f"lh_31_{ObjectId()}@example.com"
    reg = httpx.post(
        f"{BASE}/api/auth/register",
        json={"email": email, "password": "Passw0rd!", "username": f"lh31_{str(ObjectId())[-12:]}"[:20]},
        timeout=30.0,
    )
    assert reg.status_code in (200, 201), reg.text
    tok = reg.json().get("access_token") or reg.json().get("token")
    assert tok
    return tok


def _auth(t: str) -> dict:
    return {"Authorization": f"Bearer {t}"}


def test_first_run_completed_defaults_to_false(token):
    """Brand-new user → GET returns first_run_completed: false so the
    client knows it's safe to run smart-arrange."""
    league_id = str(ObjectId())
    res = httpx.get(f"{BASE}/api/users/me/league-home-layout/{league_id}", headers=_auth(token), timeout=30.0)
    assert res.status_code == 200
    assert res.json()["first_run_completed"] is False


def test_patch_sets_first_run_completed(token):
    """PATCH with first_run_completed:true → GET reads it back true."""
    league_id = str(ObjectId())
    res = httpx.patch(
        f"{BASE}/api/users/me/league-home-layout/{league_id}",
        json={"widget_order": ["pending_trades", "matchups"], "first_run_completed": True},
        headers=_auth(token), timeout=30.0,
    )
    assert res.status_code == 200
    assert res.json()["first_run_completed"] is True

    get_res = httpx.get(f"{BASE}/api/users/me/league-home-layout/{league_id}", headers=_auth(token), timeout=30.0)
    assert get_res.json()["first_run_completed"] is True


def test_reset_via_patch_false_re_arms_smart_arrange(token):
    """Once flipped to false via PATCH, the marker sticks off so the
    client can smart-arrange again on the next visit."""
    league_id = str(ObjectId())
    # Latch it true first.
    httpx.patch(
        f"{BASE}/api/users/me/league-home-layout/{league_id}",
        json={"first_run_completed": True},
        headers=_auth(token), timeout=30.0,
    )
    # Flip it back.
    httpx.patch(
        f"{BASE}/api/users/me/league-home-layout/{league_id}",
        json={"first_run_completed": False},
        headers=_auth(token), timeout=30.0,
    )
    got = httpx.get(f"{BASE}/api/users/me/league-home-layout/{league_id}", headers=_auth(token), timeout=30.0)
    assert got.json()["first_run_completed"] is False


def test_first_run_completed_ignores_non_bool(token):
    """Malformed first_run_completed → server ignores the field, other
    updates in the same payload still land."""
    league_id = str(ObjectId())
    res = httpx.patch(
        f"{BASE}/api/users/me/league-home-layout/{league_id}",
        json={"widget_order": ["matchups"], "first_run_completed": "yes"},
        headers=_auth(token), timeout=30.0,
    )
    assert res.status_code == 200
    got = httpx.get(f"{BASE}/api/users/me/league-home-layout/{league_id}", headers=_auth(token), timeout=30.0)
    body = got.json()
    assert body["widget_order"] == ["matchups"]        # order landed
    assert body["first_run_completed"] is False         # bad flag ignored


def test_first_run_completed_scoped_per_league(token):
    """Latching first_run_completed on league A leaves league B free
    to smart-arrange."""
    league_a = str(ObjectId())
    league_b = str(ObjectId())
    httpx.patch(
        f"{BASE}/api/users/me/league-home-layout/{league_a}",
        json={"first_run_completed": True},
        headers=_auth(token), timeout=30.0,
    )
    a = httpx.get(f"{BASE}/api/users/me/league-home-layout/{league_a}", headers=_auth(token), timeout=30.0)
    b = httpx.get(f"{BASE}/api/users/me/league-home-layout/{league_b}", headers=_auth(token), timeout=30.0)
    assert a.json()["first_run_completed"] is True
    assert b.json()["first_run_completed"] is False
