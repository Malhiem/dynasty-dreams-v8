"""Focused unit tests for `routes/chat.py` — channels list, create, delete,
post message, mute. Default-channel auto-creation + DM materialization are
exercised by `list_channels`."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from routes import chat as chat_routes  # noqa: E402

from tests.router_test_utils import isolated_router_app  # noqa: E402


async def _seed_league(db, *, commissioner_id="test_user_0001"):
    res = await db.leagues.insert_one({
        "name": "Chat Test League",
        "commissioner_id": commissioner_id,
        "co_commissioners": [],
    })
    return str(res.inserted_id)


async def _seed_team(db, *, league_id, name, owner_id):
    res = await db.teams.insert_one({
        "league_id": league_id, "name": name, "owner_id": owner_id, "owner_name": owner_id,
    })
    return str(res.inserted_id)


@pytest.mark.asyncio
async def test_list_channels_auto_seeds_defaults():
    async with isolated_router_app(chat_routes) as ctx:
        league_id = await _seed_league(ctx.db)
        await _seed_team(ctx.db, league_id=league_id, name="Mine", owner_id="test_user_0001")
        r = await ctx.client.get(f"/api/chat/channels?league_id={league_id}")
        assert r.status_code == 200
        body = r.json()
        names = [c["name"] for c in body["channels"] if c["kind"] == "channel"]
        assert "general" in names
        assert "trades" in names
        assert "trash-talk" in names


@pytest.mark.asyncio
async def test_list_channels_materializes_dms_with_other_teams():
    async with isolated_router_app(chat_routes) as ctx:
        league_id = await _seed_league(ctx.db)
        await _seed_team(ctx.db, league_id=league_id, name="Mine", owner_id="test_user_0001")
        await _seed_team(ctx.db, league_id=league_id, name="Rival", owner_id="rival_user")
        r = await ctx.client.get(f"/api/chat/channels?league_id={league_id}")
        body = r.json()
        dms = [c for c in body["channels"] if c["kind"] == "dm"]
        assert len(dms) == 1
        assert "Mine" in dms[0]["name"] and "Rival" in dms[0]["name"]


@pytest.mark.asyncio
async def test_create_channel_requires_commissioner():
    async with isolated_router_app(chat_routes) as ctx:
        # Someone else is the commissioner — current test_user shouldn't be allowed
        league_id = await _seed_league(ctx.db, commissioner_id="other_user")
        r = await ctx.client.post(
            "/api/chat/channels",
            json={"league_id": league_id, "name": "rumors"},
        )
        assert r.status_code == 403


@pytest.mark.asyncio
async def test_create_channel_commissioner_succeeds_and_normalizes_name():
    async with isolated_router_app(chat_routes) as ctx:
        league_id = await _seed_league(ctx.db)
        r = await ctx.client.post(
            "/api/chat/channels",
            json={"league_id": league_id, "name": "Hot Takes"},
        )
        assert r.status_code == 200
        body = r.json()
        # name lowercased + spaces → hyphens
        assert body["name"] == "hot-takes"


@pytest.mark.asyncio
async def test_create_channel_rejects_duplicate():
    async with isolated_router_app(chat_routes) as ctx:
        league_id = await _seed_league(ctx.db)
        # Trigger default-channel creation
        await ctx.client.get(f"/api/chat/channels?league_id={league_id}")
        # Now try to create another `general` — already exists
        r = await ctx.client.post(
            "/api/chat/channels",
            json={"league_id": league_id, "name": "general"},
        )
        assert r.status_code == 400
        assert "exists" in r.json()["detail"]


@pytest.mark.asyncio
async def test_create_channel_400_when_name_missing():
    async with isolated_router_app(chat_routes) as ctx:
        league_id = await _seed_league(ctx.db)
        r = await ctx.client.post(
            "/api/chat/channels",
            json={"league_id": league_id, "name": ""},
        )
        assert r.status_code == 400


@pytest.mark.asyncio
async def test_delete_default_channel_400():
    async with isolated_router_app(chat_routes) as ctx:
        league_id = await _seed_league(ctx.db)
        await ctx.client.get(f"/api/chat/channels?league_id={league_id}")
        gen = await ctx.db.chat_channels.find_one({
            "league_id": league_id, "name": "general",
        })
        r = await ctx.client.delete(f"/api/chat/channels/{gen['_id']}")
        assert r.status_code == 400


@pytest.mark.asyncio
async def test_delete_custom_channel_removes_messages_and_reads():
    async with isolated_router_app(chat_routes) as ctx:
        league_id = await _seed_league(ctx.db)
        # Create a custom channel via the endpoint
        c = await ctx.client.post(
            "/api/chat/channels",
            json={"league_id": league_id, "name": "rumors"},
        )
        cid = c.json()["_id"]
        # Seed a message + read row directly
        await ctx.db.chat_messages.insert_one({"channel_id": cid, "content": "hi"})
        await ctx.db.chat_reads.insert_one({"channel_id": cid, "user_id": "u1"})

        r = await ctx.client.delete(f"/api/chat/channels/{cid}")
        assert r.status_code == 200
        # Cascading delete
        assert await ctx.db.chat_messages.count_documents({"channel_id": cid}) == 0
        assert await ctx.db.chat_reads.count_documents({"channel_id": cid}) == 0
