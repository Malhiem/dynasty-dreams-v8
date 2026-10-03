"""Iter 231q — Draft pick timer worker tests.

Verifies the per-pick timer rollover worker:

  • Active drafts whose `current_pick_started_at + pick_time_seconds`
    has elapsed get auto-picked (queue first → top-eligible fallback).
  • Drafts with `missed_pick_action == "defer-to-user"` are skipped
    (we wait for the owner's dialog choice).
  • Paused drafts (`timer_paused: True`) are skipped.
  • Drafts whose clock hasn't actually elapsed yet (3s grace) are
    untouched on this pass.
  • Drafts with no `current_pick_started_at` anchor are skipped.
  • A heartbeat row is written to `draft_pick_timer_runs/_id="latest"`.
"""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.draft_pick_timer_worker import run_once, draft_pick_timer_loop


def _db():
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[
        os.environ.get("DB_NAME", os.environ["DB_NAME"])
    ]


async def _seed_user(db, prefix: str):
    import uuid
    suffix = uuid.uuid4().hex[:10]
    uid = ObjectId()
    await db.users.insert_one({
        "_id": uid,
        "email": f"{prefix}_{suffix}@iter231q.test",
        "username": f"{prefix}_{suffix}",
        "name": f"iter231q {prefix}",
    })
    return str(uid)


async def _seed_league_with_teams(db, n: int = 3):
    uids = [await _seed_user(db, f"u{i}") for i in range(n)]
    league_id = ObjectId()
    await db.leagues.insert_one({
        "_id": league_id,
        "name": f"Iter231q League {league_id}",
        "commissioner_id": uids[0],
        "status": "active",
    })
    team_ids = []
    abbrs = []
    for i, uid in enumerate(uids):
        t_id = ObjectId()
        abbr = f"T{i+1}"
        await db.teams.insert_one({
            "_id": t_id,
            "name": f"Iter231q Team {i+1}",
            "league_id": str(league_id),
            "owner_id": uid,
            "roster": [],
            "draft_queue": [],
        })
        team_ids.append(str(t_id))
        abbrs.append(abbr)
    return str(league_id), uids, team_ids, abbrs


async def _seed_players(db, n: int = 10):
    pids = []
    for i in range(n):
        p_id = ObjectId()
        await db.players.insert_one({
            "_id": p_id,
            "nhl_id": f"iter231q-{p_id}",
            "name": f"Iter231q Player {i+1}",
            "position": "C",
            "team": "TOR",
            "team_name": "Toronto",
            "points": 100 - i,
            "goals": 30,
            "assists": 70,
            "games_played": 82,
            "player_type": "skater",
        })
        pids.append(str(p_id))
    return pids


async def _seed_draft(db, league_id, team_ids, abbrs, *, started_at, **overrides):
    draft_id = ObjectId()
    team_map = {abbr: {"id": tid, "name": f"Team {abbr}"} for abbr, tid in zip(abbrs, team_ids)}
    doc = {
        "_id": draft_id,
        "league_id": league_id,
        "league_name": "Iter231q",
        "name": "Iter231q draft",
        "status": "active",
        "draft_type": "snake",
        "snake_draft": True,
        "total_rounds": 2,
        "pick_time_seconds": 60,
        "current_pick": 1,
        "team_abbrs": abbrs,
        "team_map": team_map,
        "picks": [],
        "chat_messages": [],
        "current_pick_started_at": started_at,
        "started_at": started_at,
    }
    doc.update(overrides)
    await db.drafts.insert_one(doc)
    return str(draft_id)


async def _cleanup(db, league_id, uids, player_ids=None):
    await db.drafts.delete_many({"league_id": league_id})
    await db.teams.delete_many({"league_id": league_id})
    await db.leagues.delete_one({"_id": ObjectId(league_id)})
    await db.users.delete_many({"_id": {"$in": [ObjectId(u) for u in uids]}})
    if player_ids:
        await db.players.delete_many({"_id": {"$in": [ObjectId(p) for p in player_ids]}})


def _wire_deps(db):
    """The worker delegates to `draft_helpers.perform_one_auto_pick` which
    reads `_deps["db"]`. In live server those are wired at startup; in
    this isolated unit test we inject by hand."""
    from routes import draft_helpers
    draft_helpers._deps["db"] = db


