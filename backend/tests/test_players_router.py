"""Focused unit tests for `routes/players.py`.

Targets the search/filter/pagination logic on `/players` and the simple
watchlist + news-bulk endpoints. The heavy per-player endpoints
(`/players/{id}/historical-stats`, `/recent-games`, `/dynasty-career`)
hit the external NHL API + are covered by `test_player_profile.py`.
"""
import os
import sys
from datetime import datetime, timezone

import pytest
from bson import ObjectId

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from routes import players as players_routes  # noqa: E402

from tests.router_test_utils import isolated_router_app  # noqa: E402


async def _seed_player(db, *, name, position="C", team="EDM", points=50, **extra):
    doc = {
        "name": name, "position": position, "team": team,
        "team_name": "Edmonton Oilers",
        "points": points, "goals": int(points * 0.4),
        "assists": int(points * 0.6),
        "games_played": 40,
    }
    doc.update(extra)
    res = await db.players.insert_one(doc)
    return str(res.inserted_id)


@pytest.mark.asyncio
async def test_players_list_default_sorted_by_points_desc():
    async with isolated_router_app(players_routes) as ctx:
        await _seed_player(ctx.db, name="Mid",  points=30)
        await _seed_player(ctx.db, name="Star", points=95)
        await _seed_player(ctx.db, name="Sub",  points=10)
        r = await ctx.client.get("/api/players")
        assert r.status_code == 200
        body = r.json()
        names = [p["name"] for p in body["players"]]
        assert names == ["Star", "Mid", "Sub"]
        assert body["total"] == 3


@pytest.mark.asyncio
async def test_players_search_substring_match():
    async with isolated_router_app(players_routes) as ctx:
        await _seed_player(ctx.db, name="Connor McDavid",  team="EDM")
        await _seed_player(ctx.db, name="Sidney Crosby",   team="PIT")
        await _seed_player(ctx.db, name="Connor Bedard",   team="CHI")
        r = await ctx.client.get("/api/players?search=connor")
        names = [p["name"] for p in r.json()["players"]]
        assert "Connor McDavid" in names
        assert "Connor Bedard" in names
        assert "Sidney Crosby" not in names


@pytest.mark.asyncio
async def test_players_position_filter():
    async with isolated_router_app(players_routes) as ctx:
        await _seed_player(ctx.db, name="A", position="C")
        await _seed_player(ctx.db, name="B", position="LW")
        await _seed_player(ctx.db, name="C", position="RW")
        # Position "W" should match both LW + RW
        r = await ctx.client.get("/api/players?position=W")
        names = sorted(p["name"] for p in r.json()["players"])
        assert names == ["B", "C"]


@pytest.mark.asyncio
async def test_players_pagination():
    async with isolated_router_app(players_routes) as ctx:
        for i in range(7):
            await _seed_player(ctx.db, name=f"P{i:02d}", points=100 - i)
        r = await ctx.client.get("/api/players?limit=3&page=2")
        body = r.json()
        # Page 2 with limit 3 = rows 4,5,6 (sorted by points desc)
        assert len(body["players"]) == 3
        assert body["total"] == 7
        assert [p["name"] for p in body["players"]] == ["P03", "P04", "P05"]


@pytest.mark.asyncio
async def test_players_availability_free_agent_excludes_rostered():
    async with isolated_router_app(players_routes) as ctx:
        pid_owned = await _seed_player(ctx.db, name="Owned", points=80)
        await _seed_player(ctx.db, name="Free", points=50)
        league_res = await ctx.db.leagues.insert_one({"name": "L"})
        league_id = str(league_res.inserted_id)
        await ctx.db.teams.insert_one({
            "league_id": league_id, "name": "T", "owner_id": "u1",
            "roster": [pid_owned],
        })
        r = await ctx.client.get(
            f"/api/players?league_id={league_id}&availability=free_agent",
        )
        names = [p["name"] for p in r.json()["players"]]
        assert names == ["Free"]


@pytest.mark.asyncio
async def test_watchlist_empty_for_new_user():
    async with isolated_router_app(players_routes) as ctx:
        r = await ctx.client.get("/api/watchlist?league_id=L1")
        assert r.json() == {"player_ids": []}


@pytest.mark.asyncio
async def test_watchlist_toggle_add_then_remove():
    async with isolated_router_app(players_routes) as ctx:
        pid = await _seed_player(ctx.db, name="Watch Me")
        # First toggle → add
        r1 = await ctx.client.post(
            "/api/watchlist/toggle",
            json={"player_id": pid, "league_id": "L1"},
        )
        assert r1.json()["added"] is True
        assert r1.json()["in_watchlist"] is True

        wl = await ctx.client.get("/api/watchlist?league_id=L1")
        assert pid in wl.json()["player_ids"]

        # Second toggle → remove
        r2 = await ctx.client.post(
            "/api/watchlist/toggle",
            json={"player_id": pid, "league_id": "L1"},
        )
        assert r2.json()["added"] is False
        assert r2.json()["in_watchlist"] is False


@pytest.mark.asyncio
async def test_watchlist_toggle_400_when_player_id_missing():
    async with isolated_router_app(players_routes) as ctx:
        r = await ctx.client.post("/api/watchlist/toggle", json={"league_id": "L1"})
        assert r.status_code == 400


@pytest.mark.asyncio
async def test_news_bulk_empty_input_returns_empty_dict():
    async with isolated_router_app(players_routes) as ctx:
        r = await ctx.client.post("/api/players/news-bulk", json={"player_ids": []})
        assert r.json() == {"news": {}}


@pytest.mark.asyncio
async def test_news_bulk_returns_most_recent_per_player_with_signal_band():
    async with isolated_router_app(players_routes) as ctx:
        pid = "p1"
        now = datetime.now(timezone.utc)
        # Two news rows for same player — most recent (fresh) wins
        from datetime import timedelta
        await ctx.db.player_news.insert_many([
            {"player_id": pid, "headline": "Old", "published_at": now - timedelta(days=10)},
            {"player_id": pid, "headline": "Fresh", "published_at": now - timedelta(days=2)},
        ])
        r = await ctx.client.post(
            "/api/players/news-bulk", json={"player_ids": [pid]},
        )
        body = r.json()["news"]
        assert pid in body
        assert body[pid]["news_headline"] == "Fresh"
        assert body[pid]["news_signal"] == "fresh"


@pytest.mark.asyncio
async def test_news_bulk_drops_news_older_than_35_days():
    async with isolated_router_app(players_routes) as ctx:
        from datetime import timedelta
        await ctx.db.player_news.insert_one({
            "player_id": "p1", "headline": "Ancient",
            "published_at": datetime.now(timezone.utc) - timedelta(days=60),
        })
        r = await ctx.client.post(
            "/api/players/news-bulk", json={"player_ids": ["p1"]},
        )
        # Signal=None branches drops the row
        assert r.json()["news"] == {}
