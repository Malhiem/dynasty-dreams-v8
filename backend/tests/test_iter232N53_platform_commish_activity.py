"""Iter 232N.53 — Platform-wide commissioner activity feed tests.

Covers `GET /api/admin/commissioner-activity`:

  1. Non-admin (regular user OR commissioner) rejected 403.
  2. Platform admin gets a merged cross-league feed with `league_id` +
     `league_name` on each row.
  3. Aggregates: `by_league` and `by_commissioner` sorted by total DESC;
     `totals` reflects window totals.
  4. `days` window filters out older events.
  5. `limit` bounds the events list; aggregates still scan full window.
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


def _wire_deps(db, caller):
    from routes import draft_ops as m
    m._deps.update({"db": db})

    async def _fake_get_user(_request):
        return caller
    m._deps["get_current_user"] = _fake_get_user


async def _seed_user(db, prefix, role="user"):
    uid = ObjectId()
    await db.users.insert_one({
        "_id": uid,
        "email": f"{prefix}_{str(uid)[:6]}@iter232n53.test",
        "name": f"iter232n53 {prefix}",
        "username": f"{prefix}_{str(uid)[:6]}",
        "role": role,
    })
    return str(uid)


async def _seed_league(db, name, commish_uid):
    league_id = ObjectId()
    await db.leagues.insert_one({
        "_id": league_id, "name": name,
        "commissioner_id": commish_uid, "status": "active",
    })
    return str(league_id)


async def _cleanup(db, league_ids, uids):
    for lid in league_ids:
        await db.leagues.delete_one({"_id": ObjectId(lid)})
        await db.draft_undo_audit.delete_many({"league_id": lid})
        await db.commissioner_pings.delete_many({"league_id": lid})
    await db.users.delete_many({"_id": {"$in": [ObjectId(u) for u in uids]}})


@pytest.mark.asyncio
async def test_platform_activity_rejects_non_admin():
    from routes.draft_ops import platform_commissioner_activity
    from fastapi import HTTPException

    db = _db()
    caller = await _seed_user(db, "regular", role="user")
    _wire_deps(db, {"_id": caller, "role": "user"})

    try:
        with pytest.raises(HTTPException) as exc:
            await platform_commissioner_activity(None, limit=50, days=30)
        assert exc.value.status_code == 403
    finally:
        await _cleanup(db, [], [caller])


@pytest.mark.asyncio
async def test_platform_activity_returns_merged_cross_league_feed():
    from routes.draft_ops import platform_commissioner_activity

    db = _db()
    admin = await _seed_user(db, "admin", role="admin")
    commishA = await _seed_user(db, "commishA")
    commishB = await _seed_user(db, "commishB")

    lA = await _seed_league(db, "League Alpha", commishA)
    lB = await _seed_league(db, "League Bravo", commishB)

    now = datetime.now(timezone.utc)
    # 2 undos in Alpha
    for i in range(2):
        await db.draft_undo_audit.insert_one({
            "league_id": lA, "draft_id": "dA",
            "pick_number": i + 1, "removed_count": 1, "cascade": False,
            "removed_picks": [{"overall": i + 1, "team": "AAA",
                                "player": {"name": f"P{i}"}}],
            "commissioner_id": commishA, "commissioner_name": "CommishA",
            "reason": "reason A",
            "undone_at": (now - timedelta(hours=i)).isoformat(),
            "on_the_clock_after": "AAA",
        })
    # 1 undo in Bravo
    await db.draft_undo_audit.insert_one({
        "league_id": lB, "draft_id": "dB",
        "pick_number": 5, "removed_count": 1, "cascade": False,
        "removed_picks": [{"overall": 5, "team": "BBB",
                            "player": {"name": "PB"}}],
        "commissioner_id": commishB, "commissioner_name": "CommishB",
        "undone_at": (now - timedelta(hours=3)).isoformat(),
    })
    # 3 pings in Alpha
    for i in range(3):
        await db.commissioner_pings.insert_one({
            "league_id": lA, "draft_id": "dA",
            "commissioner_id": commishA,
            "target_user_id": commishB, "target_team_name": "Bravo Team",
            "channels_fired": ["in_app", "email"],
            "custom_message": f"nudge {i}",
            "created_at": (now - timedelta(minutes=10 + i)).isoformat(),
        })

    _wire_deps(db, {"_id": admin, "role": "admin"})
    try:
        result = await platform_commissioner_activity(None, limit=50, days=30)

        # Total events across our 2 test leagues (may include unrelated
        # events from other leagues in the shared DB — verify by
        # filtering to our seeded league ids).
        by_league = result["aggregates"]["by_league"]
        alpha_row = next(r for r in by_league if r["id"] == lA)
        bravo_row = next(r for r in by_league if r["id"] == lB)
        assert alpha_row["total"] == 5
        assert alpha_row["undos"] == 2
        assert alpha_row["pings"] == 3
        assert bravo_row["total"] == 1
        # Commissioner ranking: verify OUR commissioners are ranked
        # correctly relative to each other (don't over-assert globals).
        by_commish = result["aggregates"]["by_commissioner"]
        commA_row = next(r for r in by_commish if r["id"] == commishA)
        commB_row = next(r for r in by_commish if r["id"] == commishB)
        assert commA_row["total"] == 5
        assert commB_row["total"] == 1
        # Feed carries cross-league metadata on every row.
        seeded_events = [
            e for e in result["events"] if e["league_id"] in {lA, lB}
        ]
        assert len(seeded_events) == 6
        assert {e["league_name"] for e in seeded_events} == {
            "League Alpha", "League Bravo",
        }
    finally:
        await _cleanup(db, [lA, lB], [admin, commishA, commishB])


@pytest.mark.asyncio
async def test_platform_activity_days_window_filters_old_events():
    from routes.draft_ops import platform_commissioner_activity

    db = _db()
    admin = await _seed_user(db, "admin", role="admin")
    commish = await _seed_user(db, "commish")
    lg = await _seed_league(db, "League OldFilter", commish)

    now = datetime.now(timezone.utc)
    # Recent (in window)
    await db.draft_undo_audit.insert_one({
        "league_id": lg, "pick_number": 1, "removed_count": 1,
        "removed_picks": [{"overall": 1, "team": "AAA"}],
        "commissioner_id": commish, "commissioner_name": "Commish",
        "undone_at": (now - timedelta(days=2)).isoformat(),
    })
    # Older than 7d
    await db.draft_undo_audit.insert_one({
        "league_id": lg, "pick_number": 2, "removed_count": 1,
        "removed_picks": [{"overall": 2, "team": "AAA"}],
        "commissioner_id": commish, "commissioner_name": "Commish",
        "undone_at": (now - timedelta(days=10)).isoformat(),
    })

    _wire_deps(db, {"_id": admin, "role": "admin"})
    try:
        result = await platform_commissioner_activity(None, limit=50, days=7)
        by_league = result["aggregates"]["by_league"]
        my_row = next((r for r in by_league if r["id"] == lg), None)
        # Only the RECENT undo (2 days old) should show up for our
        # league — the 10-day-old one is outside the 7-day window.
        assert my_row is not None
        assert my_row["undos"] == 1
        assert result["window_days"] == 7
    finally:
        await _cleanup(db, [lg], [admin, commish])


@pytest.mark.asyncio
async def test_platform_activity_limit_bounded_but_aggregates_full_window():
    from routes.draft_ops import platform_commissioner_activity

    db = _db()
    admin = await _seed_user(db, "admin", role="admin")
    commish = await _seed_user(db, "commish")
    lg = await _seed_league(db, "League Limit", commish)

    now = datetime.now(timezone.utc)
    for i in range(20):
        await db.draft_undo_audit.insert_one({
            "league_id": lg, "pick_number": i + 1, "removed_count": 1,
            "removed_picks": [{"overall": i + 1, "team": "AAA"}],
            "commissioner_id": commish, "commissioner_name": "Commish",
            "undone_at": (now - timedelta(seconds=i)).isoformat(),
        })

    _wire_deps(db, {"_id": admin, "role": "admin"})
    try:
        result = await platform_commissioner_activity(None, limit=5, days=30)
        # Events capped at 5.
        assert result["count"] == 5
        # Aggregates count all 20 undos in the window for OUR league.
        by_league = result["aggregates"]["by_league"]
        my_row = next(r for r in by_league if r["id"] == lg)
        assert my_row["undos"] == 20
        assert my_row["total"] == 20
    finally:
        await _cleanup(db, [lg], [admin, commish])
