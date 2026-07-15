"""Iter 232N.57 — Anomaly detector on the daily-rollup framework.

Given a metric + kind (or every registered metric), compute per-bucket
mean + population standard deviation over the last `window_days`
excluding the latest observed day, then flag today's row when it
deviates by more than `threshold_sigma`.

Two-directional: `spike` when today > mean + Nσ, `dip` when today <
mean - Nσ. Ignores buckets with fewer than `min_samples` historical
days (otherwise a single-day spike from zero looks infinitely
significant).

Read-only; no writes to Mongo. Intended for direct call from the
`/admin/metric-anomalies` endpoint.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

from services.daily_rollup import registered_metrics, _register_builtins


async def _latest_day(db, metric: str) -> str | None:
    doc = await db.daily_metrics.find(
        {"metric": metric}, {"day": 1}
    ).sort("day", -1).limit(1).to_list(1)
    return doc[0]["day"] if doc else None


def _mean_std(values: list[float]) -> tuple[float, float]:
    n = len(values)
    if n == 0:
        return 0.0, 0.0
    mean = sum(values) / n
    var = sum((v - mean) ** 2 for v in values) / n  # population variance
    return mean, math.sqrt(var)


async def detect_metric_anomalies(
    db,
    metric: str,
    kind: str | None = None,
    threshold_sigma: float = 2.0,
    window_days: int = 30,
    min_samples: int = 5,
) -> dict:
    """Return anomalies for `metric` (all observed kinds if `kind` is
    None). The 'today' baseline is the latest day the metric has any
    rollup rows — so a metric that's been dark for 3 days still gets
    reviewed against its most recent snapshot rather than always
    reporting 'dip'."""
    latest = await _latest_day(db, metric)
    if not latest:
        return {
            "metric": metric,
            "today": None,
            "window_days": window_days,
            "threshold_sigma": threshold_sigma,
            "anomalies": [],
        }

    today_dt = datetime.fromisoformat(latest)
    hist_start = (today_dt - timedelta(days=window_days)).date().isoformat()

    query: dict = {
        "metric": metric,
        "day": {"$gte": hist_start, "$lte": latest},
    }
    if kind:
        query["kind"] = kind

    # Bucket by (kind, id) → {days: {day: count}, name}
    per_bucket: dict[tuple[str, str], dict] = {}
    async for row in db.daily_metrics.find(query):
        k = (row.get("kind") or "?", row.get("id") or "?")
        b = per_bucket.setdefault(k, {"days": {}, "name": row.get("name") or "?"})
        b["days"][row["day"]] = int(row.get("count") or 0)
        # keep name fresh
        b["name"] = row.get("name") or b["name"]

    anomalies: list[dict] = []
    for (bk_kind, bk_id), agg in per_bucket.items():
        days_map = agg["days"]
        today_count = days_map.get(latest, 0)
        hist_counts = [c for d, c in days_map.items() if d != latest]
        if len(hist_counts) < min_samples:
            continue
        mean, std = _mean_std([float(v) for v in hist_counts])
        if std <= 0:
            # No variance in history; a nonzero today reading is
            # noteworthy iff it differs from the flat baseline.
            if today_count != int(mean):
                deviation = float(today_count - mean)
                anomalies.append({
                    "metric": metric,
                    "kind": bk_kind,
                    "id": bk_id,
                    "name": agg["name"],
                    "today_count": today_count,
                    "mean": round(mean, 2),
                    "stddev": 0.0,
                    "sigma": None,  # undefined without variance
                    "direction": "spike" if deviation > 0 else "dip",
                    "delta": round(deviation, 2),
                })
            continue

        sigma = (today_count - mean) / std
        if abs(sigma) >= threshold_sigma:
            anomalies.append({
                "metric": metric,
                "kind": bk_kind,
                "id": bk_id,
                "name": agg["name"],
                "today_count": today_count,
                "mean": round(mean, 2),
                "stddev": round(std, 2),
                "sigma": round(sigma, 2),
                "direction": "spike" if sigma > 0 else "dip",
                "delta": round(today_count - mean, 2),
            })

    # Rank by absolute sigma DESC (most noteworthy first). None-sigma
    # (zero-variance flags) rank after all quantified anomalies.
    def _rank_key(a):
        s = a.get("sigma")
        return (0 if s is not None else 1, -abs(s) if s is not None else 0)

    anomalies.sort(key=_rank_key)
    return {
        "metric": metric,
        "today": latest,
        "window_days": window_days,
        "threshold_sigma": threshold_sigma,
        "anomalies": anomalies,
    }


async def detect_all_anomalies(
    db,
    threshold_sigma: float = 2.0,
    window_days: int = 30,
    min_samples: int = 5,
) -> dict:
    """Sweep every registered metric. Convenience wrapper for the
    'what needs attention today?' admin feed."""
    _register_builtins()
    reports: list[dict] = []
    for spec in registered_metrics():
        r = await detect_metric_anomalies(
            db, spec.key,
            threshold_sigma=threshold_sigma,
            window_days=window_days,
            min_samples=min_samples,
        )
        reports.append(r)

    all_rows: list[dict] = []
    for r in reports:
        all_rows.extend(r["anomalies"])

    # Global rank across metrics.
    def _rank_key(a):
        s = a.get("sigma")
        return (0 if s is not None else 1, -abs(s) if s is not None else 0)
    all_rows.sort(key=_rank_key)

    return {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "threshold_sigma": threshold_sigma,
        "window_days": window_days,
        "min_samples": min_samples,
        "per_metric": reports,
        "top_anomalies": all_rows[:20],
        "totals": {
            "flagged": len(all_rows),
            "spikes": sum(1 for a in all_rows if a["direction"] == "spike"),
            "dips": sum(1 for a in all_rows if a["direction"] == "dip"),
        },
    }
