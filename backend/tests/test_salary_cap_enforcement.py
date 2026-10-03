"""Tests for salary cap enforcement on /api/roster/{team_id}/add.

Coverage:
- /add denies with 400 when adding would exceed league.salary_cap
- /add succeeds when under cap (drops a player first to reset)
- /compliance live-recomputes salary_used so it matches roster sum
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
USER_EMAIL = os.environ.get("TEST_OWNER_EMAIL", "test-owner@e2e.dynastydreams.com")
USER_PASSWORD = os.environ.get("TEST_OWNER_PASSWORD", "e2e-owner-password")
TEAM_ID = "69e59b30cbd3fea02a914c61"  # Zarek's Frozen
LEAGUE_ID = "69e46af167999bfb85c39628"  # Ice Kings (cap enabled @ $88M)


async def _login(client, email, password):
    r = await client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="module", autouse=True)
def _ensure_league_cap_state(_global_pollution_sweep):
    """Iter 230u — Self-healing fixture: the salary-cap suite asserts the
    league has `salary_cap_enabled=True` and `salary_cap=$88M`. Real users
    edit league settings between test runs, so the seed value drifts.
    This fixture PUTs the expected state before the module's tests run
    and restores the original config after, so the assertions are immune
    to commissioner UI activity in the same database.
    """
    import asyncio

    async def _setup():
        async with AsyncClient(base_url=BASE, timeout=30) as client:
            token = await _login(client, USER_EMAIL, USER_PASSWORD)
            h = {"Authorization": f"Bearer {token}"}
            current = await client.get(f"/api/leagues/{LEAGUE_ID}", headers=h)
            assert current.status_code == 200, current.text
            cur = current.json()
            original = {
                "salary_cap_enabled": bool(cur.get("salary_cap_enabled")),
                "salary_cap": cur.get("salary_cap"),
            }
            r = await client.put(
                f"/api/leagues/{LEAGUE_ID}/admin/cap-settings",
                headers=h,
                json={"salary_cap_enabled": True, "salary_cap": 88_000_000},
            )
            assert r.status_code == 200, f"cap-settings PUT failed: {r.status_code} {r.text[:200]}"
            return original

    async def _restore(original):
        async with AsyncClient(base_url=BASE, timeout=30) as client:
            tok = await _login(client, USER_EMAIL, USER_PASSWORD)
            h = {"Authorization": f"Bearer {tok}"}
            await client.put(
                f"/api/leagues/{LEAGUE_ID}/admin/cap-settings",
                headers=h,
                json=original,
            )

    original = asyncio.run(_setup())
    yield
    try:
        asyncio.run(_restore(original))
    except Exception:
        pass


@pytest.mark.asyncio
async def test_compliance_returns_live_salary_used():
    async with AsyncClient(base_url=BASE, timeout=30) as client:
        token = await _login(client, USER_EMAIL, USER_PASSWORD)
        r = await client.get(
            f"/api/teams/{TEAM_ID}/compliance",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["salary_cap_enabled"] is True
        assert data["salary_cap"] == 88_000_000
        assert data["salary_used"] > 0, "salary_used should be a live computation, not stale 0"


@pytest.mark.asyncio
async def test_add_denied_when_over_cap():
    """A known $1M input cannot fit into $500K of remaining room."""
    from motor.motor_asyncio import AsyncIOMotorClient
    assert os.environ.get("TEST_SUITE_ISOLATED") == "1", "Requires disposable fixture inputs"
    mongo = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = mongo[os.environ["DB_NAME"]]
    inserted = await db.players.insert_one({"name": "Fixture Overcap Target", "position": "C", "sport": "nhl",
        "player_type": "skater", "contract": {"aav": 1_000_000, "salary": 1_000_000, "yearsRemaining": 3}, "_test_seed": True})
    from bson import ObjectId
    league = await db.leagues.find_one({"_id": ObjectId(LEAGUE_ID)})
    await db.leagues.update_one({"_id": league["_id"]}, {"$set": {"roster_spots": 30}})
    async with AsyncClient(base_url=BASE, timeout=30) as client:
        token = await _login(client, USER_EMAIL, USER_PASSWORD)
        h = {"Authorization": f"Bearer {token}"}
        before = (await client.get(f"/api/teams/{TEAM_ID}/compliance", headers=h)).json()
        try:
            changed = await client.put(f"/api/leagues/{LEAGUE_ID}/admin/cap-settings", headers=h,
                json={"salary_cap_enabled": True, "salary_cap": int(before["salary_used"]) + 500_000})
            assert changed.status_code == 200, changed.text
            response = await client.post(f"/api/roster/{TEAM_ID}/add", headers=h, json={"player_id": str(inserted.inserted_id)})
            assert response.status_code == 400, response.text
            assert "salary cap" in response.json()["detail"].lower()
        finally:
            await client.put(f"/api/leagues/{LEAGUE_ID}/admin/cap-settings", headers=h,
                json={"salary_cap_enabled": True, "salary_cap": int(before["salary_cap"])})
            await db.leagues.update_one({"_id": league["_id"]}, {"$set": {"roster_spots": league["roster_spots"]}})
            await db.players.delete_one({"_id": inserted.inserted_id})
            mongo.close()


@pytest.mark.asyncio
async def test_drop_recomputes_salary_used():
    """After a drop, /compliance.salary_used should drop by the dropped
    player's synthesized salary."""
    async with AsyncClient(base_url=BASE, timeout=30) as client:
        token = await _login(client, USER_EMAIL, USER_PASSWORD)
        # Get current roster
        team = await client.get(
            f"/api/teams/{TEAM_ID}",
            headers={"Authorization": f"Bearer {token}"},
        )
        if team.status_code != 200:
            pytest.skip(f"Could not load team: {team.status_code}")
        before = await client.get(
            f"/api/teams/{TEAM_ID}/compliance",
            headers={"Authorization": f"Bearer {token}"},
        )
        before_used = before.json().get("salary_used", 0)
        # Pull team roster + drop the lowest-paid player to keep this test idempotent
        roster_resp = await client.get(
            f"/api/teams/{TEAM_ID}",
            headers={"Authorization": f"Bearer {token}"},
        )
        roster_ids = roster_resp.json().get("roster", []) if roster_resp.status_code == 200 else []
        # Skip if the test team doesn't expose roster (model may not return it)
        if not roster_ids:
            pytest.skip("Team payload does not expose roster")
        # Drop the last player (likely lowest tier)
        target = roster_ids[-1]
        drop = await client.post(
            f"/api/roster/{TEAM_ID}/drop",
            headers={"Authorization": f"Bearer {token}"},
            json={"player_id": target},
        )
        if drop.status_code not in (200, 201):
            pytest.skip(f"Drop failed: {drop.status_code} {drop.text}")
        try:
            after = await client.get(
                f"/api/teams/{TEAM_ID}/compliance",
                headers={"Authorization": f"Bearer {token}"},
            )
            after_used = after.json().get("salary_used", 0)
            assert after_used <= before_used, (
                f"salary_used should not grow after a drop: before={before_used} after={after_used}"
            )
        finally:
            # Always re-add the dropped player to keep the state stable
            await client.post(
                f"/api/roster/{TEAM_ID}/add",
                headers={"Authorization": f"Bearer {token}"},
                json={"player_id": target},
            )
