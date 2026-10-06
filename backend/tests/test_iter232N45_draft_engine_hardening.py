"""Iter 232N.45 — Draft engine hardening tests.

Covers two fixes:

  1. `draft_autostart_worker.MAX_LATE_WINDOW` bumped 24h → 30 days so a
     scheduled draft the commissioner discovered 10 days late (TFHL
     Inaugural) actually boots instead of getting silently skipped.

  2. `draft_pick_timer_worker` now handles `missed_pick_action ==
     "defer-to-user"` by checking whether any owner of the on-clock
     team is present in the draft's Socket.IO room. If nobody is
     online AND the clock has expired, we auto-pick with
     `source="defer_offline_timeout"` so the draft doesn't stall
     forever. If any owner IS present, we still defer to them.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, AsyncMock

import pytest
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _db():
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[
        os.environ.get("DB_NAME", os.environ["DB_NAME"])
    ]


async def _seed_user(db, prefix: str) -> str:
    uid = ObjectId()
    await db.users.insert_one({
        "_id": uid,
        "email": f"{prefix}_{str(uid)[:6]}@iter232n45.test",
        "username": f"{prefix}_{str(uid)[:6]}",
        "name": f"iter232n45 {prefix}",
    })
    return str(uid)


async def _seed_league_and_teams(db, n_teams: int = 2):
    uids = [await _seed_user(db, f"u{i}") for i in range(n_teams)]
    league_id = ObjectId()
    await db.leagues.insert_one({
        "_id": league_id,
        "name": f"Iter232N45 league {league_id}",
        "commissioner_id": uids[0],
        "status": "active",
        "current_season_status": "regular",
    })
    team_ids = []
    for i, uid in enumerate(uids):
        tid = ObjectId()
        await db.teams.insert_one({
            "_id": tid,
            "name": f"Team {i + 1}",
            "league_id": str(league_id),
            "owner_id": uid,
            "co_owner_ids": [],
            "roster": [],
        })
        team_ids.append(str(tid))
    return str(league_id), uids, team_ids


async def _cleanup(db, league_id, uids):
    await db.drafts.delete_many({"league_id": league_id})
    await db.teams.delete_many({"league_id": league_id})
    await db.leagues.delete_one({"_id": ObjectId(league_id)})
    await db.users.delete_many({"_id": {"$in": [ObjectId(u) for u in uids]}})
    await db.notifications.delete_many({"user_id": {"$in": uids}})
    await db.draft_picks.delete_many({"league_id": league_id})


# ─── Fix 1 ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_autostart_boots_draft_up_to_30_days_late():
    """Regression guard against reverting MAX_LATE_WINDOW back to 24h.
    TFHL Inaugural was ~10 days past its scheduled_time when the
    commissioner noticed it hadn't started."""
    from services.draft_autostart_worker import run_once
    from routes import drafts as drafts_routes

    db = _db()
    drafts_routes._deps["db"] = db

    league_id, uids, _ = await _seed_league_and_teams(db, 2)

    ten_days_late = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
    draft_id = ObjectId()
    await db.drafts.insert_one({
        "_id": draft_id, "league_id": league_id,
        "league_name": "Iter232N45", "name": "Iter232N45 10-day-late",
        "status": "scheduled", "scheduled_time": ten_days_late,
        "draft_type": "snake", "snake_draft": True,
        "total_rounds": 2, "time_per_pick": 60,
        "current_pick": 1, "team_abbrs": [], "team_map": {},
        "picks": [], "chat_messages": [],
    })

    try:
        counts = await run_once(db)
        assert counts["started"] >= 1
        refreshed = await db.drafts.find_one({"_id": draft_id})
        assert refreshed["status"] == "active"
        assert refreshed.get("started_at")
    finally:
        await _cleanup(db, league_id, uids)


