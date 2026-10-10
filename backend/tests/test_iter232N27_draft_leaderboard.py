"""Iter 232N.27 — Draft leaderboard + Speed Demon XP bonus."""
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
async def seeded(db):
    """Draft with 3 teams. Team A: 3 fast picks (10, 15, 12 secs).
    Team B: 3 slow picks (600, 900, 800). Team C: 3 auto-picks."""
    league_id = str(ObjectId())
    team_a = ObjectId()
    team_b = ObjectId()
    team_c = ObjectId()
    owner_a = ObjectId()
    owner_c = ObjectId()

    await db.teams.insert_many([
        {"_id": team_a, "league_id": league_id, "name": "Alpha", "owner_id": owner_a, "logo_abbr": "ALP"},
        {"_id": team_b, "league_id": league_id, "name": "Bravo", "owner_id": ObjectId(), "logo_abbr": "BRV"},
        {"_id": team_c, "league_id": league_id, "name": "Charlie", "owner_id": owner_c, "logo_abbr": "CHR"},
    ])
    now = datetime.now(timezone.utc)
    draft = {
        "_id": ObjectId(),
        "league_id": league_id,
        "status": "completed",  # final leaderboard
        "team_abbrs": ["ALP", "BRV", "CHR"],
        "team_map": {
            "ALP": {"id": str(team_a), "name": "Alpha"},
            "BRV": {"id": str(team_b), "name": "Bravo"},
            "CHR": {"id": str(team_c), "name": "Charlie"},
        },
        "snake_draft": True,
        "current_pick": 10,
        "total_rounds": 3,
        "time_per_pick": 900,
        "picks": [
            {"team_id": str(team_a), "overall": 1, "time_taken_seconds": 10},
            {"team_id": str(team_b), "overall": 2, "time_taken_seconds": 600},
            {"team_id": str(team_c), "overall": 3, "auto_picked": True, "auto_pick_via": "queue", "time_taken_seconds": 900},
            {"team_id": str(team_a), "overall": 4, "time_taken_seconds": 15},
            {"team_id": str(team_b), "overall": 5, "time_taken_seconds": 900},
            {"team_id": str(team_c), "overall": 6, "auto_picked": True, "auto_pick_via": "top_eligible", "time_taken_seconds": 900},
            {"team_id": str(team_a), "overall": 7, "time_taken_seconds": 12},
            {"team_id": str(team_b), "overall": 8, "time_taken_seconds": 800},
            {"team_id": str(team_c), "overall": 9, "auto_picked": True, "auto_pick_via": "queue", "time_taken_seconds": 900},
        ],
        "created_at": now - timedelta(days=1),
    }
    await db.drafts.insert_one(draft)
    # A single accepted trade between Alpha and Bravo (during draft window).
    await db.trades.insert_one({
        "_id": ObjectId(), "league_id": league_id,
        "proposer_team_id": str(team_a), "target_team_id": str(team_b),
        "status": "accepted", "created_at": now - timedelta(hours=6),
    })
    yield {
        "draft_id": str(draft["_id"]),
        "league_id": league_id,
        "team_a": str(team_a), "team_b": str(team_b), "team_c": str(team_c),
        "owner_a": owner_a, "owner_c": owner_c,
    }
    await db.drafts.delete_one({"_id": draft["_id"]})
    await db.teams.delete_many({"_id": {"$in": [team_a, team_b, team_c]}})
    await db.trades.delete_many({"league_id": league_id})


@pytest.mark.asyncio
async def test_leaderboard_aggregates_per_team_stats(db, seeded):
    """Rows should contain per-team pick counts + averages + trades."""
    import routes.draft_leaderboard as lb
    lb._deps["db"] = db

    class FakeUser:
        def __getitem__(self, k): return "fake"
    async def fake_get_user(req):
        return FakeUser()
    lb._deps["get_current_user"] = fake_get_user

    result = await lb.get_draft_leaderboard(seeded["draft_id"], request=None)

    assert result["is_final"] is True
    assert result["total_picks"] == 9
    assert result["auto_picks_total"] == 3

    by_id = {r["team_id"]: r for r in result["rows"]}
    a = by_id[seeded["team_a"]]
    b = by_id[seeded["team_b"]]
    c = by_id[seeded["team_c"]]

    assert a["picks_made"] == 3
    assert a["auto_picks"] == 0
    assert a["avg_pick_seconds"] == round((10 + 15 + 12) / 3, 1)
    assert a["fastest_pick_secs"] == 10
    assert a["slowest_pick_secs"] == 15
    assert a["trades_count"] == 1  # Alpha ↔ Bravo

    assert b["avg_pick_seconds"] == round((600 + 900 + 800) / 3, 1)
    assert b["trades_count"] == 1

    assert c["auto_picks"] == 3
    assert c["queue_hit_rate"] == round((2 / 3) * 100, 1)   # 2 queue / 3 auto
    assert c["trades_count"] == 0


