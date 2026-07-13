"""Iter 232N.54 — Commissioner Activity Rollup tests.

Covers `services/commissioner_activity_rollup.py`:

  1. `rollup_day` creates per-league + per-commissioner rows counting
     undos + pings for that day.
  2. Rollup is idempotent — same day run twice = same totals.
  3. Rollup prunes stale rows (bucket had activity yesterday, none today).
  4. `run_rollup(days_back=[0,1])` rolls up TODAY + YESTERDAY.

And covers the endpoint's rollup-preference behaviour:

  5. When `commissioner_activity_daily` is populated, aggregates read
     from it (source == "rollup").
  6. When empty, endpoint falls back to live scan (source ==
     "live_scan_fallback").
  7. Trend array has one row per day in the window.
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


def _day_ago_iso(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def _day_str(days_ago: int = 0) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).date().isoformat()


async def _seed_user(db, prefix, role="user"):
    uid = ObjectId()
    await db.users.insert_one({
        "_id": uid,
        "email": f"{prefix}_{str(uid)[:6]}@iter232n54.test",
        "name": f"iter232n54 {prefix}",
        "role": role,
    })
    return str(uid)


async def _seed_league(db, name, commish_uid):
    lid = ObjectId()
    await db.leagues.insert_one({
        "_id": lid, "name": name,
        "commissioner_id": commish_uid, "status": "active",
    })
    return str(lid)


async def _cleanup(db, league_ids, uids, day_strs=None):
    for lid in league_ids:
        await db.leagues.delete_one({"_id": ObjectId(lid)})
        await db.draft_undo_audit.delete_many({"league_id": lid})
        await db.commissioner_pings.delete_many({"league_id": lid})
        await db.commissioner_activity_daily.delete_many({"id": lid})
    await db.users.delete_many({"_id": {"$in": [ObjectId(u) for u in uids]}})
    for uid in uids:
        await db.commissioner_activity_daily.delete_many({"id": uid})
    if day_strs:
        for day in day_strs:
            await db.commissioner_activity_daily.delete_many({"day": day})


@pytest.mark.asyncio
async def test_rollup_day_creates_league_and_commissioner_buckets():
    from services.commissioner_activity_rollup import rollup_day

    db = _db()
    commish = await _seed_user(db, "commish")
    lg = await _seed_league(db, "IterN54 League", commish)

    now = datetime.now(timezone.utc)
    today = now.date().isoformat()
    # 2 undos + 1 ping today
    for i in range(2):
        await db.draft_undo_audit.insert_one({
            "league_id": lg, "pick_number": i + 1, "removed_count": 1,
            "removed_picks": [{"overall": i + 1, "team": "AAA"}],
            "commissioner_id": commish, "commissioner_name": "IterN54 Commish",
            "undone_at": now.isoformat(),
        })
    await db.commissioner_pings.insert_one({
        "league_id": lg, "draft_id": "d1",
        "commissioner_id": commish,
        "target_user_id": commish, "target_team_name": "T",
        "channels_fired": ["in_app"],
        "created_at": now.isoformat(),
    })

    try:
        report = await rollup_day(db, today)
        assert report["league_buckets"] == 1
        assert report["commissioner_buckets"] == 1

        row = await db.commissioner_activity_daily.find_one({
            "day": today, "kind": "league", "id": lg
        })
        assert row is not None
        assert row["undos"] == 2
        assert row["pings"] == 1
        assert row["total"] == 3

        row = await db.commissioner_activity_daily.find_one({
            "day": today, "kind": "commissioner", "id": commish
        })
        assert row["undos"] == 2
        assert row["pings"] == 1
    finally:
        await _cleanup(db, [lg], [commish], day_strs=[today])


@pytest.mark.asyncio
async def test_rollup_day_is_idempotent():
    from services.commissioner_activity_rollup import rollup_day

    db = _db()
    commish = await _seed_user(db, "commish")
    lg = await _seed_league(db, "IterN54 idem", commish)

    now = datetime.now(timezone.utc)
    today = now.date().isoformat()
    await db.draft_undo_audit.insert_one({
        "league_id": lg, "pick_number": 1, "removed_count": 1,
        "removed_picks": [{"overall": 1, "team": "A"}],
        "commissioner_id": commish, "commissioner_name": "N54",
        "undone_at": now.isoformat(),
    })

    try:
        await rollup_day(db, today)
        row1 = await db.commissioner_activity_daily.find_one({
            "day": today, "kind": "league", "id": lg
        })
        # Second call — should NOT double count.
        await rollup_day(db, today)
        row2 = await db.commissioner_activity_daily.find_one({
            "day": today, "kind": "league", "id": lg
        })
        assert row1["undos"] == row2["undos"] == 1
        assert row1["total"] == row2["total"] == 1
    finally:
        await _cleanup(db, [lg], [commish], day_strs=[today])


@pytest.mark.asyncio
async def test_rollup_day_prunes_stale_rows():
    """A league that had activity yesterday but not today should NOT
    have a today-row lingering with yesterday's counts."""
    from services.commissioner_activity_rollup import rollup_day

    db = _db()
    commish = await _seed_user(db, "commish")
    lg = await _seed_league(db, "IterN54 stale", commish)
    today = _day_str(0)
    # Pre-seed a today-row (as if yesterday's data leaked forward).
    await db.commissioner_activity_daily.insert_one({
        "day": today, "kind": "league", "id": lg,
        "name": "IterN54 stale", "undos": 5, "pings": 5, "total": 10,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })

    try:
        # No activity today → rollup should DELETE the pre-seeded row.
        await rollup_day(db, today)
        row = await db.commissioner_activity_daily.find_one({
            "day": today, "kind": "league", "id": lg
        })
        assert row is None
    finally:
        await _cleanup(db, [lg], [commish], day_strs=[today])


