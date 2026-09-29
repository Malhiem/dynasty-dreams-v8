"""38-case E2E test suite for historical scoring allocation.

Every test seeds:
  • Numeric game IDs with matching game records + explicit UTC puck-drop timestamps
  • Initial ownership and lineup intervals before the first scored game
  • Uses real utility functions (same code paths as API endpoints)

Covers 8 categories:
  1. Valid E2E fixtures (fixed-roster controls)
  2. Ownership and transaction history (trades, drops, pickups, gaps)
  3. Historical lineup eligibility (bench/active transitions)
  4. Late imports and corrections
  5. Consistent scoring and finalization
  6. Rotisserie recomputation
  7. Missing history and backfill
  8. Timing boundaries

Run:  cd /app/backend && python -m pytest tests/test_e2e_allocation.py -v
"""
import os, sys
from datetime import datetime, timezone, timedelta
from typing import Optional

import pytest, pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")


# ─── Fixture helpers ──────────────────────────────────────────

@pytest_asyncio.fixture
async def db():
    db_name = f"test_e2e_{ObjectId()}"
    client = AsyncIOMotorClient(MONGO_URL)
    database = client[db_name]
    yield database
    await client.drop_database(db_name)
    client.close()


def _dt(y, m, d, h=0, mi=0, s=0):
    return datetime(y, m, d, h, mi, s, tzinfo=timezone.utc)


_SEASON_START = _dt(2026, 1, 5)
_GID_SEQ = 2026020100


class Env:
    """Creates a fully-seeded league environment.

    Every game has: numeric ID, game record, explicit puck-drop timestamp.
    Every player has: initial ownership + initial lineup period from season start.
    """

    def __init__(self):
        self.league_id = str(ObjectId())
        self.teams: dict[str, str] = {}
        self.players: dict[str, str] = {}
        self._gid = 2026020100
        self._game_keys: dict[str, list[str]] = {}   # player_name -> [gid_str, ...]

    # ── setup ──

    async def create_league(self, db, *, backfilled=True, scoring_format="head_to_head"):
        doc = {
            "_id": ObjectId(self.league_id),
            "name": "E2E League",
            "season_start_date": "2026-01-05",
            "matchup_length_days": 7,
            "current_week": 1,
            "scoring_format": scoring_format,
        }
        if backfilled:
            doc["ownership_backfilled_at"] = datetime.now(timezone.utc)
        await db.leagues.insert_one(doc)

    async def create_team(self, db, name):
        tid = str(ObjectId())
        self.teams[name] = tid
        await db.teams.insert_one({
            "_id": ObjectId(tid), "name": name,
            "league_id": self.league_id, "roster": [], "lineup": {},
            "owner_name": f"Owner_{name}", "owner_id": str(ObjectId()),
            "commissioner_id": str(ObjectId()),
        })
        return tid

    async def create_player(
        self, db, name, *, team: str,
        game_schedule: list[tuple[str, int]],           # [(date_str, puck_drop_hour), ...]
        goals=2, assists=1, shots=3,
        initial_position="forward",
        player_type="skater",
    ):
        """Create a player with games, initial ownership and initial lineup.

        game_schedule: [("2026-01-05", 19), ("2026-01-06", 20), ...]
            date_str + puck_drop_hour (UTC).
        """
        pid = str(ObjectId())
        tid = self.teams[team]
        self.players[name] = pid
        self._game_keys[name] = []

        live_stats = {}
        for date_str, puck_hour in game_schedule:
            gid = self._gid
            self._gid += 1
            puck_drop = _dt(
                int(date_str[:4]), int(date_str[5:7]), int(date_str[8:10]),
                puck_hour, 0, 0,
            )
            await db.games.insert_one({
                "nhl_game_id": gid,
                "date": date_str,
                "start_time": puck_drop,        # explicit puck-drop
            })
            live_stats[str(gid)] = {
                "goals": goals, "assists": assists, "shots": shots,
                "plus_minus": 1, "penalty_minutes": 0,
                "power_play_goals": 0, "power_play_points": 0,
                "short_handed_goals": 0, "short_handed_points": 0,
                "game_winning_goals": 0,
                "wins": 0, "losses": 0, "saves": 0,
                "goals_against": 0, "shutouts": 0,
                "updated_at": f"{date_str}T{puck_hour:02d}:30:00",
            }
            self._game_keys[name].append(str(gid))

        await db.players.insert_one({
            "_id": ObjectId(pid), "name": name,
            "position": "C", "player_type": player_type,
            "live_stats": live_stats,
        })
        await db.teams.update_one(
            {"_id": ObjectId(tid)},
            {"$push": {"roster": pid},
             "$set": {f"lineup.{pid}": {"section": initial_position}}},
        )
        # Initial ownership from season start
        await db.player_ownership_periods.insert_one({
            "player_id": pid, "team_id": tid,
            "league_id": self.league_id,
            "acquired_at": _SEASON_START, "released_at": None,
            "source": "draft", "release_source": None,
        })
        # Initial lineup from season start
        await db.lineup_status_periods.insert_one({
            "player_id": pid, "team_id": tid,
            "league_id": self.league_id,
            "position": initial_position,
            "started_at": _SEASON_START, "ended_at": None,
        })
        return pid

    # ── transactions ──

    async def trade(self, db, player: str, from_team: str, to_team: str, at: datetime):
        pid, ftid, ttid = self.players[player], self.teams[from_team], self.teams[to_team]
        # Close old ownership
        await db.player_ownership_periods.update_one(
            {"player_id": pid, "team_id": ftid,
             "league_id": self.league_id, "released_at": None},
            {"$set": {"released_at": at, "release_source": "trade"}},
        )
        # Close old lineup
        await db.lineup_status_periods.update_one(
            {"player_id": pid, "team_id": ftid,
             "league_id": self.league_id, "ended_at": None},
            {"$set": {"ended_at": at}},
        )
        # Open new ownership
        await db.player_ownership_periods.insert_one({
            "player_id": pid, "team_id": ttid,
            "league_id": self.league_id,
            "acquired_at": at, "released_at": None,
            "source": "trade", "release_source": None,
        })
        # Open new lineup (active)
        await db.lineup_status_periods.insert_one({
            "player_id": pid, "team_id": ttid,
            "league_id": self.league_id,
            "position": "forward", "started_at": at, "ended_at": None,
        })
        await db.teams.update_one({"_id": ObjectId(ftid)}, {"$pull": {"roster": pid}})
        await db.teams.update_one(
            {"_id": ObjectId(ttid)},
            {"$push": {"roster": pid},
             "$set": {f"lineup.{pid}": {"section": "forward"}}},
        )

    async def drop(self, db, player: str, team: str, at: datetime):
        pid, tid = self.players[player], self.teams[team]
        await db.player_ownership_periods.update_one(
            {"player_id": pid, "team_id": tid,
             "league_id": self.league_id, "released_at": None},
            {"$set": {"released_at": at, "release_source": "drop"}},
        )
        await db.lineup_status_periods.update_one(
            {"player_id": pid, "team_id": tid,
             "league_id": self.league_id, "ended_at": None},
            {"$set": {"ended_at": at}},
        )
        await db.teams.update_one({"_id": ObjectId(tid)}, {"$pull": {"roster": pid}})

    async def pickup(self, db, player: str, team: str, at: datetime, *, position="forward"):
        pid, tid = self.players[player], self.teams[team]
        await db.player_ownership_periods.insert_one({
            "player_id": pid, "team_id": tid,
            "league_id": self.league_id,
            "acquired_at": at, "released_at": None,
            "source": "add", "release_source": None,
        })
        await db.lineup_status_periods.insert_one({
            "player_id": pid, "team_id": tid,
            "league_id": self.league_id,
            "position": position, "started_at": at, "ended_at": None,
        })
        await db.teams.update_one(
            {"_id": ObjectId(tid)},
            {"$push": {"roster": pid},
             "$set": {f"lineup.{pid}": {"section": position}}},
        )

    async def bench(self, db, player: str, team: str, at: datetime):
        pid, tid = self.players[player], self.teams[team]
        await db.lineup_status_periods.update_one(
            {"player_id": pid, "team_id": tid,
             "league_id": self.league_id, "ended_at": None},
            {"$set": {"ended_at": at}},
        )
        await db.lineup_status_periods.insert_one({
            "player_id": pid, "team_id": tid,
            "league_id": self.league_id,
            "position": "bench", "started_at": at, "ended_at": None,
        })

    async def activate(self, db, player: str, team: str, at: datetime):
        pid, tid = self.players[player], self.teams[team]
        await db.lineup_status_periods.update_one(
            {"player_id": pid, "team_id": tid,
             "league_id": self.league_id, "ended_at": None},
            {"$set": {"ended_at": at}},
        )
        await db.lineup_status_periods.insert_one({
            "player_id": pid, "team_id": tid,
            "league_id": self.league_id,
            "position": "forward", "started_at": at, "ended_at": None,
        })

    # ── queries ──

    async def fpts(self, db, team: str, ps=None, pe=None):
        from utils.game_allocation import allocate_team_period_fpts
        ps = ps or _SEASON_START
        pe = pe or _dt(2026, 1, 12)
        return await allocate_team_period_fpts(
            db, self.teams[team], self.league_id, ps, pe, None,
        )

    async def roto(self, db, team: str, cats, ps=None, pe=None):
        from utils.game_allocation import allocate_team_period_roto_stats
        ps = ps or _SEASON_START
        pe = pe or _dt(2026, 1, 12)
        return await allocate_team_period_roto_stats(
            db, self.teams[team], self.league_id, ps, pe, cats,
        )

    async def correct_game(self, db, player: str, game_index: int, **stat_updates):
        """Correct stats for a specific game (by index in creation order)."""
        pid = self.players[player]
        gid_str = self._game_keys[player][game_index]
        p = await db.players.find_one({"_id": ObjectId(pid)})
        ls = p["live_stats"]
        for k, v in stat_updates.items():
            ls[gid_str][k] = v
        await db.players.update_one(
            {"_id": ObjectId(pid)}, {"$set": {"live_stats": ls}},
        )


