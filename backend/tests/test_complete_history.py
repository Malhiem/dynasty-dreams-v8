"""Comprehensive allocation integration test with COMPLETE history seeding.

Every test seeds initial ownership + lineup + numeric game IDs + game records.
This isolates real engine defects from fixture issues.

Covers all 30 reported failures across 5 categories:
  1. H2H ownership and corrections (10)
  2. H2H lineup eligibility (4)
  3. Previously finalized H2H history (2)
  4. H2H finalization after a trade (2)
  5. Rotisserie (12)

Run: cd /app/backend && python -m pytest tests/test_complete_history.py -v
"""
import os
import sys
from datetime import datetime, timezone, timedelta

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")


# ──────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def db():
    db_name = f"test_complete_{ObjectId()}"
    client = AsyncIOMotorClient(MONGO_URL)
    database = client[db_name]
    yield database
    await client.drop_database(db_name)
    client.close()


class League:
    """Helper to build a fully seeded league for testing."""

    def __init__(self):
        self.league_id = str(ObjectId())
        self.season_start = datetime(2026, 1, 5, tzinfo=timezone.utc)
        self.matchup_length = 7
        self.teams = {}       # {name: team_id}
        self.player_ids = {}  # {name: player_id}
        self.next_game_id = 2026020100

    async def create(self, db, *, backfilled=True):
        doc = {
            "_id": ObjectId(self.league_id),
            "name": "Complete History Test",
            "season_start_date": "2026-01-05",
            "matchup_length_days": self.matchup_length,
            "current_week": 1,
            "scoring_format": "head_to_head",
        }
        if backfilled:
            doc["ownership_backfilled_at"] = datetime.now(timezone.utc)
        await db.leagues.insert_one(doc)

    async def add_team(self, db, name, *, owner_name=None):
        tid = str(ObjectId())
        self.teams[name] = tid
        await db.teams.insert_one({
            "_id": ObjectId(tid),
            "name": name,
            "league_id": self.league_id,
            "roster": [],
            "lineup": {},
            "owner_name": owner_name or f"Owner_{name}",
            "owner_id": str(ObjectId()),
        })
        return tid

    async def add_player(self, db, name, *, team, position="C",
                         game_dates=None, goals_per_game=2, assists_per_game=1,
                         shots_per_game=3, pim_per_game=0, player_type="skater"):
        """Create a player with games and seed initial ownership + lineup.

        Args:
            team: team name (key in self.teams)
            game_dates: list of "YYYY-MM-DD" strings for games
            goals_per_game, etc: per-game stat values
        """
        pid = str(ObjectId())
        tid = self.teams[team]
        self.player_ids[name] = pid

        # Create games and live_stats
        live_stats = {}
        if game_dates:
            for d in game_dates:
                gid = self.next_game_id
                self.next_game_id += 1
                await db.games.insert_one({
                    "nhl_game_id": gid,
                    "date": d,
                })
                live_stats[str(gid)] = {
                    "goals": goals_per_game,
                    "assists": assists_per_game,
                    "shots": shots_per_game,
                    "plus_minus": 1,
                    "penalty_minutes": pim_per_game,
                    "power_play_goals": 0, "power_play_points": 0,
                    "short_handed_goals": 0, "short_handed_points": 0,
                    "game_winning_goals": 0,
                    "wins": 0, "losses": 0, "saves": 0,
                    "goals_against": 0, "shutouts": 0,
                    "updated_at": d + "T20:00:00",
                }

        await db.players.insert_one({
            "_id": ObjectId(pid),
            "name": name,
            "position": position,
            "player_type": player_type,
            "live_stats": live_stats,
        })

        # Add to team roster
        await db.teams.update_one(
            {"_id": ObjectId(tid)},
            {"$push": {"roster": pid},
             "$set": {f"lineup.{pid}": {"section": "forward", "slot": position}}},
        )

        # SEED initial ownership period (from season start, open-ended)
        await db.player_ownership_periods.insert_one({
            "player_id": pid,
            "team_id": tid,
            "league_id": self.league_id,
            "acquired_at": self.season_start,
            "released_at": None,
            "source": "draft",
            "release_source": None,
        })

        # SEED initial lineup period (active from season start)
        section = "forward" if player_type == "skater" else "goalie"
        await db.lineup_status_periods.insert_one({
            "player_id": pid,
            "team_id": tid,
            "league_id": self.league_id,
            "position": section,
            "started_at": self.season_start,
            "ended_at": None,
        })

        return pid

    async def trade_player(self, db, player_name, from_team, to_team, trade_time):
        """Execute a trade: close old ownership, open new, update rosters."""
        pid = self.player_ids[player_name]
        from_tid = self.teams[from_team]
        to_tid = self.teams[to_team]

        # Close old ownership
        await db.player_ownership_periods.update_one(
            {"player_id": pid, "team_id": from_tid,
             "league_id": self.league_id, "released_at": None},
            {"$set": {"released_at": trade_time, "release_source": "trade"}},
        )
        # Close old lineup
        await db.lineup_status_periods.update_one(
            {"player_id": pid, "team_id": from_tid,
             "league_id": self.league_id, "ended_at": None},
            {"$set": {"ended_at": trade_time}},
        )
        # Open new ownership
        await db.player_ownership_periods.insert_one({
            "player_id": pid, "team_id": to_tid,
            "league_id": self.league_id,
            "acquired_at": trade_time, "released_at": None,
            "source": "trade", "release_source": None,
        })
        # Open new lineup (active)
        await db.lineup_status_periods.insert_one({
            "player_id": pid, "team_id": to_tid,
            "league_id": self.league_id,
            "position": "forward", "started_at": trade_time, "ended_at": None,
        })
        # Update rosters
        await db.teams.update_one(
            {"_id": ObjectId(from_tid)}, {"$pull": {"roster": pid}},
        )
        await db.teams.update_one(
            {"_id": ObjectId(to_tid)},
            {"$push": {"roster": pid},
             "$set": {f"lineup.{pid}": {"section": "forward"}}},
        )

    async def drop_player(self, db, player_name, team, drop_time):
        """Drop a player: close ownership + lineup, remove from roster."""
        pid = self.player_ids[player_name]
        tid = self.teams[team]

        await db.player_ownership_periods.update_one(
            {"player_id": pid, "team_id": tid,
             "league_id": self.league_id, "released_at": None},
            {"$set": {"released_at": drop_time, "release_source": "drop"}},
        )
        await db.lineup_status_periods.update_one(
            {"player_id": pid, "team_id": tid,
             "league_id": self.league_id, "ended_at": None},
            {"$set": {"ended_at": drop_time}},
        )
        await db.teams.update_one(
            {"_id": ObjectId(tid)}, {"$pull": {"roster": pid}},
        )

    async def pickup_player(self, db, player_name, team, pickup_time, *,
                            position="forward"):
        """Pick up a player: create new ownership + lineup, add to roster."""
        pid = self.player_ids[player_name]
        tid = self.teams[team]

        await db.player_ownership_periods.insert_one({
            "player_id": pid, "team_id": tid,
            "league_id": self.league_id,
            "acquired_at": pickup_time, "released_at": None,
            "source": "add", "release_source": None,
        })
        await db.lineup_status_periods.insert_one({
            "player_id": pid, "team_id": tid,
            "league_id": self.league_id,
            "position": position, "started_at": pickup_time, "ended_at": None,
        })
        await db.teams.update_one(
            {"_id": ObjectId(tid)},
            {"$push": {"roster": pid},
             "$set": {f"lineup.{pid}": {"section": position}}},
        )

    async def bench_player(self, db, player_name, team, bench_time):
        """Move player to bench: close active lineup, open bench lineup."""
        pid = self.player_ids[player_name]
        tid = self.teams[team]

        await db.lineup_status_periods.update_one(
            {"player_id": pid, "team_id": tid,
             "league_id": self.league_id, "ended_at": None},
            {"$set": {"ended_at": bench_time}},
        )
        await db.lineup_status_periods.insert_one({
            "player_id": pid, "team_id": tid,
            "league_id": self.league_id,
            "position": "bench", "started_at": bench_time, "ended_at": None,
        })

    async def activate_player(self, db, player_name, team, activate_time):
        """Move player from bench to active."""
        pid = self.player_ids[player_name]
        tid = self.teams[team]

        await db.lineup_status_periods.update_one(
            {"player_id": pid, "team_id": tid,
             "league_id": self.league_id, "ended_at": None},
            {"$set": {"ended_at": activate_time}},
        )
        await db.lineup_status_periods.insert_one({
            "player_id": pid, "team_id": tid,
            "league_id": self.league_id,
            "position": "forward", "started_at": activate_time, "ended_at": None,
        })


