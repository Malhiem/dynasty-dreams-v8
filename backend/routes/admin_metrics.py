"""Platform administrator daily metrics and anomaly read endpoints."""
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, HTTPException, Request

router = APIRouter()
_deps = {}


def setup(deps):
    _deps.update(deps)


def _db():
    return _deps["db"]


async def _get_user(request):
    return await _deps["get_current_user"](request)


# ─── Iter 232N.55 — Generic daily metrics endpoint ──────────────────────


@router.get("/admin/daily-metrics")
async def read_daily_metrics(
    request: Request,
    metric: str,
    kind: str = "league",
    days: int = 30,
    limit: int = 20,
):
    """Platform-admin-only. Reads the generic `daily_metrics` collection
    populated by the 232N.55 rollup framework. Response includes a
    leaderboard (top-N by summed count), a per-day trend array, and
    grand totals + breakdown.
    """
    user = await _get_user(request)
    if not user or user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Platform admin only")

    db = _db()
    days = max(1, min(int(days), 365))
    limit = max(1, min(int(limit), 100))
    now = datetime.now(timezone.utc)
    cutoff_day = (now - timedelta(days=days)).date().isoformat()

    leaderboard: dict[str, dict] = {}
    trend_by_day: dict[str, dict] = {}
    all_breakdown: dict[str, int] = {}
    total_count = 0
    async for row in db.daily_metrics.find({
        "day": {"$gte": cutoff_day},
        "metric": metric,
        "kind": kind,
    }):
        rid = row.get("id")
        n = int(row.get("count") or 0)
        bd = row.get("breakdown") or {}
        if rid:
            b = leaderboard.setdefault(
                rid, {"id": rid, "name": row.get("name") or "?", "count": 0, "breakdown": {}}
            )
            b["count"] += n
            for k, v in bd.items():
                b["breakdown"][k] = b["breakdown"].get(k, 0) + int(v or 0)
        day = row.get("day")
        if day:
            t = trend_by_day.setdefault(day, {"day": day, "count": 0, "breakdown": {}})
            t["count"] += n
            for k, v in bd.items():
                t["breakdown"][k] = t["breakdown"].get(k, 0) + int(v or 0)
        total_count += n
        for k, v in bd.items():
            all_breakdown[k] = all_breakdown.get(k, 0) + int(v or 0)

    sorted_leaderboard = sorted(
        leaderboard.values(), key=lambda x: x["count"], reverse=True
    )[:limit]

    trend: list[dict] = []
    for i in range(days):
        d = (now - timedelta(days=days - 1 - i)).date().isoformat()
        trend.append(trend_by_day.get(d) or {"day": d, "count": 0, "breakdown": {}})

    return {
        "checked_at": now.isoformat(),
        "metric": metric,
        "kind": kind,
        "window_days": days,
        "leaderboard": sorted_leaderboard,
        "trend": trend,
        "totals": {"count": total_count, "breakdown": all_breakdown},
    }


@router.get("/admin/daily-metrics/registered")
async def list_registered_metrics(request: Request):
    """Discovery endpoint — lists every metric the rollup framework
    knows about. Lets the admin UI populate a metric-picker dropdown
    without hard-coding the list.

    Iter 232N.56 — Enriched with `kinds` (distinct bucketing dimensions
    observed in `daily_metrics` per metric) so the Metric Explorer UI
    can populate a kind picker without a second round-trip, and with
    `last_seen_day` so admins can spot metrics whose rollup has stalled.
    """
    user = await _get_user(request)
    if not user or user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Platform admin only")

    from services.daily_rollup import registered_metrics, _register_builtins
    _register_builtins()

    db = _db()
    metrics_out = []
    for m in registered_metrics():
        kinds = await db.daily_metrics.distinct("kind", {"metric": m.key})
        # Sample one recent doc to expose last-seen bucket count for
        # freshness signalling in the UI.
        last_day = None
        recent = await db.daily_metrics.find(
            {"metric": m.key}, {"day": 1}
        ).sort("day", -1).limit(1).to_list(1)
        if recent:
            last_day = recent[0].get("day")
        metrics_out.append({
            "key": m.key,
            "description": m.description,
            "kinds": sorted(kinds) if kinds else [],
            "last_seen_day": last_day,
        })
    return {"metrics": metrics_out}


# ─── Iter 232N.57 — Anomaly detection endpoint ──────────────────────────


@router.get("/admin/metric-anomalies")
async def read_metric_anomalies(
    request: Request,
    metric: str | None = None,
    kind: str | None = None,
    threshold_sigma: float = 2.0,
    days: int = 30,
    min_samples: int = 5,
):
    """Platform-admin-only. Computes >Nσ deviations (both spikes and
    dips) for the latest observed day of each metric relative to the
    prior `days` days. When `metric` is omitted, sweeps every
    registered metric and returns a global feed of what needs
    attention today."""
    user = await _get_user(request)
    if not user or user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Platform admin only")

    db = _db()
    threshold_sigma = max(0.5, min(float(threshold_sigma), 6.0))
    days = max(3, min(int(days), 365))
    min_samples = max(1, min(int(min_samples), days))

    from services.anomaly_detector import (
        detect_metric_anomalies,
        detect_all_anomalies,
    )
    from services.anomaly_history import persist_anomalies, enrich_with_streaks

    if metric:
        r = await detect_metric_anomalies(
            db, metric,
            kind=kind,
            threshold_sigma=threshold_sigma,
            window_days=days,
            min_samples=min_samples,
        )
        # Persist + enrich (232N.58) — same shape as detect_all path.
        today = r.get("today")
        if today and r.get("anomalies"):
            await persist_anomalies(db, r["anomalies"], today)
            await enrich_with_streaks(db, r["anomalies"], today)
        return r

    return await detect_all_anomalies(
        db,
        threshold_sigma=threshold_sigma,
        window_days=days,
        min_samples=min_samples,
    )


# ─── Iter 232N.58 — Ongoing streaks endpoint ────────────────────────────


@router.get("/admin/anomaly-streaks")
async def read_anomaly_streaks(
    request: Request,
    min_streak: int = 2,
    limit: int = 20,
    max_lookback_days: int = 30,
):
    """Platform-admin-only. Returns the top ongoing anomaly streaks —
    (metric, kind, id) buckets that have been continuously flagged for
    at least `min_streak` consecutive days ending within
    `max_lookback_days`. Read-only against the `metric_anomaly_history`
    collection populated by the detector.
    """
    user = await _get_user(request)
    if not user or user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Platform admin only")

    db = _db()
    min_streak = max(1, min(int(min_streak), 90))
    limit = max(1, min(int(limit), 100))
    max_lookback_days = max(1, min(int(max_lookback_days), 365))

    from services.anomaly_history import top_ongoing_streaks
    streaks = await top_ongoing_streaks(
        db, min_streak=min_streak, limit=limit,
        max_lookback_days=max(30, max_lookback_days),
        recent_end_window_days=max_lookback_days,
    )
    return {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "min_streak": min_streak,
        "max_lookback_days": max_lookback_days,
        "count": len(streaks),
        "streaks": streaks,
    }