@pytest.mark.asyncio
async def test_expired_clock_triggers_auto_pick():
    db = _db()
    _wire_deps(db)
    league_id, uids, team_ids, abbrs = await _seed_league_with_teams(db, 3)
    pids = await _seed_players(db, 5)

    # Clock started 5 minutes ago, pick_time is 60s → way past expired.
    past = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    draft_id = await _seed_draft(db, league_id, team_ids, abbrs, started_at=past)

    try:
        # Iter 231x — scope the worker to ONLY our seeded draft so we
        # never auto-pick into production drafts that happen to be active.
        counts = await run_once(db, draft_ids_filter=[draft_id])
        assert counts["expired"] >= 1
        assert counts["picked"] >= 1

        refreshed = await db.drafts.find_one({"_id": ObjectId(draft_id)})
        assert len(refreshed["picks"]) == 1
        assert refreshed["picks"][0]["auto_picked"] is True
        assert refreshed["picks"][0]["auto_pick_source"] == "timeout"
        assert refreshed["picks"][0]["overall"] == 1
        assert refreshed["current_pick"] == 2
    finally:
        await _cleanup(db, league_id, uids, pids)


@pytest.mark.asyncio
async def test_defer_to_user_drafts_are_skipped_when_owner_online():
    # Iter 232N.45 — `defer-to-user` no longer skips unconditionally.
    # It only skips when an owner or co-owner of the on-clock team is
    # actually in the draft's Socket.IO room. Offline-owner behaviour
    # is covered separately in test_iter232N45_draft_engine_hardening.
    from unittest.mock import patch

    db = _db()
    _wire_deps(db)
    league_id, uids, team_ids, abbrs = await _seed_league_with_teams(db, 3)
    pids = await _seed_players(db, 5)

    past = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    draft_id = await _seed_draft(
        db, league_id, team_ids, abbrs,
        started_at=past, missed_pick_action="defer-to-user",
    )

    try:
        with patch(
            "services.draft_pick_timer_worker._team_owners_present_in_draft_room",
            return_value=True,
        ):
            counts = await run_once(db, draft_ids_filter=[draft_id])
        assert counts["skipped"] >= 1
        refreshed = await db.drafts.find_one({"_id": ObjectId(draft_id)})
        assert refreshed["picks"] == []
        assert refreshed["current_pick"] == 1
    finally:
        await _cleanup(db, league_id, uids, pids)


@pytest.mark.asyncio
async def test_paused_drafts_are_skipped():
    db = _db()
    _wire_deps(db)
    league_id, uids, team_ids, abbrs = await _seed_league_with_teams(db, 3)
    pids = await _seed_players(db, 5)

    past = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    draft_id = await _seed_draft(
        db, league_id, team_ids, abbrs,
        started_at=past, timer_paused=True,
    )

    try:
        counts = await run_once(db, draft_ids_filter=[draft_id])
        assert counts["skipped"] >= 1
        refreshed = await db.drafts.find_one({"_id": ObjectId(draft_id)})
        assert refreshed["picks"] == []
    finally:
        await _cleanup(db, league_id, uids, pids)


@pytest.mark.asyncio
async def test_drafts_within_grace_window_are_not_picked():
    db = _db()
    _wire_deps(db)
    league_id, uids, team_ids, abbrs = await _seed_league_with_teams(db, 3)
    pids = await _seed_players(db, 5)

    # Clock started 10s ago, pick_time 60s → 50s remaining. Should NOT pick.
    just_now = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()
    draft_id = await _seed_draft(db, league_id, team_ids, abbrs, started_at=just_now)

    try:
        counts = await run_once(db, draft_ids_filter=[draft_id])
        # Other drafts in the DB may be expired — we only care that OURS is not.
        refreshed = await db.drafts.find_one({"_id": ObjectId(draft_id)})
        assert refreshed["picks"] == []
        assert refreshed["current_pick"] == 1
    finally:
        await _cleanup(db, league_id, uids, pids)


