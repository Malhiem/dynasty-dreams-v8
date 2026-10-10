"""Auth routes — register, login, logout, /me, refresh, forgot/reset password.

Uses the standard `setup(deps)` pattern and shared account policy services.
All helpers (db, hash_password, verify_password, create_access_token,
create_refresh_token, get_current_user, JWT secret, cookie config) are
injected through `_deps`.
"""
import secrets
import re
from pymongo.errors import DuplicateKeyError
from services.account_access import require_active, require_session
from utils.refresh_tokens import predates_password_change
from datetime import datetime, timedelta, timezone

import jwt
from bson import ObjectId
from pydantic import ValidationError
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse

router = APIRouter()
_deps: dict = {}


def setup(deps: dict) -> None:
    _deps.update(deps)


def _db():     return _deps["db"]
def _logger(): return _deps["logger"]
async def _json_body(request):
    try:
        body = await request.json()
    except ValueError:
        raise HTTPException(400, "Invalid JSON")
    if not isinstance(body, dict):
        raise HTTPException(422, "Expected a JSON object")
    return body

def _models(): return _deps["auth_models"]  # dict: UserRegister/Login/Response/Role/ForgotPassword/ResetPassword


@router.post("/auth/register")
async def register(request: Request, response: Response):
    M = _models()
    body = await _json_body(request)
    try:
        input = M["UserRegister"](**body)
    except ValidationError as exc:
        raise HTTPException(422, detail=[{"loc": error["loc"], "msg": error["msg"], "type": error["type"]}
                                         for error in exc.errors()]) from exc
    db = _db()
    hash_password = _deps["hash_password"]
    create_access_token = _deps["create_access_token"]
    create_refresh_token = _deps["create_refresh_token"]
    cookie_secure = _deps["COOKIE_SECURE"]
    cookie_samesite = _deps["COOKIE_SAMESITE"]
    UserResponse = M["UserResponse"]
    UserRole = M["UserRole"]

    email = input.email.strip().lower()
    username = input.username.strip()

    # SEC P3 — Account-enumeration hardening. Previously the two
    # branches below leaked which field collided (email vs username),
    # letting an attacker enumerate one or the other. Now both
    # collisions return a single generic error.
    existing = await db.users.find_one(
        {"$or": [{"email": email}, {"username": {"$regex": "^"+re.escape(username)+"$", "$options": "i"}}]}
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
        "username_key": username.lower(),
        "email_verified": False,
        "name": username,
        "role": UserRole.USER.value,
        "subscription": None,
        "created_at": datetime.now(timezone.utc),
    }
    try:
        result = await db.users.insert_one(user_doc)
    except DuplicateKeyError:
        raise HTTPException(400, "Email or username is already in use")
    user_id = str(result.inserted_id)
    from services.account_verification import issue
    await issue(db, _deps, {**user_doc, "_id": result.inserted_id})

    session_id = str(ObjectId())
    await db.user_sessions.insert_one({"_id":ObjectId(session_id),"user_id":user_id,"issued_at":datetime.now(timezone.utc),
        "expires_at":datetime.now(timezone.utc)+timedelta(days=7),"revoked":False,"ip":request.client.host if request.client else None,
        "user_agent":request.headers.get("user-agent")})
    access_token = create_access_token(user_id, email, session_id=session_id, token_version=int(user_doc.get("token_version") or 0))
    refresh_token = create_refresh_token(user_id, session_id=session_id, token_version=int(user_doc.get("token_version") or 0))

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
    body = await _json_body(request)
    try:
        input = M["UserLogin"](**body)
    except ValidationError as exc:
        raise HTTPException(422, detail=[{"loc": error["loc"], "msg": error["msg"], "type": error["type"]}
                                         for error in exc.errors()]) from exc
    db = _db()
    verify_password = _deps["verify_password"]
    create_access_token = _deps["create_access_token"]
    create_refresh_token = _deps["create_refresh_token"]
    cookie_secure = _deps["COOKIE_SECURE"]
    cookie_samesite = _deps["COOKIE_SAMESITE"]
    UserResponse = M["UserResponse"]

    email = input.email.strip().lower()
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
    if not user or not user.get("password_hash") or not verify_password(input.password, user["password_hash"]):
        await db.login_attempts.update_one(
            {"identifier": identifier},
            {
                "$inc": {"count": 1},
                "$set": {"lockout_until": datetime.now(timezone.utc) + timedelta(minutes=15)},
            },
            upsert=True,
        )
        raise HTTPException(status_code=401, detail="Invalid email or password")

    require_active(user)
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
    session_id = str(ObjectId())
    await db.user_sessions.insert_one({"_id":ObjectId(session_id),"user_id":user_id,"issued_at":datetime.now(timezone.utc),
        "expires_at":datetime.now(timezone.utc)+timedelta(days=7),"revoked":False,"ip":request.client.host if request.client else None,
        "user_agent":request.headers.get("user-agent")})
    access_token = create_access_token(user_id, email, session_id=session_id, token_version=int(user.get("token_version") or 0))
    refresh_token = create_refresh_token(user_id, remember=bool(body.get("remember", True)), session_id=session_id, token_version=int(user.get("token_version") or 0))

    response.set_cookie(key="access_token", value=access_token, httponly=True,
                        secure=cookie_secure, samesite=cookie_samesite, max_age=43200 if body.get("remember", True) else None, path="/")
    response.set_cookie(key="refresh_token", value=refresh_token, httponly=True,
                        secure=cookie_secure, samesite=cookie_samesite, max_age=604800 if body.get("remember", True) else None, path="/")

    return UserResponse(
        id=user_id, email=user["email"],
        username=user.get("username") or user.get("name", ""),
        name=user.get("username") or user.get("name", ""),
        role=user["role"], created_at=user["created_at"],
        email_verified=user.get("email_verified",False),
        pending_email=user.get("verification_email") if user.get("verification_email") != user.get("email") else None,
        access_token=access_token, refresh_token=refresh_token,
    )


