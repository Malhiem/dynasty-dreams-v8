from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

from fastapi import FastAPI, APIRouter, HTTPException, Request, Response, Depends, Query
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
import os
import logging
import uuid
import secrets
import bcrypt
import jwt
import socketio
import asyncio
import re
from datetime import datetime, timezone, timedelta
from pydantic import BaseModel, Field, ConfigDict, EmailStr
from typing import List, Optional, Dict, Any
from enum import Enum

# Stripe Integration
from emergentintegrations.payments.stripe.checkout import (
    StripeCheckout, CheckoutSessionResponse, CheckoutStatusResponse, CheckoutSessionRequest
)

# SendGrid Integration (graceful fallback if key missing)
try:
    from sendgrid import SendGridAPIClient
    from sendgrid.helpers.mail import Mail as SendGridMail
    _SENDGRID_AVAILABLE = True
except Exception:
    _SENDGRID_AVAILABLE = False


def send_sendgrid_email(to_email: str, subject: str, html_content: str) -> dict:
    """Send an email via SendGrid. Returns dict with status.
    Gracefully degrades to mock-logged response when SENDGRID_API_KEY is missing
    or SDK import failed."""
    api_key = os.environ.get("SENDGRID_API_KEY", "").strip()
    sender = os.environ.get("SENDER_EMAIL", "no-reply@dynastydreams.app").strip()

    if not api_key or not _SENDGRID_AVAILABLE:
        return {"status": "mocked", "to": to_email, "reason": "SENDGRID_API_KEY not configured"}

    try:
        message = SendGridMail(
            from_email=sender,
            to_emails=to_email,
            subject=subject,
            html_content=html_content,
        )
        sg = SendGridAPIClient(api_key)
        resp = sg.send(message)
        return {"status": "sent", "to": to_email, "code": resp.status_code}
    except Exception as e:
        # Log and degrade gracefully so invite flow never breaks
        logger.warning(f"SendGrid send failed for {to_email}: {e}")
        return {"status": "error", "to": to_email, "error": str(e)}

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# JWT Configuration
JWT_ALGORITHM = "HS256"

# Cookie configuration — default to Secure on HTTPS. Overridable via env.
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "true").lower() in ("true", "1", "yes")
COOKIE_SAMESITE = os.environ.get("COOKIE_SAMESITE", "lax")

def get_jwt_secret() -> str:
    return os.environ["JWT_SECRET"]

# Password Hashing
def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))

# JWT Token Management
def create_access_token(user_id: str, email: str) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=15),
        "type": "access"
    }
    return jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)

def create_refresh_token(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "exp": datetime.now(timezone.utc) + timedelta(days=7),
        "type": "refresh"
    }
    return jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)

# Auth Helper
async def get_current_user(request: Request) -> dict:
    token = request.cookies.get("access_token")
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(token, get_jwt_secret(), algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Invalid token type")
        user = await db.users.find_one({"_id": ObjectId(payload["sub"])})
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        user["_id"] = str(user["_id"])
        user.pop("password_hash", None)
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

# Enums
class UserRole(str, Enum):
    USER = "user"
    COMMISSIONER = "commissioner"
    ADMIN = "admin"

class LeagueFormat(str, Enum):
    REDRAFT = "redraft"
    KEEPER = "keeper"
    DYNASTY = "dynasty"
    BEST_BALL = "best_ball"

class ScoringFormat(str, Enum):
    HEAD_TO_HEAD = "head_to_head"
    TOTAL_POINTS = "total_points"
    ROTISSERIE = "rotisserie"
    GUILLOTINE = "guillotine"
    ALL_PLAY = "all_play"

class DraftType(str, Enum):
    SNAKE = "snake"
    LINEAR = "linear"
    AUCTION = "auction"
    CUSTOM = "custom"

class TransactionType(str, Enum):
    TRADE = "trade"
    WAIVER = "waiver"
    FREE_AGENT = "free_agent"
    DROP = "drop"

# Pydantic Models
class UserRegister(BaseModel):
    email: EmailStr
    password: str
    username: str = Field(..., min_length=3, max_length=24, pattern=r"^[a-zA-Z0-9_-]+$")

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    id: str
    email: str
    username: str
    name: str  # Retained for backward compat — mirrors username
    role: str
    created_at: datetime
    access_token: Optional[str] = None  # Populated on login/register for mobile/Bearer clients
    refresh_token: Optional[str] = None

class ForgotPassword(BaseModel):
    email: EmailStr

class ResetPassword(BaseModel):
    token: str
    new_password: str

class LeagueCreate(BaseModel):
    name: str
    sport: str = "nhl"
    format: LeagueFormat
    scoring_format: ScoringFormat
    max_teams: int = Field(default=12, ge=4, le=32)
    salary_cap_enabled: bool = False
    salary_cap: Optional[float] = None
    draft_type: DraftType = DraftType.SNAKE
    roster_spots: int = Field(default=20, ge=10, le=30)
    keepers_allowed: int = Field(default=0, ge=0, le=10)
    entry_fee: Optional[float] = None
    is_private: bool = False

class LeagueResponse(BaseModel):
    id: str
    name: str
    sport: str = "nhl"
    format: str
    scoring_format: str
    max_teams: int
    current_teams: int
    commissioner_id: str
    commissioner_name: str
    co_commissioners: List[str] = []
    salary_cap_enabled: bool
    salary_cap: Optional[float]
    draft_type: str
    roster_spots: int
    keepers_allowed: int
    entry_fee: Optional[float]
    is_private: bool
    status: str
    invite_code: Optional[str] = None
    created_at: datetime

class TeamCreate(BaseModel):
    name: str
    league_id: str

class TeamResponse(BaseModel):
    id: str
    name: str
    league_id: str
    owner_id: str
    owner_name: str
    salary_used: float
    wins: int
    losses: int
    ties: int
    points_for: float
    points_against: float
    created_at: datetime
    roster: List[str] = []
    live_points: float = 0.0
    logo_abbr: Optional[str] = None
    championship_won_at: Optional[datetime] = None
    division_winner_at: Optional[datetime] = None
    conference_winner_at: Optional[datetime] = None
    playoffs_reached_at: Optional[datetime] = None
    consolation_won_at: Optional[datetime] = None

class PaymentCreate(BaseModel):
    package_type: str  # "premium_monthly", "premium_yearly", "league_fee"
    league_id: Optional[str] = None
    origin_url: str

# Payment packages (server-side only)
PAYMENT_PACKAGES = {
    "premium_monthly": {"amount": 9.99, "name": "Premium Monthly"},
    "premium_yearly": {"amount": 79.99, "name": "Premium Yearly"},
    "league_fee": {"amount": 0.0, "name": "League Entry Fee"},  # Dynamic based on league
    "league_premium": {"amount": 29.99, "name": "League Premium Unlock"}  # One-time per league
}

# Premium features unlocked by league_premium package
LEAGUE_PREMIUM_FEATURES = [
    {"id": "salary_cap", "name": "Dynasty Salary Cap", "description": "Full AAV contracts, NTC/NMC clauses, cap tracking"},
    {"id": "contracts", "name": "Multi-Year Contracts", "description": "Issue 1–8 year deals with escalators and bonuses"},
    {"id": "draft_scheduling", "name": "Advanced Draft Scheduling", "description": "Auto-schedule snake/auction/rookie drafts with reminders"},
    {"id": "minor_leagues", "name": "Minor League / Farm System", "description": "Taxi squad + prospect development slots"},
    {"id": "custom_scoring", "name": "Custom Scoring Profiles", "description": "Build your own point values per stat"},
    {"id": "activity_webhooks", "name": "Activity Webhooks", "description": "Push every trade/waiver to Discord, Slack, or a custom URL"},
]

# Create FastAPI app
fastapi_app = FastAPI(title="Dynasty Dreams API", version="1.0.0")

# Create API router
api_router = APIRouter(prefix="/api")

# Socket.IO Setup
sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins='*')

# Connected users tracking
connected_users: Dict[str, Dict[str, Any]] = {}

@sio.event
async def connect(sid, environ):
    logger.info(f"Client connected: {sid}")

@sio.event
async def disconnect(sid):
    logger.info(f"Client disconnected: {sid}")
    # Remove from all rooms and tracking
    if sid in connected_users:
        del connected_users[sid]

@sio.event
async def join_room(sid, data):
    room_id = data.get("room_id")
    user_id = data.get("user_id")
    if not room_id:
        logger.warning(f"join_room called without room_id for {sid}")
        return
    await sio.enter_room(sid, room_id)
    # Also join personal notification room
    if user_id:
        await sio.enter_room(sid, f"user_{user_id}")
    connected_users[sid] = {"room_id": room_id, "user_id": user_id}
    logger.info(f"Client {sid} joined room {room_id}")
    await sio.emit('user_joined', {"user_id": user_id, "room_id": room_id}, room=room_id)

@sio.event
async def leave_room(sid, data):
    room_id = data.get("room_id")
    if room_id:
        await sio.leave_room(sid, room_id)
        logger.info(f"Client {sid} left room {room_id}")

async def broadcast_to_room(room: str, event: str, message: dict):
    await sio.emit(event, message, room=room)

# Auth Endpoints
@api_router.post("/auth/register", response_model=UserResponse)
async def register(input: UserRegister, response: Response):
    email = input.email.lower()
    username = input.username.strip()

    existing = await db.users.find_one({"email": email})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    if await db.users.find_one({"username": username}):
        raise HTTPException(status_code=400, detail="Username already taken")

    user_doc = {
        "email": email,
        "password_hash": hash_password(input.password),
        "username": username,
        "name": username,  # Keep `name` in sync for backward-compat
        "role": UserRole.USER.value,
        "subscription": None,
        "created_at": datetime.now(timezone.utc)
    }
    result = await db.users.insert_one(user_doc)
    user_id = str(result.inserted_id)
    
    access_token = create_access_token(user_id, email)
    refresh_token = create_refresh_token(user_id)
    
    response.set_cookie(key="access_token", value=access_token, httponly=True, secure=COOKIE_SECURE, samesite=COOKIE_SAMESITE, max_age=43200, path="/")
    response.set_cookie(key="refresh_token", value=refresh_token, httponly=True, secure=COOKIE_SECURE, samesite=COOKIE_SAMESITE, max_age=604800, path="/")
    
    return UserResponse(
        id=user_id,
        email=email,
        username=username,
        name=username,
        role=UserRole.USER.value,
        created_at=user_doc["created_at"],
        access_token=access_token,
        refresh_token=refresh_token,
    )

@api_router.post("/auth/login", response_model=UserResponse)
async def login(input: UserLogin, request: Request, response: Response):
    email = input.email.lower()
    identifier = f"{request.client.host}:{email}"
    
    # Check brute force
    attempts = await db.login_attempts.find_one({"identifier": identifier})
    if attempts and attempts.get("count", 0) >= 5:
        lockout_until = attempts.get("lockout_until")
        if lockout_until and datetime.now(timezone.utc) < lockout_until:
            raise HTTPException(status_code=429, detail="Too many login attempts. Try again later.")
        else:
            await db.login_attempts.delete_one({"identifier": identifier})
    
    user = await db.users.find_one({"email": email})
    if not user or not verify_password(input.password, user["password_hash"]):
        # Increment failed attempts
        await db.login_attempts.update_one(
            {"identifier": identifier},
            {
                "$inc": {"count": 1},
                "$set": {"lockout_until": datetime.now(timezone.utc) + timedelta(minutes=15)}
            },
            upsert=True
        )
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    # Clear failed attempts on success
    await db.login_attempts.delete_one({"identifier": identifier})
    
    user_id = str(user["_id"])
    access_token = create_access_token(user_id, email)
    refresh_token = create_refresh_token(user_id)
    
    response.set_cookie(key="access_token", value=access_token, httponly=True, secure=COOKIE_SECURE, samesite=COOKIE_SAMESITE, max_age=43200, path="/")
    response.set_cookie(key="refresh_token", value=refresh_token, httponly=True, secure=COOKIE_SECURE, samesite=COOKIE_SAMESITE, max_age=604800, path="/")
    
    return UserResponse(
        id=user_id,
        email=user["email"],
        username=user.get("username") or user.get("name", ""),
        name=user.get("username") or user.get("name", ""),
        role=user["role"],
        created_at=user["created_at"],
        access_token=access_token,
        refresh_token=refresh_token,
    )

@api_router.post("/auth/logout")
async def logout(response: Response):
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")
    return {"message": "Logged out successfully"}

@api_router.get("/auth/me", response_model=UserResponse)
async def get_me(request: Request):
    user = await get_current_user(request)
    return UserResponse(
        id=user["_id"],
        email=user["email"],
        username=user.get("username") or user.get("name", ""),
        name=user.get("username") or user.get("name", ""),
        role=user["role"],
        created_at=user["created_at"]
    )

@api_router.post("/auth/refresh")
async def refresh_token(request: Request, response: Response):
    # Accept refresh token from cookie OR Authorization header (for mobile)
    token = request.cookies.get("refresh_token")
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
    if not token:
        raise HTTPException(status_code=401, detail="No refresh token")
    try:
        payload = jwt.decode(token, get_jwt_secret(), algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")
        user = await db.users.find_one({"_id": ObjectId(payload["sub"])})
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        
        user_id = str(user["_id"])
        access_token = create_access_token(user_id, user["email"])
        response.set_cookie(key="access_token", value=access_token, httponly=True, secure=COOKIE_SECURE, samesite=COOKIE_SAMESITE, max_age=43200, path="/")
        return {"message": "Token refreshed", "access_token": access_token, "refresh_token": token}
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Refresh token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

@api_router.post("/auth/forgot-password")
async def forgot_password(input: ForgotPassword):
    email = input.email.lower()
    user = await db.users.find_one({"email": email})
    if not user:
        return {"message": "If an account exists, a reset link has been sent"}
    
    token = secrets.token_urlsafe(32)
    await db.password_reset_tokens.insert_one({
        "token": token,
        "user_id": str(user["_id"]),
        "expires_at": datetime.now(timezone.utc) + timedelta(hours=1),
        "used": False
    })
    logger.info(f"Password reset link: /reset-password?token={token}")
    return {"message": "If an account exists, a reset link has been sent"}

@api_router.post("/auth/reset-password")
async def reset_password(input: ResetPassword):
    token_doc = await db.password_reset_tokens.find_one({"token": input.token, "used": False})
    if not token_doc:
        raise HTTPException(status_code=400, detail="Invalid or expired token")
    if datetime.now(timezone.utc) > token_doc["expires_at"]:
        raise HTTPException(status_code=400, detail="Token expired")
    
    await db.users.update_one(
        {"_id": ObjectId(token_doc["user_id"])},
        {"$set": {"password_hash": hash_password(input.new_password)}}
    )
    await db.password_reset_tokens.update_one({"token": input.token}, {"$set": {"used": True}})
    return {"message": "Password reset successfully"}

# League Endpoints
@api_router.post("/leagues", response_model=LeagueResponse)
async def create_league(input: LeagueCreate, request: Request):
    user = await get_current_user(request)
    
    league_doc = {
        "name": input.name,
        "sport": input.sport,
        "format": input.format.value,
        "scoring_format": input.scoring_format.value,
        "max_teams": input.max_teams,
        "current_teams": 0,
        "commissioner_id": user["_id"],
        "commissioner_name": user["name"],
        "salary_cap_enabled": input.salary_cap_enabled,
        "salary_cap": input.salary_cap if input.salary_cap_enabled else None,
        "draft_type": input.draft_type.value,
        "roster_spots": input.roster_spots,
        "keepers_allowed": input.keepers_allowed,
        "entry_fee": input.entry_fee,
        "is_private": input.is_private,
        "invite_code": secrets.token_urlsafe(8),
        "status": "setup",
        "created_at": datetime.now(timezone.utc)
    }
    result = await db.leagues.insert_one(league_doc)
    league_id = str(result.inserted_id)
    
    # Update user to commissioner if not already
    if user["role"] == UserRole.USER.value:
        await db.users.update_one({"_id": ObjectId(user["_id"])}, {"$set": {"role": UserRole.COMMISSIONER.value}})
    
    return LeagueResponse(
        id=league_id,
        name=league_doc["name"],
        sport=league_doc.get("sport", "nhl"),
        format=league_doc["format"],
        scoring_format=league_doc["scoring_format"],
        max_teams=league_doc["max_teams"],
        current_teams=0,
        commissioner_id=league_doc["commissioner_id"],
        commissioner_name=league_doc["commissioner_name"],
        co_commissioners=league_doc.get("co_commissioners", []) or [],
        salary_cap_enabled=league_doc["salary_cap_enabled"],
        salary_cap=league_doc["salary_cap"],
        draft_type=league_doc["draft_type"],
        roster_spots=league_doc["roster_spots"],
        keepers_allowed=league_doc["keepers_allowed"],
        entry_fee=league_doc["entry_fee"],
        is_private=league_doc["is_private"],
        status=league_doc["status"],
        invite_code=league_doc.get("invite_code"),
        created_at=league_doc["created_at"]
    )

@api_router.get("/leagues", response_model=List[LeagueResponse])
async def get_leagues(request: Request, my_leagues: bool = False):
    user = None
    try:
        user = await get_current_user(request)
    except:
        pass
    
    query = {}
    if my_leagues and user:
        # Get leagues where user is commissioner or has a team
        user_teams = await db.teams.find({"owner_id": user["_id"]}, {"league_id": 1}).to_list(100)
        league_ids = [t["league_id"] for t in user_teams]
        query = {"$or": [{"commissioner_id": user["_id"]}, {"_id": {"$in": [ObjectId(lid) for lid in league_ids]}}]}
    elif not my_leagues:
        query = {"is_private": False}
    
    leagues = await db.leagues.find(query).to_list(100)
    return [
        LeagueResponse(
            id=str(league["_id"]),
            name=league["name"],
            sport=league.get("sport", "nhl"),
            format=league["format"],
            scoring_format=league["scoring_format"],
            max_teams=league["max_teams"],
            current_teams=league.get("current_teams", 0),
            commissioner_id=league["commissioner_id"],
            commissioner_name=league["commissioner_name"],
            co_commissioners=league.get("co_commissioners", []) or [],
            salary_cap_enabled=league["salary_cap_enabled"],
            salary_cap=league.get("salary_cap"),
            draft_type=league["draft_type"],
            roster_spots=league["roster_spots"],
            keepers_allowed=league["keepers_allowed"],
            entry_fee=league.get("entry_fee"),
            is_private=league["is_private"],
            status=league["status"],
            invite_code=league.get("invite_code"),
            created_at=league["created_at"]
        )
        for league in leagues
    ]

@api_router.get("/leagues/{league_id}", response_model=LeagueResponse)
async def get_league(league_id: str):
    league = await db.leagues.find_one({"_id": ObjectId(league_id)})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    
    return LeagueResponse(
        id=str(league["_id"]),
        name=league["name"],
        sport=league.get("sport", "nhl"),
        format=league["format"],
        scoring_format=league["scoring_format"],
        max_teams=league["max_teams"],
        current_teams=league.get("current_teams", 0),
        commissioner_id=league["commissioner_id"],
        commissioner_name=league["commissioner_name"],
        co_commissioners=league.get("co_commissioners", []) or [],
        salary_cap_enabled=league["salary_cap_enabled"],
        salary_cap=league.get("salary_cap"),
        draft_type=league["draft_type"],
        roster_spots=league["roster_spots"],
        keepers_allowed=league["keepers_allowed"],
        entry_fee=league.get("entry_fee"),
        is_private=league["is_private"],
        status=league["status"],
        invite_code=league.get("invite_code"),
        created_at=league["created_at"]
    )

# ─── League Invite System ─────────────────────────────────────
import qrcode
import io
import base64
from fastapi.responses import StreamingResponse


# ─── League Constitution + Audit Log ──────────────────────────

class ConstitutionUpdate(BaseModel):
    content: str = Field(..., max_length=5000)


@api_router.get("/leagues/{league_id}/constitution")
async def get_constitution(league_id: str):
    league = await db.leagues.find_one(
        {"_id": _safe_object_id(league_id, "league_id")},
        {"constitution": 1, "constitution_updated_at": 1, "constitution_updated_by": 1}
    )
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    return {
        "league_id": league_id,
        "content": league.get("constitution", ""),
        "updated_at": league.get("constitution_updated_at"),
        "updated_by": league.get("constitution_updated_by"),
    }


@api_router.put("/leagues/{league_id}/constitution")
async def update_constitution(league_id: str, payload: ConstitutionUpdate, request: Request):
    user = await get_current_user(request)
    league = await db.leagues.find_one({"_id": _safe_object_id(league_id, "league_id")})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")

    # Commissioner or co-commissioner can edit
    is_comm = league["commissioner_id"] == user["_id"]
    co_comms = league.get("co_commissioners", []) or []
    is_co_comm = user["_id"] in co_comms
    if not (is_comm or is_co_comm):
        raise HTTPException(status_code=403, detail="Only commissioners and co-commissioners can edit the constitution")

    now = datetime.now(timezone.utc)
    previous = league.get("constitution", "")
    await db.leagues.update_one(
        {"_id": league["_id"]},
        {"$set": {
            "constitution": payload.content,
            "constitution_updated_at": now,
            "constitution_updated_by": user["_id"],
        }}
    )

    # Write audit event
    audit_event = {
        "league_id": league_id,
        "actor_id": user["_id"],
        "actor_name": user.get("name", user.get("email", "Unknown")),
        "action": "constitution_updated",
        "role": "commissioner" if is_comm else "co_commissioner",
        "diff": {
            "previous_length": len(previous or ""),
            "new_length": len(payload.content or ""),
            "preview": (payload.content or "")[:180],
        },
        "created_at": now,
    }
    await db.audit_log.insert_one(audit_event)

    # Broadcast to league activity feed for visibility
    try:
        await db.activity_feed.insert_one({
            "league_id": league_id,
            "event_type": "constitution_updated",
            "description": f"{user.get('name', 'A commissioner')} updated the League Constitution",
            "message": f"{user.get('name', 'A commissioner')} updated the League Constitution",
            "actor_id": user["_id"],
            "actor_name": user.get("name"),
            "created_at": now,
        })
    except Exception:
        pass

    return {
        "league_id": league_id,
        "content": payload.content,
        "updated_at": now,
        "updated_by": user["_id"],
    }


@api_router.get("/leagues/{league_id}/audit-log")
async def get_audit_log(league_id: str, request: Request, limit: int = 100):
    user = await get_current_user(request)
    league = await db.leagues.find_one({"_id": _safe_object_id(league_id, "league_id")})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    is_comm = league["commissioner_id"] == user["_id"]
    co_comms = league.get("co_commissioners", []) or []
    is_co_comm = user["_id"] in co_comms
    if not (is_comm or is_co_comm):
        raise HTTPException(status_code=403, detail="Only commissioners and co-commissioners can view the audit log")
    events = await db.audit_log.find({"league_id": league_id}).sort("created_at", -1).limit(max(1, min(limit, 500))).to_list(500)
    for e in events:
        e["id"] = str(e.pop("_id"))
    return {"league_id": league_id, "events": events}


class LeagueInviteResponse(BaseModel):
    invite_code: str
    invite_url: str
    qr_code_base64: str


class JoinByInviteRequest(BaseModel):
    invite_code: str
    team_name: str


class EmailInviteRequest(BaseModel):
    league_id: str
    emails: list[str]


@api_router.get("/leagues/{league_id}/invite")
async def get_league_invite(league_id: str, request: Request):
    user = await get_current_user(request)
    league = await db.leagues.find_one({"_id": ObjectId(league_id)})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")

    # Generate invite code if missing
    invite_code = league.get("invite_code")
    if not invite_code:
        invite_code = secrets.token_urlsafe(8)
        await db.leagues.update_one({"_id": ObjectId(league_id)}, {"$set": {"invite_code": invite_code}})

    frontend_url = os.environ.get("FRONTEND_URL", "https://dynasty-preview.preview.emergentagent.com")
    invite_url = f"{frontend_url}/join/{invite_code}"

    # Generate QR code
    qr = qrcode.QRCode(version=1, box_size=8, border=2)
    qr.add_data(invite_url)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="#00D2FF", back_color="#0A0A0A")
    buffer = io.BytesIO()
    qr_img.save(buffer, format="PNG")
    qr_base64 = base64.b64encode(buffer.getvalue()).decode()

    return LeagueInviteResponse(
        invite_code=invite_code,
        invite_url=invite_url,
        qr_code_base64=qr_base64
    )


