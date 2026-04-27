"""Tests for the Pro paywall on /api/waivers/suggest (smart drop suggestion).

Non-Pro users → 402 with detail.code = "upgrade_required".
Pro users → 200 with suggestions list.
"""
import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from httpx import AsyncClient


def _backend_url():
    env = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", ".env")
    with open(env) as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip()
    raise RuntimeError("REACT_APP_BACKEND_URL not found")


BASE = _backend_url()


async def _login(client, email, password):
    r = await client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


async def _user_id(client, token):
    r = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    return r.json()["id"]


async def _league_id(client, token):
    r = await client.get("/api/leagues?my_leagues=true",
                         headers={"Authorization": f"Bearer {token}"})
    return r.json()[0]["id"]


async def _set_pro(client, admin_token, user_id, is_pro):
    return await client.post(
        f"/api/admin/users/{user_id}/pro",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"is_pro": is_pro},
    )


@pytest.mark.asyncio
async def test_smart_drop_suggest_paywalled_for_non_pro():
    async with AsyncClient(base_url=BASE, timeout=30) as client:
        token = await _login(client, "chriszarek@gmail.com", "Chris2026!")
        admin = await _login(client, "admin@dynastydreams.com", "Admin123!")
        uid = await _user_id(client, token)
        await _set_pro(client, admin, uid, False)
        league = await _league_id(client, token)

        r = await client.get(
            f"/api/waivers/suggest?league_id={league}&position=C&limit=1",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 402, r.text
        body = r.json()
        assert body["detail"]["code"] == "upgrade_required"
        assert body["detail"]["feature"] == "smart_drop_suggest"


@pytest.mark.asyncio
async def test_smart_drop_suggest_works_for_pro():
    async with AsyncClient(base_url=BASE, timeout=30) as client:
        token = await _login(client, "chriszarek@gmail.com", "Chris2026!")
        admin = await _login(client, "admin@dynastydreams.com", "Admin123!")
        uid = await _user_id(client, token)
        await _set_pro(client, admin, uid, True)
        try:
            league = await _league_id(client, token)
            r = await client.get(
                f"/api/waivers/suggest?league_id={league}&position=C&limit=2",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["league_id"] == league
            assert isinstance(body["suggestions"], list)
            assert len(body["suggestions"]) >= 1
            # suggestions should be sorted desc by fantasy_points
            fpts = [s["fantasy_points"] for s in body["suggestions"]]
            assert fpts == sorted(fpts, reverse=True)
        finally:
            await _set_pro(client, admin, uid, False)


@pytest.mark.asyncio
async def test_smart_drop_suggest_requires_auth():
    async with AsyncClient(base_url=BASE, timeout=30) as client:
        r = await client.get(
            "/api/waivers/suggest?league_id=anything&position=C&limit=1"
        )
        assert r.status_code in (401, 403)
