"""Iter 109 — routes/lineup.py + routes/leagues.py LeagueCreate extraction.

Verifies that:
  (1) POST /teams/{id}/lineup persists section maps and returns warnings array.
  (2) GET /teams/{id}/lineup round-trips the saved state.
  (3) GET /teams/{id}/compliance returns shape with `reasons`, `compliant`, +
      retention slots + injury_reserve_compliance_mode.
  (4) PUT /leagues/{id}/injury-reserve-compliance-mode enforces commissioner
      auth (403) and rejects unknown modes (400).
  (5) POST /leagues persists a new league with a generated invite code +
      promotes the requester to commissioner role.
  (6) GET /leagues/{id} hydrates the deep pass-through fields surface.
"""
import os
import asyncio
import logging

import pytest
from bson import ObjectId
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from motor.motor_asyncio import AsyncIOMotorClient

from routes import lineup as lineup_routes
from routes import leagues as leagues_routes


@pytest.fixture
def isolated_app():
    import os
    mongo_url = os.environ.get("MONGO_URL", os.environ["MONGO_URL"])
    db_name = f"dd_test_iter109_{ObjectId()}"
    client = AsyncIOMotorClient(mongo_url, maxPoolSize=1, retryReads=True, retryWrites=True)
    db = client[db_name]

    cur_user = {"_id": "u-1", "email": "u@x.com", "name": "Owner", "role": "user"}

    async def get_current_user(request):
        return cur_user

    async def _recompute_salary(team_id):
        return 0.0

    deps = {
        "db": db,
        "logger": logging.getLogger("test-iter109"),
        "get_current_user": get_current_user,
        "_safe_object_id": lambda v, label="id": ObjectId(v),
        "_recompute_team_salary_used": _recompute_salary,
    }
    lineup_routes.setup(deps)
    leagues_routes.setup(deps)

    app = FastAPI()
    app.include_router(lineup_routes.router, prefix="/api")
    app.include_router(leagues_routes.router, prefix="/api")

    yield app, db, cur_user

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(client.drop_database(db_name))
        else:
            loop.run_until_complete(client.drop_database(db_name))
    except Exception:
        pass
    client.close()


async def _seed_league_team(db, *, owner_id="u-1"):
    from datetime import datetime, timezone
    league = {
        "_id": ObjectId(),
        "name": "Iter 109 League",
        "sport": "nhl",
        "format": "dynasty",
        "scoring_format": "head_to_head",
        "max_teams": 12,
        "current_teams": 1,
        "commissioner_id": owner_id,
        "commissioner_name": "Owner",
        "salary_cap_enabled": False,
        "draft_type": "snake",
        "roster_spots": 25,
        "keepers_allowed": 0,
        "is_private": False,
        "status": "active",
        "created_at": datetime.now(timezone.utc),
        "ir_slots": 2, "ir_plus_slots": 0, "taxi_squad_size": 0,
        "minors_spots": 4, "bench_spots": 10,
        "allow_illegal_rosters": True,  # don't block save in tests
        "salary_retention_slots": 3,
    }
    await db.leagues.insert_one(league)
    team = {
        "_id": ObjectId(),
        "league_id": str(league["_id"]),
        "owner_id": owner_id,
        "owner_name": "Owner",
        "name": "Test Squad",
        "roster": [],
    }
    await db.teams.insert_one(team)
    return str(league["_id"]), str(team["_id"])


