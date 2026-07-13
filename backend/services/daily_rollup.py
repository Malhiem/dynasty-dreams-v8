"""Iter 232N.55 — Generic Daily Rollup Framework.

Generalises the pattern established in 232N.54's
`commissioner_activity_rollup.py` so new metrics can be plugged in
without duplicating the loop / index / prune / upsert plumbing.

Storage: single collection `daily_metrics` with docs shaped:
    {
      _id: ObjectId,
      day: "2026-07-08",              # ISO date (UTC)
      metric: "commissioner_activity" # canonical metric key
              | "trades_executed"
              | "waiver_claims"
              | ...
      kind:   "league" | "commissioner" | "team" | ...
      id:     "<league_id / user_id / team_id>",
      name:   "<display name>",
      count:  int,                    # main value
      breakdown: {                    # optional per-sub-type counts
        undos: int,
        pings: int,
        ...
      },
      updated_at: ISO,
    }

Registration model: each metric registers a `MetricSpec` with:
  • `key`     — canonical `metric` value stored in the doc
  • `collect` — async function `(db, day: str) -> dict[key_tuple, {"name","count","breakdown"}]`
                where `key_tuple = (kind, id)`

The framework calls `collect()` per day, computes the diff against
existing rows for that (day, metric) slice, and upserts / prunes so
the collection always mirrors the audit-truth for the day.

Idempotent: same-day, same-input → same rows.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable, Iterable

logger = logging.getLogger(__name__)


@dataclass
class MetricSpec:
    key: str
    collect: Callable[[object, str], Awaitable[dict]]
    description: str = ""


_REGISTRY: dict[str, MetricSpec] = {}


def register_metric(spec: MetricSpec) -> None:
    _REGISTRY[spec.key] = spec


def registered_metrics() -> list[MetricSpec]:
    return list(_REGISTRY.values())


def _day_str(dt: datetime) -> str:
    return dt.date().isoformat()


async def _ensure_indexes(db):
    try:
        await db.daily_metrics.create_index(
            [("day", 1), ("metric", 1), ("kind", 1), ("id", 1)],
            name="daily_metrics_key",
            unique=True,
        )
        await db.daily_metrics.create_index(
            [("day", 1), ("metric", 1), ("kind", 1), ("count", -1)],
            name="daily_metrics_leaderboard",
        )
    except Exception as e:
        logger.debug(f"daily_metrics index create skipped: {e}")


async def rollup_metric_day(db, metric: MetricSpec, day: str) -> dict:
    """Roll up ONE metric for ONE day. Returns count of upserted rows."""
    buckets = await metric.collect(db, day)  # dict[(kind, id)] -> {name, count, breakdown}
    now_iso = datetime.now(timezone.utc).isoformat()

    # Upsert everything the collector returned.
    upserted = 0
    kinds_seen: dict[str, set] = {}
    for (kind, rid), agg in buckets.items():
        if not rid:
            continue
        await db.daily_metrics.update_one(
            {"day": day, "metric": metric.key, "kind": kind, "id": rid},
            {"$set": {
                "day": day, "metric": metric.key, "kind": kind, "id": rid,
                "name": agg.get("name") or "?",
                "count": int(agg.get("count") or 0),
                "breakdown": agg.get("breakdown") or {},
                "updated_at": now_iso,
            }},
            upsert=True,
        )
        kinds_seen.setdefault(kind, set()).add(rid)
        upserted += 1

    # Prune stale rows for (day, metric) — anything not in `buckets`.
    # Grouped by `kind` so we don't cross-prune between kinds.
    kinds_touched = set(kinds_seen.keys())
    async for existing in db.daily_metrics.find(
        {"day": day, "metric": metric.key}, {"kind": 1, "id": 1}
    ):
        if existing.get("kind") not in kinds_touched:
            # No collector output for this kind at all today —
            # safest to leave alone (a legitimate zero-day for this
            # kind, e.g. no chat messages today wouldn't imply the
            # metric never runs for `commissioner` kind).
            continue
        if existing.get("id") not in kinds_seen.get(existing.get("kind"), set()):
            await db.daily_metrics.delete_one({"_id": existing["_id"]})

    return {"metric": metric.key, "day": day, "upserted": upserted}


async def run_all(db, days_back: Iterable[int] = (0, 1)) -> dict:
    """Roll every registered metric across the given days."""
    await _ensure_indexes(db)
    now = datetime.now(timezone.utc)
    reports = []
    for delta in days_back:
        day = _day_str(now - timedelta(days=int(delta)))
        for spec in _REGISTRY.values():
            try:
                r = await rollup_metric_day(db, spec, day)
                reports.append(r)
            except Exception as e:
                logger.error(f"rollup_metric_day({spec.key}, {day}) failed: {e}")
    return {"finished_at": now.isoformat(), "reports": reports}


async def daily_rollup_loop(
    db,
    interval_seconds: int = 1800,
    startup_backfill_days: int = 7,
):
    """Single loop that drives EVERY registered metric."""
    # Register the built-ins on first entry so plumbing is centralised.
    _register_builtins()

    try:
        report = await run_all(db, days_back=list(range(startup_backfill_days)))
        await db.daily_rollup_runs.update_one(
            {"_id": "latest"},
            {"$set": {"_id": "latest", "startup": True, **report}},
            upsert=True,
        )
        logger.info(
            f"daily_rollup startup: {len(_REGISTRY)} metrics × {startup_backfill_days} days = "
            f"{len(report['reports'])} rollups"
        )
    except Exception as e:
        logger.error(f"daily_rollup startup failed: {e}")

    while True:
        try:
            report = await run_all(db)
            await db.daily_rollup_runs.update_one(
                {"_id": "latest"},
                {"$set": {"_id": "latest", "startup": False, **report}},
                upsert=True,
            )
        except Exception as e:
            logger.error(f"daily_rollup tick failed: {e}")
        await asyncio.sleep(interval_seconds)


# ─── Built-in metrics ─────────────────────────────────────────────


async def _collect_commissioner_activity(db, day: str) -> dict:
    """Reuse the 232N.54 rollup logic under the generic framework —
    now the `commissioner_activity` metric flows through the same
    `daily_metrics` collection, but the legacy
    `commissioner_activity_daily` collection stays populated too (see
    `services/commissioner_activity_rollup.py`) for backward compat
    with the existing `/admin/commissioner-activity` endpoint."""
    from bson import ObjectId
    from datetime import datetime as _dt, timezone as _tz, timedelta as _td

    d = _dt.fromisoformat(day).replace(tzinfo=_tz.utc)
    start_iso = d.isoformat()
    end_iso = (d + _td(days=1)).isoformat()

    buckets: dict[tuple[str, str], dict] = {}
    name_cache: dict[str, str] = {}

    async def _lname(lid):
        if not lid:
            return None
        if lid in name_cache:
            return name_cache[lid]
        try:
            lg = await db.leagues.find_one({"_id": ObjectId(lid)}, {"name": 1})
        except Exception:
            lg = None
        name_cache[lid] = (lg or {}).get("name") or "(unknown league)"
        return name_cache[lid]

    async def _uname(uid):
        if not uid:
            return None
        if uid in name_cache:
            return name_cache[uid]
        try:
            u = await db.users.find_one(
                {"_id": ObjectId(uid)},
                {"name": 1, "username": 1, "email": 1},
            )
        except Exception:
            u = None
        name_cache[uid] = (
            (u or {}).get("name")
            or (u or {}).get("username")
            or (u or {}).get("email")
            or "?"
        )
        return name_cache[uid]

    def _bump(k, name, sub):
        b = buckets.setdefault(k, {"name": name, "count": 0, "breakdown": {"undos": 0, "pings": 0}})
        b["breakdown"][sub] += 1
        b["count"] += 1

    async for row in db.draft_undo_audit.find({
        "undone_at": {"$gte": start_iso, "$lt": end_iso}
    }):
        lid = row.get("league_id")
        if lid:
            _bump(("league", lid), await _lname(lid), "undos")
        cid = row.get("commissioner_id")
        if cid:
            _bump(("commissioner", cid), row.get("commissioner_name") or await _uname(cid), "undos")

    async for row in db.commissioner_pings.find({
        "created_at": {"$gte": start_iso, "$lt": end_iso}
    }):
        lid = row.get("league_id")
        if lid:
            _bump(("league", lid), await _lname(lid), "pings")
        cid = row.get("commissioner_id")
        if cid:
            _bump(("commissioner", cid), await _uname(cid), "pings")

    return buckets


async def _collect_draft_picks_made(db, day: str) -> dict:
    """New metric enabled by the generic framework: how many picks were
    finalised in each draft on this day. Rolls up per-league so the
    admin dashboard can rank drafts by momentum."""
    from bson import ObjectId
    from datetime import datetime as _dt, timezone as _tz, timedelta as _td

    d = _dt.fromisoformat(day).replace(tzinfo=_tz.utc)
    start_iso = d.isoformat()
    end_iso = (d + _td(days=1)).isoformat()

    buckets: dict[tuple[str, str], dict] = {}
    league_cache: dict[str, str] = {}

    async def _lname(lid):
        if lid in league_cache:
            return league_cache[lid]
        try:
            lg = await db.leagues.find_one({"_id": ObjectId(lid)}, {"name": 1})
        except Exception:
            lg = None
        league_cache[lid] = (lg or {}).get("name") or "(unknown league)"
        return league_cache[lid]

    # `draft.picks[]` is an inline array — no per-pick timestamp on
    # some legacy shapes, so we favour rows in `draft_picks` collection
    # which stamp `picked_at` per pick.
    async for pick in db.draft_picks.find({
        "picked_at": {"$gte": start_iso, "$lt": end_iso},
        "player_id": {"$ne": None},
    }):
        lid = pick.get("league_id")
        if not lid:
            continue
        k = ("league", lid)
        b = buckets.setdefault(k, {
            "name": await _lname(lid), "count": 0,
            "breakdown": {"auto_picked": 0, "manual": 0},
        })
        b["count"] += 1
        if pick.get("auto_picked"):
            b["breakdown"]["auto_picked"] += 1
        else:
            b["breakdown"]["manual"] += 1

    return buckets


def _register_builtins():
    if "commissioner_activity" not in _REGISTRY:
        register_metric(MetricSpec(
            key="commissioner_activity",
            collect=_collect_commissioner_activity,
            description="Pick undos + offline-manager pings per league / commissioner",
        ))
    if "draft_picks_made" not in _REGISTRY:
        register_metric(MetricSpec(
            key="draft_picks_made",
            collect=_collect_draft_picks_made,
            description="Draft picks executed per day (auto vs manual)",
        ))
