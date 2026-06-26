"""Iter 230c — Notification worker unit tests.

Drives `run_once` directly against the live DB so we don't have to wait
30 minutes between asserts. Each test crafts the trigger condition
(matchup_lock_at, draft scheduled_time, etc.), runs the worker, then
verifies the right notification family fired exactly once.
"""
import os
import sys
import asyncio
from datetime import datetime, timezone, timedelta

import pytest
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
from httpx import AsyncClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.notification_worker import run_once


def _backend_url():
    env_path = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", ".env")
    with open(env_path) as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip()
    raise RuntimeError("REACT_APP_BACKEND_URL not found")


BASE = _backend_url()


def _db_sync():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    return client[os.environ.get("DB_NAME", "test_database")]


async def _login(client, email, password):
    r = await client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


async def _make_recorder():
    """Returns (record_fn, calls) so each invocation appends to `calls`."""
    calls: list = []

    async def record(user_id, event_id, title, body, league_id=None, link=None):
        calls.append({
            "user_id": user_id, "event_id": event_id, "title": title,
            "body": body, "league_id": league_id, "link": link,
        })
    return record, calls


@pytest.mark.asyncio
async def test_worker_fires_lineup_lock_reminder_within_window():
    db = _db_sync()
    record, calls = await _make_recorder()

    # Find any league with at least one team — set its lock 30 min from now.
    league = await db.leagues.find_one({})
    assert league
    team = await db.teams.find_one({"league_id": str(league["_id"])})
    assert team
    target = datetime.now(timezone.utc) + timedelta(minutes=30)
    original = league.get("matchup_lock_at")
    await db.leagues.update_one(
        {"_id": league["_id"]},
        {"$set": {"matchup_lock_at": target.isoformat()}},
    )
    # Wipe the dedup state so this fresh target_iso fires.
    await db.notification_worker_state.delete_many({"league_id": str(league["_id"])})

    try:
        counts = await run_once(db, record)
        assert counts["lineup_lock_reminders"] >= 1, calls
        lock_calls = [c for c in calls if c["event_id"] == "lineup_lock_reminder"]
        assert lock_calls
        assert all(c["league_id"] == str(league["_id"]) for c in lock_calls)

        # Dedup: second run for the same target shouldn't refire.
        record2, calls2 = await _make_recorder()
        counts2 = await run_once(db, record2)
        assert counts2["lineup_lock_reminders"] == 0
    finally:
        # Restore original league state + clear worker dedup.
        if original is None:
            await db.leagues.update_one(
                {"_id": league["_id"]},
                {"$unset": {"matchup_lock_at": ""}},
            )
        else:
            await db.leagues.update_one(
                {"_id": league["_id"]},
                {"$set": {"matchup_lock_at": original}},
            )
        await db.notification_worker_state.delete_many({"league_id": str(league["_id"])})


@pytest.mark.asyncio
async def test_worker_skips_lock_outside_window():
    db = _db_sync()
    record, calls = await _make_recorder()

    league = await db.leagues.find_one({})
    assert league
    # 8h away — outside LOCK_WINDOW_MAX (4h).
    target = datetime.now(timezone.utc) + timedelta(hours=8)
    original = league.get("matchup_lock_at")
    await db.leagues.update_one(
        {"_id": league["_id"]},
        {"$set": {"matchup_lock_at": target.isoformat()}},
    )
    await db.notification_worker_state.delete_many({"league_id": str(league["_id"])})

    try:
        counts = await run_once(db, record)
        lock_calls = [c for c in calls if c["event_id"] == "lineup_lock_reminder"
                      and c["league_id"] == str(league["_id"])]
        assert not lock_calls
        assert counts["lineup_lock_reminders"] == 0
    finally:
        if original is None:
            await db.leagues.update_one({"_id": league["_id"]}, {"$unset": {"matchup_lock_at": ""}})
        else:
            await db.leagues.update_one({"_id": league["_id"]}, {"$set": {"matchup_lock_at": original}})
        await db.notification_worker_state.delete_many({"league_id": str(league["_id"])})


@pytest.mark.asyncio
async def test_worker_fires_important_reminder_on_24h_draft():
    db = _db_sync()
    record, calls = await _make_recorder()

    # Find any league with at least one team.
    league = await db.leagues.find_one({})
    assert league
    league_id = str(league["_id"])
    team = await db.teams.find_one({"league_id": league_id})
    assert team

    # Insert a temporary draft scheduled 12h from now.
    sched = datetime.now(timezone.utc) + timedelta(hours=12)
    res = await db.drafts.insert_one({
        "league_id": league_id,
        "name": "Iter 230c TEST Draft",
        "status": "scheduled",
        "scheduled_time": sched.isoformat(),
        "team_abbrs": ["AA"],
        "team_map": {},
        "total_rounds": 1,
        "current_pick": 1,
        "snake_draft": False,
        "picks": [],
        "chat_messages": [],
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    await db.notification_worker_state.delete_many({"league_id": league_id})

    try:
        counts = await run_once(db, record)
        important_calls = [c for c in calls if c["event_id"] == "reminder_important"
                           and c["league_id"] == league_id
                           and "starts in" in (c["body"] or "")]
        assert important_calls, f"expected at least one draft reminder, got calls={calls}"
        assert counts["reminders_important"] >= 1
    finally:
        await db.drafts.delete_one({"_id": res.inserted_id})
        await db.notification_worker_state.delete_many({"league_id": league_id})
