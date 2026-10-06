"""Iter 232N.8 — /players waiver_status enrichment.

Verifies the unified free-agent screen data model:
  (1) A player with an active pending waiver_claim in the requested
      league gets `waiver_status = {on_waivers: True, processes_at}`.
  (2) A player with no pending claim gets `waiver_status =
      {on_waivers: False, processes_at: None}`.
  (3) When multiple pending claims exist for the same player, the
      EARLIEST processes_at wins (whole cohort processes together).
  (4) Pending claims in a DIFFERENT league don't leak into the
      requested league's view.
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone, timedelta

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
    d = client[os.environ.get("DB_NAME", os.environ["DB_NAME"])]
    yield d
    client.close()


class R:  # minimal request stub
    pass


@pytest.mark.asyncio
async def test_players_waiver_status_flagged_when_pending_claim_exists(db):
    from routes import players as players_routes
    from routes.players import get_players

    async def _fake_user(request):
        return {"_id": str(ObjectId())}

    def _fake_calc(stats, cfg):
        return 0.0

    players_routes.setup({
        "db": db, "get_current_user": _fake_user,
        "calculate_fantasy_points": _fake_calc,
    })

    league_id = str(ObjectId())
    sfx = uuid.uuid4().hex[:8]
    fa = await db.players.insert_one({
        "name": f"FA {sfx}", "position": "C",
        "player_type": "skater", "nhl_id": f"iter232N8-fa-{sfx}",
    })
    on_w = await db.players.insert_one({
        "name": f"OnW {sfx}", "position": "C",
        "player_type": "skater", "nhl_id": f"iter232N8-w-{sfx}",
    })
    processes_at = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
    claim = await db.waiver_claims.insert_one({
        "league_id": league_id, "player_id": str(on_w.inserted_id),
        "status": "pending", "processes_at": processes_at,
    })

    res = await get_players(
        request=R(),  # type: ignore[arg-type]
        search=sfx, league_id=league_id, limit=10,
    )
    by_name = {p["name"]: p for p in res["players"]}
    assert by_name[f"FA {sfx}"]["waiver_status"] == {"on_waivers": False, "processes_at": None}
    assert by_name[f"OnW {sfx}"]["waiver_status"]["on_waivers"] is True
    assert by_name[f"OnW {sfx}"]["waiver_status"]["processes_at"] == processes_at

    await db.players.delete_many({"_id": {"$in": [fa.inserted_id, on_w.inserted_id]}})
    await db.waiver_claims.delete_one({"_id": claim.inserted_id})


@pytest.mark.asyncio
async def test_players_waiver_status_earliest_processes_at_wins(db):
    from routes import players as players_routes
    from routes.players import get_players

    async def _fake_user(request):
        return {"_id": str(ObjectId())}

    def _fake_calc(stats, cfg):
        return 0.0

    players_routes.setup({
        "db": db, "get_current_user": _fake_user,
        "calculate_fantasy_points": _fake_calc,
    })

    league_id = str(ObjectId())
    sfx = uuid.uuid4().hex[:8]
    p = await db.players.insert_one({
        "name": f"Multi {sfx}", "position": "D",
        "player_type": "skater", "nhl_id": f"iter232N8-multi-{sfx}",
    })
    early = (datetime.now(timezone.utc) + timedelta(hours=12)).isoformat()
    late = (datetime.now(timezone.utc) + timedelta(hours=36)).isoformat()
    c1 = await db.waiver_claims.insert_one({
        "league_id": league_id, "player_id": str(p.inserted_id),
        "status": "pending", "processes_at": late,
    })
    c2 = await db.waiver_claims.insert_one({
        "league_id": league_id, "player_id": str(p.inserted_id),
        "status": "pending", "processes_at": early,
    })

    res = await get_players(request=R(), search=sfx, league_id=league_id, limit=5)  # type: ignore[arg-type]
    row = res["players"][0]
    assert row["waiver_status"]["on_waivers"] is True
    assert row["waiver_status"]["processes_at"] == early

    await db.players.delete_one({"_id": p.inserted_id})
    await db.waiver_claims.delete_many({"_id": {"$in": [c1.inserted_id, c2.inserted_id]}})


@pytest.mark.asyncio
async def test_players_waiver_status_isolates_by_league(db):
    from routes import players as players_routes
    from routes.players import get_players

    async def _fake_user(request):
        return {"_id": str(ObjectId())}

    def _fake_calc(stats, cfg):
        return 0.0

    players_routes.setup({
        "db": db, "get_current_user": _fake_user,
        "calculate_fantasy_points": _fake_calc,
    })

    la = str(ObjectId())
    lb = str(ObjectId())
    sfx = uuid.uuid4().hex[:8]
    p = await db.players.insert_one({
        "name": f"Cross {sfx}", "position": "LW",
        "player_type": "skater", "nhl_id": f"iter232N8-cross-{sfx}",
    })
    # Pending claim in league A only.
    proc = (datetime.now(timezone.utc) + timedelta(hours=48)).isoformat()
    claim = await db.waiver_claims.insert_one({
        "league_id": la, "player_id": str(p.inserted_id),
        "status": "pending", "processes_at": proc,
    })
    # From league B's perspective, the player is NOT on waivers.
    res_b = await get_players(request=R(), search=sfx, league_id=lb, limit=5)  # type: ignore[arg-type]
    assert res_b["players"][0]["waiver_status"]["on_waivers"] is False
    # From league A's perspective they ARE.
    res_a = await get_players(request=R(), search=sfx, league_id=la, limit=5)  # type: ignore[arg-type]
    assert res_a["players"][0]["waiver_status"]["on_waivers"] is True
    assert res_a["players"][0]["waiver_status"]["processes_at"] == proc

    await db.players.delete_one({"_id": p.inserted_id})
    await db.waiver_claims.delete_one({"_id": claim.inserted_id})
