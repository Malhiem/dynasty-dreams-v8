"""Auth routes — register, login, logout, /me, refresh, forgot/reset password.

Extracted verbatim from server.py via the standard `setup(deps)` pattern.
All helpers (db, hash_password, verify_password, create_access_token,
create_refresh_token, get_current_user, JWT secret, cookie config) are
injected through `_deps`.
"""
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from bson import ObjectId
from fastapi import APIRouter, HTTPException, Request, Response

router = APIRouter()
_deps: dict = {}


def setup(deps: dict) -> None:
    _deps.update(deps)


def _db():     return _deps["db"]
def _logger(): return _deps["logger"]
def _models(): return _deps["auth_models"]  # dict: UserRegister/Login/Response/Role/ForgotPassword/ResetPassword


@router.post("/auth/register")
async def register(request: Request, response: Response):
    M = _models()
    body = await request.json()
    input = M["UserRegister"](**body)
    db = _db()
    hash_password = _deps["hash_password"]
    create_access_token = _deps["create_access_token"]
    create_refresh_token = _deps["create_refresh_token"]
    cookie_secure = _deps["COOKIE_SECURE"]
    cookie_samesite = _deps["COOKIE_SAMESITE"]
    UserResponse = M["UserResponse"]
    UserRole = M["UserRole"]

    email = input.email.lower()
    username = input.username.strip()

    # SEC P3 — Account-enumeration hardening. Previously the two
    # branches below leaked which field collided (email vs username),
    # letting an attacker enumerate one or the other. Now both
    # collisions return a single generic error.
    existing = await db.users.find_one(
        {"$or": [{"email": email}, {"username": username}]}
    )
    if existing:
        raise HTTPException(
            status_code=400,
            detail="Email or username is already in use",
        )

    # Iter 206 — Content Moderation Phase 3: scan username against
    # banned keywords. If hit, auto-queue for admin review (but allow
    # the registration to proceed — admin can rename retroactively).
    try:
        from routes import moderation as _mod
        match = await _mod.scan_text(username)
        if match:
            await _mod.queue_for_review(
                source="username",
                content=username,
                author_id=None,
                author_email=email,
                matched_word=match["matched_word"],
                severity=match["severity"],
                context={"event": "registration"},
            )
    except Exception:
        pass

    user_doc = {
        "email": email,
        "password_hash": hash_password(input.password),
        "username": username,
        "name": username,
        "role": UserRole.USER.value,
        "subscription": None,
        "created_at": datetime.now(timezone.utc),
    }
    result = await db.users.insert_one(user_doc)
    user_id = str(result.inserted_id)

    access_token = create_access_token(user_id, email)
    refresh_token = create_refresh_token(user_id)

    response.set_cookie(key="access_token", value=access_token, httponly=True,
                        secure=cookie_secure, samesite=cookie_samesite, max_age=43200, path="/")
    response.set_cookie(key="refresh_token", value=refresh_token, httponly=True,
                        secure=cookie_secure, samesite=cookie_samesite, max_age=604800, path="/")

    return UserResponse(
        id=user_id, email=email, username=username, name=username,
        role=UserRole.USER.value, created_at=user_doc["created_at"],
        access_token=access_token, refresh_token=refresh_token,
    )