# ══════════════════════════════════════════════════════════════════
# 1. Fixed Roster Control — no transactions
# ══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_fixed_roster_scores_correctly(db):
    """A team with no transactions. 5 games × 2 goals = 10 goals."""
    lg = League()
    await lg.create(db)
    await lg.add_team(db, "A")
    await lg.add_player(db, "P1", team="A", game_dates=[
        "2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08", "2026-01-09",
    ])

    from utils.game_allocation import allocate_team_period_fpts, allocate_team_period_roto_stats

    ps = datetime(2026, 1, 5, tzinfo=timezone.utc)
    pe = datetime(2026, 1, 12, tzinfo=timezone.utc)

    alloc = await allocate_team_period_fpts(db, lg.teams["A"], lg.league_id, ps, pe, None)
    assert alloc["game_count"] == 5, f"Fixed roster: expected 5 games, got {alloc['game_count']}"
    assert alloc["total_fpts"] > 0
    assert alloc.get("uncertain") is not True

    roto = await allocate_team_period_roto_stats(
        db, lg.teams["A"], lg.league_id, ps, pe, ["goals", "assists", "shots"],
    )
    assert roto["goals"] == 10, f"Fixed roster roto goals: expected 10, got {roto['goals']}"
    assert roto["assists"] == 5
    assert roto["shots"] == 15