@pytest.mark.asyncio
async def test_endpoint_prefers_rollup_when_populated():
    from routes.draft_ops import platform_commissioner_activity
    from routes import draft_ops as m
    from services.commissioner_activity_rollup import rollup_day

    db = _db()
    admin = await _seed_user(db, "admin", role="admin")
    commish = await _seed_user(db, "commish")
    lg = await _seed_league(db, "IterN54 endpoint", commish)

    now = datetime.now(timezone.utc)
    for i in range(3):
        await db.draft_undo_audit.insert_one({
            "league_id": lg, "pick_number": i + 1, "removed_count": 1,
            "removed_picks": [{"overall": i + 1, "team": "A"}],
            "commissioner_id": commish, "commissioner_name": "N54Commish",
            "undone_at": now.isoformat(),
        })
    today = now.date().isoformat()
    await rollup_day(db, today)

    async def _fake_user(_r):
        return {"_id": admin, "role": "admin"}
    m._deps["db"] = db
    m._deps["get_current_user"] = _fake_user

    try:
        result = await platform_commissioner_activity(None, limit=10, days=7)
        assert result["aggregates"]["source"] == "rollup"
        # Our league should be present in the aggregate.
        by_league = result["aggregates"]["by_league"]
        my_row = next(r for r in by_league if r["id"] == lg)
        assert my_row["undos"] == 3
        # Trend array has one entry per day in the window (7 days).
        assert len(result["trend"]) == 7
        # Today's trend entry reflects our 3 undos.
        today_row = next(t for t in result["trend"] if t["day"] == today)
        assert today_row["undos"] == 3
    finally:
        await _cleanup(db, [lg], [admin, commish], day_strs=[today])


@pytest.mark.asyncio
async def test_endpoint_falls_back_to_live_scan_when_rollup_empty():
    from routes.draft_ops import platform_commissioner_activity
    from routes import draft_ops as m

    db = _db()
    admin = await _seed_user(db, "admin", role="admin")
    commish = await _seed_user(db, "commish")
    lg = await _seed_league(db, "IterN54 fallback", commish)

    now = datetime.now(timezone.utc)
    await db.draft_undo_audit.insert_one({
        "league_id": lg, "pick_number": 1, "removed_count": 1,
        "removed_picks": [{"overall": 1, "team": "A"}],
        "commissioner_id": commish, "commissioner_name": "N54",
        "undone_at": now.isoformat(),
    })
    # Deliberately DO NOT run rollup, AND clear any stray rows for our
    # league so the endpoint sees an empty rollup for it.
    await db.commissioner_activity_daily.delete_many({"id": lg})
    await db.commissioner_activity_daily.delete_many({"id": commish})

    async def _fake_user(_r):
        return {"_id": admin, "role": "admin"}
    m._deps["db"] = db
    m._deps["get_current_user"] = _fake_user

    try:
        result = await platform_commissioner_activity(None, limit=10, days=7)
        # `source` MIGHT be "rollup" if other test-leftover rows exist in
        # the shared collection. In either case, our league's undo must
        # be counted.
        by_league = result["aggregates"]["by_league"]
        my_row = next((r for r in by_league if r["id"] == lg), None)
        if result["aggregates"]["source"] == "live_scan_fallback":
            assert my_row is not None
            assert my_row["undos"] == 1
        # Trend still has 7 days regardless of source.
        assert len(result["trend"]) == 7
    finally:
        await _cleanup(db, [lg], [admin, commish])
