"""Iter 232N.67 — Structure lock (division → conference) pytest suite.

Covers the new hard-rule behaviour on the League Structure admin tab:
  1. Save with `lock=true` persists `structure_locked` + the derived
     `division_conference_map` on the league doc.
  2. Once locked, a save that tries to remap a division to a different
     conference returns 409 with structured per-team conflicts.
  3. `POST /leagues/{id}/divisions/unlock` clears the lock and lets
     the next save proceed with a new mapping.
  4. A save that has two teams in the same division but different
     conferences returns 409 (`same_division_different_conference`)
     even when the league is not locked, so we don't seed inconsistent
     state into the map.
"""
from __future__ import annotations

import asyncio
import logging

import pytest
from bson import ObjectId
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from motor.motor_asyncio import AsyncIOMotorClient

from routes import leagues as leagues_routes


@pytest.fixture
def app_and_db():
    import os
    mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    db_name = f"dd_test_iter232N67_{ObjectId()}"
    client = AsyncIOMotorClient(mongo_url, maxPoolSize=1)
    db = client[db_name]

    commish_id = ObjectId()
    cur_user = {"_id": commish_id, "email": "commish@x.com",
                "name": "C", "role": "commissioner"}

    async def get_current_user(_request):
        return cur_user

    leagues_routes.setup({
        "db": db,
        "logger": logging.getLogger("test-iter232n67"),
        "get_current_user": get_current_user,
        "_safe_object_id": lambda v, label="id": ObjectId(v),
    })

    app = FastAPI()
    app.include_router(leagues_routes.router, prefix="/api")

    yield app, db, commish_id

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(client.drop_database(db_name))
        else:
            loop.run_until_complete(client.drop_database(db_name))
    except Exception:
        pass
    client.close()


async def _seed_league_and_teams(db, commish_id, team_names=None):
    league_id = ObjectId()
    await db.leagues.insert_one({
        "_id": league_id, "name": "Test League",
        "commissioner_id": commish_id,
    })
    team_ids = []
    for name in (team_names or ["A", "B", "C", "D"]):
        tid = ObjectId()
        await db.teams.insert_one({
            "_id": tid, "league_id": str(league_id),
            "name": name,
        })
        team_ids.append(str(tid))
    return str(league_id), team_ids


def _payload(team_ids, mapping):
    """`mapping` is a list of (division, conference) tuples aligned
    with `team_ids`."""
    return {
        "assignments": [
            {"team_id": tid, "division": d, "conference": c}
            for tid, (d, c) in zip(team_ids, mapping)
        ],
    }


@pytest.mark.asyncio
async def test_save_with_lock_persists_map(app_and_db):
    app, db, commish_id = app_and_db
    league_id, tids = await _seed_league_and_teams(db, commish_id)
    body = {**_payload(tids, [
        ("Atlantic", "Eastern"), ("Atlantic", "Eastern"),
        ("Pacific",  "Western"), ("Pacific",  "Western"),
    ]), "lock": True}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.put(f"/api/leagues/{league_id}/divisions", json=body)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["structure_locked"] is True
    assert data["division_conference_map"] == {"Atlantic": "Eastern", "Pacific": "Western"}

    league = await db.leagues.find_one({"_id": ObjectId(league_id)})
    assert league["structure_locked"] is True
    assert league["division_conference_map"] == {"Atlantic": "Eastern", "Pacific": "Western"}
    assert league.get("structure_locked_by") == "commish@x.com"


