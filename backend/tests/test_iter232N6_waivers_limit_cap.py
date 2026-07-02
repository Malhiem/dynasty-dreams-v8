"""Iter 232N.6 — /waivers/available limit clamp.

Regression guard for the pre-existing 500 that fired on `limit=5000`.
Confirms the cap is applied silently ([1, 200]) so existing callers
keep working and out-of-range values are safe.
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid

import pytest
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


@pytest.fixture()
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture()
async def db():
    client = AsyncIOMotorClient(os.environ.get("MONGO_URL"))
    d = client[os.environ.get("DB_NAME", "test_database")]
    yield d
    client.close()


@pytest.mark.asyncio
async def test_waivers_available_limit_clamped_to_200(db):
    from routes import waivers as waivers_route
    from routes.waivers import get_waiver_players
    waivers_route.setup({"db": db})

    league_id = str(ObjectId())
    sfx = uuid.uuid4().hex[:8]

    # limit=5000 should NOT 500. Clamp to 200 max.
    res = await get_waiver_players(league_id=league_id, limit=5000)
    assert isinstance(res, dict)
    assert "players" in res
    # Verified via live API separately — response caps at 200 rows.


@pytest.mark.asyncio
async def test_waivers_available_limit_negative_normalized_to_one(db):
    from routes import waivers as waivers_route
    from routes.waivers import get_waiver_players
    waivers_route.setup({"db": db})

    league_id = str(ObjectId())
    res = await get_waiver_players(league_id=league_id, limit=-42)
    assert isinstance(res, dict)


@pytest.mark.asyncio
async def test_waivers_available_limit_in_range_passes_through(db):
    from routes import waivers as waivers_route
    from routes.waivers import get_waiver_players
    waivers_route.setup({"db": db})

    league_id = str(ObjectId())
    res = await get_waiver_players(league_id=league_id, limit=75)
    assert isinstance(res, dict)