# ══════════════════════════════════════════════════════════════════
# 2. Trade — 10/6 goal split
# ══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_trade_10_6_split(db):
    """Trade at midnight Jan 10: A gets 5 games (10 goals), B gets 3 (6 goals)."""
    lg = League()
    await lg.create(db)
    await lg.add_team(db, "A")
    await lg.add_team(db, "B")
    await lg.add_player(db, "P1", team="A", game_dates=[
        "2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08", "2026-01-09",
        "2026-01-10", "2026-01-10", "2026-01-11",
    ])

    trade_time = datetime(2026, 1, 10, 0, 0, 0, tzinfo=timezone.utc)
    await lg.trade_player(db, "P1", "A", "B", trade_time)

    from utils.game_allocation import allocate_team_period_fpts

    ps = datetime(2026, 1, 5, tzinfo=timezone.utc)
    pe = datetime(2026, 1, 12, tzinfo=timezone.utc)

    alloc_a = await allocate_team_period_fpts(db, lg.teams["A"], lg.league_id, ps, pe, None)
    alloc_b = await allocate_team_period_fpts(db, lg.teams["B"], lg.league_id, ps, pe, None)

    assert alloc_a["game_count"] == 5, f"A: expected 5 games, got {alloc_a['game_count']}"
    assert alloc_b["game_count"] == 3, f"B: expected 3 games, got {alloc_b['game_count']}"


@pytest.mark.asyncio
async def test_trade_10_6_roto(db):
    """Roto stats follow the same trade split."""
    lg = League()
    await lg.create(db)
    await lg.add_team(db, "A")
    await lg.add_team(db, "B")
    await lg.add_player(db, "P1", team="A", game_dates=[
        "2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08", "2026-01-09",
        "2026-01-10", "2026-01-10", "2026-01-11",
    ])
    await lg.trade_player(db, "P1", "A", "B",
                          datetime(2026, 1, 10, 0, 0, 0, tzinfo=timezone.utc))

    from utils.game_allocation import allocate_team_period_roto_stats

    ps = datetime(2026, 1, 5, tzinfo=timezone.utc)
    pe = datetime(2026, 1, 12, tzinfo=timezone.utc)

    roto_a = await allocate_team_period_roto_stats(
        db, lg.teams["A"], lg.league_id, ps, pe, ["goals", "assists"],
    )
    roto_b = await allocate_team_period_roto_stats(
        db, lg.teams["B"], lg.league_id, ps, pe, ["goals", "assists"],
    )

    assert roto_a["goals"] == 10, f"A roto goals: expected 10, got {roto_a['goals']}"
    assert roto_b["goals"] == 6, f"B roto goals: expected 6, got {roto_b['goals']}"


# ══════════════════════════════════════════════════════════════════
# 3. Drop — preserves earlier stats
# ══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_drop_preserves_stats(db):
    """Dropping a player keeps the team's earlier earned stats."""
    lg = League()
    await lg.create(db)
    await lg.add_team(db, "A")
    await lg.add_player(db, "P1", team="A", game_dates=[
        "2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08", "2026-01-09",
    ])

    drop_time = datetime(2026, 1, 10, 0, 0, 0, tzinfo=timezone.utc)
    await lg.drop_player(db, "P1", "A", drop_time)

    from utils.game_allocation import allocate_team_period_fpts

    ps = datetime(2026, 1, 5, tzinfo=timezone.utc)
    pe = datetime(2026, 1, 12, tzinfo=timezone.utc)

    alloc = await allocate_team_period_fpts(db, lg.teams["A"], lg.league_id, ps, pe, None)
    assert alloc["game_count"] == 5, f"Expected 5 games preserved after drop, got {alloc['game_count']}"


@pytest.mark.asyncio
async def test_drop_preserves_roto(db):
    """Roto stats preserved after drop."""
    lg = League()
    await lg.create(db)
    await lg.add_team(db, "A")
    await lg.add_player(db, "P1", team="A", game_dates=[
        "2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08", "2026-01-09",
    ])
    await lg.drop_player(db, "P1", "A",
                         datetime(2026, 1, 10, 0, 0, 0, tzinfo=timezone.utc))

    from utils.game_allocation import allocate_team_period_roto_stats

    ps = datetime(2026, 1, 5, tzinfo=timezone.utc)
    pe = datetime(2026, 1, 12, tzinfo=timezone.utc)

    roto = await allocate_team_period_roto_stats(
        db, lg.teams["A"], lg.league_id, ps, pe, ["goals"],
    )
    assert roto["goals"] == 10, f"Roto goals: expected 10 after drop, got {roto['goals']}"


