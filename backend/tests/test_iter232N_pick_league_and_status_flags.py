"""Iter 232N — Pick payload league label + player status flags.

Two-part fix:

(1) `build_pick_player_payload` in `routes/draft_helpers.py` — replaces
    the previously hardcoded `"league": "NHL"` string that made every
    prospect pick render as an "NHL" pick on the draft board. Now
    correctly emits the amateur league (WHL / OHL / KHL / …) for
    prospects and "NHL" for NHL players.

(2) `status_flags` on the eligible-players response — computed set of
    {injured, in_minors, unsigned, undrafted} so the
    frontend badge layer can render status symbols next to each name.
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

from routes.draft_helpers import build_pick_player_payload  # noqa: E402


@pytest.fixture()
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture()
async def db():
    client = AsyncIOMotorClient(os.environ.get("MONGO_URL"))
    db = client[os.environ.get("DB_NAME", os.environ["DB_NAME"])]
    yield db
    client.close()


# ─── (1) build_pick_player_payload ─────────────────────────────
def test_pick_payload_uses_nhl_league_for_nhl_players():
    payload = build_pick_player_payload({
        "_id": ObjectId(), "name": "NHL Guy", "position": "C",
        "team": "EDM", "player_type": "skater",
        "points": 100, "goals": 40, "assists": 60, "games_played": 82,
    })
    assert payload["league"] == "NHL"
    assert payload["player_type"] == "skater"


def test_pick_payload_uses_amateur_league_for_prospects():
    payload = build_pick_player_payload({
        "_id": ObjectId(), "name": "WHL Prospect", "position": "C",
        "team": "Medicine Hat", "player_type": "prospect",
        "amateur_league": "WHL",
    })
    assert payload["league"] == "WHL"
    assert payload["amateur_league"] == "WHL"
    assert payload["player_type"] == "prospect"


def test_pick_payload_falls_back_to_prospect_for_missing_amateur_league():
    payload = build_pick_player_payload({
        "_id": ObjectId(), "name": "Unlabeled Prospect", "position": "D",
        "player_type": "prospect",
    })
    # No amateur_league key set — payload emits the neutral "Prospect"
    # label rather than misclassifying as "NHL".
    assert payload["league"] == "Prospect"


# ─── (2) status_flags on eligible-players ──────────────────────
@pytest.mark.asyncio
async def test_eligible_players_status_flags(db):
    """End-to-end check: the /eligible-players endpoint stamps
    status_flags for injured, in_minors, unsigned, and undrafted
    on the correct rows."""
    from routes import draft_inspection
    from routes.draft_inspection import get_draft_eligible_players
    draft_inspection.setup({"db": db})

    league_id = str(ObjectId())
    draft_id = ObjectId()
    prev_draft_id = ObjectId()

    # Insert 4 prospects, each triggering a different flag.
    sfx = uuid.uuid4().hex[:8]
    injured = await db.players.insert_one({
        "name": f"Injured Pro {sfx}", "position": "C",
        "player_type": "prospect", "amateur_league": "OHL",
        "roster_status": "IR", "nhl_id": f"iter232N-{sfx}-1",
    })
    minors = await db.players.insert_one({
        "name": f"Minors Guy {sfx}", "position": "LW",
        "player_type": "prospect", "amateur_league": "AHL",
        "nhl_id": f"iter232N-{sfx}-2",
    })
    unsigned = await db.players.insert_one({
        "name": f"Unsigned Pro {sfx}", "position": "RW",
        "player_type": "prospect", "amateur_league": "USHL",
        "signed": False, "nhl_id": f"iter232N-{sfx}-3",
    })
    dropped = await db.players.insert_one({
        "name": f"Dropped Pro {sfx}", "position": "D",
        "player_type": "prospect", "amateur_league": "WHL",
        "nhl_id": f"iter232N-{sfx}-4",
    })
    dropped_pid = str(dropped.inserted_id)

    # A previous league draft that picked the "dropped" player. The
    # `undrafted` flag should now be False for this player (they WERE
    # previously drafted) even if they're not currently rostered.
    await db.drafts.insert_one({
        "_id": prev_draft_id, "league_id": league_id,
        "status": "completed",
        "picks": [{"player_id": dropped_pid, "player": {"id": dropped_pid}}],
    })
    # The current draft under test.
    await db.drafts.insert_one({
        "_id": draft_id, "league_id": league_id,
        "status": "active", "player_criteria": "prospects",
        "picks": [],
    })

    result = await get_draft_eligible_players(str(draft_id), search=sfx, limit=50)
    by_name = {p["name"]: p for p in result["players"]}
    assert f"Injured Pro {sfx}" in by_name
    assert by_name[f"Injured Pro {sfx}"]["status_flags"]["injured"] is True
    assert by_name[f"Minors Guy {sfx}"]["status_flags"]["in_minors"] is True
    assert by_name[f"Unsigned Pro {sfx}"]["status_flags"]["unsigned"] is True
    # Previously drafted → undrafted must be False.
    assert by_name[f"Dropped Pro {sfx}"]["status_flags"]["undrafted"] is False
    # Never drafted before → undrafted must be True. All three others
    # in this league had no prior pick, so they carry the undrafted flag.
    assert by_name[f"Injured Pro {sfx}"]["status_flags"]["undrafted"] is True
    assert by_name[f"Minors Guy {sfx}"]["status_flags"]["undrafted"] is True
    assert by_name[f"Unsigned Pro {sfx}"]["status_flags"]["undrafted"] is True

    # Cleanup
    await db.players.delete_many({"_id": {"$in": [
        injured.inserted_id, minors.inserted_id, unsigned.inserted_id, dropped.inserted_id,
    ]}})
    await db.drafts.delete_many({"_id": {"$in": [draft_id, prev_draft_id]}})


@pytest.mark.asyncio
async def test_previously_drafted_player_is_not_undrafted(db):
    """A player who was drafted in a prior league draft (regardless of
    current roster status) must NOT be flagged as `undrafted`."""
    from routes import draft_inspection
    from routes.draft_inspection import get_draft_eligible_players
    draft_inspection.setup({"db": db})

    league_id = str(ObjectId())
    draft_id = ObjectId()
    prev_draft_id = ObjectId()
    team_id = ObjectId()
    sfx = uuid.uuid4().hex[:8]
    rostered = await db.players.insert_one({
        "name": f"Still Rostered {sfx}", "position": "C",
        "player_type": "prospect", "amateur_league": "OHL",
        "nhl_id": f"iter232N-r-{sfx}",
    })
    pid = str(rostered.inserted_id)
    await db.drafts.insert_many([
        {"_id": prev_draft_id, "league_id": league_id, "status": "completed",
         "picks": [{"player_id": pid}]},
        {"_id": draft_id, "league_id": league_id, "status": "active",
         "player_criteria": "prospects", "picks": []},
    ])
    await db.teams.insert_one({
        "_id": team_id, "league_id": league_id, "name": "Rosterer",
        "players": [{"player_id": pid, "slot": "roster"}],
    })

    result = await get_draft_eligible_players(str(draft_id), search=sfx, limit=10)
    by_name = {p["name"]: p for p in result["players"]}
    assert by_name[f"Still Rostered {sfx}"]["status_flags"]["undrafted"] is False

    await db.players.delete_one({"_id": rostered.inserted_id})
    await db.drafts.delete_many({"_id": {"$in": [draft_id, prev_draft_id]}})
    await db.teams.delete_one({"_id": team_id})
