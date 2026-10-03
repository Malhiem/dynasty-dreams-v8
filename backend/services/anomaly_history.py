"""Iter 232N.58 — Anomaly history + streak computation.

Persists every flagged anomaly to `metric_anomaly_history` so admins
can see when a metric has been "abnormal for 3 days running", not just
"abnormal today". Idempotent upserts keyed on `(day, metric, kind, id)`
so re-runs of the detector on the same day update-in-place rather than
duplicate rows.

Two flavours of streak are computed:

  • `any_streak`         — consecutive days flagged in ANY direction
                          ("how many days has TFHL been abnormal?")
  • `directional_streak` — consecutive days flagged in the SAME
                          direction as today ("how many days has
                          trades_executed been spiking?")

Both walk backwards from the most recent flagged day for that
(metric, kind, id), so a metric that hasn't been touched today but was
flagged yesterday still surfaces its historical streak accurately.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Iterable

logger = logging.getLogger(__name__)


async def _ensure_indexes(db):
    try:
        await db.metric_anomaly_history.create_index(
            [("day", 1), ("metric", 1), ("kind", 1), ("id", 1)],
            name="metric_anomaly_history_key",
            unique=True,
        )
        await db.metric_anomaly_history.create_index(
            [("metric", 1), ("kind", 1), ("id", 1), ("day", -1)],
            name="metric_anomaly_history_lookup",
        )
    except Exception as e:
        logger.debug(f"metric_anomaly_history index create skipped: {e}")


async def persist_anomalies(db, anomalies: Iterable[dict], today: str) -> int:
    """Idempotently persist every flagged anomaly row for `today`.
    Returns the number of docs upserted."""
    await _ensure_indexes(db)
    now_iso = datetime.now(timezone.utc).isoformat()
    upserted = 0
    for a in anomalies:
        metric = a.get("metric")
        kind = a.get("kind")
        rid = a.get("id")
        if not (metric and kind and rid):
            continue
        await db.metric_anomaly_history.update_one(
            {"day": today, "metric": metric, "kind": kind, "id": rid},
            {"$set": {
                "day": today, "metric": metric, "kind": kind, "id": rid,
                "name": a.get("name") or "?",
                "today_count": int(a.get("today_count") or 0),
                "mean": float(a.get("mean") or 0.0),
                "stddev": float(a.get("stddev") or 0.0),
                "sigma": a.get("sigma"),
                "direction": a.get("direction"),
                "delta": float(a.get("delta") or 0.0),
                "detected_at": now_iso,
            }},
            upsert=True,
        )
        upserted += 1
    return upserted


async def _walk_streak(db, metric: str, kind: str, rid: str, today: str,
                        same_direction: str | None = None) -> int:
    """Walk backwards from `today` counting consecutive flagged days.
    If `same_direction` is provided, only days matching that direction
    count."""
    query: dict = {
        "metric": metric, "kind": kind, "id": rid,
        "day": {"$lte": today},
    }
    docs = await db.metric_anomaly_history.find(
        query, {"day": 1, "direction": 1}
    ).sort("day", -1).limit(365).to_list(365)

    if not docs:
        return 0

    # Build day -> direction map for quick lookup.
    by_day: dict[str, str] = {d["day"]: d.get("direction") for d in docs}
    if today not in by_day:
        return 0

    streak = 0
    cursor = datetime.fromisoformat(today).date()
    while True:
        d = cursor.isoformat()
        if d not in by_day:
            break
        if same_direction is not None and by_day[d] != same_direction:
            break
        streak += 1
        cursor = cursor - timedelta(days=1)
    return streak


async def enrich_with_streaks(db, anomalies: list[dict], today: str) -> list[dict]:
    """Add `any_streak` + `directional_streak` fields to each anomaly."""
    for a in anomalies:
        metric = a.get("metric")
        kind = a.get("kind")
        rid = a.get("id")
        direction = a.get("direction")
        if not (metric and kind and rid):
            a["any_streak"] = 0
            a["directional_streak"] = 0
            continue
        a["any_streak"] = await _walk_streak(db, metric, kind, rid, today)
        a["directional_streak"] = await _walk_streak(
            db, metric, kind, rid, today, same_direction=direction
        )
    return anomalies


async def top_ongoing_streaks(
    db,
    min_streak: int = 2,
    limit: int = 20,
    max_lookback_days: int = 365,
    recent_end_window_days: int = 2,
) -> list[dict]:
    """Rank (metric, kind, id) buckets by the length of their most-recent
    consecutive-day streak, filtering to buckets whose streak ended
    within `recent_end_window_days` of calendar today AND is at least
    `min_streak` days long.

    For every distinct (metric, kind, id) with at least one row in the
    last `max_lookback_days`, walk the tail backwards.
    """
    now = datetime.now(timezone.utc)
    cutoff = (now - timedelta(days=max_lookback_days)).date().isoformat()
    recent_days = {
        (now - timedelta(days=i)).date().isoformat()
        for i in range(max(1, int(recent_end_window_days)))
    }

    # Distinct combos with recent activity.
    combos: list[dict] = await db.metric_anomaly_history.aggregate([
        {"$match": {"day": {"$gte": cutoff}}},
        {"$group": {
            "_id": {"metric": "$metric", "kind": "$kind", "id": "$id"},
            "latest_day": {"$max": "$day"},
            "latest_name": {"$last": "$name"},
        }},
    ]).to_list(None)

    results: list[dict] = []
    for c in combos:
        latest = c.get("latest_day")
        if latest not in recent_days:
            continue
        k = c["_id"]
        any_streak = await _walk_streak(
            db, k["metric"], k["kind"], k["id"], latest
        )
        if any_streak < min_streak:
            continue
        # Direction on the latest flagged day
        latest_doc = await db.metric_anomaly_history.find_one(
            {"metric": k["metric"], "kind": k["kind"], "id": k["id"], "day": latest}
        )
        latest_direction = (latest_doc or {}).get("direction")
        directional_streak = await _walk_streak(
            db, k["metric"], k["kind"], k["id"], latest,
            same_direction=latest_direction,
        )
        results.append({
            "metric": k["metric"],
            "kind": k["kind"],
            "id": k["id"],
            "name": (latest_doc or {}).get("name") or c.get("latest_name") or "?",
            "any_streak": any_streak,
            "directional_streak": directional_streak,
            "latest_day": latest,
            "latest_direction": latest_direction,
            "latest_sigma": (latest_doc or {}).get("sigma"),
            "latest_delta": (latest_doc or {}).get("delta"),
        })

    results.sort(
        key=lambda r: (r["any_streak"], r["directional_streak"]),
        reverse=True,
    )
    return results[:limit]
