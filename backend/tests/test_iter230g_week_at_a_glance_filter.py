"""Iter 230g — Week at a Glance must not show archived/test leagues.

Regression test for the bug where stale `TEST_*` and archived leagues
left behind by integration runs polluted the real user's dashboard.
"""
import os
import sys
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _backend_url():
    env_path = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", ".env")
    with open(env_path) as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip()
    raise RuntimeError("REACT_APP_BACKEND_URL not found")


BASE = _backend_url()


def _db_sync():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    return client[os.environ.get("DB_NAME", "test_database")]


async def _login(client, email, password):
    r = await client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.mark.asyncio
async def test_week_at_a_glance_excludes_archived_and_test_leagues():
    """Seeds an archived league + a TEST_-prefixed league owned by the
    test user, then asserts neither shows up in /week-at-a-glance.
    Cleans up after itself."""
    db = _db_sync()
    async with AsyncClient(base_url=BASE, timeout=20) as client:
        token = await _login(client, "chriszarek@gmail.com", "Chris2026!")
        user = await db.users.find_one({"email": "chriszarek@gmail.com"})
        uid = str(user["_id"])

        # Snapshot the baseline count.
        r = await client.get("/api/users/me/week-at-a-glance", headers={"Authorization": f"Bearer {token}"})
        baseline = len(r.json().get("summaries") or [])

        # Seed two new leagues + one team in each — one archived, one TEST_.
        archived_league = await db.leagues.insert_one({
            "name": "Iter230g_REGRESSION_archived",
            "season": "2025-2026",
            "status": "active",
            "archived": True,  # ← should be filtered out
            "format": "head_to_head",
            "scoring_format": "categories",
            "max_teams": 12,
            "current_teams": 1,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        test_league = await db.leagues.insert_one({
            "name": "TEST_iter230g_should_be_hidden",
            "season": "2025-2026",
            "status": "active",
            "archived": False,
            "format": "head_to_head",
            "scoring_format": "categories",
            "max_teams": 12,
            "current_teams": 1,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        real_league = await db.leagues.insert_one({
            "name": "Iter230g_real_league_keep_me",
            "season": "2025-2026",
            "status": "active",
            "archived": False,
            "format": "head_to_head",
            "scoring_format": "categories",
            "max_teams": 12,
            "current_teams": 1,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        t1 = await db.teams.insert_one({
            "name": "Iter230g_archived_team",
            "league_id": str(archived_league.inserted_id),
            "owner_id": uid,
            "roster": [],
        })
        t2 = await db.teams.insert_one({
            "name": "Iter230g_test_team",
            "league_id": str(test_league.inserted_id),
            "owner_id": uid,
            "roster": [],
        })
        t3 = await db.teams.insert_one({
            "name": "Iter230g_real_team",
            "league_id": str(real_league.inserted_id),
            "owner_id": uid,
            "roster": [],
        })

        try:
            r = await client.get("/api/users/me/week-at-a-glance", headers={"Authorization": f"Bearer {token}"})
            assert r.status_code == 200, r.text
            summaries = r.json().get("summaries") or []
            team_ids_seen = {s["team_id"] for s in summaries}

            # Archived + TEST_ teams must NOT appear.
            assert str(t1.inserted_id) not in team_ids_seen, "archived team leaked into WAG"
            assert str(t2.inserted_id) not in team_ids_seen, "TEST_ team leaked into WAG"
            # The real league's team MUST appear.
            assert str(t3.inserted_id) in team_ids_seen, "real team missing from WAG"
            # Exactly 1 new team is added vs baseline.
            assert len(summaries) == baseline + 1
        finally:
            # Clean up seeded fixtures.
            await db.teams.delete_many({"_id": {"$in": [t1.inserted_id, t2.inserted_id, t3.inserted_id]}})
            await db.leagues.delete_many({"_id": {"$in": [
                archived_league.inserted_id,
                test_league.inserted_id,
                real_league.inserted_id,
            ]}})


@pytest.mark.asyncio
async def test_week_at_a_glance_includes_co_owner_teams():
    """A co-owner of a team should also see it in their own dashboard."""
    db = _db_sync()
    async with AsyncClient(base_url=BASE, timeout=20) as client:
        token = await _login(client, "chriszarek@live.com", "Chris2026!")
        live_user = await db.users.find_one({"email": "chriszarek@live.com"})
        live_uid = str(live_user["_id"])

        baseline = len((await client.get(
            "/api/users/me/week-at-a-glance",
            headers={"Authorization": f"Bearer {token}"},
        )).json().get("summaries") or [])

        # Build a real (non-test) league + team owned by someone else,
        # with chriszarek1 as co-owner.
        primary = await db.users.find_one({"email": "chriszarek@gmail.com"})
        league = await db.leagues.insert_one({
            "name": "Iter230g_co_owner_league_keep_me",
            "season": "2025-2026",
            "status": "active",
            "archived": False,
            "format": "head_to_head",
            "scoring_format": "categories",
            "max_teams": 12,
            "current_teams": 1,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        team = await db.teams.insert_one({
            "name": "Iter230g_co_owner_team",
            "league_id": str(league.inserted_id),
            "owner_id": str(primary["_id"]),
            "co_owner_ids": [live_uid],
            "roster": [],
        })
        try:
            r = await client.get(
                "/api/users/me/week-at-a-glance",
                headers={"Authorization": f"Bearer {token}"},
            )
            summaries = r.json().get("summaries") or []
            assert any(s["team_id"] == str(team.inserted_id) for s in summaries), (
                "co-owner team should appear in WAG"
            )
            assert len(summaries) == baseline + 1
        finally:
            await db.teams.delete_one({"_id": team.inserted_id})
            await db.leagues.delete_one({"_id": league.inserted_id})