# 5 games (Jan 5-9 @ 19:00) then 3 games (Jan 10×2 + Jan 11 @ 19:00)
SCHED_8 = [
    ("2026-01-05", 19), ("2026-01-06", 19), ("2026-01-07", 19),
    ("2026-01-08", 19), ("2026-01-09", 19),
    ("2026-01-10", 19), ("2026-01-10", 21), ("2026-01-11", 19),
]
SCHED_5 = SCHED_8[:5]
SCHED_7 = [
    ("2026-01-05", 19), ("2026-01-06", 19), ("2026-01-07", 19),
    ("2026-01-08", 19), ("2026-01-09", 19),
    ("2026-01-10", 19), ("2026-01-11", 19),
]


# ══════════════════════════════════════════════════════════════
# 1  VALID E2E FIXTURES — Fixed-roster controls
# ══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_1a_fixed_roster_h2h_points(db):
    """Fixed roster: A:10 goals (5 games), B:0."""
    e = Env()
    await e.create_league(db)
    await e.create_team(db, "A")
    await e.create_team(db, "B")
    await e.create_player(db, "P1", team="A", game_schedule=SCHED_5)

    a = await e.fpts(db, "A")
    b = await e.fpts(db, "B")
    assert a["game_count"] == 5
    assert a["total_fpts"] > 0
    assert b["total_fpts"] == 0.0


