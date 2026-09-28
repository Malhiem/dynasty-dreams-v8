"""Comprehensive acceptance tests for the game-level scoring allocation engine.

Tests all 5 user-reported scenarios:
  1. Trade: 10/6 goal split (Team A → Team B)
  2. Drop + reacquisition: unowned gap excludes stats
  3. Lineup change: bench-period stats excluded
  4. Late import / correction: goes to original owner at game time
  5. Recomputation: produces identical, idempotent results

Also tests:
  6. Roto stat allocation follows the same ownership rules
  7. Backfill engine produces correct ownership periods from evidence
  8. Fallback path flags results as uncertain when no ownership data exists
  9. Known unowned interval awards no stats (distinct from missing history)

Run: cd /app/backend && python -m pytest tests/test_game_allocation.py -v
"""
import asyncio
import os
import sys
from datetime import datetime, timezone, timedelta

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")


@pytest_asyncio.fixture
async def db():
    """Create an isolated test database for each test."""
    db_name = f"test_alloc_{ObjectId()}"
    client = AsyncIOMotorClient(MONGO_URL)
    database = client[db_name]
    yield database
    await client.drop_database(db_name)
    client.close()


@pytest_asyncio.fixture
async def setup_trade_scenario(db):
    """Seed the 10/6 goal split scenario:

    - Player scores 10 goals (games 1-5, Jan 5-9) while on Team A.
    - Player is traded to Team B on Jan 10.
    - Player scores 6 goals (games 6-8, Jan 10-11) while on Team B.
    - Ownership periods and lineup periods are properly seeded.
    """
    league_id = str(ObjectId())
    team_a_id = str(ObjectId())
    team_b_id = str(ObjectId())
    player_id = str(ObjectId())
    season_start = datetime(2026, 1, 5, tzinfo=timezone.utc)
    trade_time = datetime(2026, 1, 10, 0, 0, 0, tzinfo=timezone.utc)
    period_start = datetime(2026, 1, 5, tzinfo=timezone.utc)
    period_end = datetime(2026, 1, 12, tzinfo=timezone.utc)

    await db.leagues.insert_one({
        "_id": ObjectId(league_id), "name": "Test League",
        "current_week": 2, "season_start_date": "2026-01-05",
        "matchup_length_days": 7,
        "ownership_backfilled_at": datetime.now(timezone.utc),
    })
    await db.teams.insert_one({
        "_id": ObjectId(team_a_id), "name": "Team A",
        "league_id": league_id, "roster": [],
        "owner_name": "Owner A", "owner_id": "ownerA",
    })
    await db.teams.insert_one({
        "_id": ObjectId(team_b_id), "name": "Team B",
        "league_id": league_id, "roster": [player_id],
        "owner_name": "Owner B", "owner_id": "ownerB",
    })
    await db.players.insert_one({
        "_id": ObjectId(player_id), "name": "Test Player",
        "position": "C", "player_type": "skater", "team": "TST",
        "goals": 16, "assists": 8, "live_stats": {},
    })

    # Ownership: A owns from season start until trade, B owns after
    await db.player_ownership_periods.insert_many([
        {"player_id": player_id, "team_id": team_a_id, "league_id": league_id,
         "acquired_at": season_start, "released_at": trade_time,
         "source": "draft", "release_source": "trade"},
        {"player_id": player_id, "team_id": team_b_id, "league_id": league_id,
         "acquired_at": trade_time, "released_at": None,
         "source": "trade", "release_source": None},
    ])

    # Lineup: active on both teams during their ownership
    await db.lineup_status_periods.insert_many([
        {"player_id": player_id, "team_id": team_a_id, "league_id": league_id,
         "position": "forward", "started_at": season_start, "ended_at": trade_time},
        {"player_id": player_id, "team_id": team_b_id, "league_id": league_id,
         "position": "forward", "started_at": trade_time, "ended_at": None},
    ])

    # Games: 5 before trade (Jan 5-9), 3 after (2 on Jan 10, 1 on Jan 11)
    all_dates = ["2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08",
                 "2026-01-09", "2026-01-10", "2026-01-10", "2026-01-11"]
    live_stats = {}
    for i, d in enumerate(all_dates):
        gid = 2026020100 + i
        await db.games.insert_one({"nhl_game_id": gid, "date": d})
        live_stats[str(gid)] = {
            "goals": 2, "assists": 1, "shots": 3,
            "plus_minus": 1, "penalty_minutes": 0,
            "power_play_goals": 0, "power_play_points": 0,
            "short_handed_goals": 0, "short_handed_points": 0,
            "game_winning_goals": 0, "updated_at": d + "T03:00:00",
        }
    await db.players.update_one(
        {"_id": ObjectId(player_id)}, {"$set": {"live_stats": live_stats}},
    )

    from utils.scoring_roster import ensure_indexes
    await ensure_indexes(db)

    return {
        "league_id": league_id,
        "team_a_id": team_a_id,
        "team_b_id": team_b_id,
        "player_id": player_id,
        "season_start": season_start,
        "trade_time": trade_time,
        "period_start": period_start,
        "period_end": period_end,
    }


