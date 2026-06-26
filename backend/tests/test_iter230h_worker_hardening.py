"""Iter 230h+ — Notification worker hardening tests.

Covers three new behaviors layered on top of iter 230c:
  1. Archived + TEST_*-prefixed leagues are skipped (no fanout).
  2. Lineup-lock reminders include a `reason` payload for the
     "Why am I being notified?" UI.
  3. Duplicate co_owner_ids (owner also listed as co-owner) don't
     receive the same lineup_problem notification twice.
"""
import os
import sys
from datetime import datetime, timezone, timedelta

import pytest
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.notification_worker import run_once


def _db_sync():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    return client[os.environ.get("DB_NAME", "test_database")]


async def _make_recorder():
    calls: list = []

    async def record(user_id, event_id, title, body, league_id=None, link=None, reason=None):
        calls.append({
            "user_id": user_id, "event_id": event_id, "league_id": league_id,
            "reason": reason,
        })
    return record, calls


@pytest.mark.asyncio
async def test_worker_skips_archived_and_test_leagues():
    """A league with `archived=True` OR `name LIKE TEST_%` must NOT
    receive lineup-lock reminders even when the timing falls inside the
    notification window. Mirrors iter 230g WAG filter logic."""
    db = _db_sync()
    lock = (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat()

    # Build 3 leagues — archived, TEST_*, real — each with an owned team.
    real_user = await db.users.find_one({})
    assert real_user
    owner_id = str(real_user["_id"])

    archived_league = await db.leagues.insert_one({
        "name": "Iter230h_archived_league", "archived": True,
        "matchup_lock_at": lock, "status": "archived",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    test_league = await db.leagues.insert_one({
        "name": "TEST_iter230h_skip_me",
        "matchup_lock_at": lock, "status": "active",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    real_league = await db.leagues.insert_one({
        "name": "Iter230h_real_keep_me",
        "matchup_lock_at": lock, "status": "active",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    teams_inserted = []
    for lg_id in [archived_league.inserted_id, test_league.inserted_id, real_league.inserted_id]:
        r = await db.teams.insert_one({
            "name": "Iter230h_team", "league_id": str(lg_id),
            "owner_id": owner_id, "roster": [],
        })
        teams_inserted.append(r.inserted_id)
    # Wipe any prior dedup state for these leagues.
    for lg_id in [archived_league.inserted_id, test_league.inserted_id, real_league.inserted_id]:
        await db.notification_worker_state.delete_many({"league_id": str(lg_id)})

    try:
        record, calls = await _make_recorder()
        await run_once(db, record)
        # The real league fires; archived + TEST_* do NOT.
        league_ids_fired = {c["league_id"] for c in calls if c["event_id"] == "lineup_lock_reminder"}
        assert str(real_league.inserted_id) in league_ids_fired
        assert str(archived_league.inserted_id) not in league_ids_fired
        assert str(test_league.inserted_id) not in league_ids_fired
    finally:
        await db.teams.delete_many({"_id": {"$in": teams_inserted}})
        await db.leagues.delete_many({"_id": {"$in": [
            archived_league.inserted_id, test_league.inserted_id, real_league.inserted_id,
        ]}})
        for lg_id in [archived_league.inserted_id, test_league.inserted_id, real_league.inserted_id]:
            await db.notification_worker_state.delete_many({"league_id": str(lg_id)})


@pytest.mark.asyncio
async def test_worker_emits_reason_payload_for_lineup_lock():
    """Every lineup-lock reminder must carry a `reason` dict with the
    league + lock target so the 'Why am I being notified?' popover can
    explain the alert without guessing."""
    db = _db_sync()
    real_user = await db.users.find_one({})
    assert real_user
    owner_id = str(real_user["_id"])

    lock = (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat()
    league = await db.leagues.insert_one({
        "name": "Iter230h_reason_league",
        "matchup_lock_at": lock, "status": "active",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    team = await db.teams.insert_one({
        "name": "Iter230h_reason_team",
        "league_id": str(league.inserted_id),
        "owner_id": owner_id, "roster": [],
    })
    await db.notification_worker_state.delete_many({"league_id": str(league.inserted_id)})

    try:
        record, calls = await _make_recorder()
        await run_once(db, record)
        lock_calls = [
            c for c in calls
            if c["event_id"] == "lineup_lock_reminder"
            and c["league_id"] == str(league.inserted_id)
        ]
        assert lock_calls, f"expected a lineup_lock fire, got {calls}"
        reason = lock_calls[0]["reason"]
        assert isinstance(reason, dict)
        assert reason["kind"] == "lineup_lock_reminder"
        assert reason["league_id"] == str(league.inserted_id)
        assert reason["lock_at"] == lock
        assert reason["source"] == "notification_worker"
        assert "minutes_until_lock" in reason
    finally:
        await db.teams.delete_one({"_id": team.inserted_id})
        await db.leagues.delete_one({"_id": league.inserted_id})
        await db.notification_worker_state.delete_many({"league_id": str(league.inserted_id)})


@pytest.mark.asyncio
async def test_worker_dedupes_owner_in_co_owner_ids_for_lineup_problem():
    """If a team's `owner_id` is duplicated inside `co_owner_ids`, the
    same user must NOT receive two lineup_problem notifications for the
    same lock target."""
    db = _db_sync()
    real_user = await db.users.find_one({})
    assert real_user
    owner_id = str(real_user["_id"])

    # Pick a real player_id we won't add to the roster so the lineup
    # references a player who isn't on the team → lineup_problem fires.
    real_player = await db.players.find_one({})
    assert real_player
    ghost_pid = str(real_player["_id"])

    lock = (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat()
    league = await db.leagues.insert_one({
        "name": "Iter230h_dupe_owners_league",
        "matchup_lock_at": lock, "status": "active",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    team = await db.teams.insert_one({
        "name": "Iter230h_dupe_owners_team",
        "league_id": str(league.inserted_id),
        "owner_id": owner_id,
        "co_owner_ids": [owner_id, owner_id],  # duplicate of owner_id.
        "roster": [],  # ghost_pid intentionally NOT on roster.
        "lineup": {ghost_pid: {"section": "active", "slot": "C"}},
    })
    await db.notification_worker_state.delete_many({"league_id": str(league.inserted_id)})

    try:
        record, calls = await _make_recorder()
        await run_once(db, record)
        problem_calls = [
            c for c in calls
            if c["event_id"] == "lineup_problem"
            and c["league_id"] == str(league.inserted_id)
            and c["user_id"] == owner_id
        ]
        # Exactly one — no duplicates from the co_owner_ids fan-out.
        assert len(problem_calls) == 1, problem_calls
    finally:
        await db.teams.delete_one({"_id": team.inserted_id})
        await db.leagues.delete_one({"_id": league.inserted_id})
        await db.notification_worker_state.delete_many({"league_id": str(league.inserted_id)})
