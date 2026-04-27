"""Tests for /api/trade-analyzer/* + paywall + projections endpoints."""
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


async def _reset_analyzer_quota(uid, is_pro=False):
    from motor.motor_asyncio import AsyncIOMotorClient
    from bson import ObjectId
    from dotenv import load_dotenv
    load_dotenv()
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    await db.users.update_one(
        {"_id": ObjectId(uid)},
        {"$set": {"is_pro": is_pro, "analyses_used_this_year": 0,
                  "analyses_period_key": None}},
    )


@pytest.mark.asyncio
async def test_analyzer_status_initial():
    async with AsyncClient(base_url=BASE, timeout=30) as client:
        token = await _login(client, "chriszarek@gmail.com", "Chris2026!")
        uid = await _user_id(client, token)
        await _reset_analyzer_quota(uid)
        r = await client.get("/api/users/me/analyzer-status",
                             headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["is_pro"] is False
        assert body["free_analyses_per_year"] == 1
        assert body["analyses_remaining"] == 1


@pytest.mark.asyncio
async def test_value_player_unmetered():
    """Single-player valuation must NOT burn quota and must include all
    projection fields."""
    async with AsyncClient(base_url=BASE, timeout=30) as client:
        token = await _login(client, "chriszarek@gmail.com", "Chris2026!")
        uid = await _user_id(client, token)
        await _reset_analyzer_quota(uid)
        lid = await _league_id(client, token)
        pid = await _player_id(client, "Connor McDavid")
        for _ in range(3):
            r = await client.post(
                "/api/trade-analyzer/value-player",
                json={"player_id": pid, "league_id": lid},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["player_id"] == pid
            assert body["blended_fpg"] >= 0
            assert body["projected_ros_fpts"] >= 0
            assert body["games_remaining"] >= 0
            assert body["scarcity_mult"] > 0
            assert body["value"] >= 0
        # Confirm quota untouched
        r = await client.get("/api/users/me/analyzer-status",
                             headers={"Authorization": f"Bearer {token}"})
        assert r.json()["analyses_remaining"] == 1


@pytest.mark.asyncio
async def test_value_pick_curve():
    async with AsyncClient(base_url=BASE, timeout=30) as client:
        token = await _login(client, "chriszarek@gmail.com", "Chris2026!")
        # R1 must outvalue R5 must outvalue R10
        rounds = []
        for r_ in [1, 5, 10]:
            r = await client.post(
                "/api/trade-analyzer/value-pick",
                json={"round": r_, "year": 2027},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert r.status_code == 200, r.text
            rounds.append(r.json()["value"])
        assert rounds[0] > rounds[1] > rounds[2]
        # Slot adjust: 1.01 > 1.12
        r1 = await client.post(
            "/api/trade-analyzer/value-pick",
            json={"round": 1, "year": 2027, "slot": 1, "teams_in_round": 12},
            headers={"Authorization": f"Bearer {token}"},
        )
        r12 = await client.post(
            "/api/trade-analyzer/value-pick",
            json={"round": 1, "year": 2027, "slot": 12, "teams_in_round": 12},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r1.json()["value"] > r12.json()["value"]


@pytest.mark.asyncio
async def test_player_projections_endpoint():
    async with AsyncClient(base_url=BASE, timeout=30) as client:
        token = await _login(client, "chriszarek@gmail.com", "Chris2026!")
        lid = await _league_id(client, token)
        pid = await _player_id(client, "Connor McDavid")
        r = await client.get(
            f"/api/players/{pid}/projections?league_id={lid}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["player_id"] == pid
        assert body["projected_ros_fpts"] >= 0
        assert body["projected_week_fpts"] >= 0
        assert body["games_per_week_assumed"] == 3.5
        # ROS should generally be >> weekly when many games remain
        if body["games_remaining"] > 5:
            assert body["projected_ros_fpts"] >= body["projected_week_fpts"]


@pytest.mark.asyncio
async def test_analyze_paywall_after_first_analysis():
    """Free tier: 1 analysis / year. Second call returns 402 upgrade_required."""
    async with AsyncClient(base_url=BASE, timeout=60) as client:
        token = await _login(client, "chriszarek@gmail.com", "Chris2026!")
        uid = await _user_id(client, token)
        await _reset_analyzer_quota(uid, is_pro=False)
        lid = await _league_id(client, token)
        a = await _player_id(client, "Connor McDavid")
        b = await _player_id(client, "Leon Draisaitl")
        body = {
            "league_id": lid,
            "side_a": {"players": [a], "picks": [], "faab": 0},
            "side_b": {"players": [b], "picks": [], "faab": 0},
        }

        # 1st call succeeds
        r1 = await client.post(
            "/api/trade-analyzer/analyze", json=body,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r1.status_code == 200, r1.text
        result = r1.json()
        assert result["winner"] in ("a", "b", "tie")
        assert "fairness_pct" in result
        assert "verdict" in result
        assert result["analyses_remaining"] == 0

        # 2nd call must 402
        r2 = await client.post(
            "/api/trade-analyzer/analyze", json=body,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r2.status_code == 402
        assert r2.json()["detail"]["code"] == "upgrade_required"


@pytest.mark.asyncio
async def test_analyze_pro_unlimited_with_picks_and_faab():
    """Pro user can run unlimited analyses; result includes picks + FAAB."""
    async with AsyncClient(base_url=BASE, timeout=60) as client:
        token = await _login(client, "chriszarek@gmail.com", "Chris2026!")
        admin_token = await _login(client, "admin@dynastydreams.com", "Admin123!")
        uid = await _user_id(client, token)
        await _reset_analyzer_quota(uid, is_pro=False)
        lid = await _league_id(client, token)
        a = await _player_id(client, "Connor McDavid")
        b = await _player_id(client, "Leon Draisaitl")

        # Grant Pro
        await client.post(
            f"/api/admin/users/{uid}/pro",
            json={"is_pro": True},
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        body = {
            "league_id": lid,
            "side_a": {
                "players": [a], "picks": [{"round": 1, "year": 2027}],
                "faab": 50,
                "salary_retentions": [{"player_id": a, "amount": 1_000_000}],
            },
            "side_b": {
                "players": [b], "picks": [{"round": 3, "year": 2027}, {"round": 5, "year": 2028}],
                "faab": 0,
            },
        }
        for _ in range(3):
            r = await client.post(
                "/api/trade-analyzer/analyze", json=body,
                headers={"Authorization": f"Bearer {token}"},
            )
            assert r.status_code == 200, r.text
            res = r.json()
            assert res["is_pro"] is True
            assert res["analyses_remaining"] is None
            # Side A must have picks/faab/retention populated
            assert len(res["side_a"]["picks"]) == 1
            assert res["side_a"]["faab"] == 50
            assert res["side_a"]["faab_value"] > 0
            assert res["side_a"]["retention_cost"] > 0
            assert len(res["side_b"]["picks"]) == 2
            # Per-pick value: R1 > R3 > R5
            picks_a = [p["value"] for p in res["side_a"]["picks"]]
            picks_b = [p["value"] for p in res["side_b"]["picks"]]
            assert picks_a[0] > picks_b[0] > picks_b[1]

        # Cleanup: revoke Pro
        await client.post(
            f"/api/admin/users/{uid}/pro",
            json={"is_pro": False},
            headers={"Authorization": f"Bearer {admin_token}"},
        )


@pytest.mark.asyncio
async def test_analyze_rejects_empty_side():
    async with AsyncClient(base_url=BASE, timeout=30) as client:
        token = await _login(client, "chriszarek@gmail.com", "Chris2026!")
        admin_token = await _login(client, "admin@dynastydreams.com", "Admin123!")
        uid = await _user_id(client, token)
        # Pro to bypass quota for this validation test
        await client.post(
            f"/api/admin/users/{uid}/pro",
            json={"is_pro": True},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        lid = await _league_id(client, token)
        r = await client.post(
            "/api/trade-analyzer/analyze",
            json={"league_id": lid,
                  "side_a": {"players": [], "picks": [], "faab": 0},
                  "side_b": {"players": [], "picks": [], "faab": 0}},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 400
        await client.post(
            f"/api/admin/users/{uid}/pro",
            json={"is_pro": False},
            headers={"Authorization": f"Bearer {admin_token}"},
        )


@pytest.mark.asyncio
async def test_matchup_side_rail_endpoint_shape():
    """The new /leagues/{id}/matchup-side-rail returns enriched matchups
    with per-side top_contributors + projection fields."""
    async with AsyncClient(base_url=BASE, timeout=30) as client:
        token = await _login(client, "chriszarek@gmail.com", "Chris2026!")
        lid = await _league_id(client, token)
        r = await client.get(
            f"/api/leagues/{lid}/matchup-side-rail",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["league_id"] == lid
        assert "matchups" in body
        for m in body["matchups"][:3]:
            for side_key in ("away", "home"):
                side = m[side_key]
                assert "top_contributors" in side
                assert "current_fpts" in side
                assert "projected_final" in side
                assert "projected_delta" in side
                assert "games_remaining" in side
                assert isinstance(side["top_contributors"], list)
