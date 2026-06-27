"""Iter 230ar — `current_pick_started_at` is set + advanced
properly so the Draft Room's per-pick timer is server-authoritative
(no more reset to full duration on page mount).
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
    email = f"iter230ar_{suffix}_{s}@example.com"
    await client.post(
        f"{API_URL}/api/auth/register",
        json={"email": email, "password": "TestPass123!",
              "username": f"i230ar_{suffix}_{s}"[:32],
              "name": f"iter230ar {suffix}"},
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


def _parse_iso(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


@pytest.mark.asyncio
async def test_start_draft_sets_current_pick_started_at():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[
        os.environ.get("DB_NAME", "test_database")
    ]
    async with httpx.AsyncClient(timeout=30.0) as client:
        commish = await _register(client, "commish")
        teammate = await _register(client, "tm")

        r = await client.post(
            f"{API_URL}/api/leagues", headers=_h(commish["token"]),
            json={"name": f"Iter230ar {uuid.uuid4().hex[:4]}",
                  "format": "dynasty", "scoring_format": "head_to_head",
                  "max_teams": 4, "draft_type": "snake", "roster_spots": 10},
        )
        r.raise_for_status()
        league_id = r.json()["id"]
        await db.teams.insert_one({
            "_id": ObjectId(), "league_id": league_id,
            "owner_id": teammate["id"], "name": "Iter230ar B", "roster": [],
        })

        r = await client.post(
            f"{API_URL}/api/drafts", headers=_h(commish["token"]),
            json={"league_id": league_id, "draft_type": "snake",
                  "total_rounds": 2, "time_per_pick": 60,
                  "scheduled_time": (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()},
        )
        r.raise_for_status()
        draft_id = str(r.json()["_id"])

        try:
            t0 = datetime.now(timezone.utc)
            r = await client.post(f"{API_URL}/api/drafts/{draft_id}/start",
                                  headers=_h(commish["token"]))
            r.raise_for_status()

            draft = await db.drafts.find_one({"_id": ObjectId(draft_id)})
            assert draft.get("current_pick_started_at")
            anchor = _parse_iso(draft["current_pick_started_at"])
            # Should be within ~5 seconds of when we called /start.
            assert abs((anchor - t0).total_seconds()) < 5
        finally:
            await db.drafts.delete_one({"_id": ObjectId(draft_id)})
            await db.teams.delete_many({"league_id": league_id})
            await db.leagues.delete_one({"_id": ObjectId(league_id)})


@pytest.mark.asyncio
async def test_make_pick_advances_current_pick_started_at():
    """Each pick should reset the per-pick anchor so the next manager
    gets the full time-per-pick window."""
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[
        os.environ.get("DB_NAME", "test_database")
    ]
    async with httpx.AsyncClient(timeout=30.0) as client:
        commish = await _register(client, "commish")
        teammate = await _register(client, "tm")

        r = await client.post(
            f"{API_URL}/api/leagues", headers=_h(commish["token"]),
            json={"name": f"Iter230ar adv {uuid.uuid4().hex[:4]}",
                  "format": "dynasty", "scoring_format": "head_to_head",
                  "max_teams": 4, "draft_type": "snake", "roster_spots": 10},
        )
        r.raise_for_status()
        league_id = r.json()["id"]
        await db.teams.insert_one({
            "_id": ObjectId(), "league_id": league_id,
            "owner_id": teammate["id"], "name": "Iter230ar adv B", "roster": [],
        })

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
            before = await db.drafts.find_one({"_id": ObjectId(draft_id)})
            anchor_before = before["current_pick_started_at"]

            # Brief pause so the second anchor will differ from the first
            # by more than the ISO-second precision.
            await asyncio.sleep(1.1)

            player = await db.players.find_one({})
            assert player

            r = await client.post(
                f"{API_URL}/api/drafts/{draft_id}/pick",
                headers=_h(commish["token"]),
                json={"player_id": str(player["_id"])},
            )
            assert r.status_code == 200, r.text

            after = await db.drafts.find_one({"_id": ObjectId(draft_id)})
            assert after["current_pick_started_at"] != anchor_before
            assert _parse_iso(after["current_pick_started_at"]) > _parse_iso(anchor_before)
        finally:
            await db.drafts.delete_one({"_id": ObjectId(draft_id)})
            await db.teams.delete_many({"league_id": league_id})
            await db.leagues.delete_one({"_id": ObjectId(league_id)})
