"""Iter 230am — Server-side persistence of the user's league display
order. Locks the new `PUT /notifications/preferences/league-order`
endpoint + GET response shape."""
from __future__ import annotations

import os
import uuid

import pytest
import requests

API_URL = os.environ["REACT_APP_BACKEND_URL"]


def _register_user():
    suffix = uuid.uuid4().hex[:8]
    email = f"iter230am_{suffix}@example.com"
    requests.post(
        f"{API_URL}/api/auth/register",
        json={
            "email": email, "password": "TestPass123!",
            "username": f"iter230am_{suffix}", "name": "iter230am user",
        },
    ).raise_for_status()
    login = requests.post(
        f"{API_URL}/api/auth/login",
        json={"email": email, "password": "TestPass123!"},
    )
    login.raise_for_status()
    return login.json()["access_token"]


@pytest.mark.asyncio
async def test_get_preferences_includes_league_order_field():
    """Fresh user — GET returns `league_order: []` so the frontend can
    rely on the key existing."""
    token = _register_user()
    H = {"Authorization": f"Bearer {token}"}
    r = requests.get(f"{API_URL}/api/notifications/preferences", headers=H)
    r.raise_for_status()
    payload = r.json()
    assert "league_order" in payload
    assert payload["league_order"] == []


@pytest.mark.asyncio
async def test_put_league_order_round_trips_and_dedupes():
    """`PUT /notifications/preferences/league-order` persists the
    submitted list (de-duping while preserving order) and the next GET
    returns the same payload."""
    token = _register_user()
    H = {"Authorization": f"Bearer {token}"}
    payload = {"ordered_ids": ["L1", "L2", "L3", "L1", "L4"]}
    r = requests.put(
        f"{API_URL}/api/notifications/preferences/league-order",
        json=payload, headers=H,
    )
    r.raise_for_status()
    assert r.json()["league_order"] == ["L1", "L2", "L3", "L4"]

    r2 = requests.get(f"{API_URL}/api/notifications/preferences", headers=H)
    r2.raise_for_status()
    assert r2.json()["league_order"] == ["L1", "L2", "L3", "L4"]


@pytest.mark.asyncio
async def test_put_empty_league_order_clears_preference():
    """Submitting `ordered_ids: []` clears the saved order — consumers
    fall back to default sort."""
    token = _register_user()
    H = {"Authorization": f"Bearer {token}"}
    requests.put(
        f"{API_URL}/api/notifications/preferences/league-order",
        json={"ordered_ids": ["A", "B"]}, headers=H,
    ).raise_for_status()

    r = requests.put(
        f"{API_URL}/api/notifications/preferences/league-order",
        json={"ordered_ids": []}, headers=H,
    )
    r.raise_for_status()
    assert r.json()["league_order"] == []

    r2 = requests.get(f"{API_URL}/api/notifications/preferences", headers=H)
    r2.raise_for_status()
    assert r2.json()["league_order"] == []


@pytest.mark.asyncio
async def test_put_league_order_requires_auth():
    """Anonymous PUT is rejected with 401/403 (auth-gated like every
    other preference write)."""
    r = requests.put(
        f"{API_URL}/api/notifications/preferences/league-order",
        json={"ordered_ids": ["X"]},
    )
    assert r.status_code in (401, 403)