# ══════════════════════════════════════════════════════════════════
# Test 1: Trade — 10/6 goal split
# ══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_trade_goal_split(db, setup_trade_scenario):
    """Stats before trade stay with Team A, stats after go to Team B."""
    s = setup_trade_scenario
    from utils.game_allocation import allocate_team_period_fpts

    alloc_a = await allocate_team_period_fpts(
        db, s["team_a_id"], s["league_id"],
        s["period_start"], s["period_end"], None,
    )
    alloc_b = await allocate_team_period_fpts(
        db, s["team_b_id"], s["league_id"],
        s["period_start"], s["period_end"], None,
    )

    assert alloc_a["game_count"] == 5, f"Team A should have 5 games, got {alloc_a['game_count']}"
    assert alloc_b["game_count"] == 3, f"Team B should have 3 games, got {alloc_b['game_count']}"
    assert alloc_a["total_fpts"] > 0, "Team A should have positive fpts"
    assert alloc_b["total_fpts"] > 0, "Team B should have positive fpts"
    # 5:3 ratio
    ratio = alloc_a["total_fpts"] / alloc_b["total_fpts"]
    assert abs(ratio - 5 / 3) < 0.01, f"Expected 5:3 ratio, got {ratio:.3f}"


# ══════════════════════════════════════════════════════════════════
# Test 2: Drop + Reacquisition — unowned gap
# ══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_drop_reacquisition_unowned_gap(db, setup_trade_scenario):
    """Stats earned during an unowned interval are not credited to anyone."""
    s = setup_trade_scenario

    # Modify scenario: Team B drops the player on Jan 11, player is unowned
    drop_time = datetime(2026, 1, 11, 0, 0, 0, tzinfo=timezone.utc)
    await db.player_ownership_periods.update_one(
        {"player_id": s["player_id"], "team_id": s["team_b_id"],
         "league_id": s["league_id"]},
        {"$set": {"released_at": drop_time, "release_source": "drop"}},
    )

    from utils.game_allocation import allocate_team_period_fpts

    alloc_b = await allocate_team_period_fpts(
        db, s["team_b_id"], s["league_id"],
        s["period_start"], s["period_end"], None,
    )

    # Team B owned Jan 10 → Jan 11. Games on Jan 10 (2 games) count.
    # Game on Jan 11: acquired_at(Jan 10 00:00) <= Jan 11 00:00 BUT
    # released_at(Jan 11 00:00) > Jan 11 00:00 is FALSE. So NOT owned.
    assert alloc_b["game_count"] == 2, \
        f"Team B should have 2 games (Jan 10 only), got {alloc_b['game_count']}"


@pytest.mark.asyncio
async def test_drop_preserves_earlier_earnings(db, setup_trade_scenario):
    """Dropping a player does not remove previously earned stats."""
    s = setup_trade_scenario

    from utils.game_allocation import allocate_team_period_fpts

    # Get Team A's allocation (player was already traded away)
    alloc_a_before = await allocate_team_period_fpts(
        db, s["team_a_id"], s["league_id"],
        s["period_start"], s["period_end"], None,
    )

    # Now Team B drops the player
    drop_time = datetime(2026, 1, 11, 0, 0, 0, tzinfo=timezone.utc)
    await db.player_ownership_periods.update_one(
        {"player_id": s["player_id"], "team_id": s["team_b_id"],
         "league_id": s["league_id"]},
        {"$set": {"released_at": drop_time, "release_source": "drop"}},
    )

    # Team A's allocation should be UNCHANGED after Team B drops
    alloc_a_after = await allocate_team_period_fpts(
        db, s["team_a_id"], s["league_id"],
        s["period_start"], s["period_end"], None,
    )
    assert alloc_a_before["total_fpts"] == alloc_a_after["total_fpts"], \
        "Team A's stats must not change when Team B drops the player"
    assert alloc_a_before["game_count"] == alloc_a_after["game_count"]


