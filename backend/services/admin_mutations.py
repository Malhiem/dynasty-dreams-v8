"""Atomic Admin credit and appeal mutations; retry-safe on transaction-capable Mongo."""
import hashlib
import json
import uuid
from datetime import datetime, timezone
from bson import ObjectId
from fastapi import HTTPException
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError, PyMongoError


def required_reason(payload, key="reason"):
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > 2000:
        raise HTTPException(400, f"{key} must contain 1 to 2000 nonblank characters")
    return value.strip()


async def transaction_ready(db):
    try:
        hello = await db.command("hello")
    except PyMongoError as exc:
        raise HTTPException(503, "MongoDB readiness could not be confirmed. No changes were made.") from exc
    if not hello.get("setName") and hello.get("msg") != "isdbgrid":
        raise HTTPException(503, "This Admin operation requires MongoDB transaction support. No changes were made.")


def audit(admin, target, action, **fields):
    return {"_id": ObjectId(), "admin_id": str(admin["_id"]), "admin_email": admin.get("email"),
            "admin_tier": admin.get("permission_tier") or admin.get("role"),
            "target_user_id": target, "action": action, "ts": datetime.now(timezone.utc).isoformat(),
            "mocked": False, **fields}


async def credit(db, admin, user_id, payload, key=None):
    amount = payload.get("amount_cents")
    if type(amount) is not int or amount == 0 or abs(amount) > 2_147_483_647:
        raise HTTPException(400, "amount_cents must be a nonzero integer within 32-bit range")
    currency = payload.get("currency", "usd")
    note = payload.get("note", "")
    if not isinstance(currency, str) or len(currency) != 3 or not currency.isascii() or not currency.isalpha():
        raise HTTPException(400, "currency must be a three-letter code")
    if not isinstance(note, str) or len(note) > 2000:
        raise HTTPException(400, "note must be at most 2000 characters")
    key = str(uuid.uuid4()) if key is None else key
    if len(key) > 128 or not key.strip() or not key.isascii():
        raise HTTPException(400, "Idempotency-Key must contain 1 to 128 ASCII characters")
    currency = currency.lower()
    fingerprint = hashlib.sha256(json.dumps([user_id, amount, currency, note], separators=(",", ":")).encode()).hexdigest()
    operation_id = hashlib.sha256(f"{admin['_id']}:{key}".encode()).hexdigest()
    await transaction_ready(db)

    def replay(doc):
        if doc["fingerprint"] != fingerprint:
            raise HTTPException(409, "Idempotency-Key was already used for a different credit operation")
        return doc["response"]

    async def apply(session):
        previous = await db.admin_credit_operations.find_one({"_id": operation_id}, session=session)
        if previous:
            return replay(previous)
        # The unique operation ID and all effects are committed in one transaction.
        await db.admin_credit_operations.insert_one({"_id": operation_id, "fingerprint": fingerprint}, session=session)
        updated = await db.users.find_one_and_update(
            {"_id": ObjectId(user_id), "$or": [{"promo_currency": currency}, {"promo_currency": {"$exists": False}}, {"promo_credits_cents": 0}]},
            [{"$set": {"promo_credits_cents": {"$add": [{"$ifNull": ["$promo_credits_cents", 0]}, amount]}, "promo_currency": currency}}],
            return_document=ReturnDocument.AFTER, session=session)
        if not updated:
            raise HTTPException(409, "User is unavailable or has a balance in another currency")
        balance = updated["promo_credits_cents"]
        row = audit(admin, user_id, "promo_credit", reason=note,
                    metadata={"amount_cents": amount, "currency": currency, "new_balance_cents": balance, "operation_id": operation_id},
                    prior_state={"promo_credits_cents": balance - amount})
        await db.admin_user_actions.insert_one(row, session=session)
        response = {"ok": True, "audit_id": str(row["_id"]), "new_balance_cents": balance, "operation_id": operation_id}
        await db.admin_credit_operations.update_one({"_id": operation_id}, {"$set": {"response": response}}, session=session)
        return response

    try:
        async with await db.client.start_session() as session:
            return await session.with_transaction(apply)
    except DuplicateKeyError:
        # A concurrent retry may have won the unique operation ID.
        previous = await db.admin_credit_operations.find_one({"_id": operation_id})
        if previous:
            return replay(previous)
        raise HTTPException(409, "Credit operation is in progress; retry with the same Idempotency-Key")
    except PyMongoError as exc:
        raise HTTPException(503, "Credit result could not be confirmed; retry with the same Idempotency-Key") from exc


async def resolve_appeal(db, admin, oid, action, note):
    await transaction_ready(db)

    async def apply(session):
        appeal = await db.user_appeals.find_one({"_id": oid, "status": "open"}, session=session)
        if not appeal:
            raise HTTPException(404, "Appeal not found or already resolved")
        result = await db.user_appeals.update_one({"_id": oid, "status": "open"}, {"$set": {
            "status": action, "resolved_at": datetime.now(timezone.utc).isoformat(),
            "resolved_by_email": admin.get("email"), "resolution_note": note}}, session=session)
        if result.modified_count != 1:
            raise HTTPException(409, "Another administrator already resolved this appeal")
        if action == "approved":
            try:
                user_id = ObjectId(appeal["user_id"])
            except Exception as exc:
                raise HTTPException(409, "Appeal account is invalid") from exc
            changed = await db.users.update_one({"_id": user_id}, {"$set": {"status": "active"},
                "$unset": {"ban_reason_code": "", "ban_reason": "", "ban_expires_at": ""}}, session=session)
            if changed.matched_count != 1:
                raise HTTPException(409, "Appeal account no longer exists")
        await db.admin_user_actions.insert_one(audit(admin, appeal["user_id"], "appeal_resolved", reason=note,
            metadata={"appeal_id": str(oid), "decision": action}, prior_state={"status": "open"}), session=session)
        return {"ok": True, "appeal_id": str(oid), "status": action}

    try:
        async with await db.client.start_session() as session:
            return await session.with_transaction(apply)
    except PyMongoError as exc:
        raise HTTPException(503, "Appeal could not be resolved atomically; reload before retrying") from exc
