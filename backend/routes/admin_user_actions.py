"""
Iter 215 — Admin User Actions framework.

Comprehensive admin action endpoints that operate against a single
target user. Each action:
  * Requires admin authentication (tiered: senior_admin for irreversible
    actions like permanent ban / hard delete; moderator for soft actions
    like mute / warning).
  * Captures the prior state of the user document before mutating.
  * Logs an audit row to `admin_user_actions` collection with
    `admin_id`, `admin_email`, `target_user_id`, `action`, `reason`,
    `metadata`, `prior_state`, `ts`.
  * Sends a `notifications` row to the target user when applicable
    (suspend, ban, unban, warning, mute, deactivate, hard delete,
    password reset, impersonation start).

Categories implemented:
  • Account Status: suspend, ban, unban, reinstate, force_logout,
    deactivate, reactivate, delete (soft / hard).
  • Identity & Access: reset_password, verify_email, verify_phone,
    edit_username, merge_accounts (STUB), unlink_sso, revoke_session.
  • League/Team: remove_from_league, transfer_commissioner,
    reverse_trade (delegated to admin_platform), reset_team (STUB),
    force_remove_from_draft (STUB).
  • Moderation: issue_warning, mute, unmute, delete_content (STUB),
    flag_for_review, unflag, add_internal_note (delegated to
    platform_ops).
  • Financial: refund (STUB), adjust_tier, void_payout (STUB),
    manual_payout (STUB), promo_credit.
  • Support: impersonate, resend_verification, link_support_ticket
    (STUB), export_data, gdpr_delete (queues hard-delete).

Mocked/stubbed actions are clearly returned with `ok: True, mocked: True`
so the UI can render successfully while the underlying side-effect is
deferred to a follow-up iteration (Stripe refund flow, GDPR pipeline,
real account merge, etc.).
"""
from __future__ import annotations

import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/admin/platform/users", tags=["admin-user-actions"])

_deps: dict = {}

# Actions that require senior_admin tier (permanent / irreversible)
_SENIOR_ACTIONS = {
    "ban_permanent", "delete_hard", "gdpr_delete", "merge_accounts",
    "refund", "manual_payout", "void_payout",
}

# Actions that a moderator (tier=moderator) is allowed to perform
_MODERATOR_ACTIONS = {
    "issue_warning", "mute", "unmute", "flag_for_review", "unflag",
    "delete_content", "add_internal_note",
}


def setup(deps: dict) -> None:
    _deps.update(deps)


def _db():
    return _deps["db"]


def _iso(dt) -> str | None:
    if not dt:
        return None
    if isinstance(dt, str):
        return dt
    return dt.isoformat() if hasattr(dt, "isoformat") else str(dt)


