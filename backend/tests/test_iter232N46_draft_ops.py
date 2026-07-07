"""Iter 232N.46 — Draft Ops endpoint tests.

Covers `GET /api/leagues/{league_id}/draft-ops`:

  • Non-commissioner (no admin role) is rejected 403.
  • Commissioner gets a payload with worker heartbeats + drafts array.
  • Payload includes on-clock team + owner presence (online/offline).
  • Archived drafts are excluded from the drafts list.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone, timedelta

import pytest
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _db():
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[
        os.environ.get("DB_NAME", "test_database")
    ]


def _wire_deps(db):
    from routes import draft_ops as draft_ops_module
    draft_ops_module._deps["db"] = db

    async def _fake_get_user(_request):
        return draft_ops_module._deps.get("_test_user")
    draft_ops_module._deps["get_current_user"] = _fake_get_user


async def _seed_user(db, prefix: str, role: str = "user") -> str:
    uid = ObjectId()
    await db.users.insert_one({
        "_id": uid,
        "email": f"{prefix}_{str(uid)[:6]}@iter232n46.test",
        "name": f"iter232n46 {prefix}",
        "role": role,
    })
    return str(uid)


async def _seed_league_and_teams(db, n_teams: int = 2, commissioner_uid: str | None = None):
    uids = [await _seed_user(db, f"u{i}") for i in range(n_teams)]
    if not commissioner_uid:
        commissioner_uid = uids[0]
    league_id = ObjectId()
    await db.leagues.insert_one({
        "_id": league_id,
        "name": f"Iter232N46 league {league_id}",
        "commissioner_id": commissioner_uid,
        "status": "active",
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
        })
        team_ids.append(str(tid))
    return str(league_id), uids, team_ids


async def _cleanup(db, league_id, uids):
    await db.drafts.delete_many({"league_id": league_id})
    await db.teams.delete_many({"league_id": league_id})
    await db.leagues.delete_one({"_id": ObjectId(league_id)})
    await db.users.delete_many({"_id": {"$in": [ObjectId(u) for u in uids]}})


@pytest.mark.asyncio
async def test_draft_ops_rejects_non_admin():
    from routes.draft_ops import get_draft_ops
    from fastapi import HTTPException

    db = _db()
    _wire_deps(db)
    league_id, uids, _ = await _seed_league_and_teams(db, 2)
    outsider_uid = await _seed_user(db, "outsider")

    from routes import draft_ops as draft_ops_module
    draft_ops_module._deps["_test_user"] = {"_id": outsider_uid, "role": "user"}

    try:
        with pytest.raises(HTTPException) as exc:
            await get_draft_ops(league_id, None)
        assert exc.value.status_code == 403
    finally:
        await _cleanup(db, league_id, uids + [outsider_uid])


@pytest.mark.asyncio
async def test_draft_ops_returns_workers_and_drafts_for_commissioner():
    from routes.draft_ops import get_draft_ops

    db = _db()
    _wire_deps(db)
    league_id, uids, team_ids = await _seed_league_and_teams(db, 2)

    # Seed worker heartbeats
    now = datetime.now(timezone.utc)
    await db.draft_autostart_runs.update_one(
        {"_id": "latest"},
        {"$set": {
            "_id": "latest",
            "finished_at": now.isoformat(),
            "started_at": (now - timedelta(seconds=1)).isoformat(),
            "counts": {"checked": 5, "started": 1, "skipped": 4},
            "error": None,
        }},
        upsert=True,
    )
    await db.draft_pick_timer_runs.update_one(
        {"_id": "latest"},
        {"$set": {
            "_id": "latest",
            "finished_at": now.isoformat(),
            "started_at": (now - timedelta(seconds=1)).isoformat(),
            "counts": {"checked": 3, "picked": 1, "skipped": 2, "errors": 0},
            "error": None,
        }},
        upsert=True,
    )

    # Seed an active draft
    active_draft_id = ObjectId()
    await db.drafts.insert_one({
        "_id": active_draft_id, "league_id": league_id,
        "name": "Iter232N46 active", "status": "active",
        "total_rounds": 2, "time_per_pick": 60, "current_pick": 1,
        "team_abbrs": ["AAA", "BBB"], "snake_draft": True,
        "team_map": {
            "AAA": {"id": team_ids[0], "name": "T1", "owner_id": uids[0]},
            "BBB": {"id": team_ids[1], "name": "T2", "owner_id": uids[1]},
        },
        "current_pick_started_at": (now - timedelta(seconds=30)).isoformat(),
        "missed_pick_action": "auto-select", "picks": [],
    })
    # Seed an archived draft — must NOT appear.
    archived_id = ObjectId()
    await db.drafts.insert_one({
        "_id": archived_id, "league_id": league_id,
        "name": "Iter232N46 archived", "status": "archived",
        "total_rounds": 2, "team_abbrs": [], "picks": [],
    })

    from routes import draft_ops as draft_ops_module
    draft_ops_module._deps["_test_user"] = {"_id": uids[0], "role": "user"}

    try:
        result = await get_draft_ops(league_id, None)
        assert result["league_id"] == league_id
        assert "checked_at" in result
        assert result["workers"]["autostart"]["counts"] == {"checked": 5, "started": 1, "skipped": 4}
        assert result["workers"]["pick_timer"]["counts"]["picked"] == 1
        assert result["workers"]["autostart"]["healthy"] is True
        assert result["workers"]["pick_timer"]["healthy"] is True

        ids = {d["id"] for d in result["drafts"]}
        assert str(active_draft_id) in ids
        assert str(archived_id) not in ids

        active_row = next(d for d in result["drafts"] if d["id"] == str(active_draft_id))
        assert active_row["status"] == "active"
        assert active_row["team_count"] == 2
        assert active_row["total_rounds"] == 2
        assert active_row["total_picks"] == 4  # rounds * teams
        assert active_row["on_clock"] is not None
        assert active_row["on_clock"]["team_name"] == "T1"
        assert active_row["on_clock"]["abbr"] == "AAA"
        # Owner defaults to offline (nobody in Socket.IO room).
        assert active_row["on_clock"]["owners"][0]["online"] is False
        assert active_row["on_clock"]["owners"][0]["id"] == uids[0]
        # Seconds remaining: 60s clock - 30s elapsed ≈ 30s.
        assert 25 <= active_row["seconds_remaining"] <= 60
    finally:
        await _cleanup(db, league_id, uids)


@pytest.mark.asyncio
async def test_draft_ops_platform_admin_can_read_any_league():
    from routes.draft_ops import get_draft_ops

    db = _db()
    _wire_deps(db)
    league_id, uids, _ = await _seed_league_and_teams(db, 2)
    admin_uid = await _seed_user(db, "platform_admin", role="admin")

    from routes import draft_ops as draft_ops_module
    draft_ops_module._deps["_test_user"] = {"_id": admin_uid, "role": "admin"}

    try:
        result = await get_draft_ops(league_id, None)
        assert result["league_id"] == league_id
    finally:
        await _cleanup(db, league_id, uids + [admin_uid])
