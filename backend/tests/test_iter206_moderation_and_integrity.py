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



@pytest.mark.asyncio
async def test_stripe_chargeback_webhook_flags_user():
    """POST /api/webhook/stripe with a `charge.dispute.created` payload
    pushes a chargeback_flag entry onto the matching user (matched by
    stripe_customer_id)."""
    import json
    from httpx import AsyncClient, ASGITransport
    from fastapi import FastAPI
    from routes import payments as pmt

    user_id = ObjectId()
    customer_id = f"cus_iter207_{ObjectId()}"
    await _db().users.insert_one({
        "_id": user_id,
        "email": "payer@x.com",
        "stripe_customer_id": customer_id,
    })

    app = FastAPI()
    pmt.setup({"db": _db(), "logger": None, "STRIPE_API_KEY": "sk_test_emergent"})
    app.include_router(pmt.router, prefix="/api")

    body = json.dumps({
        "type": "charge.dispute.created",
        "data": {"object": {
            "id": "dp_iter207_test",
            "customer": customer_id,
            "amount": 1999,
            "currency": "usd",
            "reason": "fraudulent",
            "status": "needs_response",
            "charge": "ch_iter207",
        }},
    }).encode("utf-8")
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.post("/api/webhook/stripe", content=body,
                                  headers={"content-type": "application/json"})
            assert r.status_code == 200
            assert r.json()["event_type"] == "charge.dispute.created"

        doc = await _db().users.find_one({"_id": user_id})
        assert doc["payment_fraud_flag"] is True
        flags = doc.get("chargeback_flags") or []
        assert len(flags) == 1
        assert flags[0]["dispute_id"] == "dp_iter207_test"
        assert flags[0]["amount_cents"] == 1999
        assert flags[0]["status"] == "open"
    finally:
        await _db().users.delete_one({"_id": user_id})


@pytest.mark.asyncio
async def test_device_integrity_groups_by_device_hash():
    """`device-integrity` aggregates by device_hash. Catches multi-account
    abuse across different IPs."""
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
    shared_device = f"dev_iter207_{ObjectId()}"
    audit_ids = await _db().user_login_audit.insert_many([
        {"user_id": str(user_a), "ip": "1.1.1.1", "device_hash": shared_device, "ts": "2026-02-22T00:00:00Z"},
        {"user_id": str(user_b), "ip": "2.2.2.2", "device_hash": shared_device, "ts": "2026-02-22T01:00:00Z"},
        {"user_id": str(user_c), "ip": "3.3.3.3", "device_hash": "different_device", "ts": "2026-02-22T02:00:00Z"},
        # null device — must be excluded
        {"user_id": str(user_a), "ip": "1.1.1.1", "device_hash": None, "ts": "2026-02-22T03:00:00Z"},
    ])
    try:
        result = await mod.device_integrity(_Req(), limit=10)
        groups = result["groups"]
        # Only shared_device group qualifies (>= 2 users)
        shared = next((g for g in groups if g["device_hash"] == shared_device), None)
        assert shared is not None
        assert shared["distinct_users"] == 2
        # different_device has only 1 user → excluded
        other = next((g for g in groups if g["device_hash"] == "different_device"), None)
        assert other is None
    finally:
        await _db().users.delete_many({"_id": {"$in": [user_a, user_b, user_c]}})
        await _db().user_login_audit.delete_many({"_id": {"$in": audit_ids.inserted_ids}})


# ─── Iter 208 — Trust Score ─────────────────────────────────────────────
@pytest.mark.asyncio
async def test_trust_score_baseline_clean_user():
    """A brand-new user with no infractions starts near baseline (70)."""
    from routes import moderation as mod

    user_id = ObjectId()
    requester_id = ObjectId()
    await _db().users.insert_one({
        "_id": user_id, "email": "clean@x.com", "status": "active",
    })

    async def _user(_req): return {"_id": str(requester_id), "email": "x@x.com"}
    mod.setup({"db": _db(), "get_current_user": _user})

    try:
        result = await mod.get_user_trust_score(str(user_id), _Req())
        assert 65 <= result["score"] <= 100  # baseline ± age bonus
        assert result["tier"] in ("trusted", "neutral")
        # Non-admin requester gets NO breakdown
        assert "breakdown" not in result
    finally:
        await _db().users.delete_one({"_id": user_id})


