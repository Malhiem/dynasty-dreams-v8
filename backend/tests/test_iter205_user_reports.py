"""
Iter 205 — User Reports / Flagging tests.

Cover the public POST /api/reports endpoint and the admin queue + resolve
flow under routes/admin_platform.py.
"""
from __future__ import annotations

import os

import pytest
from bson import ObjectId
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")


def _db():
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


@pytest.mark.asyncio
async def test_submit_report_validates_category_and_dedupes_per_pair():
    """POST /reports validates category, rejects self-reports, and
    returns deduped=True when the reporter already has an open report
    against the same target."""
    from routes import user_reports as ur

    reporter_id = ObjectId()
    target_id = ObjectId()

    async def _fake_user(_req):
        return {"_id": str(reporter_id), "email": "reporter@example.com"}

    ur.setup({"db": _db(), "get_current_user": _fake_user})

    # Seed target user
    await _db().users.insert_one({
        "_id": target_id, "email": "target@example.com", "username": "targetUsr",
    })

    class _Req:
        def __init__(self, body):
            self._body = body

        async def json(self):
            return self._body

    # Invalid category
    try:
        await ur.submit_user_report(_Req({
            "target_user_id": str(target_id),
            "category": "not_a_real_category",
            "reason": "x",
        }))
        assert False, "expected 400"
    except Exception as e:
        assert "category must be" in str(e)

    # Self-report rejected
    try:
        await ur.submit_user_report(_Req({
            "target_user_id": str(reporter_id),
            "category": "harassment",
            "reason": "x",
        }))
        assert False, "expected 400 self-report"
    except Exception as e:
        assert "yourself" in str(e)

    # First valid report — created
    res1 = await ur.submit_user_report(_Req({
        "target_user_id": str(target_id),
        "category": "harassment",
        "reason": "rude language in league chat",
        "league_id": "league_abc",
        "context_url": "/chat#msg-1",
    }))
    assert res1["ok"] is True
    assert res1["deduped"] is False

    # Duplicate from same reporter against same target — deduped
    res2 = await ur.submit_user_report(_Req({
        "target_user_id": str(target_id),
        "category": "spam",
        "reason": "different reason — still deduped",
    }))
    assert res2["deduped"] is True
    assert res2["report_id"] == res1["report_id"]

    # Cleanup
    await _db().user_reports.delete_many({"reporter_id": str(reporter_id)})
    await _db().users.delete_one({"_id": target_id})


@pytest.mark.asyncio
async def test_admin_resolve_report_changes_status_and_records_action():
    """Admin can resolve an open report — status flips, resolution_action
    is recorded, and a subsequent resolve attempt fails (already resolved)."""
    from routes import admin_platform as ap

    admin_id = ObjectId()
    reporter_id = ObjectId()
    target_id = ObjectId()

    async def _fake_admin(_req):
        return {"_id": str(admin_id), "email": "admin@example.com", "role": "admin"}

    ap.setup(db=_db(), get_current_user=_fake_admin)

    # Seed an open report
    report = await _db().user_reports.insert_one({
        "reporter_id": str(reporter_id),
        "reporter_email": "reporter@example.com",
        "target_user_id": str(target_id),
        "target_user_email": "target@example.com",
        "category": "harassment",
        "reason": "trolling",
        "status": "open",
        "created_at": "2026-02-22T00:00:00Z",
    })
    rid = str(report.inserted_id)

    class _Req:
        def __init__(self, body):
            self._body = body

        async def json(self):
            return self._body

    try:
        # List should surface the open ticket
        listed = await ap.list_user_reports(_Req({}), status="open", limit=100)
        assert any(r["report_id"] == rid for r in listed["reports"])

        # Resolve with "ban"
        out = await ap.resolve_user_report(rid, _Req({
            "action": "resolved",
            "applied_action": "ban",
            "note": "permanent ban",
        }))
        assert out["ok"] is True
        assert out["status"] == "resolved"

        doc = await _db().user_reports.find_one({"_id": ObjectId(rid)})
        assert doc["status"] == "resolved"
        assert doc["resolution_action"] == "ban"
        assert doc["resolution_note"] == "permanent ban"
        assert doc["resolved_by_email"] == "admin@example.com"

        # Re-resolving should 404 (already resolved)
        try:
            await ap.resolve_user_report(rid, _Req({"action": "dismissed", "applied_action": "none"}))
            assert False, "expected 404"
        except Exception as e:
            assert "404" in str(e) or "already" in str(e).lower() or "not found" in str(e).lower()
    finally:
        await _db().user_reports.delete_one({"_id": ObjectId(rid)})
