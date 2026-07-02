"""Iter 232L — Trade asset hydration for the Transactions page.

Verifies GET /trades enriches assets with age, cap_hit (synthesized when
no contract exists), fantasy_points, fantasy_points_per_game, and a
stat_categories breakdown, plus surfaces the league scoring_categories
at the trade level for the FPts↔Categories toggle.
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone

import pytest
from motor.motor_asyncio import AsyncIOMotorClient

# Make backend importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from routes.trades import _hydrate_trade_assets, setup as trades_setup  # noqa: E402
from routes.roster import _deps as roster_deps  # noqa: E402
from routes.scoring import DEFAULT_SKATER_SCORING, DEFAULT_GOALIE_SCORING  # noqa: E402


def _calc_fn(player, config=None):
    cfg = config or {"skater_scoring": DEFAULT_SKATER_SCORING, "goalie_scoring": DEFAULT_GOALIE_SCORING}
    is_g = player.get("player_type") == "goalie" or player.get("position") == "G"
    cats = cfg.get("goalie_scoring" if is_g else "skater_scoring") or {}
    return round(sum((player.get(k, 0) or 0) * w for k, w in cats.items()), 1)


@pytest.fixture()
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture()
async def db():
    client = AsyncIOMotorClient(os.environ.get("MONGO_URL"))
    db = client[os.environ.get("DB_NAME", "test_database")]
    # Wire up the deps trades.py + roster.py rely on for calc + salary
    # synthesis. In production these come from server.py's setup(); in
    # this direct-call unit test we mirror them.
    trades_setup({
        "db": db,
        "logger": __import__("logging").getLogger("iter232L"),
        "get_current_user": None,
        "broadcast_to_room": None,
        "create_notification": None,
        "_execute_trade": None,
        "_evaluate_conditions": None,
        "calculate_fantasy_points": _calc_fn,
    })
    roster_deps["calculate_fantasy_points"] = _calc_fn
    yield db
    client.close()


@pytest.mark.asyncio
async def test_hydrate_trade_assets_populates_all_fields(db):
    # Insert a throwaway league + scoring config + player.
    league_id = "iter232L_" + uuid.uuid4().hex[:8]
    await db.scoring_configs.insert_one({
        "league_id": league_id,
        "skater_scoring": {"goals": 3, "assists": 2, "shots": 0.5},
        "goalie_scoring": {"wins": 5},
    })
    player_doc = {
        "name": "Hydration Test Player",
        "nhl_id": f"iter232L-{uuid.uuid4().hex[:8]}",
        "position": "C",
        "team": "TST",
        "player_type": "skater",
        "goals": 20, "assists": 30, "points": 50,
        "shots": 100, "games_played": 40,
        "age": 24,
    }
    result = await db.players.insert_one(player_doc)
    pid = str(result.inserted_id)

    trade = {
        "league_id": league_id,
        "assets_offered": [{
            "asset_type": "player",
            "player_id": pid,
            "player_name": "Hydration Test Player",
            "position": "C",
        }],
        "assets_requested": [{
            "asset_type": "pick",
            "pick_year": 2027,
            "pick_round": 1,
        }],
    }

    hydrated = await _hydrate_trade_assets(db, trade)

    a = hydrated["assets_offered"][0]
    assert a["age"] == 24
    assert a["cap_hit"] > 0, "cap_hit should be synthesized when no contract exists"
    assert a["fantasy_points"] == round(20 * 3 + 30 * 2 + 100 * 0.5, 1)
    assert a["games_played"] == 40
    assert a["fantasy_points_per_game"] > 0
    assert "stat_categories" in a
    assert a["stat_categories"]["goals"]["value"] == 20
    assert a["stat_categories"]["goals"]["label"] == "G"

    # Pick assets should NOT be hydrated (no player_id).
    pick = hydrated["assets_requested"][0]
    assert "fantasy_points" not in pick
    assert pick.get("age") is None or pick.get("age") == 0 or "age" not in pick

    # Trade-level scoring categories present with skater/goalie split.
    cats = hydrated["scoring_categories"]
    assert isinstance(cats["skater"], list) and len(cats["skater"]) >= 3
    assert cats["skater"][0]["label"] == "G"

    # Cleanup
    await db.players.delete_one({"_id": result.inserted_id})
    await db.scoring_configs.delete_one({"league_id": league_id})


@pytest.mark.asyncio
async def test_hydrate_prefers_contract_aav_over_synthesis(db):
    league_id = "iter232L_" + uuid.uuid4().hex[:8]
    player_doc = {
        "name": "AAV Player",
        "nhl_id": f"iter232L-{uuid.uuid4().hex[:8]}",
        "position": "RW",
        "player_type": "skater",
        "goals": 30, "assists": 40, "points": 70, "games_played": 60,
    }
    result = await db.players.insert_one(player_doc)
    pid = str(result.inserted_id)
    await db.contracts.insert_one({
        "league_id": league_id,
        "player_id": pid,
        "team_id": "team_a",
        "aav": 8_250_000,
        "years": 5,
    })

    trade = {
        "league_id": league_id,
        "assets_offered": [{"asset_type": "player", "player_id": pid}],
        "assets_requested": [],
    }
    hydrated = await _hydrate_trade_assets(db, trade)
    assert hydrated["assets_offered"][0]["cap_hit"] == 8_250_000

    await db.players.delete_one({"_id": result.inserted_id})
    await db.contracts.delete_many({"league_id": league_id})
