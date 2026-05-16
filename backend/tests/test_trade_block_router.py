"""Focused unit tests for `routes/trade_block.py`."""
import os
import sys
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from routes import trade_block as trade_block_routes  # noqa: E402

from tests.router_test_utils import (  # noqa: E402
    isolated_router_app,
    seed_league,
    seed_player,
    seed_team,
)


@pytest.mark.asyncio
async def test_get_trade_block_empty_returns_empty_list():
    async with isolated_router_app(trade_block_routes) as ctx:
        r = await ctx.client.get("/api/trade-block?league_id=anything")
        assert r.status_code == 200
        assert r.json() == []


@pytest.mark.asyncio
async def test_post_trade_block_player_persists_and_broadcasts():
    """Posting a player listing inserts the row + emits a `trade_block_changed`
    socket event so connected clients see it without polling.
    """
    async with isolated_router_app(trade_block_routes) as ctx:
        league_id = await seed_league(ctx.db)
        team_id = await seed_team(ctx.db, league_id=league_id)
        player_id = await seed_player(ctx.db, name="McDavid", position="C")

        r = await ctx.client.post("/api/trade-block", json={
            "item_type": "player",
            "league_id": league_id,
            "team_id": team_id,
            "player_id": player_id,
            "looking_for": ["RHD", "Best Offer"],
            "note": "Looking for top-pair help",
        })
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["name"] == "McDavid"
        assert body["position"] == "C"
        assert body["looking_for"] == ["RHD", "Best Offer"]
        # Listing was persisted to the ephemeral DB.
        assert await ctx.db.trade_block.count_documents({"league_id": league_id}) == 1
        # Socket broadcast fired with the new item's id.
        assert any(c["event"] == "trade_block_changed" for c in ctx.broadcast_calls)


@pytest.mark.asyncio
async def test_post_trade_block_duplicate_rejected_with_400():
    async with isolated_router_app(trade_block_routes) as ctx:
        league_id = await seed_league(ctx.db)
        team_id = await seed_team(ctx.db, league_id=league_id)
        player_id = await seed_player(ctx.db)
        payload = {
            "item_type": "player",
            "league_id": league_id,
            "team_id": team_id,
            "player_id": player_id,
        }
        first = await ctx.client.post("/api/trade-block", json=payload)
        assert first.status_code == 200

        dup = await ctx.client.post("/api/trade-block", json=payload)
        assert dup.status_code == 400
        assert "trade block" in dup.json()["detail"].lower()


@pytest.mark.asyncio
async def test_get_trade_block_joins_player_aav_for_cap_enabled_leagues():
    """The list endpoint enriches each player item with the joined AAV so the
    frontend Trade Block list view can render a Salary/AAV column without N+1.
    """
    async with isolated_router_app(trade_block_routes) as ctx:
        league_id = await seed_league(ctx.db)
        team_id = await seed_team(ctx.db, league_id=league_id)
        player_id = await seed_player(ctx.db, aav=4_500_000)
        # Add via API to exercise the create path.
        await ctx.client.post("/api/trade-block", json={
            "item_type": "player",
            "league_id": league_id,
            "team_id": team_id,
            "player_id": player_id,
        })
        rows = (await ctx.client.get(f"/api/trade-block?league_id={league_id}")).json()
        assert len(rows) == 1
        assert rows[0]["aav"] == 4_500_000


@pytest.mark.asyncio
async def test_delete_trade_block_only_for_owner():
    async with isolated_router_app(trade_block_routes) as ctx:
        league_id = await seed_league(ctx.db)
        team_id = await seed_team(ctx.db, league_id=league_id)
        player_id = await seed_player(ctx.db)
        # Insert as a DIFFERENT user so the test user is not the owner.
        ins = await ctx.db.trade_block.insert_one({
            "item_type": "player", "owner_id": "someone_else",
            "league_id": league_id, "team_id": team_id, "player_id": player_id,
            "name": "Locked", "position": "C", "created_at": datetime.now(timezone.utc),
        })
        r = await ctx.client.delete(f"/api/trade-block/{ins.inserted_id}")
        assert r.status_code == 403


@pytest.mark.asyncio
async def test_delete_trade_block_owner_succeeds_and_broadcasts():
    async with isolated_router_app(trade_block_routes) as ctx:
        league_id = await seed_league(ctx.db)
        team_id = await seed_team(ctx.db, league_id=league_id)
        player_id = await seed_player(ctx.db)
        # Insert via API so it's owned by the test user.
        item_id = (await ctx.client.post("/api/trade-block", json={
            "item_type": "player", "league_id": league_id,
            "team_id": team_id, "player_id": player_id,
        })).json()["_id"]
        ctx.broadcast_calls.clear()

        r = await ctx.client.delete(f"/api/trade-block/{item_id}")
        assert r.status_code == 200
        assert await ctx.db.trade_block.count_documents({}) == 0
        assert any(
            c["event"] == "trade_block_changed" and c["payload"]["action"] == "removed"
            for c in ctx.broadcast_calls
        )