@pytest.mark.asyncio
async def test_reacquisition_excludes_unowned_stats(db, setup_trade_scenario):
    """Reacquiring a player does not credit stats earned while unowned."""
    s = setup_trade_scenario
    team_c_id = str(ObjectId())

    # Create Team C
    await db.teams.insert_one({
        "_id": ObjectId(team_c_id), "name": "Team C",
        "league_id": s["league_id"], "roster": [s["player_id"]],
    })

    # Scenario: Team B drops on Jan 11, Team C picks up on Jan 11 12:00
    drop_time = datetime(2026, 1, 11, 0, 0, 0, tzinfo=timezone.utc)
    pickup_time = datetime(2026, 1, 11, 12, 0, 0, tzinfo=timezone.utc)

    await db.player_ownership_periods.update_one(
        {"player_id": s["player_id"], "team_id": s["team_b_id"],
         "league_id": s["league_id"]},
        {"$set": {"released_at": drop_time, "release_source": "drop"}},
    )
    await db.player_ownership_periods.insert_one({
        "player_id": s["player_id"], "team_id": team_c_id,
        "league_id": s["league_id"],
        "acquired_at": pickup_time, "released_at": None,
        "source": "add", "release_source": None,
    })
    await db.lineup_status_periods.insert_one({
        "player_id": s["player_id"], "team_id": team_c_id,
        "league_id": s["league_id"],
        "position": "forward", "started_at": pickup_time, "ended_at": None,
    })

    from utils.game_allocation import allocate_team_period_fpts

    alloc_c = await allocate_team_period_fpts(
        db, team_c_id, s["league_id"],
        s["period_start"], s["period_end"], None,
    )

    # Team C acquired at Jan 11 12:00. The Jan 11 game was at midnight.
    # acquired_at(12:00) <= Jan 11 00:00 is FALSE. So Team C gets 0 games.
    assert alloc_c["game_count"] == 0, \
        f"Team C should have 0 games (acquired after Jan 11 game), got {alloc_c['game_count']}"


# ══════════════════════════════════════════════════════════════════
# Test 3: Lineup change — bench-period exclusion
# ══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_bench_period_excludes_stats(db, setup_trade_scenario):
    """Stats earned while the player is benched are not counted."""
    s = setup_trade_scenario

    # Modify Team A's lineup: bench from Jan 7-9
    bench_start = datetime(2026, 1, 7, 0, 0, 0, tzinfo=timezone.utc)
    bench_end = datetime(2026, 1, 9, 0, 0, 0, tzinfo=timezone.utc)

    await db.lineup_status_periods.delete_many({
        "player_id": s["player_id"], "team_id": s["team_a_id"],
        "league_id": s["league_id"],
    })
    await db.lineup_status_periods.insert_many([
        {"player_id": s["player_id"], "team_id": s["team_a_id"],
         "league_id": s["league_id"],
         "position": "forward", "started_at": s["season_start"],
         "ended_at": bench_start},
        {"player_id": s["player_id"], "team_id": s["team_a_id"],
         "league_id": s["league_id"],
         "position": "bench", "started_at": bench_start,
         "ended_at": bench_end},
        {"player_id": s["player_id"], "team_id": s["team_a_id"],
         "league_id": s["league_id"],
         "position": "forward", "started_at": bench_end,
         "ended_at": s["trade_time"]},
    ])

    from utils.game_allocation import allocate_team_period_fpts

    alloc_a = await allocate_team_period_fpts(
        db, s["team_a_id"], s["league_id"],
        s["period_start"], s["period_end"], None,
    )

    # Active: Jan 5, 6, 9 (3 games). Benched: Jan 7, 8 (2 games excluded).
    assert alloc_a["game_count"] == 3, \
        f"Team A should have 3 eligible games (Jan 5,6,9), got {alloc_a['game_count']}"


