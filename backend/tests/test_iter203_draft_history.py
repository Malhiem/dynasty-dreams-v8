"""
Iter 203 — Draft History page backend invariants.

The Draft History page reads from `GET /api/drafts?league_id=...` and
client-side filters to `status='completed'`. These tests pin down the
two invariants the UI depends on:

1. The endpoint returns ALL drafts for a league (active + completed +
   anything else), and each row carries `status` so the frontend can
   filter.
2. `make_draft_pick` flips `status` from `active` → `completed` exactly
   when the final overall pick is recorded.

Implementation reference:
  /app/backend/routes/drafts.py
    - get_drafts (~line 896)
    - make_draft_pick (~line 1134) — `new_status = "completed" if next_pick > total_picks else "active"`
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest
from bson import ObjectId
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")


def _db():
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


@pytest.mark.asyncio
async def test_get_drafts_filters_by_league_and_surfaces_status():
    """`GET /api/drafts?league_id=...` returns every draft for the
    league, each carrying a `status` field the Draft History page
    can filter on. We test via the underlying helper directly so the
    test stays hermetic + doesn't depend on auth wiring."""
    from routes.drafts import setup as drafts_setup, get_drafts

    # Wire deps so the route helpers can read `_db`.
    drafts_setup({
        "db": _db(),
        "logger": None,
        "get_current_user": None,
        "broadcast_to_room": None,
        "create_notification": None,
    })

    lid = f"test_iter203_history_{ObjectId()}"
    # Seed 3 drafts: 2 completed, 1 active.
    base = {
        "league_id": lid,
        "team_abbrs": ["AAA", "BBB"],
        "team_map": {"AAA": {"id": "t1"}, "BBB": {"id": "t2"}},
        "total_rounds": 2,
        "snake_draft": True,
        "picks": [],
        "current_pick": 1,
    }
    d1 = await _db().drafts.insert_one({**base, "status": "completed", "created_at": "2026-01-01T00:00:00Z"})
    d2 = await _db().drafts.insert_one({**base, "status": "completed", "created_at": "2026-02-01T00:00:00Z"})
    d3 = await _db().drafts.insert_one({**base, "status": "active", "created_at": "2026-02-15T00:00:00Z"})

    rows = await get_drafts(league_id=lid)
    try:
        assert isinstance(rows, list)
        assert len(rows) == 3
        # All rows surface the `status` field
        assert all("status" in r for r in rows)
        completed = [r for r in rows if r["status"] == "completed"]
        active = [r for r in rows if r["status"] == "active"]
        assert len(completed) == 2
        assert len(active) == 1
        # Sorted desc by created_at — Feb 15 active should be first
        assert str(rows[0]["_id"]) == str(d3.inserted_id)
    finally:
        await _db().drafts.delete_many({"league_id": lid})


@pytest.mark.asyncio
async def test_make_draft_pick_flips_status_to_completed_on_final_pick():
    """The make_draft_pick endpoint must set `status='completed'` when
    the recorded pick is the FINAL pick (overall == total_rounds * teams).
    This is what powers the Draft History page's `status==completed`
    filter."""
    from routes.drafts import setup as drafts_setup, make_draft_pick

    # 2 teams × 1 round = 2 total picks. Seed at current_pick=2 with 1
    # pick already in, so the next pick is the final.
    league_id = str(ObjectId())
    team_id = str(ObjectId())
    team2_id = str(ObjectId())
    player_id = str(ObjectId())

    # Seed minimal player + team + league
    await _db().players.insert_one({
        "_id": ObjectId(player_id),
        "name": "Test Player",
        "position": "C",
        "team": "NHL",
    })
    await _db().teams.insert_one({
        "_id": ObjectId(team_id),
        "league_id": league_id,
        "owner_id": "test_user_iter203",
        "name": "Team Alpha",
        "roster": [],
    })
    await _db().teams.insert_one({
        "_id": ObjectId(team2_id),
        "league_id": league_id,
        "owner_id": "other_user",
        "name": "Team Bravo",
        "roster": [],
    })
    await _db().leagues.insert_one({
        "_id": ObjectId(league_id),
        "name": "Iter203 Test League",
        "commissioner_id": "test_user_iter203",
    })
    draft_doc = {
        "league_id": league_id,
        "status": "active",
        "team_abbrs": ["ALP", "BRV"],
        "team_map": {
            "ALP": {"id": team_id, "name": "Team Alpha"},
            "BRV": {"id": team2_id, "name": "Team Bravo"},
        },
        "total_rounds": 1,
        "snake_draft": False,
        "current_pick": 2,  # final pick of a 2-team × 1-round draft
        "picks": [{
            "round": 1, "pick_in_round": 1, "overall": 1, "team": "ALP",
            "team_id": team_id, "player_id": "prev_player", "player": {},
            "picked_by": "test_user_iter203",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }],
    }
    result = await _db().drafts.insert_one(draft_doc)
    draft_id = str(result.inserted_id)

    # Stub deps
    broadcast_calls = []

    async def _stub_broadcast(*args, **kwargs):
        broadcast_calls.append((args, kwargs))

    async def _stub_user(_request):
        return {"_id": "other_user", "id": "other_user", "email": "x@y.z"}

    drafts_setup({
        "db": _db(),
        "logger": None,
        "get_current_user": _stub_user,
        "broadcast_to_room": _stub_broadcast,
        "create_notification": None,
    })

    # Build a Pydantic request model
    from routes.drafts import MakeDraftPickRequest

    class _FakeRequest:
        pass

    try:
        await make_draft_pick(
            draft_id,
            MakeDraftPickRequest(player_id=player_id),
            _FakeRequest(),
        )
        # Assert the draft flipped to completed
        d = await _db().drafts.find_one({"_id": ObjectId(draft_id)})
        assert d["status"] == "completed", f"Expected completed, got {d['status']}"
        assert d["current_pick"] == 3  # n+1
        assert len(d["picks"]) == 2
        # Final broadcast was the draft_completed event
        event_names = [call[0][1] for call in broadcast_calls]
        assert "draft_completed" in event_names
    finally:
        await _db().drafts.delete_one({"_id": ObjectId(draft_id)})
        await _db().teams.delete_many({"league_id": league_id})
        await _db().leagues.delete_one({"_id": ObjectId(league_id)})
        await _db().players.delete_one({"_id": ObjectId(player_id)})
