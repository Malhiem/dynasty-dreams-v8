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

    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="Email already registered")
    if await db.users.find_one({"username": username}):
        raise HTTPException(status_code=400, detail="Username already taken")

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
    return UserResponse(
        id=user["_id"], email=user["email"],
        username=user.get("username") or user.get("name", ""),
        name=user.get("username") or user.get("name", ""),
        role=user["role"], created_at=user["created_at"],
    )


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
    user = await db.users.find_one({"email": email})
    if not user:
        return {"message": "If an account exists, a reset link has been sent"}
    token = secrets.token_urlsafe(32)
    await db.password_reset_tokens.insert_one({
        "token": token,
        "user_id": str(user["_id"]),
        "expires_at": datetime.now(timezone.utc) + timedelta(hours=1),
        "used": False,
    })
    logger.info(f"Password reset link: /reset-password?token={token}")
    return {"message": "If an account exists, a reset link has been sent"}


@router.post("/auth/reset-password")
async def reset_password(request: Request):
    M = _models()
    body = await request.json()
    input = M["ResetPassword"](**body)
    db = _db()
    hash_password = _deps["hash_password"]
    token_doc = await db.password_reset_tokens.find_one({"token": input.token, "used": False})
    if not token_doc:
        raise HTTPException(status_code=400, detail="Invalid or expired token")
    if datetime.now(timezone.utc) > token_doc["expires_at"]:
        raise HTTPException(status_code=400, detail="Token expired")
    await db.users.update_one(
        {"_id": ObjectId(token_doc["user_id"])},
        {"$set": {"password_hash": hash_password(input.new_password)}},
    )
    await db.password_reset_tokens.update_one({"token": input.token}, {"$set": {"used": True}})
    return {"message": "Password reset successfully"}