@pytest.mark.asyncio
async def test_trust_score_drops_for_resolved_reports_and_chargebacks():
    """Score decreases by 10 per resolved report and 25 per chargeback,
    floors at 0 if banned, and admin requests get the breakdown."""
    from routes import moderation as mod

    user_id = ObjectId()
    admin_id = ObjectId()
    await _db().users.insert_one({
        "_id": user_id, "email": "risky@x.com", "status": "suspended",
        "chargeback_flags": [{"reason": "fraud"}, {"reason": "fraud"}],  # -50
    })

    # Seed 3 resolved-against reports (-30)
    seeded_reports = await _db().user_reports.insert_many([
        {"target_user_id": str(user_id), "status": "resolved",
         "resolution_action": "warning", "category": "harassment"},
        {"target_user_id": str(user_id), "status": "resolved",
         "resolution_action": "ban", "category": "harassment"},
        {"target_user_id": str(user_id), "status": "resolved",
         "resolution_action": "timeout", "category": "spam"},
    ])

    async def _admin(_req): return {"_id": str(admin_id), "email": "admin@x.com", "role": "admin"}
    mod.setup({"db": _db(), "get_current_user": _admin})
    try:
        result = await mod.get_user_trust_score(str(user_id), _Req())
        assert result["score"] == 0, f"expected 0, got {result['score']} (heavy infractions + suspension)"
        assert result["tier"] == "risky"
        # Admin gets breakdown
        assert "breakdown" in result
        bd = result["breakdown"]
        assert bd["reports_resolved_against"] == 3
        assert bd["chargeback_flags"] == 2
        assert bd["status"] == "suspended"
    finally:
        await _db().users.delete_one({"_id": user_id})
        await _db().user_reports.delete_many({"_id": {"$in": seeded_reports.inserted_ids}})


@pytest.mark.asyncio
async def test_trust_score_tier_thresholds():
    """Verify the tier mapping at boundary values."""
    from routes.moderation import setup as mod_setup, get_user_trust_score
    import routes.moderation as mod

    user_id = ObjectId()
    await _db().users.insert_one({
        "_id": user_id, "email": "midrange@x.com", "status": "active",
        "chargeback_flags": [{}],  # -25 → baseline 70 + age0 - 25 = 45 (neutral)
    })
    async def _user(_req): return {"_id": str(ObjectId()), "email": "x@x.com"}
    mod_setup({"db": _db(), "get_current_user": _user})
    try:
        r = await mod.get_user_trust_score(str(user_id), _Req())
        assert 40 <= r["score"] <= 50
        assert r["tier"] == "neutral"
    finally:
        await _db().users.delete_one({"_id": user_id})


# ─── Iter 208 — Stripe webhook signature verification ──────────────────
@pytest.mark.asyncio
async def test_stripe_webhook_rejects_invalid_signature_when_secret_set(monkeypatch):
    """When STRIPE_WEBHOOK_SECRET is set, an invalid Stripe-Signature
    header must return HTTP 400."""
    import json
    from httpx import AsyncClient, ASGITransport
    from fastapi import FastAPI
    from routes import payments as pmt

    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_iter208_test_secret_value")

    app = FastAPI()
    pmt.setup({"db": _db(), "logger": None, "STRIPE_API_KEY": "sk_test_emergent"})
    app.include_router(pmt.router, prefix="/api")

    body = json.dumps({
        "type": "charge.dispute.created",
        "data": {"object": {"id": "dp_x", "customer": "cus_unknown", "amount": 100}},
    }).encode("utf-8")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post(
            "/api/webhook/stripe",
            content=body,
            headers={"content-type": "application/json", "Stripe-Signature": "invalid_sig"},
        )
        assert r.status_code == 400
        assert "signature" in r.text.lower()