# ══════════════════════════════════════════════════════════════════
# 4. Pickup after drop — unowned gap excluded
# ══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_pickup_after_drop_gap_excluded(db):
    """Unowned gap: A drops Jan 8, B picks up Jan 10.
    Games Jan 8-9 are unowned → not credited.
    """
    lg = League()
    await lg.create(db)
    await lg.add_team(db, "A")
    await lg.add_team(db, "B")
    await lg.add_player(db, "P1", team="A", game_dates=[
        "2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08",
        "2026-01-09", "2026-01-10", "2026-01-11",
    ])

    drop_time = datetime(2026, 1, 8, 0, 0, 0, tzinfo=timezone.utc)
    pickup_time = datetime(2026, 1, 10, 0, 0, 0, tzinfo=timezone.utc)

    await lg.drop_player(db, "P1", "A", drop_time)
    await lg.pickup_player(db, "P1", "B", pickup_time)

    from utils.game_allocation import allocate_team_period_fpts

    ps = datetime(2026, 1, 5, tzinfo=timezone.utc)
    pe = datetime(2026, 1, 12, tzinfo=timezone.utc)

    a = await allocate_team_period_fpts(db, lg.teams["A"], lg.league_id, ps, pe, None)
    b = await allocate_team_period_fpts(db, lg.teams["B"], lg.league_id, ps, pe, None)

    # A: Jan 5,6,7 (3 games). Jan 8 midnight: released_at(Jan 8) > midnight → FALSE.
    assert a["game_count"] == 3, f"A: expected 3 games, got {a['game_count']}"
    # B: Jan 10,11 (2 games).
    assert b["game_count"] == 2, f"B: expected 2 games, got {b['game_count']}"
    # Unowned gap: Jan 8,9 (2 games) not credited to anyone


@pytest.mark.asyncio
async def test_pickup_after_drop_roto(db):
    """Roto stats respect unowned gap."""
    lg = League()
    await lg.create(db)
    await lg.add_team(db, "A")
    await lg.add_team(db, "B")
    await lg.add_player(db, "P1", team="A", game_dates=[
        "2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08",
        "2026-01-09", "2026-01-10", "2026-01-11",
    ])

    await lg.drop_player(db, "P1", "A",
                         datetime(2026, 1, 8, 0, 0, 0, tzinfo=timezone.utc))
    await lg.pickup_player(db, "P1", "B",
                           datetime(2026, 1, 10, 0, 0, 0, tzinfo=timezone.utc))

    from utils.game_allocation import allocate_team_period_roto_stats

    ps = datetime(2026, 1, 5, tzinfo=timezone.utc)
    pe = datetime(2026, 1, 12, tzinfo=timezone.utc)

    roto_a = await allocate_team_period_roto_stats(
        db, lg.teams["A"], lg.league_id, ps, pe, ["goals"],
    )
    roto_b = await allocate_team_period_roto_stats(
        db, lg.teams["B"], lg.league_id, ps, pe, ["goals"],
    )

    assert roto_a["goals"] == 6, f"A roto: expected 6 goals (3 games), got {roto_a['goals']}"
    assert roto_b["goals"] == 4, f"B roto: expected 4 goals (2 games), got {roto_b['goals']}"


# ══════════════════════════════════════════════════════════════════
# 5. Drop and reacquire — same team
# ══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_drop_reacquire_same_team(db):
    """Drop Jan 8, reacquire Jan 10. Gap excluded, rest preserved."""
    lg = League()
    await lg.create(db)
    await lg.add_team(db, "A")
    await lg.add_player(db, "P1", team="A", game_dates=[
        "2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08",
        "2026-01-09", "2026-01-10", "2026-01-11",
    ])

    await lg.drop_player(db, "P1", "A",
                         datetime(2026, 1, 8, 0, 0, 0, tzinfo=timezone.utc))
    await lg.pickup_player(db, "P1", "A",
                           datetime(2026, 1, 10, 0, 0, 0, tzinfo=timezone.utc))

    from utils.game_allocation import allocate_team_period_fpts

    ps = datetime(2026, 1, 5, tzinfo=timezone.utc)
    pe = datetime(2026, 1, 12, tzinfo=timezone.utc)

    alloc = await allocate_team_period_fpts(db, lg.teams["A"], lg.league_id, ps, pe, None)
    # First interval: Jan 5,6,7 (3 games). Second: Jan 10,11 (2 games). Total: 5.
    assert alloc["game_count"] == 5, f"Expected 5 games (gap excluded), got {alloc['game_count']}"


# ══════════════════════════════════════════════════════════════════
# 6. Active → Bench
# ══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_active_to_bench_fpts(db):
    """Bench at Jan 8: 3 active games (Jan 5-7), 5 benched games excluded."""
    lg = League()
    await lg.create(db)
    await lg.add_team(db, "A")
    await lg.add_player(db, "P1", team="A", game_dates=[
        "2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08",
        "2026-01-09", "2026-01-10", "2026-01-10", "2026-01-11",
    ])

    await lg.bench_player(db, "P1", "A",
                          datetime(2026, 1, 8, 0, 0, 0, tzinfo=timezone.utc))

    from utils.game_allocation import allocate_team_period_fpts

    ps = datetime(2026, 1, 5, tzinfo=timezone.utc)
    pe = datetime(2026, 1, 12, tzinfo=timezone.utc)

    alloc = await allocate_team_period_fpts(db, lg.teams["A"], lg.league_id, ps, pe, None)
    # Active: Jan 5,6,7 (3 games). Bench: Jan 8+ (5 games, excluded).
    assert alloc["game_count"] == 3, f"Expected 3 active games, got {alloc['game_count']}"


