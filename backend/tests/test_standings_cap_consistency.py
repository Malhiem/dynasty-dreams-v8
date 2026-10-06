"""Tests for standings + salary cap consistency.

- /standings returns last_5 W/L/T sequence (real, not synthesized counts) and
  salary_cap_remaining + salary_used + salary_cap when cap is enabled.
- /salary-cap/{league} cap_used MUST match /teams/{id}/compliance.salary_used.
- /roster/{id}/detail per-player salary sum MUST match the same.
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
TEAM_ID = "69e59b30cbd3fea02a914c61"
LEAGUE_ID = "69e46af167999bfb85c39628"


@pytest.fixture(scope="module", autouse=True)
def configure_cap(_global_pollution_sweep):
    from pymongo import MongoClient
    from bson import ObjectId
    assert os.environ.get("TEST_SUITE_ISOLATED") == "1"
    with MongoClient(os.environ["MONGO_URL"]) as mongo:
        league = mongo[os.environ["DB_NAME"]].leagues
        previous = league.find_one({"_id": ObjectId(LEAGUE_ID)})
        league.update_one({"_id": ObjectId(LEAGUE_ID)}, {"$set": {"salary_cap_enabled": True, "salary_cap": 88_000_000}})
        yield
        league.update_one({"_id": ObjectId(LEAGUE_ID)}, {"$set": {"salary_cap_enabled": previous.get("salary_cap_enabled", False), "salary_cap": previous.get("salary_cap", 88_000_000)}})


async def _login(client, email, password):
    r = await client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.mark.asyncio
async def test_standings_includes_cap_remaining_and_last_5():
    async with AsyncClient(base_url=BASE, timeout=30) as client:
        await _login(client, USER_EMAIL, USER_PASSWORD)
        r = await client.get(f"/api/leagues/{LEAGUE_ID}/standings")
        assert r.status_code == 200, r.text
        payload = r.json()
        data = payload["standings"] if isinstance(payload, dict) else payload
        assert isinstance(data, list)
        assert len(data) > 0
        for row in data:
            assert "salary_cap_remaining" in row
            assert "salary_used" in row
            assert "salary_cap" in row
            assert "last_5" in row
            assert isinstance(row["last_5"], list)
            assert all(s in ("W", "L", "T") for s in row["last_5"])
            # Cap math sanity (cap enabled on Ice Kings)
            assert row["salary_cap_enabled"] is True
            assert row["salary_cap"] == 88_000_000
            assert row["salary_cap_remaining"] == round(row["salary_cap"] - row["salary_used"], 2)


@pytest.mark.asyncio
async def test_cap_consistency_across_endpoints():
    """compliance.salary_used == /salary-cap/{league_id} cap_used == sum of /roster/{id}/detail player.contract.salary."""
    async with AsyncClient(base_url=BASE, timeout=30) as client:
        token = await _login(client, USER_EMAIL, USER_PASSWORD)
        h = {"Authorization": f"Bearer {token}"}

        # 1. Compliance
        compliance = await client.get(f"/api/teams/{TEAM_ID}/compliance", headers=h)
        compliance_used = compliance.json()["salary_used"]

        # 2. Salary-cap overview
        overview = await client.get(f"/api/salary-cap/{LEAGUE_ID}", headers=h)
        team_row = next((t for t in overview.json()["teams"] if t["team_id"] == TEAM_ID), None)
        assert team_row is not None
        overview_used = team_row["cap_used"]

        # 3. Roster detail per-player sum
        detail = await client.get(f"/api/roster/{TEAM_ID}/detail", headers=h)
        detail_used = sum(
            ((p.get("contract") or {}).get("salary") or 0)
            for p in detail.json().get("players", [])
        )

        # All three should agree within $1 (rounding)
        assert abs(compliance_used - overview_used) < 1, (
            f"compliance ${compliance_used:,.2f} != overview ${overview_used:,.2f}"
        )
        assert abs(compliance_used - detail_used) < 1, (
            f"compliance ${compliance_used:,.2f} != detail sum ${detail_used:,.2f}"
        )


@pytest.mark.asyncio
async def test_compliance_uses_league_cap_value():
    """compliance.salary_cap mirrors league.salary_cap (set by League Administration)."""
    async with AsyncClient(base_url=BASE, timeout=30) as client:
        token = await _login(client, USER_EMAIL, USER_PASSWORD)
        h = {"Authorization": f"Bearer {token}"}
        compliance = await client.get(f"/api/teams/{TEAM_ID}/compliance", headers=h)
        cap = compliance.json()["salary_cap"]
        assert cap == 88_000_000  # Set by admin via the script in iteration 56

        # /salary-cap also returns league-level cap
        overview = await client.get(f"/api/salary-cap/{LEAGUE_ID}", headers=h)
        assert overview.json()["salary_cap"] == cap
