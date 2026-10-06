"""Tests for /api/comparisons/compare + paywall + admin Pro toggle."""
import os
import sys
import asyncio
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


async def _player_id(client, name):
    r = await client.get(f"/api/players?search={name}&limit=1")
    return r.json()["players"][0]["_id"]


async def _user_id(client, token):
    r = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    return r.json()["id"]


async def _league_id(client, token):
    r = await client.get("/api/leagues?my_leagues=true",
                         headers={"Authorization": f"Bearer {token}"})
    return r.json()[0]["id"]


async def _reset_quota(uid):
    """Reset comparisons counter directly via DB to make tests deterministic."""
    from motor.motor_asyncio import AsyncIOMotorClient
    from bson import ObjectId
    from dotenv import load_dotenv
    load_dotenv()
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    await db.users.update_one(
        {"_id": ObjectId(uid)},
        {"$set": {"is_pro": False, "comparisons_used_this_month": 0,
                  "comparisons_period_key": None}},
    )


@pytest.mark.asyncio
async def test_pro_status_initial():
    async with AsyncClient(base_url=BASE, timeout=30) as client:
        token = await _login(client, os.environ.get("TEST_OWNER_EMAIL", "test-owner@e2e.dynastydreams.com"), os.environ.get("TEST_OWNER_PASSWORD", "e2e-owner-password"))
        uid = await _user_id(client, token)
        await _reset_quota(uid)
        r = await client.get("/api/users/me/pro-status",
                             headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        body = r.json()
        assert body["is_pro"] is False
        assert body["free_quota_per_month"] == 3
        assert body["comparisons_remaining"] == 3


@pytest.mark.asyncio
async def test_compare_unlimited_after_paywall_removed():
    """Paywall removed — a non-Pro user can compare >3 times a month now."""
    async with AsyncClient(base_url=BASE, timeout=60) as client:
        token = await _login(client, os.environ.get("TEST_OWNER_EMAIL", "test-owner@e2e.dynastydreams.com"), os.environ.get("TEST_OWNER_PASSWORD", "e2e-owner-password"))
        uid = await _user_id(client, token)
        await _reset_quota(uid)
        lid = await _league_id(client, token)
        a = await _player_id(client, "Connor McDavid")
        b = await _player_id(client, "Leon Draisaitl")
        body = {"player_a_id": a, "player_b_id": b,
                "season_a": "current", "season_b": "current",
                "league_id": lid}
        # 5 consecutive compares all succeed (previously the 4th would 402)
        for i in range(5):
            r = await client.post("/api/comparisons/compare", json=body,
                                  headers={"Authorization": f"Bearer {token}"})
            assert r.status_code == 200, f"Call #{i+1}: {r.status_code} {r.text}"


@pytest.mark.asyncio
async def test_admin_can_grant_pro_then_unlimited():
    async with AsyncClient(base_url=BASE, timeout=60) as client:
        token = await _login(client, os.environ.get("TEST_OWNER_EMAIL", "test-owner@e2e.dynastydreams.com"), os.environ.get("TEST_OWNER_PASSWORD", "e2e-owner-password"))
        admin_token = await _login(client, os.environ.get("ADMIN_EMAIL", "admin@e2e.dynastydreams.com"), os.environ.get("ADMIN_PASSWORD", "e2e-admin-password"))
        uid = await _user_id(client, token)
        await _reset_quota(uid)
        lid = await _league_id(client, token)
        a = await _player_id(client, "Connor McDavid")
        b = await _player_id(client, "Leon Draisaitl")

        # Grant Pro
        r = await client.post(
            f"/api/admin/users/{uid}/pro",
            json={"is_pro": True},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert r.status_code == 200
        assert r.json()["is_pro"] is True

        # Run 5 compares as Pro — all must succeed and remaining == None
        body = {"player_a_id": a, "player_b_id": b,
                "season_a": "current", "season_b": "current",
                "league_id": lid}
        for _ in range(5):
            r = await client.post("/api/comparisons/compare", json=body,
                                  headers={"Authorization": f"Bearer {token}"})
            assert r.status_code == 200
            assert r.json()["is_pro"] is True
            assert r.json()["comparisons_remaining"] is None

        # Revoke Pro to leave the user back to free for other tests
        await client.post(
            f"/api/admin/users/{uid}/pro",
            json={"is_pro": False},
            headers={"Authorization": f"Bearer {admin_token}"},
        )


@pytest.mark.asyncio
async def test_admin_pro_toggle_rejects_non_admin():
    async with AsyncClient(base_url=BASE, timeout=30) as client:
        token = await _login(client, os.environ.get("TEST_OWNER_EMAIL", "test-owner@e2e.dynastydreams.com"), os.environ.get("TEST_OWNER_PASSWORD", "e2e-owner-password"))
        uid = await _user_id(client, token)
        r = await client.post(
            f"/api/admin/users/{uid}/pro",
            json={"is_pro": True},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 403


@pytest.mark.asyncio
async def test_compare_returns_winner_and_diff():
    async with AsyncClient(base_url=BASE, timeout=60) as client:
        token = await _login(client, os.environ.get("TEST_OWNER_EMAIL", "test-owner@e2e.dynastydreams.com"), os.environ.get("TEST_OWNER_PASSWORD", "e2e-owner-password"))
        admin_token = await _login(client, os.environ.get("ADMIN_EMAIL", "admin@e2e.dynastydreams.com"), os.environ.get("ADMIN_PASSWORD", "e2e-admin-password"))
        uid = await _user_id(client, token)
        # Grant Pro to avoid quota burning during this test
        await client.post(f"/api/admin/users/{uid}/pro",
                          json={"is_pro": True},
                          headers={"Authorization": f"Bearer {admin_token}"})
        lid = await _league_id(client, token)
        a = await _player_id(client, "Connor McDavid")
        b = await _player_id(client, "Leon Draisaitl")
        r = await client.post(
            "/api/comparisons/compare",
            json={"player_a_id": a, "player_b_id": b,
                  "season_a": "current", "season_b": "current",
                  "league_id": lid},
            headers={"Authorization": f"Bearer {token}"},
        )
        body = r.json()
        assert "winner" in body and body["winner"] in ("a", "b", "tie")
        assert isinstance(body["fpts_diff"], (int, float))
        assert "stats" in body["player_a"]
        assert "stats" in body["player_b"]
        # Cleanup
        await client.post(f"/api/admin/users/{uid}/pro",
                          json={"is_pro": False},
                          headers={"Authorization": f"Bearer {admin_token}"})


@pytest.mark.asyncio
async def test_player_bio_enrichment_with_league():
    """`GET /players/{id}?league_id=` returns the new bio + ownership +
    fantasy_points / per-game / minors_eligible block."""
    async with AsyncClient(base_url=BASE, timeout=60) as client:
        token = await _login(client, os.environ.get("TEST_OWNER_EMAIL", "test-owner@e2e.dynastydreams.com"), os.environ.get("TEST_OWNER_PASSWORD", "e2e-owner-password"))
        lid = await _league_id(client, token)
        pid = await _player_id(client, "Connor McDavid")
        r = await client.get(f"/api/players/{pid}?league_id={lid}",
                             headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        body = r.json()
        # Bio
        assert body["height_inches"] >= 60
        assert body["weight_pounds"] >= 100
        assert body["birth_date"]
        assert body["birth_country"]
        assert body["nhl_seasons"] >= 5
        # Draft
        assert body["draft_year"] == 2015
        assert body["draft_round"] == 1
        assert body["draft_overall"] == 1
        assert body["draft_team_abbr"] == "EDM"
        # League-scoped
        assert body["fantasy_points"] is not None
        assert body["fantasy_points_per_game"] is not None
        assert body["eligible_positions"] == ["C"]
        assert "minors_eligible" in body
        assert "minors_criteria" in body