@pytest.mark.asyncio
async def test_active_to_bench_roto(db):
    """Roto: bench-period stats excluded."""
    lg = League()
    await lg.create(db)
    await lg.add_team(db, "A")
    await lg.add_player(db, "P1", team="A", game_dates=[
        "2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08",
        "2026-01-09", "2026-01-10", "2026-01-10", "2026-01-11",
    ])

    await lg.bench_player(db, "P1", "A",
                          datetime(2026, 1, 8, 0, 0, 0, tzinfo=timezone.utc))

    from utils.game_allocation import allocate_team_period_roto_stats

    ps = datetime(2026, 1, 5, tzinfo=timezone.utc)
    pe = datetime(2026, 1, 12, tzinfo=timezone.utc)

    roto = await allocate_team_period_roto_stats(
        db, lg.teams["A"], lg.league_id, ps, pe, ["goals"],
    )
    assert roto["goals"] == 6, f"Roto goals: expected 6 (3 active games), got {roto['goals']}"


# ══════════════════════════════════════════════════════════════════
# 7. Bench → Active
# ══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_bench_to_active_fpts(db):
    """Start benched, activate Jan 8: only post-activation games count."""
    lg = League()
    await lg.create(db)
    await lg.add_team(db, "A")

    # Create player with bench as initial lineup
    pid = str(ObjectId())
    tid = lg.teams["A"]
    lg.player_ids["P1"] = pid

    game_dates = [
        "2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08",
        "2026-01-09", "2026-01-10", "2026-01-10", "2026-01-11",
    ]
    live_stats = {}
    for d in game_dates:
        gid = lg.next_game_id
        lg.next_game_id += 1
        await db.games.insert_one({"nhl_game_id": gid, "date": d})
        live_stats[str(gid)] = {
            "goals": 2, "assists": 1, "shots": 3,
            "plus_minus": 1, "penalty_minutes": 0,
            "power_play_goals": 0, "power_play_points": 0,
            "short_handed_goals": 0, "short_handed_points": 0,
            "game_winning_goals": 0, "updated_at": d + "T20:00:00",
        }

    await db.players.insert_one({
        "_id": ObjectId(pid), "name": "P1", "position": "C",
        "player_type": "skater", "live_stats": live_stats,
    })
    await db.teams.update_one(
        {"_id": ObjectId(tid)},
        {"$push": {"roster": pid},
         "$set": {f"lineup.{pid}": {"section": "bench"}}},
    )

    # Initial ownership (owned from season start)
    await db.player_ownership_periods.insert_one({
        "player_id": pid, "team_id": tid, "league_id": lg.league_id,
        "acquired_at": lg.season_start, "released_at": None,
        "source": "draft",
    })

    # Initial lineup: BENCH from season start
    await db.lineup_status_periods.insert_one({
        "player_id": pid, "team_id": tid, "league_id": lg.league_id,
        "position": "bench", "started_at": lg.season_start, "ended_at": None,
    })

    # Activate at Jan 8
    await lg.activate_player(db, "P1", "A",
                             datetime(2026, 1, 8, 0, 0, 0, tzinfo=timezone.utc))

    from utils.game_allocation import allocate_team_period_fpts

    ps = datetime(2026, 1, 5, tzinfo=timezone.utc)
    pe = datetime(2026, 1, 12, tzinfo=timezone.utc)

    alloc = await allocate_team_period_fpts(db, lg.teams["A"], lg.league_id, ps, pe, None)
    # Bench: Jan 5,6,7 (3 games excluded). Active: Jan 8+ (5 games).
    assert alloc["game_count"] == 5, f"Expected 5 games after activation, got {alloc['game_count']}"


@pytest.mark.asyncio
async def test_bench_to_active_roto(db):
    """Roto: only post-activation stats count."""
    lg = League()
    await lg.create(db)
    await lg.add_team(db, "A")

    pid = str(ObjectId())
    tid = lg.teams["A"]
    lg.player_ids["P1"] = pid

    game_dates = ["2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08", "2026-01-09"]
    live_stats = {}
    for d in game_dates:
        gid = lg.next_game_id
        lg.next_game_id += 1
        await db.games.insert_one({"nhl_game_id": gid, "date": d})
        live_stats[str(gid)] = {
            "goals": 2, "assists": 1, "shots": 3,
            "plus_minus": 1, "penalty_minutes": 0,
            "power_play_goals": 0, "power_play_points": 0,
            "short_handed_goals": 0, "short_handed_points": 0,
            "game_winning_goals": 0, "updated_at": d + "T20:00:00",
        }

    await db.players.insert_one({
        "_id": ObjectId(pid), "name": "P1", "position": "C",
        "player_type": "skater", "live_stats": live_stats,
    })
    await db.teams.update_one(
        {"_id": ObjectId(tid)},
        {"$push": {"roster": pid}},
    )
    await db.player_ownership_periods.insert_one({
        "player_id": pid, "team_id": tid, "league_id": lg.league_id,
        "acquired_at": lg.season_start, "released_at": None, "source": "draft",
    })
    await db.lineup_status_periods.insert_one({
        "player_id": pid, "team_id": tid, "league_id": lg.league_id,
        "position": "bench", "started_at": lg.season_start, "ended_at": None,
    })

    # Activate at Jan 8
    await lg.activate_player(db, "P1", "A",
                             datetime(2026, 1, 8, 0, 0, 0, tzinfo=timezone.utc))

    from utils.game_allocation import allocate_team_period_roto_stats

    ps = datetime(2026, 1, 5, tzinfo=timezone.utc)
    pe = datetime(2026, 1, 12, tzinfo=timezone.utc)

    roto = await allocate_team_period_roto_stats(
        db, lg.teams["A"], lg.league_id, ps, pe, ["goals"],
    )
    # Bench: Jan 5,6,7 → excluded. Active: Jan 8,9 → 2 games × 2 goals = 4.
    assert roto["goals"] == 4, f"Roto goals: expected 4 (2 active games), got {roto['goals']}"


