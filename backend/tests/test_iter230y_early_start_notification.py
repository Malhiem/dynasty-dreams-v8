"""
Iter 230y — When a commissioner starts a draft with `early_start=True`
(no clock), the team owning pick #1 receives an immediate
`draft_your_turn` notification whose body explicitly tells them when
the auto-clock will activate.

Before this change `start_draft` was silent for no-clock starts — the
first `draft_your_turn` notification only fired AFTER pick #1 was made
(via `make_draft_pick`'s look-ahead), meaning the manager who SHOULD
have been picking had no clue they were up unless someone pinged them
in chat. This test reproduces that scenario and asserts the new
notification.
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
    # The register endpoint's response `id` field has drifted from the
    # actually-authenticated user's id in some envs (off-by-one when
    # users are created in rapid succession). Resolve the canonical
    # user id via /auth/me so the league.commissioner_id we insert
    # actually matches the auth context.
    me = await client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me.status_code == 200, me.text
    user_id = me.json()["id"]
    # CRITICAL — clear the access_token cookie before returning. The
    # register endpoint sets `access_token` as an HttpOnly cookie, and
    # `get_current_user` reads cookies BEFORE the Authorization header.
    # If we leave the cookie in the AsyncClient's jar, every subsequent
    # request authenticates as THE LAST USER REGISTERED on this
    # client, regardless of the Bearer header you pass. That made the
    # 2-user (commish + owner) scenario impossible to test with a
    # single client. Clearing the cookie after each registration lets
    # explicit `Authorization: Bearer …` headers win.
    try:
        client.cookies.clear()
    except Exception:
        pass
    return token, user_id


async def _connect_db():
    from motor.motor_asyncio import AsyncIOMotorClient
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


@pytest.mark.asyncio
async def test_early_start_notifies_first_pick_owner_with_clock_time():
    db = await _connect_db()

    async with AsyncClient(base_url=BASE, timeout=30) as client:
        # Two users: a commissioner (P0) and a pick #1 owner (P1).
        commish_token, commish_id = await _register(client, "commish")
        owner_token, owner_id = await _register(client, "owner")
        commish_h = {"Authorization": f"Bearer {commish_token}"}
        owner_h = {"Authorization": f"Bearer {owner_token}"}

        # Seed a league + a team owned by P1 + a draft scheduled 2 hours
        # in the future. All `team_abbrs` point to the owner's team so
        # pick #1 unambiguously belongs to them.
        league_id = str(ObjectId())
        team_id = ObjectId()
        draft_id = ObjectId()
        scheduled_at = datetime.now(timezone.utc) + timedelta(hours=2)
        scheduled_iso = scheduled_at.isoformat().replace("+00:00", "Z")

        await db.leagues.insert_one({
            "_id": ObjectId(league_id),
            "name": "iter230y league",
            "commissioner_id": commish_id,
            "admin_ids": [commish_id],
            "current_teams": 1,
        })
        await db.teams.insert_one({
            "_id": team_id,
            "league_id": league_id,
            "name": "iter230y team",
            "logo_abbr": "I2Y",
            "owner_id": owner_id,
            "co_owner_ids": [],
            "roster": [],
        })
        await db.drafts.insert_one({
            "_id": draft_id,
            "league_id": league_id,
            "name": "iter230y draft",
            "status": "scheduled",
            "scheduled_time": scheduled_iso,
            "team_abbrs": ["I2Y"],
            "team_map": {"I2Y": {"id": str(team_id), "name": "iter230y team"}},
            "snake_draft": True,
            "total_rounds": 1,
            "current_pick": 1,
            "picks": [],
            "early_start": False,
        })

        try:
            # Hit start_draft with early_start=true as the commissioner.
            r = await client.post(
                f"/api/drafts/{draft_id}/start?early_start=true",
                headers=commish_h,
            )
            assert r.status_code == 200, r.text
            assert r.json()["early_start"] is True

            # Owner of pick #1 should now have a draft_your_turn
            # notification whose body references the clock-activation
            # ISO timestamp.
            n = await client.get("/api/notifications?limit=10", headers=owner_h)
            assert n.status_code == 200, n.text
            payload = n.json()
            items = payload if isinstance(payload, list) else payload.get("notifications", [])
            yt = [
                x for x in items
                if x.get("type") == "draft_your_turn"
                and (x.get("league_id") == league_id)
            ]
            assert yt, (
                "Pick #1 owner should have received a draft_your_turn "
                "notification when the commissioner started the draft "
                "with early_start=true"
            )
            body = yt[0].get("message") or ""
            assert "clock will start at" in body.lower(), (
                f"Expected clock-activation hint in body, got: {body!r}"
            )
            # The body must include the actual scheduled_time so the
            # manager knows exactly when the auto-clock kicks in.
            assert scheduled_iso[:16] in body, (
                f"Expected scheduled time {scheduled_iso[:16]} in body, got: {body!r}"
            )
            assert "pick now" in body.lower(), (
                f"Expected explicit 'pick now' affordance, got: {body!r}"
            )

            # The on-the-clock owner gets the notification — but NOT
            # the commissioner (unless they happen to be the same user,
            # which they aren't in this test).
            n_c = await client.get("/api/notifications?limit=10", headers=commish_h)
            payload_c = n_c.json()
            items_c = payload_c if isinstance(payload_c, list) else payload_c.get("notifications", [])
            yt_c = [
                x for x in items_c
                if x.get("type") == "draft_your_turn"
                and x.get("league_id") == league_id
            ]
            assert not yt_c, (
                "Commissioner shouldn't get the on-the-clock ping unless "
                "they're also the pick #1 owner"
            )
        finally:
            await db.drafts.delete_one({"_id": draft_id})
            await db.teams.delete_one({"_id": team_id})
            await db.leagues.delete_one({"_id": ObjectId(league_id)})
            await db.notifications.delete_many({"league_id": league_id})
            # Best-effort: also nuke the throwaway users (avoids leaking
            # tens of seeded accounts over time).
            for uid in (commish_id, owner_id):
                try:
                    await db.users.delete_one({"_id": ObjectId(uid)})
                except Exception:
                    pass
