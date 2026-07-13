"""Iter 232N.56 — Metric Explorer discovery-endpoint enrichment tests.

Covers the extended `GET /api/admin/daily-metrics/registered` shape which
now exposes:

  • `kinds` — distinct bucket dimensions observed in `daily_metrics`
  • `last_seen_day` — most recent day the metric produced a row

so the Metric Explorer UI can populate its kind picker + freshness
badge without a second round-trip.

Also covers:

  • 403 for non-admin
  • kinds derived from what's actually in the collection (not hardcoded)
  • `last_seen_day` picks the latest of multiple days
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone, timedelta

import pytest
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient
from fastapi import HTTPException

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _db():
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[
        os.environ.get("DB_NAME", "test_database")
    ]


async def _seed_user(db, role="admin"):
    uid = ObjectId()
    await db.users.insert_one({
        "_id": uid,
        "email": f"n56_{str(uid)[:6]}@iter.test",
        "name": "n56", "role": role,
    })
    return str(uid)


@pytest.mark.asyncio
async def test_registered_endpoint_rejects_non_admin():
    from routes.draft_ops import list_registered_metrics
    from routes import draft_ops as m

    db = _db()
    caller = await _seed_user(db, role="user")

    async def _fake_user(_r):
        return {"_id": caller, "role": "user"}
    m._deps["db"] = db
    m._deps["get_current_user"] = _fake_user

    try:
        with pytest.raises(HTTPException) as exc:
            await list_registered_metrics(None)
        assert exc.value.status_code == 403
    finally:
        await db.users.delete_one({"_id": ObjectId(caller)})


@pytest.mark.asyncio
async def test_registered_endpoint_returns_kinds_and_last_seen():
    from routes.draft_ops import list_registered_metrics
    from routes import draft_ops as m

    db = _db()
    admin = await _seed_user(db, role="admin")
    metric_key = "iter232n56_probe"

    now = datetime.now(timezone.utc)
    day_recent = now.date().isoformat()
    day_older = (now - timedelta(days=3)).date().isoformat()

    # Seed rollup rows across two kinds and two days.
    seed_ids = []
    for kind, day, count in [
        ("league",       day_older,  4),
        ("league",       day_recent, 6),
        ("commissioner", day_recent, 2),
    ]:
        r = await db.daily_metrics.insert_one({
            "day": day, "metric": metric_key, "kind": kind,
            "id": str(ObjectId()), "name": f"row-{kind}-{day}",
            "count": count, "breakdown": {},
            "updated_at": now.isoformat(),
        })
        seed_ids.append(r.inserted_id)

    async def _fake_user(_r):
        return {"_id": admin, "role": "admin"}
    m._deps["db"] = db
    m._deps["get_current_user"] = _fake_user

    # Register a fresh MetricSpec so the endpoint enumerates it.
    from services.daily_rollup import MetricSpec, register_metric

    async def _dummy_collect(_db, _day):
        return {}
    register_metric(MetricSpec(key=metric_key, collect=_dummy_collect,
                                description="Iter 232N.56 probe"))

    try:
        result = await list_registered_metrics(None)
        my = next(x for x in result["metrics"] if x["key"] == metric_key)
        # kinds should include BOTH observed kinds, sorted.
        assert set(my["kinds"]) == {"league", "commissioner"}
        assert my["kinds"] == sorted(my["kinds"])
        # last_seen_day == most recent day we seeded.
        assert my["last_seen_day"] == day_recent
        # description preserved.
        assert my["description"] == "Iter 232N.56 probe"
    finally:
        await db.daily_metrics.delete_many({"metric": metric_key})
        await db.users.delete_one({"_id": ObjectId(admin)})


@pytest.mark.asyncio
async def test_registered_endpoint_empty_kinds_when_no_rollups():
    """A newly-registered metric with zero rollup docs must still show
    up in discovery with empty `kinds` and null `last_seen_day` — so the
    Metric Explorer can render 'no rollup rows yet' gracefully."""
    from routes.draft_ops import list_registered_metrics
    from routes import draft_ops as m

    db = _db()
    admin = await _seed_user(db, role="admin")
    metric_key = "iter232n56_empty"

    from services.daily_rollup import MetricSpec, register_metric

    async def _dummy_collect(_db, _day):
        return {}
    register_metric(MetricSpec(key=metric_key, collect=_dummy_collect,
                                description="Empty probe"))

    # Ensure clean slate.
    await db.daily_metrics.delete_many({"metric": metric_key})

    async def _fake_user(_r):
        return {"_id": admin, "role": "admin"}
    m._deps["db"] = db
    m._deps["get_current_user"] = _fake_user

    try:
        result = await list_registered_metrics(None)
        my = next(x for x in result["metrics"] if x["key"] == metric_key)
        assert my["kinds"] == []
        assert my["last_seen_day"] is None
    finally:
        await db.users.delete_one({"_id": ObjectId(admin)})