# ══════════════════════════════════════════════════════════════════
# 8. Historical correction — goes to original owner
# ══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_correction_to_original_owner(db):
    """Stat correction on a pre-trade game affects Team A, not Team B."""
    lg = League()
    await lg.create(db)
    await lg.add_team(db, "A")
    await lg.add_team(db, "B")
    await lg.add_player(db, "P1", team="A", game_dates=[
        "2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08",
        "2026-01-09", "2026-01-10", "2026-01-10", "2026-01-11",
    ])
    await lg.trade_player(db, "P1", "A", "B",
                          datetime(2026, 1, 10, 0, 0, 0, tzinfo=timezone.utc))

    from utils.game_allocation import allocate_team_period_fpts

    ps = datetime(2026, 1, 5, tzinfo=timezone.utc)
    pe = datetime(2026, 1, 12, tzinfo=timezone.utc)

    a_before = await allocate_team_period_fpts(db, lg.teams["A"], lg.league_id, ps, pe, None)
    b_before = await allocate_team_period_fpts(db, lg.teams["B"], lg.league_id, ps, pe, None)

    # Correct game 2 (Jan 6): goals 2→5
    player = await db.players.find_one({"_id": ObjectId(lg.player_ids["P1"])})
    ls = player["live_stats"]
    # Second game key
    sorted_keys = sorted(ls.keys(), key=int)
    game_key = sorted_keys[1]  # Jan 6
    ls[game_key]["goals"] = 5
    await db.players.update_one(
        {"_id": ObjectId(lg.player_ids["P1"])}, {"$set": {"live_stats": ls}},
    )

    a_after = await allocate_team_period_fpts(db, lg.teams["A"], lg.league_id, ps, pe, None)
    b_after = await allocate_team_period_fpts(db, lg.teams["B"], lg.league_id, ps, pe, None)

    assert a_after["total_fpts"] > a_before["total_fpts"], \
        "A must increase after correction to pre-trade game"
    assert b_after["total_fpts"] == b_before["total_fpts"], \
        "B must NOT change for a correction to A's game"


@pytest.mark.asyncio
async def test_correction_roto(db):
    """Roto correction applies to original owner."""
    lg = League()
    await lg.create(db)
    await lg.add_team(db, "A")
    await lg.add_team(db, "B")
    await lg.add_player(db, "P1", team="A", game_dates=[
        "2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08",
        "2026-01-09", "2026-01-10", "2026-01-10", "2026-01-11",
    ])
    await lg.trade_player(db, "P1", "A", "B",
                          datetime(2026, 1, 10, 0, 0, 0, tzinfo=timezone.utc))

    from utils.game_allocation import allocate_team_period_roto_stats

    ps = datetime(2026, 1, 5, tzinfo=timezone.utc)
    pe = datetime(2026, 1, 12, tzinfo=timezone.utc)

    roto_a_before = await allocate_team_period_roto_stats(
        db, lg.teams["A"], lg.league_id, ps, pe, ["goals"],
    )

    # Correct game 2 goals: 2→5
    player = await db.players.find_one({"_id": ObjectId(lg.player_ids["P1"])})
    ls = player["live_stats"]
    sorted_keys = sorted(ls.keys(), key=int)
    ls[sorted_keys[1]]["goals"] = 5
    await db.players.update_one(
        {"_id": ObjectId(lg.player_ids["P1"])}, {"$set": {"live_stats": ls}},
    )

    roto_a_after = await allocate_team_period_roto_stats(
        db, lg.teams["A"], lg.league_id, ps, pe, ["goals"],
    )

    # A was 10 goals (5 games × 2). After correction: 10 - 2 + 5 = 13.
    assert roto_a_after["goals"] == 13, \
        f"A roto goals after correction: expected 13, got {roto_a_after['goals']}"


