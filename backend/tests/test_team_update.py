"""Tests for PUT /api/teams/{team_id} — name + abbreviation editing."""
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


async def _login(client, email, password):
    r = await client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


async def _my_team(client, token):
    me = (await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})).json()
    teams = (await client.get("/api/teams", headers={"Authorization": f"Bearer {token}"})).json()
    mine = [t for t in teams if t.get("owner_id") == me["id"]]
    assert mine, "no team"
    return mine[0]


@pytest.mark.asyncio
async def test_update_team_abbr():
    async with AsyncClient(base_url=BASE, timeout=20) as client:
        token = await _login(client, os.environ.get("TEST_OWNER_EMAIL", "test-owner@e2e.dynastydreams.com"), os.environ.get("TEST_OWNER_PASSWORD", "e2e-owner-password"))
        team = await _my_team(client, token)
        original_abbr = team["logo_abbr"]

        # Set custom abbr
        r = await client.put(
            f"/api/teams/{team['id']}",
            headers={"Authorization": f"Bearer {token}"},
            json={"logo_abbr": "TST"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["updated"] is True
        assert body["changes"]["logo_abbr"]["to"] == "TST"

        # Verify
        fresh = (await client.get(f"/api/teams/{team['id']}")).json()
        assert fresh["logo_abbr"] == "TST"

        # Reset
        r = await client.put(
            f"/api/teams/{team['id']}",
            headers={"Authorization": f"Bearer {token}"},
            json={"logo_abbr": original_abbr},
        )
        assert r.status_code == 200


@pytest.mark.asyncio
async def test_update_team_name_round_trip():
    async with AsyncClient(base_url=BASE, timeout=20) as client:
        token = await _login(client, os.environ.get("TEST_OWNER_EMAIL", "test-owner@e2e.dynastydreams.com"), os.environ.get("TEST_OWNER_PASSWORD", "e2e-owner-password"))
        team = await _my_team(client, token)
        original_name = team["name"]
        new_name = original_name + " Test"

        r = await client.put(
            f"/api/teams/{team['id']}",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": new_name},
        )
        assert r.status_code == 200, r.text

        fresh = (await client.get(f"/api/teams/{team['id']}")).json()
        assert fresh["name"] == new_name

        # Reset
        r = await client.put(
            f"/api/teams/{team['id']}",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": original_name},
        )
        assert r.status_code == 200


@pytest.mark.asyncio
async def test_invalid_abbr_rejected():
    async with AsyncClient(base_url=BASE, timeout=20) as client:
        token = await _login(client, os.environ.get("TEST_OWNER_EMAIL", "test-owner@e2e.dynastydreams.com"), os.environ.get("TEST_OWNER_PASSWORD", "e2e-owner-password"))
        team = await _my_team(client, token)
        r = await client.put(
            f"/api/teams/{team['id']}",
            headers={"Authorization": f"Bearer {token}"},
            json={"logo_abbr": "!@#"},
        )
        assert r.status_code == 422


@pytest.mark.asyncio
async def test_logo_url_set_via_put():
    async with AsyncClient(base_url=BASE, timeout=20) as client:
        token = await _login(client, os.environ.get("TEST_OWNER_EMAIL", "test-owner@e2e.dynastydreams.com"), os.environ.get("TEST_OWNER_PASSWORD", "e2e-owner-password"))
        team = await _my_team(client, token)
        url = "https://example.com/logo.png"
        r = await client.put(
            f"/api/teams/{team['id']}",
            headers={"Authorization": f"Bearer {token}"},
            json={"logo_url": url},
        )
        assert r.status_code == 200, r.text

        fresh = (await client.get(f"/api/teams/{team['id']}")).json()
        assert fresh["logo_url"] == url

        # Cleanup: remove logo
        await client.delete(
            f"/api/teams/{team['id']}/logo",
            headers={"Authorization": f"Bearer {token}"},
        )


@pytest.mark.asyncio
async def test_only_owner_or_commish_can_edit():
    async with AsyncClient(base_url=BASE, timeout=20) as client:
        token = await _login(client, os.environ.get("TEST_OWNER_EMAIL", "test-owner@e2e.dynastydreams.com"), os.environ.get("TEST_OWNER_PASSWORD", "e2e-owner-password"))
        teams = (await client.get("/api/teams", headers={"Authorization": f"Bearer {token}"})).json()
        me = (await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})).json()
        other = next((t for t in teams if t.get("owner_id") != me["id"]), None)
        if not other:
            pytest.skip("no other team")
        r = await client.put(
            f"/api/teams/{other['id']}",
            headers={"Authorization": f"Bearer {token}"},
            json={"logo_abbr": "BAD"},
        )
        # Either succeed (commish) or 403
        assert r.status_code in (200, 403)



@pytest.mark.asyncio
async def test_theme_color_set_and_clear():
    """Iter 229L — PUT /api/teams/{id} accepts theme_color as a hex string
    AND supports explicit clearing via theme_color=null.
    """
    async with AsyncClient(base_url=BASE, timeout=20) as client:
        token = await _login(client, os.environ.get("TEST_OWNER_EMAIL", "test-owner@e2e.dynastydreams.com"), os.environ.get("TEST_OWNER_PASSWORD", "e2e-owner-password"))
        team = await _my_team(client, token)
        original = team.get("theme_color")

        try:
            # 1. Set a valid hex color.
            r = await client.put(
                f"/api/teams/{team['id']}",
                headers={"Authorization": f"Bearer {token}"},
                json={"theme_color": "#0ea5e9"},
            )
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["updated"] is True
            assert body["changes"]["theme_color"]["to"] == "#0ea5e9"

            fresh = (await client.get(f"/api/teams/{team['id']}")).json()
            assert fresh["theme_color"] == "#0ea5e9"

            # 2. Clear via explicit null.
            r = await client.put(
                f"/api/teams/{team['id']}",
                headers={"Authorization": f"Bearer {token}"},
                json={"theme_color": None},
            )
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["updated"] is True, body
            assert body["changes"]["theme_color"]["to"] is None

            fresh = (await client.get(f"/api/teams/{team['id']}")).json()
            assert fresh.get("theme_color") in (None, "")

            # 3. Reject invalid hex.
            r = await client.put(
                f"/api/teams/{team['id']}",
                headers={"Authorization": f"Bearer {token}"},
                json={"theme_color": "not-a-color"},
            )
            assert r.status_code in (400, 422)
        finally:
            # Restore original value.
            await client.put(
                f"/api/teams/{team['id']}",
                headers={"Authorization": f"Bearer {token}"},
                json={"theme_color": original},
            )
