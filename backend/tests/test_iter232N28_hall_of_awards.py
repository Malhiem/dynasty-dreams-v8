"""Iter 232N.28 — Draft Hall of Awards (Trophy Room league endpoint)."""
from __future__ import annotations

import os
from datetime import datetime, timezone, timedelta

import pytest
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient


@pytest.fixture
async def db():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    d = client[os.environ.get("DB_NAME", "dynasty_dreams")]
    yield d
    client.close()


@pytest.fixture
async def seeded_league_hall(db):
    """Seed a league with TWO completed drafts + one active (excluded)."""
    league_id = str(ObjectId())
    team_a = ObjectId()
    team_b = ObjectId()
    await db.teams.insert_many([
        {"_id": team_a, "league_id": league_id, "name": "Alpha", "logo_abbr": "ALP", "owner_id": ObjectId()},
        {"_id": team_b, "league_id": league_id, "name": "Bravo", "logo_abbr": "BRV", "owner_id": ObjectId()},
    ])
    now = datetime.now(timezone.utc)
    completed_2025 = {
        "_id": ObjectId(),
        "league_id": league_id, "status": "completed",
        "name": "2025 Rookie Draft",
        "completed_at": (now - timedelta(days=365)),
        "team_abbrs": ["ALP", "BRV"],
        "team_map": {
            "ALP": {"id": str(team_a), "name": "Alpha"},
            "BRV": {"id": str(team_b), "name": "Bravo"},
        },
        "picks": [
            {"team_id": str(team_a), "overall": 1, "time_taken_seconds": 5},
            {"team_id": str(team_b), "overall": 2, "time_taken_seconds": 600},
            {"team_id": str(team_a), "overall": 3, "time_taken_seconds": 10},
            {"team_id": str(team_b), "overall": 4, "time_taken_seconds": 700},
            {"team_id": str(team_a), "overall": 5, "time_taken_seconds": 8},
            {"team_id": str(team_b), "overall": 6, "time_taken_seconds": 800, "auto_picked": True, "auto_pick_via": "queue"},
        ],
    }
    completed_2024 = {
        "_id": ObjectId(),
        "league_id": league_id, "status": "completed",
        "name": "2024 Startup Draft",
        "completed_at": (now - timedelta(days=730)),
        "team_abbrs": ["ALP", "BRV"],
        "team_map": completed_2025["team_map"],
        "picks": [
            {"team_id": str(team_b), "overall": 1, "time_taken_seconds": 3},
            {"team_id": str(team_a), "overall": 2, "time_taken_seconds": 200},
            {"team_id": str(team_b), "overall": 3, "time_taken_seconds": 5},
            {"team_id": str(team_a), "overall": 4, "time_taken_seconds": 250},
            {"team_id": str(team_b), "overall": 5, "time_taken_seconds": 7},
        ],
    }
    active_draft = {
        "_id": ObjectId(),
        "league_id": league_id, "status": "active",
        "name": "2026 In-Season",
        "team_abbrs": ["ALP", "BRV"],
        "team_map": completed_2025["team_map"],
        "picks": [{"team_id": str(team_a), "overall": 1, "time_taken_seconds": 3}],
    }
    await db.drafts.insert_many([completed_2025, completed_2024, active_draft])
    yield {
        "league_id": league_id,
        "team_a": str(team_a), "team_b": str(team_b),
        "completed_ids": [str(completed_2025["_id"]), str(completed_2024["_id"])],
        "active_id": str(active_draft["_id"]),
    }
    await db.drafts.delete_many({"league_id": league_id})
    await db.teams.delete_many({"_id": {"$in": [team_a, team_b]}})


@pytest.mark.asyncio
async def test_hall_of_awards_returns_only_completed_drafts(db, seeded_league_hall):
    """Active drafts are excluded, both completed drafts show up."""
    import routes.draft_leaderboard as lb
    lb._deps["db"] = db
    async def fake_user(req): return {"_id": "t"}
    lb._deps["get_current_user"] = fake_user

    result = await lb.get_league_draft_hall_of_awards(
        seeded_league_hall["league_id"], request=None
    )
    assert result["league_id"] == seeded_league_hall["league_id"]
    drafts = result["drafts"]
    assert len(drafts) == 2
    # Sorted by completed_at DESC — 2025 first
    assert drafts[0]["name"] == "2025 Rookie Draft"
    assert drafts[0]["year"] == 2025
    assert drafts[1]["name"] == "2024 Startup Draft"
    assert drafts[1]["year"] == 2024
    for e in drafts:
        assert e["draft_id"]
        assert isinstance(e["total_picks"], int) and e["total_picks"] > 0
        # Speed demon / slow poke / etc are all resolvable because
        # both teams have ≥ 3 picks in each draft.
        assert e["awards"]["speed_demon"] is not None
        assert e["awards"]["speed_demon"]["team_name"] in ("Alpha", "Bravo")


@pytest.mark.asyncio
async def test_hall_of_awards_empty_league_returns_empty_list(db):
    """Leagues with no completed drafts return `drafts: []`."""
    import routes.draft_leaderboard as lb
    lb._deps["db"] = db
    async def fake_user(req): return {"_id": "t"}
    lb._deps["get_current_user"] = fake_user

    result = await lb.get_league_draft_hall_of_awards(
        str(ObjectId()), request=None
    )
    assert result["drafts"] == []


@pytest.mark.asyncio
async def test_hall_of_awards_award_winner_shape(db, seeded_league_hall):
    """Each award entry has {team_id, team_name, logo_abbr, value}."""
    import routes.draft_leaderboard as lb
    lb._deps["db"] = db
    async def fake_user(req): return {"_id": "t"}
    lb._deps["get_current_user"] = fake_user

    result = await lb.get_league_draft_hall_of_awards(
        seeded_league_hall["league_id"], request=None
    )
    first = result["drafts"][0]
    speed = first["awards"]["speed_demon"]
    assert set(speed.keys()) == {"team_id", "team_name", "logo_abbr", "value"}
    # 2025: Alpha avg = (5+10+8)/3 = 7.67, Bravo avg = (600+700+800)/3 = 700
    # So Alpha = speed_demon
    assert speed["team_name"] == "Alpha"
    slow = first["awards"]["slow_poke"]
    assert slow["team_name"] == "Bravo"