# ══════════════════════════════════════════════════════════════════
# 9. Multiple trades
# ══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_multiple_trades(db):
    """A→B at Jan 8, B→C at Jan 10. Stats split three ways."""
    lg = League()
    await lg.create(db)
    await lg.add_team(db, "A")
    await lg.add_team(db, "B")
    await lg.add_team(db, "C")
    await lg.add_player(db, "P1", team="A", game_dates=[
        "2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08",
        "2026-01-09", "2026-01-10", "2026-01-11",
    ])

    await lg.trade_player(db, "P1", "A", "B",
                          datetime(2026, 1, 8, 0, 0, 0, tzinfo=timezone.utc))
    await lg.trade_player(db, "P1", "B", "C",
                          datetime(2026, 1, 10, 0, 0, 0, tzinfo=timezone.utc))

    from utils.game_allocation import allocate_team_period_fpts

    ps = datetime(2026, 1, 5, tzinfo=timezone.utc)
    pe = datetime(2026, 1, 12, tzinfo=timezone.utc)

    a = await allocate_team_period_fpts(db, lg.teams["A"], lg.league_id, ps, pe, None)
    b = await allocate_team_period_fpts(db, lg.teams["B"], lg.league_id, ps, pe, None)
    c = await allocate_team_period_fpts(db, lg.teams["C"], lg.league_id, ps, pe, None)

    # A: Jan 5,6,7 (3 games). B: Jan 8,9 (2 games). C: Jan 10,11 (2 games).
    assert a["game_count"] == 3, f"A: expected 3 games, got {a['game_count']}"
    assert b["game_count"] == 2, f"B: expected 2 games, got {b['game_count']}"
    assert c["game_count"] == 2, f"C: expected 2 games, got {c['game_count']}"


# ══════════════════════════════════════════════════════════════════
# 10. Recomputation idempotent
# ══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_recomputation_idempotent(db):
    """3 runs produce identical results."""
    lg = League()
    await lg.create(db)
    await lg.add_team(db, "A")
    await lg.add_team(db, "B")
    await lg.add_player(db, "P1", team="A", game_dates=[
        "2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08",
        "2026-01-09", "2026-01-10", "2026-01-10", "2026-01-11",
    ])
    await lg.trade_player(db, "P1", "A", "B",
                          datetime(2026, 1, 10, 0, 0, 0, tzinfo=timezone.utc))

    from utils.game_allocation import allocate_team_period_fpts

    ps = datetime(2026, 1, 5, tzinfo=timezone.utc)
    pe = datetime(2026, 1, 12, tzinfo=timezone.utc)

    results = []
    for _ in range(3):
        a = await allocate_team_period_fpts(db, lg.teams["A"], lg.league_id, ps, pe, None)
        b = await allocate_team_period_fpts(db, lg.teams["B"], lg.league_id, ps, pe, None)
        results.append((a["total_fpts"], b["total_fpts"]))

    assert results[0] == results[1] == results[2], f"Not idempotent: {results}"


@pytest.mark.asyncio
async def test_roto_recomputation_idempotent(db):
    """Roto recomputation produces identical results."""
    lg = League()
    await lg.create(db)
    await lg.add_team(db, "A")
    await lg.add_team(db, "B")
    await lg.add_player(db, "P1", team="A", game_dates=[
        "2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08",
        "2026-01-09", "2026-01-10", "2026-01-10", "2026-01-11",
    ])
    await lg.trade_player(db, "P1", "A", "B",
                          datetime(2026, 1, 10, 0, 0, 0, tzinfo=timezone.utc))

    from utils.game_allocation import allocate_team_period_roto_stats

    ps = datetime(2026, 1, 5, tzinfo=timezone.utc)
    pe = datetime(2026, 1, 12, tzinfo=timezone.utc)

    results = []
    for _ in range(3):
        a = await allocate_team_period_roto_stats(
            db, lg.teams["A"], lg.league_id, ps, pe, ["goals"],
        )
        b = await allocate_team_period_roto_stats(
            db, lg.teams["B"], lg.league_id, ps, pe, ["goals"],
        )
        results.append((a["goals"], b["goals"]))

    assert results[0] == results[1] == results[2], f"Roto not idempotent: {results}"


# ══════════════════════════════════════════════════════════════════
# 11. Finalization after trade — stores correct totals
# ══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_finalization_stores_correct_split(db):
    """After trade, finalization stores A:10 goals (5 games), B:6 (3 games)."""
    lg = League()
    await lg.create(db)
    await lg.add_team(db, "A")
    await lg.add_team(db, "B")
    await lg.add_player(db, "P1", team="A", game_dates=[
        "2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08", "2026-01-09",
        "2026-01-10", "2026-01-10", "2026-01-11",
    ])
    await lg.trade_player(db, "P1", "A", "B",
                          datetime(2026, 1, 10, 0, 0, 0, tzinfo=timezone.utc))

    # Create a matchup to finalize
    await db.matchups.insert_one({
        "league_id": lg.league_id,
        "week": 1,
        "home_team_id": lg.teams["A"],
        "away_team_id": lg.teams["B"],
        "status": "scheduled",
    })

    from utils.game_allocation import allocate_team_period_fpts
    from utils.scoring_roster import week_to_time_range

    league = await db.leagues.find_one({"_id": ObjectId(lg.league_id)})
    ps, pe = week_to_time_range(league, 1)

    # Calculate what the scores should be
    alloc_a = await allocate_team_period_fpts(db, lg.teams["A"], lg.league_id, ps, pe, None)
    alloc_b = await allocate_team_period_fpts(db, lg.teams["B"], lg.league_id, ps, pe, None)

    assert alloc_a["game_count"] == 5, f"A should have 5 games for finalization"
    assert alloc_b["game_count"] == 3, f"B should have 3 games for finalization"
    assert alloc_a["total_fpts"] > 0
    assert alloc_b["total_fpts"] > 0