@router.post("/auth/logout")
async def logout(request: Request, response: Response):
    import hashlib
    tokens = [request.cookies.get("access_token"), request.cookies.get("refresh_token"), request.cookies.get("admin_token_backup")]
    header = request.headers.get("Authorization", "")
    if header.startswith("Bearer "): tokens.append(header[7:])
    for token in set(filter(None, tokens)):
        try:
            payload = jwt.decode(token, _deps["get_jwt_secret"](), algorithms=[_deps["JWT_ALGORITHM"]])
            if payload.get("session_id"):
                from services.account_access import disconnect_sessions
                await _db().user_sessions.update_one({"_id":ObjectId(payload["session_id"])},{"$set":{"revoked":True}})
                await _db().revoked_auth_sessions.update_one({"_id":payload["session_id"]},
                    {"$set":{"expires_at":datetime.now(timezone.utc)+timedelta(days=7)}},upsert=True)
            if not payload.get("session_id") and payload.get("sub"):
                await _db().users.update_one({"_id":ObjectId(payload["sub"])},{"$inc":{"token_version":1}})
            await _db().revoked_auth_tokens.update_one({"_id": hashlib.sha256(token.encode()).hexdigest()},
                {"$set": {"expires_at": datetime.fromtimestamp(payload["exp"], tz=timezone.utc)}}, upsert=True)
        except (jwt.InvalidTokenError, KeyError, ValueError):
            pass
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")
    response.delete_cookie("admin_token_backup", path="/")
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
        email_verified=user.get("email_verified",False),
        pending_email=user.get("verification_email") if user.get("verification_email") != user.get("email") else None,
    ).model_dump()
    # Extended profile fields (not part of the strict UserResponse model)
    payload.update({
        "email_verified": user.get("email_verified", False),
        "pending_email": user.get("verification_email") if user.get("verification_email") != user.get("email") else None,
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
    body = await _json_body(request)
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

    # Iter 232N.61 — Sandbox impersonation runs in `mode=sandbox` so
    # writes ARE allowed (admins need to actually exercise flows —
    # trade, waiver, chat, lineup — as the test manager). We also
    # use a long 12-hour expiry since users specifically requested
    # "no timer for expiry" in the sandbox.
    IMP_MINUTES = 12 * 60  # 12 hours
    imp_mode = "sandbox"
    imp_token = create_impersonation_token(
        target_user_id=str(target["_id"]),
        token_version=int(target.get("token_version") or 0),
        target_email=target.get("email") or "",
        impersonator_id=str(admin["_id"]),
        impersonator_email=admin.get("email") or "",
        minutes=IMP_MINUTES,
        mode=imp_mode,
    )
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=IMP_MINUTES)).isoformat()
    original_token = request.cookies.get("access_token") or ""
    # Backup cookie needs to outlive the impersonation session too.
    response.set_cookie(key="admin_token_backup", value=original_token, httponly=True,
                        secure=cookie_secure, samesite=cookie_samesite, max_age=IMP_MINUTES * 60, path="/")
    response.set_cookie(key="access_token", value=imp_token, httponly=True,
                        secure=cookie_secure, samesite=cookie_samesite, max_age=IMP_MINUTES * 60, path="/")

    await db.impersonation_audit.insert_one({
        "admin_id": str(admin["_id"]), "admin_email": admin.get("email"),
        "target_user_id": str(target["_id"]), "target_email": target.get("email"),
        "reason": reason, "started_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": expires_at, "mode": imp_mode,
        "cookie_swap": True,
    })
    return {"ok": True, "expires_at": expires_at, "mode": imp_mode, "target_email": target.get("email")}


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

    auth = request.headers.get("Authorization", "")
    token = auth[7:] if auth.startswith("Bearer ") else request.cookies.get("refresh_token")
    def rejected(detail):
        result = JSONResponse(status_code=401,content={"detail":detail})
        result.delete_cookie("access_token",path="/")
        result.delete_cookie("refresh_token",path="/")
        return result
    if not token:
        return rejected("No refresh token")
    try:
        payload = jwt.decode(token, get_jwt_secret(), algorithms=[jwt_algorithm])
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")
        user = await db.users.find_one({"_id": ObjectId(payload["sub"])})
        if not user:
            raise HTTPException(status_code=401, detail="User not found")

        import hashlib
        if await db.revoked_auth_tokens.find_one({"_id": hashlib.sha256(token.encode()).hexdigest()}):
            raise HTTPException(401, "Session revoked — please sign in again")
        if payload.get("session_id") and await db.revoked_auth_sessions.find_one({"_id":payload["session_id"]}):
            raise HTTPException(401, "Session revoked — please sign in again")
        require_session(user, payload)

        # SEC P3 — Reject refresh tokens minted before the user's most
        # recent password change. Stops a stolen 7-day refresh token
        # from outliving a password reset.
        changed_at = user.get("password_changed_at")
        if predates_password_change(payload.get("iat"), changed_at):
            response.delete_cookie("access_token", path="/")
            response.delete_cookie("refresh_token", path="/")
            raise HTTPException(status_code=401, detail="Session revoked — please sign in again")

        user_id = str(user["_id"])
        access_token = create_access_token(user_id, user["email"], session_id=payload.get("session_id"), token_version=int(user.get("token_version") or 0))
        response.set_cookie(key="access_token", value=access_token, httponly=True,
                            secure=cookie_secure, samesite=cookie_samesite,
                            max_age=43200 if payload.get("remember",True) else None, path="/")
        return {"message": "Token refreshed", "access_token": access_token, "refresh_token": token}
    except HTTPException as exc:
        return rejected(exc.detail)
    except jwt.ExpiredSignatureError:
        return rejected("Refresh token expired")
    except jwt.InvalidTokenError:
        return rejected("Invalid refresh token")