@api_router.get("/leagues/{league_id}/invite/qr")
async def get_invite_qr_image(league_id: str):
    league = await db.leagues.find_one({"_id": ObjectId(league_id)})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")

    invite_code = league.get("invite_code", "")
    frontend_url = os.environ.get("FRONTEND_URL", "https://dynasty-preview.preview.emergentagent.com")
    invite_url = f"{frontend_url}/join/{invite_code}"

    qr = qrcode.QRCode(version=1, box_size=10, border=3)
    qr.add_data(invite_url)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="#00D2FF", back_color="#0A0A0A")
    buffer = io.BytesIO()
    qr_img.save(buffer, format="PNG")
    buffer.seek(0)

    return StreamingResponse(buffer, media_type="image/png")


@api_router.post("/leagues/join-by-invite")
async def join_league_by_invite(input: JoinByInviteRequest, request: Request):
    user = await get_current_user(request)

    league = await db.leagues.find_one({"invite_code": input.invite_code})
    if not league:
        raise HTTPException(status_code=404, detail="Invalid invite code")

    league_id = str(league["_id"])

    if league.get("current_teams", 0) >= league["max_teams"]:
        raise HTTPException(status_code=400, detail="League is full")

    existing = await db.teams.find_one({"league_id": league_id, "owner_id": user["_id"]})
    if existing:
        raise HTTPException(status_code=400, detail="You already have a team in this league")

    team_doc = {
        "name": input.team_name,
        "league_id": league_id,
        "owner_id": user["_id"],
        "owner_name": user["name"],
        "roster": [],
        "salary_used": 0.0,
        "wins": 0, "losses": 0, "ties": 0,
        "points_for": 0.0, "points_against": 0.0,
        "created_at": datetime.now(timezone.utc)
    }
    result = await db.teams.insert_one(team_doc)
    await db.leagues.update_one({"_id": ObjectId(league_id)}, {"$inc": {"current_teams": 1}})

    await log_activity(league_id, "team_joined", f"{user['name']} joined with team '{input.team_name}'", user["_id"])

    return {"message": f"Joined {league['name']}!", "team_id": str(result.inserted_id), "league_id": league_id, "league_name": league["name"]}


@api_router.post("/leagues/{league_id}/invite/email")
async def send_email_invites(league_id: str, input: EmailInviteRequest, request: Request):
    user = await get_current_user(request)
    league = await db.leagues.find_one({"_id": ObjectId(league_id)})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    if league["commissioner_id"] != user["_id"]:
        raise HTTPException(status_code=403, detail="Only commissioner can send invites")

    invite_code = league.get("invite_code", "")
    frontend_url = os.environ.get("FRONTEND_URL", "https://dynasty-preview.preview.emergentagent.com")
    invite_url = f"{frontend_url}/join/{invite_code}"

    # Build HTML email body
    subject = f"You're invited to join '{league['name']}' on Dynasty Dreams"
    html_template = f"""
    <div style="font-family: -apple-system, Segoe UI, Roboto, sans-serif; max-width: 560px; margin: auto; padding: 24px; background: #0b1020; color: #e6edf7; border-radius: 12px;">
      <h1 style="margin:0 0 8px; font-size: 22px; color:#7cf9d0;">Dynasty Dreams</h1>
      <p style="margin:0 0 16px; color:#9aa6c2;">Fantasy sports, re-imagined.</p>
      <h2 style="font-size:18px; margin:12px 0;">{user['name']} invited you to <span style="color:#7cf9d0;">{league['name']}</span></h2>
      <p style="color:#c9d3ea; line-height:1.5;">Click the button below to accept your invite, create your team, and join the league.</p>
      <p style="text-align:center; margin: 24px 0;">
        <a href="{invite_url}" style="background:#7cf9d0; color:#0b1020; padding: 12px 24px; border-radius: 999px; text-decoration:none; font-weight:700;">Join League</a>
      </p>
      <p style="color:#7a88a8; font-size:12px;">Or paste this link into your browser:<br/><a href="{invite_url}" style="color:#7cf9d0;">{invite_url}</a></p>
      <p style="color:#7a88a8; font-size:12px;">Invite code: <code>{invite_code}</code></p>
    </div>
    """

    # Store invite records + dispatch via SendGrid (graceful fallback when key missing)
    results = []
    for email in input.emails:
        send_result = send_sendgrid_email(email, subject, html_template)
        await db.league_invites.update_one(
            {"league_id": league_id, "email": email.lower()},
            {"$set": {
                "league_id": league_id,
                "league_name": league["name"],
                "email": email.lower(),
                "invite_code": invite_code,
                "invite_url": invite_url,
                "invited_by": user["_id"],
                "status": send_result.get("status", "sent"),
                "provider_response": {k: v for k, v in send_result.items() if k != "to"},
                "sent_at": datetime.now(timezone.utc).isoformat()
            }},
            upsert=True
        )
        results.append(send_result)

    sent_count = sum(1 for r in results if r.get("status") == "sent")
    mocked_count = sum(1 for r in results if r.get("status") == "mocked")
    error_count = sum(1 for r in results if r.get("status") == "error")

    logger.info(
        f"Invites for '{league['name']}': sent={sent_count}, mocked={mocked_count}, errors={error_count}"
    )
    return {
        "message": f"Invites processed for {len(input.emails)} email(s)",
        "invite_url": invite_url,
        "sent": sent_count,
        "mocked": mocked_count,
        "errors": error_count,
        "results": results,
    }


# ─── League Premium (Stripe) ─────────────────────────────────

@api_router.get("/leagues/{league_id}/premium")
async def get_league_premium(league_id: str, request: Request):
    """Return premium status + feature list for a league."""
    await get_current_user(request)
    league = await db.leagues.find_one({"_id": _safe_object_id(league_id, "league_id")})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    return {
        "league_id": league_id,
        "premium": bool(league.get("premium", False)),
        "activated_at": league.get("premium_activated_at").isoformat() if league.get("premium_activated_at") else None,
        "price_usd": PAYMENT_PACKAGES["league_premium"]["amount"],
        "features": LEAGUE_PREMIUM_FEATURES,
        "unlocked_features": league.get("premium_features", []),
    }


# ─── Personalized League Recommendations ─────────────────────

@api_router.get("/recommendations/leagues")
async def recommend_leagues(
    request: Request,
    commitment: str = Query("any", description="casual | serious | hardcore | any"),
    scoring: str = Query("any", description="head_to_head | rotisserie | total_points | any"),
    draft_style: str = Query("any", description="snake | auction | any"),
    limit: int = Query(5, ge=1, le=20),
):
    """Personalized league recommendations based on user state + preferences.
    Returns a ranked list — user's own in-progress leagues first, then open public
    leagues scored against the three preference dimensions."""
    user = await get_current_user(request)

    # 1) User's own leagues (continue where you left off)
    own_team_docs = await db.teams.find({"owner_id": user["_id"]}).to_list(200)
    own_league_ids = list({t["league_id"] for t in own_team_docs})
    own_leagues = []
    if own_league_ids:
        cursor = db.leagues.find({"_id": {"$in": [ObjectId(lid) for lid in own_league_ids]}})
        own_leagues = await cursor.to_list(50)

    # 2) Candidate open leagues (not private, room available)
    cursor = db.leagues.find({
        "is_private": {"$ne": True},
        "$expr": {"$lt": ["$current_teams", "$max_teams"]},
        "_id": {"$nin": [l["_id"] for l in own_leagues]},
    })
    candidates = await cursor.to_list(200)

    # Commitment buckets (map to format)
    commitment_format_map = {
        "casual":   ["redraft", "best_ball"],
        "serious":  ["keeper"],
        "hardcore": ["dynasty"],
    }

    def score(lg: dict) -> int:
        s = 0
        fmt = lg.get("format", "")
        sc = lg.get("scoring_format", "")
        dr = lg.get("draft_type", "")

        if commitment in commitment_format_map and fmt in commitment_format_map[commitment]:
            s += 40
        elif commitment == "any":
            s += 10

        if scoring != "any" and sc == scoring:
            s += 30
        elif scoring == "any":
            s += 10

        if draft_style != "any" and dr == draft_style:
            s += 20
        elif draft_style == "any":
            s += 5

        # Bonus: room to join
        fill = (lg.get("current_teams", 0) / max(1, lg.get("max_teams", 1)))
        if fill < 0.75:
            s += 10
        return s

    # Score each candidate once and keep alongside the doc for reuse
    scored = [(score(lg), lg) for lg in candidates]
    scored.sort(key=lambda t: t[0], reverse=True)
    ranked = scored[:limit]

    def _format(lg: dict, reason: str, is_own: bool, s: int) -> dict:
        return {
            "id": str(lg["_id"]),
            "name": lg["name"],
            "format": lg.get("format", ""),
            "scoring_format": lg.get("scoring_format", ""),
            "draft_type": lg.get("draft_type", ""),
            "current_teams": lg.get("current_teams", 0),
            "max_teams": lg.get("max_teams", 0),
            "entry_fee": lg.get("entry_fee"),
            "invite_code": lg.get("invite_code"),
            "premium": bool(lg.get("premium", False)),
            "is_own": is_own,
            "match_score": s,
            "match_reason": reason,
        }

    results = []
    for lg in own_leagues[:3]:
        results.append(_format(lg, "Continue where you left off", is_own=True, s=100))
    for s, lg in ranked:
        reason_parts = []
        if commitment != "any" and lg.get("format") in commitment_format_map.get(commitment, []):
            reason_parts.append(f"matches your {commitment} commitment")
        if scoring != "any" and lg.get("scoring_format") == scoring:
            reason_parts.append(f"{scoring.replace('_',' ')} scoring")
        if draft_style != "any" and lg.get("draft_type") == draft_style:
            reason_parts.append(f"{draft_style} draft")
        reason = ", ".join(reason_parts) or "Great open league with room to join"
        results.append(_format(lg, reason, is_own=False, s=s))

    return {
        "has_active_leagues": len(own_leagues) > 0,
        "preferences": {"commitment": commitment, "scoring": scoring, "draft_style": draft_style},
        "recommendations": results[:limit + 3],
    }


# ─── Live Scoring (NHL playoff/in-game data) ─────────────────

@api_router.get("/live-scoring")
async def get_live_scoring(request: Request):
    """Return latest live-scoring summary (today's games + poll timestamp)."""
    await get_current_user(request)
    state = await db.system_state.find_one({"_id": "live_scoring"}, {"_id": 0})
    if not state or not state.get("latest"):
        return {"date": None, "games": [], "games_processed": 0, "playoff_games": 0, "players_updated": 0, "polled_at": None}
    return state["latest"]


@api_router.post("/live-scoring/refresh")
async def refresh_live_scoring(request: Request):
    """Trigger an immediate live-scoring poll (manual refresh button).
    Rate-limited to 1 request per user per 20 seconds to avoid NHL API abuse."""
    user = await get_current_user(request)
    now = datetime.now(timezone.utc)

    # Per-user 20s cooldown
    last = await db.rate_limits.find_one({"_id": f"live_refresh:{user['_id']}"})
    if last and last.get("at"):
        last_at = last["at"]
        if last_at.tzinfo is None:
            last_at = last_at.replace(tzinfo=timezone.utc)
        elapsed = (now - last_at).total_seconds()
        if elapsed < 20:
            raise HTTPException(
                status_code=429,
                detail=f"Too many refreshes. Try again in {max(1, 20 - int(elapsed))}s.",
            )

    await db.rate_limits.update_one(
        {"_id": f"live_refresh:{user['_id']}"},
        {"$set": {"at": now}},
        upsert=True,
    )

    from live_scoring_worker import run_once
    summary = await run_once(db, sio)
    return summary


@api_router.get("/live-scoring/team/{team_id}")
async def get_team_live_scoring(team_id: str, request: Request):
    """Per-team live fantasy points + per-player playoff stat lines."""
    await get_current_user(request)
    team = await db.teams.find_one({"_id": _safe_object_id(team_id, "team_id")})
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    roster_ids = team.get("roster", [])
    if not roster_ids:
        return {"team_id": team_id, "team_name": team["name"], "live_points": 0.0, "players": []}

    players = await db.players.find(
        {"_id": {"$in": [ObjectId(pid) for pid in roster_ids]}},
        {"nhl_id": 1, "name": 1, "team": 1, "position": 1, "player_type": 1, "live_stats": 1},
    ).to_list(100)

    from live_scoring_worker import _fantasy_points_from_live

    def aggregate(p):
        is_g = p.get("player_type") == "goalie" or p.get("position") == "G"
        live = p.get("live_stats") or {}
        agg = {"goals": 0, "assists": 0, "shots": 0, "points": 0,
               "saves": 0, "goals_against": 0, "wins": 0, "games": 0,
               "fpts": 0.0, "last_game_state": None}
        for gid, ls in live.items():
            agg["games"] += 1
            agg["goals"] += ls.get("goals", 0) or 0
            agg["assists"] += ls.get("assists", 0) or 0
            agg["shots"] += ls.get("shots", 0) or 0
            agg["saves"] += ls.get("saves", 0) or 0
            agg["goals_against"] += ls.get("goals_against", 0) or 0
            agg["wins"] += ls.get("wins", 0) or 0
            agg["fpts"] += _fantasy_points_from_live(ls, is_g)
            agg["last_game_state"] = ls.get("game_state")
        agg["points"] = agg["goals"] + agg["assists"]
        agg["fpts"] = round(agg["fpts"], 2)
        return agg

    player_rows = []
    for p in players:
        agg = aggregate(p)
        player_rows.append({
            "id": str(p["_id"]),
            "nhl_id": p.get("nhl_id"),
            "name": p.get("name"),
            "team": p.get("team"),
            "position": p.get("position"),
            "is_goalie": p.get("player_type") == "goalie" or p.get("position") == "G",
            **agg,
        })
    player_rows.sort(key=lambda r: r["fpts"], reverse=True)
    total = round(sum(r["fpts"] for r in player_rows), 2)

    return {
        "team_id": team_id,
        "team_name": team["name"],
        "league_id": team.get("league_id"),
        "live_points": total,
        "players": player_rows,
    }