async def _require_admin(request: Request, action: str) -> dict:
    """Tiered permission resolver. The user's `permission_tier` field
    can be one of {moderator, admin, senior_admin}. If absent, we fall
    back to the legacy `role` field where `role=admin` ≡ senior_admin.

    Iter 216 — Impersonation write-guard: if the caller's JWT is a
    `type=impersonation` token (read-only view-as), every action endpoint
    is blocked. The admin must exit impersonation mode before taking
    real action.
    """
    user = await _deps["get_current_user"](request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    if user.get("_impersonation_mode") == "read_only":
        raise HTTPException(
            status_code=403,
            detail="Read-only impersonation mode is active — exit view-as to perform admin actions",
        )
    role = (user or {}).get("role")
    tier = (user or {}).get("permission_tier")
    if not tier:
        tier = "senior_admin" if role == "admin" else (
            "moderator" if role == "moderator" else "user"
        )
    if action in _SENIOR_ACTIONS and tier != "senior_admin":
        raise HTTPException(
            status_code=403,
            detail=f"Action '{action}' requires senior_admin tier",
        )
    if tier == "moderator" and action not in _MODERATOR_ACTIONS:
        raise HTTPException(
            status_code=403,
            detail=f"Action '{action}' requires admin tier (moderators may only perform soft actions)",
        )
    if tier not in ("moderator", "admin", "senior_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


async def _load_user(user_id: str) -> dict:
    try:
        oid = ObjectId(user_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid user id")
    u = await _db().users.find_one({"_id": oid})
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    return u


async def _audit(
    *,
    admin: dict,
    target_user_id: str,
    action: str,
    reason: str | None = None,
    metadata: dict | None = None,
    prior_state: dict | None = None,
    mocked: bool = False,
) -> str:
    """Write an audit row + return its id (string)."""
    doc = {
        "admin_id": str(admin.get("_id") or admin.get("id")),
        "admin_email": admin.get("email"),
        "admin_tier": admin.get("permission_tier") or admin.get("role") or "admin",
        "target_user_id": target_user_id,
        "action": action,
        "reason": reason,
        "metadata": metadata or {},
        "prior_state": prior_state or {},
        "mocked": mocked,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    res = await _db().admin_user_actions.insert_one(doc)
    return str(res.inserted_id)


async def _notify_user(
    *,
    user_id: str,
    title: str,
    body: str,
    action: str,
    appeal_path: str | None = None,
) -> None:
    """Drop a row in the notifications collection so the user sees an
    in-app message explaining the moderation action."""
    try:
        await _db().notifications.insert_one({
            "user_id": user_id,
            "type": f"admin_action.{action}",
            "title": title,
            "body": body,
            "read": False,
            "appeal_path": appeal_path,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
    except Exception:
        pass  # never let notification failure block the action


# ─────────────────────────────────────────────────────────────────────
# Account Status
# ─────────────────────────────────────────────────────────────────────
@router.post("/{user_id}/suspend")
async def suspend_user(user_id: str, request: Request):
    """Body: { duration_days: int (>0), reason_code: str, reason: str }"""
    admin = await _require_admin(request, "suspend")
    u = await _load_user(user_id)
    payload = await request.json()
    days = int(payload.get("duration_days") or 0)
    if days < 1:
        raise HTTPException(status_code=400, detail="duration_days must be >= 1")
    reason_code = (payload.get("reason_code") or "other").strip()
    reason = (payload.get("reason") or "").strip()
    expires = (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()
    prior = {"status": u.get("status"), "ban_expires_at": u.get("ban_expires_at")}
    await _db().users.update_one(
        {"_id": u["_id"]},
        {"$set": {
            "status": "suspended", "ban_reason_code": reason_code,
            "ban_reason": reason, "ban_expires_at": expires,
            "banned_by_email": admin.get("email"),
        }},
    )
    aid = await _audit(admin=admin, target_user_id=user_id, action="suspend",
                       reason=reason, metadata={"duration_days": days, "reason_code": reason_code,
                                                 "expires_at": expires}, prior_state=prior)
    await _notify_user(user_id=user_id, action="suspend",
                       title=f"Your account is suspended for {days} day(s)",
                       body=f"Reason: {reason or reason_code}. You will regain access on {expires}.",
                       appeal_path="/appeals")
    return {"ok": True, "audit_id": aid, "expires_at": expires}


@router.post("/{user_id}/ban-permanent")
async def ban_permanent(user_id: str, request: Request):
    """Body: { reason_code, reason, confirm: true, second_signoff_admin_email?: str }
    Permanent ban. Requires senior_admin tier + explicit confirmation flag.
    Distinct from the iter 206 /ban endpoint (which is for timed suspensions)."""
    admin = await _require_admin(request, "ban_permanent")
    u = await _load_user(user_id)
    payload = await request.json()
    if not payload.get("confirm"):
        raise HTTPException(status_code=400, detail="confirm=true is required for permanent ban")
    reason_code = (payload.get("reason_code") or "other").strip()
    reason = (payload.get("reason") or "").strip()
    second = payload.get("second_signoff_admin_email")
    prior = {"status": u.get("status")}
    await _db().users.update_one(
        {"_id": u["_id"]},
        {"$set": {
            "status": "banned", "ban_reason_code": reason_code, "ban_reason": reason,
            "ban_expires_at": None, "banned_by_email": admin.get("email"),
            "banned_at": datetime.now(timezone.utc).isoformat(),
            "second_signoff_admin_email": second,
        }},
    )
    aid = await _audit(admin=admin, target_user_id=user_id, action="ban_permanent",
                       reason=reason, metadata={"reason_code": reason_code,
                                                 "second_signoff_admin_email": second},
                       prior_state=prior)
    await _notify_user(user_id=user_id, action="ban_permanent",
                       title="Your account has been permanently banned",
                       body=f"Reason: {reason or reason_code}. You may submit an appeal.",
                       appeal_path="/appeals")
    return {"ok": True, "audit_id": aid}


@router.post("/{user_id}/reinstate")
async def reinstate_user(user_id: str, request: Request):
    """Body: { note: str }
    Lifts ban / suspension. Logs the admin's note (especially important
    for ban appeals)."""
    admin = await _require_admin(request, "reinstate")
    u = await _load_user(user_id)
    payload = await request.json()
    note = (payload.get("note") or "").strip()
    prior = {"status": u.get("status"), "ban_reason": u.get("ban_reason")}
    await _db().users.update_one(
        {"_id": u["_id"]},
        {"$set": {"status": "active"},
         "$unset": {"ban_reason_code": "", "ban_reason": "", "ban_expires_at": "",
                    "banned_by_email": "", "banned_at": ""}},
    )
    aid = await _audit(admin=admin, target_user_id=user_id, action="reinstate",
                       reason=note, prior_state=prior)
    await _notify_user(user_id=user_id, action="reinstate",
                       title="Your account has been reinstated",
                       body=f"Note from the admin team: {note or 'Reinstated.'}")
    return {"ok": True, "audit_id": aid}


@router.post("/{user_id}/force-logout")
async def force_logout(user_id: str, request: Request):
    """Revokes ALL active sessions immediately. Implementation: bumps
    `token_version` on the user (JWT verifier should reject older
    tokens) AND flips `revoked=true` on every `user_sessions` row."""
    admin = await _require_admin(request, "force_logout")
    u = await _load_user(user_id)
    new_version = int(u.get("token_version") or 0) + 1
    await _db().users.update_one(
        {"_id": u["_id"]},
        {"$set": {"token_version": new_version}},
    )
    revoke_res = await _db().user_sessions.update_many(
        {"user_id": user_id, "revoked": {"$ne": True}},
        {"$set": {"revoked": True, "revoked_at": datetime.now(timezone.utc).isoformat(),
                  "revoked_by_admin": admin.get("email")}},
    )
    aid = await _audit(admin=admin, target_user_id=user_id, action="force_logout",
                       metadata={"token_version": new_version,
                                 "sessions_revoked": revoke_res.modified_count})
    return {"ok": True, "audit_id": aid, "sessions_revoked": revoke_res.modified_count}


@router.post("/{user_id}/deactivate")
async def deactivate_user(user_id: str, request: Request):
    """Soft deactivation. Body: { reason?: str }. Account hidden + login
    blocked, but data preserved. Reversible via /reactivate."""
    admin = await _require_admin(request, "deactivate")
    u = await _load_user(user_id)
    payload = await request.json() if request.headers.get("content-length") else {}
    reason = (payload.get("reason") or "").strip()
    prior = {"status": u.get("status"), "is_active": u.get("is_active", True)}
    await _db().users.update_one(
        {"_id": u["_id"]},
        {"$set": {"status": "deactivated", "is_active": False,
                  "deactivated_at": datetime.now(timezone.utc).isoformat()}},
    )
    aid = await _audit(admin=admin, target_user_id=user_id, action="deactivate",
                       reason=reason, prior_state=prior)
    await _notify_user(user_id=user_id, action="deactivate",
                       title="Account deactivated",
                       body=f"Your account has been deactivated. Reason: {reason or 'admin action'}.")
    return {"ok": True, "audit_id": aid}


@router.post("/{user_id}/reactivate")
async def reactivate_user(user_id: str, request: Request):
    admin = await _require_admin(request, "reactivate")
    u = await _load_user(user_id)
    prior = {"status": u.get("status"), "is_active": u.get("is_active")}
    await _db().users.update_one(
        {"_id": u["_id"]},
        {"$set": {"status": "active", "is_active": True},
         "$unset": {"deactivated_at": ""}},
    )
    aid = await _audit(admin=admin, target_user_id=user_id, action="reactivate", prior_state=prior)
    return {"ok": True, "audit_id": aid}


@router.post("/{user_id}/delete")
async def delete_user(user_id: str, request: Request):
    """Hard delete (anonymization). Body: { confirm: true, reason: str }.
    Requires senior_admin tier. PII is anonymized but the document is
    kept so historical league data (rosters, trades) remains intact."""
    admin = await _require_admin(request, "delete_hard")
    u = await _load_user(user_id)
    payload = await request.json()
    if not payload.get("confirm"):
        raise HTTPException(status_code=400, detail="confirm=true is required")
    reason = (payload.get("reason") or "").strip()
    prior = {"email": u.get("email"), "username": u.get("username"),
             "name": u.get("name"), "phone": u.get("phone")}
    anon_marker = f"deleted_user_{ObjectId()}"
    await _db().users.update_one(
        {"_id": u["_id"]},
        {"$set": {
            "status": "deleted", "is_active": False,
            "email": f"{anon_marker}@anonymised.local",
            "username": anon_marker, "name": anon_marker,
            "phone": None,
            "deleted_at": datetime.now(timezone.utc).isoformat(),
            "deleted_by_admin": admin.get("email"),
        },
         "$unset": {"password_hash": "", "linked_sso_accounts": "",
                    "recovery_email": "", "security_questions": ""}},
    )
    aid = await _audit(admin=admin, target_user_id=user_id, action="delete_hard",
                       reason=reason, prior_state=prior)
    return {"ok": True, "audit_id": aid, "anon_marker": anon_marker}


# ─────────────────────────────────────────────────────────────────────
# Identity & Access
# ─────────────────────────────────────────────────────────────────────
@router.post("/{user_id}/reset-password")
async def reset_password(user_id: str, request: Request):
    """Force a password reset. Generates a single-use token, stores it
    on `password_reset_audit`, and (in production) triggers an email
    via SendGrid. Returns the token so the admin can confirm it was
    generated; admin never sees the password itself."""
    admin = await _require_admin(request, "reset_password")
    await _load_user(user_id)
    expires = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
    await _db().password_reset_audit.insert_one({
        "user_id": user_id, "token_hash": secrets.token_hex(16),
        "issued_by_admin": admin.get("email"),
        "issued_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": expires, "outcome": "issued",
    })
    aid = await _audit(admin=admin, target_user_id=user_id, action="reset_password",
                       metadata={"expires_at": expires}, mocked=True)
    await _notify_user(user_id=user_id, action="reset_password",
                       title="Password reset requested by admin",
                       body="A password reset email has been sent. Use the link to set a new password.")
    return {"ok": True, "audit_id": aid, "expires_at": expires, "mocked": True,
            "note": "Email delivery STUBBED — wire SendGrid send_email in production"}


@router.post("/{user_id}/verify-email")
async def verify_email(user_id: str, request: Request):
    admin = await _require_admin(request, "verify_email")
    u = await _load_user(user_id)
    prior = {"email_verified": u.get("email_verified", False)}
    await _db().users.update_one({"_id": u["_id"]}, {"$set": {"email_verified": True}})
    aid = await _audit(admin=admin, target_user_id=user_id, action="verify_email", prior_state=prior)
    return {"ok": True, "audit_id": aid}


@router.post("/{user_id}/verify-phone")
async def verify_phone(user_id: str, request: Request):
    admin = await _require_admin(request, "verify_phone")
    u = await _load_user(user_id)
    prior = {"phone_verified": u.get("phone_verified", False)}
    await _db().users.update_one({"_id": u["_id"]}, {"$set": {"phone_verified": True}})
    aid = await _audit(admin=admin, target_user_id=user_id, action="verify_phone", prior_state=prior)
    return {"ok": True, "audit_id": aid}


@router.post("/{user_id}/edit-username")
async def edit_username(user_id: str, request: Request):
    """Body: { username: str, reason?: str }
    Admin override of the normal change-frequency limit. Records the
    transition in user_audit_log for the history table."""
    admin = await _require_admin(request, "edit_username")
    u = await _load_user(user_id)
    payload = await request.json()
    new_username = (payload.get("username") or "").strip()
    reason = (payload.get("reason") or "").strip()
    if not new_username:
        raise HTTPException(status_code=400, detail="username is required")
    old = u.get("username")
    await _db().users.update_one({"_id": u["_id"]}, {"$set": {"username": new_username}})
    await _db().user_audit_log.insert_one({
        "user_id": user_id, "event_type": "username_changed",
        "from_value": old, "to_value": new_username,
        "ts": datetime.now(timezone.utc).isoformat(),
        "by_admin": admin.get("email"), "reason": reason,
    })
    aid = await _audit(admin=admin, target_user_id=user_id, action="edit_username",
                       reason=reason, prior_state={"username": old},
                       metadata={"new_username": new_username})
    return {"ok": True, "audit_id": aid}


@router.post("/{user_id}/merge-accounts")
async def merge_accounts(user_id: str, request: Request):
    """Body: { source_user_id: str, reason: str }
    Merges source → target (user_id). Real migration:
      • teams.owner_id, teams.owner_history append
      • trades.proposer_team_owner_id, target_team_owner_id
      • league_invites.sender_id, recipient_user_id
      • user_reports.reporter_id, target_user_id
      • forum_threads.author_id, forum_posts.author_id
      • notifications.user_id
      • user_login_audit.user_id
      • admin_user_actions.target_user_id, admin_id
    Merges relevant scalar fields (warnings, watchlist, payment_methods,
    promo_credits_cents, trust_score) into the target. Source user is
    soft-deleted (status='merged_into_other_account')."""
    admin = await _require_admin(request, "merge_accounts")
    target = await _load_user(user_id)
    payload = await request.json()
    source_id = (payload.get("source_user_id") or "").strip()
    reason = (payload.get("reason") or "").strip()
    if not source_id:
        raise HTTPException(status_code=400, detail="source_user_id is required")
    if source_id == user_id:
        raise HTTPException(status_code=400, detail="source and target are the same user")
    source = await _load_user(source_id)
    db = _db()

    # Reassignments. We capture row counts for the audit log.
    counts = {}

    counts["teams_owner_id"] = (await db.teams.update_many(
        {"owner_id": source_id}, {"$set": {"owner_id": user_id}}
    )).modified_count

    # Append source to teams.owner_history so storytelling can still
    # reconstruct who-played-where-when.
    counts["teams_history_appended"] = (await db.teams.update_many(
        {"owner_id": user_id, "owner_history": {"$not": {"$elemMatch": {"user_id": source_id}}}},
        {"$push": {"owner_history": {
            "user_id": source_id, "merged_at": datetime.now(timezone.utc).isoformat(),
            "merge_reason": reason,
        }}},
    )).modified_count

    counts["trades_proposer"] = (await db.trades.update_many(
        {"proposer_team_owner_id": source_id},
        {"$set": {"proposer_team_owner_id": user_id}},
    )).modified_count

    counts["trades_target"] = (await db.trades.update_many(
        {"target_team_owner_id": source_id},
        {"$set": {"target_team_owner_id": user_id}},
    )).modified_count

    counts["invites_sender"] = (await db.league_invites.update_many(
        {"sender_id": source_id}, {"$set": {"sender_id": user_id}}
    )).modified_count

    counts["invites_recipient"] = (await db.league_invites.update_many(
        {"recipient_user_id": source_id},
        {"$set": {"recipient_user_id": user_id}},
    )).modified_count

    counts["reports_reporter"] = (await db.user_reports.update_many(
        {"reporter_id": source_id}, {"$set": {"reporter_id": user_id}}
    )).modified_count

    counts["reports_target"] = (await db.user_reports.update_many(
        {"target_user_id": source_id}, {"$set": {"target_user_id": user_id}}
    )).modified_count

    counts["forum_threads"] = (await db.forum_threads.update_many(
        {"author_id": source_id}, {"$set": {"author_id": user_id}}
    )).modified_count

    counts["forum_posts"] = (await db.forum_posts.update_many(
        {"author_id": source_id}, {"$set": {"author_id": user_id}}
    )).modified_count

    counts["notifications"] = (await db.notifications.update_many(
        {"user_id": source_id}, {"$set": {"user_id": user_id}}
    )).modified_count

    counts["login_audit"] = (await db.user_login_audit.update_many(
        {"user_id": source_id}, {"$set": {"user_id": user_id}}
    )).modified_count

    counts["admin_actions_target"] = (await db.admin_user_actions.update_many(
        {"target_user_id": source_id}, {"$set": {"target_user_id": user_id}}
    )).modified_count

    counts["chat_messages"] = (await db.chat_messages.update_many(
        {"sender_id": source_id}, {"$set": {"sender_id": user_id}}
    )).modified_count

    counts["roster_snapshots"] = (await db.roster_snapshots.update_many(
        {"owner_id": source_id}, {"$set": {"owner_id": user_id}}
    )).modified_count

    # Merge scalar fields into target
    merged_warnings = (target.get("warnings") or []) + (source.get("warnings") or [])
    merged_payment = (target.get("payment_methods") or []) + (source.get("payment_methods") or [])
    target_credits = int(target.get("promo_credits_cents") or 0)
    source_credits = int(source.get("promo_credits_cents") or 0)
    await db.users.update_one(
        {"_id": target["_id"]},
        {"$set": {
            "warnings": merged_warnings,
            "payment_methods": merged_payment,
            "promo_credits_cents": target_credits + source_credits,
            "trust_score": min(target.get("trust_score") or 100,
                                source.get("trust_score") or 100),
            "watchlist": bool(target.get("watchlist") or source.get("watchlist")),
            "merged_from_user_ids": (target.get("merged_from_user_ids") or []) + [source_id],
        }},
    )

    # Soft-delete source
    await db.users.update_one(
        {"_id": source["_id"]},
        {"$set": {
            "status": "merged_into_other_account",
            "is_active": False,
            "merged_into_user_id": user_id,
            "merged_at": datetime.now(timezone.utc).isoformat(),
            "merged_by_admin": admin.get("email"),
            "merge_reason": reason,
            "original_email_before_merge": source.get("email"),
            "email": f"merged_{ObjectId()}@anonymised.local",
        },
         "$unset": {"password_hash": ""}},
    )

    aid = await _audit(admin=admin, target_user_id=user_id, action="merge_accounts",
                       reason=reason,
                       metadata={"source_user_id": source_id, "counts": counts},
                       prior_state={"source_email": source.get("email")})
    return {"ok": True, "audit_id": aid, "counts": counts}


@router.post("/{user_id}/unlink-sso")
async def unlink_sso(user_id: str, request: Request):
    """Body: { provider: 'google'|'apple'|... }"""
    admin = await _require_admin(request, "unlink_sso")
    u = await _load_user(user_id)
    payload = await request.json()
    provider = (payload.get("provider") or "").strip()
    if not provider:
        raise HTTPException(status_code=400, detail="provider is required")
    linked = u.get("linked_sso_accounts") or []
    new_linked = [s for s in linked if (s.get("provider") if isinstance(s, dict) else s) != provider]
    await _db().users.update_one({"_id": u["_id"]}, {"$set": {"linked_sso_accounts": new_linked}})
    aid = await _audit(admin=admin, target_user_id=user_id, action="unlink_sso",
                       metadata={"provider": provider}, prior_state={"linked_sso_accounts": linked})
    return {"ok": True, "audit_id": aid}


@router.post("/{user_id}/revoke-session")
async def revoke_session(user_id: str, request: Request):
    """Body: { session_id: str }"""
    admin = await _require_admin(request, "revoke_session")
    payload = await request.json()
    sid = (payload.get("session_id") or "").strip()
    if not sid:
        raise HTTPException(status_code=400, detail="session_id is required")
    try:
        oid = ObjectId(sid)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid session_id")
    res = await _db().user_sessions.update_one(
        {"_id": oid, "user_id": user_id},
        {"$set": {"revoked": True, "revoked_at": datetime.now(timezone.utc).isoformat(),
                  "revoked_by_admin": admin.get("email")}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Session not found")
    aid = await _audit(admin=admin, target_user_id=user_id, action="revoke_session",
                       metadata={"session_id": sid})
    return {"ok": True, "audit_id": aid}


# ─────────────────────────────────────────────────────────────────────
# League / Team
# ─────────────────────────────────────────────────────────────────────
@router.post("/{user_id}/remove-from-league")
async def remove_from_league(user_id: str, request: Request):
    """Body: { league_id: str, handover_mode: 'commissioner'|'ai'|'pause',
              reason: str }"""
    admin = await _require_admin(request, "remove_from_league")
    payload = await request.json()
    league_id = (payload.get("league_id") or "").strip()
    handover = (payload.get("handover_mode") or "commissioner").strip()
    reason = (payload.get("reason") or "").strip()
    if not league_id:
        raise HTTPException(status_code=400, detail="league_id is required")
    if handover not in ("commissioner", "ai", "pause"):
        raise HTTPException(status_code=400, detail="invalid handover_mode")
    db = _db()
    team = await db.teams.find_one({"league_id": league_id, "owner_id": user_id})
    if not team:
        raise HTTPException(status_code=404, detail="No team owned by this user in that league")
    prior = {"team_id": str(team["_id"]), "owner_id": user_id,
             "handover_mode": handover}
    update = {"owner_id": None, "owner_handover_mode": handover,
              "owner_removed_at": datetime.now(timezone.utc).isoformat()}
    if handover == "pause":
        await db.leagues.update_one({"_id": ObjectId(league_id)}, {"$set": {"status": "paused"}})
    await db.teams.update_one({"_id": team["_id"]}, {"$set": update})
    aid = await _audit(admin=admin, target_user_id=user_id, action="remove_from_league",
                       reason=reason, prior_state=prior,
                       metadata={"league_id": league_id, "handover_mode": handover})
    return {"ok": True, "audit_id": aid, "team_id": str(team["_id"])}


@router.post("/{user_id}/transfer-commissioner")
async def transfer_commissioner(user_id: str, request: Request):
    """Body: { league_id, new_commissioner_user_id, reason }
    user_id = current commissioner being demoted."""
    admin = await _require_admin(request, "transfer_commissioner")
    payload = await request.json()
    league_id = (payload.get("league_id") or "").strip()
    new_commish = (payload.get("new_commissioner_user_id") or "").strip()
    reason = (payload.get("reason") or "").strip()
    if not (league_id and new_commish):
        raise HTTPException(status_code=400, detail="league_id and new_commissioner_user_id required")
    try:
        lg = await _db().leagues.find_one({"_id": ObjectId(league_id)})
    except Exception:
        lg = None
    if not lg:
        raise HTTPException(status_code=404, detail="League not found")
    prior = {"commissioner_id": lg.get("commissioner_id")}
    await _db().leagues.update_one(
        {"_id": ObjectId(league_id)},
        {"$set": {"commissioner_id": new_commish}},
    )
    aid = await _audit(admin=admin, target_user_id=user_id, action="transfer_commissioner",
                       reason=reason, prior_state=prior,
                       metadata={"league_id": league_id, "new_commissioner_user_id": new_commish})
    return {"ok": True, "audit_id": aid}


@router.post("/{user_id}/force-remove-from-draft")
async def force_remove_from_draft(user_id: str, request: Request):
    """Iter 221 — Real eviction (was stub). Flips the user's team(s) to
    autopick mode AND, if their team is currently on the clock, drains
    every consecutive pick they owe via the shared auto-pick helper.
    Body: { draft_id, reason }.
    """
    admin = await _require_admin(request, "force_remove_from_draft")
    payload = await request.json()
    draft_id = (payload.get("draft_id") or "").strip()
    reason = (payload.get("reason") or "").strip()
    if not draft_id:
        raise HTTPException(status_code=400, detail="draft_id required")

    try:
        oid = ObjectId(draft_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid draft_id")

    draft = await _db().drafts.find_one({"_id": oid})
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")

    # Flag the user's team(s) in this league for autopick going forward.
    update_res = await _db().teams.update_many(
        {"league_id": draft.get("league_id"), "owner_id": user_id},
        {"$set": {
            "autopick_enabled": True,
            "autopick_forced_at": datetime.now(timezone.utc).isoformat(),
            "autopick_forced_by_admin": admin["_id"],
        }},
    )
    if update_res.matched_count == 0:
        raise HTTPException(
            status_code=404,
            detail=f"User has no team in league {draft.get('league_id')}",
        )

    # Drain on-clock picks: while the draft is active and the next on-clock
    # team belongs to the evicted user, execute auto-pick. Bounded by total
    # picks to be safe.
    # Iter 231n — Direct import (no more late-bound `from routes.drafts`).
    from routes.draft_helpers import perform_one_auto_pick
    from draft_engine import get_team_for_pick

    drained: list = []
    max_iters = max(1, int(draft.get("total_rounds", 1)) * len(draft.get("team_abbrs", []) or []))
    for _ in range(max_iters):
        cur = await _db().drafts.find_one({"_id": oid})
        if not cur or cur.get("status") != "active":
            break
        on_clock = get_team_for_pick(cur["team_abbrs"], cur["current_pick"], cur["snake_draft"])
        on_clock_team_id = (cur.get("team_map") or {}).get(on_clock, {}).get("id")
        if not on_clock_team_id:
            break
        on_clock_team = await _db().teams.find_one({"_id": ObjectId(on_clock_team_id)})
        if not on_clock_team or on_clock_team.get("owner_id") != user_id:
            break
        pick = await perform_one_auto_pick(draft_id, source="eviction")
        drained.append(pick)

    aid = await _audit(
        admin=admin, target_user_id=user_id, action="force_remove_from_draft",
        reason=reason,
        metadata={
            "draft_id": draft_id,
            "teams_flagged": update_res.matched_count,
            "picks_drained": len(drained),
        },
    )
    await _notify_user(
        user_id=user_id, action="force_remove_from_draft",
        title="Removed from draft",
        body=(f"You were removed from the active draft by an admin. "
              f"Your team is now on auto-pick. {len(drained)} pick(s) were drained."),
    )
    return {
        "ok": True,
        "audit_id": aid,
        "teams_flagged": update_res.matched_count,
        "picks_drained": len(drained),
    }


@router.post("/{user_id}/reset-team")
async def reset_team(user_id: str, request: Request):
    """Body: { team_id: str, snapshot_id: str, reason: str }
    Restore a team's roster/lineup/IR/taxi/cap/FAAB from a prior
    snapshot. Takes a pre-restore snapshot first so the restore is
    itself reversible. Snapshots are managed via
    `/api/teams/{team_id}/snapshots`."""
    admin = await _require_admin(request, "reset_team")
    payload = await request.json()
    team_id = (payload.get("team_id") or "").strip()
    snapshot_id = (payload.get("snapshot_id") or "").strip()
    reason = (payload.get("reason") or "").strip()
    if not (team_id and snapshot_id):
        raise HTTPException(status_code=400, detail="team_id and snapshot_id are required")
    db = _db()
    try:
        team = await db.teams.find_one({"_id": ObjectId(team_id)})
        snap = await db.roster_snapshots.find_one(
            {"_id": ObjectId(snapshot_id), "team_id": team_id}
        )
    except Exception:
        team = snap = None
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    if not snap:
        raise HTTPException(status_code=404, detail="Snapshot not found for this team")
    # Pre-restore safety snapshot (so the admin can undo the restore)
    pre_snap_doc = {
        "team_id": team_id, "league_id": team.get("league_id"),
        "owner_id": team.get("owner_id"),
        "taken_at": datetime.now(timezone.utc).isoformat(),
        "taken_by": admin.get("email"),
        "reason": f"pre_admin_reset_of_{snapshot_id}",
        "roster": team.get("roster") or [], "lineup": team.get("lineup") or {},
        "ir": team.get("ir") or [], "taxi": team.get("taxi") or [],
        "salary_cap_used_cents": team.get("salary_cap_used_cents"),
        "faab_remaining": team.get("faab_remaining"),
        "metadata": {"admin_action": "reset_team"},
    }
    pre_res = await db.roster_snapshots.insert_one(pre_snap_doc)
    await db.teams.update_one(
        {"_id": team["_id"]},
        {"$set": {
            "roster": snap.get("roster") or [],
            "lineup": snap.get("lineup") or {},
            "ir": snap.get("ir") or [],
            "taxi": snap.get("taxi") or [],
            "salary_cap_used_cents": snap.get("salary_cap_used_cents"),
            "faab_remaining": snap.get("faab_remaining"),
            "last_restored_from": snapshot_id,
            "last_restored_at": datetime.now(timezone.utc).isoformat(),
            "last_restored_by": admin.get("email"),
        }},
    )
    aid = await _audit(admin=admin, target_user_id=user_id, action="reset_team",
                       reason=reason,
                       metadata={"team_id": team_id, "snapshot_id": snapshot_id,
                                 "pre_restore_snapshot_id": str(pre_res.inserted_id)})
    return {"ok": True, "audit_id": aid,
            "restored_from_snapshot": snapshot_id,
            "pre_restore_snapshot_id": str(pre_res.inserted_id)}


# ─────────────────────────────────────────────────────────────────────
# Moderation
# ─────────────────────────────────────────────────────────────────────
@router.post("/{user_id}/warning")
async def issue_warning(user_id: str, request: Request):
    """Body: { reason: str }. Tiered: 3rd warning auto-suspends 3 days."""
    admin = await _require_admin(request, "issue_warning")
    u = await _load_user(user_id)
    payload = await request.json()
    reason = (payload.get("reason") or "").strip()
    warnings = u.get("warnings") or []
    new_warning = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "issued_by_email": admin.get("email"),
        "reason": reason,
    }
    warnings.append(new_warning)
    update: dict = {"warnings": warnings}
    auto_suspended = False
    current_status = u.get("status") or ("active" if u.get("is_active", True) else "inactive")
    if len(warnings) >= 3 and current_status == "active":
        update.update({
            "status": "suspended", "ban_reason_code": "auto_three_warnings",
            "ban_reason": "Automatic 3-day suspension after 3rd warning",
            "ban_expires_at": (datetime.now(timezone.utc) + timedelta(days=3)).isoformat(),
        })
        auto_suspended = True
    await _db().users.update_one({"_id": u["_id"]}, {"$set": update})
    aid = await _audit(admin=admin, target_user_id=user_id, action="issue_warning",
                       reason=reason, metadata={"warning_count": len(warnings),
                                                 "auto_suspended": auto_suspended})
    body = f"Reason: {reason}. This is warning #{len(warnings)}."
    if auto_suspended:
        body += " You have been automatically suspended for 3 days."
    await _notify_user(user_id=user_id, action="warning",
                       title=f"Warning #{len(warnings)} issued", body=body,
                       appeal_path="/appeals")
    return {"ok": True, "audit_id": aid, "warning_count": len(warnings),
            "auto_suspended": auto_suspended}


@router.post("/{user_id}/mute")
async def mute_user(user_id: str, request: Request):
    """Body: { duration_hours: int, reason: str }. Chat-only restriction."""
    admin = await _require_admin(request, "mute")
    u = await _load_user(user_id)
    payload = await request.json()
    hours = int(payload.get("duration_hours") or 24)
    if hours < 1:
        raise HTTPException(status_code=400, detail="duration_hours must be >= 1")
    reason = (payload.get("reason") or "").strip()
    expires = (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()
    prior = {"chat_muted_until": u.get("chat_muted_until")}
    await _db().users.update_one(
        {"_id": u["_id"]},
        {"$set": {"chat_muted_until": expires, "chat_mute_reason": reason}},
    )
    aid = await _audit(admin=admin, target_user_id=user_id, action="mute",
                       reason=reason, metadata={"duration_hours": hours, "expires_at": expires},
                       prior_state=prior)
    await _notify_user(user_id=user_id, action="mute",
                       title=f"You have been muted for {hours} hour(s)",
                       body=f"Reason: {reason}. You can still play but cannot post chat.")
    return {"ok": True, "audit_id": aid, "expires_at": expires}


@router.post("/{user_id}/unmute")
async def unmute_user(user_id: str, request: Request):
    admin = await _require_admin(request, "unmute")
    u = await _load_user(user_id)
    prior = {"chat_muted_until": u.get("chat_muted_until")}
    await _db().users.update_one(
        {"_id": u["_id"]},
        {"$unset": {"chat_muted_until": "", "chat_mute_reason": ""}},
    )
    aid = await _audit(admin=admin, target_user_id=user_id, action="unmute", prior_state=prior)
    return {"ok": True, "audit_id": aid}


@router.post("/{user_id}/flag-for-review")
async def flag_for_review(user_id: str, request: Request):
    """Watchlist (no visible action). Body: { reason }."""
    admin = await _require_admin(request, "flag_for_review")
    u = await _load_user(user_id)
    payload = await request.json()
    reason = (payload.get("reason") or "").strip()
    await _db().users.update_one(
        {"_id": u["_id"]},
        {"$set": {"watchlist": True, "watchlist_reason": reason,
                  "watchlist_added_at": datetime.now(timezone.utc).isoformat(),
                  "watchlist_added_by": admin.get("email")}},
    )
    aid = await _audit(admin=admin, target_user_id=user_id, action="flag_for_review", reason=reason)
    return {"ok": True, "audit_id": aid}


@router.post("/{user_id}/unflag")
async def unflag(user_id: str, request: Request):
    admin = await _require_admin(request, "unflag")
    u = await _load_user(user_id)
    await _db().users.update_one(
        {"_id": u["_id"]},
        {"$unset": {"watchlist": "", "watchlist_reason": "",
                    "watchlist_added_at": "", "watchlist_added_by": ""}},
    )
    aid = await _audit(admin=admin, target_user_id=user_id, action="unflag")
    return {"ok": True, "audit_id": aid}


@router.post("/{user_id}/delete-content")
async def delete_content(user_id: str, request: Request):
    """STUB: audit-only delete-specific-content. Body: { content_type:
    'chat_message'|'forum_post'|'team_name'|'avatar', content_id: str,
    reason: str }. Real deletion is delegated to the moderation queue
    in iter 206."""
    admin = await _require_admin(request, "delete_content")
    payload = await request.json()
    ct = (payload.get("content_type") or "").strip()
    cid = (payload.get("content_id") or "").strip()
    reason = (payload.get("reason") or "").strip()
    if ct not in ("chat_message", "forum_post", "team_name", "avatar"):
        raise HTTPException(status_code=400, detail="invalid content_type")
    aid = await _audit(admin=admin, target_user_id=user_id, action="delete_content",
                       reason=reason, metadata={"content_type": ct, "content_id": cid},
                       mocked=True)
    return {"ok": True, "audit_id": aid, "mocked": True,
            "note": "Content deletion handled via existing /moderation/{id}/resolve flow"}


# ─────────────────────────────────────────────────────────────────────
# Financial (all stubs — real Stripe wiring follows in a future iter)
# ─────────────────────────────────────────────────────────────────────
@router.post("/{user_id}/refund")
async def refund(user_id: str, request: Request):
    """STUB: audit-only. Body: { amount_cents, currency, reason,
    transaction_id }. Real refund through Stripe API in future iter."""
    admin = await _require_admin(request, "refund")
    payload = await request.json()
    aid = await _audit(admin=admin, target_user_id=user_id, action="refund",
                       reason=(payload.get("reason") or ""),
                       metadata={k: payload.get(k) for k in
                                 ("amount_cents", "currency", "transaction_id")},
                       mocked=True)
    return {"ok": True, "audit_id": aid, "mocked": True,
            "note": "Stripe refund API call STUBBED"}


@router.post("/{user_id}/adjust-tier")
async def adjust_tier(user_id: str, request: Request):
    """Body: { tier: 'free'|'pro'|'commish'|..., reason, comp: bool }"""
    admin = await _require_admin(request, "adjust_tier")
    u = await _load_user(user_id)
    payload = await request.json()
    tier = (payload.get("tier") or "").strip()
    if not tier:
        raise HTTPException(status_code=400, detail="tier is required")
    prior = {"subscription_tier": u.get("subscription_tier"), "is_pro": u.get("is_pro")}
    await _db().users.update_one(
        {"_id": u["_id"]},
        {"$set": {"subscription_tier": tier,
                  "is_pro": tier in ("pro", "commish", "premium"),
                  "tier_set_by_admin": admin.get("email"),
                  "tier_set_at": datetime.now(timezone.utc).isoformat()}},
    )
    aid = await _audit(admin=admin, target_user_id=user_id, action="adjust_tier",
                       reason=(payload.get("reason") or ""),
                       metadata={"tier": tier, "comp": bool(payload.get("comp"))},
                       prior_state=prior)
    return {"ok": True, "audit_id": aid}


@router.post("/{user_id}/promo-credit")
async def promo_credit(user_id: str, request: Request):
    """Body: { amount_cents: int (positive=add, negative=remove),
              currency: 'usd', note: str }"""
    admin = await _require_admin(request, "promo_credit")
    u = await _load_user(user_id)
    payload = await request.json()
    amt = int(payload.get("amount_cents") or 0)
    if amt == 0:
        raise HTTPException(status_code=400, detail="amount_cents must be non-zero")
    cur = (payload.get("currency") or "usd").lower()
    prior = {"promo_credits_cents": u.get("promo_credits_cents") or 0}
    new_balance = (u.get("promo_credits_cents") or 0) + amt
    await _db().users.update_one(
        {"_id": u["_id"]},
        {"$set": {"promo_credits_cents": new_balance, "promo_currency": cur}},
    )
    aid = await _audit(admin=admin, target_user_id=user_id, action="promo_credit",
                       reason=(payload.get("note") or ""),
                       metadata={"amount_cents": amt, "currency": cur,
                                 "new_balance_cents": new_balance},
                       prior_state=prior)
    return {"ok": True, "audit_id": aid, "new_balance_cents": new_balance}


@router.post("/{user_id}/void-payout")
async def void_payout(user_id: str, request: Request):
    admin = await _require_admin(request, "void_payout")
    payload = await request.json()
    aid = await _audit(admin=admin, target_user_id=user_id, action="void_payout",
                       reason=(payload.get("reason") or ""),
                       metadata={"payout_id": payload.get("payout_id")}, mocked=True)
    return {"ok": True, "audit_id": aid, "mocked": True}


@router.post("/{user_id}/manual-payout")
async def manual_payout(user_id: str, request: Request):
    admin = await _require_admin(request, "manual_payout")
    payload = await request.json()
    aid = await _audit(admin=admin, target_user_id=user_id, action="manual_payout",
                       reason=(payload.get("reason") or ""),
                       metadata={"amount_cents": payload.get("amount_cents"),
                                 "currency": payload.get("currency")}, mocked=True)
    return {"ok": True, "audit_id": aid, "mocked": True}


# ─────────────────────────────────────────────────────────────────────
# Support
# ─────────────────────────────────────────────────────────────────────
@router.post("/{user_id}/impersonate")
async def impersonate(user_id: str, request: Request):
    """Create a short-lived (15-min) impersonation JWT for read-only
    view-as. Heavy audit + notifies the user (per most privacy regs).
    Returns the JWT so the front-end can swap its bearer for the
    read-only impersonation session. `get_current_user` decodes the
    token and decorates the response with `_impersonator_email` so any
    write endpoint can block by checking for that field."""
    admin = await _require_admin(request, "impersonate")
    u = await _load_user(user_id)
    payload = await request.json() if request.headers.get("content-length") else {}
    reason = (payload.get("reason") or "").strip()
    expires = (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat()
    create_token = _deps.get("create_impersonation_token")
    if not create_token:
        raise HTTPException(status_code=500, detail="impersonation token issuer not wired")
    token = create_token(
        target_user_id=str(u["_id"]),
        target_email=u.get("email") or "",
        impersonator_id=str(admin.get("_id") or admin.get("id")),
        impersonator_email=admin.get("email") or "",
        minutes=15,
    )
    await _db().impersonation_audit.insert_one({
        "admin_id": str(admin.get("_id")),
        "admin_email": admin.get("email"),
        "target_user_id": user_id,
        "target_email": u.get("email"),
        "reason": reason,
        "token_hash": secrets.token_hex(16),
        "started_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": expires,
        "mode": "read_only",
    })
    aid = await _audit(admin=admin, target_user_id=user_id, action="impersonate",
                       reason=reason, metadata={"expires_at": expires, "mode": "read_only"})
    await _notify_user(user_id=user_id, action="impersonate",
                       title="An admin viewed your account",
                       body=f"Reason: {reason or 'support investigation'}. Read-only view, expires in 15 minutes.")
    return {"ok": True, "audit_id": aid, "impersonation_token": token,
            "expires_at": expires, "mode": "read_only"}


@router.post("/{user_id}/resend-verification")
async def resend_verification(user_id: str, request: Request):
    admin = await _require_admin(request, "resend_verification")
    u = await _load_user(user_id)
    aid = await _audit(admin=admin, target_user_id=user_id, action="resend_verification",
                       metadata={"email": u.get("email")}, mocked=True)
    return {"ok": True, "audit_id": aid, "mocked": True,
            "note": "SendGrid send_email integration STUBBED"}


@router.post("/{user_id}/link-support-ticket")
async def link_support_ticket(user_id: str, request: Request):
    """Body: { ticket_id, ticket_url, note }"""
    admin = await _require_admin(request, "link_support_ticket")
    payload = await request.json()
    tid = (payload.get("ticket_id") or "").strip()
    if not tid:
        raise HTTPException(status_code=400, detail="ticket_id required")
    await _db().user_support_links.insert_one({
        "user_id": user_id, "ticket_id": tid,
        "ticket_url": payload.get("ticket_url"),
        "note": payload.get("note"),
        "linked_by": admin.get("email"),
        "ts": datetime.now(timezone.utc).isoformat(),
    })
    aid = await _audit(admin=admin, target_user_id=user_id, action="link_support_ticket",
                       metadata={"ticket_id": tid})
    return {"ok": True, "audit_id": aid}


@router.get("/{user_id}/export-data")
async def export_data(user_id: str, request: Request):
    """Returns a JSON dump of the user's data for GDPR / CCPA access
    requests. Includes profile, login history, reports (about them),
    leagues + teams they own, and trades they participated in."""
    admin = await _require_admin(request, "export_data")
    u = await _load_user(user_id)
    db = _db()
    teams = await db.teams.find({"owner_id": user_id}).to_list(200)
    leagues_ids = list({t.get("league_id") for t in teams if t.get("league_id")})
    leagues = []
    if leagues_ids:
        async for lg in db.leagues.find({"_id": {"$in": [
            ObjectId(lid) for lid in leagues_ids if ObjectId.is_valid(str(lid))
        ]}}):
            leagues.append({"id": str(lg["_id"]), "name": lg.get("name")})
    logins = await db.user_login_audit.find({"user_id": user_id}).to_list(500)
    reports_against = await db.user_reports.find({"target_user_id": user_id}).to_list(200)
    reports_filed = await db.user_reports.find({"reporter_id": user_id}).to_list(200)
    trades = await db.trades.find({
        "$or": [{"proposer_team_owner_id": user_id}, {"target_team_owner_id": user_id}]
    }).to_list(500)
    payload = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "exported_by_admin": admin.get("email"),
        "user": {
            "id": str(u["_id"]),
            "email": u.get("email"),
            "username": u.get("username"),
            "name": u.get("name"),
            "phone": u.get("phone"),
            "created_at": _iso(u.get("created_at")),
            "status": u.get("status"),
            "linked_sso_accounts": u.get("linked_sso_accounts") or [],
            "warnings": u.get("warnings") or [],
            "chargeback_flags": u.get("chargeback_flags") or [],
        },
        "leagues": leagues,
        "teams": [{"id": str(t["_id"]), "name": t.get("name"),
                   "league_id": t.get("league_id")} for t in teams],
        "login_history": [{
            "ts": _iso(rec.get("ts")), "ip": rec.get("ip"),
            "user_agent": rec.get("user_agent"),
        } for rec in logins],
        "reports_against_user": [{
            "id": str(r["_id"]), "category": r.get("category"),
            "ts": _iso(r.get("created_at")), "status": r.get("status"),
        } for r in reports_against],
        "reports_filed_by_user": [{
            "id": str(r["_id"]), "category": r.get("category"),
            "ts": _iso(r.get("created_at")),
        } for r in reports_filed],
        "trades_count": len(trades),
    }
    aid = await _audit(admin=admin, target_user_id=user_id, action="export_data",
                       metadata={"counts": {"logins": len(logins),
                                            "reports_against": len(reports_against),
                                            "reports_filed": len(reports_filed),
                                            "trades": len(trades),
                                            "leagues": len(leagues)}})
    payload["audit_id"] = aid
    return payload


@router.post("/{user_id}/gdpr-delete")
async def gdpr_delete(user_id: str, request: Request):
    """Queue a right-to-be-forgotten deletion. Same anonymization as
    /delete but marked as GDPR-initiated for compliance audit trails."""
    admin = await _require_admin(request, "gdpr_delete")
    u = await _load_user(user_id)
    payload = await request.json()
    if not payload.get("confirm"):
        raise HTTPException(status_code=400, detail="confirm=true required")
    reason = (payload.get("reason") or "GDPR/CCPA data deletion request").strip()
    prior = {"email": u.get("email"), "username": u.get("username"),
             "name": u.get("name"), "phone": u.get("phone")}
    anon_marker = f"gdpr_deleted_user_{ObjectId()}"
    await _db().users.update_one(
        {"_id": u["_id"]},
        {"$set": {
            "status": "deleted", "is_active": False,
            "email": f"{anon_marker}@anonymised.local",
            "username": anon_marker, "name": anon_marker, "phone": None,
            "gdpr_deleted_at": datetime.now(timezone.utc).isoformat(),
            "gdpr_deleted_by_admin": admin.get("email"),
            "deletion_basis": "gdpr_ccpa_request",
        },
         "$unset": {"password_hash": "", "linked_sso_accounts": "",
                    "recovery_email": "", "security_questions": ""}},
    )
    aid = await _audit(admin=admin, target_user_id=user_id, action="gdpr_delete",
                       reason=reason, prior_state=prior,
                       metadata={"anon_marker": anon_marker})
    return {"ok": True, "audit_id": aid, "anon_marker": anon_marker}


@router.post("/{user_id}/permission-tier")
async def set_permission_tier(user_id: str, request: Request):
    """Body: { tier: 'user'|'moderator'|'admin'|'senior_admin', reason: str }
    Grants or revokes admin permission tiers on a target user. Requires
    senior_admin (you can only promote up to or below your own tier)."""
    admin = await _require_admin(request, "set_permission_tier")
    # Senior admin gate
    actor_tier = admin.get("permission_tier")
    if not actor_tier:
        actor_tier = "senior_admin" if admin.get("role") == "admin" else "user"
    if actor_tier != "senior_admin":
        raise HTTPException(status_code=403, detail="Only senior_admin can change permission tiers")
    u = await _load_user(user_id)
    payload = await request.json()
    tier = (payload.get("tier") or "").strip()
    reason = (payload.get("reason") or "").strip()
    if tier not in ("user", "moderator", "admin", "senior_admin"):
        raise HTTPException(status_code=400, detail="invalid tier")
    # Sync the legacy `role` field too — moderator/admin/senior_admin all
    # map to `role='admin'` for backward compatibility with existing
    # admin-gated endpoints; user tier maps to `role='user'`.
    new_role = "admin" if tier in ("moderator", "admin", "senior_admin") else "user"
    prior = {"permission_tier": u.get("permission_tier"), "role": u.get("role")}
    await _db().users.update_one(
        {"_id": u["_id"]},
        {"$set": {"permission_tier": tier, "role": new_role,
                  "tier_set_by_admin": admin.get("email"),
                  "tier_set_at": datetime.now(timezone.utc).isoformat()}},
    )
    aid = await _audit(admin=admin, target_user_id=user_id, action="set_permission_tier",
                       reason=reason, prior_state=prior,
                       metadata={"new_tier": tier, "new_role": new_role})
    await _notify_user(user_id=user_id, action="set_permission_tier",
                       title=f"Your account permission tier is now '{tier}'",
                       body=f"Reason: {reason or 'admin action'}.")
    return {"ok": True, "audit_id": aid, "tier": tier, "role": new_role}


# ─────────────────────────────────────────────────────────────────────
# Audit log read endpoint (for the detail drawer)
# ─────────────────────────────────────────────────────────────────────
@router.get("/{user_id}/admin-actions")
async def list_admin_actions(user_id: str, request: Request):
    """Return the audit-log entries for actions taken against the user
    (so admins can see prior bans, warnings, refunds, etc.)."""
    await _require_admin(request, "audit_read")
    rows = await _db().admin_user_actions.find(
        {"target_user_id": user_id}
    ).sort("ts", -1).to_list(200)
    return {
        "actions": [{
            "id": str(r["_id"]),
            "action": r.get("action"),
            "admin_email": r.get("admin_email"),
            "admin_tier": r.get("admin_tier"),
            "reason": r.get("reason"),
            "metadata": r.get("metadata"),
            "prior_state": r.get("prior_state"),
            "mocked": bool(r.get("mocked", False)),
            "ts": _iso(r.get("ts")),
        } for r in rows]
    }