@router.post("/auth/forgot-password")
async def forgot_password(request: Request):
    M = _models()
    body = await _json_body(request)
    try:
        input = M["ForgotPassword"](**body)
    except ValidationError as exc:
        raise HTTPException(422, detail=[{"loc": e["loc"], "msg": e["msg"], "type": e["type"]} for e in exc.errors()]) from exc
    db = _db()
    logger = _logger()
    email = input.email.strip().lower()

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
    from services.account_mail import send_link
    await send_link(db, _deps, email, "Reset your password", "/reset-password", token)
    return {"message": "If an account exists, a reset link has been sent"}


@router.post("/auth/reset-password")
async def reset_password(request: Request, response: Response):
    M = _models()
    body = await _json_body(request)
    try:
        input = M["ResetPassword"](**body)
    except ValidationError as exc:
        raise HTTPException(422, detail=[{"loc": e["loc"], "msg": e["msg"], "type": e["type"]} for e in exc.errors()]) from exc
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
    account = await db.users.find_one({"_id": ObjectId(token_doc["user_id"])})
    require_active(account)
    claimed = await db.password_reset_tokens.update_one({"_id": token_doc["_id"], "used": False}, {"$set": {"used": True}})
    if not claimed.modified_count:
        raise HTTPException(400, "Invalid or expired token")
    changed = await db.users.update_one(
        {"_id": ObjectId(token_doc["user_id"]), "password_hash": account["password_hash"]},
        {"$set": {
            "password_hash": hash_password(input.new_password),
            "password_changed_at": now.isoformat(),
        }},
    )
    if not changed.modified_count:
        raise HTTPException(400, "Invalid or expired token")
    await db.user_sessions.update_many({"user_id":token_doc["user_id"]},{"$set":{"revoked":True}})
    await db.password_reset_tokens.update_many({"user_id": token_doc["user_id"]}, {"$set": {"used": True}})
    from services.account_access import disconnect_sessions
    await disconnect_sessions(_deps,token_doc["user_id"])
    # Best-effort cookie clear (no harm if the caller wasn't logged in).
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")
    return {"message": "Password reset successfully"}