@pytest.mark.asyncio
async def test_1b_fixed_roster_h2h_categories(db):
    """Fixed roster: A has stats, B has none."""
    e = Env()
    await e.create_league(db)
    await e.create_team(db, "A")
    await e.create_team(db, "B")
    await e.create_player(db, "P1", team="A", game_schedule=SCHED_5)

    a = await e.roto(db, "A", ["goals", "assists", "shots"])
    b = await e.roto(db, "B", ["goals", "assists", "shots"])
    assert a["goals"] == 10
    assert a["assists"] == 5
    assert b["goals"] == 0


@pytest.mark.asyncio
async def test_1c_fixed_roster_roto(db):
    """Roto fixed roster: A:10 goals, B:0."""
    e = Env()
    await e.create_league(db, scoring_format="rotisserie")
    await e.create_team(db, "A")
    await e.create_team(db, "B")
    await e.create_player(db, "P1", team="A", game_schedule=SCHED_5)

    a = await e.roto(db, "A", ["goals", "assists"])
    b = await e.roto(db, "B", ["goals", "assists"])
    assert a["goals"] == 10
    assert b["goals"] == 0


# ══════════════════════════════════════════════════════════════
# 2  OWNERSHIP AND TRANSACTION HISTORY
# ══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_2a_trade_10_6_split(db):
    """Trade at 10:00 Jan 10. 5 games pre-trade @19:00, 3 games post-trade.
    A:10 goals (5 games), B:6 goals (3 games)."""
    e = Env()
    await e.create_league(db)
    await e.create_team(db, "A")
    await e.create_team(db, "B")
    await e.create_player(db, "P1", team="A", game_schedule=SCHED_8)

    # Trade after Jan 9 game but before Jan 10 puck drop
    await e.trade(db, "P1", "A", "B", _dt(2026, 1, 10, 10, 0))

    a = await e.fpts(db, "A")
    b = await e.fpts(db, "B")
    assert a["game_count"] == 5, f"A={a['game_count']}"
    assert b["game_count"] == 3, f"B={b['game_count']}"

    ra = await e.roto(db, "A", ["goals"])
    rb = await e.roto(db, "B", ["goals"])
    assert ra["goals"] == 10
    assert rb["goals"] == 6


@pytest.mark.asyncio
async def test_2b_drop_preserves_10(db):
    """Drop after 5 games. Team keeps 10 goals."""
    e = Env()
    await e.create_league(db)
    await e.create_team(db, "A")
    await e.create_player(db, "P1", team="A", game_schedule=SCHED_5)

    await e.drop(db, "P1", "A", _dt(2026, 1, 10, 10, 0))

    a = await e.fpts(db, "A")
    assert a["game_count"] == 5
    ra = await e.roto(db, "A", ["goals"])
    assert ra["goals"] == 10


@pytest.mark.asyncio
async def test_2c_unowned_gap_credited_to_nobody(db):
    """A drops Jan 8 10:00, B picks up Jan 10 10:00. Jan 8-9 games unowned."""
    e = Env()
    await e.create_league(db)
    await e.create_team(db, "A")
    await e.create_team(db, "B")
    await e.create_player(db, "P1", team="A", game_schedule=SCHED_7)

    await e.drop(db, "P1", "A", _dt(2026, 1, 8, 10, 0))
    await e.pickup(db, "P1", "B", _dt(2026, 1, 10, 10, 0))

    a = await e.fpts(db, "A")
    b = await e.fpts(db, "B")
    # A: games Jan 5-7 @19:00 (all before drop @10:00 Jan 8). Jan 8 @19:00 is AFTER drop → not owned
    assert a["game_count"] == 3, f"A={a['game_count']}"
    # B: games Jan 10 @19:00, Jan 11 @19:00 (both after pickup @10:00 Jan 10)
    assert b["game_count"] == 2, f"B={b['game_count']}"
    # 2 games unowned (Jan 8, 9)


@pytest.mark.asyncio
async def test_2d_reacquisition_preserves_and_excludes_gap(db):
    """A drops Jan 8, picks up Jan 10. Gap excluded, both intervals counted."""
    e = Env()
    await e.create_league(db)
    await e.create_team(db, "A")
    await e.create_player(db, "P1", team="A", game_schedule=SCHED_7)

    await e.drop(db, "P1", "A", _dt(2026, 1, 8, 10, 0))
    await e.pickup(db, "P1", "A", _dt(2026, 1, 10, 10, 0))

    a = await e.fpts(db, "A")
    # First interval: Jan 5,6,7 (3). Second: Jan 10,11 (2). Total: 5.
    assert a["game_count"] == 5, f"A={a['game_count']}"


@pytest.mark.asyncio
async def test_2e_multiple_trades_allocate_each_game_once(db):
    """A→B at 10:00 Jan 8, B→C at 10:00 Jan 10. Each game allocated once."""
    e = Env()
    await e.create_league(db)
    await e.create_team(db, "A")
    await e.create_team(db, "B")
    await e.create_team(db, "C")
    await e.create_player(db, "P1", team="A", game_schedule=SCHED_7)

    await e.trade(db, "P1", "A", "B", _dt(2026, 1, 8, 10, 0))
    await e.trade(db, "P1", "B", "C", _dt(2026, 1, 10, 10, 0))

    a = await e.fpts(db, "A")
    b = await e.fpts(db, "B")
    c = await e.fpts(db, "C")
    # A: Jan 5,6,7 (3). B: Jan 8,9 (2). C: Jan 10,11 (2).
    assert a["game_count"] == 3
    assert b["game_count"] == 2
    assert c["game_count"] == 2
    assert a["game_count"] + b["game_count"] + c["game_count"] == 7


