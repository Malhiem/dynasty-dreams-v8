"""Iter 232N.70 — Orphan draft cleanup + hardened draft-lock pytest suite.

Covers the "why is there a draft running if no draft has been set in
the league administration page?" bug. Root cause was that
`utils/draft_lock.py::get_locking_draft` accepted any draft doc with
`status=in_progress` — including stub docs left over from cancelled
setup flows — which surfaced a false "Draft in progress" lock on the
free-agent pickup path.

Tests:
  1. `_looks_like_real_draft` rejects a stub doc that only has
     `status=in_progress` + a few fake team_abbrs, and accepts a doc
     with a real scheduling / ordering signal.
  2. `get_locking_draft` returns `None` for a league whose only
     matching draft is a stub, and correctly returns a legit draft
     when one exists.
  3. `POST /admin/drafts/cleanup-orphans` deletes only orphan draft
     docs and leaves properly-configured drafts alone. Cascade-deletes
     dangling `draft_picks` too.
  4. `GET /drafts?league_id=X` hides orphans from the default response
     but reveals them with `?include_orphans=true`.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

import pytest
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _db():
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[
        os.environ.get("DB_NAME", os.environ["DB_NAME"])
    ]


class _StubReq:
    def __init__(self):
        self.headers = {}
        self.cookies = {}


async def _seed_admin(db):
    uid = ObjectId()
    await db.users.insert_one({
        "_id": uid, "email": f"n70_{str(uid)[:6]}@iter.test",
        "name": "N70 admin", "role": "admin",
    })
    return str(uid)


def _wire_admin_test_sandbox(user_id):
    from routes import admin_test_sandbox as m
    db = _db()
    async def _fake_user(_r):
        return await db.users.find_one({"_id": ObjectId(user_id)})
    m._deps["db"] = db
    m._deps["get_current_user"] = _fake_user


# ── Unit tests for `_looks_like_real_draft` ─────────────────────

def test_looks_like_real_draft_rejects_orphan_stub():
    from utils.draft_lock import _looks_like_real_draft
    # Reproduces the exact rogue doc from the user's sandbox.
    orphan = {
        "_id": "abc",
        "league_id": "xyz",
        "type": "entry",
        "status": "in_progress",
        "current_pick": 1,
        "team_abbrs": ["t1", "t2", "t3"],
    }
    assert _looks_like_real_draft(orphan) is False


def test_looks_like_real_draft_accepts_scheduled_draft():
    from utils.draft_lock import _looks_like_real_draft
    scheduled = {
        "_id": "abc", "league_id": "xyz",
        "status": "scheduled",
        "scheduled_at": "2026-09-01T15:00:00Z",
        "total_rounds": 20,
    }
    assert _looks_like_real_draft(scheduled) is True


def test_looks_like_real_draft_accepts_live_draft_with_on_the_clock():
    from utils.draft_lock import _looks_like_real_draft
    live = {
        "_id": "abc", "league_id": "xyz",
        "status": "in_progress",
        "on_the_clock_team_id": "team_1",
        "pick_order": ["team_1", "team_2", "team_3"],
    }
    assert _looks_like_real_draft(live) is True


def test_looks_like_real_draft_ignores_empty_pick_order():
    from utils.draft_lock import _looks_like_real_draft
    empty = {
        "_id": "abc", "league_id": "xyz",
        "status": "in_progress",
        "pick_order": [], "team_abbrs": ["t1"],
    }
    assert _looks_like_real_draft(empty) is False


# ── `get_locking_draft` integration ─────────────────────────────

@pytest.mark.asyncio
async def test_get_locking_draft_ignores_orphan_returns_real():
    from utils.draft_lock import get_locking_draft
    db = _db()
    league_id = str(ObjectId())

    # Seed an orphan (should be ignored)
    orphan = await db.drafts.insert_one({
        "league_id": league_id,
        "status": "in_progress",
        "type": "entry", "current_pick": 1,
        "team_abbrs": ["t1", "t2"],
    })

    # No lock: orphan doesn't count.
    assert await get_locking_draft(db, league_id) is None

    # Add a legit draft — now the lock returns.
    real = await db.drafts.insert_one({
        "league_id": league_id,
        "status": "in_progress",
        "total_rounds": 20,
        "pick_order": ["t1", "t2", "t3"],
        "on_the_clock_team_id": "t1",
    })
    locking = await get_locking_draft(db, league_id)
    assert locking is not None
    assert locking["_id"] == real.inserted_id

    # Cleanup
    await db.drafts.delete_one({"_id": orphan.inserted_id})
    await db.drafts.delete_one({"_id": real.inserted_id})


# ── Cleanup endpoint ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cleanup_orphan_drafts_deletes_stubs_only():
    from routes import admin_test_sandbox as m
    db = _db()
    admin_id = await _seed_admin(db)
    _wire_admin_test_sandbox(admin_id)

    league_id = str(ObjectId())
    stub_ids = []
    for _ in range(2):
        r = await db.drafts.insert_one({
            "league_id": league_id,
            "status": "in_progress",
            "current_pick": 1, "team_abbrs": ["t1", "t2"],
        })
        stub_ids.append(r.inserted_id)
        # Attach a dangling draft_pick to prove cascade cleanup works
        await db.draft_picks.insert_one({
            "draft_id": str(r.inserted_id),
            "pick_number": 1, "team_id": "t1",
        })
    real = await db.drafts.insert_one({
        "league_id": league_id,
        "status": "scheduled",
        "scheduled_at": "2026-09-01T15:00:00Z",
        "total_rounds": 20,
    })

    res = await m.cleanup_orphan_drafts(_StubReq(), league_id=league_id)
    assert res["ok"] is True
    assert res["deleted"] == 2
    assert res["kept"] == 1
    assert set(res["deleted_draft_ids"]) == {str(s) for s in stub_ids}

    # Real draft still present.
    assert await db.drafts.find_one({"_id": real.inserted_id}) is not None
    # Dangling draft_picks nuked.
    for sid in stub_ids:
        assert await db.draft_picks.count_documents({"draft_id": str(sid)}) == 0

    # Cleanup
    await db.drafts.delete_one({"_id": real.inserted_id})
    await db.users.delete_one({"_id": ObjectId(admin_id)})


# ── /drafts list endpoint filters orphans by default ────────────

@pytest.mark.asyncio
async def test_upcoming_drafts_endpoint_filters_orphans():
    from routes import draft_inspection
    db = _db()
    draft_inspection._deps["db"] = db  # type: ignore

    league_id = str(ObjectId())
    stub = await db.drafts.insert_one({
        "league_id": league_id,
        "status": "scheduled",
        "current_pick": 1, "team_abbrs": ["t1"],
        # No scheduled_time, no total_rounds, no pick_order — pure orphan
    })
    real_scheduled = await db.drafts.insert_one({
        "league_id": league_id,
        "status": "scheduled",
        "scheduled_time": (__import__("datetime").datetime.now(__import__("datetime").timezone.utc) + __import__("datetime").timedelta(days=1)).isoformat(),
        "total_rounds": 20,
    })

    res = await draft_inspection.get_upcoming_drafts(league_id=league_id, days=90)
    ids = {d["_id"] for d in res["drafts"]}
    assert str(real_scheduled.inserted_id) in ids
    assert str(stub.inserted_id) not in ids
    assert res["count"] == 1

    await db.drafts.delete_one({"_id": stub.inserted_id})
    await db.drafts.delete_one({"_id": real_scheduled.inserted_id})


# ── /drafts list endpoint filters orphans by default ────────────

@pytest.mark.asyncio
async def test_drafts_list_hides_orphans_by_default_shows_with_flag():
    from routes import draft_inspection
    db = _db()
    draft_inspection._deps["db"] = db  # type: ignore

    league_id = str(ObjectId())
    stub = await db.drafts.insert_one({
        "league_id": league_id,
        "status": "in_progress",
        "current_pick": 1, "team_abbrs": ["t1"],
    })
    real = await db.drafts.insert_one({
        "league_id": league_id,
        "status": "scheduled",
        "scheduled_at": "2026-09-01T15:00:00Z",
        "total_rounds": 20,
    })

    default = await draft_inspection.get_drafts(league_id=league_id)
    ids_default = {d["_id"] for d in default}
    assert str(real.inserted_id) in ids_default
    assert str(stub.inserted_id) not in ids_default  # orphan hidden

    with_orphans = await draft_inspection.get_drafts(
        league_id=league_id, include_orphans=True,
    )
    ids_all = {d["_id"] for d in with_orphans}
    assert str(real.inserted_id) in ids_all
    assert str(stub.inserted_id) in ids_all       # orphan surfaced

    # Cleanup
    await db.drafts.delete_one({"_id": stub.inserted_id})
    await db.drafts.delete_one({"_id": real.inserted_id})
