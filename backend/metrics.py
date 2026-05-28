"""In-memory per-route request metrics — drives /api/admin/health-deep.

Lightweight (no Prometheus / OTel dependency). Recorded values are scoped
to the current process; multi-worker deployments would see only one
worker's slice. For our supervisor + single-uvicorn-worker setup that's
exactly what we want.

Per-route bucket:
    count, error_count, status_4xx_count
    sum_latency_ms, max_latency_ms
    last_seen_at (ISO)
    samples (collections.deque, last 200 latencies → p50 / p95)

Aggregated view:
    record(method, route_template, status, latency_ms)
    snapshot() → {
        uptime_seconds, started_at,
        total_requests, total_errors, error_rate_pct,
        routes: [{method, route, count, error_count, ...}],
    }

Route key is the ROUTE TEMPLATE (e.g. /api/teams/{team_id}/dead-cap) rather
than the concrete path so that {team_id} variations collapse into one
bucket — exactly what an admin wants to see.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from datetime import datetime, timezone
from typing import Optional


_LOCK = threading.Lock()
_BUCKETS: dict[tuple[str, str], dict] = {}
_STARTED_AT = time.monotonic()
_STARTED_AT_ISO = datetime.now(timezone.utc).isoformat()
_SAMPLE_WINDOW = 200  # rolling latency samples per route — enough for p50/p95


def _percentile(values: list[float], pct: float) -> float:
    """Cheap nearest-rank percentile. `values` is small (≤200) so sorting
    on every call is fine; trading a tiny CPU hit for code simplicity."""
    if not values:
        return 0.0
    s = sorted(values)
    k = max(0, min(len(s) - 1, int(round((pct / 100.0) * (len(s) - 1)))))
    return s[k]


def record(method: str, route: str, status: int, latency_ms: float) -> None:
    """Append one observation. Safe to call from FastAPI middleware."""
    key = (method.upper(), route or "<unknown>")
    is_5xx = status >= 500
    is_4xx = 400 <= status < 500
    with _LOCK:
        b = _BUCKETS.get(key)
        if b is None:
            b = {
                "count": 0,
                "error_count": 0,
                "status_4xx_count": 0,
                "sum_latency_ms": 0.0,
                "max_latency_ms": 0.0,
                "last_seen_at": None,
                "last_status": None,
                "samples": deque(maxlen=_SAMPLE_WINDOW),
            }
            _BUCKETS[key] = b
        b["count"] += 1
        if is_5xx:
            b["error_count"] += 1
        if is_4xx:
            b["status_4xx_count"] += 1
        b["sum_latency_ms"] += latency_ms
        if latency_ms > b["max_latency_ms"]:
            b["max_latency_ms"] = latency_ms
        b["last_seen_at"] = datetime.now(timezone.utc).isoformat()
        b["last_status"] = status
        b["samples"].append(latency_ms)


def snapshot(top_n: Optional[int] = None) -> dict:
    """Return a JSON-safe snapshot of the current metrics state."""
    with _LOCK:
        rows = []
        total_requests = 0
        total_errors = 0
        for (method, route), b in _BUCKETS.items():
            count = b["count"]
            samples = list(b["samples"])
            avg = (b["sum_latency_ms"] / count) if count else 0.0
            rows.append({
                "method": method,
                "route": route,
                "count": count,
                "error_count": b["error_count"],
                "status_4xx_count": b["status_4xx_count"],
                "error_rate_pct": round((b["error_count"] / count) * 100, 2) if count else 0.0,
                "avg_latency_ms": round(avg, 2),
                "p50_latency_ms": round(_percentile(samples, 50), 2),
                "p95_latency_ms": round(_percentile(samples, 95), 2),
                "max_latency_ms": round(b["max_latency_ms"], 2),
                "last_status": b["last_status"],
                "last_seen_at": b["last_seen_at"],
            })
            total_requests += count
            total_errors += b["error_count"]

    # Default: slowest by p95 first so the slowest endpoints are obvious.
    rows.sort(key=lambda r: r["p95_latency_ms"], reverse=True)
    if top_n is not None:
        rows = rows[:top_n]

    return {
        "started_at": _STARTED_AT_ISO,
        "uptime_seconds": round(time.monotonic() - _STARTED_AT, 1),
        "total_requests": total_requests,
        "total_errors": total_errors,
        "error_rate_pct": round((total_errors / total_requests) * 100, 2) if total_requests else 0.0,
        "routes": rows,
    }


def reset() -> None:
    """Test helper — clears all recorded metrics."""
    with _LOCK:
        _BUCKETS.clear()
