"""Iter 232N.54 — Commissioner Activity Rollup Worker.

Pre-computes daily aggregates from `draft_undo_audit` +
`commissioner_pings` into `commissioner_activity_daily` so the admin
panel's aggregate stats become a single indexed read instead of a
two-full-collection scan per refresh.

Schema of `commissioner_activity_daily`:
    {
      _id: ObjectId,
      day: "2026-07-08",       # ISO date string (UTC)
      kind: "league" | "commissioner",
      id: "<league_id or commissioner_id>",
      name: "<league.name or user display name>",
      undos: int,
      pings: int,
      total: int,
      updated_at: ISO string,
    }

Uniqueness enforced by the compound query in each upsert
(day, kind, id). On first run, the worker also creates the compound
index for fast admin-panel reads.

The rollup loop runs every 30 minutes to keep TODAY current + refresh
YESTERDAY (idempotent — same day rolled twice produces the same
counts because we `$set` totals, not `$inc`).

Rebuilds the last 7 days on startup (guards against a preview-env
hibernation gap that missed a rollup — very cheap since totals are
just re-derived from the audit collections).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Iterable

from bson import ObjectId

logger = logging.getLogger(__name__)

# Cadence: fast enough that today's counts feel live, slow enough that
# writes don't hammer Mongo. 30 min ≈ 48 rollups/day per bucket.
ROLLUP_INTERVAL_SECONDS = 1800
# Backfill window on startup — safety net against missed ticks.
STARTUP_BACKFILL_DAYS = 7


def _day_str(dt: datetime) -> str:
    return dt.date().isoformat()


def _day_bounds_iso(day: str) -> tuple[str, str]:
    """Return (start_iso, end_iso_exclusive) for `day` (UTC)."""
    d = datetime.fromisoformat(day).replace(tzinfo=timezone.utc)
    return d.isoformat(), (d + timedelta(days=1)).isoformat()


async def _ensure_indexes(db):
    try:
        await db.commissioner_activity_daily.create_index(
            [("day", 1), ("kind", 1), ("id", 1)],
            name="daily_bucket_key",
            unique=True,
        )
        await db.commissioner_activity_daily.create_index(
            [("day", 1), ("kind", 1), ("total", -1)],
            name="daily_bucket_leaderboard",
        )
    except Exception as e:
        logger.debug(f"commissioner_activity_rollup index create skipped: {e}")


async def _resolve_league_name(db, league_id: str, cache: dict) -> str:
    if league_id in cache:
        return cache[league_id]
    try:
        lg = await db.leagues.find_one({"_id": ObjectId(league_id)}, {"name": 1})
    except Exception:
        lg = None
    name = (lg or {}).get("name") or "(unknown league)"
    cache[league_id] = name
    return name


async def _resolve_user_name(db, user_id: str, cache: dict) -> str:
    if user_id in cache:
        return cache[user_id]
    try:
        u = await db.users.find_one(
            {"_id": ObjectId(user_id)},
            {"name": 1, "username": 1, "email": 1},
        )
    except Exception:
        u = None
    name = (
        (u or {}).get("name")
        or (u or {}).get("username")
        or (u or {}).get("email")
        or "Commissioner"
    )
    cache[user_id] = name
    return name


async def rollup_day(db, day: str) -> dict:
    """Recompute `commissioner_activity_daily` rows for a single day.

    Returns `{day, league_buckets, commissioner_buckets}` — the number
    of upserts written to each bucket kind.
    """
    start_iso, end_iso = _day_bounds_iso(day)
    league_agg: dict[str, dict] = {}
    commish_agg: dict[str, dict] = {}
    league_name_cache: dict[str, str] = {}
    user_name_cache: dict[str, str] = {}

    def _bump(bucket: dict, key: str, name: str, kind: str):
        if not key:
            return
        if key not in bucket:
            bucket[key] = {"id": key, "name": name, "undos": 0, "pings": 0, "total": 0}
        if kind == "undo":
            bucket[key]["undos"] += 1
        else:
            bucket[key]["pings"] += 1
        bucket[key]["total"] += 1

    # ─── undos ───
    async for row in db.draft_undo_audit.find({
        "undone_at": {"$gte": start_iso, "$lt": end_iso}
    }):
        lid = row.get("league_id")
        if lid:
            lname = await _resolve_league_name(db, lid, league_name_cache)
            _bump(league_agg, lid, lname, "undo")
        cid = row.get("commissioner_id")
        if cid:
            cname = row.get("commissioner_name") or await _resolve_user_name(db, cid, user_name_cache)
            _bump(commish_agg, cid, cname, "undo")

    # ─── pings ───
    async for row in db.commissioner_pings.find({
        "created_at": {"$gte": start_iso, "$lt": end_iso}
    }):
        lid = row.get("league_id")
        if lid:
            lname = await _resolve_league_name(db, lid, league_name_cache)
            _bump(league_agg, lid, lname, "ping")
        cid = row.get("commissioner_id")
        if cid:
            cname = await _resolve_user_name(db, cid, user_name_cache)
            _bump(commish_agg, cid, cname, "ping")

    updated_iso = datetime.now(timezone.utc).isoformat()

    # ─── Upsert leagues ───
    for lid, agg in league_agg.items():
        await db.commissioner_activity_daily.update_one(
            {"day": day, "kind": "league", "id": lid},
            {"$set": {**agg, "day": day, "kind": "league", "updated_at": updated_iso}},
            upsert=True,
        )
    # ─── Upsert commissioners ───
    for cid, agg in commish_agg.items():
        await db.commissioner_activity_daily.update_one(
            {"day": day, "kind": "commissioner", "id": cid},
            {"$set": {**agg, "day": day, "kind": "commissioner", "updated_at": updated_iso}},
            upsert=True,
        )
    # ─── Prune stale rows (buckets that had activity yesterday but not
    #      today) — otherwise a league that stopped acting today would
    #      still show yesterday's totals in the "today" slice.
    await db.commissioner_activity_daily.delete_many({
        "day": day,
        "kind": "league",
        "id": {"$nin": list(league_agg.keys())},
    })
    await db.commissioner_activity_daily.delete_many({
        "day": day,
        "kind": "commissioner",
        "id": {"$nin": list(commish_agg.keys())},
    })

    return {
        "day": day,
        "league_buckets": len(league_agg),
        "commissioner_buckets": len(commish_agg),
    }


async def run_rollup(db, days_back: Iterable[int] = (0, 1)) -> dict:
    """Roll up N days. Defaults to TODAY and YESTERDAY.

    Idempotent: the same call at 3pm and 3:30pm on the same day
    produces identical rows (we `$set` totals, not `$inc`).
    """
    await _ensure_indexes(db)
    now = datetime.now(timezone.utc)
    reports = []
    for delta in days_back:
        day = _day_str(now - timedelta(days=int(delta)))
        try:
            reports.append(await rollup_day(db, day))
        except Exception as e:
            logger.error(f"rollup_day failed for {day}: {e}")
    return {"finished_at": now.isoformat(), "days": reports}


async def commissioner_activity_rollup_loop(
    db,
    interval_seconds: int = ROLLUP_INTERVAL_SECONDS,
    startup_backfill_days: int = STARTUP_BACKFILL_DAYS,
):
    """Long-running loop. Wire from `server.py` startup like the other
    background workers."""
    # ─── Startup backfill ───────────────────────────────────────
    try:
        backfill = list(range(startup_backfill_days))
        report = await run_rollup(db, days_back=backfill)
        await db.commissioner_activity_rollup_runs.update_one(
            {"_id": "latest"},
            {"$set": {
                "_id": "latest", "startup_backfill": True,
                "backfilled_days": len(backfill),
                "finished_at": report["finished_at"],
                "days_report": report["days"],
            }},
            upsert=True,
        )
        logger.info(
            f"commissioner_activity_rollup startup backfill: "
            f"{len(backfill)} days, {sum(d['league_buckets'] for d in report['days'])} league rows, "
            f"{sum(d['commissioner_buckets'] for d in report['days'])} commissioner rows"
        )
    except Exception as e:
        logger.error(f"commissioner_activity_rollup startup failed: {e}")

    while True:
        try:
            report = await run_rollup(db)
            await db.commissioner_activity_rollup_runs.update_one(
                {"_id": "latest"},
                {"$set": {
                    "_id": "latest", "startup_backfill": False,
                    "finished_at": report["finished_at"],
                    "days_report": report["days"],
                }},
                upsert=True,
            )
        except Exception as e:
            logger.error(f"commissioner_activity_rollup tick failed: {e}")
        await asyncio.sleep(interval_seconds)
