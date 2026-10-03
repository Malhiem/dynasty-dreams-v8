"""Iter 232N.58 — Anomaly history persistence + streak computation tests.

Covers:
  1. `persist_anomalies` idempotently upserts one doc per (day, metric,
     kind, id) — same-day re-run mutates in place.
  2. `_walk_streak` returns 0 for buckets with no history.
  3. `_walk_streak` counts consecutive flagged days back from today.
  4. `_walk_streak` with `same_direction` filter counts only matching
     days (spike streak breaks when a dip lands).
  5. `enrich_with_streaks` populates both `any_streak` and
     `directional_streak` on every anomaly.
  6. `top_ongoing_streaks` ranks buckets by streak length and only
     surfaces streaks ongoing today or yesterday.
  7. `detect_all_anomalies` persists into `metric_anomaly_history` and
     enriches with streaks (integration test).
  8. Endpoint `GET /admin/anomaly-streaks` 403s for non-admin.
  9. Endpoint returns correct shape for admin.
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
        os.environ.get("DB_NAME", os.environ["DB_NAME"])
    ]


async def _seed_user(db, role="admin"):
    uid = ObjectId()
    await db.users.insert_one({
        "_id": uid,
        "email": f"n58_{str(uid)[:6]}@iter.test",
        "name": "n58", "role": role,
    })
    return str(uid)


def _day(offset: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=offset)).date().isoformat()


@pytest.mark.asyncio
async def test_persist_anomalies_idempotent():
    from services.anomaly_history import persist_anomalies
    db = _db()
    metric = "iter232n58_persist"
    rid = str(ObjectId())
    today = _day(0)
    row = {
        "metric": metric, "kind": "league", "id": rid, "name": "R",
        "today_count": 10, "mean": 2.0, "stddev": 1.0, "sigma": 8.0,
        "direction": "spike", "delta": 8.0,
    }
    try:
        n1 = await persist_anomalies(db, [row], today)
        assert n1 == 1
        # Idempotent — second call updates in place.
        row["today_count"] = 12
        n2 = await persist_anomalies(db, [row], today)
        assert n2 == 1
        docs = await db.metric_anomaly_history.find({"metric": metric}).to_list(None)
        assert len(docs) == 1
        assert docs[0]["today_count"] == 12
    finally:
        await db.metric_anomaly_history.delete_many({"metric": metric})


@pytest.mark.asyncio
async def test_walk_streak_empty_returns_zero():
    from services.anomaly_history import _walk_streak
    db = _db()
    n = await _walk_streak(db, "nonexistent_metric", "league", str(ObjectId()), _day(0))
    assert n == 0


@pytest.mark.asyncio
async def test_walk_streak_counts_consecutive_days():
    from services.anomaly_history import _walk_streak, persist_anomalies
    db = _db()
    metric = "iter232n58_streak"
    rid = str(ObjectId())
    try:
        # 3 consecutive days flagged, ending today
        for off in [2, 1, 0]:
            await persist_anomalies(db, [{
                "metric": metric, "kind": "league", "id": rid, "name": "S",
                "today_count": 10, "mean": 2, "stddev": 1, "sigma": 8,
                "direction": "spike", "delta": 8,
            }], _day(off))
        # Extra day 5 days ago (breaks streak going further back)
        await persist_anomalies(db, [{
            "metric": metric, "kind": "league", "id": rid, "name": "S",
            "today_count": 10, "mean": 2, "stddev": 1, "sigma": 8,
            "direction": "spike", "delta": 8,
        }], _day(5))

        streak = await _walk_streak(db, metric, "league", rid, _day(0))
        assert streak == 3
    finally:
        await db.metric_anomaly_history.delete_many({"metric": metric})


@pytest.mark.asyncio
async def test_directional_streak_breaks_on_direction_flip():
    from services.anomaly_history import _walk_streak, persist_anomalies
    db = _db()
    metric = "iter232n58_direction"
    rid = str(ObjectId())
    try:
        # Yesterday=dip, today=spike → directional (spike) streak = 1
        await persist_anomalies(db, [{
            "metric": metric, "kind": "league", "id": rid, "name": "D",
            "today_count": 0, "mean": 10, "stddev": 2, "sigma": -5,
            "direction": "dip", "delta": -10,
        }], _day(1))
        await persist_anomalies(db, [{
            "metric": metric, "kind": "league", "id": rid, "name": "D",
            "today_count": 20, "mean": 10, "stddev": 2, "sigma": 5,
            "direction": "spike", "delta": 10,
        }], _day(0))

        any_streak = await _walk_streak(db, metric, "league", rid, _day(0))
        assert any_streak == 2

        spike_streak = await _walk_streak(
            db, metric, "league", rid, _day(0), same_direction="spike"
        )
        assert spike_streak == 1
    finally:
        await db.metric_anomaly_history.delete_many({"metric": metric})


@pytest.mark.asyncio
async def test_enrich_with_streaks_populates_both_fields():
    from services.anomaly_history import enrich_with_streaks, persist_anomalies
    db = _db()
    metric = "iter232n58_enrich"
    rid = str(ObjectId())
    try:
        for off in [2, 1, 0]:
            await persist_anomalies(db, [{
                "metric": metric, "kind": "league", "id": rid, "name": "E",
                "today_count": 10, "mean": 2, "stddev": 1, "sigma": 8,
                "direction": "spike", "delta": 8,
            }], _day(off))

        anomalies = [{
            "metric": metric, "kind": "league", "id": rid, "name": "E",
            "direction": "spike",
        }]
        enriched = await enrich_with_streaks(db, anomalies, _day(0))
        assert enriched[0]["any_streak"] == 3
        assert enriched[0]["directional_streak"] == 3
    finally:
        await db.metric_anomaly_history.delete_many({"metric": metric})


@pytest.mark.asyncio
async def test_top_ongoing_streaks_ranks_and_filters():
    from services.anomaly_history import persist_anomalies, top_ongoing_streaks
    db = _db()

    long_metric = "iter232n58_top_long"
    short_metric = "iter232n58_top_short"
    stale_metric = "iter232n58_top_stale"
    rid_long = str(ObjectId())
    rid_short = str(ObjectId())
    rid_stale = str(ObjectId())

    try:
        # Long streak: 4 consecutive days ending today
        for off in [3, 2, 1, 0]:
            await persist_anomalies(db, [{
                "metric": long_metric, "kind": "league", "id": rid_long, "name": "LongLg",
                "direction": "spike", "today_count": 10, "mean": 2, "stddev": 1, "sigma": 8, "delta": 8,
            }], _day(off))
        # Short streak: 2 days ending today
        for off in [1, 0]:
            await persist_anomalies(db, [{
                "metric": short_metric, "kind": "league", "id": rid_short, "name": "ShortLg",
                "direction": "dip", "today_count": 0, "mean": 5, "stddev": 1, "sigma": -5, "delta": -5,
            }], _day(off))
        # Stale streak: 3 days but ended 5 days ago — should NOT surface
        for off in [7, 6, 5]:
            await persist_anomalies(db, [{
                "metric": stale_metric, "kind": "league", "id": rid_stale, "name": "StaleLg",
                "direction": "spike", "today_count": 10, "mean": 2, "stddev": 1, "sigma": 8, "delta": 8,
            }], _day(off))

        rows = await top_ongoing_streaks(db, min_streak=2, limit=10)
        # Only ongoing (today/yesterday) buckets should appear
        ids = {r["id"] for r in rows}
        assert rid_long in ids
        assert rid_short in ids
        assert rid_stale not in ids

        # Ranking — longest first
        long_row = next(r for r in rows if r["id"] == rid_long)
        short_row = next(r for r in rows if r["id"] == rid_short)
        assert long_row["any_streak"] == 4
        assert short_row["any_streak"] == 2
        assert rows.index(long_row) < rows.index(short_row)

        # min_streak filter
        rows_min3 = await top_ongoing_streaks(db, min_streak=3, limit=10)
        ids_min3 = {r["id"] for r in rows_min3}
        assert rid_long in ids_min3
        assert rid_short not in ids_min3
    finally:
        await db.metric_anomaly_history.delete_many({
            "metric": {"$in": [long_metric, short_metric, stale_metric]},
        })


@pytest.mark.asyncio
async def test_detect_all_persists_and_enriches():
    """End-to-end: seed daily_metrics with a clear spike, run
    detect_all_anomalies, verify history collection populated + streak
    fields present."""
    from services.daily_rollup import MetricSpec, register_metric
    from services.anomaly_detector import detect_all_anomalies
    db = _db()
    metric = "iter232n58_e2e"
    rid = str(ObjectId())
    now = datetime.now(timezone.utc)

    async def _collect(_db, _day):
        return {}
    register_metric(MetricSpec(key=metric, collect=_collect,
                                description="E2E N58 probe"))

    try:
        # 10 days of low counts + 1 spike day (today)
        for i in range(10):
            d = (now - timedelta(days=10 - i)).date().isoformat()
            await db.daily_metrics.insert_one({
                "day": d, "metric": metric, "kind": "league",
                "id": rid, "name": "E2E lg", "count": 2, "breakdown": {},
                "updated_at": now.isoformat(),
            })
        today = now.date().isoformat()
        await db.daily_metrics.insert_one({
            "day": today, "metric": metric, "kind": "league",
            "id": rid, "name": "E2E lg", "count": 30, "breakdown": {},
            "updated_at": now.isoformat(),
        })

        result = await detect_all_anomalies(db, threshold_sigma=2.0)
        # Find the row for our probe
        our = [a for a in result["top_anomalies"] if a["metric"] == metric]
        assert len(our) == 1
        row = our[0]
        assert row["direction"] == "spike"
        assert row["any_streak"] == 1
        assert row["directional_streak"] == 1
        # History persisted
        persisted = await db.metric_anomaly_history.find_one(
            {"metric": metric, "day": today, "id": rid}
        )
        assert persisted is not None
        assert persisted["direction"] == "spike"
    finally:
        await db.daily_metrics.delete_many({"metric": metric})
        await db.metric_anomaly_history.delete_many({"metric": metric})


@pytest.mark.asyncio
async def test_anomaly_streaks_endpoint_rejects_non_admin():
    from routes.admin_metrics import read_anomaly_streaks
    from routes import admin_metrics as m
    db = _db()
    caller = await _seed_user(db, role="user")

    async def _fake_user(_r):
        return {"_id": caller, "role": "user"}
    m._deps["db"] = db
    m._deps["get_current_user"] = _fake_user

    try:
        with pytest.raises(HTTPException) as exc:
            await read_anomaly_streaks(None)
        assert exc.value.status_code == 403
    finally:
        await db.users.delete_one({"_id": ObjectId(caller)})


@pytest.mark.asyncio
async def test_anomaly_streaks_endpoint_returns_shape():
    from routes.admin_metrics import read_anomaly_streaks
    from routes import admin_metrics as m
    db = _db()
    admin = await _seed_user(db, role="admin")

    async def _fake_user(_r):
        return {"_id": admin, "role": "admin"}
    m._deps["db"] = db
    m._deps["get_current_user"] = _fake_user

    try:
        r = await read_anomaly_streaks(None, min_streak=2, limit=10)
        assert "checked_at" in r
        assert "streaks" in r
        assert r["min_streak"] == 2
    finally:
        await db.users.delete_one({"_id": ObjectId(admin)})
