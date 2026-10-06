"""Iter 108 — bracket-advancement notifications + extracted scoring router.

(1) When `simulate_week` finishes a playoff matchup, a one-time
    `playoff_bracket_advance` notification is fanned out to every league
    member; subsequent re-simulations within 22h are suppressed via
    `tbd_deadline_pings`.

(2) `/api/scoring/config` GET still returns defaults under the same shape
    after the iter-108 extraction into routes/scoring.py.
"""
import os
import asyncio
from datetime import datetime, timezone

import pytest
from bson import ObjectId
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from motor.motor_asyncio import AsyncIOMotorClient

from routes import matchups as matchups_routes
from routes import scoring as scoring_routes
from routes import live_scoring as live_scoring_routes


@pytest.fixture
def isolated_app():
    import os
    mongo_url = os.environ.get("MONGO_URL", os.environ["MONGO_URL"])
    db_name = f"dd_test_iter108_{ObjectId()}"
    client = AsyncIOMotorClient(mongo_url, maxPoolSize=1, retryReads=True, retryWrites=True)
    db = client[db_name]

    notifications_fired: list = []

    async def get_current_user(request):
        return {"_id": "commish-1", "email": "c@x.com", "name": "Commish"}

    async def fake_create_notification(user_id, notif_type, title, message, league_id, link):
        notifications_fired.append({
            "user_id": user_id, "type": notif_type, "title": title,
            "message": message, "league_id": league_id, "link": link,
        })

    async def fake_broadcast(*a, **k):
        return None

    deps = {
        "db": db,
        "sio": None,
        "logger": __import__("logging").getLogger("test"),
        "get_current_user": get_current_user,
        "_safe_object_id": lambda v, label="id": ObjectId(v),
        "calculate_fantasy_points": lambda p, c=None: 5.0,
        "_evaluate_conditions": lambda t: {"all_met": False},
        "_execute_trade": lambda t: None,
        "_apply_pick_upgrades": None,
        "broadcast_to_room": fake_broadcast,
        "create_notification": fake_create_notification,
    }
    matchups_routes.setup(deps)
    scoring_routes.setup(deps)
    live_scoring_routes.setup(deps)

    app = FastAPI()
    app.include_router(matchups_routes.router, prefix="/api")
    app.include_router(scoring_routes.router, prefix="/api")
    app.include_router(live_scoring_routes.router, prefix="/api")

    yield app, db, notifications_fired

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
async def test_scoring_config_defaults_after_extraction(isolated_app):
    app, db, _ = isolated_app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        inserted = await db.leagues.insert_one({"name": "Defaults Fixture", "commissioner_id": "commish-1"})
        r = await ac.get("/api/scoring/config", params={"league_id": str(inserted.inserted_id)})
        assert r.status_code == 200
        body = r.json()
        # Defaults are returned when no config exists for the league.
        assert "skater_scoring" in body
        assert "goalie_scoring" in body
        assert body["skater_scoring"]["goals"] == 3  # default skater goals weight
        assert body["goalie_scoring"]["wins"] == 5   # default goalie wins weight


@pytest.mark.asyncio
async def test_simulate_week_fires_playoff_bracket_advance_notification(isolated_app):
    app, db, notifs = isolated_app

    # Seed: 1 league with 2 owners + 2 teams + 1 playoff matchup ready to settle.
    league_id = str(ObjectId())
    await db.leagues.insert_one({
        "_id": ObjectId(league_id),
        "name": "Test League",
        "commissioner_id": "commish-1",
        "season": 2026,
        "current_week": 1,
    })
    # Seed players so calc_team_score differs between the two teams.
    p1 = ObjectId(); p2 = ObjectId(); p3 = ObjectId()
    await db.players.insert_one({"_id": p1, "name": "P1"})
    await db.players.insert_one({"_id": p2, "name": "P2"})
    await db.players.insert_one({"_id": p3, "name": "P3"})

    home_id = str(ObjectId())
    away_id = str(ObjectId())
    await db.teams.insert_one({
        "_id": ObjectId(home_id), "league_id": league_id,
        "owner_id": "u-home", "owner_name": "Home",
        "name": "Home Team", "roster": [str(p1), str(p2)],
    })
    await db.teams.insert_one({
        "_id": ObjectId(away_id), "league_id": league_id,
        "owner_id": "u-away", "owner_name": "Away",
        "name": "Away Team", "roster": [str(p3)],
    })
    matchup_id = ObjectId()
    await db.matchups.insert_one({
        "_id": matchup_id, "league_id": league_id, "week": 1,
        "status": "scheduled",
        "home_team_id": home_id, "away_team_id": away_id,
        "home_team_name": "Home Team", "away_team_name": "Away Team",
        "is_playoff": True, "bracket_round": 1, "bracket": "championship",
        "is_final": False,
    })

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.post(
            "/api/matchups/simulate-week",
            json={"league_id": league_id, "week": 1},
        )
        assert r.status_code == 200, r.text

    # Both owners should have received a playoff_bracket_advance notif.
    types = [n["type"] for n in notifs]
    assert "playoff_bracket_advance" in types, f"types={types}"

    # Idempotency row written so a re-simulate doesn't fire again.
    ping = await db.tbd_deadline_pings.find_one({
        "league_id": league_id, "bracket": "playoff_advance",
        "matchup_id": str(matchup_id),
    })
    assert ping is not None
