"""Iter 232N.11 — /players waivers-first composite sort.

Verifies that when `waivers_first=True` and a league context has pending
claims, waiver-clearing players surface at the top of the response,
ordered by soonest `processes_at` ascending, and non-waiver rows fall
back to the caller's primary sort behind them.
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
    d = client[os.environ.get("DB_NAME", "test_database")]
    yield d
    client.close()


class R:  # minimal request stub
    pass


async def _setup_players_route(db):
    from routes import players as players_routes

    async def _fake_user(request):
        return {"_id": str(ObjectId())}

    def _fake_calc(stats, cfg):
        return 0.0

    players_routes.setup({
        "db": db, "get_current_user": _fake_user,
        "calculate_fantasy_points": _fake_calc,
    })


@pytest.mark.asyncio
async def test_waivers_first_surfaces_clearing_players_ahead_by_processes_at(db):
    from routes.players import get_players
    await _setup_players_route(db)

    league_id = str(ObjectId())
    sfx = uuid.uuid4().hex[:8]

    # Two high-scoring FAs (should sort ahead of low-point waiver
    # players in the default order) + two low-point waiver players
    # with staggered processes_at.
    hi1 = await db.players.insert_one({
        "name": f"Hi1 {sfx}", "position": "C", "player_type": "skater",
        "nhl_id": f"iter232N11-hi1-{sfx}", "points": 100,
    })
    hi2 = await db.players.insert_one({
        "name": f"Hi2 {sfx}", "position": "C", "player_type": "skater",
        "nhl_id": f"iter232N11-hi2-{sfx}", "points": 90,
    })
    wearly = await db.players.insert_one({
        "name": f"WEarly {sfx}", "position": "LW", "player_type": "skater",
        "nhl_id": f"iter232N11-early-{sfx}", "points": 10,
    })
    wlate = await db.players.insert_one({
        "name": f"WLate {sfx}", "position": "RW", "player_type": "skater",
        "nhl_id": f"iter232N11-late-{sfx}", "points": 20,
    })

    early_iso = (datetime.now(timezone.utc) + timedelta(hours=6)).isoformat()
    late_iso = (datetime.now(timezone.utc) + timedelta(hours=48)).isoformat()
    c1 = await db.waiver_claims.insert_one({
        "league_id": league_id, "player_id": str(wearly.inserted_id),
        "status": "pending", "processes_at": early_iso,
    })
    c2 = await db.waiver_claims.insert_one({
        "league_id": league_id, "player_id": str(wlate.inserted_id),
        "status": "pending", "processes_at": late_iso,
    })

    try:
        # OFF: default points-desc sort → Hi1, Hi2, WLate (pts=20), WEarly (pts=10)
        off = await get_players(
            request=R(), search=sfx, league_id=league_id, limit=10,
        )
        off_names = [p["name"] for p in off["players"]]
        assert off_names[0] == f"Hi1 {sfx}"
        assert off_names[1] == f"Hi2 {sfx}"

        # ON: waiver players surface first, ordered by processes_at
        # ascending — WEarly (6h) then WLate (48h) — then the high-point
        # non-waiver rows fall back to the primary sort behind them.
        on = await get_players(
            request=R(), search=sfx, league_id=league_id, limit=10,
            waivers_first=True,
        )
        on_names = [p["name"] for p in on["players"]]
        assert on_names[0] == f"WEarly {sfx}", f"expected WEarly first, got {on_names}"
        assert on_names[1] == f"WLate {sfx}", f"expected WLate second, got {on_names}"
        assert on_names[2] == f"Hi1 {sfx}"
        assert on_names[3] == f"Hi2 {sfx}"

        # waiver_status remains stamped correctly regardless of sort.
        by_name = {p["name"]: p for p in on["players"]}
        assert by_name[f"WEarly {sfx}"]["waiver_status"]["on_waivers"] is True
        assert by_name[f"WEarly {sfx}"]["waiver_status"]["processes_at"] == early_iso
        assert by_name[f"Hi1 {sfx}"]["waiver_status"]["on_waivers"] is False
    finally:
        await db.players.delete_many({
            "_id": {"$in": [hi1.inserted_id, hi2.inserted_id, wearly.inserted_id, wlate.inserted_id]},
        })
        await db.waiver_claims.delete_many({
            "_id": {"$in": [c1.inserted_id, c2.inserted_id]},
        })


@pytest.mark.asyncio
async def test_waivers_first_no_op_without_pending_claims(db):
    """Toggle is a no-op when the league has zero pending claims —
    the response must match the default (non-aggregation) sort order
    exactly."""
    from routes.players import get_players
    await _setup_players_route(db)

    league_id = str(ObjectId())
    sfx = uuid.uuid4().hex[:8]
    ins = []
    for i, pts in enumerate([80, 40, 60]):
        r = await db.players.insert_one({
            "name": f"NW{i} {sfx}", "position": "C", "player_type": "skater",
            "nhl_id": f"iter232N11-nw{i}-{sfx}", "points": pts,
        })
        ins.append(r.inserted_id)
    try:
        off = await get_players(
            request=R(), search=sfx, league_id=league_id, limit=10,
        )
        on = await get_players(
            request=R(), search=sfx, league_id=league_id, limit=10,
            waivers_first=True,
        )
        assert [p["name"] for p in on["players"]] == [p["name"] for p in off["players"]]
    finally:
        await db.players.delete_many({"_id": {"$in": ins}})


@pytest.mark.asyncio
async def test_waivers_first_ignored_without_league_id(db):
    """Without a league context we don't know what "on waivers" means,
    so the toggle silently no-ops rather than blowing up."""
    from routes.players import get_players
    await _setup_players_route(db)

    sfx = uuid.uuid4().hex[:8]
    r = await db.players.insert_one({
        "name": f"NoLg {sfx}", "position": "C", "player_type": "skater",
        "nhl_id": f"iter232N11-nolg-{sfx}", "points": 5,
    })
    try:
        res = await get_players(request=R(), search=sfx, limit=5, waivers_first=True)
        # Doesn't 500, and doesn't add waiver_status without league_id.
        assert res["players"] and res["players"][0]["name"] == f"NoLg {sfx}"
    finally:
        await db.players.delete_one({"_id": r.inserted_id})
