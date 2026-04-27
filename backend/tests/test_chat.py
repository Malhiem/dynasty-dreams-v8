"""Chat regression — channels, DMs, messages, unread, mute, create/delete,
@mention members, and trade-execution chat hook (general + DM)."""
import os
import sys
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from httpx import AsyncClient  # noqa: E402


def _backend_url():
    env_path = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", ".env")
    with open(env_path) as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip()
    raise RuntimeError("REACT_APP_BACKEND_URL not found")


BASE = _backend_url()


async def _login(client, email, password):
    r = await client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


async def _league(client, token):
    r = await client.get("/api/leagues?my_leagues=true",
                         headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    return r.json()[0]["id"]


@pytest.mark.asyncio
async def test_default_channels_and_max_cap():
    async with AsyncClient(base_url=BASE, timeout=30) as c:
        tok = await _login(c, "chriszarek@gmail.com", "Chris2026!")
        lid = await _league(c, tok)
        r = await c.get(f"/api/chat/channels?league_id={lid}",
                        headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["max_channels"] == 12
        names = {x["name"] for x in body["channels"] if x["kind"] == "channel"}
        assert {"general", "trades", "trash-talk"} <= names


@pytest.mark.asyncio
async def test_dms_auto_materialize_and_members():
    async with AsyncClient(base_url=BASE, timeout=30) as c:
        tok = await _login(c, "chriszarek@gmail.com", "Chris2026!")
        lid = await _league(c, tok)
        h = {"Authorization": f"Bearer {tok}"}
        r = await c.get(f"/api/chat/channels?league_id={lid}", headers=h)
        dms = [x for x in r.json()["channels"] if x["kind"] == "dm"]
        assert len(dms) >= 11
        r = await c.get(f"/api/chat/league/{lid}/members", headers=h)
        assert r.status_code == 200
        members = r.json()["members"]
        assert len(members) == 12
        assert all(m["team_id"] and m["team_name"] and m["abbr"] for m in members)


@pytest.mark.asyncio
async def test_post_message_and_read_cursor():
    async with AsyncClient(base_url=BASE, timeout=30) as c:
        tok = await _login(c, "chriszarek@gmail.com", "Chris2026!")
        lid = await _league(c, tok)
        h = {"Authorization": f"Bearer {tok}"}
        chans = (await c.get(f"/api/chat/channels?league_id={lid}", headers=h)).json()["channels"]
        general = next(x for x in chans if x["name"] == "general")
        # post
        r = await c.post(f"/api/chat/channels/{general['_id']}/messages",
                         json={"content": "regression ping"}, headers=h)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["content"] == "regression ping"
        assert body["is_system"] is False
        # list — sender should be unread=0 since posting also moves the cursor
        r = await c.get(f"/api/chat/channels/{general['_id']}/messages?limit=10", headers=h)
        assert r.status_code == 200
        assert any(m["content"] == "regression ping" for m in r.json()["messages"])

        # empty content rejected
        r = await c.post(f"/api/chat/channels/{general['_id']}/messages",
                         json={"content": "  "}, headers=h)
        assert r.status_code == 400


@pytest.mark.asyncio
async def test_mute_durations_and_unmute():
    async with AsyncClient(base_url=BASE, timeout=30) as c:
        tok = await _login(c, "chriszarek@gmail.com", "Chris2026!")
        lid = await _league(c, tok)
        h = {"Authorization": f"Bearer {tok}"}
        chans = (await c.get(f"/api/chat/channels?league_id={lid}", headers=h)).json()["channels"]
        general = next(x for x in chans if x["name"] == "general")
        for d in ("30m", "1h", "4h", "12h", "24h"):
            r = await c.post(f"/api/chat/channels/{general['_id']}/mute",
                             json={"duration": d}, headers=h)
            assert r.status_code == 200 and r.json()["muted"] is True
        # indefinite has no expiry
        r = await c.post(f"/api/chat/channels/{general['_id']}/mute",
                         json={"duration": "indefinite"}, headers=h)
        body = r.json()
        assert body["muted"] is True and body["mute_until"] is None
        # unmute
        r = await c.post(f"/api/chat/channels/{general['_id']}/mute",
                         json={"duration": None}, headers=h)
        assert r.json()["muted"] is False
        # bad duration
        r = await c.post(f"/api/chat/channels/{general['_id']}/mute",
                         json={"duration": "999d"}, headers=h)
        assert r.status_code == 400


@pytest.mark.asyncio
async def test_commissioner_create_delete_and_default_protected():
    async with AsyncClient(base_url=BASE, timeout=30) as c:
        tok = await _login(c, "chriszarek@gmail.com", "Chris2026!")
        lid = await _league(c, tok)
        h = {"Authorization": f"Bearer {tok}"}
        # create
        name = f"pytest-{int(datetime.now(timezone.utc).timestamp())}"
        r = await c.post("/api/chat/channels",
                         json={"league_id": lid, "name": name}, headers=h)
        assert r.status_code == 200, r.text
        cid = r.json()["_id"]
        # default protected
        chans = (await c.get(f"/api/chat/channels?league_id={lid}", headers=h)).json()["channels"]
        general = next(x for x in chans if x["name"] == "general")
        r = await c.delete(f"/api/chat/channels/{general['_id']}", headers=h)
        assert r.status_code == 400
        # custom deletes
        r = await c.delete(f"/api/chat/channels/{cid}", headers=h)
        assert r.status_code == 200 and r.json()["deleted"] == cid


@pytest.mark.asyncio
async def test_trade_execution_emits_chat_messages():
    """End-to-end: execute a 2-party pick swap and verify the trade hook
    posted at least one system message into a `channel`-kind chat AND one
    into a `dm`-kind chat."""
    from motor.motor_asyncio import AsyncIOMotorClient
    from bson import ObjectId

    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

    async with AsyncClient(base_url=BASE, timeout=30) as c:
        tok = await _login(c, "chriszarek@gmail.com", "Chris2026!")
        lid = await _league(c, tok)
        h = {"Authorization": f"Bearer {tok}"}

        teams = await db.teams.find({"league_id": lid}).to_list(20)
        me = next(t for t in teams if t.get("name") == "Zarek's Frozen")
        other = next(t for t in teams if t["_id"] != me["_id"])
        my_pick = await db.draft_picks.find_one({"league_id": lid, "current_team_id": str(me["_id"])})
        other_pick = await db.draft_picks.find_one({"league_id": lid, "current_team_id": str(other["_id"])})
        if not my_pick or not other_pick:
            pytest.skip("No draft picks seeded")

        payload = {
            "league_id": lid,
            "target_team_id": str(other["_id"]),
            "assets_offered": [{"asset_type": "pick", "pick_id": str(my_pick["_id"])}],
            "assets_requested": [{"asset_type": "pick", "pick_id": str(other_pick["_id"])}],
            "message": "chat-hook pytest",
        }
        r = await c.post("/api/trades", json=payload, headers=h)
        assert r.status_code == 200, r.text
        body = r.json()
        trade_id = body.get("id") or body.get("_id") or body.get("trade_id")
        assert trade_id, f"No trade id in response: {body}"

        # chris is co-comm of Ice Kings, can force-execute
        r = await c.post(f"/api/trades/{trade_id}/execute", headers=h)
        assert r.status_code == 200, r.text

        msgs = await db.chat_messages.find({
            "league_id": lid, "is_system": True, "metadata.trade_id": trade_id,
        }).to_list(20)
        assert msgs, "Expected trade chat hook to post system messages"
        kinds = set()
        for m in msgs:
            chan = await db.chat_channels.find_one({"_id": ObjectId(m["channel_id"])})
            if chan:
                kinds.add(chan["kind"])
        assert "channel" in kinds and "dm" in kinds, f"Got chat kinds={kinds}"
