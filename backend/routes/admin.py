"""Site-admin endpoints — extracted from server.py (iter 115).

Endpoints:
    POST /api/admin/snapshot-ownership — manually trigger an ownership snapshot
    GET  /api/admin/health-deep        — per-route latency + error rates +
                                         DB / worker liveness (iter 116)
"""
from __future__ import annotations

import asyncio
import os
import time

from fastapi import APIRouter, HTTPException, Query, Request

from metrics import snapshot as _metrics_snapshot


router = APIRouter()
_deps: dict = {}


def setup(deps: dict) -> None:
    _deps.update(deps)


def _db(): return _deps["db"]
async def _get_user(request): return await _deps["get_current_user"](request)


def _is_site_admin(user: dict) -> bool:
    admin_email = os.environ.get("ADMIN_EMAIL", "admin@dynastydreams.com")
    return user.get("email") == admin_email


@router.post("/admin/snapshot-ownership")
async def admin_snapshot_ownership(request: Request):
    """Site-admin trigger to capture an ownership snapshot RIGHT NOW.

    Useful when site operators want the % Change column to populate before
    the natural 24h tick fires. Auth: only the user with email ==
    ADMIN_EMAIL can call this.
    """
    user = await _get_user(request)
    if not _is_site_admin(user):
        raise HTTPException(status_code=403, detail="Site admin only")
    from ownership_snapshot_worker import snapshot_once
    return await snapshot_once(_db())


@router.get("/admin/health-deep")
async def admin_health_deep(
    request: Request,
    top: int = Query(25, ge=1, le=200, description="Limit routes returned (slowest first by p95)"),
):
    """Deep health probe surfacing per-route latency + error rates so the
    admin page can spot which endpoint is dragging before users feel it.

    Returns
    -------
    {
      "ok": bool,                # all probes green
      "checked_at": ISO,
      "service": {
        "started_at": ISO,
        "uptime_seconds": float,
        "total_requests": int,
        "total_errors": int,
        "error_rate_pct": float,
      },
      "database": {
        "alive": bool,
        "ping_ms": float|None,
        "error": str|None,
      },
      "workers": {
        "live_scoring": bool,
        "ownership_snapshot": bool,
        "tbd_deadline": bool,
      },
      "routes": [ {method, route, count, error_count, error_rate_pct,
                   avg_latency_ms, p50_latency_ms, p95_latency_ms,
                   max_latency_ms, last_status, last_seen_at}, ... ]
    }

    Auth: site admin only.
    """
    user = await _get_user(request)
    if not _is_site_admin(user):
        raise HTTPException(status_code=403, detail="Site admin only")

    # ── DB liveness: motor admin.command("ping") with a short timeout ──
    db_info: dict = {"alive": False, "ping_ms": None, "error": None}
    try:
        t0 = time.perf_counter()
        await asyncio.wait_for(_db().command("ping"), timeout=2.0)
        db_info["alive"] = True
        db_info["ping_ms"] = round((time.perf_counter() - t0) * 1000.0, 2)
    except Exception as e:
        db_info["error"] = str(e)

    # ── Background worker liveness (set in server.py startup hook) ──
    fastapi_state = request.app.state
    workers = {
        "live_scoring": _task_alive(getattr(fastapi_state, "live_scoring_task", None)),
        "ownership_snapshot": _task_alive(getattr(fastapi_state, "ownership_snapshot_task", None)),
        "tbd_deadline": _task_alive(getattr(fastapi_state, "tbd_deadline_task", None)),
    }

    snap = _metrics_snapshot(top_n=top)
    ok = db_info["alive"] and all(workers.values())

    return {
        "ok": ok,
        "checked_at": _now_iso(),
        "service": {
            "started_at": snap["started_at"],
            "uptime_seconds": snap["uptime_seconds"],
            "total_requests": snap["total_requests"],
            "total_errors": snap["total_errors"],
            "error_rate_pct": snap["error_rate_pct"],
        },
        "database": db_info,
        "workers": workers,
        "routes": snap["routes"],
    }


# ─── Helpers ─────────────────────────────────────────────────────────


def _task_alive(task) -> bool:
    """An asyncio task is 'alive' if it exists and isn't done/cancelled."""
    if task is None:
        return False
    try:
        return not task.done()
    except Exception:
        return False


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
