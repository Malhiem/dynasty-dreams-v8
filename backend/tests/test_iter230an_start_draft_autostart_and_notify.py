"""Iter 230an — `start_draft` enhancements:

1. Idempotency — second call on an active draft returns success
   (`already_active: true`) instead of 400.
2. Auto-start — non-commissioner trigger allowed after `scheduled_time`
   has elapsed (used by the frontend countdown hook to boot the draft
   when the clock hits 0).
3. Stale team_abbrs refresh — drafts created before all teams joined
   the league get their `team_abbrs` / `team_map` refreshed from the
   current league teams on start.
4. Pick #1 + #2 notifications fire on EVERY start (not only
   early-start) so the on-the-clock manager always gets a heads-up.
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


async def _register(client: httpx.AsyncClient, email_suffix: str):
    suffix = uuid.uuid4().hex[:6]
    email = f"iter230an_{email_suffix}_{suffix}@example.com"
    username = f"i230an_{email_suffix}_{suffix}"[:32]
    r = await client.post(
        f"{API_URL}/api/auth/register",
        json={
            "email": email, "password": "TestPass123!",
            "username": username,
            "name": f"iter230an {email_suffix}",
        },
    )
    r.raise_for_status()
    # Iter 230y note — clear cookies so the Bearer header wins on
    # subsequent calls when the same client is reused for multiple users.
    client.cookies.clear()
    login = await client.post(
        f"{API_URL}/api/auth/login",
        json={"email": email, "password": "TestPass123!"},
    )
    login.raise_for_status()
    client.cookies.clear()
    body = login.json()
    return {"email": email, "token": body["access_token"], "id": body["id"]}


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_start_draft_is_idempotent_when_already_active():
    """Second POST /drafts/{id}/start on an active draft returns
    success (`already_active: true`) instead of 400."""
    db_client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = db_client[os.environ.get("DB_NAME", "test_database")]
    async with httpx.AsyncClient(timeout=30.0) as client:
        commish = await _register(client, "commish")

        # Create league + 2 teams
        league_r = await client.post(
            f"{API_URL}/api/leagues", headers=_h(commish["token"]),
            json={"name": f"Iter230an idem {uuid.uuid4().hex[:4]}",
                  "format": "dynasty", "scoring_format": "head_to_head",
                  "max_teams": 4, "draft_type": "snake", "roster_spots": 10},
        )
        league_r.raise_for_status()
        league_id = league_r.json()["id"]

        # Add a 2nd team via direct DB insert (cheap shortcut)
        owner2 = await _register(client, "owner2")
        await db.teams.insert_one({
            "name": "Iter230an Team B", "league_id": league_id,
            "owner_id": owner2["id"], "roster": [],
            "_id": ObjectId(),
        })

        # Create draft
        draft_r = await client.post(
            f"{API_URL}/api/drafts", headers=_h(commish["token"]),
            json={"league_id": league_id, "draft_type": "snake",
                  "total_rounds": 2, "time_per_pick": 60,
                  "scheduled_time": (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()},
        )
        draft_r.raise_for_status()
        draft_id = str(draft_r.json()["_id"])

        try:
            r1 = await client.post(f"{API_URL}/api/drafts/{draft_id}/start",
                                   headers=_h(commish["token"]))
            assert r1.status_code == 200, r1.text
            assert r1.json().get("already_active") is not True

            r2 = await client.post(f"{API_URL}/api/drafts/{draft_id}/start",
                                   headers=_h(commish["token"]))
            assert r2.status_code == 200, r2.text
            assert r2.json().get("already_active") is True
        finally:
            await db.drafts.delete_one({"_id": ObjectId(draft_id)})
            await db.teams.delete_many({"league_id": league_id})
            await db.leagues.delete_one({"_id": ObjectId(league_id)})


@pytest.mark.asyncio
async def test_non_commish_can_auto_start_after_scheduled_time_elapsed():
    """A non-commissioner team owner CAN trigger /start once the
    draft's scheduled_time has passed (auto-start path used by the
    frontend countdown hook)."""
    db_client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = db_client[os.environ.get("DB_NAME", "test_database")]
    async with httpx.AsyncClient(timeout=30.0) as client:
        commish = await _register(client, "commish")
        teammate = await _register(client, "teammate")

        league_r = await client.post(
            f"{API_URL}/api/leagues", headers=_h(commish["token"]),
            json={"name": f"Iter230an autostart {uuid.uuid4().hex[:4]}",
                  "format": "dynasty", "scoring_format": "head_to_head",
                  "max_teams": 4, "draft_type": "snake", "roster_spots": 10},
        )
        league_r.raise_for_status()
        league_id = league_r.json()["id"]

        # Insert teammate's team into the league
        await db.teams.insert_one({
            "name": "Iter230an autostart team", "league_id": league_id,
            "owner_id": teammate["id"], "roster": [],
        })

        # Draft with scheduled_time 5 minutes in the past
        draft_r = await client.post(
            f"{API_URL}/api/drafts", headers=_h(commish["token"]),
            json={"league_id": league_id, "draft_type": "snake",
                  "total_rounds": 2, "time_per_pick": 60,
                  "scheduled_time": (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()},
        )
        draft_r.raise_for_status()
        draft_id = str(draft_r.json()["_id"])

        try:
            # Teammate (NOT commish) calls /start
            r = await client.post(f"{API_URL}/api/drafts/{draft_id}/start",
                                  headers=_h(teammate["token"]))
            assert r.status_code == 200, r.text

            # Verify status flipped to active
            updated = await db.drafts.find_one({"_id": ObjectId(draft_id)})
            assert updated["status"] == "active"
        finally:
            await db.drafts.delete_one({"_id": ObjectId(draft_id)})
            await db.teams.delete_many({"league_id": league_id})
            await db.leagues.delete_one({"_id": ObjectId(league_id)})


@pytest.mark.asyncio
async def test_non_commish_cannot_auto_start_before_scheduled_time():
    """A non-commissioner CANNOT trigger /start while the
    scheduled_time is still in the future — only after it elapses."""
    db_client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = db_client[os.environ.get("DB_NAME", "test_database")]
    async with httpx.AsyncClient(timeout=30.0) as client:
        commish = await _register(client, "commish")
        teammate = await _register(client, "teammate")

        league_r = await client.post(
            f"{API_URL}/api/leagues", headers=_h(commish["token"]),
            json={"name": f"Iter230an future {uuid.uuid4().hex[:4]}",
                  "format": "dynasty", "scoring_format": "head_to_head",
                  "max_teams": 4, "draft_type": "snake", "roster_spots": 10},
        )
        league_r.raise_for_status()
        league_id = league_r.json()["id"]

        await db.teams.insert_one({
            "name": "Iter230an future team", "league_id": league_id,
            "owner_id": teammate["id"], "roster": [],
        })

        # scheduled_time is in the FUTURE
        draft_r = await client.post(
            f"{API_URL}/api/drafts", headers=_h(commish["token"]),
            json={"league_id": league_id, "draft_type": "snake",
                  "total_rounds": 2, "time_per_pick": 60,
                  "scheduled_time": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()},
        )
        draft_r.raise_for_status()
        draft_id = str(draft_r.json()["_id"])

        try:
            r = await client.post(f"{API_URL}/api/drafts/{draft_id}/start",
                                  headers=_h(teammate["token"]))
            assert r.status_code == 403, r.text
        finally:
            await db.drafts.delete_one({"_id": ObjectId(draft_id)})
            await db.teams.delete_many({"league_id": league_id})
            await db.leagues.delete_one({"_id": ObjectId(league_id)})


@pytest.mark.asyncio
async def test_start_draft_refreshes_stale_team_abbrs():
    """When a draft was created before all teams joined the league
    (team_abbrs missing the late joiners), start_draft now refreshes
    the abbr list from the current set of league teams."""
    db_client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = db_client[os.environ.get("DB_NAME", "test_database")]
    async with httpx.AsyncClient(timeout=30.0) as client:
        commish = await _register(client, "commish")

        league_r = await client.post(
            f"{API_URL}/api/leagues", headers=_h(commish["token"]),
            json={"name": f"Iter230an stale {uuid.uuid4().hex[:4]}",
                  "format": "dynasty", "scoring_format": "head_to_head",
                  "max_teams": 4, "draft_type": "snake", "roster_spots": 10},
        )
        league_r.raise_for_status()
        league_id = league_r.json()["id"]

        # Create draft (only 1 team in league at this point — the
        # commissioner's auto-created team)
        draft_r = await client.post(
            f"{API_URL}/api/drafts", headers=_h(commish["token"]),
            json={"league_id": league_id, "draft_type": "snake",
                  "total_rounds": 2, "time_per_pick": 60,
                  "scheduled_time": (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()},
        )
        draft_r.raise_for_status()
        draft_id = str(draft_r.json()["_id"])

        # Confirm draft has only 1 team in team_abbrs (snapshot at creation)
        stale = await db.drafts.find_one({"_id": ObjectId(draft_id)})
        assert len(stale.get("team_abbrs") or []) <= 1

        # Now insert 2 more teams AFTER draft creation
        teammate1 = await _register(client, "tm1")
        teammate2 = await _register(client, "tm2")
        await db.teams.insert_one({
            "name": "Iter230an late team A", "league_id": league_id,
            "owner_id": teammate1["id"], "roster": [],
        })
        await db.teams.insert_one({
            "name": "Iter230an late team B", "league_id": league_id,
            "owner_id": teammate2["id"], "roster": [],
        })

        try:
            r = await client.post(f"{API_URL}/api/drafts/{draft_id}/start",
                                  headers=_h(commish["token"]))
            assert r.status_code == 200, r.text

            refreshed = await db.drafts.find_one({"_id": ObjectId(draft_id)})
            assert len(refreshed["team_abbrs"]) >= 3, refreshed["team_abbrs"]
            # team_map should also reflect all 3 teams
            assert len(refreshed["team_map"] or {}) >= 3
        finally:
            await db.drafts.delete_one({"_id": ObjectId(draft_id)})
            await db.teams.delete_many({"league_id": league_id})
            await db.leagues.delete_one({"_id": ObjectId(league_id)})


@pytest.mark.asyncio
async def test_start_draft_notifies_pick_one_and_two_even_without_early_start():
    """Regular (non-early-start) clock-started drafts must ALSO fire
    `draft_your_turn` (pick #1) and `draft_on_deck` (pick #2)
    notifications. Previously this was gated behind `if early_start:`."""
    db_client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = db_client[os.environ.get("DB_NAME", "test_database")]
    async with httpx.AsyncClient(timeout=30.0) as client:
        commish = await _register(client, "commish")
        teammate = await _register(client, "teammate")

        league_r = await client.post(
            f"{API_URL}/api/leagues", headers=_h(commish["token"]),
            json={"name": f"Iter230an notify {uuid.uuid4().hex[:4]}",
                  "format": "dynasty", "scoring_format": "head_to_head",
                  "max_teams": 4, "draft_type": "snake", "roster_spots": 10},
        )
        league_r.raise_for_status()
        league_id = league_r.json()["id"]

        await db.teams.insert_one({
            "name": "Iter230an notify team B", "league_id": league_id,
            "owner_id": teammate["id"], "roster": [],
        })

        draft_r = await client.post(
            f"{API_URL}/api/drafts", headers=_h(commish["token"]),
            json={"league_id": league_id, "draft_type": "snake",
                  "total_rounds": 2, "time_per_pick": 60,
                  "scheduled_time": (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()},
        )
        draft_r.raise_for_status()
        draft_id = str(draft_r.json()["_id"])

        try:
            # Clear pre-existing notifications for both users so we
            # only see ones from this start call.
            await db.notifications.delete_many(
                {"user_id": {"$in": [commish["id"], teammate["id"]]}})

            # early_start=False (default) — clock-started
            r = await client.post(f"{API_URL}/api/drafts/{draft_id}/start",
                                  headers=_h(commish["token"]))
            assert r.status_code == 200, r.text

            # Allow async fanout to flush
            await asyncio.sleep(0.3)

            notifs = await db.notifications.find(
                {"user_id": {"$in": [commish["id"], teammate["id"]]}}
            ).to_list(20)
            # Refreshed team_abbrs determines pick order — find which
            # owner is pick #1 and which is pick #2.
            refreshed = await db.drafts.find_one({"_id": ObjectId(draft_id)})
            abbrs = refreshed.get("team_abbrs") or []
            team_map = refreshed.get("team_map") or {}
            owner_for_pick = {}
            for i in (1, 2):
                if i <= len(abbrs):
                    tid = (team_map.get(abbrs[i - 1]) or {}).get("id")
                    if tid:
                        team_doc = await db.teams.find_one({"_id": ObjectId(tid)})
                        owner_for_pick[i] = team_doc.get("owner_id")
            assert 1 in owner_for_pick and 2 in owner_for_pick

            kinds_by_user = {}
            for n in notifs:
                kinds_by_user.setdefault(n["user_id"], []).append(n.get("type"))

            assert "draft_your_turn" in kinds_by_user.get(owner_for_pick[1], [])
            assert "draft_on_deck" in kinds_by_user.get(owner_for_pick[2], [])
        finally:
            await db.drafts.delete_one({"_id": ObjectId(draft_id)})
            await db.teams.delete_many({"league_id": league_id})
            await db.leagues.delete_one({"_id": ObjectId(league_id)})
            await db.notifications.delete_many(
                {"user_id": {"$in": [commish["id"], teammate["id"]]}})