@pytest.mark.asyncio
async def test_set_trade_block_note_validates_length_and_ownership():
    async with isolated_router_app(trade_block_routes) as ctx:
        league_id = await seed_league(ctx.db)
        owned_team = await seed_team(ctx.db, league_id=league_id)
        other_team = await seed_team(ctx.db, league_id=league_id, owner_id="someone_else", name="Other")

        # Length cap (200 chars).
        too_long = await ctx.client.put(
            f"/api/teams/{owned_team}/trade-block-note", json={"note": "x" * 201},
        )
        assert too_long.status_code == 400

        # Not your team.
        forbidden = await ctx.client.put(
            f"/api/teams/{other_team}/trade-block-note", json={"note": "hey"},
        )
        assert forbidden.status_code == 403

        # Happy path.
        ok = await ctx.client.put(
            f"/api/teams/{owned_team}/trade-block-note",
            json={"note": "  Looking for top-9 forwards  "},
        )
        assert ok.status_code == 200
        assert ok.json()["note"] == "Looking for top-9 forwards"

        # Read-back via GET.
        got = await ctx.client.get(f"/api/teams/{owned_team}/trade-block-note")
        assert got.json()["note"] == "Looking for top-9 forwards"


@pytest.mark.asyncio
async def test_retention_preference_cascades_to_listings():
    """Changing a team's salary-retention preference must immediately update
    every active trade-block listing for that team so the homepage widget
    reflects the new value without a full stats refresh.
    """
    async with isolated_router_app(trade_block_routes) as ctx:
        league_id = await seed_league(ctx.db)
        team_id = await seed_team(ctx.db, league_id=league_id)
        player_id = await seed_player(ctx.db)
        await ctx.client.post("/api/trade-block", json={
            "item_type": "player", "league_id": league_id,
            "team_id": team_id, "player_id": player_id,
        })

        r = await ctx.client.put(
            f"/api/teams/{team_id}/trade-block-preference",
            json={"preference": "willing_to_retain"},
        )
        assert r.status_code == 200

        item = await ctx.db.trade_block.find_one({"team_id": team_id})
        assert item["salary_retention_pref"] == "willing_to_retain"


@pytest.mark.asyncio
async def test_retention_preference_rejects_invalid_value():
    async with isolated_router_app(trade_block_routes) as ctx:
        league_id = await seed_league(ctx.db)
        team_id = await seed_team(ctx.db, league_id=league_id)
        r = await ctx.client.put(
            f"/api/teams/{team_id}/trade-block-preference",
            json={"preference": "totally_made_up"},
        )
        assert r.status_code == 400


@pytest.mark.asyncio
async def test_trade_block_summary_sorts_by_fantasy_points_desc():
    async with isolated_router_app(trade_block_routes) as ctx:
        await ctx.db.trade_block.insert_many([
            {"league_id": "L1", "owner_id": "u1", "fantasy_points": 10.0, "name": "Low"},
            {"league_id": "L1", "owner_id": "u1", "fantasy_points": 99.0, "name": "High"},
            {"league_id": "L1", "owner_id": "u1", "fantasy_points": 50.0, "name": "Mid"},
        ])
        r = await ctx.client.get("/api/leagues/L1/trade-block-summary?limit=2")
        body = r.json()
        names = [it["name"] for it in body["items"]]
        assert names == ["High", "Mid"]


@pytest.mark.asyncio
async def test_refresh_stats_blocks_non_commissioner():
    """Only commissioners + co-commissioners may run the refresh."""
    async with isolated_router_app(trade_block_routes) as ctx:
        league_id = await seed_league(ctx.db, commissioner_id="someone_else")
        r = await ctx.client.post(f"/api/leagues/{league_id}/trade-block/refresh-stats")
        assert r.status_code == 403


@pytest.mark.asyncio
async def test_refresh_stats_commissioner_allowed_when_in_co_list():
    async with isolated_router_app(trade_block_routes) as ctx:
        league_id = await seed_league(
            ctx.db,
            commissioner_id="someone_else",
            co_commissioners=["test_user_0001"],
        )
        r = await ctx.client.post(f"/api/leagues/{league_id}/trade-block/refresh-stats")
        assert r.status_code == 200
        assert r.json()["items_refreshed"] == 0
