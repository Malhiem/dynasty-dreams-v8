"""Iter 231y — Worker honours `time_per_pick` + per-day clock window.

Two production bugs surfaced by the TFHL Inaugural Draft incident:

  1. **`pick_time_seconds` vs `time_per_pick` field mismatch**: The
     canonical `create_draft` endpoint writes `time_per_pick` (in
     seconds). The legacy worker only read `pick_time_seconds`, fell
     back to the 60s default, and timed out 4-hour picks after 60s.
     TFHL's `time_per_pick: 14400` was being honoured everywhere
     EXCEPT in the auto-pick worker — so the worker raced through
     hundreds of picks at 60s cadence overnight.

  2. **No time-of-day clock window**: Drafts can configure
     `clock_starts_at` / `clock_stops_at` (HH:MM in `clock_timezone`)
     so the pick clock pauses overnight. The worker ignored these
     and fired auto-picks 24/7. After this fix the worker skips
     drafts whose local time falls outside the configured window.
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.draft_pick_timer_worker import run_once, _is_within_clock_window


def _db():
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[
        os.environ.get("DB_NAME", os.environ["DB_NAME"])
    ]


# ─── Source guards ─────────────────────────────────────────────────


def test_worker_reads_time_per_pick_field():
    from pathlib import Path
    src = Path("/app/backend/services/draft_pick_timer_worker.py").read_text()
    # Must honour `time_per_pick` (canonical) before falling back to
    # the legacy `pick_time_seconds` alias.
    assert "draft.get(\"time_per_pick\")" in src
    assert "draft.get(\"pick_time_seconds\")" in src
    # Confirm ORDERING — time_per_pick must come FIRST in the `or` chain.
    idx_tpp = src.index('draft.get("time_per_pick")')
    idx_pts = src.index('draft.get("pick_time_seconds")')
    assert idx_tpp < idx_pts, "time_per_pick must be read before pick_time_seconds"


def test_worker_honours_clock_window():
    from pathlib import Path
    src = Path("/app/backend/services/draft_pick_timer_worker.py").read_text()
    assert "async def _is_within_clock_window" in src
    assert "clock_starts_at" in src
    assert "clock_stops_at" in src
    assert "clock_timezone" in src
    # Must support windows that cross midnight (e.g. 21:00–06:00).
    assert "Window crosses midnight" in src


# ─── Functional tests for _is_within_clock_window ──────────────────


@pytest.mark.asyncio
async def test_clock_window_no_config_runs_24_7():
    """No `clock_starts_at` / `clock_stops_at` → always returns True
    (legacy 24/7 default; no regression for drafts without a window)."""
    now = datetime.now(timezone.utc)
    assert await _is_within_clock_window({}, now) is True
    assert await _is_within_clock_window({"clock_timezone": "America/New_York"}, now) is True


@pytest.mark.asyncio
async def test_clock_window_same_day_inside():
    """9am-9pm UTC, current time 2pm UTC → inside → True."""
    now = datetime(2026, 6, 28, 14, 0, 0, tzinfo=timezone.utc)
    draft = {"clock_starts_at": "09:00", "clock_stops_at": "21:00", "clock_timezone": "UTC"}
    assert await _is_within_clock_window(draft, now) is True


@pytest.mark.asyncio
async def test_clock_window_same_day_outside():
    """9am-9pm UTC, current time 1am UTC → outside → False (the TFHL
    1am EST scenario)."""
    now = datetime(2026, 6, 28, 1, 0, 0, tzinfo=timezone.utc)
    draft = {"clock_starts_at": "09:00", "clock_stops_at": "21:00", "clock_timezone": "UTC"}
    assert await _is_within_clock_window(draft, now) is False


@pytest.mark.asyncio
async def test_clock_window_overnight_window_inside():
    """21:00-06:00 UTC, current time 2am UTC → inside (overnight) → True."""
    now = datetime(2026, 6, 28, 2, 0, 0, tzinfo=timezone.utc)
    draft = {"clock_starts_at": "21:00", "clock_stops_at": "06:00", "clock_timezone": "UTC"}
    assert await _is_within_clock_window(draft, now) is True


@pytest.mark.asyncio
async def test_clock_window_overnight_window_outside():
    """21:00-06:00 UTC, current time 12pm UTC → outside (daytime) → False."""
    now = datetime(2026, 6, 28, 12, 0, 0, tzinfo=timezone.utc)
    draft = {"clock_starts_at": "21:00", "clock_stops_at": "06:00", "clock_timezone": "UTC"}
    assert await _is_within_clock_window(draft, now) is False


@pytest.mark.asyncio
async def test_clock_window_honours_timezone():
    """9am-9pm America/New_York, current time 02:00 UTC = 22:00 EDT
    (DST in June) → outside → False."""
    now = datetime(2026, 6, 28, 2, 0, 0, tzinfo=timezone.utc)
    draft = {
        "clock_starts_at": "09:00", "clock_stops_at": "21:00",
        "clock_timezone": "America/New_York",
    }
    assert await _is_within_clock_window(draft, now) is False


# ─── End-to-end functional: run_once respects time_per_pick + window ───


async def _seed_draft(db, *, started_at, time_per_pick=None, pick_time_seconds=None,
                       clock_starts_at=None, clock_stops_at=None, clock_timezone=None):
    suffix = uuid.uuid4().hex[:8]
    uid = ObjectId()
    await db.users.insert_one({"_id": uid, "email": f"i231y_{suffix}@example.com",
                                "username": f"i231y_{suffix}"[:24], "name": f"i231y"})
    league_id = ObjectId()
    await db.leagues.insert_one({"_id": league_id, "name": f"i231y League {suffix}",
                                  "commissioner_id": str(uid), "status": "active"})
    team_ids = []
    abbrs = []
    team_map = {}
    for i in range(3):
        t_id = ObjectId()
        abbr = f"T{i+1}"
        await db.teams.insert_one({"_id": t_id, "name": f"i231y Team {i+1}",
                                    "league_id": str(league_id), "owner_id": str(uid),
                                    "roster": [], "draft_queue": []})
        team_ids.append(str(t_id))
        abbrs.append(abbr)
        team_map[abbr] = {"id": str(t_id), "name": f"i231y Team {i+1}"}
    pids = []
    for i in range(3):
        p_id = ObjectId()
        await db.players.insert_one({"_id": p_id, "nhl_id": f"i231y-{p_id}",
                                      "name": f"i231y Player {i+1}", "position": "C",
                                      "team": "TOR", "team_name": "Toronto",
                                      "points": 100 - i, "games_played": 82, "player_type": "skater"})
        pids.append(str(p_id))
    draft_id = ObjectId()
    doc = {
        "_id": draft_id, "league_id": str(league_id), "name": "i231y Draft",
        "status": "active", "draft_type": "snake", "snake_draft": True,
        "total_rounds": 2, "current_pick": 1,
        "team_abbrs": abbrs, "team_map": team_map, "picks": [], "chat_messages": [],
        "current_pick_started_at": started_at, "started_at": started_at,
    }
    if time_per_pick is not None: doc["time_per_pick"] = time_per_pick
    if pick_time_seconds is not None: doc["pick_time_seconds"] = pick_time_seconds
    if clock_starts_at is not None: doc["clock_starts_at"] = clock_starts_at
    if clock_stops_at is not None: doc["clock_stops_at"] = clock_stops_at
    if clock_timezone is not None: doc["clock_timezone"] = clock_timezone
    await db.drafts.insert_one(doc)
    return str(draft_id), str(league_id), [str(uid)], team_ids, pids


async def _cleanup(db, league_id, uids, pids):
    await db.drafts.delete_many({"league_id": league_id})
    await db.teams.delete_many({"league_id": league_id})
    await db.leagues.delete_one({"_id": ObjectId(league_id)})
    await db.users.delete_many({"_id": {"$in": [ObjectId(u) for u in uids]}})
    await db.players.delete_many({"_id": {"$in": [ObjectId(p) for p in pids]}})


def _wire_deps(db):
    from routes import draft_helpers
    draft_helpers._deps["db"] = db


@pytest.mark.asyncio
async def test_run_once_honours_time_per_pick_field():
    """Critical TFHL regression guard: a draft with `time_per_pick=14400`
    (4 hours) and a clock that started just 5 minutes ago is NOT past
    its deadline and must NOT be auto-picked. The legacy worker
    incorrectly fell through the 60s default and timed it out."""
    db = _db()
    _wire_deps(db)
    five_min_ago = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    draft_id, league_id, uids, team_ids, pids = await _seed_draft(
        db, started_at=five_min_ago, time_per_pick=14400,  # 4 hours
    )
    try:
        counts = await run_once(db, draft_ids_filter=[draft_id])
        assert counts["expired"] == 0, "4-hour pick clock should NOT expire after 5 minutes"
        assert counts["picked"] == 0
        refreshed = await db.drafts.find_one({"_id": ObjectId(draft_id)})
        assert refreshed["picks"] == []
    finally:
        await _cleanup(db, league_id, uids, pids)


@pytest.mark.asyncio
async def test_run_once_skips_drafts_outside_clock_window():
    """A draft scheduled for 9am-9pm America/New_York that started its
    pick clock 5 hours ago at 2am local time should NOT be auto-picked
    when `now` falls outside the window — even though the pick clock
    has expired."""
    db = _db()
    _wire_deps(db)
    # Use a far-past `started_at` so the pick clock is definitely
    # expired. Whether the worker SKIPS depends solely on the window.
    long_ago = (datetime.now(timezone.utc) - timedelta(hours=10)).isoformat()
    # Window = 1 minute starting and ending the same minute → effectively
    # always outside (unless we land exactly within that 1-minute window).
    # Robust: configure a window that's the OPPOSITE half of the day.
    now = datetime.now(timezone.utc)
    now_hour = now.hour
    # Configure a window that EXCLUDES the current UTC hour.
    if now_hour < 12:
        starts, stops = "13:00", "23:00"
    else:
        starts, stops = "01:00", "11:00"
    draft_id, league_id, uids, team_ids, pids = await _seed_draft(
        db, started_at=long_ago, time_per_pick=60,
        clock_starts_at=starts, clock_stops_at=stops, clock_timezone="UTC",
    )
    try:
        counts = await run_once(db, draft_ids_filter=[draft_id])
        assert counts["skipped"] == 1, f"Draft should be skipped outside window; counts={counts}"
        assert counts["picked"] == 0
        refreshed = await db.drafts.find_one({"_id": ObjectId(draft_id)})
        assert refreshed["picks"] == []
    finally:
        await _cleanup(db, league_id, uids, pids)
