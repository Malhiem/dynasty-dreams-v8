"""Iter 113 — Salary retention rows merge into dead_cap_schedule.

Verifies:
  (1) GET /teams/{id}/dead-cap-schedule now flattens active
      `db.salary_retentions` rows into per-year entries using each player's
      contract `yearsRemaining`.
  (2) Mixed buyout + retention sources yield aggregated `total` per year and
      separate `entries` with the right `source` discriminator + player names.
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


@pytest.fixture
def isolated_app():
    import os
    mongo_url = os.environ.get("MONGO_URL", os.environ["MONGO_URL"])
    db_name = f"dd_test_iter113_{ObjectId()}"
    client = AsyncIOMotorClient(mongo_url, maxPoolSize=1, retryReads=True, retryWrites=True)
    db = client[db_name]

    cur_user = {"_id": "owner-1", "email": "o@x.com", "name": "Owner", "role": "user"}

    async def get_current_user(request):
        return cur_user

    deps = {
        "db": db,
        "logger": logging.getLogger("test-iter113"),
        "get_current_user": get_current_user,
        "_safe_object_id": lambda v, label="id": ObjectId(v),
    }
    teams_routes.setup(deps)

    app = FastAPI()
    app.include_router(teams_routes.router, prefix="/api")
    yield app, db

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(client.drop_database(db_name))
        else:
            loop.run_until_complete(client.drop_database(db_name))
    except Exception:
        pass
    client.close()


@pytest.mark.asyncio
async def test_retention_inlined_into_schedule(isolated_app):
    app, db = isolated_app
    league = {
        "_id": ObjectId(),
        "name": "Iter 113",
        "sport": "nhl", "format": "dynasty", "scoring_format": "head_to_head",
        "max_teams": 12, "current_teams": 1,
        "commissioner_id": "owner-1", "commissioner_name": "Owner",
        "salary_cap_enabled": True, "salary_cap": 82_500_000,
        "draft_type": "snake", "roster_spots": 25, "keepers_allowed": 0,
        "is_private": False, "status": "active",
        "created_at": datetime.now(timezone.utc),
        "contract_buyouts_enabled": True,
    }
    await db.leagues.insert_one(league)
    player_a = {
        "_id": ObjectId(),
        "name": "Buyout Bobby", "position": "C", "team": "TST",
        "fantasy_points": 250, "points": 90, "nhl_id": 8478402, "age": 27,
    }
    player_b = {
        "_id": ObjectId(),
        "name": "Retained Rick", "position": "LW", "team": "OTH",
        "fantasy_points": 150, "points": 60, "nhl_id": 8478403, "age": 24,
    }
    await db.players.insert_many([player_a, player_b])
    team = {
        "_id": ObjectId(),
        "league_id": str(league["_id"]),
        "owner_id": "owner-1", "owner_name": "Owner",
        "name": "Tester", "roster": [str(player_a["_id"])],
    }
    await db.teams.insert_one(team)
    # Add a salary_retention row for player_b that our team is paying
    await db.salary_retentions.insert_one({
        "league_id": str(league["_id"]),
        "retainer_team_id": str(team["_id"]),
        "player_id": str(player_b["_id"]),
        "amount": 1_500_000,
        "pct": 25,
    })

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Now also buy out player_a so the schedule has mixed sources.
        r1 = await ac.post(f"/api/teams/{team['_id']}/players/{player_a['_id']}/buyout", json={})
        assert r1.status_code == 200, r1.text

        r2 = await ac.get(f"/api/teams/{team['_id']}/dead-cap-schedule")
        assert r2.status_code == 200
        body = r2.json()
        # We expect AT LEAST one year that has BOTH a buyout and retention
        first_year = body["schedule"][0]
        sources = sorted({e["source"] for e in first_year["entries"]})
        # Buyouts are written at current calendar year; retention starts at
        # current calendar year too — they should overlap on >= 1 year.
        assert "buyout" in sources
        assert "retention" in sources
        # Entry surface
        names = {e["player_name"] for e in first_year["entries"]}
        assert "Buyout Bobby" in names
        assert "Retained Rick" in names
        # total = sum of entries
        assert first_year["total"] == sum(e["amount"] for e in first_year["entries"])


@pytest.mark.asyncio
async def test_retention_only_team_still_returns_schedule(isolated_app):
    """A team with retention but no buyouts must still get schedule rows."""
    app, db = isolated_app
    league = {
        "_id": ObjectId(),
        "name": "Retention only",
        "sport": "nhl", "format": "dynasty", "scoring_format": "head_to_head",
        "max_teams": 12, "current_teams": 1,
        "commissioner_id": "owner-1", "commissioner_name": "Owner",
        "salary_cap_enabled": True, "salary_cap": 82_500_000,
        "draft_type": "snake", "roster_spots": 25, "keepers_allowed": 0,
        "is_private": False, "status": "active",
        "created_at": datetime.now(timezone.utc),
    }
    await db.leagues.insert_one(league)
    player = {"_id": ObjectId(), "name": "Just Retained", "position": "C",
              "team": "X", "fantasy_points": 100, "points": 40, "nhl_id": 99, "age": 25}
    await db.players.insert_one(player)
    team = {"_id": ObjectId(), "league_id": str(league["_id"]),
            "owner_id": "owner-1", "owner_name": "Owner",
            "name": "T", "roster": []}
    await db.teams.insert_one(team)
    await db.salary_retentions.insert_one({
        "league_id": str(league["_id"]),
        "retainer_team_id": str(team["_id"]),
        "player_id": str(player["_id"]),
        "amount": 750_000,
    })

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.get(f"/api/teams/{team['_id']}/dead-cap-schedule")
        assert r.status_code == 200
        body = r.json()
        assert body["total_dead_cap"] > 0
        first = body["schedule"][0]
        assert first["entries"][0]["source"] == "retention"
        assert first["entries"][0]["player_name"] == "Just Retained"