# ─── Fix 2 ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_defer_to_user_auto_picks_when_all_owners_offline():
    from services.draft_pick_timer_worker import run_once as timer_run_once
    from routes import drafts as drafts_routes

    db = _db()
    drafts_routes._deps["db"] = db

    league_id, uids, team_ids = await _seed_league_and_teams(db, 2)

    # Clock elapsed 10 minutes ago; 60s per-pick + 3s grace → deadline
    # long since expired.
    started = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    draft_id = ObjectId()
    await db.drafts.insert_one({
        "_id": draft_id, "league_id": league_id,
        "league_name": "Iter232N45", "name": "Iter232N45 defer offline",
        "status": "active", "draft_type": "snake", "snake_draft": True,
        "total_rounds": 2, "time_per_pick": 60, "current_pick": 1,
        "team_abbrs": ["AAA", "BBB"],
        "team_map": {
            "AAA": {"id": team_ids[0], "name": "T1", "owner_id": uids[0]},
            "BBB": {"id": team_ids[1], "name": "T2", "owner_id": uids[1]},
        },
        "current_pick_started_at": started,
        "missed_pick_action": "defer-to-user",
        "picks": [], "chat_messages": [],
    })

    # Force the presence probe to say "nobody is online".
    with patch(
        "services.draft_pick_timer_worker._team_owners_present_in_draft_room",
        return_value=False,
    ), patch(
        "routes.draft_helpers.perform_one_auto_pick",
        new_callable=AsyncMock,
    ) as fake_pick:
        fake_pick.return_value = {"auto_pick_via": "top_ranked"}
        try:
            counts = await timer_run_once(db, draft_ids_filter=[str(draft_id)])
            assert counts["picked"] == 1, counts
            fake_pick.assert_awaited_once()
            # Confirm the source signal is our new defer_offline_timeout
            call_kwargs = fake_pick.await_args.kwargs
            assert call_kwargs.get("source") == "defer_offline_timeout", call_kwargs
        finally:
            await _cleanup(db, league_id, uids)


@pytest.mark.asyncio
async def test_defer_to_user_still_skips_when_owner_is_online():
    from services.draft_pick_timer_worker import run_once as timer_run_once
    from routes import drafts as drafts_routes

    db = _db()
    drafts_routes._deps["db"] = db

    league_id, uids, team_ids = await _seed_league_and_teams(db, 2)

    started = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    draft_id = ObjectId()
    await db.drafts.insert_one({
        "_id": draft_id, "league_id": league_id,
        "league_name": "Iter232N45", "name": "Iter232N45 defer online",
        "status": "active", "draft_type": "snake", "snake_draft": True,
        "total_rounds": 2, "time_per_pick": 60, "current_pick": 1,
        "team_abbrs": ["AAA", "BBB"],
        "team_map": {
            "AAA": {"id": team_ids[0], "name": "T1", "owner_id": uids[0]},
            "BBB": {"id": team_ids[1], "name": "T2", "owner_id": uids[1]},
        },
        "current_pick_started_at": started,
        "missed_pick_action": "defer-to-user",
        "picks": [], "chat_messages": [],
    })

    with patch(
        "services.draft_pick_timer_worker._team_owners_present_in_draft_room",
        return_value=True,
    ), patch(
        "routes.draft_helpers.perform_one_auto_pick",
        new_callable=AsyncMock,
    ) as fake_pick:
        try:
            counts = await timer_run_once(db, draft_ids_filter=[str(draft_id)])
            assert counts["picked"] == 0, counts
            assert counts["skipped"] >= 1, counts
            fake_pick.assert_not_awaited()
        finally:
            await _cleanup(db, league_id, uids)


@pytest.mark.asyncio
async def test_team_owners_present_reads_connected_users():
    """Direct unit test for the presence helper — verifies it reads
    `server.connected_users` and filters by both `room_id` and
    `user_id` correctly."""
    from services.draft_pick_timer_worker import _team_owners_present_in_draft_room

    import server as srv
    prior = dict(srv.connected_users)
    try:
        srv.connected_users.clear()
        # Wrong room, right user
        srv.connected_users["sid-wrong-room"] = {
            "room_id": "draft_OTHER", "user_id": "user-a",
        }
        assert not _team_owners_present_in_draft_room(
            "draft_X", {"owner_id": "user-a"}
        )
        # Right room, wrong user
        srv.connected_users["sid-wrong-user"] = {
            "room_id": "draft_X", "user_id": "user-b",
        }
        assert not _team_owners_present_in_draft_room(
            "X", {"owner_id": "user-a"}
        )
        # Right room, right user (owner)
        srv.connected_users["sid-owner"] = {
            "room_id": "draft_X", "user_id": "user-a",
        }
        assert _team_owners_present_in_draft_room(
            "X", {"owner_id": "user-a"}
        )
        # Right room, co-owner also counts
        srv.connected_users.clear()
        srv.connected_users["sid-co"] = {
            "room_id": "draft_X", "user_id": "co-owner-c",
        }
        assert _team_owners_present_in_draft_room(
            "X", {"owner_id": "user-a", "co_owner_ids": ["co-owner-c"]}
        )
        # No owners on the team → never present.
        assert not _team_owners_present_in_draft_room(
            "X", {"owner_id": None, "co_owner_ids": []}
        )
        # None team → False.
        assert not _team_owners_present_in_draft_room("X", None)
    finally:
        srv.connected_users.clear()
        srv.connected_users.update(prior)
