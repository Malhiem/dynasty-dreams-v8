"""Focused unit tests for `routes/activity.py`."""
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from routes import activity as activity_routes  # noqa: E402

from tests.router_test_utils import isolated_router_app  # noqa: E402


@pytest.mark.asyncio
async def test_activity_feed_empty_returns_pagination_skeleton():
    async with isolated_router_app(activity_routes) as ctx:
        r = await ctx.client.get("/api/activity/some_league_id")
        assert r.status_code == 200
        body = r.json()
        assert body == {"items": [], "total": 0, "page": 1, "pages": 0}


@pytest.mark.asyncio
async def test_activity_feed_returns_items_sorted_desc():
    async with isolated_router_app(activity_routes) as ctx:
        now = datetime.now(timezone.utc)
        await ctx.db.activity_feed.insert_many([
            {"league_id": "L1", "event_type": "roster_add", "message": "older",
             "created_at": now - timedelta(hours=2)},
            {"league_id": "L1", "event_type": "trade_executed", "message": "newer",
             "created_at": now},
            {"league_id": "L2", "event_type": "roster_add", "message": "other league",
             "created_at": now},
        ])
        r = await ctx.client.get("/api/activity/L1")
        body = r.json()
        assert body["total"] == 2
        assert body["items"][0]["message"] == "newer"
        assert body["items"][1]["message"] == "older"


@pytest.mark.asyncio
async def test_activity_feed_event_type_filter_supports_csv():
    """The frontend passes a comma-separated list to narrow the feed; both
    single + multi values must work.
    """
    async with isolated_router_app(activity_routes) as ctx:
        now = datetime.now(timezone.utc)
        await ctx.db.activity_feed.insert_many([
            {"league_id": "L1", "event_type": "roster_add", "created_at": now},
            {"league_id": "L1", "event_type": "roster_drop", "created_at": now},
            {"league_id": "L1", "event_type": "trade_executed", "created_at": now},
        ])
        single = (await ctx.client.get("/api/activity/L1?event_type=trade_executed")).json()
        assert single["total"] == 1

        multi = (await ctx.client.get("/api/activity/L1?event_type=roster_add,roster_drop")).json()
        assert multi["total"] == 2


@pytest.mark.asyncio
async def test_transactions_normalizes_metadata_into_top_level_keys():
    """The transactions endpoint flattens metadata.* fields into the row so the
    frontend doesn't have to dig through `metadata`. Regression-guards the
    Transactions page contract.
    """
    async with isolated_router_app(activity_routes) as ctx:
        now = datetime.now(timezone.utc)
        await ctx.db.activity_feed.insert_one({
            "league_id": "L1",
            "event_type": "waiver_won",
            "message": "Team A wins McDavid",
            "created_at": now,
            "metadata": {
                "team_id": "team_a",
                "team_name": "Team A",
                "player_id": "p_99",
                "player_name": "McDavid",
                "winning_bid": 50,
                "competing_claims": [{"team": "B", "bid": 40}],
            },
        })
        r = await ctx.client.get("/api/leagues/L1/transactions")
        body = r.json()
        assert body["count"] == 1
        row = body["transactions"][0]
        assert row["type"] == "waiver_won"
        assert row["team_name"] == "Team A"
        assert row["player_name"] == "McDavid"
        assert row["winning_bid"] == 50
        assert row["competing_claims"] == [{"team": "B", "bid": 40}]


@pytest.mark.asyncio
async def test_transactions_since_filter_drops_older_rows():
    async with isolated_router_app(activity_routes) as ctx:
        old = datetime(2026, 1, 1, tzinfo=timezone.utc)
        recent = datetime(2026, 5, 1, tzinfo=timezone.utc)
        await ctx.db.activity_feed.insert_many([
            {"league_id": "L1", "event_type": "roster_add", "message": "old", "created_at": old},
            {"league_id": "L1", "event_type": "roster_add", "message": "recent", "created_at": recent},
        ])
        r = await ctx.client.get("/api/leagues/L1/transactions?since=2026-04-01")
        body = r.json()
        assert body["count"] == 1
        assert body["transactions"][0]["description"] == "recent"


@pytest.mark.asyncio
async def test_transactions_team_id_filter_uses_metadata():
    async with isolated_router_app(activity_routes) as ctx:
        now = datetime.now(timezone.utc)
        await ctx.db.activity_feed.insert_many([
            {"league_id": "L1", "event_type": "roster_drop", "created_at": now,
             "metadata": {"team_id": "team_a", "player_name": "P1"}},
            {"league_id": "L1", "event_type": "roster_drop", "created_at": now,
             "metadata": {"team_id": "team_b", "player_name": "P2"}},
        ])
        r = await ctx.client.get("/api/leagues/L1/transactions?team_id=team_a")
        body = r.json()
        assert body["count"] == 1
        assert body["transactions"][0]["player_name"] == "P1"


@pytest.mark.asyncio
async def test_transactions_excludes_non_player_events():
    """Only roster_add / roster_drop / waiver_won / waiver_lost / trade_executed
    show up — `contract_signed`, `league_created`, etc. are out of scope for
    the Transactions page.
    """
    async with isolated_router_app(activity_routes) as ctx:
        now = datetime.now(timezone.utc)
        await ctx.db.activity_feed.insert_many([
            {"league_id": "L1", "event_type": "roster_add", "created_at": now},
            {"league_id": "L1", "event_type": "contract_signed", "created_at": now},
            {"league_id": "L1", "event_type": "league_created", "created_at": now},
        ])
        r = await ctx.client.get("/api/leagues/L1/transactions")
        assert r.json()["count"] == 1