@pytest.mark.asyncio
async def test_drafts_with_no_started_anchor_are_skipped():
    db = _db()
    _wire_deps(db)
    league_id, uids, team_ids, abbrs = await _seed_league_with_teams(db, 3)
    pids = await _seed_players(db, 5)

    draft_id = await _seed_draft(db, league_id, team_ids, abbrs, started_at=None)

    try:
        counts = await run_once(db, draft_ids_filter=[draft_id])
        assert counts["skipped"] >= 1
        refreshed = await db.drafts.find_one({"_id": ObjectId(draft_id)})
        assert refreshed["picks"] == []
    finally:
        await _cleanup(db, league_id, uids, pids)


@pytest.mark.asyncio
async def test_queue_player_picked_before_best_eligible():
    db = _db()
    _wire_deps(db)
    league_id, uids, team_ids, abbrs = await _seed_league_with_teams(db, 3)
    pids = await _seed_players(db, 5)

    # Pre-seed the on-clock team's draft_queue with the LAST player (lowest
    # points). If the worker correctly honours the queue, that player gets
    # picked instead of the top-eligible #1.
    queued_pid = pids[-1]  # lowest points
    on_clock_team_id = team_ids[0]
    await db.teams.update_one(
        {"_id": ObjectId(on_clock_team_id)},
        {"$set": {"draft_queue": [queued_pid]}},
    )

    past = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    draft_id = await _seed_draft(db, league_id, team_ids, abbrs, started_at=past)

    try:
        await run_once(db, draft_ids_filter=[draft_id])
        refreshed = await db.drafts.find_one({"_id": ObjectId(draft_id)})
        assert len(refreshed["picks"]) == 1
        assert refreshed["picks"][0]["player_id"] == queued_pid
        assert refreshed["picks"][0]["auto_pick_via"] == "queue"
    finally:
        await _cleanup(db, league_id, uids, pids)


@pytest.mark.asyncio
async def test_inactive_drafts_are_ignored():
    db = _db()
    _wire_deps(db)
    league_id, uids, team_ids, abbrs = await _seed_league_with_teams(db, 3)
    pids = await _seed_players(db, 5)

    past = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    # Status: scheduled (not active) — worker should NOT touch it.
    draft_id = await _seed_draft(
        db, league_id, team_ids, abbrs,
        started_at=past, status="scheduled",
    )

    try:
        counts = await run_once(db, draft_ids_filter=[draft_id])
        # `checked` excludes non-active drafts (worker query filters them out).
        refreshed = await db.drafts.find_one({"_id": ObjectId(draft_id)})
        assert refreshed["picks"] == []
        assert refreshed["status"] == "scheduled"
    finally:
        await _cleanup(db, league_id, uids, pids)


@pytest.mark.asyncio
async def test_run_once_returns_count_shape():
    """Smoke: run_once returns the expected counters dict shape even when
    there's nothing to do (empty drafts collection scan).

    Iter 231x — pass an empty filter list so the worker scans nothing
    (we just want to verify the return shape). This is the test that
    formerly scanned production drafts and caused iter231q pollution."""
    db = _db()
    _wire_deps(db)
    counts = await run_once(db, draft_ids_filter=[])
    for k in ("checked", "expired", "picked", "skipped", "errors"):
        assert k in counts
        assert isinstance(counts[k], int)
    # With an empty filter, nothing should be scanned.
    assert counts["checked"] == 0


@pytest.mark.asyncio
async def test_loop_writes_heartbeat_and_can_be_cancelled():
    """The long-running loop writes a heartbeat to draft_pick_timer_runs
    on every pass. Start it with a 1s interval, let it tick once, then
    cancel."""
    db = _db()
    _wire_deps(db)

    # Clear any prior heartbeat so we can prove this run wrote one.
    await db.draft_pick_timer_runs.delete_one({"_id": "latest"})

    task = asyncio.create_task(draft_pick_timer_loop(db, interval_seconds=1))
    try:
        # Give the worker ~1.5s to complete its first pass + sleep + tick.
        await asyncio.sleep(1.5)
        hb = await db.draft_pick_timer_runs.find_one({"_id": "latest"})
        assert hb is not None
        assert "started_at" in hb
        assert "finished_at" in hb
        assert "counts" in hb
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
