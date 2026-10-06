"""Verify `PUT /leagues/{id}` works correctly after the iter-80 refactor that
moved the handler from `server.py` into `routes/leagues.py`. The endpoint URL,
auth checks, sparse-update behaviour, and audit-log diff should all be
unchanged from the caller's perspective.
"""
import os
import sys

import pytest
from httpx import AsyncClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _backend_url():
    env_path = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", ".env")
    with open(env_path) as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip()
    raise RuntimeError("REACT_APP_BACKEND_URL not found")


BASE = _backend_url()
EMAIL = os.environ.get("TEST_OWNER_EMAIL", "test-owner@e2e.dynastydreams.com")
PASSWORD = os.environ.get("TEST_OWNER_PASSWORD", "e2e-owner-password")
LID = "69e46af167999bfb85c39628"


@pytest.mark.asyncio
async def test_put_league_endpoint_still_registered():
    """A 200 from PUT /api/leagues/{id} on the seeded league proves the route
    is registered after the refactor (OpenAPI schema is disabled in this env)."""
    async with AsyncClient(base_url=BASE, timeout=15) as client:
        r = await client.post("/api/auth/login",
                              json={"email": EMAIL, "password": PASSWORD})
        token = r.json()["access_token"]
        # Empty payload is a no-op but must still 200
        r = await client.put(
            f"/api/leagues/{LID}",
            headers={"Authorization": f"Bearer {token}"},
            json={},
        )
        assert r.status_code == 200, r.text
        assert r.json().get("league_id") == LID


@pytest.mark.asyncio
async def test_put_league_sparse_update_and_diff_log_still_works():
    """End-to-end sanity: PUT a single field, GET back the canonical config,
    confirm the audit log captured the diff. Same contract as before refactor.
    """
    async with AsyncClient(base_url=BASE, timeout=20) as client:
        r = await client.post("/api/auth/login",
                              json={"email": EMAIL, "password": PASSWORD})
        token = r.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Snapshot original value to restore after the test
        before = await client.get(f"/api/leagues/{LID}", headers=headers)
        before_pct = before.json().get("trade_veto_threshold_pct")
        target = 55 if before_pct != 55 else 60

        r = await client.put(
            f"/api/leagues/{LID}",
            headers=headers,
            json={"trade_veto_threshold_pct": target},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["trade_veto_threshold_pct"] == target
        assert "changes" in body
        # Only the one provided key changed
        if before_pct != target:
            assert "trade_veto_threshold_pct" in body["changes"]
            assert body["changes"]["trade_veto_threshold_pct"]["to"] == target

        # GET round-trip
        r = await client.get(f"/api/leagues/{LID}", headers=headers)
        assert r.json()["trade_veto_threshold_pct"] == target

        # Restore
        await client.put(
            f"/api/leagues/{LID}",
            headers=headers,
            json={"trade_veto_threshold_pct": before_pct},
        )


@pytest.mark.asyncio
async def test_put_league_403_for_non_commissioner_post_refactor():
    """Non-commissioner of another league still gets 403 with the same message."""
    async with AsyncClient(base_url=BASE, timeout=15) as client:
        r = await client.post("/api/auth/login",
                              json={"email": EMAIL, "password": PASSWORD})
        token = r.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        me = (await client.get("/api/auth/me", headers=headers)).json()
        leagues = (await client.get("/api/leagues", headers=headers)).json()
        other = next(
            (
                l for l in leagues
                if l.get("commissioner_id") != me["id"]
                and me["id"] not in (l.get("co_commissioners") or [])
            ),
            None,
        )
        if not other:
            pytest.skip("no league where user isn't a commissioner")
        r = await client.put(
            f"/api/leagues/{other['id']}",
            headers=headers,
            json={"trade_veto_threshold_pct": 99},
        )
        assert r.status_code == 403, r.text
        assert "commissioner" in r.json()["detail"].lower()
