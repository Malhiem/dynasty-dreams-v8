"""
Iter 206 — Content Moderation Phase 2 & 3 + Account Integrity.

Responsibilities
────────────────
1.  Keyword-driven content scanning helper (`scan_text`) used by chat,
    trade-block comments, username/team-name set endpoints to auto-flag
    suspicious content into `db.moderation_queue`.

2.  Admin endpoints:
      GET    /api/admin/platform/moderation-queue   — list flagged items
      POST   /api/admin/platform/moderation/{id}/resolve — approve | delete
      GET    /api/admin/platform/keyword-filters    — list configured banned words
      POST   /api/admin/platform/keyword-filters    — add a banned word
      DELETE /api/admin/platform/keyword-filters/{id} — remove a banned word
      GET    /api/admin/platform/account-integrity  — flag users sharing IP / device
      POST   /api/admin/platform/users/{id}/ban     — apply ban/suspension
      POST   /api/admin/platform/users/{id}/unban   — lift ban
      POST   /api/admin/platform/users/{id}/flag-chargeback — manual payment-fraud flag

3.  Public endpoints:
      POST /api/appeals — banned user submits an appeal
      GET  /api/appeals/mine — user's own appeal status
      GET  /api/admin/platform/appeals — admin queue
      POST /api/admin/platform/appeals/{id}/resolve — admin acts on appeal

Collections
───────────
* `moderation_queue`  : flagged user-generated content awaiting review
* `keyword_filters`   : banned-word dictionary (admin-managed)
* `user_appeals`      : ban-appeal tickets
* `user_login_audit`  : per-login IP/UA fingerprint trail (for multi-account)
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Query, Request

router = APIRouter(prefix="/admin/platform", tags=["moderation"])
appeals_router = APIRouter()  # mounted at /api (public + admin both use one router)

_deps: dict = {}


def setup(deps: dict) -> None:
    _deps.update(deps)


def _db():
    return _deps["db"]


async def _require_admin(request: Request) -> dict:
    user = await _deps["get_current_user"](request)
    if (user or {}).get("role") != "admin":
        raise HTTPException(status_code=403, detail="Platform admin access required")
    return user


def _iso(dt) -> str | None:
    if not dt:
        return None
    if isinstance(dt, str):
        return dt
    return dt.isoformat() if hasattr(dt, "isoformat") else str(dt)


# ─────────────────────────────────────────────────────────────────────
# Keyword scanner — used by chat / trade-block / signup endpoints to
# auto-flag suspicious content into the moderation queue.
# ─────────────────────────────────────────────────────────────────────
# In-memory keyword cache. Refreshed via `refresh_keyword_cache()` on
# admin add/remove + once on app startup.
_keyword_cache: list[dict] = []  # [{word, severity}]
_keyword_cache_loaded = False


async def refresh_keyword_cache():
    global _keyword_cache, _keyword_cache_loaded
    rows = await _db().keyword_filters.find({}).to_list(500)
    _keyword_cache = [
        {"word": (r.get("word") or "").lower(), "severity": r.get("severity", "medium")}
        for r in rows
        if r.get("word")
    ]
    _keyword_cache_loaded = True


async def _ensure_cache():
    if not _keyword_cache_loaded:
        await refresh_keyword_cache()


async def scan_text(text: str) -> dict | None:
    """Return a match descriptor if any banned word is found in `text`,
    else None. Case-insensitive substring + word-boundary match."""
    if not text:
        return None
    await _ensure_cache()
    needle = text.lower()
    for entry in _keyword_cache:
        word = entry["word"]
        if not word:
            continue
        # Word-boundary match where possible, fallback to substring for
        # multi-token banned phrases.
        if " " in word:
            if word in needle:
                return {"matched_word": word, "severity": entry["severity"]}
        else:
            if re.search(r"\b" + re.escape(word) + r"\b", needle):
                return {"matched_word": word, "severity": entry["severity"]}
    return None


async def queue_for_review(
    *,
    source: str,                # "chat" | "trade_block" | "username" | "team_name" | "avatar"
    content: str,
    author_id: Optional[str],
    author_email: Optional[str] = None,
    context: Optional[dict] = None,
    matched_word: Optional[str] = None,
    severity: str = "medium",
    auto_flagged: bool = True,
) -> str:
    """Insert a moderation_queue entry. Returns inserted_id as str."""
    doc = {
        "source": source,
        "content": (content or "")[:4000],
        "author_id": author_id,
        "author_email": author_email,
        "context": context or {},
        "matched_word": matched_word,
        "severity": severity,
        "auto_flagged": auto_flagged,
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    res = await _db().moderation_queue.insert_one(doc)
    return str(res.inserted_id)


# ─────────────────────────────────────────────────────────────────────
# Admin: Moderation Queue
# ─────────────────────────────────────────────────────────────────────
@router.get("/moderation-queue")
async def list_moderation_queue(
    request: Request,
    status: str = Query("pending", pattern=r"^(pending|approved|deleted|all)$"),
    source: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
):
    await _require_admin(request)
    db = _db()
    q: dict = {} if status == "all" else {"status": status}
    if source:
        q["source"] = source
    rows = await db.moderation_queue.find(q).sort("created_at", -1).to_list(limit)
    out = []
    for r in rows:
        out.append({
            "item_id": str(r["_id"]),
            "source": r.get("source"),
            "content": r.get("content"),
            "author_id": r.get("author_id"),
            "author_email": r.get("author_email"),
            "context": r.get("context") or {},
            "matched_word": r.get("matched_word"),
            "severity": r.get("severity"),
            "status": r.get("status"),
            "auto_flagged": r.get("auto_flagged", True),
            "created_at": _iso(r.get("created_at")),
            "resolved_at": _iso(r.get("resolved_at")),
            "resolved_by_email": r.get("resolved_by_email"),
        })
    pending_count = await db.moderation_queue.count_documents({"status": "pending"})
    return {"items": out, "pending_count": pending_count}


@router.post("/moderation/{item_id}/resolve")
async def resolve_moderation_item(item_id: str, request: Request):
    """Body: { "action": "approved" | "deleted", "note": "..." }"""
    user = await _require_admin(request)
    try:
        oid = ObjectId(item_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid item id")
    payload = await request.json()
    action = payload.get("action")
    if action not in ("approved", "deleted"):
        raise HTTPException(status_code=400, detail="action must be approved|deleted")
    res = await _db().moderation_queue.update_one(
        {"_id": oid, "status": "pending"},
        {"$set": {
            "status": action,
            "resolved_at": datetime.now(timezone.utc).isoformat(),
            "resolved_by": str(user["_id"]),
            "resolved_by_email": user.get("email"),
            "resolution_note": (payload.get("note") or "")[:1000],
        }},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Item not found or already resolved")
    return {"ok": True, "item_id": item_id, "status": action}


# ─────────────────────────────────────────────────────────────────────
# Admin: Keyword Filter Management
# ─────────────────────────────────────────────────────────────────────
@router.get("/keyword-filters")
async def list_keyword_filters(request: Request):
    await _require_admin(request)
    rows = await _db().keyword_filters.find({}).sort("word", 1).to_list(500)
    return {
        "filters": [{
            "filter_id": str(r["_id"]),
            "word": r.get("word"),
            "severity": r.get("severity", "medium"),
            "created_at": _iso(r.get("created_at")),
            "created_by_email": r.get("created_by_email"),
        } for r in rows]
    }


@router.post("/keyword-filters")
async def add_keyword_filter(request: Request):
    """Body: { "word": "slur", "severity": "low"|"medium"|"high" }"""
    user = await _require_admin(request)
    payload = await request.json()
    word = (payload.get("word") or "").strip().lower()
    severity = payload.get("severity") or "medium"
    if not word:
        raise HTTPException(status_code=400, detail="word is required")
    if severity not in ("low", "medium", "high"):
        raise HTTPException(status_code=400, detail="severity must be low|medium|high")
    existing = await _db().keyword_filters.find_one({"word": word})
    if existing:
        return {"ok": True, "filter_id": str(existing["_id"]), "deduped": True}
    res = await _db().keyword_filters.insert_one({
        "word": word,
        "severity": severity,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by_email": user.get("email"),
    })
    await refresh_keyword_cache()
    return {"ok": True, "filter_id": str(res.inserted_id), "deduped": False}


@router.delete("/keyword-filters/{filter_id}")
async def delete_keyword_filter(filter_id: str, request: Request):
    await _require_admin(request)
    try:
        oid = ObjectId(filter_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid id")
    res = await _db().keyword_filters.delete_one({"_id": oid})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Filter not found")
    await refresh_keyword_cache()
    return {"ok": True}


# ─────────────────────────────────────────────────────────────────────
# Admin: Account Integrity — multi-account detection via shared IPs
# ─────────────────────────────────────────────────────────────────────
@router.get("/account-integrity")
async def account_integrity(request: Request, limit: int = Query(50, ge=1, le=200)):
    """Surface groups of distinct users sharing the same IP within the
    last 30 days. Highest-overlap groups first."""
    await _require_admin(request)
    db = _db()
    pipeline = [
        {"$group": {
            "_id": "$ip",
            "user_ids": {"$addToSet": "$user_id"},
            "user_count": {"$sum": 1},
        }},
        {"$addFields": {"distinct_users": {"$size": "$user_ids"}}},
        {"$match": {"distinct_users": {"$gte": 2}}},
        {"$sort": {"distinct_users": -1}},
        {"$limit": limit},
    ]
    rows = await db.user_login_audit.aggregate(pipeline).to_list(limit)
    out = []
    for r in rows:
        ids = [uid for uid in (r.get("user_ids") or []) if uid]
        emails = []
        for uid in ids:
            try:
                u = await db.users.find_one({"_id": ObjectId(uid)}, {"email": 1, "status": 1})
                if u:
                    emails.append({
                        "user_id": str(u["_id"]),
                        "email": u.get("email"),
                        "status": u.get("status", "active"),
                    })
            except Exception:
                continue
        out.append({
            "ip": r["_id"],
            "distinct_users": r["distinct_users"],
            "login_count": r["user_count"],
            "users": emails,
        })
    return {"groups": out}


@router.get("/device-integrity")
async def device_integrity(request: Request, limit: int = Query(50, ge=1, le=200)):
    """Iter 207 — Surface groups of distinct users sharing the same
    device fingerprint (canvas/UA hash). Catches multi-accounting via
    VPN/IP rotation. `device_hash=null` rows are excluded."""
    await _require_admin(request)
    db = _db()
    pipeline = [
        {"$match": {"device_hash": {"$ne": None, "$exists": True}}},
        {"$group": {
            "_id": "$device_hash",
            "user_ids": {"$addToSet": "$user_id"},
            "login_count": {"$sum": 1},
        }},
        {"$addFields": {"distinct_users": {"$size": "$user_ids"}}},
        {"$match": {"distinct_users": {"$gte": 2}}},
        {"$sort": {"distinct_users": -1}},
        {"$limit": limit},
    ]
    rows = await db.user_login_audit.aggregate(pipeline).to_list(limit)
    out = []
    for r in rows:
        ids = [uid for uid in (r.get("user_ids") or []) if uid]
        emails = []
        for uid in ids:
            try:
                u = await db.users.find_one({"_id": ObjectId(uid)}, {"email": 1, "status": 1})
                if u:
                    emails.append({
                        "user_id": str(u["_id"]),
                        "email": u.get("email"),
                        "status": u.get("status", "active"),
                    })
            except Exception:
                continue
        out.append({
            "device_hash": r["_id"],
            "distinct_users": r["distinct_users"],
            "login_count": r["login_count"],
            "users": emails,
        })
    return {"groups": out}


# ─────────────────────────────────────────────────────────────────────
# Admin: Ban / Suspension Management
# ─────────────────────────────────────────────────────────────────────
@router.post("/users/{user_id}/ban")
async def ban_user(user_id: str, request: Request):
    """Body: { "reason_code": "harassment|fraud|cheating|other",
              "reason": "...",
              "duration_days": null | int (null=permanent) }
    """
    admin = await _require_admin(request)
    try:
        oid = ObjectId(user_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid user id")
    payload = await request.json()
    reason_code = payload.get("reason_code") or "other"
    if reason_code not in ("harassment", "fraud", "cheating", "collusion", "other"):
        raise HTTPException(status_code=400, detail="invalid reason_code")
    reason = (payload.get("reason") or "").strip()[:1000]
    duration_days = payload.get("duration_days")
    expires_at = None
    if duration_days is not None:
        try:
            duration_days = int(duration_days)
        except Exception:
            raise HTTPException(status_code=400, detail="duration_days must be int or null")
        if duration_days < 1:
            raise HTTPException(400, "duration_days must be positive")
        from datetime import timedelta
        expires_at = (datetime.now(timezone.utc) + timedelta(days=duration_days)).isoformat()

    status = "suspended" if duration_days else "banned"
    res = await _db().users.update_one(
        {"_id": oid},
        {"$set": {
            "status": status,
            "ban_reason_code": reason_code,
            "ban_reason": reason,
            "ban_expires_at": expires_at,
            "banned_at": datetime.now(timezone.utc).isoformat(),
            "banned_by": str(admin["_id"]),
            "banned_by_email": admin.get("email"),
        }, "$inc": {"token_version": 1}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    from services.account_access import disconnect_sessions
    await disconnect_sessions(_deps,user_id)
    return {"ok": True, "user_id": user_id, "status": status, "ban_expires_at": expires_at}


@router.post("/users/{user_id}/unban")
async def unban_user(user_id: str, request: Request):
    admin = await _require_admin(request)
    try:
        oid = ObjectId(user_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid user id")
    res = await _db().users.update_one(
        {"_id": oid},
        {"$set": {"status": "active"},
         "$unset": {
             "ban_reason_code": "", "ban_reason": "",
             "ban_expires_at": "", "banned_at": "",
         },
         "$push": {"ban_history": {
             "lifted_at": datetime.now(timezone.utc).isoformat(),
             "lifted_by_email": admin.get("email"),
         }}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    return {"ok": True, "user_id": user_id, "status": "active"}


@router.post("/users/{user_id}/flag-chargeback")
async def flag_chargeback(user_id: str, request: Request):
    """Manually flag a user for payment fraud (chargeback / stolen card).
    Body: { "amount_cents": int?, "reason": "...", "stripe_charge_id": "..."? }
    """
    admin = await _require_admin(request)
    try:
        oid = ObjectId(user_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid user id")
    payload = await request.json()
    flag = {
        "flagged_at": datetime.now(timezone.utc).isoformat(),
        "flagged_by_email": admin.get("email"),
        "amount_cents": payload.get("amount_cents"),
        "reason": (payload.get("reason") or "").strip()[:500],
        "stripe_charge_id": payload.get("stripe_charge_id"),
    }
    res = await _db().users.update_one(
        {"_id": oid},
        {"$push": {"chargeback_flags": flag},
         "$set": {"payment_fraud_flag": True}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    return {"ok": True, "user_id": user_id}


# ─────────────────────────────────────────────────────────────────────
# Appeals (public + admin)
# ─────────────────────────────────────────────────────────────────────
@appeals_router.post("/appeals")
async def submit_appeal(request: Request):
    """A banned/suspended user can submit one appeal. Body: { "message": "..." }"""
    user = await _deps["get_current_user"](request)
    if (user or {}).get("status") not in ("banned", "suspended"):
        raise HTTPException(status_code=400, detail="No active ban to appeal")
    payload = await request.json()
    message = (payload.get("message") or "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="message is required")
    existing = await _db().user_appeals.find_one({
        "user_id": str(user["_id"]),
        "status": "open",
    })
    if existing:
        return {"ok": True, "appeal_id": str(existing["_id"]), "deduped": True}
    doc = {
        "user_id": str(user["_id"]),
        "user_email": user.get("email"),
        "message": message[:2000],
        "status": "open",
        "ban_reason_code": user.get("ban_reason_code"),
        "ban_reason": user.get("ban_reason"),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    res = await _db().user_appeals.insert_one(doc)
    return {"ok": True, "appeal_id": str(res.inserted_id), "deduped": False}


@appeals_router.get("/appeals/mine")
async def my_appeals(request: Request):
    user = await _deps["get_current_user"](request)
    rows = await _db().user_appeals.find({"user_id": str(user["_id"])}).sort("created_at", -1).to_list(20)
    return {
        "appeals": [{
            "appeal_id": str(r["_id"]),
            "status": r.get("status"),
            "message": r.get("message"),
            "created_at": _iso(r.get("created_at")),
            "resolved_at": _iso(r.get("resolved_at")),
            "resolution_note": r.get("resolution_note"),
        } for r in rows]
    }


@router.get("/appeals")
async def admin_list_appeals(request: Request, status: str = Query("open", pattern=r"^(open|approved|denied|all)$")):
    await _require_admin(request)
    q = {} if status == "all" else {"status": status}
    rows = await _db().user_appeals.find(q).sort("created_at", -1).to_list(200)
    out = []
    for r in rows:
        out.append({
            "appeal_id": str(r["_id"]),
            "user_id": r.get("user_id"),
            "user_email": r.get("user_email"),
            "ban_reason_code": r.get("ban_reason_code"),
            "ban_reason": r.get("ban_reason"),
            "message": r.get("message"),
            "status": r.get("status"),
            "created_at": _iso(r.get("created_at")),
            "resolved_at": _iso(r.get("resolved_at")),
            "resolution_note": r.get("resolution_note"),
        })
    return {"appeals": out}


@router.post("/appeals/{appeal_id}/resolve")
async def admin_resolve_appeal(appeal_id: str, request: Request):
    """Body: { "action": "approved"|"denied", "note": "..." }
    Approving an appeal auto-unbans the user."""
    admin = await _require_admin(request)
    try:
        oid = ObjectId(appeal_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid appeal id")
    payload = await request.json()
    action = payload.get("action")
    if action not in ("approved", "denied"):
        raise HTTPException(status_code=400, detail="action must be approved|denied")
    appeal = await _db().user_appeals.find_one({"_id": oid, "status": "open"})
    if not appeal:
        raise HTTPException(status_code=404, detail="Appeal not found or already resolved")
    note = (payload.get("note") or "").strip()[:1000]
    await _db().user_appeals.update_one(
        {"_id": oid},
        {"$set": {
            "status": action,
            "resolved_at": datetime.now(timezone.utc).isoformat(),
            "resolved_by_email": admin.get("email"),
            "resolution_note": note,
        }},
    )
    if action == "approved":
        try:
            await _db().users.update_one(
                {"_id": ObjectId(appeal["user_id"])},
                {"$set": {"status": "active"},
                 "$unset": {"ban_reason_code": "", "ban_reason": "", "ban_expires_at": ""}},
            )
        except Exception:
            pass
    return {"ok": True, "appeal_id": appeal_id, "status": action}



# ─────────────────────────────────────────────────────────────────────
# Iter 208 — Trust Score
# ─────────────────────────────────────────────────────────────────────
async def _aliases_for(db, field: str, values: list, exclude_user_id: str):
    """Async generator yielding user_ids sharing any of `values` on
    `field` (ip or device_hash), excluding the user themselves."""
    cursor = db.user_login_audit.find(
        {field: {"$in": values}, "user_id": {"$ne": exclude_user_id}},
        {"user_id": 1},
    )
    async for row in cursor:
        if row.get("user_id"):
            yield row["user_id"]


@appeals_router.get("/users/{user_id}/trust-score")
async def get_user_trust_score(user_id: str, request: Request):
    """Compute a 0-100 trust score for a user. Available to any
    authenticated user (returns just score+tier). Admins also get the
    detailed breakdown.

    Components:
      - Account age (older = higher trust, capped at +30)
      - Resolved-against-them reports (each -10)
      - Mod-queue hits attributed to them (each -5)
      - Shared IP/device aliases (each unique alias -15)
      - Active ban (= 0) / suspension (-40)
      - Chargeback flags (each -25)
    Final score clamped to [0, 100]."""
    requester = await _deps["get_current_user"](request)
    db = _db()
    try:
        oid = ObjectId(user_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid user id")
    user = await db.users.find_one({"_id": oid})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    score = 70
    breakdown: dict = {}

    # Account age bonus (+1 every 24 days, max +30 at ~2 years)
    created = user.get("created_at")
    if created:
        try:
            if isinstance(created, str):
                created_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
            else:
                created_dt = created if created.tzinfo else created.replace(tzinfo=timezone.utc)
            age_days = (datetime.now(timezone.utc) - created_dt).days
            age_bonus = min(30, max(0, age_days // 24))
            breakdown["account_age_days"] = age_days
            breakdown["account_age_bonus"] = age_bonus
            score += age_bonus
        except Exception:
            pass

    reports_against = await db.user_reports.count_documents({
        "target_user_id": user_id,
        "status": "resolved",
        "resolution_action": {"$in": ["warning", "timeout", "ban"]},
    })
    breakdown["reports_resolved_against"] = reports_against
    score -= reports_against * 10

    mod_hits = await db.moderation_queue.count_documents({
        "author_id": user_id,
        "status": {"$in": ["pending", "deleted"]},
    })
    breakdown["mod_queue_hits"] = mod_hits
    score -= mod_hits * 5

    aggregated = await db.user_login_audit.aggregate([
        {"$match": {"user_id": user_id}},
        {"$group": {"_id": None,
                    "ips": {"$addToSet": "$ip"},
                    "devices": {"$addToSet": "$device_hash"}}},
    ]).to_list(1)
    ip_count = 0
    dev_count = 0
    if aggregated:
        my_ips = [i for i in (aggregated[0].get("ips") or []) if i]
        my_devices = [d for d in (aggregated[0].get("devices") or []) if d]
        if my_ips:
            ip_count = len({uid async for uid in _aliases_for(db, "ip", my_ips, user_id)})
        if my_devices:
            dev_count = len({uid async for uid in _aliases_for(db, "device_hash", my_devices, user_id)})
    breakdown["ip_aliases"] = ip_count
    breakdown["device_aliases"] = dev_count
    score -= (ip_count + dev_count) * 15

    status_val = user.get("status", "active")
    breakdown["status"] = status_val
    if status_val == "banned":
        score = 0
    elif status_val == "suspended":
        score -= 40

    chargebacks = len(user.get("chargeback_flags") or [])
    breakdown["chargeback_flags"] = chargebacks
    score -= chargebacks * 25

    final = max(0, min(100, score))
    tier = (
        "trusted" if final >= 75
        else "neutral" if final >= 40
        else "watch" if final >= 15
        else "risky"
    )

    payload = {"user_id": user_id, "score": final, "tier": tier}
    if (requester or {}).get("role") == "admin":
        payload["breakdown"] = breakdown
    return payload
