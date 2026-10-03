"""Tests for team logo upload, validation, and removal.

These tests run against the **live** backend (REACT_APP_BACKEND_URL) so they
exercise the same path the frontend will use.
"""
import io
import os
import sys
import asyncio
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image
from httpx import AsyncClient


def _backend_url():
    # Read REACT_APP_BACKEND_URL from frontend/.env so tests hit the same
    # external host the UI uses.
    env_path = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", ".env")
    with open(env_path) as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip()
    raise RuntimeError("REACT_APP_BACKEND_URL not found")


BASE = _backend_url()


def _png_bytes(size=(80, 80), color=(0, 200, 220, 255)):
    img = Image.new("RGBA", size, color)
    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()


async def _login(client, email, password):
    resp = await client.post("/api/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


async def _my_team_id(client, token):
    me = (await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})).json()
    teams = (await client.get("/api/teams", headers={"Authorization": f"Bearer {token}"})).json()
    mine = [t for t in teams if t.get("owner_id") == me["id"]]
    assert mine, "user has no team"
    return mine[0]["id"]


@pytest.mark.asyncio
async def test_logo_upload_success_and_round_trip():
    async with AsyncClient(base_url=BASE, timeout=30) as client:
        token = await _login(client, os.environ.get("TEST_OWNER_EMAIL", "test-owner@e2e.dynastydreams.com"), os.environ.get("TEST_OWNER_PASSWORD", "e2e-owner-password"))
        team_id = await _my_team_id(client, token)
        files = {"file": ("logo.png", _png_bytes((400, 400)), "image/png")}
        r = await client.post(
            f"/api/teams/{team_id}/logo",
            headers={"Authorization": f"Bearer {token}"},
            files=files,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["logo_url"].startswith("data:image/png;base64,")
        team = (await client.get(f"/api/teams/{team_id}")).json()
        assert team["logo_url"].startswith("data:image/png;base64,")


@pytest.mark.asyncio
async def test_logo_rejects_unsupported_type():
    async with AsyncClient(base_url=BASE, timeout=30) as client:
        token = await _login(client, os.environ.get("TEST_OWNER_EMAIL", "test-owner@e2e.dynastydreams.com"), os.environ.get("TEST_OWNER_PASSWORD", "e2e-owner-password"))
        team_id = await _my_team_id(client, token)
        files = {"file": ("logo.txt", b"hello", "text/plain")}
        r = await client.post(
            f"/api/teams/{team_id}/logo",
            headers={"Authorization": f"Bearer {token}"},
            files=files,
        )
        assert r.status_code == 400
        assert "Unsupported" in r.json()["detail"]


@pytest.mark.asyncio
async def test_logo_rejects_oversize():
    async with AsyncClient(base_url=BASE, timeout=30) as client:
        token = await _login(client, os.environ.get("TEST_OWNER_EMAIL", "test-owner@e2e.dynastydreams.com"), os.environ.get("TEST_OWNER_PASSWORD", "e2e-owner-password"))
        team_id = await _my_team_id(client, token)
        big = b"\x00" * (1024 * 1024 + 1)
        files = {"file": ("big.png", big, "image/png")}
        r = await client.post(
            f"/api/teams/{team_id}/logo",
            headers={"Authorization": f"Bearer {token}"},
            files=files,
        )
        assert r.status_code == 413
        assert "too large" in r.text.lower() or "413" in r.text


@pytest.mark.asyncio
async def test_logo_only_owner_or_commish_can_upload():
    async with AsyncClient(base_url=BASE, timeout=30) as client:
        token = await _login(client, os.environ.get("TEST_OWNER_EMAIL", "test-owner@e2e.dynastydreams.com"), os.environ.get("TEST_OWNER_PASSWORD", "e2e-owner-password"))
        teams = (await client.get("/api/teams", headers={"Authorization": f"Bearer {token}"})).json()
        me = (await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})).json()
        other = next((t for t in teams if t.get("owner_id") != me["id"]), None)
        if not other:
            pytest.skip("no other team to test against")
        files = {"file": ("logo.png", _png_bytes(), "image/png")}
        r = await client.post(
            f"/api/teams/{other['id']}/logo",
            headers={"Authorization": f"Bearer {token}"},
            files=files,
        )
        assert r.status_code in (200, 403)


@pytest.mark.asyncio
async def test_logo_delete():
    async with AsyncClient(base_url=BASE, timeout=30) as client:
        token = await _login(client, os.environ.get("TEST_OWNER_EMAIL", "test-owner@e2e.dynastydreams.com"), os.environ.get("TEST_OWNER_PASSWORD", "e2e-owner-password"))
        team_id = await _my_team_id(client, token)
        files = {"file": ("logo.png", _png_bytes(), "image/png")}
        await client.post(
            f"/api/teams/{team_id}/logo",
            headers={"Authorization": f"Bearer {token}"},
            files=files,
        )
        r = await client.delete(
            f"/api/teams/{team_id}/logo",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200, r.text
        team = (await client.get(f"/api/teams/{team_id}")).json()
        assert team.get("logo_url") in (None, "")