@pytest.mark.asyncio
async def test_ir_period_excludes_stats(db, setup_trade_scenario):
    """Stats earned while the player is on IR are not counted."""
    s = setup_trade_scenario

    # Put player on IR for Jan 6-8
    ir_start = datetime(2026, 1, 6, 0, 0, 0, tzinfo=timezone.utc)
    ir_end = datetime(2026, 1, 8, 0, 0, 0, tzinfo=timezone.utc)

    await db.lineup_status_periods.delete_many({
        "player_id": s["player_id"], "team_id": s["team_a_id"],
        "league_id": s["league_id"],
    })
    await db.lineup_status_periods.insert_many([
        {"player_id": s["player_id"], "team_id": s["team_a_id"],
         "league_id": s["league_id"],
         "position": "forward", "started_at": s["season_start"],
         "ended_at": ir_start},
        {"player_id": s["player_id"], "team_id": s["team_a_id"],
         "league_id": s["league_id"],
         "position": "ir", "started_at": ir_start,
         "ended_at": ir_end},
        {"player_id": s["player_id"], "team_id": s["team_a_id"],
         "league_id": s["league_id"],
         "position": "forward", "started_at": ir_end,
         "ended_at": s["trade_time"]},
    ])

    from utils.game_allocation import allocate_team_period_fpts

    alloc_a = await allocate_team_period_fpts(
        db, s["team_a_id"], s["league_id"],
        s["period_start"], s["period_end"], None,
    )

    # Active: Jan 5 (1), Jan 8 (1), Jan 9 (1) = 3 games
    # IR: Jan 6, 7 = excluded
    assert alloc_a["game_count"] == 3, \
        f"Team A should have 3 games (IR excludes Jan 6-7), got {alloc_a['game_count']}"


# ══════════════════════════════════════════════════════════════════
# Test 4: Late import / correction — goes to original owner
# ══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_correction_applies_to_original_owner(db, setup_trade_scenario):
    """A stat correction for a pre-trade game changes Team A, not Team B."""
    s = setup_trade_scenario
    from utils.game_allocation import allocate_team_period_fpts

    alloc_a_before = await allocate_team_period_fpts(
        db, s["team_a_id"], s["league_id"],
        s["period_start"], s["period_end"], None,
    )
    alloc_b_before = await allocate_team_period_fpts(
        db, s["team_b_id"], s["league_id"],
        s["period_start"], s["period_end"], None,
    )

    # Correct game 2 (Jan 6, gid=2026020101): 2G → 5G
    player = await db.players.find_one({"_id": ObjectId(s["player_id"])})
    ls = player["live_stats"]
    ls["2026020101"]["goals"] = 5
    await db.players.update_one(
        {"_id": ObjectId(s["player_id"])}, {"$set": {"live_stats": ls}},
    )

    alloc_a_after = await allocate_team_period_fpts(
        db, s["team_a_id"], s["league_id"],
        s["period_start"], s["period_end"], None,
    )
    alloc_b_after = await allocate_team_period_fpts(
        db, s["team_b_id"], s["league_id"],
        s["period_start"], s["period_end"], None,
    )

    assert alloc_a_after["total_fpts"] > alloc_a_before["total_fpts"], \
        "Team A's fpts must increase after correction to their game"
    assert alloc_b_after["total_fpts"] == alloc_b_before["total_fpts"], \
        "Team B's fpts must NOT change for a correction to Team A's game"


@pytest.mark.asyncio
async def test_late_import_goes_to_owner_at_game_time(db, setup_trade_scenario):
    """Late-arriving stats for a game go to whoever owned the player at game time."""
    s = setup_trade_scenario
    from utils.game_allocation import allocate_team_period_fpts

    # Add a new game on Jan 8 (Team A's ownership period) with late data
    new_gid = 2026020199
    await db.games.insert_one({"nhl_game_id": new_gid, "date": "2026-01-08"})

    # Add the stats as if they arrived late
    player = await db.players.find_one({"_id": ObjectId(s["player_id"])})
    ls = player["live_stats"]
    ls[str(new_gid)] = {
        "goals": 3, "assists": 2, "shots": 5,
        "plus_minus": 2, "penalty_minutes": 0,
        "power_play_goals": 0, "power_play_points": 0,
        "short_handed_goals": 0, "short_handed_points": 0,
        "game_winning_goals": 0, "updated_at": "2026-01-08T23:00:00",
    }
    await db.players.update_one(
        {"_id": ObjectId(s["player_id"])}, {"$set": {"live_stats": ls}},
    )

    alloc_a = await allocate_team_period_fpts(
        db, s["team_a_id"], s["league_id"],
        s["period_start"], s["period_end"], None,
    )
    alloc_b = await allocate_team_period_fpts(
        db, s["team_b_id"], s["league_id"],
        s["period_start"], s["period_end"], None,
    )

    # Team A should have 6 games now (5 original + 1 late import on Jan 8)
    assert alloc_a["game_count"] == 6, \
        f"Team A should have 6 games (incl. late Jan 8 import), got {alloc_a['game_count']}"
    # Team B should still have only 3
    assert alloc_b["game_count"] == 3, \
        f"Team B should still have 3 games, got {alloc_b['game_count']}"