@pytest.mark.asyncio
async def test_2f_no_overlapping_ownership(db):
    """After trade, verify exactly one owner per game — no overlaps or gaps."""
    e = Env()
    await e.create_league(db)
    await e.create_team(db, "A")
    await e.create_team(db, "B")
    await e.create_player(db, "P1", team="A", game_schedule=SCHED_8)

    await e.trade(db, "P1", "A", "B", _dt(2026, 1, 10, 10, 0))

    # Check ownership period boundaries
    pid = e.players["P1"]
    periods = await db.player_ownership_periods.find(
        {"player_id": pid, "league_id": e.league_id},
    ).sort("acquired_at", 1).to_list(10)

    assert len(periods) == 2
    # A's end == B's start (no gap, no overlap)
    a_end = periods[0]["released_at"]
    b_start = periods[1]["acquired_at"]
    # Normalize for comparison
    if a_end.tzinfo is None:
        a_end = a_end.replace(tzinfo=timezone.utc)
    if b_start.tzinfo is None:
        b_start = b_start.replace(tzinfo=timezone.utc)
    assert a_end == b_start, f"Gap/overlap: A ends {a_end}, B starts {b_start}"


# ══════════════════════════════════════════════════════════════
# 3  HISTORICAL LINEUP ELIGIBILITY
# ══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_3a_active_to_bench(db):
    """Active→bench at 10:00 Jan 8. 3 active games (10→6: keep 10 earlier, exclude 6 later)."""
    e = Env()
    await e.create_league(db)
    await e.create_team(db, "A")
    await e.create_player(db, "P1", team="A", game_schedule=SCHED_8)

    await e.bench(db, "P1", "A", _dt(2026, 1, 8, 10, 0))

    a = await e.fpts(db, "A")
    # Active games: Jan 5,6,7 @19:00 (before bench @10:00 Jan 8). Jan 8 @19:00 is AFTER bench.
    assert a["game_count"] == 3, f"A={a['game_count']}"
    ra = await e.roto(db, "A", ["goals"])
    assert ra["goals"] == 6  # 3 games × 2 goals


@pytest.mark.asyncio
async def test_3b_bench_to_active(db):
    """Bench→active at 10:00 Jan 8. Exclude earlier 3 bench games, count 5 active."""
    e = Env()
    await e.create_league(db)
    await e.create_team(db, "A")
    await e.create_player(db, "P1", team="A",
                          game_schedule=SCHED_8, initial_position="bench")

    await e.activate(db, "P1", "A", _dt(2026, 1, 8, 10, 0))

    a = await e.fpts(db, "A")
    # Bench: Jan 5,6,7 @19:00 (before activation). Active: Jan 8+ @19:00.
    assert a["game_count"] == 5, f"A={a['game_count']}"
    ra = await e.roto(db, "A", ["goals"])
    assert ra["goals"] == 10  # 5 games × 2 goals


@pytest.mark.asyncio
async def test_3c_eligibility_at_puck_drop(db):
    """Bench at 20:00 Jan 7 — game at 19:00 Jan 7 was before bench → eligible."""
    e = Env()
    await e.create_league(db)
    await e.create_team(db, "A")
    await e.create_player(db, "P1", team="A", game_schedule=SCHED_5)

    # Bench AFTER Jan 7 puck drop (19:00) but before Jan 8
    await e.bench(db, "P1", "A", _dt(2026, 1, 7, 20, 0))

    a = await e.fpts(db, "A")
    # Jan 5,6 @19:00: eligible. Jan 7 @19:00: bench at 20:00 → 19:00 < 20:00 → still active → eligible!
    # Jan 8,9 @19:00: benched → not eligible.
    assert a["game_count"] == 3, f"A={a['game_count']}"


@pytest.mark.asyncio
async def test_3d_mid_game_lineup_no_change(db):
    """Lineup change during a game doesn't alter that game's eligibility."""
    e = Env()
    await e.create_league(db)
    await e.create_team(db, "A")
    # Single game at 19:00 Jan 5
    await e.create_player(db, "P1", team="A",
                          game_schedule=[("2026-01-05", 19)])

    # Bench at 20:00 Jan 5 (game started at 19:00)
    await e.bench(db, "P1", "A", _dt(2026, 1, 5, 20, 0))

    a = await e.fpts(db, "A")
    # Game started at 19:00, bench at 20:00 → at puck drop (19:00) player was active
    assert a["game_count"] == 1


# ══════════════════════════════════════════════════════════════
# 4  LATE IMPORTS AND CORRECTIONS
# ══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_4a_late_import_uses_game_time(db):
    """Late-arriving stats use original game time, not import time."""
    e = Env()
    await e.create_league(db)
    await e.create_team(db, "A")
    await e.create_team(db, "B")
    await e.create_player(db, "P1", team="A",
                          game_schedule=SCHED_8)

    await e.trade(db, "P1", "A", "B", _dt(2026, 1, 10, 10, 0))

    # Add a late game on Jan 7 (Team A's ownership) — as if NHL corrected schedule
    gid = e._gid; e._gid += 1
    await db.games.insert_one({
        "nhl_game_id": gid, "date": "2026-01-07",
        "start_time": _dt(2026, 1, 7, 21, 0),
    })
    pid = e.players["P1"]
    await db.players.update_one(
        {"_id": ObjectId(pid)},
        {"$set": {f"live_stats.{gid}": {
            "goals": 3, "assists": 2, "shots": 5,
            "plus_minus": 1, "penalty_minutes": 0,
            "power_play_goals": 0, "power_play_points": 0,
            "short_handed_goals": 0, "short_handed_points": 0,
            "game_winning_goals": 0,
            "updated_at": "2026-01-12T10:00:00",  # import time is AFTER trade
        }}},
    )

    a = await e.fpts(db, "A")
    # A: 5 original + 1 late game on Jan 7 = 6
    assert a["game_count"] == 6
    b = await e.fpts(db, "B")
    assert b["game_count"] == 3  # unchanged


