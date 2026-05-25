"""Iter 111 — Future-year salary caps + contract buyouts toggle backend support.

Verifies that the iter-111 admin endpoint accepts the new fields, persists
them, and that the LeagueResponse hydrates them on subsequent GETs.
"""
import asyncio
import logging

import pytest
from bson import ObjectId
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from motor.motor_asyncio import AsyncIOMotorClient

from routes import leagues as leagues_routes


@pytest.fixture
def isolated_app():
    import os
    mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    db_name = f"dd_test_iter111_{ObjectId()}"
    client = AsyncIOMotorClient(mongo_url, maxPoolSize=1, retryReads=True, retryWrites=True)
    db = client[db_name]

    cur_user = {"_id": "commish-1", "email": "c@x.com", "name": "Commish", "role": "commissioner"}

    async def get_current_user(request):
        return cur_user

    deps = {
        "db": db,
        "logger": logging.getLogger("test-iter111"),
        "get_current_user": get_current_user,
        "_safe_object_id": lambda v, label="id": ObjectId(v),
    }
    leagues_routes.setup(deps)

    app = FastAPI()
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


@pytest.mark.asyncio
async def test_cap_settings_persists_future_caps_and_buyouts(isolated_app):
    app, db, _ = isolated_app
    from datetime import datetime, timezone
    league_id = ObjectId()
    await db.leagues.insert_one({
        "_id": league_id,
        "name": "Iter 111 League",
        "sport": "nhl",
        "format": "dynasty",
        "scoring_format": "head_to_head",
        "max_teams": 12,
        "current_teams": 0,
        "commissioner_id": "commish-1",
        "commissioner_name": "Commish",
        "salary_cap_enabled": False,
        "draft_type": "snake",
        "roster_spots": 25,
        "keepers_allowed": 0,
        "is_private": False,
        "status": "active",
        "created_at": datetime.now(timezone.utc),
    })

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.put(
            f"/api/leagues/{league_id}/admin/cap-settings",
            json={
                "salary_cap_enabled": True,
                "salary_cap": 82_500_000,
                "salary_cap_year_plus_1": 85_000_000,
                "salary_cap_year_plus_2": 88_000_000,
                "salary_cap_year_plus_1_tentative": False,
                "salary_cap_year_plus_2_tentative": True,
                "contract_buyouts_enabled": True,
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        # Response payload reflects iter-111 fields
        assert body["salary_cap"] == 82_500_000
        assert body["salary_cap_year_plus_1"] == 85_000_000
        assert body["salary_cap_year_plus_2"] == 88_000_000
        assert body["salary_cap_year_plus_1_tentative"] is False
        assert body["salary_cap_year_plus_2_tentative"] is True
        assert body["contract_buyouts_enabled"] is True

        # GET /leagues/{id} hydrates the same fields via the LeagueResponse
        r2 = await ac.get(f"/api/leagues/{league_id}")
        assert r2.status_code == 200, r2.text
        body2 = r2.json()
        assert body2["salary_cap_year_plus_1"] == 85_000_000
        assert body2["salary_cap_year_plus_2"] == 88_000_000
        assert body2["salary_cap_year_plus_1_tentative"] is False
        assert body2["salary_cap_year_plus_2_tentative"] is True
        assert body2["contract_buyouts_enabled"] is True


@pytest.mark.asyncio
async def test_cap_settings_independently_togglable_fields(isolated_app):
    """A sparse payload only touching `contract_buyouts_enabled` must not
    erase a previously-saved future-year cap."""
    app, db, _ = isolated_app
    from datetime import datetime, timezone
    league_id = ObjectId()
    await db.leagues.insert_one({
        "_id": league_id,
        "name": "Iter 111 Sparse",
        "sport": "nhl", "format": "dynasty", "scoring_format": "head_to_head",
        "max_teams": 12, "current_teams": 0,
        "commissioner_id": "commish-1", "commissioner_name": "Commish",
        "salary_cap_enabled": True,
        "salary_cap": 80_000_000,
        "salary_cap_year_plus_1": 84_000_000,
        "salary_cap_year_plus_1_tentative": True,
        "draft_type": "snake", "roster_spots": 25, "keepers_allowed": 0,
        "is_private": False, "status": "active",
        "created_at": datetime.now(timezone.utc),
    })

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.put(
            f"/api/leagues/{league_id}/admin/cap-settings",
            json={"contract_buyouts_enabled": True},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["contract_buyouts_enabled"] is True
        # Untouched future-year cap preserved
        assert body["salary_cap_year_plus_1"] == 84_000_000
        assert body["salary_cap_year_plus_1_tentative"] is True
        assert body["salary_cap"] == 80_000_000