# ══════════════════════════════════════════════════════════════════
# Test 5: Recomputation — idempotent results
# ══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_recomputation_is_idempotent(db, setup_trade_scenario):
    """Running the same allocation twice produces identical results."""
    s = setup_trade_scenario
    from utils.game_allocation import allocate_team_period_fpts

    run1_a = await allocate_team_period_fpts(
        db, s["team_a_id"], s["league_id"],
        s["period_start"], s["period_end"], None,
    )
    run1_b = await allocate_team_period_fpts(
        db, s["team_b_id"], s["league_id"],
        s["period_start"], s["period_end"], None,
    )

    # Run a second time — must be identical
    run2_a = await allocate_team_period_fpts(
        db, s["team_a_id"], s["league_id"],
        s["period_start"], s["period_end"], None,
    )
    run2_b = await allocate_team_period_fpts(
        db, s["team_b_id"], s["league_id"],
        s["period_start"], s["period_end"], None,
    )

    assert run1_a["total_fpts"] == run2_a["total_fpts"], "Team A fpts must be idempotent"
    assert run1_a["game_count"] == run2_a["game_count"], "Team A game count must be idempotent"
    assert run1_b["total_fpts"] == run2_b["total_fpts"], "Team B fpts must be idempotent"
    assert run1_b["game_count"] == run2_b["game_count"], "Team B game count must be idempotent"


@pytest.mark.asyncio
async def test_recomputation_after_correction_is_stable(db, setup_trade_scenario):
    """After a correction, recomputation produces the corrected results
    deterministically on every subsequent call."""
    s = setup_trade_scenario
    from utils.game_allocation import allocate_team_period_fpts

    # Apply correction
    player = await db.players.find_one({"_id": ObjectId(s["player_id"])})
    ls = player["live_stats"]
    ls["2026020101"]["goals"] = 5  # was 2
    await db.players.update_one(
        {"_id": ObjectId(s["player_id"])}, {"$set": {"live_stats": ls}},
    )

    results = []
    for _ in range(3):
        alloc_a = await allocate_team_period_fpts(
            db, s["team_a_id"], s["league_id"],
            s["period_start"], s["period_end"], None,
        )
        results.append(alloc_a["total_fpts"])

    assert results[0] == results[1] == results[2], \
        f"Recomputation must be stable: {results}"


# ══════════════════════════════════════════════════════════════════
# Test 6: Roto stat allocation
# ══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_roto_stats_split_correctly(db, setup_trade_scenario):
    """Roto category stats follow the same ownership split as fpts."""
    s = setup_trade_scenario
    from utils.game_allocation import allocate_team_period_roto_stats

    stats_a = await allocate_team_period_roto_stats(
        db, s["team_a_id"], s["league_id"],
        s["period_start"], s["period_end"], ["goals", "assists", "shots"],
    )
    stats_b = await allocate_team_period_roto_stats(
        db, s["team_b_id"], s["league_id"],
        s["period_start"], s["period_end"], ["goals", "assists", "shots"],
    )

    # 5 games × 2 goals = 10 for Team A, 3 games × 2 goals = 6 for Team B
    assert stats_a["goals"] == 10, f"Team A: expected 10 goals, got {stats_a['goals']}"
    assert stats_b["goals"] == 6, f"Team B: expected 6 goals, got {stats_b['goals']}"
    assert stats_a["assists"] == 5, f"Team A: expected 5 assists, got {stats_a['assists']}"
    assert stats_b["assists"] == 3, f"Team B: expected 3 assists, got {stats_b['assists']}"
    assert stats_a["shots"] == 15, f"Team A: expected 15 shots, got {stats_a['shots']}"
    assert stats_b["shots"] == 9, f"Team B: expected 9 shots, got {stats_b['shots']}"


