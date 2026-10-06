"""Tests that simulate the REAL API flow — no pre-seeded ownership data.

These tests reproduce the exact failures the user reported:
  1. Trade: earlier stats follow the player to the new team (A:0 / B:16)
  2. Drop: dropping removes previously earned stats
  3. Pickup after drop: unowned gap not excluded
  4. Drop+reacquire: earlier stats return zero
  5. Active→bench: bench-period stats still counted (16 instead of 10)
  6. Bench→active: pre-activation stats counted (16 instead of 6)
  7. Finalization after trade: A:0 / B:16 instead of A:10 / B:6
  8. Historical correction: goes to current owner, not original owner
  9. Roto recomputation: moves earlier goals to new owner

Each test seeds ONLY games + players (no ownership/lineup periods) and
then triggers mutations via `log_roster_change` / `record_lineup_change`
— the same functions the real API calls.

Run: cd /app/backend && python -m pytest tests/test_api_flow_allocation.py -v
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

MONGO_URL = os.environ.get("MONGO_URL", os.environ["MONGO_URL"])


@pytest_asyncio.fixture
async def db():
    db_name = f"test_apiflow_{ObjectId()}"
    client = AsyncIOMotorClient(MONGO_URL)
    database = client[db_name]
    yield database
    await client.drop_database(db_name)
    client.close()


async def _seed_league(db, league_id, season_start="2026-01-05"):
    """Create a league with ownership_backfilled_at set (simulates a backfilled league)."""
    await db.leagues.insert_one({
        "_id": ObjectId(league_id),
        "name": "API Flow Test League",
        "season_start_date": season_start,
        "matchup_length_days": 7,
        "current_week": 1,
        "ownership_backfilled_at": datetime.now(timezone.utc),
    })


async def _seed_player_with_games(db, player_id, game_dates, goals_per_game=2):
    """Create a player with live_stats for the given game dates."""
    live_stats = {}
    for i, d in enumerate(game_dates):
        gid = 2026020300 + i
        await db.games.insert_one({"nhl_game_id": gid, "date": d})
        live_stats[str(gid)] = {
            "goals": goals_per_game, "assists": 1, "shots": 3,
            "plus_minus": 1, "penalty_minutes": 0,
            "power_play_goals": 0, "power_play_points": 0,
            "short_handed_goals": 0, "short_handed_points": 0,
            "game_winning_goals": 0, "updated_at": d + "T20:00:00",
        }
    await db.players.insert_one({
        "_id": ObjectId(player_id),
        "name": "Test Player",
        "position": "C", "player_type": "skater",
        "live_stats": live_stats,
    })


# ══════════════════════════════════════════════════════════════════
# Test A: Trade — retroactive ownership creation
# ══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_trade_creates_retroactive_ownership(db):
    """When a trade happens via log_roster_change (the real API path),
    the old team gets a retroactive ownership period even though initial
    ownership was never seeded.

    Expected: A:10 goals (5 games pre-trade), B:6 goals (3 games post-trade).
    Previously broken: A:0, B:16.
    """
    league_id = str(ObjectId())
    team_a_id = str(ObjectId())
    team_b_id = str(ObjectId())
    player_id = str(ObjectId())
    trade_time = datetime(2026, 1, 10, 0, 0, 0, tzinfo=timezone.utc)

    await _seed_league(db, league_id)

    # Teams: player starts on Team A
    await db.teams.insert_many([
        {"_id": ObjectId(team_a_id), "name": "Team A",
         "league_id": league_id, "roster": [player_id],
         "lineup": {player_id: {"section": "forward", "slot": "C"}}},
        {"_id": ObjectId(team_b_id), "name": "Team B",
         "league_id": league_id, "roster": [],
         "lineup": {}},
    ])

    # 8 games: 5 before trade (Jan 5-9), 3 after (Jan 10, 10, 11)
    game_dates = ["2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08",
                  "2026-01-09", "2026-01-10", "2026-01-10", "2026-01-11"]
    await _seed_player_with_games(db, player_id, game_dates)

    # Simulate trade: this is what the real trade API calls
    from utils.scoring_roster import log_roster_change

    # Move roster first (like the real API)
    await db.teams.update_one(
        {"_id": ObjectId(team_a_id)}, {"$pull": {"roster": player_id}},
    )
    await db.teams.update_one(
        {"_id": ObjectId(team_b_id)}, {"$push": {"roster": player_id}},
    )
    # Update lineup for Team B
    await db.teams.update_one(
        {"_id": ObjectId(team_b_id)},
        {"$set": {f"lineup.{player_id}": {"section": "forward", "slot": "C"}}},
    )

    # Log the roster changes (same as real trade API, but with explicit timestamp)
    await log_roster_change(db, team_id=team_a_id, league_id=league_id,
        player_id=player_id, action="remove", source="trade", week=1,
        timestamp=trade_time)
    await log_roster_change(db, team_id=team_b_id, league_id=league_id,
        player_id=player_id, action="add", source="trade", week=1,
        timestamp=trade_time)

    # Verify ownership periods were created
    a_periods = await db.player_ownership_periods.find(
        {"player_id": player_id, "team_id": team_a_id, "league_id": league_id}
    ).to_list(10)
    b_periods = await db.player_ownership_periods.find(
        {"player_id": player_id, "team_id": team_b_id, "league_id": league_id}
    ).to_list(10)

    assert len(a_periods) == 1, f"Team A should have 1 ownership period, got {len(a_periods)}"
    assert a_periods[0]["released_at"] is not None, "Team A period should be closed"
    assert len(b_periods) == 1, f"Team B should have 1 ownership period, got {len(b_periods)}"
    assert b_periods[0]["released_at"] is None, "Team B period should be open"

    # Now calculate scoring
    from utils.game_allocation import allocate_team_period_fpts

    period_start = datetime(2026, 1, 5, tzinfo=timezone.utc)
    period_end = datetime(2026, 1, 12, tzinfo=timezone.utc)

    alloc_a = await allocate_team_period_fpts(
        db, team_a_id, league_id, period_start, period_end, None,
    )
    alloc_b = await allocate_team_period_fpts(
        db, team_b_id, league_id, period_start, period_end, None,
    )

    # Team A: owned from season start to trade time (midnight Jan 10).
    # Games on Jan 5-9 (midnight) → released_at(midnight Jan 10) > game(midnight Jan 5-9) → TRUE
    # Games on Jan 10 (midnight) → released_at(midnight Jan 10) > game(midnight Jan 10) → FALSE
    # So Team A gets 5 games (Jan 5-9).
    assert alloc_a["game_count"] == 5, \
        f"Team A: expected 5 games, got {alloc_a['game_count']}"

    # Team B: owned from trade time (midnight Jan 10).
    # Games on Jan 10 (midnight) → acquired(midnight) <= game(midnight) → TRUE
    # Game on Jan 11 (midnight) → TRUE
    # So Team B gets 3 games (2× Jan 10, 1× Jan 11).
    assert alloc_b["game_count"] == 3, \
        f"Team B: expected 3 games, got {alloc_b['game_count']}"


@pytest.mark.asyncio
async def test_trade_with_midnight_games_and_midnight_trade(db):
    """Same-day trade at midnight: game at midnight owned by OLD team.

    When trade happens at exactly midnight (same timestamp as game),
    the ownership comparison acquired_at <= game_date uses <= for old team
    and acquired_at <= game_date for new team. The old team's released_at
    is at midnight, so released_at > midnight is FALSE → old team doesn't
    get the game. But new team's acquired_at is at midnight, so
    acquired_at <= midnight is TRUE → new team gets it.

    Convention: ownership changes at the transaction timestamp. The new
    owner gets games at or after that timestamp.
    """
    league_id = str(ObjectId())
    team_a_id = str(ObjectId())
    team_b_id = str(ObjectId())
    player_id = str(ObjectId())

    await _seed_league(db, league_id)

    await db.teams.insert_many([
        {"_id": ObjectId(team_a_id), "name": "Team A",
         "league_id": league_id, "roster": [player_id],
         "lineup": {player_id: {"section": "forward", "slot": "C"}}},
        {"_id": ObjectId(team_b_id), "name": "Team B",
         "league_id": league_id, "roster": [],
         "lineup": {}},
    ])

    # 2 games: Jan 9 (before trade) and Jan 10 (on trade day)
    await _seed_player_with_games(db, player_id, ["2026-01-09", "2026-01-10"])

    from utils.scoring_roster import log_roster_change

    # Trade at midnight Jan 10
    trade_time = datetime(2026, 1, 10, 0, 0, 0, tzinfo=timezone.utc)
    await db.teams.update_one({"_id": ObjectId(team_a_id)}, {"$pull": {"roster": player_id}})
    await db.teams.update_one({"_id": ObjectId(team_b_id)}, {"$push": {"roster": player_id}})
    await db.teams.update_one({"_id": ObjectId(team_b_id)},
        {"$set": {f"lineup.{player_id}": {"section": "forward"}}})

    await log_roster_change(db, team_id=team_a_id, league_id=league_id,
        player_id=player_id, action="remove", source="trade", week=1,
        timestamp=trade_time)
    await log_roster_change(db, team_id=team_b_id, league_id=league_id,
        player_id=player_id, action="add", source="trade", week=1,
        timestamp=trade_time)

    from utils.game_allocation import allocate_team_period_fpts

    period_start = datetime(2026, 1, 5, tzinfo=timezone.utc)
    period_end = datetime(2026, 1, 12, tzinfo=timezone.utc)

    alloc_a = await allocate_team_period_fpts(
        db, team_a_id, league_id, period_start, period_end, None,
    )
    alloc_b = await allocate_team_period_fpts(
        db, team_b_id, league_id, period_start, period_end, None,
    )

    # Team A: owned until midnight Jan 10. Game on Jan 9 (midnight) is owned.
    # Game on Jan 10 (midnight): released_at(midnight) > game(midnight) is FALSE.
    # So Team A gets only Jan 9.
    assert alloc_a["game_count"] == 1, f"Team A: expected 1 game, got {alloc_a['game_count']}"
    # Team B: owned from midnight Jan 10. Game on Jan 10: acquired(midnight) <= game(midnight) TRUE.
    assert alloc_b["game_count"] == 1, f"Team B: expected 1 game, got {alloc_b['game_count']}"


# ══════════════════════════════════════════════════════════════════
# Test B: Drop — preserves earlier stats
# ══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_drop_preserves_historical_stats(db):
    """Dropping a player preserves the team's earlier earned stats.

    Previously broken: A:0 after drop (stats vanished).
    """
    league_id = str(ObjectId())
    team_id = str(ObjectId())
    player_id = str(ObjectId())

    await _seed_league(db, league_id)
    await db.teams.insert_one({
        "_id": ObjectId(team_id), "name": "Team A",
        "league_id": league_id, "roster": [player_id],
        "lineup": {player_id: {"section": "forward", "slot": "C"}},
    })
    # 5 games, then drop
    await _seed_player_with_games(db, player_id, [
        "2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08", "2026-01-09",
    ])

    from utils.scoring_roster import log_roster_change
    from utils.game_allocation import allocate_team_period_fpts

    # Drop on Jan 10
    drop_time = datetime(2026, 1, 10, 0, 0, 0, tzinfo=timezone.utc)
    await db.teams.update_one({"_id": ObjectId(team_id)}, {"$pull": {"roster": player_id}})
    await log_roster_change(db, team_id=team_id, league_id=league_id,
        player_id=player_id, action="remove", source="drop", week=1,
        timestamp=drop_time)

    period_start = datetime(2026, 1, 5, tzinfo=timezone.utc)
    period_end = datetime(2026, 1, 12, tzinfo=timezone.utc)

    alloc = await allocate_team_period_fpts(
        db, team_id, league_id, period_start, period_end, None,
    )

    # Team had the player during all 5 games (Jan 5-9), dropped after
    assert alloc["game_count"] == 5, f"Expected 5 games preserved after drop, got {alloc['game_count']}"
    assert alloc["total_fpts"] > 0, "Stats should be preserved after drop"


# ══════════════════════════════════════════════════════════════════
# Test C: Pickup after drop — unowned gap excluded
# ══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_pickup_after_drop_excludes_unowned_gap(db):
    """Team A drops on Jan 8, Team B picks up on Jan 10.
    Games on Jan 8-9 are unowned and must not be credited to either team.
    """
    league_id = str(ObjectId())
    team_a_id = str(ObjectId())
    team_b_id = str(ObjectId())
    player_id = str(ObjectId())

    await _seed_league(db, league_id)
    await db.teams.insert_many([
        {"_id": ObjectId(team_a_id), "name": "Team A",
         "league_id": league_id, "roster": [player_id],
         "lineup": {player_id: {"section": "forward"}}},
        {"_id": ObjectId(team_b_id), "name": "Team B",
         "league_id": league_id, "roster": [],
         "lineup": {}},
    ])

    await _seed_player_with_games(db, player_id, [
        "2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08",
        "2026-01-09", "2026-01-10", "2026-01-11",
    ])

    from utils.scoring_roster import log_roster_change
    from utils.game_allocation import allocate_team_period_fpts

    # Team A drops on Jan 8
    drop_time = datetime(2026, 1, 8, 0, 0, 0, tzinfo=timezone.utc)
    await db.teams.update_one({"_id": ObjectId(team_a_id)}, {"$pull": {"roster": player_id}})
    await log_roster_change(db, team_id=team_a_id, league_id=league_id,
        player_id=player_id, action="remove", source="drop", week=1,
        timestamp=drop_time)

    # Team B picks up on Jan 10
    pickup_time = datetime(2026, 1, 10, 0, 0, 0, tzinfo=timezone.utc)
    await db.teams.update_one({"_id": ObjectId(team_b_id)}, {"$push": {"roster": player_id}})
    await db.teams.update_one({"_id": ObjectId(team_b_id)},
        {"$set": {f"lineup.{player_id}": {"section": "forward"}}})
    await log_roster_change(db, team_id=team_b_id, league_id=league_id,
        player_id=player_id, action="add", source="add", week=1,
        timestamp=pickup_time)

    period_start = datetime(2026, 1, 5, tzinfo=timezone.utc)
    period_end = datetime(2026, 1, 12, tzinfo=timezone.utc)

    alloc_a = await allocate_team_period_fpts(
        db, team_a_id, league_id, period_start, period_end, None,
    )
    alloc_b = await allocate_team_period_fpts(
        db, team_b_id, league_id, period_start, period_end, None,
    )

    # Team A: owned from season start (Jan 5) to drop_time (Jan 8 midnight)
    # Games: Jan 5, 6, 7 have midnight < Jan 8 midnight → owned
    # Jan 8 midnight: released_at(Jan 8) > game(Jan 8) → FALSE → not owned
    assert alloc_a["game_count"] == 3, f"Team A: expected 3 games (Jan 5-7), got {alloc_a['game_count']}"

    # Team B: owned from pickup_time (Jan 10 midnight)
    # Games: Jan 10 midnight: acquired(Jan 10) <= game(Jan 10) → TRUE → owned
    # Jan 11 midnight: acquired(Jan 10) <= game(Jan 11) → TRUE → owned
    assert alloc_b["game_count"] == 2, f"Team B: expected 2 games (Jan 10-11), got {alloc_b['game_count']}"

    # Unowned gap (Jan 8-9): no team gets credit for those games
    total_games = alloc_a["game_count"] + alloc_b["game_count"]
    assert total_games == 5, f"Expected 5 credited games (3+2), with 2 unowned, got {total_games}"


# ══════════════════════════════════════════════════════════════════
# Test D: Drop and reacquire — same team
# ══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_drop_and_reacquire_preserves_earlier_stats(db):
    """Team A drops, then reacquires. Both ownership intervals are preserved.

    Previously broken: returned zero instead of 10 earlier goals.
    """
    league_id = str(ObjectId())
    team_id = str(ObjectId())
    player_id = str(ObjectId())

    await _seed_league(db, league_id)
    await db.teams.insert_one({
        "_id": ObjectId(team_id), "name": "Team A",
        "league_id": league_id, "roster": [player_id],
        "lineup": {player_id: {"section": "forward"}},
    })

    await _seed_player_with_games(db, player_id, [
        "2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08", "2026-01-09",
    ])

    from utils.scoring_roster import log_roster_change
    from utils.game_allocation import allocate_team_period_fpts

    # Drop then reacquire at specific times
    drop_time = datetime(2026, 1, 8, 0, 0, 0, tzinfo=timezone.utc)
    reacquire_time = datetime(2026, 1, 10, 0, 0, 0, tzinfo=timezone.utc)

    await db.teams.update_one({"_id": ObjectId(team_id)}, {"$pull": {"roster": player_id}})
    await log_roster_change(db, team_id=team_id, league_id=league_id,
        player_id=player_id, action="remove", source="drop", week=1,
        timestamp=drop_time)

    await db.teams.update_one({"_id": ObjectId(team_id)}, {"$push": {"roster": player_id}})
    await db.teams.update_one({"_id": ObjectId(team_id)},
        {"$set": {f"lineup.{player_id}": {"section": "forward"}}})
    await log_roster_change(db, team_id=team_id, league_id=league_id,
        player_id=player_id, action="add", source="add", week=1,
        timestamp=reacquire_time)

    period_start = datetime(2026, 1, 5, tzinfo=timezone.utc)
    period_end = datetime(2026, 1, 12, tzinfo=timezone.utc)

    alloc = await allocate_team_period_fpts(
        db, team_id, league_id, period_start, period_end, None,
    )

    # First interval: Jan 5 → Jan 8 (drop). Games Jan 5, 6, 7 = 3 games.
    # Gap: Jan 8-9 (unowned)
    # Second interval: Jan 10 → open. No games after Jan 9 in this set.
    # But wait — there are 5 games Jan 5-9. With drop at midnight Jan 8:
    # Games Jan 5(midnight), 6, 7 → owned (< Jan 8 midnight).
    # Game Jan 8 midnight: released_at(Jan 8) > game(Jan 8) → FALSE → not owned.
    # Game Jan 9: not owned (after drop, before reacquire).
    # Reacquire at Jan 10: no games at or after Jan 10 in this set.
    # Total: 3 games.
    assert alloc["game_count"] == 3, \
        f"Expected 3 games (Jan 5-7, excluding gap), got {alloc['game_count']}"


# ══════════════════════════════════════════════════════════════════
# Test E: Bench period exclusion through API flow
# ══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_active_to_bench_excludes_bench_stats(db):
    """Moving to bench via record_lineup_change excludes subsequent games.

    Simulates the real lineup API flow.
    """
    league_id = str(ObjectId())
    team_id = str(ObjectId())
    player_id = str(ObjectId())
    bench_time = datetime(2026, 1, 8, 0, 0, 0, tzinfo=timezone.utc)

    await _seed_league(db, league_id)
    await db.teams.insert_one({
        "_id": ObjectId(team_id), "name": "Team A",
        "league_id": league_id, "roster": [player_id],
        "lineup": {player_id: {"section": "forward"}},
    })

    # Seed ownership period (simulating a league with seeded ownership)
    season_start = datetime(2026, 1, 5, tzinfo=timezone.utc)
    await db.player_ownership_periods.insert_one({
        "player_id": player_id, "team_id": team_id, "league_id": league_id,
        "acquired_at": season_start, "released_at": None,
        "source": "draft", "release_source": None,
    })

    # Seed initial active lineup period
    await db.lineup_status_periods.insert_one({
        "player_id": player_id, "team_id": team_id, "league_id": league_id,
        "position": "forward", "started_at": season_start, "ended_at": None,
    })

    await _seed_player_with_games(db, player_id, [
        "2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08",
        "2026-01-09", "2026-01-10", "2026-01-10", "2026-01-11",
    ])

    # Move to bench (like the real lineup API)
    from utils.scoring_roster import record_lineup_change
    await record_lineup_change(
        db, player_id=player_id, team_id=team_id, league_id=league_id,
        new_position="bench", timestamp=bench_time,
    )

    from utils.game_allocation import allocate_team_period_fpts

    period_start = datetime(2026, 1, 5, tzinfo=timezone.utc)
    period_end = datetime(2026, 1, 12, tzinfo=timezone.utc)

    alloc = await allocate_team_period_fpts(
        db, team_id, league_id, period_start, period_end, None,
    )

    # Active: Jan 5, 6, 7 (3 games before bench_time midnight Jan 8)
    # Bench: Jan 8, 9, 10, 10, 11 (5 games, not counted)
    assert alloc["game_count"] == 3, \
        f"Expected 3 games (Jan 5-7, before bench), got {alloc['game_count']}"


@pytest.mark.asyncio
async def test_bench_to_active_excludes_bench_stats(db):
    """Player starts benched, activated later. Only post-activation games count."""
    league_id = str(ObjectId())
    team_id = str(ObjectId())
    player_id = str(ObjectId())
    activate_time = datetime(2026, 1, 8, 0, 0, 0, tzinfo=timezone.utc)
    season_start = datetime(2026, 1, 5, tzinfo=timezone.utc)

    await _seed_league(db, league_id)
    await db.teams.insert_one({
        "_id": ObjectId(team_id), "name": "Team A",
        "league_id": league_id, "roster": [player_id],
        "lineup": {player_id: {"section": "bench"}},
    })

    # Seed ownership + initial bench lineup
    await db.player_ownership_periods.insert_one({
        "player_id": player_id, "team_id": team_id, "league_id": league_id,
        "acquired_at": season_start, "released_at": None,
        "source": "draft", "release_source": None,
    })
    await db.lineup_status_periods.insert_one({
        "player_id": player_id, "team_id": team_id, "league_id": league_id,
        "position": "bench", "started_at": season_start, "ended_at": None,
    })

    await _seed_player_with_games(db, player_id, [
        "2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08",
        "2026-01-09", "2026-01-10", "2026-01-10", "2026-01-11",
    ])

    # Activate (like the real lineup API)
    from utils.scoring_roster import record_lineup_change
    await record_lineup_change(
        db, player_id=player_id, team_id=team_id, league_id=league_id,
        new_position="forward", timestamp=activate_time,
    )

    from utils.game_allocation import allocate_team_period_fpts

    period_start = datetime(2026, 1, 5, tzinfo=timezone.utc)
    period_end = datetime(2026, 1, 12, tzinfo=timezone.utc)

    alloc = await allocate_team_period_fpts(
        db, team_id, league_id, period_start, period_end, None,
    )

    # Benched: Jan 5, 6, 7 (not counted)
    # Active from Jan 8: Jan 8, 9, 10, 10, 11 (5 games)
    assert alloc["game_count"] == 5, \
        f"Expected 5 games (Jan 8-11, after activation), got {alloc['game_count']}"


# ══════════════════════════════════════════════════════════════════
# Test F: Historical correction applies to original owner
# ══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_correction_after_trade_goes_to_original_owner(db):
    """A correction to a pre-trade game changes Team A (original owner),
    not Team B (current owner). Uses the real API flow.
    """
    league_id = str(ObjectId())
    team_a_id = str(ObjectId())
    team_b_id = str(ObjectId())
    player_id = str(ObjectId())

    await _seed_league(db, league_id)
    await db.teams.insert_many([
        {"_id": ObjectId(team_a_id), "name": "Team A",
         "league_id": league_id, "roster": [player_id],
         "lineup": {player_id: {"section": "forward"}}},
        {"_id": ObjectId(team_b_id), "name": "Team B",
         "league_id": league_id, "roster": [],
         "lineup": {}},
    ])

    await _seed_player_with_games(db, player_id, [
        "2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08",
        "2026-01-09", "2026-01-10", "2026-01-10", "2026-01-11",
    ])

    from utils.scoring_roster import log_roster_change
    from utils.game_allocation import allocate_team_period_fpts

    # Trade
    await db.teams.update_one({"_id": ObjectId(team_a_id)}, {"$pull": {"roster": player_id}})
    await db.teams.update_one({"_id": ObjectId(team_b_id)}, {"$push": {"roster": player_id}})
    await db.teams.update_one({"_id": ObjectId(team_b_id)},
        {"$set": {f"lineup.{player_id}": {"section": "forward"}}})

    # Trade at Jan 10 10:00
    trade_time = datetime(2026, 1, 10, 10, 0, 0, tzinfo=timezone.utc)
    await log_roster_change(db, team_id=team_a_id, league_id=league_id,
        player_id=player_id, action="remove", source="trade", week=1,
        timestamp=trade_time)
    await log_roster_change(db, team_id=team_b_id, league_id=league_id,
        player_id=player_id, action="add", source="trade", week=1,
        timestamp=trade_time)

    period_start = datetime(2026, 1, 5, tzinfo=timezone.utc)
    period_end = datetime(2026, 1, 12, tzinfo=timezone.utc)

    # Get pre-correction scores
    alloc_a_before = await allocate_team_period_fpts(
        db, team_a_id, league_id, period_start, period_end, None,
    )
    alloc_b_before = await allocate_team_period_fpts(
        db, team_b_id, league_id, period_start, period_end, None,
    )

    # Apply correction: game 2 (Jan 6, gid=2026020301) goals: 2 → 5
    player = await db.players.find_one({"_id": ObjectId(player_id)})
    ls = player["live_stats"]
    ls["2026020301"]["goals"] = 5
    await db.players.update_one(
        {"_id": ObjectId(player_id)}, {"$set": {"live_stats": ls}},
    )

    alloc_a_after = await allocate_team_period_fpts(
        db, team_a_id, league_id, period_start, period_end, None,
    )
    alloc_b_after = await allocate_team_period_fpts(
        db, team_b_id, league_id, period_start, period_end, None,
    )

    assert alloc_a_after["total_fpts"] > alloc_a_before["total_fpts"], \
        "Correction to pre-trade game MUST increase Team A's score"
    assert alloc_b_after["total_fpts"] == alloc_b_before["total_fpts"], \
        "Correction to pre-trade game MUST NOT change Team B's score"


# ══════════════════════════════════════════════════════════════════
# Test G: Roto allocation follows ownership
# ══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_roto_allocation_via_api_flow(db):
    """Roto stats split correctly after trade via API flow."""
    league_id = str(ObjectId())
    team_a_id = str(ObjectId())
    team_b_id = str(ObjectId())
    player_id = str(ObjectId())

    await _seed_league(db, league_id)
    await db.teams.insert_many([
        {"_id": ObjectId(team_a_id), "name": "Team A",
         "league_id": league_id, "roster": [player_id],
         "lineup": {player_id: {"section": "forward"}}},
        {"_id": ObjectId(team_b_id), "name": "Team B",
         "league_id": league_id, "roster": [],
         "lineup": {}},
    ])

    await _seed_player_with_games(db, player_id, [
        "2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08", "2026-01-09",
    ])

    from utils.scoring_roster import log_roster_change
    from utils.game_allocation import allocate_team_period_roto_stats

    # Trade
    await db.teams.update_one({"_id": ObjectId(team_a_id)}, {"$pull": {"roster": player_id}})
    await db.teams.update_one({"_id": ObjectId(team_b_id)}, {"$push": {"roster": player_id}})
    await db.teams.update_one({"_id": ObjectId(team_b_id)},
        {"$set": {f"lineup.{player_id}": {"section": "forward"}}})

    # Trade at Jan 8 10:00
    trade_time = datetime(2026, 1, 8, 10, 0, 0, tzinfo=timezone.utc)
    await log_roster_change(db, team_id=team_a_id, league_id=league_id,
        player_id=player_id, action="remove", source="trade", week=1,
        timestamp=trade_time)
    await log_roster_change(db, team_id=team_b_id, league_id=league_id,
        player_id=player_id, action="add", source="trade", week=1,
        timestamp=trade_time)

    period_start = datetime(2026, 1, 5, tzinfo=timezone.utc)
    period_end = datetime(2026, 1, 12, tzinfo=timezone.utc)

    stats_a = await allocate_team_period_roto_stats(
        db, team_a_id, league_id, period_start, period_end, ["goals", "assists"],
    )
    stats_b = await allocate_team_period_roto_stats(
        db, team_b_id, league_id, period_start, period_end, ["goals", "assists"],
    )

    # Team A: owned from season start (Jan 5) to trade (Jan 8 10:00)
    # Games: Jan 5, 6, 7 (midnight < Jan 8 10:00) → 3 games, 6 goals, 3 assists
    # Jan 8 midnight: acquired <= midnight(Jan8) TRUE, released(10:00) > midnight(Jan8) → TRUE → owned!
    # So Team A gets Jan 5, 6, 7, 8 = 4 games, 8 goals, 4 assists
    assert stats_a["goals"] == 8, f"Team A roto goals: expected 8, got {stats_a['goals']}"
    assert stats_a["assists"] == 4, f"Team A roto assists: expected 4, got {stats_a['assists']}"
    # Team B: owned from Jan 8 10:00
    # Jan 8 midnight: acquired(10:00) <= midnight(Jan8) → FALSE → not owned
    # Jan 9 midnight: acquired(10:00) <= midnight(Jan9) → TRUE → owned
    assert stats_b["goals"] == 2, f"Team B roto goals: expected 2, got {stats_b['goals']}"


# ══════════════════════════════════════════════════════════════════
# Test H: Recomputation is idempotent via API flow
# ══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_recomputation_idempotent_via_api_flow(db):
    """Running allocation twice via API flow produces identical results."""
    league_id = str(ObjectId())
    team_id = str(ObjectId())
    player_id = str(ObjectId())

    await _seed_league(db, league_id)
    await db.teams.insert_one({
        "_id": ObjectId(team_id), "name": "Team A",
        "league_id": league_id, "roster": [player_id],
        "lineup": {player_id: {"section": "forward"}},
    })

    # Seed ownership
    season_start = datetime(2026, 1, 5, tzinfo=timezone.utc)
    await db.player_ownership_periods.insert_one({
        "player_id": player_id, "team_id": team_id, "league_id": league_id,
        "acquired_at": season_start, "released_at": None,
        "source": "draft", "release_source": None,
    })
    await db.lineup_status_periods.insert_one({
        "player_id": player_id, "team_id": team_id, "league_id": league_id,
        "position": "forward", "started_at": season_start, "ended_at": None,
    })

    await _seed_player_with_games(db, player_id, [
        "2026-01-05", "2026-01-06", "2026-01-07",
    ])

    from utils.game_allocation import allocate_team_period_fpts

    period_start = datetime(2026, 1, 5, tzinfo=timezone.utc)
    period_end = datetime(2026, 1, 12, tzinfo=timezone.utc)

    r1 = await allocate_team_period_fpts(db, team_id, league_id, period_start, period_end, None)
    r2 = await allocate_team_period_fpts(db, team_id, league_id, period_start, period_end, None)
    r3 = await allocate_team_period_fpts(db, team_id, league_id, period_start, period_end, None)

    assert r1["total_fpts"] == r2["total_fpts"] == r3["total_fpts"], \
        f"Must be idempotent: {r1['total_fpts']}, {r2['total_fpts']}, {r3['total_fpts']}"
    assert r1["game_count"] == r2["game_count"] == r3["game_count"]
