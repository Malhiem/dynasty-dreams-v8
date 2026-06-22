"""
Iter 206 — Content Moderation Phase 2 & 3 + Account Integrity tests.
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


class _Req:
    def __init__(self, body=None):
        self._body = body or {}

    async def json(self):
        return self._body


@pytest.mark.asyncio
async def test_keyword_scanner_matches_and_queues_for_review():
    """`scan_text` should match a banned word (word-boundary, case-insensitive)
    and `queue_for_review` should insert a pending mod-queue entry."""
    from routes import moderation as mod

    mod.setup({"db": _db(), "get_current_user": lambda r: {"role": "admin"}})

    seed_word = "iter206testbadword"
    await _db().keyword_filters.insert_one({"word": seed_word, "severity": "high"})
    await mod.refresh_keyword_cache()

    # Match (case-insensitive word boundary)
    m1 = await mod.scan_text(f"hey {seed_word.upper()}!")
    assert m1 is not None
    assert m1["matched_word"] == seed_word
    assert m1["severity"] == "high"

    # No match
    m2 = await mod.scan_text("perfectly fine message")
    assert m2 is None

    # Queue for review
    item_id = await mod.queue_for_review(
        source="chat",
        content="hey BANNED!",
        author_id=str(ObjectId()),
        author_email="x@y.z",
        matched_word=seed_word,
        severity="high",
    )
    assert ObjectId.is_valid(item_id)
    doc = await _db().moderation_queue.find_one({"_id": ObjectId(item_id)})
    assert doc["status"] == "pending"
    assert doc["source"] == "chat"

    # Cleanup
    await _db().keyword_filters.delete_one({"word": seed_word})
    await _db().moderation_queue.delete_one({"_id": ObjectId(item_id)})


@pytest.mark.asyncio
async def test_admin_can_resolve_moderation_queue_item():
    from routes import moderation as mod

    admin_id = ObjectId()
    async def _admin(_req): return {"_id": str(admin_id), "email": "admin@x.com", "role": "admin"}
    mod.setup({"db": _db(), "get_current_user": _admin})

    item_id = await mod.queue_for_review(
        source="chat", content="bad msg", author_id="u1", matched_word="x", severity="medium",
    )
    try:
        out = await mod.resolve_moderation_item(item_id, _Req({"action": "deleted", "note": "spam"}))
        assert out["status"] == "deleted"
        doc = await _db().moderation_queue.find_one({"_id": ObjectId(item_id)})
        assert doc["status"] == "deleted"
        assert doc["resolution_note"] == "spam"
    finally:
        await _db().moderation_queue.delete_one({"_id": ObjectId(item_id)})


@pytest.mark.asyncio
async def test_ban_unban_user_workflow():
    from routes import moderation as mod

    admin_id = ObjectId()
    async def _admin(_req): return {"_id": str(admin_id), "email": "admin@x.com", "role": "admin"}
    mod.setup({"db": _db(), "get_current_user": _admin})

    target_id = ObjectId()
    await _db().users.insert_one({"_id": target_id, "email": "target@x.com", "status": "active"})
    try:
        out = await mod.ban_user(str(target_id), _Req({
            "reason_code": "harassment",
            "reason": "Repeated abuse",
        }))
        assert out["status"] == "banned"
        doc = await _db().users.find_one({"_id": target_id})
        assert doc["status"] == "banned"
        assert doc["ban_reason_code"] == "harassment"

        # Suspension with duration
        out2 = await mod.ban_user(str(target_id), _Req({
            "reason_code": "cheating",
            "reason": "1-day timeout",
            "duration_days": 1,
        }))
        assert out2["status"] == "suspended"
        assert out2["ban_expires_at"] is not None

        # Unban clears fields
        out3 = await mod.unban_user(str(target_id), _Req())
        assert out3["status"] == "active"
        doc2 = await _db().users.find_one({"_id": target_id})
        assert doc2["status"] == "active"
        assert "ban_reason_code" not in doc2
    finally:
        await _db().users.delete_one({"_id": target_id})


@pytest.mark.asyncio
async def test_account_integrity_groups_users_by_shared_ip():
    from routes import moderation as mod

    admin_id = ObjectId()
    async def _admin(_req): return {"_id": str(admin_id), "email": "admin@x.com", "role": "admin"}
    mod.setup({"db": _db(), "get_current_user": _admin})

    user_a = ObjectId(); user_b = ObjectId(); user_c = ObjectId()
    await _db().users.insert_many([
        {"_id": user_a, "email": "a@x.com"},
        {"_id": user_b, "email": "b@x.com"},
        {"_id": user_c, "email": "c@x.com"},
    ])
    shared_ip = "203.0.113.45"
    other_ip = "203.0.113.99"
    audit_ids = await _db().user_login_audit.insert_many([
        {"user_id": str(user_a), "ip": shared_ip, "ts": "2026-02-20T00:00:00Z"},
        {"user_id": str(user_b), "ip": shared_ip, "ts": "2026-02-21T00:00:00Z"},
        {"user_id": str(user_a), "ip": shared_ip, "ts": "2026-02-22T00:00:00Z"},  # repeat A
        {"user_id": str(user_c), "ip": other_ip, "ts": "2026-02-22T00:00:00Z"},
    ])
    try:
        result = await mod.account_integrity(_Req(), limit=10)
        groups = result["groups"]
        shared = next((g for g in groups if g["ip"] == shared_ip), None)
        assert shared is not None
        assert shared["distinct_users"] == 2  # A + B
        ids = [u["user_id"] for u in shared["users"]]
        assert str(user_a) in ids and str(user_b) in ids
        # Solo C should NOT appear
        solo = next((g for g in groups if g["ip"] == other_ip), None)
        assert solo is None
    finally:
        await _db().users.delete_many({"_id": {"$in": [user_a, user_b, user_c]}})
        await _db().user_login_audit.delete_many({"_id": {"$in": audit_ids.inserted_ids}})


@pytest.mark.asyncio
async def test_appeal_workflow_with_auto_unban():
    """A banned user can submit one appeal (deduped while open). When
    admin approves the appeal, the user is auto-unbanned."""
    from routes import moderation as mod

    target_id = ObjectId()
    admin_id = ObjectId()
    await _db().users.insert_one({
        "_id": target_id, "email": "banned@x.com", "status": "banned",
        "ban_reason_code": "harassment", "ban_reason": "language",
    })

    async def _target(_req):
        return await _db().users.find_one({"_id": target_id})

    async def _admin(_req):
        return {"_id": str(admin_id), "email": "admin@x.com", "role": "admin"}

    # Submit appeal as banned user
    mod.setup({"db": _db(), "get_current_user": _target})
    res = await mod.submit_appeal(_Req({"message": "I'm reformed, please reinstate."}))
    assert res["ok"] and res["deduped"] is False
    appeal_id = res["appeal_id"]

    # Dedupe: second submission returns same id
    res2 = await mod.submit_appeal(_Req({"message": "Same thing"}))
    assert res2["deduped"] is True
    assert res2["appeal_id"] == appeal_id

    # Admin approves → user auto-unbanned
    mod.setup({"db": _db(), "get_current_user": _admin})
    try:
        out = await mod.admin_resolve_appeal(appeal_id, _Req({
            "action": "approved", "note": "Good faith reinstated",
        }))
        assert out["status"] == "approved"
        doc = await _db().users.find_one({"_id": target_id})
        assert doc["status"] == "active"
        assert "ban_reason_code" not in doc
    finally:
        await _db().users.delete_one({"_id": target_id})
        await _db().user_appeals.delete_one({"_id": ObjectId(appeal_id)})