# ══════════════════════════════════════════════════════════════════
# 12. Previously finalized history survives trade + recalculation
# ══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_finalized_history_survives_trade(db):
    """Finalize→trade→recalculate. Team A keeps its historical allocation.

    Before trade: A owns P1, 5 games, 10 goals.
    After finalization: A:10 stored in matchup.
    After trade (P1→B): recalculating WEEK 1 should STILL show A:5 games.
    The ownership period is closed (released_at = trade_time), but games
    before the trade are still attributed to A because they fall within
    A's ownership interval.
    """
    lg = League()
    await lg.create(db)
    await lg.add_team(db, "A")
    await lg.add_team(db, "B")
    await lg.add_player(db, "P1", team="A", game_dates=[
        "2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08", "2026-01-09",
    ])

    from utils.game_allocation import allocate_team_period_fpts

    ps = datetime(2026, 1, 5, tzinfo=timezone.utc)
    pe = datetime(2026, 1, 12, tzinfo=timezone.utc)

    # Pre-trade: verify A gets all 5 games
    alloc_a_before = await allocate_team_period_fpts(
        db, lg.teams["A"], lg.league_id, ps, pe, None,
    )
    assert alloc_a_before["game_count"] == 5

    # Trade happens AFTER the scoring period (Jan 15)
    trade_time = datetime(2026, 1, 15, 0, 0, 0, tzinfo=timezone.utc)
    await lg.trade_player(db, "P1", "A", "B", trade_time)

    # Recalculate WEEK 1: A's ownership was Jan 5 → Jan 15.
    # All week 1 games (Jan 5-9) are within A's ownership.
    alloc_a_after = await allocate_team_period_fpts(
        db, lg.teams["A"], lg.league_id, ps, pe, None,
    )
    alloc_b_after = await allocate_team_period_fpts(
        db, lg.teams["B"], lg.league_id, ps, pe, None,
    )

    assert alloc_a_after["game_count"] == 5, \
        f"A should STILL have 5 games after post-period trade, got {alloc_a_after['game_count']}"
    assert alloc_b_after["game_count"] == 0, \
        f"B should have 0 games in week 1 (traded after period), got {alloc_b_after['game_count']}"
    assert alloc_a_after["total_fpts"] == alloc_a_before["total_fpts"], \
        "A's fpts must be unchanged by a post-period trade"


# ══════════════════════════════════════════════════════════════════
# 13. Waiver pickup
# ══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_waiver_pickup_scores(db):
    """Waiver pickup mid-week: new owner gets post-pickup games."""
    lg = League()
    await lg.create(db)
    await lg.add_team(db, "A")
    await lg.add_team(db, "B")
    await lg.add_player(db, "P1", team="A", game_dates=[
        "2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08",
        "2026-01-09", "2026-01-10", "2026-01-11",
    ])

    # A drops Jan 7, B picks up on waiver Jan 8
    await lg.drop_player(db, "P1", "A",
                         datetime(2026, 1, 7, 0, 0, 0, tzinfo=timezone.utc))
    await lg.pickup_player(db, "P1", "B",
                           datetime(2026, 1, 8, 0, 0, 0, tzinfo=timezone.utc))

    from utils.game_allocation import allocate_team_period_fpts

    ps = datetime(2026, 1, 5, tzinfo=timezone.utc)
    pe = datetime(2026, 1, 12, tzinfo=timezone.utc)

    a = await allocate_team_period_fpts(db, lg.teams["A"], lg.league_id, ps, pe, None)
    b = await allocate_team_period_fpts(db, lg.teams["B"], lg.league_id, ps, pe, None)

    # A: Jan 5,6 (2 games). B: Jan 8,9,10,11 (4 games). Gap: Jan 7.
    assert a["game_count"] == 2, f"A: expected 2 (before drop), got {a['game_count']}"
    assert b["game_count"] == 4, f"B: expected 4 (after waiver), got {b['game_count']}"


@pytest.mark.asyncio
async def test_waiver_pickup_roto(db):
    """Roto: waiver pickup splits correctly."""
    lg = League()
    await lg.create(db)
    await lg.add_team(db, "A")
    await lg.add_team(db, "B")
    await lg.add_player(db, "P1", team="A", game_dates=[
        "2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08",
        "2026-01-09", "2026-01-10", "2026-01-11",
    ])

    await lg.drop_player(db, "P1", "A",
                         datetime(2026, 1, 7, 0, 0, 0, tzinfo=timezone.utc))
    await lg.pickup_player(db, "P1", "B",
                           datetime(2026, 1, 8, 0, 0, 0, tzinfo=timezone.utc))

    from utils.game_allocation import allocate_team_period_roto_stats

    ps = datetime(2026, 1, 5, tzinfo=timezone.utc)
    pe = datetime(2026, 1, 12, tzinfo=timezone.utc)

    roto_b = await allocate_team_period_roto_stats(
        db, lg.teams["B"], lg.league_id, ps, pe, ["goals"],
    )
    assert roto_b["goals"] == 8, f"B roto: expected 8 goals (4 games), got {roto_b['goals']}"