@api_router.get("/live-scoring/league/{league_id}")
async def get_league_live_scoring(league_id: str, request: Request):
    """League-wide leaderboard of team live points."""
    await get_current_user(request)
    _ = _safe_object_id(league_id, "league_id")
    teams = await db.teams.find({"league_id": league_id}, {"_id": 1, "name": 1, "owner_name": 1, "live_points": 1, "roster": 1}).to_list(200)
    rows = [
        {
            "team_id": str(t["_id"]),
            "team_name": t["name"],
            "owner_name": t.get("owner_name"),
            "live_points": round(t.get("live_points", 0.0) or 0.0, 2),
            "roster_count": len(t.get("roster", [])),
        }
        for t in teams
    ]
    rows.sort(key=lambda r: r["live_points"], reverse=True)
    return {"league_id": league_id, "leaderboard": rows}


@api_router.get("/live-scoring/team/{team_id}/week")
async def get_team_week_summary(team_id: str, request: Request):
    """Return weekly/daily/top-performer/rank-delta summary for a team."""
    await get_current_user(request)
    team = await db.teams.find_one({"_id": _safe_object_id(team_id, "team_id")})
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    league = await db.leagues.find_one({"_id": ObjectId(team["league_id"])}, {"name": 1, "scoring_format": 1})

    roster_ids = team.get("roster") or []
    if not roster_ids:
        return {
            "team_id": team_id,
            "team_name": team["name"],
            "league_id": team["league_id"],
            "league_name": league.get("name") if league else None,
            "daily_fpts": 0.0,
            "weekly_fpts": 0.0,
            "top_performer": None,
            "rank": None,
            "rank_delta": 0,
        }

    from live_scoring_worker import _fantasy_points_from_live
    players = await db.players.find(
        {"_id": {"$in": [ObjectId(pid) for pid in roster_ids]}},
        {"name": 1, "position": 1, "player_type": 1, "team": 1, "live_stats": 1},
    ).to_list(100)

    now = datetime.now(timezone.utc)
    day_start = now - timedelta(hours=24)
    week_start = now - timedelta(days=7)

    daily_total = 0.0
    weekly_total = 0.0
    top_today = None

    for p in players:
        is_g = p.get("player_type") == "goalie" or p.get("position") == "G"
        for _gid, ls in (p.get("live_stats") or {}).items():
            updated = ls.get("updated_at")
            if not updated:
                continue
            if isinstance(updated, str):
                try:
                    updated = datetime.fromisoformat(updated.replace("Z", "+00:00"))
                except Exception:
                    continue
            if updated.tzinfo is None:
                updated = updated.replace(tzinfo=timezone.utc)

            fpts = _fantasy_points_from_live(ls, is_g)

            if updated >= week_start:
                weekly_total += fpts
            if updated >= day_start:
                daily_total += fpts
                if not top_today or fpts > top_today["fpts"]:
                    top_today = {
                        "id": str(p["_id"]),
                        "name": p.get("name"),
                        "team": p.get("team"),
                        "position": p.get("position"),
                        "is_goalie": is_g,
                        "goals": ls.get("goals", 0) or 0,
                        "assists": ls.get("assists", 0) or 0,
                        "shots": ls.get("shots", 0) or 0,
                        "saves": ls.get("saves", 0) or 0,
                        "goals_against": ls.get("goals_against", 0) or 0,
                        "shutouts": ls.get("shutouts", 0) or 0,
                        "decision": ls.get("decision"),
                        "fpts": round(fpts, 2),
                    }

    # Rank & rank delta — compare current live_points leaderboard to yesterday's snapshot
    all_teams = await db.teams.find(
        {"league_id": team["league_id"]},
        {"_id": 1, "live_points": 1},
    ).to_list(100)
    ranked = sorted(all_teams, key=lambda t: t.get("live_points", 0.0) or 0.0, reverse=True)
    current_rank = next((i + 1 for i, t in enumerate(ranked) if str(t["_id"]) == team_id), None)

    snapshot = await db.team_rank_snapshots.find_one({
        "league_id": team["league_id"],
        "team_id": team_id,
    })
    rank_delta = 0
    if snapshot and current_rank:
        prev_rank = snapshot.get("rank")
        if prev_rank:
            rank_delta = prev_rank - current_rank  # positive = moved up

    # Opportunistically refresh the snapshot if older than 24h (lightweight)
    needs_update = not snapshot
    if snapshot and snapshot.get("updated_at"):
        last = snapshot["updated_at"]
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        needs_update = (now - last).total_seconds() > 86400
    if needs_update:
        await db.team_rank_snapshots.update_one(
            {"league_id": team["league_id"], "team_id": team_id},
            {"$set": {
                "league_id": team["league_id"],
                "team_id": team_id,
                "rank": current_rank,
                "updated_at": now,
            }},
            upsert=True,
        )

    # H2H opponent lookup for current week (if applicable)
    opponent_info = None
    scoring_format = (league or {}).get("scoring_format", "") or ""
    if "head_to_head" in scoring_format or scoring_format == "h2h":
        # Find the "current" week: first matchup with no winner/status=scheduled
        cur = await db.matchups.find_one(
            {"league_id": team["league_id"], "status": {"$in": ["scheduled", "in_progress"]}},
            sort=[("week", 1)],
        )
        week_num = cur.get("week") if cur else 1
        pair = await db.matchups.find_one({
            "league_id": team["league_id"],
            "week": week_num,
            "$or": [{"home_team_id": team_id}, {"away_team_id": team_id}],
        })
        if pair:
            opp_id = pair["away_team_id"] if pair["home_team_id"] == team_id else pair["home_team_id"]
            opp_name = pair["away_team_name"] if pair["home_team_id"] == team_id else pair["home_team_name"]
            opp_team = await db.teams.find_one({"_id": ObjectId(opp_id)}) if opp_id else None
            opp_weekly = 0.0
            if opp_team:
                for pid in (opp_team.get("roster", []) or [])[:50]:
                    try:
                        pp = await db.players.find_one({"_id": ObjectId(pid)})
                        if not pp: continue
                        is_g = pp.get("player_type") == "goalie" or pp.get("position") == "G"
                        for gid, gls in (pp.get("live_stats") or {}).items():
                            opp_weekly += _fantasy_points_from_live(gls, is_g)
                    except Exception:
                        pass
            opponent_info = {
                "opponent_team_id": opp_id,
                "opponent_team_name": opp_name,
                "opponent_weekly_fpts": round(opp_weekly, 2),
                "week": week_num,
            }

    return {
        "team_id": team_id,
        "team_name": team["name"],
        "league_id": team["league_id"],
        "league_name": league.get("name") if league else None,
        "scoring_format": scoring_format,
        "daily_fpts": round(daily_total, 2),
        "weekly_fpts": round(weekly_total, 2),
        "top_performer": top_today,
        "rank": current_rank,
        "total_teams": len(ranked),
        "rank_delta": rank_delta,
        "opponent": opponent_info,
    }


@api_router.get("/users/me/week-at-a-glance")
async def get_my_week_at_a_glance(request: Request):
    """Return week-at-a-glance summary for every team owned by the current user."""
    user = await get_current_user(request)
    teams = await db.teams.find({"owner_id": user["_id"]}, {"_id": 1, "league_id": 1, "name": 1}).to_list(50)
    if not teams:
        return {"summaries": []}
    summaries = []
    for t in teams:
        try:
            # Reuse the single-team endpoint logic by simulating the request
            res = await get_team_week_summary(str(t["_id"]), request)
            summaries.append(res)
        except HTTPException:
            continue
    return {"summaries": summaries}


# ─── Fantasy Level / Gamification ────────────────────────────

LEVEL_TITLES = [
    (1, 5, "Bench Warmer"),
    (6, 15, "Rink Regular"),
    (16, 30, "Line Captain"),
    (31, 50, "Hat Trick Hero"),
    (51, 75, "Playoff Contender"),
    (76, 999, "Stanley Cup Dynasty"),
]


def _title_for_level(level: int) -> str:
    for lo, hi, title in LEVEL_TITLES:
        if lo <= level <= hi:
            return title
    return "Rookie"


@api_router.get("/users/me/level")
async def get_my_level(request: Request):
    """Yahoo-style fantasy level based on career activity:
       trades executed, drafts completed, teams managed, accumulated live points."""
    user = await get_current_user(request)
    user_id = user["_id"]

    teams = await db.teams.find({"owner_id": user_id}).to_list(100)
    total_team_count = len(teams)
    total_wins = sum(t.get("wins", 0) or 0 for t in teams)
    total_points_for = sum(t.get("points_for", 0.0) or 0.0 for t in teams)
    total_live_points = sum(t.get("live_points", 0.0) or 0.0 for t in teams)

    # Trade + draft activity
    trades_executed = await db.trades.count_documents({
        "$or": [{"proposer_id": user_id}, {"recipient_id": user_id}],
        "status": "accepted",
    })
    drafts_completed = await db.drafts.count_documents({
        "participants": {"$in": [str(t["_id"]) for t in teams]},
        "status": "complete",
    }) if teams else 0
    waiver_claims = await db.waiver_claims.count_documents({
        "team_id": {"$in": [str(t["_id"]) for t in teams]},
    }) if teams else 0

    # XP formula — calibrated so an active user hits lvl 15-ish after a full season
    xp = int(
        total_team_count * 50
        + total_wins * 20
        + trades_executed * 25
        + drafts_completed * 40
        + waiver_claims * 5
        + (total_points_for + total_live_points) / 5
    )

    # Level curve: each level requires 100 + level*50 XP cumulatively
    level = 1
    xp_remaining = xp
    while True:
        cost = 100 + level * 50
        if xp_remaining < cost:
            break
        xp_remaining -= cost
        level += 1
    xp_to_next = (100 + level * 50) - xp_remaining

    title = _title_for_level(level)

    return {
        "user_id": str(user_id),
        "level": level,
        "title": title,
        "xp_total": xp,
        "xp_in_level": xp_remaining,
        "xp_to_next_level": xp_to_next,
        "xp_required_for_next": 100 + level * 50,
        "progress_pct": round((xp_remaining / (100 + level * 50)) * 100, 1),
        "stats": {
            "teams_managed": total_team_count,
            "total_wins": total_wins,
            "trades_accepted": trades_executed,
            "drafts_completed": drafts_completed,
            "waiver_claims": waiver_claims,
            "total_points_for": round(total_points_for + total_live_points, 2),
        },
    }


# ─── Public Profile ──────────────────────────────────────────

@api_router.get("/u/{username}")
async def get_public_profile(username: str):
    """Shareable public profile snapshot for a username. No auth required."""
    username = username.strip()
    user = await db.users.find_one(
        {"username": {"$regex": f"^{re.escape(username)}$", "$options": "i"}},
        {"password_hash": 0},
    )
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user_id = str(user["_id"])

    # All teams + league info
    teams = await db.teams.find({"owner_id": user_id}).to_list(100)
    league_ids = list({t["league_id"] for t in teams})
    leagues = await db.leagues.find(
        {"_id": {"$in": [ObjectId(lid) for lid in league_ids]}}
    ).to_list(100)
    leagues_by_id = {str(l["_id"]): l for l in leagues}

    team_cards = []
    trophies = []  # current 1st place finishes — our "championships in progress"
    championships_won = 0
    division_titles = 0
    conference_titles = 0
    consolations_won = 0
    playoff_appearances = 0
    total_wins = total_losses = total_ties = 0
    total_points_for = 0.0

    for t in teams:
        lg = leagues_by_id.get(t["league_id"]) or {}
        # Compute current league rank from points_for desc
        league_teams = await db.teams.find(
            {"league_id": t["league_id"]},
            {"_id": 1, "points_for": 1, "live_points": 1},
        ).to_list(100)
        ranked = sorted(
            league_teams,
            key=lambda x: (x.get("points_for", 0.0) or 0.0) + (x.get("live_points", 0.0) or 0.0),
            reverse=True,
        )
        rank = next((i + 1 for i, x in enumerate(ranked) if x["_id"] == t["_id"]), None)

        total_wins += t.get("wins", 0) or 0
        total_losses += t.get("losses", 0) or 0
        total_ties += t.get("ties", 0) or 0
        total_points_for += (t.get("points_for", 0.0) or 0.0) + (t.get("live_points", 0.0) or 0.0)

        champ_at = t.get("championship_won_at")
        div_at = t.get("division_winner_at")
        conf_at = t.get("conference_winner_at")
        cons_at = t.get("consolation_won_at")
        playoffs_at = t.get("playoffs_reached_at")
        if champ_at: championships_won += 1
        if div_at: division_titles += 1
        if conf_at: conference_titles += 1
        if cons_at: consolations_won += 1
        if playoffs_at: playoff_appearances += 1

        card = {
            "team_id": str(t["_id"]),
            "team_name": t["name"],
            "league_id": t["league_id"],
            "league_name": lg.get("name", "Unknown league"),
            "league_format": lg.get("format"),
            "league_sport": lg.get("sport", "nhl"),
            "wins": t.get("wins", 0),
            "losses": t.get("losses", 0),
            "ties": t.get("ties", 0),
            "points_for": round((t.get("points_for", 0.0) or 0.0) + (t.get("live_points", 0.0) or 0.0), 2),
            "rank": rank,
            "total_teams": len(league_teams),
            "live_points": round(t.get("live_points", 0.0) or 0.0, 2),
            "championship_won_at": champ_at,
            "division_winner_at": div_at,
            "conference_winner_at": conf_at,
            "consolation_won_at": cons_at,
            "playoffs_reached_at": playoffs_at,
        }
        team_cards.append(card)

        # Permanent career trophies (most visible first)
        if champ_at:
            trophies.append({
                "league_id": t["league_id"], "league_name": lg.get("name"),
                "team_name": t["name"], "label": "League Champion",
                "type": "championship", "earned_at": champ_at,
            })
        if conf_at:
            trophies.append({
                "league_id": t["league_id"], "league_name": lg.get("name"),
                "team_name": t["name"], "label": "Conference Champion",
                "type": "conference", "earned_at": conf_at,
            })
        if div_at:
            trophies.append({
                "league_id": t["league_id"], "league_name": lg.get("name"),
                "team_name": t["name"], "label": "Division Champion",
                "type": "division", "earned_at": div_at,
            })
        if cons_at:
            trophies.append({
                "league_id": t["league_id"], "league_name": lg.get("name"),
                "team_name": t["name"], "label": "Consolation Winner",
                "type": "consolation", "earned_at": cons_at,
            })

        # Current-standing trophies (non-permanent)
        if rank == 1:
            trophies.append({
                "league_id": t["league_id"],
                "league_name": lg.get("name"),
                "team_name": t["name"],
                "label": "1st Place (current)",
                "type": "lead",
            })
        elif rank and rank <= 3:
            trophies.append({
                "league_id": t["league_id"],
                "league_name": lg.get("name"),
                "team_name": t["name"],
                "label": f"Top 3 (#{rank})",
                "type": "top3",
            })

    # Lifetime top performer — highest single-game fpts across all rostered players
    lifetime_best = None
    if teams:
        from live_scoring_worker import _fantasy_points_from_live
        roster_ids = set()
        for t in teams:
            roster_ids.update(t.get("roster") or [])
        if roster_ids:
            players = await db.players.find(
                {"_id": {"$in": [ObjectId(p) for p in list(roster_ids)[:500]]}},
                {"name": 1, "team": 1, "position": 1, "player_type": 1, "live_stats": 1},
            ).to_list(500)
            for p in players:
                is_g = p.get("player_type") == "goalie" or p.get("position") == "G"
                for _gid, ls in (p.get("live_stats") or {}).items():
                    fpts = _fantasy_points_from_live(ls, is_g)
                    if not lifetime_best or fpts > lifetime_best["fpts"]:
                        lifetime_best = {
                            "id": str(p["_id"]),
                            "name": p.get("name"),
                            "team": p.get("team"),
                            "position": p.get("position"),
                            "is_goalie": is_g,
                            "goals": ls.get("goals", 0) or 0,
                            "assists": ls.get("assists", 0) or 0,
                            "shots": ls.get("shots", 0) or 0,
                            "saves": ls.get("saves", 0) or 0,
                            "goals_against": ls.get("goals_against", 0) or 0,
                            "fpts": round(fpts, 2),
                        }

    # Level data (reuse the same formula used by /users/me/level so numbers match)
    trades_executed = await db.trades.count_documents({
        "$or": [{"proposer_id": user_id}, {"recipient_id": user_id}],
        "status": "accepted",
    })
    drafts_completed = await db.drafts.count_documents({
        "participants": {"$in": [str(t["_id"]) for t in teams]},
        "status": "complete",
    }) if teams else 0
    waiver_claims = await db.waiver_claims.count_documents({
        "team_id": {"$in": [str(t["_id"]) for t in teams]},
    }) if teams else 0

    xp = int(
        len(teams) * 50
        + total_wins * 20
        + trades_executed * 25
        + drafts_completed * 40
        + waiver_claims * 5
        + total_points_for / 5
        + championships_won * 500
        + conference_titles * 250
        + division_titles * 150
        + consolations_won * 100
        + playoff_appearances * 75
    )
    level = 1
    xp_rem = xp
    while True:
        cost = 100 + level * 50
        if xp_rem < cost:
            break
        xp_rem -= cost
        level += 1

    return {
        "username": user.get("username"),
        "display_name": user.get("name") or user.get("username"),
        "member_since": user.get("created_at"),
        "level": level,
        "title": _title_for_level(level),
        "xp_in_level": xp_rem,
        "xp_required_for_next": 100 + level * 50,
        "progress_pct": round((xp_rem / (100 + level * 50)) * 100, 1),
        "stats": {
            "leagues_joined": len(teams),
            "total_wins": total_wins,
            "total_losses": total_losses,
            "total_ties": total_ties,
            "total_points": round(total_points_for, 2),
            "trades_accepted": trades_executed,
            "drafts_completed": drafts_completed,
            "waiver_claims": waiver_claims,
            "championships_won": championships_won,
            "conference_titles": conference_titles,
            "division_titles": division_titles,
            "consolations_won": consolations_won,
            "playoff_appearances": playoff_appearances,
        },
        "teams": team_cards,
        "trophies": trophies,
        "lifetime_top_performer": lifetime_best,
    }


# ─── Sport-Agnostic Player Fetch ──────────────────────────────

@api_router.get("/sports")
async def get_supported_sports():
    return [
        {"id": "nhl", "name": "NHL", "full_name": "National Hockey League", "positions": ["C", "LW", "RW", "D", "G"], "active": True, "player_count": await db.players.count_documents({"season": "2025-2026"})},
        {"id": "nfl", "name": "NFL", "full_name": "National Football League", "positions": ["QB", "RB", "WR", "TE", "K", "DEF"], "active": False, "player_count": 0},
        {"id": "nba", "name": "NBA", "full_name": "National Basketball Association", "positions": ["PG", "SG", "SF", "PF", "C"], "active": False, "player_count": 0},
        {"id": "mlb", "name": "MLB", "full_name": "Major League Baseball", "positions": ["C", "1B", "2B", "3B", "SS", "OF", "SP", "RP"], "active": False, "player_count": 0}
    ]