# ══════════════════════════════════════════════════════════════════
# Test 7: Backfill engine
# ══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_backfill_from_trades(db):
    """Backfill engine reconstructs ownership periods from trade records."""
    league_id = str(ObjectId())
    team_a_id = str(ObjectId())
    team_b_id = str(ObjectId())
    player_id = str(ObjectId())

    await db.leagues.insert_one({
        "_id": ObjectId(league_id), "name": "Backfill Test League",
        "season_start_date": "2026-01-01",
    })
    await db.teams.insert_many([
        {"_id": ObjectId(team_a_id), "name": "Team A",
         "league_id": league_id, "roster": [],
         "lineup": {}},
        {"_id": ObjectId(team_b_id), "name": "Team B",
         "league_id": league_id, "roster": [player_id],
         "lineup": {player_id: {"section": "forward", "slot": "C"}}},
    ])

    # Simulate an executed trade: player moved from A to B
    trade_time = datetime(2026, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
    await db.trades.insert_one({
        "league_id": league_id,
        "status": "executed",
        "is_multi_party": True,
        "proposer_team_id": team_a_id,
        "target_team_id": team_b_id,
        "processed_at": trade_time.isoformat(),
        "execution_moves": [
            {"player_id": player_id, "from": team_a_id,
             "to": team_b_id, "from_name": "Team A", "to_name": "Team B"},
        ],
    })

    # Simulate activity feed: original add
    add_time = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    await db.activity_feed.insert_one({
        "league_id": league_id, "event_type": "roster_add",
        "metadata": {"team_id": team_a_id, "player_id": player_id},
        "created_at": add_time,
    })

    from utils.backfill_ownership import backfill_league_ownership
    result = await backfill_league_ownership(db, league_id)

    assert result["ownership_periods_created"] > 0
    assert result["events_found"] > 0

    # Verify the ownership periods are correct
    periods = await db.player_ownership_periods.find(
        {"player_id": player_id, "league_id": league_id},
    ).sort("acquired_at", 1).to_list(10)

    # Should have 2 periods: A (add → trade) and B (trade → open)
    assert len(periods) >= 2, f"Expected 2+ ownership periods, got {len(periods)}"

    def _strip_tz(dt):
        """Normalize for comparison — MongoDB stores naive UTC."""
        if dt is None:
            return None
        return dt.replace(tzinfo=None) if dt.tzinfo else dt

    # Period 1: Team A from add_time to trade_time
    p1 = next((p for p in periods if p["team_id"] == team_a_id), None)
    assert p1 is not None, "Should have ownership period for Team A"
    assert _strip_tz(p1["released_at"]) == _strip_tz(trade_time), \
        f"Team A released at trade time: {p1['released_at']} vs {trade_time}"

    # Period 2: Team B from trade_time, open-ended
    p2 = next((p for p in periods if p["team_id"] == team_b_id), None)
    assert p2 is not None, "Should have ownership period for Team B"
    assert p2["released_at"] is None, "Team B period should be open"


@pytest.mark.asyncio
async def test_backfill_is_idempotent(db):
    """Running backfill twice produces the same number of records."""
    league_id = str(ObjectId())
    team_id = str(ObjectId())
    player_id = str(ObjectId())

    await db.leagues.insert_one({
        "_id": ObjectId(league_id), "name": "Idempotent Test",
        "season_start_date": "2026-01-01",
    })
    await db.teams.insert_one({
        "_id": ObjectId(team_id), "name": "Team",
        "league_id": league_id, "roster": [player_id],
        "lineup": {},
    })

    from utils.backfill_ownership import backfill_league_ownership

    r1 = await backfill_league_ownership(db, league_id)
    count_after_1 = await db.player_ownership_periods.count_documents(
        {"league_id": league_id}
    )

    r2 = await backfill_league_ownership(db, league_id)
    count_after_2 = await db.player_ownership_periods.count_documents(
        {"league_id": league_id}
    )

    assert count_after_1 == count_after_2, \
        f"Backfill must be idempotent: {count_after_1} vs {count_after_2}"


@pytest.mark.asyncio
async def test_backfill_inferred_baseline_for_no_events(db):
    """Players on roster with no transaction history get inferred_baseline evidence."""
    league_id = str(ObjectId())
    team_id = str(ObjectId())
    player_id = str(ObjectId())

    await db.leagues.insert_one({
        "_id": ObjectId(league_id), "name": "Baseline Test",
        "season_start_date": "2026-01-01",
    })
    await db.teams.insert_one({
        "_id": ObjectId(team_id), "name": "Team",
        "league_id": league_id, "roster": [player_id],
        "lineup": {},
    })

    from utils.backfill_ownership import backfill_league_ownership
    await backfill_league_ownership(db, league_id)

    periods = await db.player_ownership_periods.find(
        {"player_id": player_id, "league_id": league_id},
    ).to_list(10)

    assert len(periods) == 1, f"Expected 1 inferred period, got {len(periods)}"
    assert periods[0]["evidence"] == "inferred_baseline", \
        f"Expected inferred_baseline evidence, got {periods[0].get('evidence')}"
    assert periods[0]["backfilled"] is True


# ══════════════════════════════════════════════════════════════════
# Test 8: Fallback path — uncertain flag
# ══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_fallback_flags_uncertain_when_no_ownership(db):
    """When no ownership data and no backfill, results are flagged uncertain."""
    league_id = str(ObjectId())
    team_id = str(ObjectId())
    player_id = str(ObjectId())

    await db.leagues.insert_one({
        "_id": ObjectId(league_id), "name": "No Data League",
        "season_start_date": "2026-01-01",
        "matchup_length_days": 7,
        # No ownership_backfilled_at — backfill hasn't been run
    })
    await db.teams.insert_one({
        "_id": ObjectId(team_id), "name": "Team",
        "league_id": league_id, "roster": [player_id],
    })
    await db.players.insert_one({
        "_id": ObjectId(player_id), "name": "Player",
        "position": "C", "player_type": "skater",
        "goals": 10, "assists": 5,
    })

    from utils.game_allocation import allocate_team_period_fpts

    period_start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    period_end = datetime(2026, 1, 8, tzinfo=timezone.utc)

    alloc = await allocate_team_period_fpts(
        db, team_id, league_id, period_start, period_end, None,
    )

    assert alloc.get("uncertain") is True, "Should be flagged as uncertain"
    assert alloc.get("needs_backfill") is True, "Should indicate backfill needed"


@pytest.mark.asyncio
async def test_backfilled_league_returns_zero_for_empty_team(db):
    """After backfill, a team with no players in a period gets 0 (not uncertain)."""
    league_id = str(ObjectId())
    team_id = str(ObjectId())

    await db.leagues.insert_one({
        "_id": ObjectId(league_id), "name": "Backfilled Empty League",
        "season_start_date": "2026-01-01",
        "ownership_backfilled_at": datetime.now(timezone.utc),
    })
    await db.teams.insert_one({
        "_id": ObjectId(team_id), "name": "Empty Team",
        "league_id": league_id, "roster": [],
    })

    from utils.game_allocation import allocate_team_period_fpts

    period_start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    period_end = datetime(2026, 1, 8, tzinfo=timezone.utc)

    alloc = await allocate_team_period_fpts(
        db, team_id, league_id, period_start, period_end, None,
    )

    assert alloc["total_fpts"] == 0.0
    assert alloc["game_count"] == 0
    assert alloc.get("uncertain") is False, "Backfilled empty result should NOT be uncertain"


# ══════════════════════════════════════════════════════════════════
# Test 9: Known unowned interval distinct from missing history
# ══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_known_unowned_awards_no_stats(db, setup_trade_scenario):
    """Explicitly unowned interval: no stats credited to any team."""
    s = setup_trade_scenario
    from utils.game_allocation import allocate_team_period_fpts

    # Drop from Team B, no pickup
    drop_time = datetime(2026, 1, 10, 6, 0, 0, tzinfo=timezone.utc)
    await db.player_ownership_periods.update_one(
        {"player_id": s["player_id"], "team_id": s["team_b_id"]},
        {"$set": {"released_at": drop_time, "release_source": "drop"}},
    )

    # After drop, the Jan 10 games at midnight are still Team B's
    # (acquired at midnight, released at 6am — game at midnight is owned)
    # But the Jan 11 game at midnight is NOT owned by anyone.
    alloc_b = await allocate_team_period_fpts(
        db, s["team_b_id"], s["league_id"],
        s["period_start"], s["period_end"], None,
    )

    # Team B: 2 games on Jan 10 (owned midnight → 6am, games at midnight)
    assert alloc_b["game_count"] == 2, \
        f"Team B should have 2 games (Jan 10 before drop), got {alloc_b['game_count']}"

    # Team A should be unaffected
    alloc_a = await allocate_team_period_fpts(
        db, s["team_a_id"], s["league_id"],
        s["period_start"], s["period_end"], None,
    )
    assert alloc_a["game_count"] == 5, \
        f"Team A should still have 5 games, got {alloc_a['game_count']}"


# ══════════════════════════════════════════════════════════════════
# Test 10: End-to-end — backfill then allocate
# ══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_backfill_then_allocate_produces_correct_split(db):
    """Full pipeline: seed trade data → backfill → allocate → verify split."""
    league_id = str(ObjectId())
    team_a_id = str(ObjectId())
    team_b_id = str(ObjectId())
    player_id = str(ObjectId())
    season_start = datetime(2026, 1, 5, tzinfo=timezone.utc)
    trade_time = datetime(2026, 1, 10, 0, 0, 0, tzinfo=timezone.utc)

    await db.leagues.insert_one({
        "_id": ObjectId(league_id), "name": "E2E Test League",
        "season_start_date": "2026-01-05",
        "matchup_length_days": 7,
    })
    await db.teams.insert_many([
        {"_id": ObjectId(team_a_id), "name": "Team A",
         "league_id": league_id, "roster": [],
         "lineup": {}},
        {"_id": ObjectId(team_b_id), "name": "Team B",
         "league_id": league_id, "roster": [player_id],
         "lineup": {player_id: {"section": "forward", "slot": "C"}}},
    ])
    await db.players.insert_one({
        "_id": ObjectId(player_id), "name": "E2E Player",
        "position": "C", "player_type": "skater", "live_stats": {},
    })

    # Seed evidence: activity_feed add + trade
    await db.activity_feed.insert_one({
        "league_id": league_id, "event_type": "roster_add",
        "metadata": {"team_id": team_a_id, "player_id": player_id},
        "created_at": season_start,
    })
    await db.trades.insert_one({
        "league_id": league_id, "status": "executed",
        "is_multi_party": True,
        "proposer_team_id": team_a_id,
        "target_team_id": team_b_id,
        "processed_at": trade_time.isoformat(),
        "execution_moves": [
            {"player_id": player_id, "from": team_a_id,
             "to": team_b_id, "from_name": "Team A", "to_name": "Team B"},
        ],
    })

    # Seed games (same pattern as trade scenario)
    all_dates = ["2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08",
                 "2026-01-09", "2026-01-10", "2026-01-10", "2026-01-11"]
    live_stats = {}
    for i, d in enumerate(all_dates):
        gid = 2026020200 + i
        await db.games.insert_one({"nhl_game_id": gid, "date": d})
        live_stats[str(gid)] = {
            "goals": 2, "assists": 1, "shots": 3,
            "plus_minus": 1, "penalty_minutes": 0,
            "power_play_goals": 0, "power_play_points": 0,
            "short_handed_goals": 0, "short_handed_points": 0,
            "game_winning_goals": 0, "updated_at": d + "T03:00:00",
        }
    await db.players.update_one(
        {"_id": ObjectId(player_id)}, {"$set": {"live_stats": live_stats}},
    )

    # Run backfill
    from utils.backfill_ownership import backfill_league_ownership
    result = await backfill_league_ownership(db, league_id)
    assert result["ownership_periods_created"] >= 2, \
        f"Backfill should create 2+ ownership periods, got {result['ownership_periods_created']}"

    # Now allocate
    from utils.game_allocation import allocate_team_period_fpts

    period_start = datetime(2026, 1, 5, tzinfo=timezone.utc)
    period_end = datetime(2026, 1, 12, tzinfo=timezone.utc)

    alloc_a = await allocate_team_period_fpts(
        db, team_a_id, league_id, period_start, period_end, None,
    )
    alloc_b = await allocate_team_period_fpts(
        db, team_b_id, league_id, period_start, period_end, None,
    )

    assert alloc_a["game_count"] == 5, \
        f"After backfill, Team A should have 5 games, got {alloc_a['game_count']}"
    assert alloc_b["game_count"] == 3, \
        f"After backfill, Team B should have 3 games, got {alloc_b['game_count']}"
    assert alloc_a.get("uncertain") is not True, "Backfilled result should not be uncertain"
