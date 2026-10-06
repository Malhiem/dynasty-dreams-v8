"""Iter 114 — Buyout length-option presets + commissioner reversal endpoints +
retention double-count prevention.
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
    db_name = f"dd_test_iter114_{ObjectId()}"
    client = AsyncIOMotorClient(mongo_url, maxPoolSize=1, retryReads=True, retryWrites=True)
    db = client[db_name]

    role = {"value": "commissioner"}

    async def get_current_user(request):
        return {"_id": "owner-1", "email": "o@x.com", "name": "Owner", "role": role["value"]}

    deps = {
        "db": db,
        "logger": logging.getLogger("test-iter114"),
        "get_current_user": get_current_user,
        "_safe_object_id": lambda v, label="id": ObjectId(v),
    }
    teams_routes.setup(deps)

    app = FastAPI()
    app.include_router(teams_routes.router, prefix="/api")
    yield app, db, role

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(client.drop_database(db_name))
        else:
            loop.run_until_complete(client.drop_database(db_name))
    except Exception:
        pass
    client.close()


async def _seed(db, *, contract_buyouts_enabled=True, owner_id="owner-1"):
    league = {
        "_id": ObjectId(),
        "name": "Iter 114",
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
        "name": "Buyout Brett", "position": "C", "team": "TST",
        "fantasy_points": 250, "points": 90, "nhl_id": 8478402, "age": 27,
    }
    await db.players.insert_one(player)
    team = {
        "_id": ObjectId(),
        "league_id": str(league["_id"]),
        "owner_id": owner_id, "owner_name": "Owner",
        "name": "Tester", "roster": [str(player["_id"])],
    }
    await db.teams.insert_one(team)
    return str(league["_id"]), str(team["_id"]), str(player["_id"])


@pytest.mark.asyncio
async def test_buyout_length_option_one_year(isolated_app):
    app, db, _ = isolated_app
    _, team_id, player_id = await _seed(db)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.post(
            f"/api/teams/{team_id}/players/{player_id}/buyout",
            json={"length_option": "one_year"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        # one_year preset => rate=1.0, span=1 → full salary*yearsRem packed into 1 yr
        assert body["span_years"] == 1
        assert body["dead_cap_total"] > 0
        assert body["annual_dead_cap"] == body["dead_cap_total"]


@pytest.mark.asyncio
async def test_buyout_length_option_half(isolated_app):
    app, db, _ = isolated_app
    _, team_id, player_id = await _seed(db)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.post(
            f"/api/teams/{team_id}/players/{player_id}/buyout",
            json={"length_option": "half"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        # half = 50% rate
        # Verify entry stamp on schedule
        sched = await ac.get(f"/api/teams/{team_id}/dead-cap-schedule")
        entries = [e for r in sched.json()["schedule"] for e in r["entries"]]
        assert any(e.get("length_option") == "half" for e in entries)


@pytest.mark.asyncio
async def test_reverse_buyout_restores_roster_and_clears_schedule(isolated_app):
    app, db, _ = isolated_app
    _, team_id, player_id = await _seed(db)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r1 = await ac.post(f"/api/teams/{team_id}/players/{player_id}/buyout", json={})
        assert r1.status_code == 200
        team_after = await db.teams.find_one({"_id": ObjectId(team_id)})
        assert player_id not in team_after["roster"]

        r2 = await ac.delete(f"/api/teams/{team_id}/buyouts/{player_id}")
        assert r2.status_code == 200, r2.text
        body = r2.json()
        assert body["reversed"] is True
        assert body["removed_entries"] > 0

        team_restored = await db.teams.find_one({"_id": ObjectId(team_id)})
        assert player_id in team_restored["roster"]
        remaining_buyout = [
            e for e in (team_restored.get("dead_cap_schedule") or [])
            if e.get("source") == "buyout" and e.get("player_id") == player_id
        ]
        assert remaining_buyout == []


@pytest.mark.asyncio
async def test_reverse_buyout_requires_commissioner(isolated_app):
    app, db, role = isolated_app
    _, team_id, player_id = await _seed(db)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        await ac.post(f"/api/teams/{team_id}/players/{player_id}/buyout", json={})
        # Demote user
        role["value"] = "user"
        # Make user NOT the commissioner — change commissioner on the league
        await db.leagues.update_one(
            {},
            {"$set": {"commissioner_id": "someone-else", "co_commissioners": []}},
        )
        r = await ac.delete(f"/api/teams/{team_id}/buyouts/{player_id}")
        assert r.status_code == 403


@pytest.mark.asyncio
async def test_retention_no_double_count_after_schedule_write(isolated_app):
    """If a retention is *already* in team.dead_cap_schedule (written by the
    trade engine), the on-the-fly merge in /dead-cap-schedule must NOT
    re-add it."""
    app, db, _ = isolated_app
    league_id, team_id, _ = await _seed(db, contract_buyouts_enabled=False)
    other_player = {
        "_id": ObjectId(), "name": "Retained R", "position": "C", "team": "OTH",
        "fantasy_points": 100, "points": 40, "nhl_id": 99, "age": 25,
    }
    await db.players.insert_one(other_player)
    cur_year = datetime.now(timezone.utc).year
    # Pre-existing schedule entry (simulates trade-engine write)
    await db.teams.update_one(
        {"_id": ObjectId(team_id)},
        {"$push": {"dead_cap_schedule": {"$each": [
            {"year": cur_year, "amount": 500_000, "source": "retention",
             "player_id": str(other_player["_id"]), "player_name": "Retained R"},
            {"year": cur_year + 1, "amount": 500_000, "source": "retention",
             "player_id": str(other_player["_id"]), "player_name": "Retained R"},
        ]}}},
    )
    # And a retention row in the legacy collection for the SAME player
    await db.salary_retentions.insert_one({
        "league_id": league_id,
        "retainer_team_id": team_id,
        "player_id": str(other_player["_id"]),
        "amount": 500_000,
    })

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.get(f"/api/teams/{team_id}/dead-cap-schedule")
        assert r.status_code == 200
        rows = r.json()["schedule"]
        total = sum(r["total"] for r in rows)
        # 2 entries × $500k each = $1,000,000 (NOT double-counted to $2M)
        assert total == 1_000_000
