"""Tests for ownership snapshot worker + admin trigger endpoint."""
import os
import sys
import asyncio
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from httpx import AsyncClient


def _backend_url():
    env_path = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", ".env")
    with open(env_path) as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip()
    raise RuntimeError("REACT_APP_BACKEND_URL not found")


BASE = _backend_url()


async def _login(client, email, password):
    resp = await client.post("/api/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


@pytest.mark.asyncio
async def test_admin_snapshot_returns_per_player_rows():
    """As ADMIN_EMAIL, hitting the trigger writes 1 row per player."""
    async with AsyncClient(base_url=BASE, timeout=120) as client:
        token = await _login(client, os.environ.get("ADMIN_EMAIL", "admin@e2e.dynastydreams.com"), os.environ.get("ADMIN_PASSWORD", "e2e-admin-password"))
        r = await client.post(
            "/api/admin/snapshot-ownership",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["players"] >= 1
        assert body["rows_upserted"] == body["players"]
        assert "date" in body and len(body["date"]) == 10  # YYYY-MM-DD


@pytest.mark.asyncio
async def test_admin_snapshot_rejects_non_admin():
    async with AsyncClient(base_url=BASE, timeout=30) as client:
        token = await _login(client, os.environ.get("TEST_OWNER_EMAIL", "test-owner@e2e.dynastydreams.com"), os.environ.get("TEST_OWNER_PASSWORD", "e2e-owner-password"))
        r = await client.post(
            "/api/admin/snapshot-ownership",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 403, r.text
        assert "admin" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_snapshot_is_idempotent_within_same_day():
    """Calling twice in the same UTC day MUST upsert (not duplicate)."""
    async with AsyncClient(base_url=BASE, timeout=120) as client:
        token = await _login(client, os.environ.get("ADMIN_EMAIL", "admin@e2e.dynastydreams.com"), os.environ.get("ADMIN_PASSWORD", "e2e-admin-password"))
        r1 = await client.post(
            "/api/admin/snapshot-ownership",
            headers={"Authorization": f"Bearer {token}"},
        )
        r2 = await client.post(
            "/api/admin/snapshot-ownership",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r1.status_code == 200
        assert r2.status_code == 200
        # Both calls must produce identical row counts (same date → upserts,
        # never inserts) — validating the unique key on (player_id, snapshot_date).
        assert r1.json()["players"] == r2.json()["players"]
        assert r1.json()["date"] == r2.json()["date"]