@router.post('/auth/resend-verification')
async def resend_verification(request: Request):
    from services.account_verification import issue
    user=await _deps['get_current_user'](request)
    if user.get('email_verified') and not user.get('verification_email'):
        return {'message':'Email already verified'}
    await issue(_db(),_deps,user,user.get('verification_email'))
    return {'message':'Verification email requested'}

@router.post('/auth/verify-email')
async def verify_email(request: Request):
    from services.account_verification import complete
    body=await _json_body(request)
    token=body.get('token')
    if not isinstance(token,str) or not token:
        raise HTTPException(400,'Invalid or expired verification link')
    user=await complete(_db(),token)
    if user['email'] != user.get('verification_email'):
        from services.account_mail import send_notice
        await send_notice(_db(),_deps,user['email'],'Your account email changed','Your account email was changed. Contact support if you did not request this.')
    return {'message':'Email verified. You can sign in with the verified address.'}

@router.post('/auth/change-password')
async def change_password(request: Request, response: Response):
    from services.account_access import validate_password
    user=await _deps['get_current_user'](request)
    body=await _json_body(request)
    current=body.get('current_password')
    password=body.get('new_password')
    if not isinstance(current,str) or not isinstance(password,str):
        raise HTTPException(422,'Current and new passwords are required')
    account=await _db().users.find_one({'_id':ObjectId(user['_id'])})
    if not _deps['verify_password'](current,account.get('password_hash','')):
        raise HTTPException(400,'Current password is incorrect')
    try: validate_password(password)
    except ValueError as exc: raise HTTPException(422,str(exc))
    result=await _db().users.update_one({'_id':account['_id'],'password_hash':account['password_hash']},
        {'$set':{'password_hash':_deps['hash_password'](password),'password_changed_at':datetime.now(timezone.utc).isoformat()}})
    if not result.modified_count: raise HTTPException(409,'Account changed. Please sign in again')
    await _db().user_sessions.update_many({'user_id':str(account['_id'])},{'$set':{'revoked':True}})
    await _db().password_reset_tokens.update_many({'user_id':str(account['_id'])},{'$set':{'used':True}})
    from services.account_access import disconnect_sessions
    await disconnect_sessions(_deps,user['_id'])
    response.delete_cookie('access_token',path='/')
    response.delete_cookie('refresh_token',path='/')
    return {'message':'Password changed. Please sign in again.'}