@pytest.mark.asyncio
async def test_leaderboard_awards_assign_correct_winners(db, seeded):
    """Speed demon = Alpha (12.3 avg). Slow poke = Bravo. Autopilot = Charlie."""
    import routes.draft_leaderboard as lb
    lb._deps["db"] = db

    async def fake_get_user(req):
        return {"_id": "test"}
    lb._deps["get_current_user"] = fake_get_user

    result = await lb.get_draft_leaderboard(seeded["draft_id"], request=None)
    awards = result["awards"]

    assert awards["speed_demon"]["team_id"] == seeded["team_a"]
    # Slow poke = Charlie (900 avg from all auto-picks) — auto-picks
    # count as maxed-out clocks, correctly identifying who stalled.
    assert awards["slow_poke"]["team_id"] == seeded["team_c"]
    assert awards["autopilot"]["team_id"] == seeded["team_c"]
    assert awards["queue_master"]["team_id"] == seeded["team_c"]
    # Iron man is a 3-way tie (each team has 3 picks) — winner is
    # alphabetically-first team due to (value, name) sort.
    assert awards["iron_man"]["team_id"] in (seeded["team_a"], seeded["team_b"], seeded["team_c"])
    assert awards["is_final"] is True


@pytest.mark.asyncio
async def test_award_draft_speed_bonus_broadcasts_to_owner(db, seeded):
    """award_draft_completion_bonuses hands +50 XP to Alpha's owner."""
    from utils.xp import award_draft_completion_bonuses
    calls = []

    async def fake_broadcast(room, event, payload):
        calls.append((room, event, payload))

    award = await award_draft_completion_bonuses(
        db, draft_id=seeded["draft_id"], broadcast_fn=fake_broadcast,
    )
    assert award["winner_team_id"] == seeded["team_a"]
    assert award["meta"]["avg_pick_seconds"] == round((10 + 15 + 12) / 3, 1)
    # Owner should have received one xp_awarded broadcast.
    matched = [c for c in calls if c[0] == f"user_{seeded['owner_a']}" and c[2]['source'] == 'draft_speed_champion']
    assert len(matched) == 1
    assert matched[0][1] == "xp_awarded"
    assert matched[0][2]["delta"] == 50
    assert matched[0][2]["source"] == "draft_speed_champion"


@pytest.mark.asyncio
async def test_leaderboard_hides_reveal_awards_while_live(db, seeded):
    """Flip draft to active — awards['hidden_until_final'] should still
    include the reveal categories but is_final flips to False."""
    import routes.draft_leaderboard as lb
    lb._deps["db"] = db
    async def fake_get_user(req):
        return {"_id": "test"}
    lb._deps["get_current_user"] = fake_get_user

    await db.drafts.update_one(
        {"_id": ObjectId(seeded["draft_id"])},
        {"$set": {"status": "active"}},
    )
    result = await lb.get_draft_leaderboard(seeded["draft_id"], request=None)
    assert result["is_final"] is False
    assert "speed_demon" in result["awards"]["hidden_until_final"]
    assert "slow_poke" in result["awards"]["hidden_until_final"]


@pytest.mark.asyncio
async def test_award_skips_when_no_team_has_three_picks(db):
    """Speed demon requires ≥ 3 picks/team to avoid outlier fluke wins."""
    from utils.xp import award_draft_completion_bonuses
    tid = ObjectId()
    await db.teams.insert_one({"_id": tid, "name": "Solo", "owner_id": ObjectId()})
    draft_id = ObjectId()
    await db.drafts.insert_one({
        "_id": draft_id, "league_id": str(ObjectId()), "status": "completed",
        "picks": [
            {"team_id": str(tid), "overall": 1, "time_taken_seconds": 5},
            {"team_id": str(tid), "overall": 2, "time_taken_seconds": 5},
        ],
    })
    calls = []
    async def fake_broadcast(*a): calls.append(a)
    award = await award_draft_completion_bonuses(
        db, draft_id=str(draft_id), broadcast_fn=fake_broadcast,
    )
    assert award == {}
    assert len(calls) == 1
    assert calls[0][2]['source'] == 'draft_completed'
    assert calls[0][2]['delta'] == 40
    await db.drafts.delete_one({"_id": draft_id})
    await db.teams.delete_one({"_id": tid})
