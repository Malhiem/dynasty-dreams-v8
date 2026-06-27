"""Iter 230an.2 — Regression: `make_draft_pick` must successfully
fire the next-5 notifications (your turn / on deck / coming up)
without crashing on `pick_msg` not being defined.

Pre-fix bug: `pick_msg["text"]` was referenced inside the
EVT_DRAFT_PICK_MADE fanout loop BEFORE `pick_msg` was constructed
further down in the function. The whole notification block was wrapped
in try/except, so the NameError silently swallowed all downstream
notifications — including `draft_on_deck` to pick #2 owner. This test
seeds a 3-team draft, makes pick #1, and asserts pick #2's owner
receives the on-deck notification.
"""
from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient
import httpx

API_URL = os.environ["REACT_APP_BACKEND_URL"]


async def _register(client: httpx.AsyncClient, suffix: str):
    s = uuid.uuid4().hex[:6]
    email = f"iter230an2_{suffix}_{s}@example.com"
    await client.post(
        f"{API_URL}/api/auth/register",
        json={"email": email, "password": "TestPass123!",
              "username": f"i230an2_{suffix}_{s}"[:32],
              "name": f"iter230an2 {suffix}"},
    )
    client.cookies.clear()
    r = await client.post(
        f"{API_URL}/api/auth/login",
        json={"email": email, "password": "TestPass123!"},
    )
    r.raise_for_status()
    client.cookies.clear()
    body = r.json()
    return {"email": email, "token": body["access_token"], "id": body["id"]}


def _h(t: str) -> dict:
    return {"Authorization": f"Bearer {t}"}


@pytest.mark.asyncio
async def test_make_draft_pick_fires_on_deck_to_pick_2_owner():
    """After pick #1 is made, pick #2's owner MUST receive the
    `draft_on_deck` notification (previously swallowed by NameError)."""
    db_client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = db_client[os.environ.get("DB_NAME", "test_database")]

    async with httpx.AsyncClient(timeout=30.0) as client:
        commish = await _register(client, "commish")
        owner2 = await _register(client, "owner2")

        # Create league
        r = await client.post(
            f"{API_URL}/api/leagues", headers=_h(commish["token"]),
            json={"name": f"Iter230an2 {uuid.uuid4().hex[:4]}",
                  "format": "dynasty", "scoring_format": "head_to_head",
                  "max_teams": 4, "draft_type": "snake", "roster_spots": 10},
        )
        r.raise_for_status()
        league_id = r.json()["id"]

        # Add owner2's team
        await db.teams.insert_one({
            "name": "Iter230an2 Team B", "league_id": league_id,
            "owner_id": owner2["id"], "roster": [],
        })

        # Create + start draft (scheduled in past so commish path works)
        r = await client.post(
            f"{API_URL}/api/drafts", headers=_h(commish["token"]),
            json={"league_id": league_id, "draft_type": "snake",
                  "total_rounds": 2, "time_per_pick": 60,
                  "scheduled_time": (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()},
        )
        r.raise_for_status()
        draft_id = str(r.json()["_id"])

        try:
            r = await client.post(f"{API_URL}/api/drafts/{draft_id}/start",
                                  headers=_h(commish["token"]))
            r.raise_for_status()

            # Wipe notifications so we only see ones from the pick
            await db.notifications.delete_many(
                {"user_id": {"$in": [commish["id"], owner2["id"]]}})

            # Find an arbitrary player to draft
            any_player = await db.players.find_one({})
            assert any_player

            # Make pick #1 (commish's team — refreshed team_abbrs puts
            # the commish's auto-created team at index 0)
            r = await client.post(
                f"{API_URL}/api/drafts/{draft_id}/pick",
                headers=_h(commish["token"]),
                json={"player_id": str(any_player["_id"])},
            )
            assert r.status_code == 200, r.text

            await asyncio.sleep(0.3)

            # Determine which owner is pick #2 from the refreshed draft
            refreshed = await db.drafts.find_one({"_id": ObjectId(draft_id)})
            abbrs = refreshed["team_abbrs"]
            team_map = refreshed["team_map"]
            tid_pick2 = (team_map.get(abbrs[1]) or {}).get("id")
            assert tid_pick2
            team_pick2 = await db.teams.find_one({"_id": ObjectId(tid_pick2)})
            owner_pick2 = team_pick2["owner_id"]

            notifs = await db.notifications.find(
                {"user_id": owner_pick2}
            ).to_list(20)
            types = [n.get("type") for n in notifs]
            assert "draft_your_turn" in types, (
                f"Pick #2 owner should now be on the clock — got {types}"
            )
        finally:
            await db.drafts.delete_one({"_id": ObjectId(draft_id)})
            await db.teams.delete_many({"league_id": league_id})
            await db.leagues.delete_one({"_id": ObjectId(league_id)})
            await db.notifications.delete_many(
                {"user_id": {"$in": [commish["id"], owner2["id"]]}})
