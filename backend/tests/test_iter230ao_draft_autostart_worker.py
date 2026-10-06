"""Iter 230ao — Draft auto-start worker tests.

Confirms the worker boots any draft whose `scheduled_time` has elapsed
but is still in `status: "scheduled"`, refreshes stale `team_abbrs`,
fires pick #1 + pick #2 notifications, and skips stale (>24h late) /
future-scheduled / already-active drafts.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

import pytest
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.draft_autostart_worker import run_once


def _db():
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[
        os.environ.get("DB_NAME", os.environ["DB_NAME"])
    ]


async def _seed_user(db, email_prefix: str):
    uid = str(ObjectId())
    await db.users.insert_one({
        "_id": ObjectId(uid),
        "email": f"{email_prefix}_{uid[:6]}@iter230ao.test",
        "username": f"{email_prefix}_{uid[:6]}",
        "name": f"iter230ao {email_prefix}",
    })
    return uid


async def _seed_league_with_teams(db, n_teams: int = 3):
    uids = [await _seed_user(db, f"u{i}") for i in range(n_teams)]
    league_id = ObjectId()
    await db.leagues.insert_one({
        "_id": league_id,
        "name": f"Iter230ao league {league_id}",
        "commissioner_id": uids[0],
        "status": "active",
        "current_season_status": "regular",
    })
    team_ids = []
    for i, uid in enumerate(uids):
        t_id = ObjectId()
        await db.teams.insert_one({
            "_id": t_id,
            "name": f"Iter230ao Team {i+1}",
            "league_id": str(league_id),
            "owner_id": uid,
            "roster": [],
        })
        team_ids.append(str(t_id))
    return str(league_id), uids, team_ids


async def _cleanup(db, league_id, user_ids):
    await db.drafts.delete_many({"league_id": league_id})
    await db.teams.delete_many({"league_id": league_id})
    await db.leagues.delete_one({"_id": ObjectId(league_id)})
    await db.users.delete_many({"_id": {"$in": [ObjectId(u) for u in user_ids]}})
    await db.notifications.delete_many({"user_id": {"$in": user_ids}})


@pytest.mark.asyncio
async def test_autostart_boots_due_scheduled_draft_and_notifies_first_two_picks():
    db = _db()
    # Iter 230ao — the worker delegates to `routes.drafts` helpers which
    # read `_deps["db"]`. In the live server those are wired at startup;
    # in this isolated unit test we inject them by hand so
    # `create_notification` can find the DB.
    from routes import drafts as drafts_routes
    drafts_routes._deps.setdefault("db", db)
    drafts_routes._deps["db"] = db

    league_id, uids, _ = await _seed_league_with_teams(db, 3)

    past = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    draft_id = ObjectId()
    await db.drafts.insert_one({
        "_id": draft_id,
        "league_id": league_id,
        "league_name": "Iter230ao league",
        "name": "Iter230ao draft",
        "status": "scheduled",
        "scheduled_time": past,
        "draft_type": "snake",
        "snake_draft": True,
        "total_rounds": 2,
        "time_per_pick": 60,
        "current_pick": 1,
        "team_abbrs": [],  # intentionally empty — worker should refresh
        "team_map": {},
        "picks": [],
        "chat_messages": [],
    })

    try:
        await db.notifications.delete_many({"user_id": {"$in": uids}})

        counts = await run_once(db)
        assert counts["started"] >= 1

        refreshed = await db.drafts.find_one({"_id": draft_id})
        assert refreshed["status"] == "active"
        assert len(refreshed["team_abbrs"]) == 3
        assert refreshed.get("started_at")

        # Pick #1 owner should have draft_your_turn; pick #2 → on_deck.
        abbr_to_owner = {}
        for abbr, info in (refreshed.get("team_map") or {}).items():
            tid = info.get("id")
            if not tid:
                continue
            t = await db.teams.find_one({"_id": ObjectId(tid)})
            abbr_to_owner[abbr] = t.get("owner_id")
        owner_pick1 = abbr_to_owner.get(refreshed["team_abbrs"][0])
        owner_pick2 = abbr_to_owner.get(refreshed["team_abbrs"][1])

        n1 = await db.notifications.find({"user_id": owner_pick1}).to_list(10)
        n2 = await db.notifications.find({"user_id": owner_pick2}).to_list(10)
        assert any(n.get("type") == "draft_your_turn" for n in n1), n1
        assert any(n.get("type") == "draft_on_deck" for n in n2), n2
    finally:
        await _cleanup(db, league_id, uids)


@pytest.mark.asyncio
async def test_autostart_skips_future_scheduled_drafts():
    db = _db()
    league_id, uids, _ = await _seed_league_with_teams(db, 2)

    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    draft_id = ObjectId()
    await db.drafts.insert_one({
        "_id": draft_id, "league_id": league_id,
        "league_name": "Iter230ao", "name": "Iter230ao future",
        "status": "scheduled", "scheduled_time": future,
        "draft_type": "snake", "snake_draft": True,
        "total_rounds": 2, "time_per_pick": 60,
        "current_pick": 1, "team_abbrs": [], "team_map": {},
        "picks": [], "chat_messages": [],
    })

    try:
        await run_once(db)
        unchanged = await db.drafts.find_one({"_id": draft_id})
        assert unchanged["status"] == "scheduled"
    finally:
        await _cleanup(db, league_id, uids)


@pytest.mark.asyncio
async def test_autostart_skips_stale_more_than_30_days_late_drafts():
    # Iter 232N.45 — Late window bumped 24h → 30 days. A draft 2 days
    # in the past should now boot; only genuinely ancient junk stays
    # skipped.
    db = _db()
    league_id, uids, _ = await _seed_league_with_teams(db, 2)

    very_late = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()
    draft_id = ObjectId()
    await db.drafts.insert_one({
        "_id": draft_id, "league_id": league_id,
        "league_name": "Iter230ao", "name": "Iter230ao stale",
        "status": "scheduled", "scheduled_time": very_late,
        "draft_type": "snake", "snake_draft": True,
        "total_rounds": 2, "time_per_pick": 60,
        "current_pick": 1, "team_abbrs": [], "team_map": {},
        "picks": [], "chat_messages": [],
    })

    try:
        counts = await run_once(db)
        unchanged = await db.drafts.find_one({"_id": draft_id})
        assert unchanged["status"] == "scheduled"
        assert counts["started"] == 0
    finally:
        await _cleanup(db, league_id, uids)


@pytest.mark.asyncio
async def test_autostart_idempotent_on_already_active_drafts():
    db = _db()
    league_id, uids, _ = await _seed_league_with_teams(db, 2)

    past = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    draft_id = ObjectId()
    await db.drafts.insert_one({
        "_id": draft_id, "league_id": league_id,
        "league_name": "Iter230ao", "name": "Iter230ao active",
        "status": "active",
        "scheduled_time": past,
        "draft_type": "snake", "snake_draft": True,
        "total_rounds": 2, "time_per_pick": 60,
        "current_pick": 1,
        "team_abbrs": ["AA", "BB"], "team_map": {},
        "picks": [], "chat_messages": [],
        "started_at": past,
    })

    try:
        counts = await run_once(db)
        assert counts["started"] == 0
    finally:
        await _cleanup(db, league_id, uids)
