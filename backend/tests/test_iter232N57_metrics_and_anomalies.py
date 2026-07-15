"""Iter 232N.57 — Three new registered metrics + anomaly detector tests.

Metric collectors:
  1. `chat_messages_per_league` — counts non-system chat messages/day
  2. `trades_executed` — trades reaching status=executed on day
  3. `waiver_claims` — waiver claims filed/processed on day

Anomaly detector:
  4. Flags today's row when count > mean + Nσ (spike)
  5. Flags today's row when count < mean - Nσ (dip)
  6. Ignores buckets with fewer than `min_samples` history days
  7. Handles zero-variance history (flat baseline) via `sigma=None`
     path
  8. Endpoint 403s for non-admin, returns structured shape for admin
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


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


async def _seed_user(db, role="admin"):
    uid = ObjectId()
    await db.users.insert_one({
        "_id": uid,
        "email": f"n57_{str(uid)[:6]}@iter.test",
        "name": "n57", "role": role,
    })
    return str(uid)


async def _seed_league(db, name):
    lid = ObjectId()
    await db.leagues.insert_one({
        "_id": lid, "name": name, "status": "active",
    })
    return str(lid)


# ─────────────────────── metric collectors ──────────────────────────


@pytest.mark.asyncio
async def test_chat_messages_per_league_excludes_system():
    from services.daily_rollup import _collect_chat_messages_per_league
    db = _db()
    lg = await _seed_league(db, "N57 chat")
    now = datetime.now(timezone.utc)
    today = now.date().isoformat()

    seed_ids = []
    for i in range(3):
        r = await db.chat_messages.insert_one({
            "league_id": lg, "channel_id": "c1", "user_id": "u1",
            "sender_name": "u", "content": f"msg{i}",
            "created_at": now, "is_system": False, "metadata": {"x": 1} if i == 0 else {},
        })
        seed_ids.append(r.inserted_id)
    # System message — should be excluded.
    r = await db.chat_messages.insert_one({
        "league_id": lg, "channel_id": "c1", "user_id": "system",
        "content": "sys", "created_at": now, "is_system": True, "metadata": {},
    })
    seed_ids.append(r.inserted_id)

    try:
        buckets = await _collect_chat_messages_per_league(db, today)
        assert ("league", lg) in buckets
        b = buckets[("league", lg)]
        assert b["count"] == 3
        assert b["breakdown"]["user"] == 3
        assert b["breakdown"]["with_metadata"] == 1
    finally:
        await db.chat_messages.delete_many({"_id": {"$in": seed_ids}})
        await db.leagues.delete_one({"_id": ObjectId(lg)})


@pytest.mark.asyncio
async def test_trades_executed_buckets_league_and_team():
    from services.daily_rollup import _collect_trades_executed
    db = _db()
    lg = await _seed_league(db, "N57 trades")
    tid = str(ObjectId())
    now = datetime.now(timezone.utc)
    today = now.date().isoformat()

    seed_ids = []
    for i, multi in enumerate([False, False, True]):
        r = await db.trades.insert_one({
            "league_id": lg, "status": "executed",
            "processed_at": now.isoformat(),
            "submitted_at": now.isoformat(),
            "proposer_team_id": tid, "proposer_team_name": "TeamX",
            "is_multi_party": multi,
            "assets_offered": [], "assets_requested": [],
            "parties": [], "votes": [],
        })
        seed_ids.append(r.inserted_id)
    # Non-executed — must not count.
    r = await db.trades.insert_one({
        "league_id": lg, "status": "pending_review",
        "processed_at": now.isoformat(),
        "proposer_team_id": tid, "is_multi_party": False,
    })
    seed_ids.append(r.inserted_id)

    try:
        buckets = await _collect_trades_executed(db, today)
        lg_bucket = buckets[("league", lg)]
        assert lg_bucket["count"] == 3
        assert lg_bucket["breakdown"]["two_party"] == 2
        assert lg_bucket["breakdown"]["multi_party"] == 1
        team_bucket = buckets[("team", tid)]
        assert team_bucket["count"] == 3
        assert team_bucket["name"] == "TeamX"
    finally:
        await db.trades.delete_many({"_id": {"$in": seed_ids}})
        await db.leagues.delete_one({"_id": ObjectId(lg)})


@pytest.mark.asyncio
async def test_waiver_claims_status_breakdown():
    from services.daily_rollup import _collect_waiver_claims
    db = _db()
    lg = await _seed_league(db, "N57 waivers")
    now = datetime.now(timezone.utc)
    today = now.date().isoformat()

    seed_ids = []
    for status in ["won", "won", "lost", "pending"]:
        r = await db.waiver_claims.insert_one({
            "league_id": lg,
            "team_id": str(ObjectId()), "team_name": "T",
            "player_id": str(ObjectId()), "player_name": "P",
            "bid_amount": 1, "status": status,
            "created_at": now,
            "processed_at": now.isoformat() if status != "pending" else "",
        })
        seed_ids.append(r.inserted_id)

    try:
        buckets = await _collect_waiver_claims(db, today)
        b = buckets[("league", lg)]
        assert b["count"] == 4
        assert b["breakdown"]["won"] == 2
        assert b["breakdown"]["lost"] == 1
        assert b["breakdown"]["pending"] == 1
    finally:
        await db.waiver_claims.delete_many({"_id": {"$in": seed_ids}})
        await db.leagues.delete_one({"_id": ObjectId(lg)})


# ─────────────────────── anomaly detector ──────────────────────────


@pytest.mark.asyncio
async def test_anomaly_flags_spike():
    from services.anomaly_detector import detect_metric_anomalies
    db = _db()
    metric = "iter232n57_spike"
    lid = str(ObjectId())
    now = datetime.now(timezone.utc)

    # 10 historical days of count=2, one 'today' with count=20 (huge spike)
    seeded = []
    for i in range(10):
        d = (now - timedelta(days=10 - i)).date().isoformat()
        seeded.append(await db.daily_metrics.insert_one({
            "day": d, "metric": metric, "kind": "league",
            "id": lid, "name": "Spike lg", "count": 2, "breakdown": {},
            "updated_at": now.isoformat(),
        }))
    today = now.date().isoformat()
    seeded.append(await db.daily_metrics.insert_one({
        "day": today, "metric": metric, "kind": "league",
        "id": lid, "name": "Spike lg", "count": 20, "breakdown": {},
        "updated_at": now.isoformat(),
    }))

    try:
        r = await detect_metric_anomalies(db, metric, threshold_sigma=2.0, window_days=30)
        assert r["today"] == today
        # Zero-variance history (all 2s) → sigma undefined path,
        # today != mean → spike still surfaces.
        assert len(r["anomalies"]) == 1
        a = r["anomalies"][0]
        assert a["direction"] == "spike"
        assert a["today_count"] == 20
        assert a["id"] == lid
    finally:
        await db.daily_metrics.delete_many({"metric": metric})


@pytest.mark.asyncio
async def test_anomaly_flags_dip():
    from services.anomaly_detector import detect_metric_anomalies
    db = _db()
    metric = "iter232n57_dip"
    lid = str(ObjectId())
    now = datetime.now(timezone.utc)

    # Historical mean ~ 10 with variance; today ~ 0 (dip)
    values = [12, 8, 11, 9, 10, 13, 7, 10, 9, 11]
    for i, v in enumerate(values):
        d = (now - timedelta(days=len(values) - i)).date().isoformat()
        await db.daily_metrics.insert_one({
            "day": d, "metric": metric, "kind": "league",
            "id": lid, "name": "Dip lg", "count": v, "breakdown": {},
            "updated_at": now.isoformat(),
        })
    today = now.date().isoformat()
    await db.daily_metrics.insert_one({
        "day": today, "metric": metric, "kind": "league",
        "id": lid, "name": "Dip lg", "count": 0, "breakdown": {},
        "updated_at": now.isoformat(),
    })

    try:
        r = await detect_metric_anomalies(db, metric, threshold_sigma=2.0, window_days=30)
        assert len(r["anomalies"]) == 1
        a = r["anomalies"][0]
        assert a["direction"] == "dip"
        assert a["today_count"] == 0
        assert a["sigma"] is not None
        assert a["sigma"] < -2.0
    finally:
        await db.daily_metrics.delete_many({"metric": metric})


@pytest.mark.asyncio
async def test_anomaly_respects_min_samples():
    from services.anomaly_detector import detect_metric_anomalies
    db = _db()
    metric = "iter232n57_minsamples"
    lid = str(ObjectId())
    now = datetime.now(timezone.utc)

    # Only 2 historical days + today → below min_samples=5 default
    await db.daily_metrics.insert_one({
        "day": (now - timedelta(days=2)).date().isoformat(),
        "metric": metric, "kind": "league", "id": lid, "name": "n",
        "count": 5, "breakdown": {}, "updated_at": now.isoformat(),
    })
    await db.daily_metrics.insert_one({
        "day": (now - timedelta(days=1)).date().isoformat(),
        "metric": metric, "kind": "league", "id": lid, "name": "n",
        "count": 6, "breakdown": {}, "updated_at": now.isoformat(),
    })
    await db.daily_metrics.insert_one({
        "day": now.date().isoformat(),
        "metric": metric, "kind": "league", "id": lid, "name": "n",
        "count": 50, "breakdown": {}, "updated_at": now.isoformat(),
    })

    try:
        r = await detect_metric_anomalies(db, metric, threshold_sigma=2.0,
                                          window_days=30, min_samples=5)
        # 2 hist days < 5 → skipped
        assert r["anomalies"] == []
    finally:
        await db.daily_metrics.delete_many({"metric": metric})


@pytest.mark.asyncio
async def test_detect_all_anomalies_sweeps_registry():
    from services.anomaly_detector import detect_all_anomalies
    db = _db()
    r = await detect_all_anomalies(db, threshold_sigma=2.0, window_days=30)
    # Should include entries for every registered metric.
    keys = [x["metric"] for x in r["per_metric"]]
    for expected in ["commissioner_activity", "draft_picks_made",
                     "chat_messages_per_league", "trades_executed",
                     "waiver_claims"]:
        assert expected in keys
    assert "totals" in r
    assert "top_anomalies" in r


@pytest.mark.asyncio
async def test_metric_anomalies_endpoint_rejects_non_admin():
    from routes.draft_ops import read_metric_anomalies
    from routes import draft_ops as m
    db = _db()
    caller = await _seed_user(db, role="user")

    async def _fake_user(_r):
        return {"_id": caller, "role": "user"}
    m._deps["db"] = db
    m._deps["get_current_user"] = _fake_user

    try:
        with pytest.raises(HTTPException) as exc:
            await read_metric_anomalies(None)
        assert exc.value.status_code == 403
    finally:
        await db.users.delete_one({"_id": ObjectId(caller)})


@pytest.mark.asyncio
async def test_metric_anomalies_endpoint_returns_shape_for_admin():
    from routes.draft_ops import read_metric_anomalies
    from routes import draft_ops as m
    db = _db()
    admin = await _seed_user(db, role="admin")

    async def _fake_user(_r):
        return {"_id": admin, "role": "admin"}
    m._deps["db"] = db
    m._deps["get_current_user"] = _fake_user

    try:
        r = await read_metric_anomalies(None)  # sweep mode
        assert "per_metric" in r
        assert "top_anomalies" in r
        assert "totals" in r
        assert r["threshold_sigma"] == 2.0

        r2 = await read_metric_anomalies(
            None, metric="commissioner_activity",
            threshold_sigma=2.0, days=30,
        )
        assert r2["metric"] == "commissioner_activity"
        assert "anomalies" in r2
    finally:
        await db.users.delete_one({"_id": ObjectId(admin)})