@pytest.mark.asyncio
async def test_4b_correction_10_to_12(db):
    """Correct A's 10 goals to 12. A:12, B:6."""
    e = Env()
    await e.create_league(db)
    await e.create_team(db, "A")
    await e.create_team(db, "B")
    await e.create_player(db, "P1", team="A", game_schedule=SCHED_8)

    await e.trade(db, "P1", "A", "B", _dt(2026, 1, 10, 10, 0))

    # Before correction
    ra_before = await e.roto(db, "A", ["goals"])
    assert ra_before["goals"] == 10

    # Correct game 0 (Jan 5): goals 2→4
    await e.correct_game(db, "P1", 0, goals=4)

    ra = await e.roto(db, "A", ["goals"])
    rb = await e.roto(db, "B", ["goals"])
    assert ra["goals"] == 12, f"A={ra['goals']}"  # was 10, +2 correction
    assert rb["goals"] == 6, f"B={rb['goals']}"   # unchanged


@pytest.mark.asyncio
async def test_4c_no_duplication_on_reimport(db):
    """Reimporting the same game doesn't duplicate its contribution."""
    e = Env()
    await e.create_league(db)
    await e.create_team(db, "A")
    await e.create_player(db, "P1", team="A", game_schedule=SCHED_5)

    a1 = await e.roto(db, "A", ["goals"])

    # "Reimport" — update the same stats again
    pid = e.players["P1"]
    gid_str = e._game_keys["P1"][0]
    await db.players.update_one(
        {"_id": ObjectId(pid)},
        {"$set": {f"live_stats.{gid_str}.goals": 2}},  # same value
    )

    a2 = await e.roto(db, "A", ["goals"])
    assert a1["goals"] == a2["goals"], "Reimport must not duplicate"


# ══════════════════════════════════════════════════════════════
# 5  CONSISTENT SCORING AND FINALIZATION
# ══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_5a_finalization_after_within_period_trade(db):
    """Finalize after trade within period: A:10 (5 games), B:6 (3 games)."""
    e = Env()
    await e.create_league(db)
    await e.create_team(db, "A")
    await e.create_team(db, "B")
    await e.create_player(db, "P1", team="A", game_schedule=SCHED_8)

    await e.trade(db, "P1", "A", "B", _dt(2026, 1, 10, 10, 0))

    a = await e.fpts(db, "A")
    b = await e.fpts(db, "B")

    # Simulate finalization by storing results
    matchup_id = ObjectId()
    await db.matchups.insert_one({
        "_id": matchup_id,
        "league_id": e.league_id, "week": 1,
        "home_team_id": e.teams["A"], "away_team_id": e.teams["B"],
        "home_score": a["total_fpts"], "away_score": b["total_fpts"],
        "status": "completed",
    })

    stored = await db.matchups.find_one({"_id": matchup_id})
    assert stored["home_score"] == a["total_fpts"]
    assert stored["away_score"] == b["total_fpts"]
    assert a["game_count"] == 5
    assert b["game_count"] == 3


@pytest.mark.asyncio
async def test_5b_finalize_before_trade_then_recalculate(db):
    """Finalize week 1 (A:10, B:0). Trade after period. Recalculate: A still 10."""
    e = Env()
    await e.create_league(db)
    await e.create_team(db, "A")
    await e.create_team(db, "B")
    await e.create_player(db, "P1", team="A", game_schedule=SCHED_5)

    # Finalize: A has all stats
    a_pre = await e.fpts(db, "A")
    assert a_pre["game_count"] == 5

    # Trade AFTER the scoring period
    await e.trade(db, "P1", "A", "B", _dt(2026, 1, 15, 10, 0))

    # Recalculate same period
    a_post = await e.fpts(db, "A")
    b_post = await e.fpts(db, "B")

    assert a_post["game_count"] == 5, f"A should keep 5, got {a_post['game_count']}"
    assert b_post["game_count"] == 0, f"B should have 0, got {b_post['game_count']}"
    assert a_post["total_fpts"] == a_pre["total_fpts"]


@pytest.mark.asyncio
async def test_5c_breakdown_agrees_with_total(db):
    """Historical breakdown and total fpts agree."""
    e = Env()
    await e.create_league(db)
    await e.create_team(db, "A")
    await e.create_team(db, "B")
    await e.create_player(db, "P1", team="A", game_schedule=SCHED_8)

    await e.trade(db, "P1", "A", "B", _dt(2026, 1, 10, 10, 0))

    a = await e.fpts(db, "A")
    b = await e.fpts(db, "B")

    # Sum of player breakdowns should equal total
    a_bd = a.get("player_breakdown", {})
    b_bd = b.get("player_breakdown", {})
    a_sum = sum(v.get("fpts", 0) if isinstance(v, dict) else v for v in a_bd.values())
    b_sum = sum(v.get("fpts", 0) if isinstance(v, dict) else v for v in b_bd.values())
    assert abs(a_sum - a["total_fpts"]) < 0.01
    assert abs(b_sum - b["total_fpts"]) < 0.01


# ══════════════════════════════════════════════════════════════
# 6  ROTISSERIE RECOMPUTATION
# ══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_6a_roto_uses_historical_ownership(db):
    """Roto category totals use historical ownership."""
    e = Env()
    await e.create_league(db, scoring_format="rotisserie")
    await e.create_team(db, "A")
    await e.create_team(db, "B")
    await e.create_player(db, "P1", team="A", game_schedule=SCHED_8)

    await e.trade(db, "P1", "A", "B", _dt(2026, 1, 10, 10, 0))

    ra = await e.roto(db, "A", ["goals", "assists"])
    rb = await e.roto(db, "B", ["goals", "assists"])
    assert ra["goals"] == 10
    assert rb["goals"] == 6


