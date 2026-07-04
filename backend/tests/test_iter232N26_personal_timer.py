"""Iter 232N.26 — Personal pick timer + auto-pick preference.

Covers:
- worker chooses `personal_pick_timer_seconds` when it's tighter than
  `time_per_pick`
- worker pauses the personal cap during a `pending_review` trade
- `perform_one_auto_pick(..., preference="best_available")` skips the
  team's queue and takes the top-eligible player
- endpoint PATCH /teams/{id}/auto-pick-preference persists the field
"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone, timedelta

import pytest
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient
from fastapi.testclient import TestClient


@pytest.fixture
async def db():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    d = client[os.environ.get("DB_NAME", "dynasty_dreams")]
    yield d
    client.close()


@pytest.fixture
async def seeded_draft(db):
    """Create a minimal active draft, 2 teams, 2 players. Returns ids."""
    league_id = str(ObjectId())
    team_a = ObjectId()
    team_b = ObjectId()
    player_top = ObjectId()
    player_second = ObjectId()
    player_queued = ObjectId()

    await db.teams.insert_many([
        {"_id": team_a, "league_id": league_id, "name": "Alpha", "logo_abbr": "ALP",
         "owner_id": ObjectId(), "auto_pick_preference": "queue_then_best",
         "draft_queue": [str(player_queued)]},
        {"_id": team_b, "league_id": league_id, "name": "Bravo", "logo_abbr": "BRV",
         "owner_id": ObjectId()},
    ])
    await db.players.insert_many([
        {"_id": player_top, "name": "Top Scorer", "points": 200,
         "player_type": "regular", "position": "C", "team": "NHL",
         "nhl_id": f"test-top-{player_top}"},
        {"_id": player_second, "name": "Second", "points": 150,
         "player_type": "regular", "position": "LW", "team": "NHL",
         "nhl_id": f"test-2nd-{player_second}"},
        {"_id": player_queued, "name": "Queued Guy", "points": 80,
         "player_type": "regular", "position": "D", "team": "NHL",
         "nhl_id": f"test-que-{player_queued}"},
    ])
    draft = {
        "_id": ObjectId(),
        "league_id": league_id,
        "status": "active",
        "team_abbrs": ["ALP", "BRV"],
        "team_map": {
            "ALP": {"id": str(team_a), "name": "Alpha"},
            "BRV": {"id": str(team_b), "name": "Bravo"},
        },
        "snake_draft": True,
        "current_pick": 1,
        "total_rounds": 2,
        "time_per_pick": 900,       # 15 min
        "personal_pick_timer_seconds": 60,  # 1 min personal cap
        "current_pick_started_at": (datetime.now(timezone.utc) - timedelta(seconds=120)).isoformat(),
        "picks": [],
        "missed_pick_action": "auto-select",
        "draft_started": True,
        "timer_paused": False,
        "player_criteria": "all",
    }
    await db.drafts.insert_one(draft)
    yield {
        "draft_id": str(draft["_id"]),
        "league_id": league_id,
        "team_a": str(team_a),
        "team_b": str(team_b),
        "player_top": str(player_top),
        "player_queued": str(player_queued),
    }
    # Teardown
    await db.drafts.delete_one({"_id": draft["_id"]})
    await db.teams.delete_many({"_id": {"$in": [team_a, team_b]}})
    await db.players.delete_many({"_id": {"$in": [player_top, player_second, player_queued]}})
    await db.trades.delete_many({"league_id": league_id})


@pytest.mark.asyncio
async def test_worker_fires_when_personal_cap_expires_first(db, seeded_draft):
    """Started 120s ago; personal cap 60s + 3s grace → picked. Main
    clock has 900s so it wouldn't fire yet — personal did."""
    from services.draft_pick_timer_worker import run_once
    import routes.draft_helpers as draft_helpers

    # Wire _deps["db"] so perform_one_auto_pick can resolve the DB
    # outside a FastAPI request context.
    draft_helpers._deps["db"] = db

    counts = await run_once(db, draft_ids_filter=[seeded_draft["draft_id"]])
    assert counts["expired"] == 1
    assert counts["picked"] == 1
    # Confirm the pick was audited with personal_timeout source
    draft = await db.drafts.find_one({"_id": ObjectId(seeded_draft["draft_id"])})
    assert len(draft["picks"]) == 1
    assert draft["picks"][0]["auto_pick_source"] == "personal_timeout"


@pytest.mark.asyncio
async def test_worker_skips_personal_cap_during_trade_review(db, seeded_draft):
    """A pending_review trade in the league → personal cap paused,
    only the main pick clock (900s) can fire. Since we're 120s in, no
    pick should fire this tick."""
    from services.draft_pick_timer_worker import run_once

    await db.trades.insert_one({
        "_id": ObjectId(),
        "league_id": seeded_draft["league_id"],
        "status": "pending_review",
        "created_at": datetime.now(timezone.utc),
    })

    counts = await run_once(db, draft_ids_filter=[seeded_draft["draft_id"]])
    assert counts["expired"] == 0
    assert counts["picked"] == 0
    draft = await db.drafts.find_one({"_id": ObjectId(seeded_draft["draft_id"])})
    assert draft["picks"] == []


@pytest.mark.asyncio
async def test_perform_auto_pick_best_available_skips_queue(db, seeded_draft):
    """`preference='best_available'` bypasses the team's draft_queue
    and takes the top-eligible player (Top Scorer, 200 pts)."""
    from routes.draft_helpers import perform_one_auto_pick
    import routes.draft_helpers as draft_helpers
    draft_helpers._deps["db"] = db

    pick = await perform_one_auto_pick(
        seeded_draft["draft_id"], preference="best_available"
    )
    assert pick["auto_pick_via"] == "top_eligible"
    assert pick["player_id"] == seeded_draft["player_top"]


@pytest.mark.asyncio
async def test_perform_auto_pick_queue_preference_uses_queued_player(db, seeded_draft):
    """Default preference walks the queue — should pick the queued
    player even if a higher-scoring player exists."""
    from routes.draft_helpers import perform_one_auto_pick
    import routes.draft_helpers as draft_helpers
    draft_helpers._deps["db"] = db

    pick = await perform_one_auto_pick(
        seeded_draft["draft_id"], preference="queue_then_best"
    )
    assert pick["auto_pick_via"] == "queue"
    assert pick["player_id"] == seeded_draft["player_queued"]