@router.post("/auth/login")
async def login(request: Request, response: Response):
    M = _models()
    body = await request.json()
    input = M["UserLogin"](**body)
    db = _db()
    verify_password = _deps["verify_password"]
    create_access_token = _deps["create_access_token"]
    create_refresh_token = _deps["create_refresh_token"]
    cookie_secure = _deps["COOKIE_SECURE"]
    cookie_samesite = _deps["COOKIE_SAMESITE"]
    UserResponse = M["UserResponse"]

    email = input.email.lower()
    identifier = f"{request.client.host}:{email}"

    attempts = await db.login_attempts.find_one({"identifier": identifier})
    if attempts and attempts.get("count", 0) >= 5:
        lockout_until = attempts.get("lockout_until")
        if lockout_until and lockout_until.tzinfo is None:
            lockout_until = lockout_until.replace(tzinfo=timezone.utc)
        if lockout_until and datetime.now(timezone.utc) < lockout_until:
            raise HTTPException(status_code=429, detail="Too many login attempts. Try again later.")
        await db.login_attempts.delete_one({"identifier": identifier})

    user = await db.users.find_one({"email": email})
    if not user or not verify_password(input.password, user["password_hash"]):
        await db.login_attempts.update_one(
            {"identifier": identifier},
            {
                "$inc": {"count": 1},
                "$set": {"lockout_until": datetime.now(timezone.utc) + timedelta(minutes=15)},
            },
            upsert=True,
        )
        raise HTTPException(status_code=401, detail="Invalid email or password")

    await db.login_attempts.delete_one({"identifier": identifier})

    # Iter 206 — Account Integrity: block banned users + log IP audit.
    user_status = user.get("status", "active")
    if user_status == "banned":
        raise HTTPException(status_code=403, detail="Account banned. Submit an appeal to /api/appeals.")
    if user_status == "suspended":
        expires = user.get("ban_expires_at")
        if expires:
            try:
                exp_dt = datetime.fromisoformat(str(expires).replace("Z", "+00:00"))
                if datetime.now(timezone.utc) < exp_dt:
                    raise HTTPException(status_code=403, detail=f"Account suspended until {expires}. Submit an appeal to /api/appeals.")
                await db.users.update_one(
                    {"_id": user["_id"]},
                    {"$set": {"status": "active"},
                     "$unset": {"ban_expires_at": "", "ban_reason_code": "", "ban_reason": ""}},
                )
            except HTTPException:
                raise
            except Exception:
                raise HTTPException(status_code=403, detail="Account suspended.")

    # Record login audit for multi-account detection (best-effort).
    # Iter 207 — also capture a device fingerprint (client-supplied
    # canvas/UA hash) so we can detect users on different IPs but the
    # same device.
    try:
        device_hash = None
        try:
            _body = body if isinstance(body, dict) else {}
            device_hash = _body.get("device_hash")
        except Exception:
            device_hash = None
        await db.user_login_audit.insert_one({
            "user_id": str(user["_id"]),
            "email": user.get("email"),
            "ip": (request.client.host if request.client else None),
            "user_agent": request.headers.get("user-agent"),
            "device_hash": device_hash,
            "ts": datetime.now(timezone.utc).isoformat(),
        })
    except Exception:
        pass

    user_id = str(user["_id"])
    access_token = create_access_token(user_id, email)
    refresh_token = create_refresh_token(user_id)

    response.set_cookie(key="access_token", value=access_token, httponly=True,
                        secure=cookie_secure, samesite=cookie_samesite, max_age=43200, path="/")
    response.set_cookie(key="refresh_token", value=refresh_token, httponly=True,
                        secure=cookie_secure, samesite=cookie_samesite, max_age=604800, path="/")

    return UserResponse(
        id=user_id, email=user["email"],
        username=user.get("username") or user.get("name", ""),
        name=user.get("username") or user.get("name", ""),
        role=user["role"], created_at=user["created_at"],
        access_token=access_token, refresh_token=refresh_token,
    )


@router.post("/auth/logout")
async def logout(response: Response):
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")
    return {"message": "Logged out successfully"}


@router.get("/auth/me")
async def get_me(request: Request):
    get_current_user = _deps["get_current_user"]
    UserResponse = _models()["UserResponse"]
    user = await get_current_user(request)
    payload = UserResponse(
        id=user["_id"], email=user["email"],
        username=user.get("username") or user.get("name", ""),
        name=user.get("username") or user.get("name", ""),
        role=user["role"], created_at=user["created_at"],
    ).model_dump()
    # Extended profile fields (not part of the strict UserResponse model)
    payload.update({
        "favourite_sport": user.get("favourite_sport"),
        "favourite_team": user.get("favourite_team"),
        "city": user.get("city"),
        "province_state": user.get("province_state"),
        "country": user.get("country"),
        "avatar_url": user.get("avatar_url"),
        # Iter 216b — impersonation banner. When the auth cookie carries a
        # `type=impersonation` JWT, `get_current_user` decorates the user
        # with these fields; surface them so the frontend can render the
        # "You are viewing as X — read-only · expires in MM:SS" banner.
        "_impersonator_id": user.get("_impersonator_id"),
        "_impersonator_email": user.get("_impersonator_email"),
        "_impersonation_mode": user.get("_impersonation_mode"),
        "_impersonation_expires_at": user.get("_impersonation_expires_at"),
    })
    return payload