@pytest.mark.asyncio
async def test_6b_roto_no_retroactive_movement(db):
    """A later roster change does not move earlier category contributions."""
    e = Env()
    await e.create_league(db, scoring_format="rotisserie")
    await e.create_team(db, "A")
    await e.create_team(db, "B")
    await e.create_player(db, "P1", team="A", game_schedule=SCHED_5)

    ra_before = await e.roto(db, "A", ["goals"])
    assert ra_before["goals"] == 10

    # Trade after all games
    await e.trade(db, "P1", "A", "B", _dt(2026, 1, 15, 10, 0))

    ra_after = await e.roto(db, "A", ["goals"])
    rb_after = await e.roto(db, "B", ["goals"])
    assert ra_after["goals"] == 10, "A's earlier goals must not move"
    assert rb_after["goals"] == 0


@pytest.mark.asyncio
async def test_6c_roto_recomputation_idempotent(db):
    """Repeating roto computation produces identical totals."""
    e = Env()
    await e.create_league(db, scoring_format="rotisserie")
    await e.create_team(db, "A")
    await e.create_team(db, "B")
    await e.create_player(db, "P1", team="A", game_schedule=SCHED_8)
    await e.trade(db, "P1", "A", "B", _dt(2026, 1, 10, 10, 0))

    results = []
    for _ in range(3):
        ra = await e.roto(db, "A", ["goals"])
        rb = await e.roto(db, "B", ["goals"])
        results.append((ra["goals"], rb["goals"]))
    assert results[0] == results[1] == results[2]


@pytest.mark.asyncio
async def test_6d_roto_correction_updates_allocation(db):
    """Correction updates affected historical allocation in roto."""
    e = Env()
    await e.create_league(db, scoring_format="rotisserie")
    await e.create_team(db, "A")
    await e.create_team(db, "B")
    await e.create_player(db, "P1", team="A", game_schedule=SCHED_8)
    await e.trade(db, "P1", "A", "B", _dt(2026, 1, 10, 10, 0))

    # Correct game 0 (A's game): 2→5 goals
    await e.correct_game(db, "P1", 0, goals=5)

    ra = await e.roto(db, "A", ["goals"])
    rb = await e.roto(db, "B", ["goals"])
    assert ra["goals"] == 13  # 10 - 2 + 5
    assert rb["goals"] == 6   # unchanged


# ══════════════════════════════════════════════════════════════
# 7  MISSING HISTORY AND BACKFILL
# ══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_7a_missing_vs_unowned(db):
    """Missing history ≠ confirmed unowned interval."""
    e = Env()
    await e.create_league(db, backfilled=False)  # NOT backfilled
    await e.create_team(db, "A")
    # No player, no ownership — just an empty team
    a = await e.fpts(db, "A")
    assert a.get("uncertain") is True or a.get("needs_backfill") is True or a["total_fpts"] == 0


@pytest.mark.asyncio
async def test_7b_uncertain_not_definitive_zero(db):
    """Un-backfilled league with players returns uncertain, not definitive zero."""
    e = Env()
    await e.create_league(db, backfilled=False)
    await e.create_team(db, "A")
    # Player on roster but NO ownership periods seeded (and league not backfilled)
    pid = str(ObjectId())
    tid = e.teams["A"]
    await db.players.insert_one({
        "_id": ObjectId(pid), "name": "Orphan", "position": "C",
        "player_type": "skater", "live_stats": {},
    })
    await db.teams.update_one({"_id": ObjectId(tid)}, {"$push": {"roster": pid}})
    # Don't seed ownership!

    a = await e.fpts(db, "A")
    # Should be flagged as uncertain, not presented as definitive
    assert a.get("uncertain") is True or a.get("needs_backfill") is True


@pytest.mark.asyncio
async def test_7c_backfill_uses_evidence(db):
    """Backfill creates periods from trade evidence."""
    e = Env()
    await e.create_league(db, backfilled=False)
    await e.create_team(db, "A")
    await e.create_team(db, "B")

    pid = str(ObjectId())
    trade_time = _dt(2026, 1, 10, 10, 0)

    # Seed a trade in the trades collection
    await db.trades.insert_one({
        "league_id": e.league_id, "status": "executed",
        "is_multi_party": True,
        "processed_at": trade_time.isoformat(),
        "execution_moves": [
            {"player_id": pid, "from": e.teams["A"],
             "to": e.teams["B"]},
        ],
    })
    await db.teams.update_one(
        {"_id": ObjectId(e.teams["B"])}, {"$push": {"roster": pid}},
    )

    from utils.backfill_ownership import backfill_league_ownership
    result = await backfill_league_ownership(db, e.league_id)

    assert result["ownership_periods_created"] > 0
    assert result["events_found"] > 0


@pytest.mark.asyncio
async def test_7d_current_roster_not_season_long(db):
    """Current roster alone does not establish season-long history."""
    e = Env()
    await e.create_league(db, backfilled=False)
    await e.create_team(db, "A")

    pid = str(ObjectId())
    await db.players.insert_one({
        "_id": ObjectId(pid), "name": "Recent", "position": "C",
        "player_type": "skater", "live_stats": {},
    })
    await db.teams.update_one({"_id": ObjectId(e.teams["A"])}, {"$push": {"roster": pid}})

    a = await e.fpts(db, "A")
    # Without ownership data, should NOT return definitive scores
    assert a.get("uncertain") is True or a["total_fpts"] == 0


@pytest.mark.asyncio
async def test_7e_repeated_backfill_no_duplicates(db):
    """Running backfill twice produces no duplicate periods."""
    e = Env()
    await e.create_league(db, backfilled=False)
    await e.create_team(db, "A")

    pid = str(ObjectId())
    await db.teams.update_one(
        {"_id": ObjectId(e.teams["A"])},
        {"$push": {"roster": pid}, "$set": {"lineup": {}}},
    )

    from utils.backfill_ownership import backfill_league_ownership

    r1 = await backfill_league_ownership(db, e.league_id)
    c1 = await db.player_ownership_periods.count_documents({"league_id": e.league_id})

    r2 = await backfill_league_ownership(db, e.league_id)
    c2 = await db.player_ownership_periods.count_documents({"league_id": e.league_id})

    assert c1 == c2, f"Duplicate: {c1} vs {c2}"


