"""Iter 112 — Contract Buyouts workflow + Server-side depth persistence + League
Invites router extraction.

Verifies:
  (1) POST /teams/{id}/players/{pid}/buyout requires `contract_buyouts_enabled`
      (400 otherwise), removes the player from the roster, and stamps a
      multi-year dead-cap schedule.
  (2) GET /teams/{id}/dead-cap-schedule aggregates per year.
  (3) Double-buyout rejected with 400.
  (4) PUT /teams/{id}/depth-projections + GET round-trip.
  (5) PUT /teams/{id}/depth-lineup + GET round-trip (y0/y1/y2 only).
  (6) Extracted /api/leagues/{id}/invite + /api/public-leagues + /api/leagues/{id}/recalculate-stats
      respond under the new routes/league_invites.py module.
"""
import os
import asyncio
import logging
from datetime import datetime, timezone

import pytest
from bson import ObjectId
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from motor.motor_asyncio import AsyncIOMotorClient

from routes import teams as teams_routes
from routes import league_invites as league_invites_routes


@pytest.fixture
def isolated_app():
    import os
    mongo_url = os.environ.get("MONGO_URL", os.environ["MONGO_URL"])
    db_name = f"dd_test_iter112_{ObjectId()}"
    client = AsyncIOMotorClient(mongo_url, maxPoolSize=1, retryReads=True, retryWrites=True)
    db = client[db_name]

    cur_user = {"_id": "owner-1", "email": "o@x.com", "name": "Owner", "role": "user"}

    async def get_current_user(request):
        return cur_user

    async def log_activity(*args, **kwargs):
        return None

    def send_email(*args, **kwargs):
        return {"status": "mocked"}

    deps = {
        "db": db,
        "logger": logging.getLogger("test-iter112"),
        "get_current_user": get_current_user,
        "_safe_object_id": lambda v, label="id": ObjectId(v),
        "log_activity": log_activity,
        "send_sendgrid_email": send_email,
    }
    teams_routes.setup(deps)
    league_invites_routes.setup(deps)

    app = FastAPI()
    app.include_router(teams_routes.router, prefix="/api")
    app.include_router(league_invites_routes.router, prefix="/api")

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


async def _seed(db, *, owner_id="owner-1", contract_buyouts_enabled=True):
    league = {
        "_id": ObjectId(),
        "name": "Iter 112",
        "sport": "nhl", "format": "dynasty", "scoring_format": "head_to_head",
        "max_teams": 12, "current_teams": 1,
        "commissioner_id": owner_id, "commissioner_name": "Owner",
        "salary_cap_enabled": True, "salary_cap": 82_500_000,
        "draft_type": "snake", "roster_spots": 25, "keepers_allowed": 0,
        "is_private": False, "status": "active",
        "created_at": datetime.now(timezone.utc),
        "contract_buyouts_enabled": contract_buyouts_enabled,
    }
    await db.leagues.insert_one(league)
    player = {
        "_id": ObjectId(),
        "name": "Test Star",
        "position": "C",
        "team": "TST",
        "fantasy_points": 250,
        "points": 90,
        "nhl_id": 8478402,
        "age": 27,
    }
    await db.players.insert_one(player)
    team = {
        "_id": ObjectId(),
        "league_id": str(league["_id"]),
        "owner_id": owner_id,
        "owner_name": "Owner",
        "name": "Test Squad",
        "roster": [str(player["_id"])],
    }
    await db.teams.insert_one(team)
    return str(league["_id"]), str(team["_id"]), str(player["_id"])


@pytest.mark.asyncio
async def test_buyout_blocked_when_league_setting_off(isolated_app):
    app, db, _ = isolated_app
    _, team_id, player_id = await _seed(db, contract_buyouts_enabled=False)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.post(f"/api/teams/{team_id}/players/{player_id}/buyout", json={})
        assert r.status_code == 400
        assert "not enabled" in r.json()["detail"]


@pytest.mark.asyncio
async def test_buyout_creates_dead_cap_schedule(isolated_app):
    app, db, _ = isolated_app
    league_id, team_id, player_id = await _seed(db, contract_buyouts_enabled=True)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.post(f"/api/teams/{team_id}/players/{player_id}/buyout", json={})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["player_name"] == "Test Star"
        assert body["dead_cap_total"] > 0
        assert body["span_years"] >= 2

        # Player removed from roster
        team = await db.teams.find_one({"_id": ObjectId(team_id)})
        assert player_id not in team["roster"]
        assert team.get("dead_cap_schedule"), "schedule should be written"

        # GET aggregates per year
        r2 = await ac.get(f"/api/teams/{team_id}/dead-cap-schedule")
        assert r2.status_code == 200
        rows = r2.json()["schedule"]
        assert len(rows) >= 2
        assert all("year" in r and "total" in r for r in rows)


@pytest.mark.asyncio
async def test_double_buyout_rejected(isolated_app):
    app, db, _ = isolated_app
    _, team_id, player_id = await _seed(db, contract_buyouts_enabled=True)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r1 = await ac.post(f"/api/teams/{team_id}/players/{player_id}/buyout", json={})
        assert r1.status_code == 200
        # Re-add player to roster manually to simulate weird state, then re-buyout
        await db.teams.update_one({"_id": ObjectId(team_id)}, {"$push": {"roster": player_id}})
        r2 = await ac.post(f"/api/teams/{team_id}/players/{player_id}/buyout", json={})
        assert r2.status_code == 400
        assert "already" in r2.json()["detail"].lower()


@pytest.mark.asyncio
async def test_depth_projections_round_trip(isolated_app):
    app, db, _ = isolated_app
    _, team_id, _ = await _seed(db)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.put(
            f"/api/teams/{team_id}/depth-projections",
            json={"projections": {"p1": [100, 95, 92], "p2": [80, 78, 75]}},
        )
        assert r.status_code == 200, r.text
        assert r.json()["count"] == 2
        r2 = await ac.get(f"/api/teams/{team_id}/depth-projections")
        assert r2.status_code == 200
        assert r2.json()["projections"]["p1"] == [100, 95, 92]


@pytest.mark.asyncio
async def test_depth_lineup_round_trip(isolated_app):
    app, db, _ = isolated_app
    _, team_id, _ = await _seed(db)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.put(
            f"/api/teams/{team_id}/depth-lineup",
            json={"lineups": {"y0": {"L1-LW": "abc"}, "y3": {"bad": "x"}}},
        )
        assert r.status_code == 200, r.text
        r2 = await ac.get(f"/api/teams/{team_id}/depth-lineup")
        body = r2.json()
        assert body["lineups"]["y0"]["L1-LW"] == "abc"
        # y3 is filtered out (only y0/y1/y2 allowed)
        assert "y3" not in body["lineups"]


@pytest.mark.asyncio
async def test_league_invites_router_extraction(isolated_app):
    app, db, _ = isolated_app
    league_id, _, _ = await _seed(db)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # /invite
        r1 = await ac.get(f"/api/leagues/{league_id}/invite")
        assert r1.status_code == 200
        body = r1.json()
        assert body["invite_code"]
        assert body["invite_url"].startswith("http")

        # /public-leagues
        r2 = await ac.get("/api/public-leagues")
        assert r2.status_code == 200
        assert r2.json()["total"] >= 1

        # recalculate-stats (no matchups → no diffs but should still 200)
        r3 = await ac.post(f"/api/leagues/{league_id}/recalculate-stats")
        assert r3.status_code == 200
        assert r3.json()["teams_changed"] == 0