# Team Endpoints
@api_router.post("/teams", response_model=TeamResponse)
async def create_team(input: TeamCreate, request: Request):
    user = await get_current_user(request)
    
    league = await db.leagues.find_one({"_id": ObjectId(input.league_id)})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    
    if league["current_teams"] >= league["max_teams"]:
        raise HTTPException(status_code=400, detail="League is full")
    
    existing = await db.teams.find_one({"league_id": input.league_id, "owner_id": user["_id"]})
    if existing:
        raise HTTPException(status_code=400, detail="You already have a team in this league")
    
    team_doc = {
        "name": input.name,
        "league_id": input.league_id,
        "owner_id": user["_id"],
        "owner_name": user["name"],
        "roster": [],
        "salary_used": 0.0,
        "wins": 0,
        "losses": 0,
        "ties": 0,
        "points_for": 0.0,
        "points_against": 0.0,
        "created_at": datetime.now(timezone.utc)
    }
    result = await db.teams.insert_one(team_doc)
    
    # Update league team count
    await db.leagues.update_one({"_id": ObjectId(input.league_id)}, {"$inc": {"current_teams": 1}})
    
    return TeamResponse(
        id=str(result.inserted_id),
        name=team_doc["name"],
        league_id=team_doc["league_id"],
        owner_id=team_doc["owner_id"],
        owner_name=team_doc["owner_name"],
        salary_used=team_doc["salary_used"],
        wins=team_doc["wins"],
        losses=team_doc["losses"],
        ties=team_doc["ties"],
        points_for=team_doc["points_for"],
        points_against=team_doc["points_against"],
        created_at=team_doc["created_at"]
    )

@api_router.get("/teams", response_model=List[TeamResponse])
async def get_teams(league_id: Optional[str] = None, request: Request = None):
    query = {}
    if league_id:
        query["league_id"] = league_id
    
    teams = await db.teams.find(query).to_list(200)
    return [_team_to_response(team) for team in teams]

@api_router.get("/teams/{team_id}", response_model=TeamResponse)
async def get_team(team_id: str):
    team = await db.teams.find_one({"_id": _safe_object_id(team_id, "team_id")})
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    return _team_to_response(team)

def _team_to_response(team: dict) -> TeamResponse:
    name = team.get("name", "")
    # Derive abbreviation from team name (first letters of each significant word)
    words = [w for w in name.replace("-", " ").split() if w and w[0].isalnum()]
    if len(words) >= 2:
        abbr = (words[0][0] + words[1][0] + (words[2][0] if len(words) > 2 else "")).upper()[:3]
    else:
        abbr = name[:3].upper() if name else "TBD"
    return TeamResponse(
        id=str(team["_id"]),
        name=name,
        league_id=team["league_id"],
        owner_id=team["owner_id"],
        owner_name=team["owner_name"],
        salary_used=team.get("salary_used", 0.0),
        wins=team.get("wins", 0),
        losses=team.get("losses", 0),
        ties=team.get("ties", 0),
        points_for=team.get("points_for", 0.0),
        points_against=team.get("points_against", 0.0),
        created_at=team["created_at"],
        roster=team.get("roster", []),
        live_points=round(team.get("live_points", 0.0) or 0.0, 2),
        logo_abbr=abbr,
        championship_won_at=team.get("championship_won_at"),
        division_winner_at=team.get("division_winner_at"),
        conference_winner_at=team.get("conference_winner_at"),
        playoffs_reached_at=team.get("playoffs_reached_at"),
        consolation_won_at=team.get("consolation_won_at"),
    )

# NHL Players Endpoints
@api_router.get("/players")
async def get_players(
    search: Optional[str] = None,
    position: Optional[str] = None,
    team: Optional[str] = None,
    page: int = 1,
    limit: int = 50
):
    query = {}
    if search:
        query["$or"] = [
            {"name": {"$regex": search, "$options": "i"}},
            {"team": {"$regex": search, "$options": "i"}}
        ]
    if position:
        query["position"] = position
    if team:
        query["team"] = team
    
    skip = (page - 1) * limit
    players = await db.players.find(query).skip(skip).limit(limit).to_list(limit)
    total = await db.players.count_documents(query)
    
    # Convert ObjectId to string
    for player in players:
        player["_id"] = str(player["_id"])
    
    return {
        "players": players,
        "total": total,
        "page": page,
        "pages": (total + limit - 1) // limit
    }

@api_router.get("/players/{player_id}")
async def get_player(player_id: str):
    player = await db.players.find_one({"_id": ObjectId(player_id)})
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    player["_id"] = str(player["_id"])
    return player

# Draft Endpoints - Full Draft Engine
from draft_engine import (
    CreateDraftRequest, MakeDraftPickRequest, DraftChatRequest,
    UpdateDraftConfigRequest, get_team_for_pick, get_draft_order, build_draft_board
)

