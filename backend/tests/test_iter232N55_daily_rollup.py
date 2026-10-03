"""Iter 232N.55 — Generic daily rollup framework tests.

Covers `services/daily_rollup.py`:

  1. `register_metric` adds a spec to the registry; `registered_metrics()`
     returns it back.
  2. `rollup_metric_day` upserts one row per collected bucket.
  3. Idempotent: rolling the same day twice with unchanged inputs
     yields identical row counts.
  4. Stale prune: a bucket that disappears from collect() is removed.
  5. Built-in `commissioner_activity` metric collects both undos + pings
     into a breakdown dict.
  6. Built-in `draft_picks_made` metric counts picks executed on the
     day with auto/manual breakdown.

And the endpoint `GET /api/admin/daily-metrics`:

  7. Rejects non-admin 403.
  8. Returns leaderboard + trend + totals from `daily_metrics`.
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
        os.environ.get("DB_NAME", os.environ["DB_NAME"])
    ]


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


async def _seed_user(db, prefix, role="user"):
    uid = ObjectId()
    await db.users.insert_one({
        "_id": uid,
        "email": f"{prefix}_{str(uid)[:6]}@iter232n55.test",
        "name": f"iter232n55 {prefix}",
        "role": role,
    })
    return str(uid)


async def _seed_league(db, name, commish):
    lid = ObjectId()
    await db.leagues.insert_one({
        "_id": lid, "name": name,
        "commissioner_id": commish, "status": "active",
    })
    return str(lid)


async def _cleanup(db, league_ids, uids, day=None):
    for lid in league_ids:
        await db.leagues.delete_one({"_id": ObjectId(lid)})
        await db.draft_undo_audit.delete_many({"league_id": lid})
        await db.commissioner_pings.delete_many({"league_id": lid})
        await db.draft_picks.delete_many({"league_id": lid})
        await db.daily_metrics.delete_many({"id": lid})
    for uid in uids:
        await db.daily_metrics.delete_many({"id": uid})
    await db.users.delete_many({"_id": {"$in": [ObjectId(u) for u in uids]}})
    if day:
        await db.daily_metrics.delete_many({"day": day})


@pytest.mark.asyncio
async def test_register_metric_and_list():
    from services.daily_rollup import MetricSpec, register_metric, registered_metrics

    async def _dummy_collect(_db, _day):
        return {}

    register_metric(MetricSpec(key="iter232n55_probe", collect=_dummy_collect,
                                description="Probe metric"))
    keys = [m.key for m in registered_metrics()]
    assert "iter232n55_probe" in keys


@pytest.mark.asyncio
async def test_rollup_metric_day_idempotent_and_prunes():
    from services.daily_rollup import MetricSpec, rollup_metric_day

    db = _db()
    today = _today()
    league1 = str(ObjectId())
    league2 = str(ObjectId())

    calls = {"round": 1}

    async def _collect(_db, _day):
        if calls["round"] == 1:
            return {
                ("league", league1): {"name": "L1", "count": 3,
                                      "breakdown": {"a": 2, "b": 1}},
                ("league", league2): {"name": "L2", "count": 1,
                                      "breakdown": {"a": 1}},
            }
        else:
            # L2 vanished; L1 changed count.
            return {
                ("league", league1): {"name": "L1", "count": 5,
                                      "breakdown": {"a": 4, "b": 1}},
            }

    spec = MetricSpec(key="iter232n55_probe", collect=_collect)
    try:
        r1 = await rollup_metric_day(db, spec, today)
        assert r1["upserted"] == 2

        # Idempotent — same collector output, same rows.
        r2 = await rollup_metric_day(db, spec, today)
        assert r2["upserted"] == 2
        rows = await db.daily_metrics.count_documents({
            "metric": "iter232n55_probe", "day": today,
        })
        assert rows == 2

        # Second round: L2 disappears → pruned; L1 updates.
        calls["round"] = 2
        r3 = await rollup_metric_day(db, spec, today)
        assert r3["upserted"] == 1

        remaining = await db.daily_metrics.find({
            "metric": "iter232n55_probe", "day": today,
        }).to_list(None)
        assert len(remaining) == 1
        assert remaining[0]["id"] == league1
        assert remaining[0]["count"] == 5
        assert remaining[0]["breakdown"]["a"] == 4
    finally:
        await db.daily_metrics.delete_many({"metric": "iter232n55_probe"})


@pytest.mark.asyncio
async def test_builtin_commissioner_activity_metric_collects_breakdown():
    from services.daily_rollup import _collect_commissioner_activity

    db = _db()
    commish = await _seed_user(db, "commish")
    lg = await _seed_league(db, "N55 lg", commish)
    now = datetime.now(timezone.utc)
    today = now.date().isoformat()

    await db.draft_undo_audit.insert_one({
        "league_id": lg, "pick_number": 1, "removed_count": 1,
        "removed_picks": [{"overall": 1, "team": "A"}],
        "commissioner_id": commish, "commissioner_name": "N55",
        "undone_at": now.isoformat(),
    })
    await db.commissioner_pings.insert_one({
        "league_id": lg, "draft_id": "d", "commissioner_id": commish,
        "target_user_id": commish, "target_team_name": "T",
        "channels_fired": ["in_app"],
        "created_at": now.isoformat(),
    })

    try:
        buckets = await _collect_commissioner_activity(db, today)
        lg_bucket = buckets[("league", lg)]
        assert lg_bucket["count"] == 2
        assert lg_bucket["breakdown"] == {"undos": 1, "pings": 1}
        cm_bucket = buckets[("commissioner", commish)]
        assert cm_bucket["count"] == 2
        assert cm_bucket["breakdown"]["undos"] == 1
        assert cm_bucket["breakdown"]["pings"] == 1
    finally:
        await _cleanup(db, [lg], [commish], day=today)


@pytest.mark.asyncio
async def test_builtin_draft_picks_made_metric():
    from services.daily_rollup import _collect_draft_picks_made

    db = _db()
    commish = await _seed_user(db, "c")
    lg = await _seed_league(db, "N55 picks", commish)
    now = datetime.now(timezone.utc)
    today = now.date().isoformat()

    # 2 manual + 1 auto pick today
    for i in range(3):
        await db.draft_picks.insert_one({
            "league_id": lg, "draft_id": "d", "pick_number": i + 1,
            "team_abbr": "A", "player_id": str(ObjectId()),
            "player_name": f"P{i}",
            "picked_at": now.isoformat(),
            "auto_picked": i == 2,
        })

    try:
        buckets = await _collect_draft_picks_made(db, today)
        lg_bucket = buckets[("league", lg)]
        assert lg_bucket["count"] == 3
        assert lg_bucket["breakdown"]["manual"] == 2
        assert lg_bucket["breakdown"]["auto_picked"] == 1
    finally:
        await _cleanup(db, [lg], [commish], day=today)


@pytest.mark.asyncio
async def test_daily_metrics_endpoint_rejects_non_admin():
    from routes.admin_metrics import read_daily_metrics
    from routes import admin_metrics as m
    from fastapi import HTTPException

    db = _db()
    caller = await _seed_user(db, "regular", role="user")

    async def _fake_user(_r):
        return {"_id": caller, "role": "user"}
    m._deps["db"] = db
    m._deps["get_current_user"] = _fake_user

    try:
        with pytest.raises(HTTPException) as exc:
            await read_daily_metrics(None, metric="commissioner_activity",
                                      kind="league", days=7, limit=10)
        assert exc.value.status_code == 403
    finally:
        await _cleanup(db, [], [caller])


@pytest.mark.asyncio
async def test_daily_metrics_endpoint_returns_leaderboard_and_trend():
    from routes.admin_metrics import read_daily_metrics
    from routes import admin_metrics as m

    db = _db()
    admin = await _seed_user(db, "admin", role="admin")
    lg = str(ObjectId())
    today = _today()
    # Pre-seed daily_metrics directly.
    await db.daily_metrics.insert_one({
        "day": today, "metric": "iter232n55_endpoint",
        "kind": "league", "id": lg, "name": "N55 Endpoint",
        "count": 7, "breakdown": {"a": 4, "b": 3},
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })

    async def _fake_user(_r):
        return {"_id": admin, "role": "admin"}
    m._deps["db"] = db
    m._deps["get_current_user"] = _fake_user

    try:
        result = await read_daily_metrics(
            None, metric="iter232n55_endpoint", kind="league",
            days=7, limit=10,
        )
        assert result["metric"] == "iter232n55_endpoint"
        assert result["totals"]["count"] == 7
        assert result["totals"]["breakdown"]["a"] == 4
        # Leaderboard has our lg row.
        my_row = next(r for r in result["leaderboard"] if r["id"] == lg)
        assert my_row["count"] == 7
        # Trend has one entry per day in window (7).
        assert len(result["trend"]) == 7
        today_row = next(t for t in result["trend"] if t["day"] == today)
        assert today_row["count"] == 7
    finally:
        await db.daily_metrics.delete_many({"metric": "iter232n55_endpoint"})
        await _cleanup(db, [], [admin])
