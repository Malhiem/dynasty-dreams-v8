"""
Iter 230aj — `start_draft(early_start=True)` also notifies the on-deck
team (pick #2's owner). User report (chriszarek1): "It should indicate
to Toronto Singularity's user that they are next to pick but the
clock hadn't started yet."

This test seeds a 2-team early-start draft and asserts BOTH pick #1's
owner (your turn) AND pick #2's owner (on deck) receive notifications.
"""
import os
import sys
import random
import pytest
from bson import ObjectId
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from httpx import AsyncClient


def _backend_url():
    env = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", ".env")
    with open(env) as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip()
    raise RuntimeError("REACT_APP_BACKEND_URL not found")


BASE = _backend_url()


async def _register(client, suffix):
    suf = f"{suffix}_{random.randint(10000, 99999)}"
    r = await client.post(
        "/api/auth/register",
        json={
            "username": f"u_{suf}",
            "email": f"u_{suf}@example.com",
            "password": "TestPass123!",
        },
    )
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    me = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    user_id = me.json()["id"]
    # Clear cookie jar (see iter230y comment for full rationale).
    try: client.cookies.clear()
    except Exception: pass
    return token, user_id


async def _connect_db():
    from motor.motor_asyncio import AsyncIOMotorClient
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


@pytest.mark.asyncio
async def test_early_start_notifies_pick_1_AND_pick_2_owners():
    db = await _connect_db()

    async with AsyncClient(base_url=BASE, timeout=30) as client:
        commish_token, commish_id = await _register(client, "commish_aj")
        p1_token, p1_id = await _register(client, "pick1_aj")
        p2_token, p2_id = await _register(client, "pick2_aj")
        commish_h = {"Authorization": f"Bearer {commish_token}"}
        p1_h = {"Authorization": f"Bearer {p1_token}"}
        p2_h = {"Authorization": f"Bearer {p2_token}"}

        league_id = str(ObjectId())
        t1_id = ObjectId()
        t2_id = ObjectId()
        draft_id = ObjectId()
        scheduled_at = datetime.now(timezone.utc) + timedelta(hours=2)
        scheduled_iso = scheduled_at.isoformat().replace("+00:00", "Z")

        await db.leagues.insert_one({
            "_id": ObjectId(league_id),
            "name": "iter230aj league",
            "commissioner_id": commish_id,
            "admin_ids": [commish_id],
            "current_teams": 2,
        })
        await db.teams.insert_many([
            {"_id": t1_id, "league_id": league_id, "name": "Team One", "logo_abbr": "T1",
             "owner_id": p1_id, "co_owner_ids": [], "roster": []},
            {"_id": t2_id, "league_id": league_id, "name": "Team Two", "logo_abbr": "T2",
             "owner_id": p2_id, "co_owner_ids": [], "roster": []},
        ])
        await db.drafts.insert_one({
            "_id": draft_id,
            "league_id": league_id,
            "name": "iter230aj draft",
            "status": "scheduled",
            "scheduled_time": scheduled_iso,
            "team_abbrs": ["T1", "T2"],
            "team_map": {
                "T1": {"id": str(t1_id), "name": "Team One"},
                "T2": {"id": str(t2_id), "name": "Team Two"},
            },
            "snake_draft": True,
            "total_rounds": 2,
            "current_pick": 1,
            "picks": [],
            "early_start": False,
        })

        try:
            r = await client.post(
                f"/api/drafts/{draft_id}/start?early_start=true",
                headers=commish_h,
            )
            assert r.status_code == 200, r.text

            # Pick #1 owner — `draft_your_turn`.
            n1 = (await client.get("/api/notifications?limit=10", headers=p1_h)).json()
            items1 = n1 if isinstance(n1, list) else n1.get("notifications", [])
            yt = [x for x in items1 if x.get("type") == "draft_your_turn" and x.get("league_id") == league_id]
            assert yt, "pick #1 owner missing draft_your_turn notification"
            assert "clock will start at" in (yt[0].get("message") or "").lower()

            # Pick #2 owner — `draft_on_deck`.
            n2 = (await client.get("/api/notifications?limit=10", headers=p2_h)).json()
            items2 = n2 if isinstance(n2, list) else n2.get("notifications", [])
            od = [x for x in items2 if x.get("type") == "draft_on_deck" and x.get("league_id") == league_id]
            assert od, (
                "pick #2 owner SHOULD receive `draft_on_deck` notification "
                "when the commissioner starts a no-clock draft (the user's "
                "Toronto Singularity bug)"
            )
            od_body = (od[0].get("message") or "").lower()
            assert "pick #2" in od_body and "up next" in od_body
            assert "clock will start at" in od_body, (
                f"on-deck body should include clock-activation hint, got: {od_body!r}"
            )

            # Pick #2 owner should NOT also receive the YOUR_TURN ping —
            # would be confusing UX (only pick #1's owner is "on the clock").
            yt2 = [x for x in items2 if x.get("type") == "draft_your_turn" and x.get("league_id") == league_id]
            assert not yt2, "pick #2 owner should NOT get draft_your_turn — they're on deck, not on the clock"
        finally:
            await db.drafts.delete_one({"_id": draft_id})
            await db.teams.delete_many({"_id": {"$in": [t1_id, t2_id]}})
            await db.leagues.delete_one({"_id": ObjectId(league_id)})
            await db.notifications.delete_many({"league_id": league_id})
            for uid in (commish_id, p1_id, p2_id):
                try: await db.users.delete_one({"_id": ObjectId(uid)})
                except Exception: pass