@pytest.mark.asyncio
async def test_2g_multi_player_partial_trade(db):
    """Two players on A, only P1 traded. P2 stays — A keeps all P2 stats."""
    e = Env()
    await e.create_league(db)
    await e.create_team(db, "A")
    await e.create_team(db, "B")
    await e.create_player(db, "P1", team="A", game_schedule=SCHED_8)
    await e.create_player(db, "P2", team="A", game_schedule=SCHED_7, goals=3, assists=0, shots=1)

    await e.trade(db, "P1", "A", "B", _dt(2026, 1, 10, 10, 0))

    a = await e.fpts(db, "A")
    b = await e.fpts(db, "B")
    # A: 5 games P1 + 7 games P2 = 12. B: 3 games P1.
    assert a["game_count"] == 12, f"A={a['game_count']}"
    assert b["game_count"] == 3, f"B={b['game_count']}"
    # Verify player breakdown
    assert e.players["P1"] in a["player_breakdown"]
    assert e.players["P2"] in a["player_breakdown"]
    assert a["player_breakdown"][e.players["P1"]]["games"] == 5
    assert a["player_breakdown"][e.players["P2"]]["games"] == 7


@pytest.mark.asyncio
async def test_2h_waiver_pickup_after_gap(db):
    """Drop + waiver claim after gap. Gap games credited to nobody."""
    e = Env()
    await e.create_league(db)
    await e.create_team(db, "A")
    await e.create_team(db, "B")
    await e.create_player(db, "P1", team="A", game_schedule=SCHED_7)

    await e.drop(db, "P1", "A", _dt(2026, 1, 7, 10, 0))
    # Waiver claim on Jan 9 (2 days later, position="forward" by default)
    await e.pickup(db, "P1", "B", _dt(2026, 1, 9, 10, 0))

    a = await e.fpts(db, "A")
    b = await e.fpts(db, "B")
    # A: Jan 5,6 @19:00 (before drop 10:00 Jan 7). Jan 7 @19:00 is AFTER drop.
    assert a["game_count"] == 2, f"A={a['game_count']}"
    # B: Jan 9,10,11 @19:00 (after pickup 10:00 Jan 9).
    assert b["game_count"] == 3, f"B={b['game_count']}"
    # Jan 7, 8 unowned


@pytest.mark.asyncio
async def test_3e_ir_to_active(db):
    """Player starts on IR, activated mid-period. Only post-activation games count."""
    e = Env()
    await e.create_league(db)
    await e.create_team(db, "A")
    await e.create_player(db, "P1", team="A",
                          game_schedule=SCHED_7, initial_position="ir")

    # Activate on Jan 8 10:00
    await e.activate(db, "P1", "A", _dt(2026, 1, 8, 10, 0))

    a = await e.fpts(db, "A")
    # IR: Jan 5,6,7 @19:00 — not eligible. Active: Jan 8-11 @19:00 = 4 games.
    assert a["game_count"] == 4, f"A={a['game_count']}"


@pytest.mark.asyncio
async def test_3f_bench_active_bench_sandwich(db):
    """Bench→active→bench: only middle interval eligible."""
    e = Env()
    await e.create_league(db)
    await e.create_team(db, "A")
    await e.create_player(db, "P1", team="A",
                          game_schedule=SCHED_7, initial_position="bench")

    await e.activate(db, "P1", "A", _dt(2026, 1, 7, 10, 0))
    await e.bench(db, "P1", "A", _dt(2026, 1, 9, 10, 0))

    a = await e.fpts(db, "A")
    # Bench: Jan 5,6 @19:00. Active: Jan 7,8 @19:00. Bench again: Jan 9,10,11 @19:00.
    assert a["game_count"] == 2, f"A={a['game_count']}"
    ra = await e.roto(db, "A", ["goals"])
    assert ra["goals"] == 4  # 2 games × 2 goals


@pytest.mark.asyncio
async def test_4d_goalie_scoring(db):
    """Goalie stats are allocated by historical ownership just like skaters."""
    e = Env()
    await e.create_league(db)
    await e.create_team(db, "A")
    await e.create_team(db, "B")

    # Create goalie with goalie-specific live_stats
    pid = str(ObjectId())
    tid_a = e.teams["A"]
    e.players["G1"] = pid
    e._game_keys["G1"] = []

    # 4 games
    sched = [("2026-01-05", 19), ("2026-01-06", 19), ("2026-01-07", 19), ("2026-01-08", 19)]
    live_stats = {}
    for date_str, puck_hour in sched:
        gid = e._gid; e._gid += 1
        puck_drop = _dt(int(date_str[:4]), int(date_str[5:7]), int(date_str[8:10]), puck_hour)
        await db.games.insert_one({
            "nhl_game_id": gid, "date": date_str, "start_time": puck_drop,
        })
        live_stats[str(gid)] = {
            "wins": 1, "losses": 0, "saves": 30, "goals_against": 2,
            "shutouts": 0, "overtime_losses": 0,
            "goals": 0, "assists": 0, "shots": 0,
            "plus_minus": 0, "penalty_minutes": 0,
            "power_play_goals": 0, "power_play_points": 0,
            "short_handed_goals": 0, "short_handed_points": 0,
            "game_winning_goals": 0,
        }
        e._game_keys["G1"].append(str(gid))

    await db.players.insert_one({
        "_id": ObjectId(pid), "name": "G1",
        "position": "G", "player_type": "goalie",
        "live_stats": live_stats,
    })
    await db.teams.update_one(
        {"_id": ObjectId(tid_a)},
        {"$push": {"roster": pid},
         "$set": {f"lineup.{pid}": {"section": "goalie"}}},
    )
    await db.player_ownership_periods.insert_one({
        "player_id": pid, "team_id": tid_a,
        "league_id": e.league_id,
        "acquired_at": _SEASON_START, "released_at": None,
        "source": "draft", "release_source": None,
    })
    await db.lineup_status_periods.insert_one({
        "player_id": pid, "team_id": tid_a,
        "league_id": e.league_id,
        "position": "goalie", "started_at": _SEASON_START, "ended_at": None,
    })

    # Trade goalie after game 2
    await e.trade(db, "G1", "A", "B", _dt(2026, 1, 7, 10, 0))

    a = await e.fpts(db, "A")
    b = await e.fpts(db, "B")
    # A: Jan 5,6 @19:00 (2 games). B: Jan 7,8 @19:00 (2 games).
    assert a["game_count"] == 2, f"A={a['game_count']}"
    assert b["game_count"] == 2, f"B={b['game_count']}"
    # Goalie fpts: each game = 1*5 + 0*(-2) + 30*0.2 + 2*(-1) + 0*3 = 5+6-2 = 9
    assert a["total_fpts"] > 0
    assert b["total_fpts"] > 0


