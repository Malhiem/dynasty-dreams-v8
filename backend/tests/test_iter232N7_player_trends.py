"""Iter 232N.7 — Cross-league player trends aggregator + endpoints.

Covers:
  (1) `aggregate_player_trends_once` counts adds via activity +
      waiver_claims, drops via activity, and trades via executed
      trades (both two-party and multi-party). Only events within
      the window are counted.
  (2) `trend` label rules — hot / dropped / traded gated on both a
      minimum count AND a minimum distinct_leagues.
  (3) Repeat runs are idempotent (upsert by player_id).
  (4) Zero-out pass: when a player fell out of the window, their
      previous non-null trend is cleared.
  (5) `/player-trends/leaderboard?movers=hot|dropped|traded|all`
      returns sorted rows.
  (6) `fetch_trends_map` is efficient for enriching a list of
      player_ids.
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone, timedelta

import pytest
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.player_trends_aggregator import (  # noqa: E402
    aggregate_player_trends_once, _derive_trend,
)


@pytest.fixture()
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture()
async def db():
    client = AsyncIOMotorClient(os.environ.get("MONGO_URL"))
    d = client[os.environ.get("DB_NAME", "test_database")]
    yield d
    client.close()


# ─── (2) Trend label rules ──────────────────────────────────────
def test_derive_trend_hot_requires_two_leagues():
    assert _derive_trend(adds=5, drops=0, trades=0, leagues_adds=1, leagues_drops=0, leagues_trades=0) is None
    assert _derive_trend(adds=3, drops=0, trades=0, leagues_adds=2, leagues_drops=0, leagues_trades=0) == "hot"


def test_derive_trend_multi_signal_picks_highest_count():
    # adds=4 (hot qualifies), drops=3 (dropped qualifies), trades=1 (below).
    # adds count is higher → hot wins.
    assert _derive_trend(adds=4, drops=3, trades=1, leagues_adds=2, leagues_drops=2, leagues_trades=0) == "hot"


def test_derive_trend_ties_break_by_priority():
    # adds=3 and drops=3 tied → hot has higher priority.
    assert _derive_trend(adds=3, drops=3, trades=0, leagues_adds=2, leagues_drops=2, leagues_trades=0) == "hot"


# ─── (1)+(3)+(4) Aggregator ─────────────────────────────────────
@pytest.mark.asyncio
async def test_aggregator_counts_adds_drops_trades_across_leagues(db):
    sfx = uuid.uuid4().hex[:8]
    p_hot_id = str(ObjectId())
    p_dropped_id = str(ObjectId())
    p_traded_id = str(ObjectId())
    la = str(ObjectId())
    lb = str(ObjectId())
    lc = str(ObjectId())

    now = datetime.now(timezone.utc)

    # Hot: adds=3 across 2 leagues.
    for lg in [la, la, lb]:
        await db.activity.insert_one({
            "league_id": lg, "event_type": "roster_add",
            "created_at": now - timedelta(hours=6),
            "metadata": {"player_id": p_hot_id}, "_iter232n7_sfx": sfx,
        })
    # Dropped: drops=3 across 2 leagues.
    for lg in [la, lb, lb]:
        await db.activity.insert_one({
            "league_id": lg, "event_type": "roster_drop",
            "created_at": now - timedelta(hours=6),
            "metadata": {"player_id": p_dropped_id}, "_iter232n7_sfx": sfx,
        })
    # Traded: 2 executed trades across 2 leagues.
    for lg in [la, lc]:
        await db.trades.insert_one({
            "status": "executed", "league_id": lg,
            "processes_at": (now - timedelta(hours=6)).isoformat(),
            "assets_offered": [{"asset_type": "player", "player_id": p_traded_id}],
            "assets_requested": [], "is_multi_party": False,
            "_iter232n7_sfx": sfx,
        })

    res = await aggregate_player_trends_once(db, window_days=7)
    assert res["upserted"] >= 3

    hot = await db.player_trends.find_one({"player_id": p_hot_id})
    assert hot is not None
    assert hot["adds_7d"] == 3
    assert hot["leagues_adds_7d"] == 2
    assert hot["trend"] == "hot"

    dropped = await db.player_trends.find_one({"player_id": p_dropped_id})
    assert dropped["drops_7d"] == 3
    assert dropped["trend"] == "dropped"

    traded = await db.player_trends.find_one({"player_id": p_traded_id})
    assert traded["trades_7d"] == 2
    assert traded["leagues_trades_7d"] == 2
    assert traded["trend"] == "traded"

    # ── Idempotence: a second run must NOT double the counts. ─
    res2 = await aggregate_player_trends_once(db, window_days=7)
    hot2 = await db.player_trends.find_one({"player_id": p_hot_id})
    assert hot2["adds_7d"] == 3  # unchanged
    assert res2["upserted"] == res["upserted"]

    # Cleanup.
    await db.activity.delete_many({"_iter232n7_sfx": sfx})
    await db.trades.delete_many({"_iter232n7_sfx": sfx})
    await db.player_trends.delete_many({"player_id": {"$in": [p_hot_id, p_dropped_id, p_traded_id]}})


@pytest.mark.asyncio
async def test_aggregator_zeros_out_stale_snapshots(db):
    """A player that had a trend last week but has no events in the
    current window must have their trend cleared to None."""
    stale_pid = str(ObjectId())
    await db.player_trends.insert_one({
        "player_id": stale_pid,
        "adds_7d": 5, "drops_7d": 0, "trades_7d": 0,
        "total_events_7d": 5,
        "leagues_adds_7d": 3, "leagues_drops_7d": 0, "leagues_trades_7d": 0,
        "distinct_leagues_7d": 3,
        "trend": "hot",
        "computed_at": (datetime.now(timezone.utc) - timedelta(days=8)).isoformat(),
        "window_days": 7,
    })
    # No activity / trades for this pid inside the window → aggregator
    # should zero it out.
    await aggregate_player_trends_once(db, window_days=7)
    updated = await db.player_trends.find_one({"player_id": stale_pid})
    assert updated["trend"] is None
    assert updated["adds_7d"] == 0

    await db.player_trends.delete_one({"player_id": stale_pid})


@pytest.mark.asyncio
async def test_aggregator_multi_party_trade_extracts_all_players(db):
    sfx = uuid.uuid4().hex[:8]
    pids = [str(ObjectId()) for _ in range(3)]
    league_a = str(ObjectId())
    league_b = str(ObjectId())
    now = datetime.now(timezone.utc)

    # One multi-party trade with 3 players moving between 3 teams.
    for lg in [league_a, league_b]:
        await db.trades.insert_one({
            "status": "executed", "league_id": lg, "is_multi_party": True,
            "processes_at": (now - timedelta(hours=2)).isoformat(),
            "parties": [
                {"team_id": "t1", "sends": [{"asset_type": "player", "player_id": pids[0]}], "receives": [{"asset_type": "player", "player_id": pids[1]}]},
                {"team_id": "t2", "sends": [{"asset_type": "player", "player_id": pids[1]}], "receives": [{"asset_type": "player", "player_id": pids[2]}]},
                {"team_id": "t3", "sends": [{"asset_type": "player", "player_id": pids[2]}], "receives": [{"asset_type": "player", "player_id": pids[0]}]},
            ],
            "_iter232n7_sfx": sfx,
        })

    await aggregate_player_trends_once(db, window_days=7)
    for pid in pids:
        row = await db.player_trends.find_one({"player_id": pid})
        assert row is not None
        assert row["trades_7d"] == 2  # both trades counted
        assert row["leagues_trades_7d"] == 2
        assert row["trend"] == "traded"

    await db.trades.delete_many({"_iter232n7_sfx": sfx})
    await db.player_trends.delete_many({"player_id": {"$in": pids}})


# ─── (5)+(6) Endpoints ──────────────────────────────────────────
@pytest.mark.asyncio
async def test_leaderboard_returns_sorted_players(db):
    from routes import player_trends as trends_route
    from routes.player_trends import get_trends_leaderboard
    trends_route.setup({"db": db})

    sfx = uuid.uuid4().hex[:8]
    hot_pid = ObjectId()
    less_pid = ObjectId()
    await db.players.insert_many([
        {"_id": hot_pid, "name": f"Hot {sfx}", "position": "C", "team": "EDM", "nhl_id": f"n7-h-{sfx}"},
        {"_id": less_pid, "name": f"Less {sfx}", "position": "D", "team": "TOR", "nhl_id": f"n7-l-{sfx}"},
    ])
    await db.player_trends.insert_many([
        {"player_id": str(hot_pid), "trend": "hot", "adds_7d": 10, "drops_7d": 0, "trades_7d": 0, "distinct_leagues_7d": 4, "total_events_7d": 10},
        {"player_id": str(less_pid), "trend": "hot", "adds_7d": 4, "drops_7d": 0, "trades_7d": 0, "distinct_leagues_7d": 2, "total_events_7d": 4},
    ])

    class R:
        pass
    res = await get_trends_leaderboard(R(), movers="hot", days=7, limit=5)  # type: ignore[arg-type]
    ids = [p["player_id"] for p in res["players"]]
    assert ids[0] == str(hot_pid)  # highest adds first
    assert str(less_pid) in ids
    # Category filter respected: dropped movers should return none.
    res_d = await get_trends_leaderboard(R(), movers="dropped", days=7, limit=5)  # type: ignore[arg-type]
    assert res_d["players"] == []

    await db.players.delete_many({"_id": {"$in": [hot_pid, less_pid]}})
    await db.player_trends.delete_many({"player_id": {"$in": [str(hot_pid), str(less_pid)]}})


@pytest.mark.asyncio
async def test_fetch_trends_map_only_returns_active(db):
    from routes import player_trends as trends_route
    from routes.player_trends import fetch_trends_map
    trends_route.setup({"db": db})

    active_pid = str(ObjectId())
    inactive_pid = str(ObjectId())
    await db.player_trends.insert_many([
        {"player_id": active_pid, "trend": "hot", "adds_7d": 5, "drops_7d": 0, "trades_7d": 0, "distinct_leagues_7d": 3},
        {"player_id": inactive_pid, "trend": None, "adds_7d": 0, "drops_7d": 0, "trades_7d": 0, "distinct_leagues_7d": 0},
    ])
    out = await fetch_trends_map([active_pid, inactive_pid, str(ObjectId())])  # last one has no row
    assert active_pid in out
    assert inactive_pid not in out  # None trend filtered
    assert out[active_pid]["trend"] == "hot"

    await db.player_trends.delete_many({"player_id": {"$in": [active_pid, inactive_pid]}})