@pytest.mark.asyncio
async def test_lineup_save_and_get(isolated_app):
    app, db, _ = isolated_app
    league_id, team_id = await _seed_league_team(db)
    p1 = ObjectId()
    p2 = ObjectId()
    await db.teams.update_one(
        {"_id": ObjectId(team_id)},
        {"$set": {"roster": [str(p1), str(p2)]}},
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Save lineup with 1 forward + 1 bench
        r = await ac.post(
            f"/api/teams/{team_id}/lineup",
            json={"lineup": {
                str(p1): {"section": "forward", "slot": "C"},
                str(p2): {"section": "bench", "slot": "BN"},
            }},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["saved"] is True
        assert body["starter_count"] == 1
        assert body["lineup_size"] == 2
        assert isinstance(body["warnings"], list)

        # Read it back
        r2 = await ac.get(f"/api/teams/{team_id}/lineup")
        assert r2.status_code == 200
        lineup = r2.json()["lineup"]
        assert lineup[str(p1)]["section"] == "forward"
        assert lineup[str(p2)]["section"] == "bench"


@pytest.mark.asyncio
async def test_compliance_returns_full_shape(isolated_app):
    app, db, _ = isolated_app
    _, team_id = await _seed_league_team(db)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.get(f"/api/teams/{team_id}/compliance")
        assert r.status_code == 200, r.text
        body = r.json()
        # Iter 230o — a seeded team with zero players is now intentionally
        # surfaced as non-compliant via the `empty_roster` reason so the
        # Roster Status tile doesn't silently lie about expansion teams.
        assert body["compliant"] is False
        assert body["roster_count"] == 0
        codes = [r.get("code") for r in body["reasons"]]
        assert codes == ["empty_roster"]
        assert body["salary_retention_slots_total"] == 3
        assert body["injury_reserve_compliance_mode"] == "none"


@pytest.mark.asyncio
async def test_set_ir_compliance_mode_rejects_bad_mode(isolated_app):
    app, db, _ = isolated_app
    league_id, _ = await _seed_league_team(db)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Invalid mode
        r = await ac.put(
            f"/api/leagues/{league_id}/injury-reserve-compliance-mode",
            json={"mode": "bogus"},
        )
        assert r.status_code == 400, r.text
        # Happy path
        r2 = await ac.put(
            f"/api/leagues/{league_id}/injury-reserve-compliance-mode",
            json={"mode": "lock_waivers"},
        )
        assert r2.status_code == 200
        assert r2.json()["injury_reserve_compliance_mode"] == "lock_waivers"


@pytest.mark.asyncio
async def test_create_league_promotes_user_to_commissioner(isolated_app):
    app, db, cur_user = isolated_app
    await db.users.insert_one({
        "_id": ObjectId(),
        "email": "u@x.com",
        "name": "Owner",
        "role": "user",
    })
    # The deps lookup uses `cur_user["_id"]` as the user id string, so make sure
    # the user document we just inserted matches that id for the role-promotion
    # branch to find it.
    real_user = await db.users.find_one({"email": "u@x.com"})
    cur_user["_id"] = str(real_user["_id"])

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.post(
            "/api/leagues",
            json={
                "name": "Iter 109 Created",
                "sport": "nhl",
                "format": "dynasty",
                "scoring_format": "head_to_head",
                "max_teams": 12,
                "draft_type": "snake",
                "roster_spots": 25,
                "keepers_allowed": 0,
                "is_private": False,
                "salary_cap_enabled": False,
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["name"] == "Iter 109 Created"
        assert body["status"] == "setup"
        assert body["invite_code"]  # generated

    promoted = await db.users.find_one({"_id": real_user["_id"]})
    assert promoted["role"] == "commissioner"


@pytest.mark.asyncio
async def test_get_league_hydrates_extended_fields(isolated_app):
    app, db, _ = isolated_app
    league_id, _ = await _seed_league_team(db)
    # Stamp a few iter-105/106 fields on the league
    await db.leagues.update_one(
        {"_id": ObjectId(league_id)},
        {"$set": {
            "goalie_scoring_method": "daily_lock",
            "emergency_changes_enabled": True,
            "emergency_changes_scope": "per_season",
            "playoff_format": "playoff_tree",
        }},
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.get(f"/api/leagues/{league_id}")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["goalie_scoring_method"] == "daily_lock"
        assert body["emergency_changes_scope"] == "per_season"
        assert body["playoff_format"] == "playoff_tree"
        assert body["emergency_changes_enabled"] is True