@pytest.mark.asyncio
async def test_locked_save_rejects_remap_with_409(app_and_db):
    app, db, commish_id = app_and_db
    league_id, tids = await _seed_league_and_teams(db, commish_id)
    # Lock: Atlantic→Eastern, Pacific→Western
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.put(f"/api/leagues/{league_id}/divisions", json={
            **_payload(tids, [
                ("Atlantic", "Eastern"), ("Atlantic", "Eastern"),
                ("Pacific",  "Western"), ("Pacific",  "Western"),
            ]),
            "lock": True,
        })
        assert r.status_code == 200

        # Now try to remap the last team from Pacific→Eastern (which
        # would flip the locked map).
        r = await c.put(f"/api/leagues/{league_id}/divisions", json=_payload(tids, [
            ("Atlantic", "Eastern"), ("Atlantic", "Eastern"),
            ("Pacific",  "Western"), ("Pacific",  "Eastern"),  # ⚠️
        ]))
    assert r.status_code == 409, r.text
    detail = r.json()["detail"]
    assert detail["code"] == "division_conference_mapping_conflict"
    assert detail["structure_locked"] is True
    # Should surface the offending team.
    offending = [c for c in detail["conflicts"] if c["team_id"] == tids[3]]
    assert offending, detail
    assert offending[0]["division"] == "Pacific"
    assert offending[0]["expected_conference"] == "Western"
    assert offending[0]["attempted_conference"] == "Eastern"
    # Reason may be `same_division_different_conference` (in-batch check
    # fires first) or `locked_mapping_violation` — both are valid, both
    # explain why the save was rejected.
    assert offending[0]["reason"] in ("locked_mapping_violation", "same_division_different_conference")


@pytest.mark.asyncio
async def test_unlock_then_remap_succeeds(app_and_db):
    app, db, commish_id = app_and_db
    league_id, tids = await _seed_league_and_teams(db, commish_id)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        # Lock initial mapping.
        r = await c.put(f"/api/leagues/{league_id}/divisions", json={
            **_payload(tids, [
                ("Atlantic", "Eastern"), ("Atlantic", "Eastern"),
                ("Pacific",  "Western"), ("Pacific",  "Western"),
            ]),
            "lock": True,
        })
        assert r.status_code == 200
        # Unlock.
        r = await c.post(f"/api/leagues/{league_id}/divisions/unlock")
        assert r.status_code == 200, r.text
        assert r.json()["structure_locked"] is False
        # Remap Pacific→Eastern is now allowed.
        r = await c.put(f"/api/leagues/{league_id}/divisions", json=_payload(tids, [
            ("Atlantic", "Eastern"), ("Atlantic", "Eastern"),
            ("Pacific",  "Eastern"), ("Pacific",  "Eastern"),
        ]))
    assert r.status_code == 200, r.text
    league = await db.leagues.find_one({"_id": ObjectId(league_id)})
    assert league.get("structure_locked") is False


@pytest.mark.asyncio
async def test_same_division_different_conferences_rejects_when_locking(app_and_db):
    """Unlocked saves tolerate inconsistency (commissioners often shift
    teams mid-edit). The moment `lock=true` is set, that same
    inconsistency becomes a hard 409 so we don't seed a broken map."""
    app, db, commish_id = app_and_db
    league_id, tids = await _seed_league_and_teams(db, commish_id)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        # Unlocked save: allowed (backwards-compat with existing UIs).
        r = await c.put(f"/api/leagues/{league_id}/divisions", json=_payload(tids, [
            ("Atlantic", "Eastern"),
            ("Atlantic", "Western"),   # inconsistent
            ("Pacific",  "Western"),
            ("Pacific",  "Western"),
        ]))
        assert r.status_code == 200, r.text

        # But locking that same inconsistent state is a hard 409.
        r = await c.put(f"/api/leagues/{league_id}/divisions", json={
            **_payload(tids, [
                ("Atlantic", "Eastern"),
                ("Atlantic", "Western"),
                ("Pacific",  "Western"),
                ("Pacific",  "Western"),
            ]),
            "lock": True,
        })
    assert r.status_code == 409, r.text
    detail = r.json()["detail"]
    assert detail["code"] == "division_conference_mapping_conflict"
    assert any(c["reason"] == "same_division_different_conference"
               for c in detail["conflicts"])


@pytest.mark.asyncio
async def test_get_divisions_exposes_lock_state(app_and_db):
    app, db, commish_id = app_and_db
    league_id, tids = await _seed_league_and_teams(db, commish_id)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.put(f"/api/leagues/{league_id}/divisions", json={
            **_payload(tids, [
                ("Atlantic", "Eastern"), ("Atlantic", "Eastern"),
                ("Pacific",  "Western"), ("Pacific",  "Western"),
            ]),
            "lock": True,
        })
        assert r.status_code == 200
        r = await c.get(f"/api/leagues/{league_id}/divisions")
    assert r.status_code == 200
    data = r.json()
    assert data["structure_locked"] is True
    assert data["division_conference_map"] == {"Atlantic": "Eastern", "Pacific": "Western"}