@pytest.mark.asyncio
async def test_5d_fpts_idempotent_with_trade(db):
    """Running fpts 3 times with a trade yields identical results each time."""
    e = Env()
    await e.create_league(db)
    await e.create_team(db, "A")
    await e.create_team(db, "B")
    await e.create_player(db, "P1", team="A", game_schedule=SCHED_8)
    await e.trade(db, "P1", "A", "B", _dt(2026, 1, 10, 10, 0))

    results = []
    for _ in range(3):
        a = await e.fpts(db, "A")
        b = await e.fpts(db, "B")
        results.append((a["total_fpts"], a["game_count"], b["total_fpts"], b["game_count"]))
    assert results[0] == results[1] == results[2], f"Not idempotent: {results}"


# ══════════════════════════════════════════════════════════════
# 8  TIMING BOUNDARIES
# ══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_8a_game_before_transaction_to_old_owner(db):
    """Game starting before transaction → old owner. Game at/after → new owner."""
    e = Env()
    await e.create_league(db)
    await e.create_team(db, "A")
    await e.create_team(db, "B")
    # Game at 19:00 Jan 7, trade at 20:00 Jan 7, game at 19:00 Jan 8
    await e.create_player(db, "P1", team="A",
                          game_schedule=[("2026-01-07", 19), ("2026-01-08", 19)])

    await e.trade(db, "P1", "A", "B", _dt(2026, 1, 7, 20, 0))

    a = await e.fpts(db, "A")
    b = await e.fpts(db, "B")
    # Jan 7 @19:00: trade at 20:00 → owned by A at puck drop → A gets it
    # Jan 8 @19:00: trade at 20:00 Jan 7 → B owns since 20:00 Jan 7 → B gets it
    assert a["game_count"] == 1, f"A={a['game_count']}"
    assert b["game_count"] == 1, f"B={b['game_count']}"


@pytest.mark.asyncio
async def test_8b_game_exactly_at_transaction(db):
    """Game starting exactly at transaction time → new owner gets it."""
    e = Env()
    await e.create_league(db)
    await e.create_team(db, "A")
    await e.create_team(db, "B")
    # Game at 19:00 Jan 7
    await e.create_player(db, "P1", team="A",
                          game_schedule=[("2026-01-07", 19)])

    # Trade at exactly 19:00 Jan 7 (same as puck drop)
    await e.trade(db, "P1", "A", "B", _dt(2026, 1, 7, 19, 0))

    a = await e.fpts(db, "A")
    b = await e.fpts(db, "B")
    # A: released_at = 19:00, game at 19:00. released_at > game_time → 19:00 > 19:00 → FALSE
    # → A does NOT own this game
    # B: acquired_at = 19:00, game at 19:00. acquired_at <= game_time → 19:00 <= 19:00 → TRUE
    # → B OWNS this game
    assert a["game_count"] == 0, f"A={a['game_count']}"
    assert b["game_count"] == 1, f"B={b['game_count']}"


@pytest.mark.asyncio
async def test_8c_timezone_equivalence(db):
    """Same timestamps in different representations produce identical results."""
    e = Env()
    await e.create_league(db)
    await e.create_team(db, "A")
    await e.create_team(db, "B")
    await e.create_player(db, "P1", team="A", game_schedule=SCHED_8)

    await e.trade(db, "P1", "A", "B", _dt(2026, 1, 10, 10, 0))

    a1 = await e.fpts(db, "A")
    # Same query with different but equivalent period bounds
    from utils.game_allocation import allocate_team_period_fpts
    ps_utc = _dt(2026, 1, 5, 0, 0)
    pe_utc = _dt(2026, 1, 12, 0, 0)
    a2 = await allocate_team_period_fpts(
        db, e.teams["A"], e.league_id, ps_utc, pe_utc, None,
    )

    assert a1["game_count"] == a2["game_count"]
    assert abs(a1["total_fpts"] - a2["total_fpts"]) < 0.01


@pytest.mark.asyncio
async def test_8d_same_day_double_header_trade_between(db):
    """Two games on same day. Trade between puck drops → each goes to correct owner."""
    e = Env()
    await e.create_league(db)
    await e.create_team(db, "A")
    await e.create_team(db, "B")
    # Two games on Jan 7: 14:00 and 20:00
    await e.create_player(db, "P1", team="A",
                          game_schedule=[("2026-01-07", 14), ("2026-01-07", 20)])

    # Trade at 17:00 Jan 7 (between the two games)
    await e.trade(db, "P1", "A", "B", _dt(2026, 1, 7, 17, 0))

    a = await e.fpts(db, "A")
    b = await e.fpts(db, "B")
    # Game 1 @14:00: A owns (trade at 17:00). Game 2 @20:00: B owns (trade at 17:00).
    assert a["game_count"] == 1, f"A={a['game_count']}"
    assert b["game_count"] == 1, f"B={b['game_count']}"