@api_router.post("/drafts")
async def create_draft(input: CreateDraftRequest, request: Request):
    user = await get_current_user(request)

    league = await db.leagues.find_one({"_id": ObjectId(input.league_id)})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")

    if league["commissioner_id"] != user["_id"]:
        raise HTTPException(status_code=403, detail="Only commissioner can create drafts")

    # Get league teams for draft order
    teams = await db.teams.find({"league_id": input.league_id}).to_list(100)
    team_abbrs = [t["name"][:4].upper() for t in teams]
    team_map = {t["name"][:4].upper(): {"id": str(t["_id"]), "name": t["name"], "owner_id": t["owner_id"]} for t in teams}

    scheduled = None
    if input.scheduled_time:
        scheduled = input.scheduled_time

    draft_doc = {
        "league_id": input.league_id,
        "league_name": league["name"],
        "draft_type": input.draft_type,
        "scheduled_time": scheduled,
        "total_rounds": input.total_rounds,
        "time_per_pick": input.time_per_pick,
        "snake_draft": input.snake_draft,
        "player_criteria": input.player_criteria,
        "missed_pick_action": input.missed_pick_action,
        "current_pick": 1,
        "status": "scheduled",
        "draft_started": False,
        "early_start": False,
        "timer_paused": False,
        "team_abbrs": team_abbrs,
        "team_map": team_map,
        "picks": [],
        "chat_messages": [],
        "created_by": user["_id"],
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    result = await db.drafts.insert_one(draft_doc)
    draft_doc["_id"] = str(result.inserted_id)
    draft_doc.pop("team_map", None)
    return draft_doc

@api_router.get("/drafts")
async def get_drafts(league_id: Optional[str] = None, request: Request = None):
    query = {}
    if league_id:
        query["league_id"] = league_id
    drafts = await db.drafts.find(query, {"team_map": 0}).sort("created_at", -1).to_list(100)
    for d in drafts:
        d["_id"] = str(d["_id"])
    return drafts

@api_router.get("/drafts/{draft_id}")
async def get_draft(draft_id: str):
    draft = await db.drafts.find_one({"_id": ObjectId(draft_id)})
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    draft["_id"] = str(draft["_id"])
    return draft

@api_router.get("/drafts/{draft_id}/board")
async def get_draft_board(draft_id: str):
    draft = await db.drafts.find_one({"_id": ObjectId(draft_id)})
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")

    board = build_draft_board(
        draft["team_abbrs"],
        draft["total_rounds"],
        draft["snake_draft"],
        draft["picks"]
    )
    return {
        "board": board,
        "current_pick": draft["current_pick"],
        "status": draft["status"],
        "team_abbrs": draft["team_abbrs"],
        "total_rounds": draft["total_rounds"],
        "snake_draft": draft["snake_draft"],
        "on_the_clock": get_team_for_pick(draft["team_abbrs"], draft["current_pick"], draft["snake_draft"]) if draft["team_abbrs"] else None
    }

@api_router.get("/drafts/{draft_id}/eligible-players")
async def get_draft_eligible_players(
    draft_id: str,
    search: Optional[str] = None,
    position: Optional[str] = None,
    page: int = 1,
    limit: int = 50
):
    draft = await db.drafts.find_one({"_id": ObjectId(draft_id)})
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")

    # Get already-drafted player IDs
    drafted_ids = [p["player_id"] for p in draft.get("picks", []) if p.get("player_id")]

    query = {}
    if drafted_ids:
        query["_id"] = {"$nin": [ObjectId(pid) for pid in drafted_ids]}

    if search:
        query["$or"] = [
            {"name": {"$regex": search, "$options": "i"}},
            {"team": {"$regex": search, "$options": "i"}}
        ]
    if position and position != "all":
        query["position"] = position

    skip = (page - 1) * limit
    players = await db.players.find(query).sort("points", -1).skip(skip).limit(limit).to_list(limit)
    total = await db.players.count_documents(query)

    result = []
    for i, p in enumerate(players):
        result.append({
            "id": str(p["_id"]),
            "name": p["name"],
            "position": p["position"],
            "nhlTeam": p.get("team", ""),
            "team_name": p.get("team_name", ""),
            "age": 0,
            "league": "NHL",
            "gp": p.get("games_played", 0),
            "g": p.get("goals", 0),
            "a": p.get("assists", 0),
            "pts": p.get("points", 0),
            "plus_minus": p.get("plus_minus", 0),
            "ranking": skip + i + 1,
            "drafted": False
        })

    return {"players": result, "total": total, "page": page, "pages": (total + limit - 1) // limit}

@api_router.post("/drafts/{draft_id}/start")
async def start_draft(draft_id: str, request: Request, early_start: bool = False):
    user = await get_current_user(request)

    draft = await db.drafts.find_one({"_id": ObjectId(draft_id)})
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")

    league = await db.leagues.find_one({"_id": ObjectId(draft["league_id"])})
    if league["commissioner_id"] != user["_id"]:
        raise HTTPException(status_code=403, detail="Only commissioner can start draft")

    if draft["status"] == "active":
        raise HTTPException(status_code=400, detail="Draft already active")

    update = {
        "$set": {
            "status": "active",
            "draft_started": True,
            "early_start": early_start,
            "current_pick": 1,
            "started_at": datetime.now(timezone.utc).isoformat()
        }
    }
    await db.drafts.update_one({"_id": ObjectId(draft_id)}, update)

    # Broadcast draft start
    await broadcast_to_room(f"draft_{draft_id}", "draft_started", {
        "draft_id": draft_id,
        "early_start": early_start,
        "team_abbrs": draft["team_abbrs"],
        "on_the_clock": draft["team_abbrs"][0] if draft["team_abbrs"] else None
    })

    # Add system chat message
    system_msg = {
        "id": f"sys-{datetime.now(timezone.utc).timestamp()}",
        "type": "pick",
        "sender": "System",
        "text": f"Draft has started! {'(No Clock)' if early_start else 'Timer is running.'}",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    await db.drafts.update_one({"_id": ObjectId(draft_id)}, {"$push": {"chat_messages": system_msg}})
    await broadcast_to_room(f"draft_{draft_id}", "draft_chat", system_msg)

    return {"message": "Draft started", "early_start": early_start}

@api_router.post("/drafts/{draft_id}/pick")
async def make_draft_pick(draft_id: str, input: MakeDraftPickRequest, request: Request):
    user = await get_current_user(request)

    draft = await db.drafts.find_one({"_id": ObjectId(draft_id)})
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")

    if draft["status"] != "active":
        raise HTTPException(status_code=400, detail="Draft is not active")

    # Validate it's the user's turn
    team = await db.teams.find_one({"league_id": draft["league_id"], "owner_id": user["_id"]})
    if not team:
        raise HTTPException(status_code=403, detail="You don't have a team in this league")

    team_abbr = team["name"][:4].upper()
    on_clock = get_team_for_pick(draft["team_abbrs"], draft["current_pick"], draft["snake_draft"])

    # Commissioner can pick for any team, or it must be the user's turn
    league = await db.leagues.find_one({"_id": ObjectId(draft["league_id"])})
    is_commissioner = league["commissioner_id"] == user["_id"]

    if team_abbr != on_clock and not is_commissioner:
        raise HTTPException(status_code=403, detail=f"Not your turn. {on_clock} is on the clock.")

    # Validate player exists and not already drafted
    player = await db.players.find_one({"_id": ObjectId(input.player_id)})
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")

    already_picked = any(p.get("player_id") == input.player_id for p in draft.get("picks", []))
    if already_picked:
        raise HTTPException(status_code=400, detail="Player already drafted")

    total_teams = len(draft["team_abbrs"])
    current_pick = draft["current_pick"]
    round_num = ((current_pick - 1) // total_teams) + 1
    pick_in_round = ((current_pick - 1) % total_teams) + 1

    pick_doc = {
        "round": round_num,
        "pick_in_round": pick_in_round,
        "overall": current_pick,
        "team": on_clock,
        "player_id": str(player["_id"]),
        "player": {
            "name": player["name"],
            "position": player["position"],
            "nhlTeam": player.get("team", ""),
            "pts": player.get("points", 0)
        },
        "picked_by": user["_id"],
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

    next_pick = current_pick + 1
    total_picks = draft["total_rounds"] * total_teams
    new_status = "completed" if next_pick > total_picks else "active"

    await db.drafts.update_one(
        {"_id": ObjectId(draft_id)},
        {
            "$push": {"picks": pick_doc},
            "$set": {"current_pick": next_pick, "status": new_status}
        }
    )

    # Broadcast pick
    await broadcast_to_room(f"draft_{draft_id}", "draft_pick", {
        **pick_doc,
        "next_pick": next_pick,
        "on_the_clock": get_team_for_pick(draft["team_abbrs"], next_pick, draft["snake_draft"]) if new_status == "active" else None,
        "draft_complete": new_status == "completed"
    })

    # System chat for the pick
    pick_msg = {
        "id": f"pick-{current_pick}",
        "type": "pick",
        "sender": "System",
        "text": f"Pick #{current_pick} (Rd {round_num}, Pick {pick_in_round}): {on_clock} selects {player['name']} ({player['position']})",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    await db.drafts.update_one({"_id": ObjectId(draft_id)}, {"$push": {"chat_messages": pick_msg}})
    await broadcast_to_room(f"draft_{draft_id}", "draft_chat", pick_msg)

    if new_status == "completed":
        complete_msg = {
            "id": f"sys-complete",
            "type": "pick",
            "sender": "System",
            "text": "Draft is complete! All picks have been made.",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        await db.drafts.update_one({"_id": ObjectId(draft_id)}, {"$push": {"chat_messages": complete_msg}})
        await broadcast_to_room(f"draft_{draft_id}", "draft_chat", complete_msg)
        await broadcast_to_room(f"draft_{draft_id}", "draft_completed", {"draft_id": draft_id})

    return pick_doc

@api_router.post("/drafts/{draft_id}/pause")
async def pause_draft(draft_id: str, request: Request):
    user = await get_current_user(request)
    draft = await db.drafts.find_one({"_id": ObjectId(draft_id)})
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")

    league = await db.leagues.find_one({"_id": ObjectId(draft["league_id"])})
    if league["commissioner_id"] != user["_id"]:
        raise HTTPException(status_code=403, detail="Only commissioner can pause draft")

    paused = not draft.get("timer_paused", False)
    await db.drafts.update_one({"_id": ObjectId(draft_id)}, {"$set": {"timer_paused": paused}})

    await broadcast_to_room(f"draft_{draft_id}", "draft_timer_toggle", {"paused": paused})
    return {"paused": paused}

@api_router.post("/drafts/{draft_id}/chat")
async def send_draft_chat(draft_id: str, input: DraftChatRequest, request: Request):
    user = await get_current_user(request)

    team = await db.teams.find_one({"league_id": (await db.drafts.find_one({"_id": ObjectId(draft_id)}))["league_id"], "owner_id": user["_id"]})
    sender = team["name"] if team else user["name"]

    msg = {
        "id": f"chat-{datetime.now(timezone.utc).timestamp()}",
        "type": "chat",
        "sender": sender,
        "text": input.text,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

    await db.drafts.update_one({"_id": ObjectId(draft_id)}, {"$push": {"chat_messages": msg}})
    await broadcast_to_room(f"draft_{draft_id}", "draft_chat", msg)
    return msg

@api_router.get("/drafts/{draft_id}/chat")
async def get_draft_chat(draft_id: str):
    draft = await db.drafts.find_one({"_id": ObjectId(draft_id)}, {"chat_messages": 1})
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    return draft.get("chat_messages", [])

@api_router.put("/drafts/{draft_id}/config")
async def update_draft_config(draft_id: str, input: UpdateDraftConfigRequest, request: Request):
    user = await get_current_user(request)
    draft = await db.drafts.find_one({"_id": ObjectId(draft_id)})
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")

    league = await db.leagues.find_one({"_id": ObjectId(draft["league_id"])})
    if league["commissioner_id"] != user["_id"]:
        raise HTTPException(status_code=403, detail="Only commissioner can update draft config")

    updates = {}
    if input.time_per_pick is not None:
        updates["time_per_pick"] = input.time_per_pick
    if input.total_rounds is not None:
        updates["total_rounds"] = input.total_rounds
    if input.snake_draft is not None:
        updates["snake_draft"] = input.snake_draft
    if input.player_criteria is not None:
        updates["player_criteria"] = input.player_criteria
    if input.missed_pick_action is not None:
        updates["missed_pick_action"] = input.missed_pick_action

    if updates:
        await db.drafts.update_one({"_id": ObjectId(draft_id)}, {"$set": updates})
        await broadcast_to_room(f"draft_{draft_id}", "draft_config_updated", updates)

    return {"updated": list(updates.keys())}

# ═══════════════════════════════════════════════════════════════
# Notifications Engine
# ═══════════════════════════════════════════════════════════════

class NotificationType(str, Enum):
    TRADE_PROPOSED = "trade_proposed"
    TRADE_ACCEPTED = "trade_accepted"
    TRADE_REJECTED = "trade_rejected"
    TRADE_VETOED = "trade_vetoed"
    WAIVER_WON = "waiver_won"
    WAIVER_LOST = "waiver_lost"
    WAIVERS_PROCESSED = "waivers_processed"
    DRAFT_STARTED = "draft_started"
    DRAFT_PICK = "draft_pick"
    DRAFT_YOUR_TURN = "draft_your_turn"
    DRAFT_COMPLETED = "draft_completed"
    WEEK_SIMULATED = "week_simulated"
    TEAM_JOINED = "team_joined"


async def create_notification(user_id: str, notif_type: str, title: str, message: str, league_id: str = None, link: str = None):
    """Create a notification and broadcast it via WebSocket."""
    doc = {
        "user_id": user_id,
        "type": notif_type,
        "title": title,
        "message": message,
        "league_id": league_id,
        "link": link,
        "read": False,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    result = await db.notifications.insert_one(doc)
    doc["_id"] = str(result.inserted_id)
    # Broadcast to user's personal room
    await sio.emit("notification", doc, room=f"user_{user_id}")
    return doc


async def notify_league(league_id: str, notif_type: str, title: str, message: str, link: str = None, exclude_user: str = None):
    """Send notification to all team owners in a league."""
    teams = await db.teams.find({"league_id": league_id}, {"owner_id": 1}).to_list(100)
    for team in teams:
        if team["owner_id"] != exclude_user:
            await create_notification(team["owner_id"], notif_type, title, message, league_id, link)


@api_router.get("/notifications")
async def get_notifications(request: Request, unread_only: bool = False, limit: int = 50):
    user = await get_current_user(request)
    query = {"user_id": user["_id"]}
    if unread_only:
        query["read"] = False
    notifs = await db.notifications.find(query).sort("created_at", -1).limit(limit).to_list(limit)
    for n in notifs:
        n["_id"] = str(n["_id"])
    return notifs


@api_router.get("/notifications/count")
async def get_unread_count(request: Request):
    user = await get_current_user(request)
    count = await db.notifications.count_documents({"user_id": user["_id"], "read": False})
    return {"count": count}


@api_router.post("/notifications/{notif_id}/read")
async def mark_notification_read(notif_id: str, request: Request):
    user = await get_current_user(request)
    await db.notifications.update_one(
        {"_id": ObjectId(notif_id), "user_id": user["_id"]},
        {"$set": {"read": True}}
    )
    return {"message": "Marked as read"}


@api_router.post("/notifications/read-all")
async def mark_all_read(request: Request):
    user = await get_current_user(request)
    result = await db.notifications.update_many(
        {"user_id": user["_id"], "read": False},
        {"$set": {"read": True}}
    )
    return {"message": f"Marked {result.modified_count} notifications as read"}


# ═══════════════════════════════════════════════════════════════
# Auction Draft Engine
# ═══════════════════════════════════════════════════════════════

class AuctionNominateRequest(BaseModel):
    player_id: str
    opening_bid: float = Field(ge=1)


class AuctionBidRequest(BaseModel):
    amount: float = Field(ge=1)


@api_router.post("/drafts/{draft_id}/auction/nominate")
async def auction_nominate(draft_id: str, input: AuctionNominateRequest, request: Request):
    """Nominate a player for auction bidding."""
    user = await get_current_user(request)
    draft = await db.drafts.find_one({"_id": ObjectId(draft_id)})
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    if draft["status"] != "active":
        raise HTTPException(status_code=400, detail="Draft is not active")
    if draft.get("draft_type") != "auction":
        raise HTTPException(status_code=400, detail="This is not an auction draft")

    # Check no active auction
    if draft.get("active_auction"):
        raise HTTPException(status_code=400, detail="An auction is already in progress")

    team = await db.teams.find_one({"league_id": draft["league_id"], "owner_id": user["_id"]})
    if not team:
        raise HTTPException(status_code=403, detail="No team in this league")

    # Check budget
    team_budget = draft.get("auction_budgets", {}).get(str(team["_id"]), draft.get("salary_cap", 200))
    if input.opening_bid > team_budget:
        raise HTTPException(status_code=400, detail=f"Insufficient budget (${team_budget} remaining)")

    player = await db.players.find_one({"_id": ObjectId(input.player_id)})
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")

    # Check player not already drafted
    drafted_ids = [p.get("player_id") for p in draft.get("picks", [])]
    if input.player_id in drafted_ids:
        raise HTTPException(status_code=400, detail="Player already drafted")

    auction = {
        "player_id": input.player_id,
        "player_name": player["name"],
        "player_position": player["position"],
        "player_team": player.get("team", ""),
        "nominator_team_id": str(team["_id"]),
        "nominator_team_name": team["name"],
        "current_bid": input.opening_bid,
        "current_bidder_team_id": str(team["_id"]),
        "current_bidder_team_name": team["name"],
        "bid_history": [{
            "team_id": str(team["_id"]),
            "team_name": team["name"],
            "amount": input.opening_bid,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }],
        "timer_seconds": 15,
        "started_at": datetime.now(timezone.utc).isoformat()
    }

    await db.drafts.update_one(
        {"_id": ObjectId(draft_id)},
        {"$set": {"active_auction": auction}}
    )

    await broadcast_to_room(f"draft_{draft_id}", "auction_nomination", auction)

    # System chat
    msg = {
        "id": f"auction-{datetime.now(timezone.utc).timestamp()}",
        "type": "pick",
        "sender": "System",
        "text": f"{team['name']} nominates {player['name']} ({player['position']}) - Opening bid: ${input.opening_bid}",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    await db.drafts.update_one({"_id": ObjectId(draft_id)}, {"$push": {"chat_messages": msg}})
    await broadcast_to_room(f"draft_{draft_id}", "draft_chat", msg)

    return auction


@api_router.post("/drafts/{draft_id}/auction/bid")
async def auction_bid(draft_id: str, input: AuctionBidRequest, request: Request):
    """Place a bid on the current auction."""
    user = await get_current_user(request)
    draft = await db.drafts.find_one({"_id": ObjectId(draft_id)})
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")

    auction = draft.get("active_auction")
    if not auction:
        raise HTTPException(status_code=400, detail="No active auction")

    team = await db.teams.find_one({"league_id": draft["league_id"], "owner_id": user["_id"]})
    if not team:
        raise HTTPException(status_code=403, detail="No team in this league")

    if input.amount <= auction["current_bid"]:
        raise HTTPException(status_code=400, detail=f"Bid must be higher than ${auction['current_bid']}")

    # Check budget
    team_id_str = str(team["_id"])
    team_budget = draft.get("auction_budgets", {}).get(team_id_str, draft.get("salary_cap", 200))
    if input.amount > team_budget:
        raise HTTPException(status_code=400, detail=f"Insufficient budget (${team_budget} remaining)")

    bid_entry = {
        "team_id": team_id_str,
        "team_name": team["name"],
        "amount": input.amount,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

    await db.drafts.update_one(
        {"_id": ObjectId(draft_id)},
        {
            "$set": {
                "active_auction.current_bid": input.amount,
                "active_auction.current_bidder_team_id": team_id_str,
                "active_auction.current_bidder_team_name": team["name"],
                "active_auction.timer_seconds": 15,
            },
            "$push": {"active_auction.bid_history": bid_entry}
        }
    )

    bid_data = {
        "team_id": team_id_str,
        "team_name": team["name"],
        "amount": input.amount,
        "player_name": auction["player_name"],
        "timer_reset": 15
    }
    await broadcast_to_room(f"draft_{draft_id}", "auction_bid", bid_data)

    return bid_data


@api_router.post("/drafts/{draft_id}/auction/resolve")
async def auction_resolve(draft_id: str, request: Request):
    """Resolve current auction - timer expired, winner gets player."""
    user = await get_current_user(request)
    draft = await db.drafts.find_one({"_id": ObjectId(draft_id)})
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")

    league = await db.leagues.find_one({"_id": ObjectId(draft["league_id"])})
    if league["commissioner_id"] != user["_id"]:
        raise HTTPException(status_code=403, detail="Only commissioner can resolve auctions")

    auction = draft.get("active_auction")
    if not auction:
        raise HTTPException(status_code=400, detail="No active auction")

    winner_team_id = auction["current_bidder_team_id"]
    winning_bid = auction["current_bid"]
    player_id = auction["player_id"]

    # Create the pick
    pick_doc = {
        "round": 0,
        "pick_in_round": len(draft.get("picks", [])) + 1,
        "overall": len(draft.get("picks", [])) + 1,
        "team": auction["current_bidder_team_name"],
        "player_id": player_id,
        "player": {
            "name": auction["player_name"],
            "position": auction["player_position"],
            "nhlTeam": auction["player_team"],
        },
        "auction_price": winning_bid,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

    # Deduct budget
    budget_key = f"auction_budgets.{winner_team_id}"
    current_budget = draft.get("auction_budgets", {}).get(winner_team_id, draft.get("salary_cap", 200))
    new_budget = current_budget - winning_bid

    await db.drafts.update_one(
        {"_id": ObjectId(draft_id)},
        {
            "$push": {"picks": pick_doc},
            "$set": {
                "active_auction": None,
                budget_key: new_budget
            }
        }
    )

    result = {
        **pick_doc,
        "winning_bid": winning_bid,
        "winner_team": auction["current_bidder_team_name"],
        "remaining_budget": new_budget
    }
    await broadcast_to_room(f"draft_{draft_id}", "auction_resolved", result)

    # System chat
    msg = {
        "id": f"resolved-{datetime.now(timezone.utc).timestamp()}",
        "type": "pick",
        "sender": "System",
        "text": f"SOLD! {auction['player_name']} goes to {auction['current_bidder_team_name']} for ${winning_bid}",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    await db.drafts.update_one({"_id": ObjectId(draft_id)}, {"$push": {"chat_messages": msg}})
    await broadcast_to_room(f"draft_{draft_id}", "draft_chat", msg)

    # Notify all league members
    await notify_league(
        draft["league_id"],
        NotificationType.DRAFT_PICK.value,
        "Auction Pick",
        f"{auction['current_bidder_team_name']} wins {auction['player_name']} for ${winning_bid}",
        link=f"/draft-room/{draft_id}"
    )

    return result


@api_router.get("/drafts/{draft_id}/auction/state")
async def get_auction_state(draft_id: str):
    """Get current auction state including active auction and budgets."""
    draft = await db.drafts.find_one({"_id": ObjectId(draft_id)})
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")

    teams = await db.teams.find({"league_id": draft["league_id"]}).to_list(100)
    budgets = []
    for t in teams:
        tid = str(t["_id"])
        budget = draft.get("auction_budgets", {}).get(tid, draft.get("salary_cap", 200))
        picks_count = sum(1 for p in draft.get("picks", []) if p.get("team") == t["name"])
        budgets.append({
            "team_id": tid,
            "team_name": t["name"],
            "budget_remaining": budget,
            "players_won": picks_count
        })

    return {
        "active_auction": draft.get("active_auction"),
        "budgets": budgets,
        "total_picks": len(draft.get("picks", [])),
        "draft_type": draft.get("draft_type"),
        "salary_cap": draft.get("salary_cap", 200)
    }


@api_router.post("/drafts/{draft_id}/auction/init-budgets")
async def init_auction_budgets(draft_id: str, request: Request):
    """Initialize auction budgets for all teams (commissioner only)."""
    user = await get_current_user(request)
    draft = await db.drafts.find_one({"_id": ObjectId(draft_id)})
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")

    league = await db.leagues.find_one({"_id": ObjectId(draft["league_id"])})
    if league["commissioner_id"] != user["_id"]:
        raise HTTPException(status_code=403, detail="Only commissioner")

    cap = league.get("salary_cap") or 200
    teams = await db.teams.find({"league_id": draft["league_id"]}).to_list(100)
    budgets = {str(t["_id"]): cap for t in teams}

    await db.drafts.update_one(
        {"_id": ObjectId(draft_id)},
        {"$set": {"auction_budgets": budgets, "salary_cap": cap}}
    )

    return {"message": f"Initialized {len(budgets)} budgets at ${cap}", "budgets": budgets}


# ═══════════════════════════════════════════════════════════════
# Salary Cap & Contracts Engine
# ═══════════════════════════════════════════════════════════════

class ContractStatus(str, Enum):
    ACTIVE = "active"
    INJURED_RESERVE = "ir"
    BUYOUT = "buyout"
    EXPIRED = "expired"


class PlayerStatus(str, Enum):
    RFA = "rfa"
    UFA = "ufa"
    SIGNED = "signed"
    ENTRY_LEVEL = "entry_level"


class ContractCreate(BaseModel):
    league_id: str
    team_id: str
    player_id: str
    aav: float = Field(ge=0, description="Average Annual Value")
    total_value: float = Field(ge=0)
    signing_bonus: float = Field(default=0, ge=0)
    years: int = Field(ge=1, le=8)
    start_year: int = Field(default=2025)
    no_trade_clause: bool = False
    no_move_clause: bool = False
    player_status: str = "signed"


class ContractUpdate(BaseModel):
    aav: Optional[float] = None
    status: Optional[str] = None
    no_trade_clause: Optional[bool] = None
    no_move_clause: Optional[bool] = None


@api_router.post("/contracts")
async def create_contract(input: ContractCreate, request: Request):
    user = await get_current_user(request)

    league = await db.leagues.find_one({"_id": ObjectId(input.league_id)})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")

    team = await db.teams.find_one({"_id": ObjectId(input.team_id)})
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    # Only team owner or commissioner can add contracts
    is_commissioner = league["commissioner_id"] == user["_id"]
    if team["owner_id"] != user["_id"] and not is_commissioner:
        raise HTTPException(status_code=403, detail="Not authorized")

    player = await db.players.find_one({"_id": ObjectId(input.player_id)})
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")

    # Check cap space
    if league.get("salary_cap_enabled"):
        cap = league.get("salary_cap", 82500000)
        current_used = await get_team_cap_used(input.team_id, input.league_id)
        if current_used + input.aav > cap:
            raise HTTPException(status_code=400, detail=f"Exceeds salary cap. Used: ${current_used:,.0f}, Cap: ${cap:,.0f}, Contract: ${input.aav:,.0f}")

    contract_doc = {
        "league_id": input.league_id,
        "team_id": input.team_id,
        "team_name": team["name"],
        "player_id": input.player_id,
        "player_name": player["name"],
        "player_position": player["position"],
        "player_nhl_team": player.get("team", ""),
        "aav": input.aav,
        "total_value": input.total_value,
        "signing_bonus": input.signing_bonus,
        "years": input.years,
        "start_year": input.start_year,
        "end_year": input.start_year + input.years - 1,
        "free_agency_year": input.start_year + input.years,
        "no_trade_clause": input.no_trade_clause,
        "no_move_clause": input.no_move_clause,
        "player_status": input.player_status,
        "status": ContractStatus.ACTIVE.value,
        "created_at": datetime.now(timezone.utc).isoformat()
    }

    result = await db.contracts.insert_one(contract_doc)
    contract_doc["_id"] = str(result.inserted_id)

    await log_activity(input.league_id, "contract_signed", f"{team['name']} signs {player['name']} to {input.years}-year, ${input.aav:,.0f} AAV contract", user["_id"])

    return contract_doc


async def get_team_cap_used(team_id: str, league_id: str):
    pipeline = [
        {"$match": {"team_id": team_id, "league_id": league_id, "status": "active"}},
        {"$group": {"_id": None, "total": {"$sum": "$aav"}}}
    ]
    result = await db.contracts.aggregate(pipeline).to_list(1)
    return result[0]["total"] if result else 0.0


@api_router.get("/contracts")
async def get_contracts(league_id: str, team_id: Optional[str] = None, status: Optional[str] = None):
    query = {"league_id": league_id}
    if team_id:
        query["team_id"] = team_id
    if status:
        query["status"] = status
    contracts = await db.contracts.find(query).sort("aav", -1).to_list(500)
    for c in contracts:
        c["_id"] = str(c["_id"])
    return contracts


@api_router.get("/contracts/{contract_id}")
async def get_contract(contract_id: str):
    contract = await db.contracts.find_one({"_id": ObjectId(contract_id)})
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")
    contract["_id"] = str(contract["_id"])
    return contract


@api_router.put("/contracts/{contract_id}")
async def update_contract(contract_id: str, input: ContractUpdate, request: Request):
    user = await get_current_user(request)
    contract = await db.contracts.find_one({"_id": ObjectId(contract_id)})
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")

    league = await db.leagues.find_one({"_id": ObjectId(contract["league_id"])})
    if league["commissioner_id"] != user["_id"]:
        raise HTTPException(status_code=403, detail="Only commissioner can edit contracts")

    updates = {}
    if input.aav is not None: updates["aav"] = input.aav
    if input.status is not None: updates["status"] = input.status
    if input.no_trade_clause is not None: updates["no_trade_clause"] = input.no_trade_clause
    if input.no_move_clause is not None: updates["no_move_clause"] = input.no_move_clause

    if updates:
        await db.contracts.update_one({"_id": ObjectId(contract_id)}, {"$set": updates})
    return {"updated": list(updates.keys())}


@api_router.get("/salary-cap/{league_id}")
async def get_salary_cap_overview(league_id: str):
    league = await db.leagues.find_one({"_id": ObjectId(league_id)})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")

    cap = league.get("salary_cap") or 82500000
    teams = await db.teams.find({"league_id": league_id}).to_list(100)

    team_caps = []
    for team in teams:
        tid = str(team["_id"])
        used = await get_team_cap_used(tid, league_id)
        contracts = await db.contracts.count_documents({"team_id": tid, "league_id": league_id, "status": "active"})

        # Count by status
        rfa = await db.contracts.count_documents({"team_id": tid, "league_id": league_id, "player_status": "rfa"})
        ufa = await db.contracts.count_documents({"team_id": tid, "league_id": league_id, "player_status": "ufa"})

        team_caps.append({
            "team_id": tid,
            "team_name": team["name"],
            "owner_name": team["owner_name"],
            "cap_used": round(used, 2),
            "cap_remaining": round(cap - used, 2),
            "cap_pct": round((used / cap) * 100, 1) if cap > 0 else 0,
            "active_contracts": contracts,
            "rfa_count": rfa,
            "ufa_count": ufa
        })

    team_caps.sort(key=lambda t: -t["cap_used"])
    return {"salary_cap": cap, "teams": team_caps}


@api_router.get("/salary-cap/{league_id}/expiring")
async def get_expiring_contracts(league_id: str, year: int = 2026):
    contracts = await db.contracts.find({
        "league_id": league_id,
        "free_agency_year": year,
        "status": "active"
    }).sort("aav", -1).to_list(200)
    for c in contracts:
        c["_id"] = str(c["_id"])
    return contracts


# ═══════════════════════════════════════════════════════════════
# League Activity Feed
# ═══════════════════════════════════════════════════════════════

async def log_activity(league_id: str, event_type: str, message: str, user_id: str = None, metadata: dict = None):
    doc = {
        "league_id": league_id,
        "event_type": event_type,
        "message": message,
        "user_id": user_id,
        "metadata": metadata or {},
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.activity_feed.insert_one(doc)
    # Broadcast to league room
    doc.pop("_id", None)
    await broadcast_to_room(f"league_{league_id}", "activity_feed", doc)


@api_router.get("/activity/{league_id}")
async def get_activity_feed(league_id: str, event_type: Optional[str] = None, limit: int = 50, page: int = 1):
    query = {"league_id": league_id}
    if event_type:
        query["event_type"] = event_type
    skip = (page - 1) * limit
    items = await db.activity_feed.find(query).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    total = await db.activity_feed.count_documents(query)
    for item in items:
        item["_id"] = str(item["_id"])
    return {"items": items, "total": total, "page": page, "pages": (total + limit - 1) // limit}


@api_router.post("/activity/{league_id}/chat")
async def post_league_chat(league_id: str, input: DraftChatRequest, request: Request):
    user = await get_current_user(request)
    team = await db.teams.find_one({"league_id": league_id, "owner_id": user["_id"]})
    sender = team["name"] if team else user["name"]

    await log_activity(league_id, "chat", input.text, user["_id"], {"sender": sender})
    return {"message": "Chat posted"}


from trade_waiver_engine import (
    TradeBlockItemCreate, TradeBlockItemRemove, TradeProposalCreate,
    TradeVote, TradeAsset as TradeAssetModel,
    WaiverClaimCreate, WaiverClaimCancel
)

# ─── Trade Block ──────────────────────────────────────────────

@api_router.post("/trade-block")
async def add_to_trade_block(input: TradeBlockItemCreate, request: Request):
    user = await get_current_user(request)

    item_doc = {
        "item_type": input.item_type,
        "looking_for": input.looking_for,
        "owner_id": user["_id"],
        "owner_name": user["name"],
        "created_at": datetime.now(timezone.utc).isoformat()
    }

    if input.item_type == "player" and input.player_id:
        player = await db.players.find_one({"_id": ObjectId(input.player_id)})
        if not player:
            raise HTTPException(status_code=404, detail="Player not found")
        item_doc["player_id"] = input.player_id
        item_doc["name"] = player["name"]
        item_doc["position"] = player["position"]
        item_doc["nhl_team"] = player.get("team", "")
        item_doc["goals"] = player.get("goals", 0)
        item_doc["assists"] = player.get("assists", 0)
        item_doc["points"] = player.get("points", 0)
        item_doc["games_played"] = player.get("games_played", 0)
        item_doc["plus_minus"] = player.get("plus_minus", 0)
    elif input.item_type == "pick":
        item_doc["name"] = f"{input.pick_year} {input.pick_round} Round"
        item_doc["position"] = "Pick"
        item_doc["pick_year"] = input.pick_year
        item_doc["pick_round"] = input.pick_round

    # Prevent duplicates
    existing = await db.trade_block.find_one({
        "owner_id": user["_id"],
        "player_id": input.player_id if input.player_id else None,
        "item_type": input.item_type
    })
    if existing:
        raise HTTPException(status_code=400, detail="Already on trade block")

    result = await db.trade_block.insert_one(item_doc)
    item_doc["_id"] = str(result.inserted_id)
    return item_doc

@api_router.get("/trade-block")
async def get_trade_block(league_id: Optional[str] = None):
    query: dict = {}
    if league_id:
        query["league_id"] = league_id
    items = await db.trade_block.find(query).sort("created_at", -1).to_list(200)
    for item in items:
        item["_id"] = str(item["_id"])
    return items

@api_router.delete("/trade-block/{item_id}")
async def remove_from_trade_block(item_id: str, request: Request):
    user = await get_current_user(request)
    item = await db.trade_block.find_one({"_id": ObjectId(item_id)})
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    if item["owner_id"] != user["_id"]:
        raise HTTPException(status_code=403, detail="Not your item")
    await db.trade_block.delete_one({"_id": ObjectId(item_id)})
    return {"message": "Removed from trade block"}

# ─── Trade Proposals ──────────────────────────────────────────

@api_router.post("/trades")
async def create_trade_proposal(input: TradeProposalCreate, request: Request):
    user = await get_current_user(request)

    league = await db.leagues.find_one({"_id": ObjectId(input.league_id)})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")

    # Get proposer's team
    proposer_team = await db.teams.find_one({"league_id": input.league_id, "owner_id": user["_id"]})
    if not proposer_team:
        raise HTTPException(status_code=403, detail="You don't have a team in this league")

    target_team = await db.teams.find_one({"_id": ObjectId(input.target_team_id)})
    if not target_team:
        raise HTTPException(status_code=404, detail="Target team not found")

    # Build asset details
    offered_details = []
    for asset in input.assets_offered:
        detail = asset.dict()
        if asset.player_id:
            player = await db.players.find_one({"_id": ObjectId(asset.player_id)})
            if player:
                detail["player_name"] = player["name"]
                detail["position"] = player["position"]
                detail["nhl_team"] = player.get("team", "")
                detail["points"] = player.get("points", 0)
                detail["goals"] = player.get("goals", 0)
                detail["assists"] = player.get("assists", 0)
        offered_details.append(detail)

    requested_details = []
    for asset in input.assets_requested:
        detail = asset.dict()
        if asset.player_id:
            player = await db.players.find_one({"_id": ObjectId(asset.player_id)})
            if player:
                detail["player_name"] = player["name"]
                detail["position"] = player["position"]
                detail["nhl_team"] = player.get("team", "")
                detail["points"] = player.get("points", 0)
                detail["goals"] = player.get("goals", 0)
                detail["assists"] = player.get("assists", 0)
        requested_details.append(detail)

    review_period_hours = 72
    has_conditions = bool(getattr(input, "conditions", None))
    trade_doc = {
        "league_id": input.league_id,
        "proposer_team_id": str(proposer_team["_id"]),
        "proposer_team_name": proposer_team["name"],
        "proposer_id": user["_id"],
        "target_team_id": input.target_team_id,
        "target_team_name": target_team["name"],
        "target_owner_id": target_team["owner_id"],
        "assets_offered": offered_details,
        "assets_requested": requested_details,
        "conditions": [c.dict() if hasattr(c, "dict") else c for c in (input.conditions or [])],
        "conditional": has_conditions,
        "message": input.message,
        "status": "pending",
        "votes": {"approve": 0, "veto": 0, "voters": []},
        "submitted_at": datetime.now(timezone.utc).isoformat(),
        "processes_at": (datetime.now(timezone.utc) + timedelta(hours=review_period_hours)).isoformat(),
        "responded_at": None,
        "processed_at": None
    }

    result = await db.trades.insert_one(trade_doc)
    trade_doc["_id"] = str(result.inserted_id)

    # WebSocket notification
    await broadcast_to_room(f"league_{input.league_id}", "trade_proposed", {
        "trade_id": str(result.inserted_id),
        "proposer": proposer_team["name"],
        "target": target_team["name"]
    })

    # Notify target team owner
    await create_notification(
        target_team["owner_id"],
        NotificationType.TRADE_PROPOSED.value,
        "New Trade Proposal",
        f"{proposer_team['name']} wants to trade with you",
        input.league_id,
        f"/transactions"
    )

    return trade_doc

@api_router.get("/trades")
async def get_trades(
    league_id: Optional[str] = None,
    status: Optional[str] = None,
    my_trades: bool = False,
    request: Request = None
):
    query = {}
    if league_id:
        query["league_id"] = league_id
    if status:
        query["status"] = status

    if my_trades:
        try:
            user = await get_current_user(request)
            query["$or"] = [
                {"proposer_id": user["_id"]},
                {"target_owner_id": user["_id"]}
            ]
        except:
            pass

    trades = await db.trades.find(query).sort("submitted_at", -1).to_list(200)
    for t in trades:
        t["_id"] = str(t["_id"])
    return trades

@api_router.get("/trades/{trade_id}")
async def get_trade(trade_id: str):
    trade = await db.trades.find_one({"_id": ObjectId(trade_id)})
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")
    trade["_id"] = str(trade["_id"])
    return trade

@api_router.post("/trades/{trade_id}/accept")
async def accept_trade(trade_id: str, request: Request):
    user = await get_current_user(request)
    trade = await db.trades.find_one({"_id": ObjectId(trade_id)})
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")
    if trade["target_owner_id"] != user["_id"]:
        raise HTTPException(status_code=403, detail="Only the target team can accept")
    if trade["status"] != "pending":
        raise HTTPException(status_code=400, detail="Trade is not pending")

    await db.trades.update_one(
        {"_id": ObjectId(trade_id)},
        {"$set": {"status": "accepted", "responded_at": datetime.now(timezone.utc).isoformat()}}
    )
    # Refresh trade after status change
    trade = await db.trades.find_one({"_id": ObjectId(trade_id)})

    # If no conditions, execute immediately. Otherwise keep pending until evaluate.
    executed = None
    if not trade.get("conditions"):
        try:
            executed = await _execute_trade(trade)
        except Exception as e:
            logger.exception("Trade auto-execute failed: %s", e)

    await broadcast_to_room(f"league_{trade['league_id']}", "trade_accepted", {
        "trade_id": trade_id,
        "proposer": trade["proposer_team_name"],
        "target": trade["target_team_name"]
    })

    # Notify proposer
    await create_notification(
        trade["proposer_id"],
        NotificationType.TRADE_ACCEPTED.value,
        "Trade Accepted!",
        f"{trade['target_team_name']} accepted your trade proposal",
        trade["league_id"],
        f"/transactions"
    )

    return {"message": "Trade accepted", "status": "accepted", "executed": bool(executed and executed.get("executed"))}
    # Note: activity logged via broadcast

@api_router.post("/trades/{trade_id}/reject")
async def reject_trade(trade_id: str, request: Request):
    user = await get_current_user(request)
    trade = await db.trades.find_one({"_id": ObjectId(trade_id)})
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")
    if trade["target_owner_id"] != user["_id"]:
        raise HTTPException(status_code=403, detail="Only the target team can reject")
    if trade["status"] != "pending":
        raise HTTPException(status_code=400, detail="Trade is not pending")

    await db.trades.update_one(
        {"_id": ObjectId(trade_id)},
        {"$set": {"status": "rejected", "responded_at": datetime.now(timezone.utc).isoformat()}}
    )

    return {"message": "Trade rejected", "status": "rejected"}

@api_router.post("/trades/{trade_id}/withdraw")
async def withdraw_trade(trade_id: str, request: Request):
    user = await get_current_user(request)
    trade = await db.trades.find_one({"_id": ObjectId(trade_id)})
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")
    if trade["proposer_id"] != user["_id"]:
        raise HTTPException(status_code=403, detail="Only the proposer can withdraw")
    if trade["status"] != "pending":
        raise HTTPException(status_code=400, detail="Trade is not pending")

    await db.trades.update_one(
        {"_id": ObjectId(trade_id)},
        {"$set": {"status": "withdrawn", "responded_at": datetime.now(timezone.utc).isoformat()}}
    )

    return {"message": "Trade withdrawn", "status": "withdrawn"}


# ─── Trade Execution + Conditions ─────────────────────────────

def _metric_value_for_player(player: dict, metric: str) -> float:
    if metric == "nhl_points":
        return float(player.get("points", 0) or 0)
    if metric == "nhl_goals":
        return float(player.get("goals", 0) or 0)
    if metric == "nhl_assists":
        return float(player.get("assists", 0) or 0)
    if metric == "nhl_wins":
        return float(player.get("wins", 0) or 0)
    if metric == "games_played":
        return float(player.get("games_played", 0) or 0)
    if metric == "fantasy_points":
        return float(player.get("fantasy_points", 0) or 0)
    if metric == "live_fantasy_points":
        live = player.get("live_stats") or {}
        total = 0.0
        for _, ls in live.items():
            total += (ls.get("goals", 0) or 0) * 3 + (ls.get("assists", 0) or 0) * 2
        return total
    return 0.0


async def _evaluate_conditions(trade: dict) -> dict:
    results = []
    all_met = True
    league_id = trade.get("league_id")
    for cond in (trade.get("conditions") or []):
        subject_type = cond.get("subject_type", "player")
        subject = cond.get("subject", "offered")
        side_assets = trade.get(f"assets_{subject}", []) or []
        metric = cond.get("metric")
        operator = (cond.get("operator") or "gte").lower()
        threshold = float(cond.get("threshold", 0) or 0)
        actual = 0.0

        if subject_type == "team":
            # Resolve team: explicit team_id OR the team on the 'subject' side of the trade
            team_id = cond.get("team_id")
            if not team_id:
                team_id = trade["proposer_team_id"] if subject == "offered" else trade["target_team_id"]
            try:
                team = await db.teams.find_one({"_id": ObjectId(team_id)})
            except Exception:
                team = None
            if team:
                if metric == "team_wins":
                    actual = float(team.get("wins", 0) or 0)
                elif metric == "team_losses":
                    actual = float(team.get("losses", 0) or 0)
                elif metric == "team_points_for":
                    actual = float(team.get("points_for", 0) or 0)
                elif metric == "team_rank":
                    # Lower = better; compute by points_for in league
                    peers = await db.teams.find({"league_id": league_id}).to_list(100)
                    peers.sort(key=lambda t: -(t.get("points_for", 0) or 0))
                    rank = next((i + 1 for i, t in enumerate(peers) if str(t["_id"]) == team_id), None)
                    actual = float(rank) if rank else 999.0
                elif metric == "made_playoffs":
                    actual = 1.0 if team.get("playoffs_reached_at") else 0.0
                elif metric == "won_division":
                    actual = 1.0 if team.get("division_winner_at") else 0.0
                elif metric == "won_conference":
                    actual = 1.0 if team.get("conference_winner_at") else 0.0
                elif metric == "won_championship":
                    actual = 1.0 if team.get("championship_won_at") else 0.0
                elif metric == "won_consolation":
                    actual = 1.0 if team.get("consolation_won_at") else 0.0
        else:
            # Player-level
            specific_pid = cond.get("player_id")
            candidate_pids = []
            for a in side_assets:
                if a.get("asset_type") != "player":
                    continue
                if specific_pid and a.get("player_id") != specific_pid:
                    continue
                if a.get("player_id"):
                    candidate_pids.append(a["player_id"])
            best = 0.0
            for pid in candidate_pids:
                try:
                    player = await db.players.find_one({"_id": ObjectId(pid)})
                    if player:
                        val = _metric_value_for_player(player, metric)
                        if val > best:
                            best = val
                except Exception:
                    pass
            actual = best

        if operator == "gte":
            met = actual >= threshold
        elif operator == "lte":
            met = actual <= threshold
        elif operator == "eq":
            met = abs(actual - threshold) < 1e-6
        else:
            met = False
        results.append({"condition": cond, "actual_value": actual, "met": met})
        if not met:
            all_met = False
    return {"all_met": all_met, "results": results}


async def _execute_trade(trade: dict) -> dict:
    if trade.get("status") == "executed":
        return {"already_executed": True}
    league_id = trade["league_id"]
    proposer_tid = trade["proposer_team_id"]
    target_tid = trade["target_team_id"]
    proposer = await db.teams.find_one({"_id": ObjectId(proposer_tid)})
    target = await db.teams.find_one({"_id": ObjectId(target_tid)})
    if not proposer or not target:
        raise HTTPException(status_code=404, detail="Trade team(s) not found")
    proposer_roster = list(proposer.get("roster", []) or [])
    target_roster = list(target.get("roster", []) or [])
    moves = {"players_out": [], "picks_out": [], "players_in": [], "picks_in": [], "retained": []}

    for a in trade.get("assets_offered", []):
        if a.get("asset_type") == "player" and a.get("player_id"):
            pid = a["player_id"]
            if pid in proposer_roster:
                proposer_roster.remove(pid)
            if pid not in target_roster:
                target_roster.append(pid)
            moves["players_out"].append({"player_id": pid, "from": proposer_tid, "to": target_tid})
            if a.get("salary_retained_pct", 0) > 0:
                moves["retained"].append({"player_id": pid, "retainer_team_id": proposer_tid, "pct": a["salary_retained_pct"]})
        elif a.get("asset_type") == "pick":
            query = {"league_id": league_id, "current_team_id": proposer_tid}
            if a.get("pick_id"):
                query["_id"] = ObjectId(a["pick_id"])
            else:
                if a.get("pick_year"): query["year"] = int(a["pick_year"])
                if a.get("pick_round"):
                    try: query["round"] = int(str(a["pick_round"]).replace("R", "").strip())
                    except Exception: pass
            p = await db.draft_picks.find_one(query)
            if p:
                await db.draft_picks.update_one(
                    {"_id": p["_id"]},
                    {
                        "$set": {"current_team_id": target_tid, "current_team_name": target.get("name")},
                        "$push": {"trade_history": {
                            "trade_id": str(trade["_id"]),
                            "from_team_id": proposer_tid,
                            "from_team_name": proposer.get("name"),
                            "to_team_id": target_tid,
                            "to_team_name": target.get("name"),
                            "traded_at": datetime.now(timezone.utc),
                        }},
                    }
                )
                moves["picks_out"].append({"pick_id": str(p["_id"]), "year": p["year"], "round": p["round"],
                                            "from": proposer_tid, "to": target_tid})

    for a in trade.get("assets_requested", []):
        if a.get("asset_type") == "player" and a.get("player_id"):
            pid = a["player_id"]
            if pid in target_roster:
                target_roster.remove(pid)
            if pid not in proposer_roster:
                proposer_roster.append(pid)
            moves["players_in"].append({"player_id": pid, "from": target_tid, "to": proposer_tid})
            if a.get("salary_retained_pct", 0) > 0:
                moves["retained"].append({"player_id": pid, "retainer_team_id": target_tid, "pct": a["salary_retained_pct"]})
        elif a.get("asset_type") == "pick":
            query = {"league_id": league_id, "current_team_id": target_tid}
            if a.get("pick_id"):
                query["_id"] = ObjectId(a["pick_id"])
            else:
                if a.get("pick_year"): query["year"] = int(a["pick_year"])
                if a.get("pick_round"):
                    try: query["round"] = int(str(a["pick_round"]).replace("R", "").strip())
                    except Exception: pass
            p = await db.draft_picks.find_one(query)
            if p:
                await db.draft_picks.update_one(
                    {"_id": p["_id"]},
                    {
                        "$set": {"current_team_id": proposer_tid, "current_team_name": proposer.get("name")},
                        "$push": {"trade_history": {
                            "trade_id": str(trade["_id"]),
                            "from_team_id": target_tid,
                            "from_team_name": target.get("name"),
                            "to_team_id": proposer_tid,
                            "to_team_name": proposer.get("name"),
                            "traded_at": datetime.now(timezone.utc),
                        }},
                    }
                )
                moves["picks_in"].append({"pick_id": str(p["_id"]), "year": p["year"], "round": p["round"],
                                           "from": target_tid, "to": proposer_tid})

    await db.teams.update_one({"_id": proposer["_id"]}, {"$set": {"roster": proposer_roster}})
    await db.teams.update_one({"_id": target["_id"]}, {"$set": {"roster": target_roster}})

    for r in moves["retained"]:
        await db.salary_retentions.update_one(
            {"league_id": league_id, "player_id": r["player_id"], "retainer_team_id": r["retainer_team_id"]},
            {"$set": {**r, "league_id": league_id, "trade_id": str(trade["_id"]),
                      "created_at": datetime.now(timezone.utc)}},
            upsert=True,
        )

    await db.trades.update_one(
        {"_id": trade["_id"]},
        {"$set": {
            "status": "executed",
            "processed_at": datetime.now(timezone.utc).isoformat(),
            "execution_moves": moves,
        }}
    )

    try:
        await db.activity_feed.insert_one({
            "league_id": league_id,
            "event_type": "trade_executed",
            "description": f"Trade executed: {trade['proposer_team_name']} ↔ {trade['target_team_name']}",
            "message": f"Trade executed: {trade['proposer_team_name']} ↔ {trade['target_team_name']}",
            "created_at": datetime.now(timezone.utc),
        })
    except Exception:
        pass
    return {"executed": True, "moves": moves}


@api_router.post("/trades/{trade_id}/execute")
async def execute_trade_endpoint(trade_id: str, request: Request):
    user = await get_current_user(request)
    trade = await db.trades.find_one({"_id": ObjectId(trade_id)})
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")
    if trade.get("status") not in ("accepted", "pending", "conditional"):
        raise HTTPException(status_code=400, detail=f"Trade status is {trade.get('status')}")
    league = await db.leagues.find_one({"_id": ObjectId(trade["league_id"])})
    is_participant = user["_id"] in (trade.get("proposer_id"), trade.get("target_owner_id"))
    is_comm = league and (league["commissioner_id"] == user["_id"] or user["_id"] in (league.get("co_commissioners") or []))
    if not (is_participant or is_comm):
        raise HTTPException(status_code=403, detail="Not authorized to execute this trade")
    if trade.get("conditions"):
        check = await _evaluate_conditions(trade)
        if not check["all_met"]:
            return {"executed": False, "reason": "conditions_not_met", **check}
    return await _execute_trade(trade)


@api_router.post("/trades/{trade_id}/evaluate-conditions")
async def evaluate_trade_conditions_endpoint(trade_id: str):
    trade = await db.trades.find_one({"_id": ObjectId(trade_id)})
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")
    return await _evaluate_conditions(trade)


# ─── Draft Picks → moved to routes/drafts.py ──────────────────
# ─── Team Awards (set_team_awards) → moved to routes/awards.py ────


@api_router.post("/trades/{trade_id}/vote")
async def vote_on_trade(trade_id: str, input: TradeVote, request: Request):
    user = await get_current_user(request)
    trade = await db.trades.find_one({"_id": ObjectId(trade_id)})
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")
    if trade["status"] not in ["pending", "accepted"]:
        raise HTTPException(status_code=400, detail="Trade is not open for voting")

    # Check if already voted
    voters = trade.get("votes", {}).get("voters", [])
    if user["_id"] in voters:
        raise HTTPException(status_code=400, detail="Already voted on this trade")

    vote_field = "votes.approve" if input.vote == "approve" else "votes.veto"
    await db.trades.update_one(
        {"_id": ObjectId(trade_id)},
        {
            "$inc": {vote_field: 1},
            "$push": {"votes.voters": user["_id"]}
        }
    )

    # Check veto threshold (>50% of league managers)
    league = await db.leagues.find_one({"_id": ObjectId(trade["league_id"])})
    total_teams = league.get("current_teams", 0)
    veto_threshold = total_teams // 2

    updated_trade = await db.trades.find_one({"_id": ObjectId(trade_id)})
    if updated_trade["votes"]["veto"] > veto_threshold:
        await db.trades.update_one(
            {"_id": ObjectId(trade_id)},
            {"$set": {"status": "vetoed", "processed_at": datetime.now(timezone.utc).isoformat()}}
        )
        await broadcast_to_room(f"league_{trade['league_id']}", "trade_vetoed", {"trade_id": trade_id})
        return {"message": "Trade vetoed by league vote", "status": "vetoed"}

    return {"message": f"Vote recorded: {input.vote}", "votes": updated_trade["votes"]}

# ═══════════════════════════════════════════════════════════════
# Waiver Wire Endpoints
# ═══════════════════════════════════════════════════════════════

@api_router.get("/waivers/available")
async def get_waiver_players(
    league_id: Optional[str] = None,
    search: Optional[str] = None,
    position: Optional[str] = None,
    page: int = 1,
    limit: int = 50
):
    """Get players available on waivers (not on any team roster)."""
    # For now, return players from the database sorted by points
    query = {}
    if search:
        query["$or"] = [
            {"name": {"$regex": search, "$options": "i"}},
            {"team": {"$regex": search, "$options": "i"}}
        ]
    if position and position != "all":
        query["position"] = position

    skip = (page - 1) * limit
    players = await db.players.find(query).sort("points", -1).skip(skip).limit(limit).to_list(limit)
    total = await db.players.count_documents(query)

    result = []
    for p in players:
        # Check for active waiver claims
        active_claim = await db.waiver_claims.find_one({
            "player_id": str(p["_id"]),
            "status": "pending"
        })
        result.append({
            "id": str(p["_id"]),
            "name": p["name"],
            "position": p["position"],
            "team": p.get("team", ""),
            "team_name": p.get("team_name", ""),
            "points": p.get("points", 0),
            "goals": p.get("goals", 0),
            "assists": p.get("assists", 0),
            "games_played": p.get("games_played", 0),
            "has_active_claim": active_claim is not None
        })

    return {"players": result, "total": total, "page": page, "pages": (total + limit - 1) // limit}

@api_router.post("/waivers/claim")
async def place_waiver_claim(input: WaiverClaimCreate, request: Request):
    user = await get_current_user(request)

    # Get user's team in this league
    team = await db.teams.find_one({"league_id": input.league_id, "owner_id": user["_id"]})
    if not team:
        raise HTTPException(status_code=403, detail="You don't have a team in this league")

    # Validate player exists
    player = await db.players.find_one({"_id": ObjectId(input.player_id)})
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")

    # Check FAAB budget
    team_budget = await db.waiver_budgets.find_one({
        "team_id": str(team["_id"]),
        "league_id": input.league_id
    })
    if not team_budget:
        # Initialize budget ($100 default)
        team_budget = {
            "team_id": str(team["_id"]),
            "league_id": input.league_id,
            "total_budget": 100.0,
            "spent": 0.0,
            "remaining": 100.0
        }
        await db.waiver_budgets.insert_one(team_budget)

    if input.bid_amount > team_budget["remaining"]:
        raise HTTPException(status_code=400, detail=f"Insufficient FAAB budget. Remaining: ${team_budget['remaining']}")

    # Check for duplicate claim
    existing = await db.waiver_claims.find_one({
        "team_id": str(team["_id"]),
        "player_id": input.player_id,
        "status": "pending"
    })
    if existing:
        raise HTTPException(status_code=400, detail="You already have a pending claim for this player")

    claim_doc = {
        "league_id": input.league_id,
        "team_id": str(team["_id"]),
        "team_name": team["name"],
        "owner_id": user["_id"],
        "player_id": input.player_id,
        "player_name": player["name"],
        "player_position": player["position"],
        "player_team": player.get("team", ""),
        "bid_amount": input.bid_amount,
        "drop_player_id": input.drop_player_id,
        "drop_player_name": None,
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "processes_at": (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
    }

    if input.drop_player_id:
        drop_player = await db.players.find_one({"_id": ObjectId(input.drop_player_id)})
        if drop_player:
            claim_doc["drop_player_name"] = drop_player["name"]

    result = await db.waiver_claims.insert_one(claim_doc)
    claim_doc["_id"] = str(result.inserted_id)
    return claim_doc

@api_router.get("/waivers/claims")
async def get_waiver_claims(
    league_id: Optional[str] = None,
    my_claims: bool = False,
    status: Optional[str] = None,
    request: Request = None
):
    query = {}
    if league_id:
        query["league_id"] = league_id
    if status:
        query["status"] = status

    if my_claims:
        try:
            user = await get_current_user(request)
            query["owner_id"] = user["_id"]
        except:
            pass

    claims = await db.waiver_claims.find(query).sort("created_at", -1).to_list(200)
    for c in claims:
        c["_id"] = str(c["_id"])
    return claims

@api_router.delete("/waivers/claims/{claim_id}")
async def cancel_waiver_claim(claim_id: str, request: Request):
    user = await get_current_user(request)
    claim = await db.waiver_claims.find_one({"_id": ObjectId(claim_id)})
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")
    if claim["owner_id"] != user["_id"]:
        raise HTTPException(status_code=403, detail="Not your claim")
    if claim["status"] != "pending":
        raise HTTPException(status_code=400, detail="Claim is not pending")

    await db.waiver_claims.update_one(
        {"_id": ObjectId(claim_id)},
        {"$set": {"status": "cancelled"}}
    )
    return {"message": "Claim cancelled"}

@api_router.get("/waivers/budget")
async def get_waiver_budget(league_id: str, request: Request = None):
    user = await get_current_user(request)
    team = await db.teams.find_one({"league_id": league_id, "owner_id": user["_id"]})
    if not team:
        raise HTTPException(status_code=403, detail="No team in this league")

    budget = await db.waiver_budgets.find_one({
        "team_id": str(team["_id"]),
        "league_id": league_id
    })
    if not budget:
        budget = {
            "team_id": str(team["_id"]),
            "league_id": league_id,
            "total_budget": 100.0,
            "spent": 0.0,
            "remaining": 100.0
        }
        await db.waiver_budgets.insert_one(budget)

    budget["_id"] = str(budget["_id"]) if "_id" in budget else None
    return budget

@api_router.get("/waivers/order")
async def get_waiver_order(league_id: str):
    """Get waiver priority order (inverse of standings)."""
    teams = await db.teams.find({"league_id": league_id}).to_list(100)
    # Sort by worst record first (inverse standings = waiver priority)
    teams.sort(key=lambda t: (t.get("wins", 0), t.get("points_for", 0)))

    order = []
    for i, team in enumerate(teams):
        order.append({
            "rank": i + 1,
            "team_id": str(team["_id"]),
            "team_name": team["name"],
            "owner_name": team["owner_name"],
            "wins": team.get("wins", 0),
            "losses": team.get("losses", 0)
        })
    return order

@api_router.get("/waivers/history")
async def get_waiver_history(league_id: Optional[str] = None, limit: int = 50):
    query = {"status": {"$in": ["won", "lost", "processed"]}}
    if league_id:
        query["league_id"] = league_id
    claims = await db.waiver_claims.find(query).sort("created_at", -1).to_list(limit)
    for c in claims:
        c["_id"] = str(c["_id"])
    return claims

@api_router.post("/waivers/process")
async def process_waivers(league_id: str, request: Request):
    """Commissioner-only: process all pending waiver claims for a league."""
    user = await get_current_user(request)
    league = await db.leagues.find_one({"_id": ObjectId(league_id)})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    if league["commissioner_id"] != user["_id"]:
        raise HTTPException(status_code=403, detail="Only commissioner can process waivers")

    # Get all pending claims grouped by player
    pending = await db.waiver_claims.find({
        "league_id": league_id,
        "status": "pending"
    }).to_list(1000)

    if not pending:
        return {"message": "No pending claims to process", "processed": 0}

    # Group by player
    player_claims = {}
    for claim in pending:
        pid = claim["player_id"]
        if pid not in player_claims:
            player_claims[pid] = []
        player_claims[pid].append(claim)

    processed_count = 0
    results = []

    for player_id, claims in player_claims.items():
        # Sort by bid amount (highest wins), then by claim time (earlier wins ties)
        claims.sort(key=lambda c: (-c["bid_amount"], c["created_at"]))

        winner = claims[0]
        losers = claims[1:]

        # Mark winner
        await db.waiver_claims.update_one(
            {"_id": winner["_id"]},
            {"$set": {"status": "won", "processed_at": datetime.now(timezone.utc).isoformat()}}
        )

        # Deduct FAAB from winner
        await db.waiver_budgets.update_one(
            {"team_id": winner["team_id"], "league_id": league_id},
            {"$inc": {"spent": winner["bid_amount"], "remaining": -winner["bid_amount"]}}
        )

        # Mark losers
        for loser in losers:
            await db.waiver_claims.update_one(
                {"_id": loser["_id"]},
                {"$set": {"status": "lost", "processed_at": datetime.now(timezone.utc).isoformat()}}
            )

        results.append({
            "player": winner["player_name"],
            "winner": winner["team_name"],
            "bid": winner["bid_amount"]
        })
        processed_count += 1

    await broadcast_to_room(f"league_{league_id}", "waivers_processed", {"results": results})

    return {"message": f"Processed {processed_count} waiver claims", "processed": processed_count, "results": results}

# ═══════════════════════════════════════════════════════════════
# Roster Management Endpoints
# ═══════════════════════════════════════════════════════════════

@api_router.get("/roster/{team_id}")
async def get_roster(team_id: str):
    team = await db.teams.find_one({"_id": ObjectId(team_id)})
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    roster_players = team.get("roster", [])
    players = []
    for pid in roster_players:
        player = await db.players.find_one({"_id": ObjectId(pid)})
        if player:
            # Calculate fantasy points
            config = await db.scoring_configs.find_one({"league_id": team["league_id"]})
            fpts = calculate_fantasy_points(player, config)
            players.append({
                "player_id": str(player["_id"]),
                "name": player["name"],
                "position": player["position"],
                "nhl_team": player.get("team", ""),
                "team_name": player.get("team_name", ""),
                "games_played": player.get("games_played", 0),
                "goals": player.get("goals", 0),
                "assists": player.get("assists", 0),
                "points": player.get("points", 0),
                "plus_minus": player.get("plus_minus", 0),
                "penalty_minutes": player.get("penalty_minutes", 0),
                "power_play_goals": player.get("power_play_goals", 0),
                "power_play_points": player.get("power_play_points", 0),
                "shots": player.get("shots", 0),
                "wins": player.get("wins", 0),
                "save_pct": player.get("save_pct", 0),
                "goals_against_avg": player.get("goals_against_avg", 0),
                "shutouts": player.get("shutouts", 0),
                "fantasy_points": fpts
            })

    players.sort(key=lambda p: -(p.get("fantasy_points") or 0))
    return {"team_id": team_id, "team_name": team["name"], "players": players}


@api_router.get("/roster/{team_id}/detail")
async def get_roster_detail(team_id: str):
    """Rich roster payload for the Lovable Team page. Includes per-player
    season + live stats, category breakdown, synthesized contracts/eligibility
    (fantasy metadata not yet modelled in DB), and roster section assignment."""
    team = await db.teams.find_one({"_id": _safe_object_id(team_id, "team_id")})
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    league = await db.leagues.find_one({"_id": ObjectId(team["league_id"])})
    config = await db.scoring_configs.find_one({"league_id": team["league_id"]})

    roster_ids = team.get("roster", []) or []
    if not roster_ids:
        return {"team_id": team_id, "team_name": team["name"], "league_id": team["league_id"],
                "league_name": (league or {}).get("name"), "players": []}

    players_raw = await db.players.find(
        {"_id": {"$in": [ObjectId(pid) for pid in roster_ids]}},
    ).to_list(100)

    from live_scoring_worker import _fantasy_points_from_live

    # Count forwards/defensemen/goalies for roster section bucketing
    starting_slots = [
        ("C1", "C", ["C"]), ("C2", "C", ["C"]),
        ("LW1", "LW", ["LW"]), ("RW1", "RW", ["RW"]),
        ("W1", "W", ["LW", "RW"]),
        ("D1", "D", ["D"]), ("D2", "D", ["D"]),
        ("UTIL1", "UTIL", ["C", "LW", "RW", "D"]),
        ("G1", "G", ["G"]), ("G2", "G", ["G"]),
    ]

    # Map live stats
    def live_agg(p):
        is_g = p.get("player_type") == "goalie" or p.get("position") == "G"
        live = p.get("live_stats") or {}
        goals = assists = shots = saves = ga = wins = 0
        fpts_live = 0.0
        for gid, ls in live.items():
            goals += ls.get("goals", 0) or 0
            assists += ls.get("assists", 0) or 0
            shots += ls.get("shots", 0) or 0
            saves += ls.get("saves", 0) or 0
            ga += ls.get("goals_against", 0) or 0
            wins += ls.get("wins", 0) or 0
            fpts_live += _fantasy_points_from_live(ls, is_g)
        return {
            "goals": goals, "assists": assists, "shots": shots,
            "saves": saves, "goals_against": ga, "wins": wins,
            "fpts": round(fpts_live, 2),
        }

    # Build normalized players + assign roster slots (best players to starting slots)
    enriched = []
    for p in players_raw:
        pos = p.get("position", "F")
        is_g = p.get("player_type") == "goalie" or pos == "G"
        live = live_agg(p)
        fpts_season = calculate_fantasy_points(p, config)
        games = p.get("games_played", 0) or 0
        points = p.get("points", 0) or 0
        # Synthesize dynasty value from points + age
        age = 27  # age not in DB; default; could be enriched later
        dyn_val = int(max(1000, points * 80 + (fpts_season * 10)))
        trend = "up" if live["fpts"] > 0 else ("down" if games > 0 and points < 10 else "stable")

        # Synthesize eligible positions (primary + one secondary for forwards)
        eligible = [pos] if pos in ("C", "LW", "RW", "D", "G") else ["F"]

        # Contract salary (synthesized realistic NHL tiers based on points G+A)
        # Elite (>=100) → $11-13M, Star (60-99) → $6-10M, Mid (30-59) → $3-6M, Role (10-29) → $1.5-3M
        if is_g:
            # Goalies tiered by fantasy points
            if fpts_season >= 300:   salary = 9_500_000
            elif fpts_season >= 180: salary = 6_000_000
            elif fpts_season >= 100: salary = 3_500_000
            else:                     salary = 1_200_000
        elif points >= 100:
            salary = 11_000_000 + min(2_500_000, (points - 100) * 70_000)
        elif points >= 60:
            salary = 6_000_000 + (points - 60) * 100_000
        elif points >= 30:
            salary = 3_000_000 + (points - 30) * 90_000
        elif points >= 10:
            salary = 1_500_000 + (points - 10) * 75_000
        else:
            salary = 950_000 + points * 40_000
        salary = int(min(13_500_000, max(775_000, salary)))
        years_remaining = 1 + (int(p.get("nhl_id", 0)) % 6)
        contract_type = "ELC" if age < 23 and salary < 1200000 else ("RFA" if years_remaining == 1 and age < 27 else ("UFA" if years_remaining == 1 else "Signed"))

        stats_by_period = {
            "season": round(fpts_season, 1),
            "1d": round(live["fpts"], 1),
            "7d": round(live["fpts"], 1),
            "14d": round(live["fpts"] * 1.3, 1),
            "30d": round(fpts_season * 0.3, 1),
            "60d": round(fpts_season * 0.55, 1),
            "100d": round(fpts_season * 0.85, 1),
        }

        category_breakdown = {
            "G": p.get("goals", 0) or 0,
            "A": p.get("assists", 0) or 0,
            "PPP": p.get("power_play_points", 0) or 0,
            "SHP": p.get("short_handed_points", 0) or 0,
            "SOG": p.get("shots", 0) or 0,
            "HIT": p.get("hits", 0) or 0,
            "BLK": p.get("blocked_shots", 0) or 0,
            "PIM": p.get("penalty_minutes", 0) or 0,
            "+/-": p.get("plus_minus", 0) or 0,
            "FOW": 0, "FOL": 0,
        }

        enriched.append({
            "id": str(p["_id"]),
            "player_id": str(p["_id"]),
            "nhl_id": p.get("nhl_id"),
            "name": p.get("name"),
            "team": p.get("team"),
            "position": pos,
            "eligiblePositions": eligible,
            "is_goalie": is_g,
            "age": age,
            "dynastyValue": dyn_val,
            "trend": trend,
            "contract": {
                "salary": salary,
                "yearsRemaining": years_remaining,
                "type": contract_type,
            },
            "games_played": games,
            "points": points,
            "fantasy_points": round(fpts_season, 2),
            "live": live,
            "statsByPeriod": stats_by_period,
            "categoryBreakdown": category_breakdown,
            "matchupGames": live.get("games", 0) if isinstance(live.get("games"), int) else 0,
        })

    # Rank by season fantasy points; assign roster sections
    enriched.sort(key=lambda x: -x["fantasy_points"])

    def fill_slot(label, eligible_positions, pool, assigned):
        for cand in pool:
            if cand["id"] in assigned:
                continue
            if cand["position"] in eligible_positions or any(ep in eligible_positions for ep in cand.get("eligiblePositions", [])):
                assigned.add(cand["id"])
                cand["rosterSlotId"] = label[0]
                cand["rosterSection"] = "starting"
                return cand
        return None

    assigned_ids = set()
    for slot_id, label, elig in starting_slots:
        for cand in enriched:
            if cand["id"] in assigned_ids:
                continue
            if cand["position"] in elig:
                cand["rosterSlotId"] = slot_id
                cand["rosterSection"] = "starting"
                assigned_ids.add(cand["id"])
                break

    # Put remaining into bench / minors
    for cand in enriched:
        if cand["id"] in assigned_ids:
            continue
        cand["rosterSlotId"] = None
        # Mark as bench; overflow goes to minors
        bench_count = sum(1 for c in enriched if c.get("rosterSection") == "bench")
        if bench_count < 6:
            cand["rosterSection"] = "bench"
        else:
            cand["rosterSection"] = "minors"
        assigned_ids.add(cand["id"])

    total_fpts = round(sum(p["fantasy_points"] for p in enriched), 2)
    total_live = round(sum(p["live"]["fpts"] for p in enriched), 2)
    return {
        "team_id": team_id,
        "team_name": team["name"],
        "owner_name": team.get("owner_name"),
        "league_id": team["league_id"],
        "league_name": (league or {}).get("name"),
        "wins": team.get("wins", 0),
        "losses": team.get("losses", 0),
        "ties": team.get("ties", 0),
        "salary_used": team.get("salary_used", 0.0),
        "season_fpts": total_fpts,
        "live_fpts": total_live,
        "players": enriched,
    }


class RosterAction(BaseModel):
    player_id: str


@api_router.post("/roster/{team_id}/add")
async def add_to_roster(team_id: str, input: RosterAction, request: Request):
    user = await get_current_user(request)
    team = await db.teams.find_one({"_id": ObjectId(team_id)})
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    if team["owner_id"] != user["_id"]:
        raise HTTPException(status_code=403, detail="Not your team")

    # Check roster limit
    league = await db.leagues.find_one({"_id": ObjectId(team["league_id"])})
    max_roster = league.get("roster_spots", 20)
    current_roster = team.get("roster", [])
    if len(current_roster) >= max_roster:
        raise HTTPException(status_code=400, detail=f"Roster full ({max_roster} players max)")

    # Validate player
    player = await db.players.find_one({"_id": ObjectId(input.player_id)})
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")

    if input.player_id in current_roster:
        raise HTTPException(status_code=400, detail="Player already on roster")

    await db.teams.update_one(
        {"_id": ObjectId(team_id)},
        {"$push": {"roster": input.player_id}}
    )

    await log_activity(team["league_id"], "roster_add", f"{team['name']} adds {player['name']} ({player['position']})", user["_id"])

    return {"message": f"Added {player['name']} to roster"}


@api_router.post("/roster/{team_id}/drop")
async def drop_from_roster(team_id: str, input: RosterAction, request: Request):
    user = await get_current_user(request)
    team = await db.teams.find_one({"_id": ObjectId(team_id)})
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    if team["owner_id"] != user["_id"]:
        raise HTTPException(status_code=403, detail="Not your team")

    current_roster = team.get("roster", [])
    if input.player_id not in current_roster:
        raise HTTPException(status_code=400, detail="Player not on roster")

    await db.teams.update_one(
        {"_id": ObjectId(team_id)},
        {"$pull": {"roster": input.player_id}}
    )

    player = await db.players.find_one({"_id": ObjectId(input.player_id)})
    name = player["name"] if player else "Unknown"
    await log_activity(team["league_id"], "roster_drop", f"{team['name']} drops {name}", user["_id"])
    return {"message": f"Dropped {name} from roster"}


# ═══════════════════════════════════════════════════════════════
# Scoring Engine Endpoints
# ═══════════════════════════════════════════════════════════════

DEFAULT_SKATER_SCORING = {
    "goals": 3, "assists": 2, "plus_minus": 1, "penalty_minutes": -0.5,
    "power_play_goals": 1, "power_play_points": 0.5,
    "short_handed_goals": 2, "short_handed_points": 1,
    "game_winning_goals": 1, "shots": 0.5,
}

DEFAULT_GOALIE_SCORING = {
    "wins": 5, "losses": -2, "saves": 0.2, "goals_against": -1,
    "shutouts": 3, "overtime_losses": 0,
}


def calculate_fantasy_points(player, config=None):
    """Calculate fantasy points for a player based on scoring config."""
    if not config:
        skater = DEFAULT_SKATER_SCORING
        goalie = DEFAULT_GOALIE_SCORING
    else:
        skater = config.get("skater_scoring", DEFAULT_SKATER_SCORING)
        goalie = config.get("goalie_scoring", DEFAULT_GOALIE_SCORING)

    fpts = 0.0
    if player.get("player_type") == "goalie" or player.get("position") == "G":
        for stat, weight in goalie.items():
            fpts += player.get(stat, 0) * weight
    else:
        for stat, weight in skater.items():
            fpts += player.get(stat, 0) * weight

    return round(fpts, 1)


class ScoringConfigCreate(BaseModel):
    league_id: str
    skater_scoring: dict
    goalie_scoring: dict
    roto_categories: list = []


@api_router.post("/scoring/config")
async def save_scoring_config(input: ScoringConfigCreate, request: Request):
    user = await get_current_user(request)

    league = await db.leagues.find_one({"_id": ObjectId(input.league_id)})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    if league["commissioner_id"] != user["_id"]:
        raise HTTPException(status_code=403, detail="Only commissioner can update scoring")

    config_doc = {
        "league_id": input.league_id,
        "skater_scoring": input.skater_scoring,
        "goalie_scoring": input.goalie_scoring,
        "roto_categories": input.roto_categories,
        "updated_by": user["_id"],
        "updated_at": datetime.now(timezone.utc).isoformat()
    }

    await db.scoring_configs.update_one(
        {"league_id": input.league_id},
        {"$set": config_doc},
        upsert=True
    )

    return {"message": "Scoring config saved"}


@api_router.get("/scoring/config")
async def get_scoring_config(league_id: str):
    config = await db.scoring_configs.find_one({"league_id": league_id})
    if not config:
        return {
            "league_id": league_id,
            "skater_scoring": DEFAULT_SKATER_SCORING,
            "goalie_scoring": DEFAULT_GOALIE_SCORING,
            "roto_categories": ["goals", "assists", "plus_minus", "power_play_points", "shots", "penalty_minutes", "wins", "save_pct", "goals_against_avg", "shutouts"]
        }
    config["_id"] = str(config["_id"])
    return config


@api_router.get("/scoring/calculate/{league_id}")
async def calculate_league_scoring(league_id: str):
    """Calculate fantasy points for all teams in a league."""
    config = await db.scoring_configs.find_one({"league_id": league_id})
    teams = await db.teams.find({"league_id": league_id}).to_list(100)

    results = []
    for team in teams:
        total_fpts = 0.0
        roster = team.get("roster", [])
        for pid in roster:
            player = await db.players.find_one({"_id": ObjectId(pid)})
            if player:
                total_fpts += calculate_fantasy_points(player, config)

        results.append({
            "team_id": str(team["_id"]),
            "team_name": team["name"],
            "owner_name": team["owner_name"],
            "roster_size": len(roster),
            "total_fantasy_points": round(total_fpts, 1)
        })

    results.sort(key=lambda t: -t["total_fantasy_points"])

    return results


@api_router.get("/scoring/roto/{league_id}")
async def calculate_roto_standings(league_id: str):
    """Calculate rotisserie standings across selected categories."""
    config = await db.scoring_configs.find_one({"league_id": league_id})
    categories = (config or {}).get("roto_categories", [
        "goals", "assists", "plus_minus", "power_play_points",
        "shots", "penalty_minutes", "wins", "save_pct", "goals_against_avg", "shutouts"
    ])

    teams = await db.teams.find({"league_id": league_id}).to_list(100)

    # Calculate category totals per team
    team_stats = []
    for team in teams:
        stats = {cat: 0 for cat in categories}
        roster = team.get("roster", [])
        for pid in roster:
            player = await db.players.find_one({"_id": ObjectId(pid)})
            if player:
                for cat in categories:
                    stats[cat] += player.get(cat, 0)

        team_stats.append({
            "team_id": str(team["_id"]),
            "team_name": team["name"],
            "owner_name": team["owner_name"],
            "stats": stats,
            "roto_points": 0
        })

    # Rank teams in each category
    num_teams = len(team_stats)
    for cat in categories:
        # Higher is better for most, lower is better for GAA/PIM
        reverse = cat not in ["goals_against_avg", "penalty_minutes"]
        sorted_teams = sorted(team_stats, key=lambda t: t["stats"][cat], reverse=reverse)
        for rank, ts in enumerate(sorted_teams):
            ts["roto_points"] += num_teams - rank  # Top gets num_teams points

    # Sort by total roto points
    team_stats.sort(key=lambda t: -t["roto_points"])

    return {"categories": categories, "standings": team_stats}


def _safe_object_id(value: str, label: str = "id") -> ObjectId:
    """Convert a string to ObjectId, raising HTTP 400 on malformed input."""
    try:
        return ObjectId(value)
    except Exception:
        raise HTTPException(status_code=400, detail=f"Invalid {label}: {value}")


@api_router.post("/payments/create")
async def create_checkout(input: PaymentCreate, request: Request):
    user = await get_current_user(request)
    
    if input.package_type not in PAYMENT_PACKAGES:
        raise HTTPException(status_code=400, detail="Invalid package type")
    
    package = PAYMENT_PACKAGES[input.package_type]
    amount = package["amount"]
    
    # For league fees, get amount from league
    if input.package_type == "league_fee" and input.league_id:
        league = await db.leagues.find_one({"_id": _safe_object_id(input.league_id, "league_id")})
        if not league or not league.get("entry_fee"):
            raise HTTPException(status_code=400, detail="League has no entry fee")
        amount = float(league["entry_fee"])

    # For league premium, require league_id and commissioner ownership
    if input.package_type == "league_premium":
        if not input.league_id:
            raise HTTPException(status_code=400, detail="league_id is required for league_premium")
        league = await db.leagues.find_one({"_id": _safe_object_id(input.league_id, "league_id")})
        if not league:
            raise HTTPException(status_code=404, detail="League not found")
        if league["commissioner_id"] != user["_id"]:
            raise HTTPException(status_code=403, detail="Only the commissioner can upgrade this league")
        if league.get("premium"):
            raise HTTPException(status_code=400, detail="League is already premium")
    
    api_key = os.environ.get("STRIPE_API_KEY")
    webhook_url = f"{str(request.base_url).rstrip('/')}/api/webhook/stripe"
    stripe_checkout = StripeCheckout(api_key=api_key, webhook_url=webhook_url)
    
    success_url = f"{input.origin_url}/payment/success?session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url = f"{input.origin_url}/payment/cancel"
    
    checkout_request = CheckoutSessionRequest(
        amount=amount,
        currency="usd",
        success_url=success_url,
        cancel_url=cancel_url,
        metadata={
            "user_id": user["_id"],
            "package_type": input.package_type,
            "league_id": input.league_id or ""
        }
    )
    
    session = await stripe_checkout.create_checkout_session(checkout_request)
    
    # Create payment transaction record
    await db.payment_transactions.insert_one({
        "session_id": session.session_id,
        "user_id": user["_id"],
        "email": user["email"],
        "amount": amount,
        "currency": "usd",
        "package_type": input.package_type,
        "league_id": input.league_id,
        "payment_status": "pending",
        "created_at": datetime.now(timezone.utc)
    })
    
    return {"url": session.url, "session_id": session.session_id}

@api_router.get("/payments/status/{session_id}")
async def get_payment_status(session_id: str, request: Request):
    user = await get_current_user(request)
    
    transaction = await db.payment_transactions.find_one({"session_id": session_id})
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")
    
    if transaction["user_id"] != user["_id"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Check with Stripe (gracefully handle upstream errors so clients can keep polling)
    api_key = os.environ.get("STRIPE_API_KEY")
    webhook_url = f"{str(request.base_url).rstrip('/')}/api/webhook/stripe"
    stripe_checkout = StripeCheckout(api_key=api_key, webhook_url=webhook_url)

    try:
        status = await stripe_checkout.get_checkout_status(session_id)
    except Exception as e:
        logger.warning(f"Stripe status lookup failed for {session_id}: {e}")
        return {
            "status": "unknown",
            "payment_status": transaction.get("payment_status", "pending"),
            "amount": float(transaction.get("amount", 0.0)),
            "currency": transaction.get("currency", "usd"),
        }
    
    # Update transaction if status changed
    if status.payment_status != transaction["payment_status"]:
        await db.payment_transactions.update_one(
            {"session_id": session_id},
            {"$set": {"payment_status": status.payment_status, "updated_at": datetime.now(timezone.utc)}}
        )
        
        # If paid, grant subscription or league access
        if status.payment_status == "paid" and transaction["payment_status"] != "paid":
            if transaction["package_type"] in ["premium_monthly", "premium_yearly"]:
                await db.users.update_one(
                    {"_id": ObjectId(transaction["user_id"])},
                    {"$set": {"subscription": transaction["package_type"], "subscription_updated_at": datetime.now(timezone.utc)}}
                )
            elif transaction["package_type"] == "league_premium" and transaction.get("league_id"):
                # Unlock premium features for the league
                await db.leagues.update_one(
                    {"_id": ObjectId(transaction["league_id"])},
                    {"$set": {
                        "premium": True,
                        "premium_activated_at": datetime.now(timezone.utc),
                        "premium_features": [f["id"] for f in LEAGUE_PREMIUM_FEATURES],
                    }}
                )
                await log_activity(
                    transaction["league_id"],
                    "league_premium_unlocked",
                    f"Premium features unlocked for this league",
                    transaction["user_id"],
                )
    
    return {
        "status": status.status,
        "payment_status": status.payment_status,
        "amount": status.amount_total / 100,
        "currency": status.currency
    }

@api_router.post("/webhook/stripe")
async def stripe_webhook(request: Request):
    body = await request.body()
    signature = request.headers.get("Stripe-Signature")
    
    api_key = os.environ.get("STRIPE_API_KEY")
    webhook_url = f"{str(request.base_url).rstrip('/')}/api/webhook/stripe"
    stripe_checkout = StripeCheckout(api_key=api_key, webhook_url=webhook_url)
    
    try:
        event = await stripe_checkout.handle_webhook(body, signature)
        
        if event.payment_status == "paid":
            await db.payment_transactions.update_one(
                {"session_id": event.session_id},
                {"$set": {"payment_status": "paid", "updated_at": datetime.now(timezone.utc)}}
            )
        
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return {"status": "error"}

# ═══════════════════════════════════════════════════════════════
# Weekly Matchup Simulation Engine
# ═══════════════════════════════════════════════════════════════
# Matchups + schedule generation → moved to routes/matchups.py
# ═══════════════════════════════════════════════════════════════


# Standings
@api_router.get("/leagues/{league_id}/standings")
async def get_standings(league_id: str):
    teams = await db.teams.find({"league_id": league_id}).to_list(100)
    
    # Sort by wins, then points_for
    teams.sort(key=lambda t: (t.get("wins", 0), t.get("points_for", 0)), reverse=True)
    
    standings = []
    for i, team in enumerate(teams):
        standings.append({
            "rank": i + 1,
            "team_id": str(team["_id"]),
            "team_name": team["name"],
            "owner_name": team["owner_name"],
            "wins": team.get("wins", 0),
            "losses": team.get("losses", 0),
            "ties": team.get("ties", 0),
            "points_for": team.get("points_for", 0),
            "points_against": team.get("points_against", 0)
        })
    
    return standings

# Health check
@api_router.get("/")
async def root():
    return {"message": "Dynasty Dreams API", "version": "1.0.0"}

@api_router.get("/health")
async def health():
    return {"status": "healthy"}

# ─── Wire modular routers (awards, drafts, matchups) ──────────
from routes import awards as awards_routes, drafts as drafts_routes, matchups as matchups_routes

_router_deps = {
    "db": db,
    "sio": sio,
    "logger": logger,
    "get_current_user": get_current_user,
    "_safe_object_id": _safe_object_id,
    "_evaluate_conditions": _evaluate_conditions,
    "_execute_trade": _execute_trade,
    "calculate_fantasy_points": calculate_fantasy_points,
    "broadcast_to_room": broadcast_to_room,
}
awards_routes.setup(_router_deps)
drafts_routes.setup(_router_deps)
matchups_routes.setup(_router_deps)
api_router.include_router(awards_routes.router)
api_router.include_router(drafts_routes.router)
api_router.include_router(matchups_routes.router)

# Include router
fastapi_app.include_router(api_router)

# CORS
fastapi_app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.environ.get("FRONTEND_URL", "http://localhost:3000")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Startup events
@fastapi_app.on_event("startup")
async def startup():
    logger.info("Starting Dynasty Dreams API...")
    
    # Create indexes
    await db.users.create_index("email", unique=True)
    await db.password_reset_tokens.create_index("expires_at", expireAfterSeconds=0)
    await db.login_attempts.create_index("identifier")
    await db.players.create_index("name")
    await db.players.create_index("team")
    await db.players.create_index("position")
    try:
        await db.players.create_index("nhl_id")
    except Exception:
        pass  # Existing unique index may conflict — ignore
    
    # Seed admin
    admin_email = os.environ.get("ADMIN_EMAIL", "admin@dynastydreams.com")
    admin_password = os.environ.get("ADMIN_PASSWORD", "admin123")
    existing = await db.users.find_one({"email": admin_email})
    if existing is None:
        hashed = hash_password(admin_password)
        await db.users.insert_one({
            "email": admin_email,
            "password_hash": hashed,
            "name": "Admin",
            "role": UserRole.ADMIN.value,
            "created_at": datetime.now(timezone.utc)
        })
        logger.info(f"Admin user created: {admin_email}")
    elif not verify_password(admin_password, existing["password_hash"]):
        await db.users.update_one({"email": admin_email}, {"$set": {"password_hash": hash_password(admin_password)}})
        logger.info("Admin password updated")
    
    # Write test credentials
    import os as os_module
    os_module.makedirs("/app/memory", exist_ok=True)
    with open("/app/memory/test_credentials.md", "w") as f:
        f.write("# Test Credentials\n\n")
        f.write("## Admin User\n")
        f.write(f"- Email: {admin_email}\n")
        f.write(f"- Password: {admin_password}\n")
        f.write("- Role: admin\n\n")
        f.write("## Auth Endpoints\n")
        f.write("- POST /api/auth/register\n")
        f.write("- POST /api/auth/login\n")
        f.write("- POST /api/auth/logout\n")
        f.write("- GET /api/auth/me\n")
        f.write("- POST /api/auth/refresh\n")
        f.write("- POST /api/auth/forgot-password\n")
        f.write("- POST /api/auth/reset-password\n")

    # Kick off background live-scoring worker (nhlpy polling).
    try:
        from live_scoring_worker import live_scoring_loop
        loop = asyncio.get_event_loop()
        fastapi_app.state.live_scoring_task = loop.create_task(live_scoring_loop(db, sio))
        logger.info("Live scoring worker scheduled")
    except Exception as e:
        logger.warning(f"Could not start live scoring worker: {e}")

@fastapi_app.on_event("shutdown")
async def shutdown():
    task = getattr(fastapi_app.state, "live_scoring_task", None)
    if task:
        task.cancel()
    client.close()

# Wrap FastAPI with Socket.IO
socket_app = socketio.ASGIApp(sio, other_asgi_app=fastapi_app, socketio_path='/api/socket.io')
app = socket_app