@router.post("/auth/impersonate-start")
async def impersonate_start(request: Request, response: Response):
    """Iter 216b — Cookie-swap impersonation.

    Body: { target_user_id: str, reason: str }

    Server validates the caller is admin, mints a `type=impersonation`
    JWT for the target user, then:
      * stores the caller's existing access_token in a separate
        `admin_token_backup` cookie so `/auth/impersonate-stop` can
        restore it later, AND
      * replaces the `access_token` cookie with the impersonation token.

    The browser will then see the target user on every subsequent
    request until impersonate-stop is called or the impersonation
    token (15 min) expires.
    """
    from bson import ObjectId as _OID
    db = _db()
    get_current_user = _deps["get_current_user"]
    create_impersonation_token = _deps["create_impersonation_token"]
    cookie_secure = _deps["COOKIE_SECURE"]
    cookie_samesite = _deps["COOKIE_SAMESITE"]
    admin = await get_current_user(request)
    if (admin or {}).get("role") != "admin" and (admin or {}).get("permission_tier") not in ("admin", "senior_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    if admin.get("_impersonation_mode"):
        raise HTTPException(status_code=400, detail="Already impersonating — call /auth/impersonate-stop first")
    body = await request.json()
    target_id = (body.get("target_user_id") or "").strip()
    reason = (body.get("reason") or "").strip()
    if not target_id:
        raise HTTPException(status_code=400, detail="target_user_id required")
    try:
        target = await db.users.find_one({"_id": _OID(target_id)})
    except Exception:
        target = None
    if not target:
        raise HTTPException(status_code=404, detail="Target user not found")

    # Iter 232N.59 — Impersonation is restricted to accounts explicitly
    # flagged `is_test_account=true`. This is the safety floor: an admin
    # can never accidentally act as a real user; every impersonation
    # target must be a test-sandbox account seeded via
    # `POST /admin/test-sandbox/leagues`.
    if not target.get("is_test_account"):
        raise HTTPException(
            status_code=403,
            detail="Impersonation restricted to test-sandbox accounts (is_test_account=true)",
        )

    imp_token = create_impersonation_token(
        target_user_id=str(target["_id"]),
        target_email=target.get("email") or "",
        impersonator_id=str(admin["_id"]),
        impersonator_email=admin.get("email") or "",
        minutes=15,
    )
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat()
    original_token = request.cookies.get("access_token") or ""
    response.set_cookie(key="admin_token_backup", value=original_token, httponly=True,
                        secure=cookie_secure, samesite=cookie_samesite, max_age=1800, path="/")
    response.set_cookie(key="access_token", value=imp_token, httponly=True,
                        secure=cookie_secure, samesite=cookie_samesite, max_age=900, path="/")

    await db.impersonation_audit.insert_one({
        "admin_id": str(admin["_id"]), "admin_email": admin.get("email"),
        "target_user_id": str(target["_id"]), "target_email": target.get("email"),
        "reason": reason, "started_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": expires_at, "mode": "read_only",
        "cookie_swap": True,
    })
    return {"ok": True, "expires_at": expires_at, "target_email": target.get("email")}


@router.post("/auth/impersonate-stop")
async def impersonate_stop(request: Request, response: Response):
    """Iter 216b — Restore the admin's original access_token cookie
    from `admin_token_backup`. Audit the stop event."""
    db = _db()
    get_current_user = _deps["get_current_user"]
    cookie_secure = _deps["COOKIE_SECURE"]
    cookie_samesite = _deps["COOKIE_SAMESITE"]
    # We expect to be impersonating right now
    try:
        current = await get_current_user(request)
    except HTTPException:
        current = None
    backup = request.cookies.get("admin_token_backup")
    if not backup:
        raise HTTPException(status_code=400, detail="Not currently impersonating")
    response.set_cookie(key="access_token", value=backup, httponly=True,
                        secure=cookie_secure, samesite=cookie_samesite, max_age=43200, path="/")
    response.delete_cookie("admin_token_backup", path="/")
    if current and current.get("_impersonator_id"):
        await db.impersonation_audit.insert_one({
            "admin_id": current.get("_impersonator_id"),
            "admin_email": current.get("_impersonator_email"),
            "target_user_id": current.get("_id"),
            "target_email": current.get("email"),
            "stopped_at": datetime.now(timezone.utc).isoformat(),
            "mode": "read_only", "event": "stop",
        })
    return {"ok": True}


@router.post("/auth/refresh")
async def refresh_token_endpoint(request: Request, response: Response):
    db = _db()
    create_access_token = _deps["create_access_token"]
    cookie_secure = _deps["COOKIE_SECURE"]
    cookie_samesite = _deps["COOKIE_SAMESITE"]
    get_jwt_secret = _deps["get_jwt_secret"]
    jwt_algorithm = _deps["JWT_ALGORITHM"]

    token = request.cookies.get("refresh_token")
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
    if not token:
        raise HTTPException(status_code=401, detail="No refresh token")
    try:
        payload = jwt.decode(token, get_jwt_secret(), algorithms=[jwt_algorithm])
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")
        user = await db.users.find_one({"_id": ObjectId(payload["sub"])})
        if not user:
            raise HTTPException(status_code=401, detail="User not found")

        # SEC P3 — Reject refresh tokens minted before the user's most
        # recent password change. Stops a stolen 7-day refresh token
        # from outliving a password reset.
        changed_at = user.get("password_changed_at")
        token_iat = payload.get("iat")
        if changed_at and token_iat:
            # PyJWT exposes iat as int (epoch seconds).
            if isinstance(token_iat, (int, float)):
                token_iat_dt = datetime.fromtimestamp(int(token_iat), tz=timezone.utc)
            else:
                token_iat_dt = token_iat
            if isinstance(changed_at, str):
                try:
                    changed_at = datetime.fromisoformat(changed_at)
                except Exception:
                    changed_at = None
            # Mongo returns naive UTC; coerce to aware before compare.
            if changed_at and getattr(changed_at, "tzinfo", None) is None:
                changed_at = changed_at.replace(tzinfo=timezone.utc)
            if changed_at and token_iat_dt < changed_at:
                # Clear the stale cookies so the client re-authenticates.
                response.delete_cookie("access_token", path="/")
                response.delete_cookie("refresh_token", path="/")
                raise HTTPException(
                    status_code=401, detail="Session revoked — please sign in again",
                )

        user_id = str(user["_id"])
        access_token = create_access_token(user_id, user["email"])
        response.set_cookie(key="access_token", value=access_token, httponly=True,
                            secure=cookie_secure, samesite=cookie_samesite,
                            max_age=43200, path="/")
        return {"message": "Token refreshed", "access_token": access_token, "refresh_token": token}
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Refresh token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")


@router.post("/auth/forgot-password")
async def forgot_password(request: Request):
    M = _models()
    body = await request.json()
    input = M["ForgotPassword"](**body)
    db = _db()
    logger = _logger()
    email = input.email.lower()

    # SEC P3 — Rate limit. Per-email (5/h, 1/min) + per-IP (10/h, 3/min)
    # throttle so the endpoint cannot be used to spam the mail provider
    # or to enumerate accounts via timing. We always return the same
    # generic message to preserve the audit-mandated non-enumeration
    # behavior, even when throttled.
    now = datetime.now(timezone.utc)
    client_ip = (
        request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        or (request.client.host if request.client else "unknown")
    )
    hour_ago = now - timedelta(hours=1)
    minute_ago = now - timedelta(minutes=1)
    email_count_h = await db.password_reset_throttle.count_documents(
        {"email": email, "ts": {"$gte": hour_ago}}
    )
    email_count_m = await db.password_reset_throttle.count_documents(
        {"email": email, "ts": {"$gte": minute_ago}}
    )
    ip_count_h = await db.password_reset_throttle.count_documents(
        {"ip": client_ip, "ts": {"$gte": hour_ago}}
    )
    ip_count_m = await db.password_reset_throttle.count_documents(
        {"ip": client_ip, "ts": {"$gte": minute_ago}}
    )
    if email_count_h >= 5 or email_count_m >= 1 or ip_count_h >= 10 or ip_count_m >= 3:
        logger.warning(
            f"forgot-password throttled email={email} ip={client_ip} "
            f"e/h={email_count_h} e/m={email_count_m} ip/h={ip_count_h} ip/m={ip_count_m}"
        )
        # Same response shape as the success branch so attackers can't
        # use this to enumerate accounts.
        return {"message": "If an account exists, a reset link has been sent"}

    # Record the attempt FIRST so even a non-existent email contributes
    # to throttle counts (otherwise enumeration via 429 timing is back).
    await db.password_reset_throttle.insert_one({
        "email": email, "ip": client_ip, "ts": now,
    })

    user = await db.users.find_one({"email": email})
    if not user:
        return {"message": "If an account exists, a reset link has been sent"}
    token = secrets.token_urlsafe(32)
    await db.password_reset_tokens.insert_one({
        "token": token,
        "user_id": str(user["_id"]),
        "expires_at": now + timedelta(hours=1),
        "used": False,
    })
    logger.info(f"Password reset link: /reset-password?token={token}")
    return {"message": "If an account exists, a reset link has been sent"}


@router.post("/auth/reset-password")
async def reset_password(request: Request, response: Response):
    M = _models()
    body = await request.json()
    input = M["ResetPassword"](**body)
    db = _db()
    hash_password = _deps["hash_password"]
    token_doc = await db.password_reset_tokens.find_one({"token": input.token, "used": False})
    if not token_doc:
        raise HTTPException(status_code=400, detail="Invalid or expired token")
    # Mongo returns naive UTC datetimes; coerce to aware before compare.
    expires_at = token_doc["expires_at"]
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) > expires_at:
        raise HTTPException(status_code=400, detail="Token expired")
    # SEC P3 — Invalidate ALL existing sessions on reset. We stamp
    # `password_changed_at` on the user doc; the refresh endpoint
    # rejects any refresh token whose `iat` is older. Also clears the
    # caller's own cookies so the UI flow isn't left in a half-broken
    # state (next request will 401 → redirect to login).
    now = datetime.now(timezone.utc)
    await db.users.update_one(
        {"_id": ObjectId(token_doc["user_id"])},
        {"$set": {
            "password_hash": hash_password(input.new_password),
            "password_changed_at": now,
        }},
    )
    await db.password_reset_tokens.update_one({"token": input.token}, {"$set": {"used": True}})
    # Best-effort cookie clear (no harm if the caller wasn't logged in).
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")
    return {"message": "Password reset successfully"}
