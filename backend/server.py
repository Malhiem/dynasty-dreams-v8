from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

from fastapi import FastAPI, APIRouter, HTTPException, Request, Response, Depends, Query, UploadFile, File
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
    setup_wizard_complete: bool = False
    # Extended wizard / commissioner-settable fields (single source of truth)
    bench_spots: Optional[int] = None
    minors_spots: Optional[int] = None
    trade_review_period_hours: Optional[int] = None
    trade_veto_threshold_pct: Optional[int] = None
    trade_deadline_week: Optional[int] = None
    waiver_faab_budget: Optional[int] = None
    waiver_period_days: Optional[int] = None
    playoff_teams: Optional[int] = None
    playoff_start_week: Optional[int] = None
    playoff_rounds: Optional[int] = None
    playoff_end_week: Optional[int] = None
    regular_season_weeks: Optional[int] = None
    # Salary retention controls (toggle + max % of contract retainable)
    salary_retention_enabled: Optional[bool] = None
    salary_retention_max_pct: Optional[int] = None
    salary_retention_slots: Optional[int] = None
    # Schedule shape — wall-clock start/end + matchup-period config
    season_start_date: Optional[str] = None
    season_end_date: Optional[str] = None
    matchup_length_days: Optional[int] = None
    opponents_per_matchup_period: Optional[int] = None
    # Consolation playoff bracket
    consolation_enabled: Optional[bool] = None
    consolation_start_week: Optional[int] = None
    consolation_end_week: Optional[int] = None
    consolation_uses_playoff_schedule: Optional[bool] = None
    # Iter 81: extended roster controls
    ir_slots: Optional[int] = None
    ir_plus_slots: Optional[int] = None
    taxi_squad_size: Optional[int] = None
    position_limits: Optional[dict] = None
    enforce_position_maxes: Optional[bool] = None
    min_active_players: Optional[int] = None
    min_games_played: Optional[int] = None
    prorate_min_max_by_period: Optional[bool] = None
    allow_illegal_rosters: Optional[bool] = None
    ir_eligibility_modes: Optional[List[str]] = None

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
    logo_url: Optional[str] = None
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

# Auth Endpoints — extracted to routes/auth.py

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
        created_at=league_doc["created_at"],
        setup_wizard_complete=bool(league_doc.get("setup_wizard_complete", False)),
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
            created_at=league["created_at"],
            setup_wizard_complete=bool(league.get("setup_wizard_complete", False)),
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
        created_at=league["created_at"],
        setup_wizard_complete=bool(league.get("setup_wizard_complete", False)),
        bench_spots=league.get("bench_spots"),
        minors_spots=league.get("minors_spots"),
        trade_review_period_hours=league.get("trade_review_period_hours"),
        trade_veto_threshold_pct=league.get("trade_veto_threshold_pct"),
        trade_deadline_week=league.get("trade_deadline_week"),
        waiver_faab_budget=league.get("waiver_faab_budget"),
        waiver_period_days=league.get("waiver_period_days"),
        playoff_teams=league.get("playoff_teams"),
        playoff_start_week=league.get("playoff_start_week"),
        playoff_rounds=league.get("playoff_rounds"),
        playoff_end_week=league.get("playoff_end_week"),
        regular_season_weeks=league.get("regular_season_weeks"),
        salary_retention_enabled=league.get("salary_retention_enabled"),
        salary_retention_max_pct=league.get("salary_retention_max_pct"),
        salary_retention_slots=league.get("salary_retention_slots"),
        season_start_date=league.get("season_start_date"),
        season_end_date=league.get("season_end_date"),
        matchup_length_days=league.get("matchup_length_days"),
        opponents_per_matchup_period=league.get("opponents_per_matchup_period"),
        consolation_enabled=league.get("consolation_enabled"),
        consolation_start_week=league.get("consolation_start_week"),
        consolation_end_week=league.get("consolation_end_week"),
        consolation_uses_playoff_schedule=league.get("consolation_uses_playoff_schedule"),
        ir_slots=league.get("ir_slots"),
        ir_plus_slots=league.get("ir_plus_slots"),
        taxi_squad_size=league.get("taxi_squad_size"),
        position_limits=league.get("position_limits"),
        enforce_position_maxes=league.get("enforce_position_maxes"),
        min_active_players=league.get("min_active_players"),
        min_games_played=league.get("min_games_played"),
        prorate_min_max_by_period=league.get("prorate_min_max_by_period"),
        allow_illegal_rosters=league.get("allow_illegal_rosters"),
        ir_eligibility_modes=league.get("ir_eligibility_modes"),
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


@api_router.post("/leagues/{league_id}/recalculate-stats")
async def recalculate_league_stats(league_id: str, request: Request):
    """Commissioner-only: re-derive every team's wins/losses/ties/PF/PA from
    `matchups` where status='completed'. Fixes drift introduced by repeated
    simulate-week runs over deleted matchups, partial seeds, etc.
    """
    user = await get_current_user(request)
    league = await db.leagues.find_one({"_id": _safe_object_id(league_id, "league_id")})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    is_comm = league["commissioner_id"] == user["_id"]
    co_comms = league.get("co_commissioners", []) or []
    if not (is_comm or user["_id"] in co_comms):
        raise HTTPException(status_code=403, detail="Only commissioners can recalculate league stats")

    teams = await db.teams.find({"league_id": league_id}).to_list(100)
    completed = await db.matchups.find({"league_id": league_id, "status": "completed"}).to_list(2000)

    # Aggregate per-team
    agg: dict = {str(t["_id"]): {"wins": 0, "losses": 0, "ties": 0,
                                  "points_for": 0.0, "points_against": 0.0}
                 for t in teams}
    for mm in completed:
        h, a = mm.get("home_team_id"), mm.get("away_team_id")
        hs = float(mm.get("home_score", 0) or 0)
        as_ = float(mm.get("away_score", 0) or 0)
        winner = mm.get("winner")
        if h in agg:
            agg[h]["points_for"] += hs
            agg[h]["points_against"] += as_
            if winner == h:
                agg[h]["wins"] += 1
            elif winner == a:
                agg[h]["losses"] += 1
            else:
                agg[h]["ties"] += 1
        if a in agg:
            agg[a]["points_for"] += as_
            agg[a]["points_against"] += hs
            if winner == a:
                agg[a]["wins"] += 1
            elif winner == h:
                agg[a]["losses"] += 1
            else:
                agg[a]["ties"] += 1

    # Apply
    diffs = []
    for tid, vals in agg.items():
        old = next((t for t in teams if str(t["_id"]) == tid), None)
        if not old:
            continue
        before = {
            "wins": old.get("wins", 0), "losses": old.get("losses", 0),
            "ties": old.get("ties", 0),
            "points_for": round(old.get("points_for", 0.0) or 0.0, 2),
            "points_against": round(old.get("points_against", 0.0) or 0.0, 2),
        }
        after = {
            "wins": vals["wins"], "losses": vals["losses"], "ties": vals["ties"],
            "points_for": round(vals["points_for"], 2),
            "points_against": round(vals["points_against"], 2),
        }
        if before != after:
            await db.teams.update_one({"_id": ObjectId(tid)}, {"$set": after})
            diffs.append({"team_id": tid, "team_name": old.get("name"),
                          "before": before, "after": after})

    await db.audit_log.insert_one({
        "league_id": league_id,
        "actor_id": user["_id"],
        "actor_name": user.get("name", user.get("email", "Unknown")),
        "action": "league_stats_recalculated",
        "role": "commissioner" if is_comm else "co_commissioner",
        "diff": {"completed_matchups": len(completed),
                 "teams_changed": len(diffs)},
        "created_at": datetime.now(timezone.utc),
    })

    return {
        "league_id": league_id,
        "completed_matchups": len(completed),
        "teams_changed": len(diffs),
        "diffs": diffs,
    }


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


# ─── Public league discovery + join + privacy toggle ──────────────
class JoinPublicLeagueRequest(BaseModel):
    team_name: str = Field(..., min_length=1, max_length=80)


class LeagueUpdate(BaseModel):
    """DEPRECATED — moved to routes/leagues.py in iter 80. Kept as a thin
    placeholder to avoid stale imports during the same process boot.
    """
    pass


@api_router.get("/public-leagues")
async def discover_public_leagues(request: Request, q: Optional[str] = None, sport: Optional[str] = None, format: Optional[str] = None):
    """Return public leagues with open spots, excluding ones the current user is already in."""
    user_id = None
    try:
        user = await get_current_user(request)
        user_id = user["_id"]
    except HTTPException:
        user_id = None

    query: dict = {"is_private": {"$ne": True}}
    if sport:
        query["sport"] = sport
    if format:
        query["format"] = format
    if q:
        query["name"] = {"$regex": q, "$options": "i"}

    leagues = await db.leagues.find(query).sort("created_at", -1).to_list(200)

    # Pre-compute which leagues the user already belongs to (so we can mark them)
    user_league_ids = set()
    if user_id:
        user_teams = await db.teams.find({"owner_id": user_id}, {"league_id": 1}).to_list(500)
        user_league_ids = {t["league_id"] for t in user_teams}

    out = []
    for league in leagues:
        lid = str(league["_id"])
        out.append({
            "id": lid,
            "name": league.get("name"),
            "sport": league.get("sport", "nhl"),
            "format": league.get("format"),
            "scoring_format": league.get("scoring_format"),
            "max_teams": league.get("max_teams"),
            "current_teams": league.get("current_teams", 0),
            "open_spots": max(0, (league.get("max_teams", 0) or 0) - (league.get("current_teams", 0) or 0)),
            "commissioner_name": league.get("commissioner_name"),
            "salary_cap_enabled": bool(league.get("salary_cap_enabled")),
            "salary_cap": league.get("salary_cap"),
            "entry_fee": league.get("entry_fee"),
            "keepers_allowed": league.get("keepers_allowed", 0),
            "is_full": (league.get("current_teams", 0) >= (league.get("max_teams", 0) or 0)),
            "already_member": lid in user_league_ids,
            "created_at": league.get("created_at"),
        })
    return {"leagues": out, "total": len(out)}


@api_router.post("/leagues/{league_id}/join-public")
async def join_public_league(league_id: str, payload: JoinPublicLeagueRequest, request: Request):
    """Self-serve join for any public (is_private=false) league with an open spot."""
    user = await get_current_user(request)
    league = await db.leagues.find_one({"_id": _safe_object_id(league_id, "league_id")})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    if league.get("is_private"):
        raise HTTPException(status_code=403, detail="This league is private — invite only")
    if league.get("current_teams", 0) >= league["max_teams"]:
        raise HTTPException(status_code=400, detail="League is full")

    existing = await db.teams.find_one({"league_id": league_id, "owner_id": user["_id"]})
    if existing:
        raise HTTPException(status_code=400, detail="You already have a team in this league")

    team_doc = {
        "name": payload.team_name.strip(),
        "league_id": league_id,
        "owner_id": user["_id"],
        "owner_name": user["name"],
        "roster": [],
        "salary_used": 0.0,
        "wins": 0, "losses": 0, "ties": 0,
        "points_for": 0.0, "points_against": 0.0,
        "created_at": datetime.now(timezone.utc),
    }
    result = await db.teams.insert_one(team_doc)
    await db.leagues.update_one({"_id": ObjectId(league_id)}, {"$inc": {"current_teams": 1}})
    await log_activity(league_id, "team_joined",
                       f"{user['name']} joined with team '{payload.team_name}'", user["_id"])
    return {
        "message": f"Joined {league['name']}!",
        "team_id": str(result.inserted_id),
        "league_id": league_id,
        "league_name": league["name"],
    }


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
    """League-wide leaderboard of team live points.

    Now enriched with:
    - `preweek_projection` — what the team was projected to score for this
      week *at the start of the week* (average PF per completed week, floored
      at a minimum so week 1 teams don't see 0). Cached to
      `team.preweek_projections[week_N]` so the number is stable mid-week even
      if the team streams players.
    - `projection_delta` — `live_points − preweek_projection`. Positive =
      outperforming (green ↑), zero = on pace (grey =), negative = missing
      (red ↓). Frontend uses this as the sole comparator.
    - `matchup_id` — so the frontend can group rows when a league runs 2+
      matchups per period.
    - `projected_rank_change` — delta vs. the pre-week rank (ranked by PF
      *before* live points), so every team shows a projected move (↑/↓/–).
    """
    await get_current_user(request)
    _ = _safe_object_id(league_id, "league_id")

    teams = await db.teams.find(
        {"league_id": league_id},
        {"_id": 1, "name": 1, "owner_name": 1, "live_points": 1, "roster": 1,
         "points_for": 1, "wins": 1, "losses": 1, "ties": 1,
         "preweek_projections": 1},
    ).to_list(200)

    # Map team_id -> live points (for opponent lookup, kept for future use)
    tid_to_live = {str(t["_id"]): float(t.get("live_points", 0.0) or 0.0) for t in teams}

    # Grab current-week matchups to resolve each team's opponent
    league = await db.leagues.find_one({"_id": ObjectId(league_id)})
    cur_week = int((league or {}).get("current_week", 1) or 1)
    matchups = await db.matchups.find({"league_id": league_id, "week": cur_week}).to_list(50)
    opp_map: dict = {}
    matchup_map: dict = {}
    for m in matchups:
        hid = m.get("home_team_id"); aid = m.get("away_team_id")
        mid = str(m.get("_id"))
        if hid and aid:
            opp_map[hid] = aid
            opp_map[aid] = hid
            matchup_map[hid] = mid
            matchup_map[aid] = mid

    # ── Pre-week projection helper ─────────────────────────────────
    # Cached on team.preweek_projections so it's stable for the entire week
    # once the first live-scoring call of the week hits. Formula: average
    # `points_for` per completed week, clamped to [60, 250] so week-1 teams
    # or post-bye teams don't see wild numbers. Persisted via a single
    # $set so subsequent calls are O(1).
    async def preweek_proj(t: dict) -> float:
        cache_key = f"week_{cur_week}"
        cached = (t.get("preweek_projections") or {}).get(cache_key)
        if cached is not None:
            return float(cached)
        games_played = int(t.get("wins", 0) or 0) + int(t.get("losses", 0) or 0) + int(t.get("ties", 0) or 0)
        pf = float(t.get("points_for") or 0.0)
        if games_played >= 1 and pf > 0:
            avg = pf / games_played
            # Seed data sometimes has season-total FPTS in points_for — anything
            # over ~400/week is almost certainly accumulated, not a realistic
            # single-matchup total. Fall back to a neutral 120 so the variance
            # stays meaningful.
            if avg > 400.0:
                avg = 120.0
        else:
            avg = 120.0  # reasonable H2H week baseline
        proj = max(60.0, min(300.0, round(avg, 1)))
        await db.teams.update_one(
            {"_id": t["_id"]},
            {"$set": {f"preweek_projections.{cache_key}": proj}},
        )
        return proj

    # Pre-week rank = rank by points_for (before this week's live points).
    # Post-week projected rank = rank by points_for + live_points.
    pre_rank = {
        r["team_id"]: idx + 1 for idx, r in enumerate(
            sorted(
                [{"team_id": str(t["_id"]), "pre": float(t.get("points_for", 0) or 0)} for t in teams],
                key=lambda x: x["pre"], reverse=True,
            )
        )
    }
    proj_rank = {
        r["team_id"]: idx + 1 for idx, r in enumerate(
            sorted(
                [
                    {
                        "team_id": str(t["_id"]),
                        "post": float(t.get("points_for", 0) or 0) + float(t.get("live_points", 0) or 0),
                    }
                    for t in teams
                ],
                key=lambda x: x["post"], reverse=True,
            )
        )
    }

    rows = []
    for t in teams:
        tid = str(t["_id"])
        opp_id = opp_map.get(tid)
        lp_against = round(tid_to_live.get(opp_id, 0.0), 2) if opp_id else None
        pre = pre_rank.get(tid, 0)
        post = proj_rank.get(tid, 0)
        delta = (pre - post) if (pre and post) else 0   # positive = moved UP, negative = moved DOWN
        projection = await preweek_proj(t)
        live_pts = round(t.get("live_points", 0.0) or 0.0, 2)
        rows.append({
            "team_id": tid,
            "team_name": t["name"],
            "owner_name": t.get("owner_name"),
            "live_points": live_pts,
            "live_points_against": lp_against,
            "preweek_projection": projection,
            "projection_delta": round(live_pts - projection, 2),
            "opponent_team_id": opp_id,
            "matchup_id": matchup_map.get(tid),
            "roster_count": len(t.get("roster", [])),
            "pre_rank": pre,
            "projected_rank": post,
            "projected_rank_change": delta,
        })
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
    # Explicit override (set via PUT /teams/{id}) wins over auto-derivation
    override = (team.get("logo_abbr_override") or "").strip().upper()
    if override:
        abbr = override[:3]
    else:
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
        logo_url=team.get("logo_url"),
        championship_won_at=team.get("championship_won_at"),
        division_winner_at=team.get("division_winner_at"),
        conference_winner_at=team.get("conference_winner_at"),
        playoffs_reached_at=team.get("playoffs_reached_at"),
        consolation_won_at=team.get("consolation_won_at"),
    )

# Players + watchlist routes extracted to routes/players.py


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
    """Create a notification and broadcast it via WebSocket + Expo push."""
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
    # Broadcast to user's personal room (socket.io)
    await sio.emit("notification", doc, room=f"user_{user_id}")
    # Fire an Expo push in parallel (non-blocking best-effort)
    try:
        from routes.push import send_push
        asyncio.create_task(send_push(
            [user_id],
            title=title,
            body=message,
            data={"type": notif_type, "league_id": league_id, "link": link, "notification_id": doc["_id"]},
        ))
    except Exception as e:
        logger.debug(f"push notify skipped: {e}")
    return doc


async def notify_league(league_id: str, notif_type: str, title: str, message: str, link: str = None, exclude_user: str = None):
    """Send notification to all team owners in a league."""
    teams = await db.teams.find({"league_id": league_id}, {"owner_id": 1}).to_list(100)
    for team in teams:
        if team["owner_id"] != exclude_user:
            await create_notification(team["owner_id"], notif_type, title, message, league_id, link)


# Notifications routes moved to routes/notifications.py (iter 85).





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
    """Returns the team's active cap usage. Source of truth:
    1. Sum of `db.contracts.aav` if any active contracts exist (legacy / commissioner-managed).
    2. Otherwise the synthesized per-player salary used everywhere else
       (`_synthesize_player_salary`, kept consistent with the roster page,
       compliance check, and `/roster/{id}/detail`).
    """
    pipeline = [
        {"$match": {"team_id": team_id, "league_id": league_id, "status": "active"}},
        {"$group": {"_id": None, "total": {"$sum": "$aav"}}}
    ]
    result = await db.contracts.aggregate(pipeline).to_list(1)
    if result and result[0]["total"]:
        return result[0]["total"]
    # Fallback: live recompute from synthesized roster salaries so
    # `/salary-cap/{league_id}` matches `/teams/{id}/compliance` exactly.
    try:
        return await _recompute_team_salary_used(team_id)
    except Exception:
        return 0.0


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

    cap = league.get("salary_cap") or 88_000_000  # Default $88M if league hasn't configured one
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
        # Store as native datetime so it sorts consistently with trade/waiver
        # entries; mixing ISO strings with datetimes breaks MongoDB sort order.
        "created_at": datetime.now(timezone.utc),
    }
    await db.activity_feed.insert_one(doc)
    # Broadcast to league room
    doc.pop("_id", None)
    # Convert to ISO for the JSON broadcast
    broadcast_doc = {**doc, "created_at": doc["created_at"].isoformat()}
    await broadcast_to_room(f"league_{league_id}", "activity_feed", broadcast_doc)


@api_router.get("/activity/{league_id}")
async def get_activity_feed(league_id: str, event_type: Optional[str] = None, limit: int = 50, page: int = 1):
    query: dict = {"league_id": league_id}
    if event_type:
        # Support comma-separated event types: "roster_add,roster_drop,trade_executed"
        types = [t.strip() for t in event_type.split(",") if t.strip()]
        if len(types) == 1:
            query["event_type"] = types[0]
        elif types:
            query["event_type"] = {"$in": types}
    skip = (page - 1) * limit
    items = await db.activity_feed.find(query).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    total = await db.activity_feed.count_documents(query)
    for item in items:
        item["_id"] = str(item["_id"])
    return {"items": items, "total": total, "page": page, "pages": (total + limit - 1) // limit}


# ─── League transactions (normalized adds/drops/waivers/trades) ─
@api_router.get("/leagues/{league_id}/transactions")
async def get_league_transactions(
    league_id: str, limit: int = 30,
    since: Optional[str] = None, team_id: Optional[str] = None,
):
    """Returns the most recent player transactions for a league in a normalized shape:
    [{type, description, team_id?, team_name?, player_name?, created_at, raw}, ...]
    Types: roster_add, roster_drop, waiver_won, trade_executed.

    Filters:
      - `since`: ISO date string (e.g. "2026-04-01") — only events on/after this date.
      - `team_id`: filter by metadata.team_id (the actor team).
    """
    query: dict = {
        "league_id": league_id,
        "event_type": {"$in": ["roster_add", "roster_drop", "waiver_won", "waiver_lost", "trade_executed"]},
    }
    if since:
        try:
            from datetime import datetime as _dt
            cutoff = _dt.fromisoformat(since.replace("Z", "+00:00"))
            query["created_at"] = {"$gte": cutoff}
        except Exception:
            pass
    if team_id:
        query["metadata.team_id"] = team_id
    cursor = db.activity_feed.find(query).sort("created_at", -1).limit(max(1, min(limit, 500)))
    items = await cursor.to_list(limit)
    out = []
    for it in items:
        it["_id"] = str(it["_id"])
        meta = it.get("metadata") or {}
        out.append({
            "id": it["_id"],
            "type": it.get("event_type"),
            "description": it.get("message") or it.get("description"),
            "team_id": meta.get("team_id"),
            "team_name": meta.get("team_name"),
            "player_id": meta.get("player_id"),
            "player_name": meta.get("player_name"),
            "bid_amount": meta.get("bid_amount"),
            "winning_team_name": meta.get("winning_team_name"),
            "winning_bid": meta.get("winning_bid"),
            "competing_claims": meta.get("competing_claims") or [],
            "created_at": it.get("created_at"),
        })
    return {"league_id": league_id, "transactions": out, "count": len(out)}


@api_router.get("/leagues/{league_id}/pending-trades")
async def get_pending_trades(league_id: str):
    """Trades currently in flight (status in pending/voting/conditional). Intended for the
    league homepage 'Pending Trades' panel."""
    trades = await db.trades.find({
        "league_id": league_id,
        "status": {"$in": ["pending", "voting", "conditional"]},
    }).sort("submitted_at", -1).to_list(100)
    for t in trades:
        t["_id"] = str(t["_id"])
    return {"league_id": league_id, "pending_trades": trades, "count": len(trades)}


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
    MultiPartyTradeProposalCreate, TradePartyResponse,
    WaiverClaimCreate, WaiverClaimCancel
)

# ─── Trade Block ──────────────────────────────────────────────

@api_router.post("/trade-block")
async def add_to_trade_block(input: TradeBlockItemCreate, request: Request):
    user = await get_current_user(request)

    # Auto-resolve team_id from owner+league if the client didn't provide one,
    # so every new row gets a team_id (avoids the missing-Crown-link issue).
    resolved_team_id = input.team_id
    if not resolved_team_id and input.league_id:
        owner_team = await db.teams.find_one(
            {"league_id": input.league_id, "owner_id": user["_id"]},
            {"_id": 1},
        )
        if owner_team:
            resolved_team_id = str(owner_team["_id"])

    item_doc = {
        "item_type": input.item_type,
        "looking_for": input.looking_for or [],
        "owner_id": user["_id"],
        "owner_name": user["name"],
        "league_id": input.league_id,
        "team_id": resolved_team_id,
        "note": (input.note or "").strip(),
        "created_at": datetime.now(timezone.utc),
    }

    # Resolve team_name + retention preference once
    if resolved_team_id:
        team = await db.teams.find_one({"_id": ObjectId(resolved_team_id)})
        if team:
            item_doc["team_name"] = team.get("name")
            item_doc["salary_retention_pref"] = team.get(
                "salary_retention_pref", "no_preference"
            )

    if input.item_type == "player" and input.player_id:
        player = await db.players.find_one({"_id": ObjectId(input.player_id)})
        if not player:
            raise HTTPException(status_code=404, detail="Player not found")
        item_doc["player_id"] = input.player_id
        item_doc["name"] = player["name"]
        item_doc["position"] = player["position"]
        item_doc["nhl_team"] = player.get("team", "")

        season = player.get("season_stats") or {}
        gp = int(season.get("games_played") or player.get("games_played") or 0)
        item_doc["goals"] = int(season.get("goals") or player.get("goals") or 0)
        item_doc["assists"] = int(season.get("assists") or player.get("assists") or 0)
        item_doc["points"] = int(season.get("points") or player.get("points") or 0)
        item_doc["plus_minus"] = int(season.get("plus_minus") or player.get("plus_minus") or 0)
        item_doc["games_played"] = gp
        fpts = float(
            player.get("fantasy_points")
            or season.get("fantasy_points")
            or 0
        )
        item_doc["fantasy_points"] = round(fpts, 1)
        item_doc["fantasy_ppg"] = round(fpts / gp, 2) if gp else 0.0

        # Recent form: last 3 weeks of fantasy points from week_summaries (avg)
        if input.team_id and input.league_id:
            recent = await db.week_summaries.find({
                "league_id": input.league_id,
                "team_id": input.team_id,
            }).sort("week", -1).limit(3).to_list(3)
            if recent:
                item_doc["recent_form_ppw"] = round(
                    sum((r.get("points_for", 0.0) or 0.0) for r in recent) / len(recent),
                    1,
                )
    elif input.item_type == "pick":
        if input.pick_id:
            pick = await db.draft_picks.find_one({"_id": ObjectId(input.pick_id)})
            if not pick:
                raise HTTPException(status_code=404, detail="Pick not found")
            item_doc["pick_id"] = input.pick_id
            item_doc["pick_year"] = pick.get("year")
            item_doc["pick_round"] = pick.get("round")
            item_doc["pick_number"] = pick.get("pick_number")
            item_doc["name"] = (
                f"{pick.get('year')} R{pick.get('round')}"
                + (f" #{pick.get('pick_number')}" if pick.get("pick_number") else "")
            )
        else:
            item_doc["name"] = f"{input.pick_year} {input.pick_round} Round"
            item_doc["pick_year"] = input.pick_year
            item_doc["pick_round"] = input.pick_round
        item_doc["position"] = "PICK"

    # Prevent duplicates (per-owner, per-league, per-asset)
    dup_query: dict = {"owner_id": user["_id"], "item_type": input.item_type}
    if input.league_id:
        dup_query["league_id"] = input.league_id
    if input.team_id:
        dup_query["team_id"] = input.team_id
    if input.player_id:
        dup_query["player_id"] = input.player_id
    elif input.pick_id:
        dup_query["pick_id"] = input.pick_id
    elif input.pick_year and input.pick_round:
        dup_query["pick_year"] = input.pick_year
        dup_query["pick_round"] = input.pick_round
    existing = await db.trade_block.find_one(dup_query)
    if existing:
        raise HTTPException(status_code=400, detail="Already on trade block")

    result = await db.trade_block.insert_one(item_doc)
    item_doc["_id"] = str(result.inserted_id)

    # Also broadcast for live UI updates
    if input.league_id:
        await broadcast_to_room(f"league_{input.league_id}", "trade_block_changed",
                                {"action": "added", "item_id": str(result.inserted_id)})
    return item_doc

@api_router.get("/trade-block")
async def get_trade_block(
    league_id: Optional[str] = None,
    team_id: Optional[str] = None,
    owner_id: Optional[str] = None,
):
    query: dict = {}
    if league_id:
        query["league_id"] = league_id
    if team_id:
        query["team_id"] = team_id
    if owner_id:
        query["owner_id"] = owner_id
    items = await db.trade_block.find(query).sort("created_at", -1).to_list(500)

    # Enrich each item with the player's contract / salary so the frontend
    # Trade Block can render an AAV column when the league has the cap
    # turned on. We do this in one batch lookup to avoid N+1 reads.
    player_ids = [item["player_id"] for item in items if item.get("player_id")]
    salary_map: dict = {}
    if player_ids:
        oids = []
        for pid in player_ids:
            try:
                oids.append(ObjectId(pid))
            except Exception:
                continue
        if oids:
            cursor = db.players.find(
                {"_id": {"$in": oids}},
                {"contract": 1, "salary": 1, "cap_hit": 1},
            )
            async for p in cursor:
                contract = p.get("contract") or {}
                salary_map[str(p["_id"])] = {
                    "aav": contract.get("aav"),
                    "salary": p.get("salary"),
                    "cap_hit": p.get("cap_hit"),
                }
    for item in items:
        item["_id"] = str(item["_id"])
        if item.get("player_id"):
            info = salary_map.get(item["player_id"]) or {}
            # Prefer the explicit AAV value when present, fall back through
            # the synthesized salary then cap_hit so we always have *something*
            # to surface when cap is enabled.
            item["aav"] = info.get("aav") or info.get("salary") or info.get("cap_hit")
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
    if item.get("league_id"):
        await broadcast_to_room(f"league_{item['league_id']}", "trade_block_changed",
                                {"action": "removed", "item_id": item_id})
    return {"message": "Removed from trade block"}


# ─── Trade Block: salary retention preference (per team) ────────
class SalaryRetentionPrefUpdate(BaseModel):
    preference: str  # "willing_to_retain" | "no_preference" | "seeking_retention"


@api_router.put("/teams/{team_id}/trade-block-note")
async def set_trade_block_note(team_id: str, payload: dict, request: Request):
    """Update the team's public trade block note (max 200 chars).

    Visible to anyone viewing the team's trade block; only the team owner
    can edit it.
    """
    user = await get_current_user(request)
    note = (payload.get("note") or "").strip()
    if len(note) > 200:
        raise HTTPException(status_code=400, detail="Note must be 200 characters or fewer")
    team = await db.teams.find_one({"_id": _safe_object_id(team_id, "team_id")})
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    if team.get("owner_id") != user["_id"]:
        raise HTTPException(status_code=403, detail="Not your team")
    await db.teams.update_one(
        {"_id": team["_id"]},
        {"$set": {
            "trade_block_note": note,
            "trade_block_note_updated_at": datetime.now(timezone.utc),
        }},
    )
    return {"team_id": team_id, "note": note}


@api_router.get("/teams/{team_id}/trade-block-note")
async def get_trade_block_note(team_id: str):
    team = await db.teams.find_one({"_id": _safe_object_id(team_id, "team_id")})
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    return {
        "team_id": team_id,
        "note": team.get("trade_block_note") or "",
        "updated_at": team.get("trade_block_note_updated_at"),
    }


# --- Team logo upload/delete moved to routes/teams.py ------------------------


@api_router.put("/teams/{team_id}/trade-block-preference")
async def set_trade_block_preference(team_id: str, payload: SalaryRetentionPrefUpdate, request: Request):
    user = await get_current_user(request)
    if payload.preference not in ("willing_to_retain", "no_preference", "seeking_retention"):
        raise HTTPException(status_code=400, detail="Invalid preference")
    team = await db.teams.find_one({"_id": _safe_object_id(team_id, "team_id")})
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    if team.get("owner_id") != user["_id"]:
        raise HTTPException(status_code=403, detail="Not your team")

    await db.teams.update_one({"_id": team["_id"]},
                              {"$set": {"salary_retention_pref": payload.preference}})
    # Cascade preference to current trade-block items for this team
    await db.trade_block.update_many(
        {"owner_id": user["_id"], "team_id": team_id},
        {"$set": {"salary_retention_pref": payload.preference}},
    )
    return {"team_id": team_id, "preference": payload.preference}


@api_router.get("/leagues/{league_id}/trade-block-summary")
async def trade_block_summary(league_id: str, limit: int = 10):
    """Return enriched, top-valued trade block items for a league, ranked by season fantasy
    points then by recent_form_ppw (last 3 weeks). Used by the league homepage widget."""
    items = await db.trade_block.find({"league_id": league_id}).to_list(500)

    # Backfill team_name + salary_retention_pref for legacy items that were added before
    # the team_id field existed. We resolve the team via the owner_id within this league.
    needs_fill = [it for it in items if not it.get("team_name") or not it.get("salary_retention_pref")]
    if needs_fill:
        owner_ids = list({it["owner_id"] for it in needs_fill if it.get("owner_id")})
        teams_in_league = await db.teams.find({
            "league_id": league_id, "owner_id": {"$in": owner_ids},
        }).to_list(100)
        by_owner = {t["owner_id"]: t for t in teams_in_league}
        for it in needs_fill:
            t = by_owner.get(it.get("owner_id"))
            if t:
                if not it.get("team_name"):
                    it["team_name"] = t.get("name")
                if not it.get("salary_retention_pref"):
                    it["salary_retention_pref"] = t.get("salary_retention_pref", "no_preference")
                if not it.get("team_id"):
                    it["team_id"] = str(t["_id"])

    items.sort(
        key=lambda x: (
            float(x.get("fantasy_points") or 0),
            float(x.get("recent_form_ppw") or 0),
        ),
        reverse=True,
    )
    out = []
    for it in items[: max(1, min(limit, 50))]:
        it["_id"] = str(it["_id"])
        out.append(it)
    return {"league_id": league_id, "items": out, "count": len(items)}


@api_router.post("/leagues/{league_id}/trade-block/refresh-stats")
async def refresh_trade_block_stats(league_id: str, request: Request):
    """Re-pull current player season_stats + recent-form into all this league's trade-block
    items so the homepage widget stays in sync as the season advances. Idempotent.
    """
    user = await get_current_user(request)
    league = await db.leagues.find_one({"_id": _safe_object_id(league_id, "league_id")})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    is_comm = league["commissioner_id"] == user["_id"]
    co_comms = league.get("co_commissioners", []) or []
    if not (is_comm or user["_id"] in co_comms):
        raise HTTPException(status_code=403, detail="Only commissioners can refresh trade-block stats")

    items = await db.trade_block.find({"league_id": league_id, "item_type": "player"}).to_list(500)
    updated = 0
    for it in items:
        pid = it.get("player_id")
        if not pid:
            continue
        try:
            player = await db.players.find_one({"_id": ObjectId(pid)})
        except Exception:
            continue
        if not player:
            continue
        season = player.get("season_stats") or {}
        gp = int(season.get("games_played") or player.get("games_played") or 0)
        fpts = float(player.get("fantasy_points") or season.get("fantasy_points") or 0)
        patch = {
            "goals": int(season.get("goals") or player.get("goals") or 0),
            "assists": int(season.get("assists") or player.get("assists") or 0),
            "points": int(season.get("points") or player.get("points") or 0),
            "plus_minus": int(season.get("plus_minus") or player.get("plus_minus") or 0),
            "games_played": gp,
            "fantasy_points": round(fpts, 1),
            "fantasy_ppg": round(fpts / gp, 2) if gp else 0.0,
        }
        if it.get("team_id"):
            recent = await db.week_summaries.find({
                "league_id": league_id, "team_id": it["team_id"],
            }).sort("week", -1).limit(3).to_list(3)
            if recent:
                patch["recent_form_ppw"] = round(
                    sum((r.get("points_for", 0.0) or 0.0) for r in recent) / len(recent), 1,
                )
        await db.trade_block.update_one({"_id": it["_id"]}, {"$set": patch})
        updated += 1
    return {"league_id": league_id, "items_refreshed": updated}

# Trade routes extracted to routes/trades.py



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
                elif metric == "won_draft_lottery":
                    actual = 1.0 if team.get("draft_lottery_won_at") else 0.0
        elif subject_type == "pick":
            # Pick-level metrics — used for pick protection ("if pick lands top N").
            # Resolves the pick from cond.pick_id (or auto-falls back to a pick
            # found in this side's assets if not specified).
            pick_id = cond.get("pick_id")
            if not pick_id:
                for a in side_assets:
                    if a.get("asset_type") == "pick" and a.get("pick_id"):
                        pick_id = a["pick_id"]; break
            if pick_id:
                try:
                    pick = await db.draft_picks.find_one({"_id": ObjectId(pick_id)})
                except Exception:
                    pick = None
                if pick:
                    if metric == "pick_slot":
                        # Lower = better. Returns 999 when slot not yet drawn (so
                        # `lte` thresholds correctly stay unmet pre-lottery).
                        actual = float(pick.get("pick_number") or 999)
                    elif metric == "pick_round":
                        actual = float(pick.get("round") or 0)
        else:
            # Player-level. If `player_id` is set explicitly we look the player
            # up directly (works regardless of which side of the trade they're
            # on). Otherwise we scan the assets on `subject` side and take the
            # best metric among them.
            specific_pid = cond.get("player_id")
            candidate_pids = []
            if specific_pid:
                candidate_pids = [specific_pid]
            else:
                for a in side_assets:
                    if a.get("asset_type") != "player":
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


async def _format_player_for_trade_msg(pid: str) -> str:
    try:
        p = await db.players.find_one({"_id": ObjectId(pid)}, {"name": 1, "position": 1, "team": 1})
    except Exception:
        return pid
    if not p:
        return pid
    bits = [p.get("name", "Unknown")]
    pos = p.get("position")
    team = p.get("team")
    if pos or team:
        bits.append("(" + " · ".join(x for x in [pos, team] if x) + ")")
    return " ".join(bits)


async def _format_pick_for_trade_msg(pick_id: Optional[str], year: Optional[int], rnd: Optional[int]) -> str:
    if pick_id:
        try:
            d = await db.draft_picks.find_one({"_id": ObjectId(pick_id)}, {"year": 1, "round": 1})
            if d:
                year = d.get("year"); rnd = d.get("round")
        except Exception:
            pass
    if year and rnd:
        return f"{year} R{rnd} pick"
    return "Draft pick"


async def _post_trade_chat_messages(trade: dict, moves) -> None:
    """Best-effort: drop a detailed system message in the league `general`
    channel and in each pairwise DM between the trade participants.
    `moves` is the structured roster-movement dict (singles dict for 2-party,
    list for multi-party). Failures are swallowed so chat hiccups never block
    the underlying trade."""
    try:
        from routes.chat import post_system_message  # local import avoids circular
        league_id = trade["league_id"]
        teams_in_trade: list[tuple[str, str]] = []  # (team_id, team_name)
        per_team_lines: dict[str, list[str]] = {}   # team_id -> ["received: ...", ...]

        if trade.get("is_multi_party") and isinstance(moves, list):
            # Multi-party: moves is a flat list of {asset_type, from, to, ...}
            for p in (trade.get("parties") or []):
                tid = p["team_id"]
                teams_in_trade.append((tid, p.get("team_name", "Team")))
                per_team_lines.setdefault(tid, [])
            for m in moves:
                from_tid, to_tid = m.get("from"), m.get("to")
                if m.get("asset_type") == "player":
                    label = await _format_player_for_trade_msg(m.get("player_id"))
                else:
                    label = await _format_pick_for_trade_msg(m.get("pick_id"), m.get("year"), m.get("round"))
                if to_tid in per_team_lines:
                    per_team_lines[to_tid].append(f"+ {label}  ← from {m.get('from_name','?')}")
                if from_tid in per_team_lines:
                    per_team_lines[from_tid].append(f"− {label}  → to {m.get('to_name','?')}")
        else:
            # Two-party: moves dict with players_out/in + picks_out/in
            ptid = trade.get("proposer_team_id"); pname = trade.get("proposer_team_name", "Team A")
            ttid = trade.get("target_team_id");   tname = trade.get("target_team_name", "Team B")
            teams_in_trade = [(ptid, pname), (ttid, tname)]
            per_team_lines = {ptid: [], ttid: []}
            for it in moves.get("players_out", []):
                lbl = await _format_player_for_trade_msg(it["player_id"])
                per_team_lines[ptid].append(f"− {lbl}  → to {tname}")
                per_team_lines[ttid].append(f"+ {lbl}  ← from {pname}")
            for it in moves.get("players_in", []):
                lbl = await _format_player_for_trade_msg(it["player_id"])
                per_team_lines[ptid].append(f"+ {lbl}  ← from {tname}")
                per_team_lines[ttid].append(f"− {lbl}  → to {pname}")
            for it in moves.get("picks_out", []):
                lbl = await _format_pick_for_trade_msg(it.get("pick_id"), it.get("year"), it.get("round"))
                per_team_lines[ptid].append(f"− {lbl}  → to {tname}")
                per_team_lines[ttid].append(f"+ {lbl}  ← from {pname}")
            for it in moves.get("picks_in", []):
                lbl = await _format_pick_for_trade_msg(it.get("pick_id"), it.get("year"), it.get("round"))
                per_team_lines[ptid].append(f"+ {lbl}  ← from {tname}")
                per_team_lines[ttid].append(f"− {lbl}  → to {pname}")

        names = " ↔ ".join(n for _, n in teams_in_trade)
        general_lines = [f"🤝 Trade executed: {names}"]
        for tid, tname in teams_in_trade:
            received = [ln for ln in per_team_lines.get(tid, []) if ln.startswith("+")]
            if received:
                general_lines.append(f"  • {tname} receives:")
                general_lines.extend(f"      {ln[2:]}" for ln in received)
        general_text = "\n".join(general_lines)
        await post_system_message(
            db, league_id, general_text,
            channel_name="general",
            metadata={"trade_id": str(trade.get("_id")), "kind": "trade_executed"},
        )
        await post_system_message(
            db, league_id, general_text,
            channel_name="trades",
            metadata={"trade_id": str(trade.get("_id")), "kind": "trade_executed"},
        )

        # DMs: one message in every pairwise DM
        for i in range(len(teams_in_trade)):
            for j in range(i + 1, len(teams_in_trade)):
                tid_a, name_a = teams_in_trade[i]
                tid_b, name_b = teams_in_trade[j]
                lines = [f"🤝 Trade complete — {name_a} ↔ {name_b}"]
                a_lines = per_team_lines.get(tid_a, [])
                b_lines = per_team_lines.get(tid_b, [])
                if a_lines:
                    lines.append(f"\n{name_a}:")
                    lines.extend(f"  {ln}" for ln in a_lines)
                if b_lines:
                    lines.append(f"\n{name_b}:")
                    lines.extend(f"  {ln}" for ln in b_lines)
                await post_system_message(
                    db, league_id, "\n".join(lines),
                    team_pair=[tid_a, tid_b],
                    metadata={"trade_id": str(trade.get("_id")), "kind": "trade_executed_dm"},
                )
    except Exception as e:
        logger.warning("trade chat hook failed: %s", e)


async def _evaluate_single_condition(condition: dict, trade: dict) -> tuple[bool, float]:
    """Reuse `_evaluate_conditions` mechanics for a single condition. Returns
    (met, actual_value). The trade context is needed to resolve subject sides."""
    fake = {**trade, "conditions": [condition]}
    res = await _evaluate_conditions(fake)
    if not res.get("results"):
        return (False, 0.0)
    r = res["results"][0]
    return (bool(r.get("met")), float(r.get("actual_value", 0.0)))


async def _apply_pick_upgrades(trade: dict, *, final_eval: bool = False) -> dict:
    """Evaluate every `pick_upgrades` clause attached to the trade. When the
    clause's condition is met and not yet applied, mutate the underlying
    `draft_picks` doc (round + optional year), append a `pick_upgrade` entry
    to its `trade_history`, mark the upgrade entry on the trade as
    `applied_at`, and write a pass audit_log row.

    When `final_eval=True` and the condition is unmet, mark the upgrade as
    `failed_at` and write a fail audit_log row — used at season end to lock
    the outcome in. Otherwise (mid-season), unmet clauses remain pending.

    Returns `{applied: int, failed: int, results: [...]}`."""
    upgrades = trade.get("pick_upgrades") or []
    if not upgrades:
        return {"applied": 0, "failed": 0, "results": []}
    league_id = trade["league_id"]
    trade_id = str(trade.get("_id"))
    applied, failed = 0, 0
    results = []
    now = datetime.now(timezone.utc)

    for idx, up in enumerate(list(upgrades)):
        if up.get("applied_at") or up.get("failed_at"):
            results.append({"index": idx, "skipped": True, "status": "settled"})
            continue
        cond = up.get("condition") or {}
        try:
            met, actual = await _evaluate_single_condition(cond, trade)
        except Exception as e:
            logger.warning("pick upgrade eval errored trade=%s idx=%s: %s", trade_id, idx, e)
            continue

        if met:
            pick_id = up.get("pick_id")
            action = up.get("action") or "rewrite"
            try:
                pick = await db.draft_picks.find_one({"_id": ObjectId(pick_id)})
            except Exception:
                pick = None
            if not pick:
                results.append({"index": idx, "met": True, "applied": False, "reason": "pick_not_found"})
                continue

            old_round = pick.get("round")
            old_year = pick.get("year")
            old_owner = pick.get("current_team_id")

            if action == "add" or action == "remove":
                # Transfer ownership: from_team_id → to_team_id
                from_team_id = up.get("from_team_id")
                to_team_id = up.get("to_team_id")
                if not to_team_id:
                    results.append({"index": idx, "met": True, "applied": False,
                                    "reason": "missing_to_team_id"})
                    continue
                history_kind = "pick_added" if action == "add" else "pick_removed"
                history_emoji = "📈" if action == "add" else "📉"
                history_label = "Pick added" if action == "add" else "Pick removed"
                await db.draft_picks.update_one(
                    {"_id": ObjectId(pick_id)},
                    {
                        "$set": {"current_team_id": to_team_id},
                        "$push": {"trade_history": {
                            "trade_id": trade_id,
                            "kind": history_kind,
                            "from_team_id": from_team_id or old_owner,
                            "to_team_id": to_team_id,
                            "round": old_round,
                            "year": old_year,
                            "trigger": cond.get("description") or cond.get("metric"),
                            "actual_value": actual,
                            "applied_at": now,
                        }},
                    },
                )
                # Resolve team names for chat/audit
                from_team_name = None
                to_team_name = None
                try:
                    if from_team_id or old_owner:
                        ft = await db.teams.find_one({"_id": ObjectId(from_team_id or old_owner)})
                        from_team_name = (ft or {}).get("name")
                    tt = await db.teams.find_one({"_id": ObjectId(to_team_id)})
                    to_team_name = (tt or {}).get("name")
                except Exception:
                    pass
                await db.trades.update_one(
                    {"_id": trade["_id"]},
                    {"$set": {f"pick_upgrades.{idx}.applied_at": now,
                              f"pick_upgrades.{idx}.actual_value": actual}},
                )
                await db.audit_log.insert_one({
                    "league_id": league_id,
                    "action": f"pick_upgrade_{action}_applied",
                    "result": "pass",
                    "trade_id": trade_id,
                    "pick_id": pick_id,
                    "from_team_id": from_team_id or old_owner,
                    "to_team_id": to_team_id,
                    "round": old_round, "year": old_year,
                    "trigger": cond.get("description") or cond.get("metric"),
                    "actual_value": actual,
                    "created_at": now,
                })
                try:
                    from routes.chat import post_system_message
                    await post_system_message(
                        db, league_id,
                        f"{history_emoji} {history_label}: {old_year} R{old_round} "
                        f"{'→' if action == 'add' else 'reverts to'} {to_team_name or to_team_id} "
                        f"(condition: {cond.get('description') or cond.get('metric')})",
                        channel_name="trades",
                        metadata={"trade_id": trade_id, "kind": history_kind},
                    )
                except Exception:
                    pass
                applied += 1
                results.append({"index": idx, "met": True, "applied": True,
                                "action": action,
                                "from_team_id": from_team_id or old_owner,
                                "to_team_id": to_team_id})
                continue

            # action == "rewrite" (default, back-compat)
            new_round = int(up.get("new_round", 0))
            new_year = up.get("new_year")
            update_set = {"round": new_round}
            if new_year:
                update_set["year"] = int(new_year)
            await db.draft_picks.update_one(
                {"_id": ObjectId(pick_id)},
                {
                    "$set": update_set,
                    "$push": {"trade_history": {
                        "trade_id": trade_id,
                        "kind": "pick_upgrade",
                        "from_round": old_round, "to_round": new_round,
                        "from_year": old_year, "to_year": new_year or old_year,
                        "trigger": cond.get("description") or cond.get("metric"),
                        "actual_value": actual,
                        "applied_at": now,
                    }},
                },
            )
            await db.trades.update_one(
                {"_id": trade["_id"]},
                {"$set": {f"pick_upgrades.{idx}.applied_at": now,
                          f"pick_upgrades.{idx}.actual_value": actual}},
            )
            await db.audit_log.insert_one({
                "league_id": league_id,
                "action": "pick_upgrade_applied",
                "result": "pass",
                "trade_id": trade_id,
                "pick_id": pick_id,
                "from_round": old_round, "to_round": new_round,
                "from_year": old_year, "to_year": new_year or old_year,
                "trigger": cond.get("description") or cond.get("metric"),
                "actual_value": actual,
                "created_at": now,
            })
            try:
                from routes.chat import post_system_message
                await post_system_message(
                    db, league_id,
                    f"📈 Pick upgrade triggered: {old_year} R{old_round} → {new_year or old_year} R{new_round} "
                    f"(condition: {cond.get('description') or cond.get('metric')})",
                    channel_name="trades",
                    metadata={"trade_id": trade_id, "kind": "pick_upgrade"},
                )
            except Exception:
                pass
            applied += 1
            results.append({"index": idx, "met": True, "applied": True,
                            "action": "rewrite",
                            "from_round": old_round, "to_round": new_round})
        else:
            if final_eval:
                await db.trades.update_one(
                    {"_id": trade["_id"]},
                    {"$set": {f"pick_upgrades.{idx}.failed_at": now,
                              f"pick_upgrades.{idx}.actual_value": actual}},
                )
                await db.audit_log.insert_one({
                    "league_id": league_id,
                    "action": "pick_upgrade_failed",
                    "result": "fail",
                    "trade_id": trade_id,
                    "pick_id": up.get("pick_id"),
                    "trigger": cond.get("description") or cond.get("metric"),
                    "actual_value": actual,
                    "created_at": now,
                })
                failed += 1
                results.append({"index": idx, "met": False, "final": True})
            else:
                results.append({"index": idx, "met": False, "pending": True})
    return {"applied": applied, "failed": failed, "results": results}


async def _execute_multi_party_trade(trade: dict) -> dict:
    """Execute a trade with 3+ parties.
    Each party's `sends` are removed from their roster; the engine then routes
    each sent asset to the receiving party. Routing rules:
      1. If asset has explicit `to_team_id`, send there.
      2. Otherwise, find the unique party whose `receives` lists this asset
         (matched by player_id or pick_id) and send there.
      3. If neither resolves, raise.
    Draft picks update `current_team_id` and append to `trade_history`.
    """
    league_id = trade["league_id"]
    parties = trade.get("parties") or []
    teams_by_id: dict[str, dict] = {}
    rosters: dict[str, list] = {}
    for p in parties:
        team = await db.teams.find_one({"_id": ObjectId(p["team_id"])})
        if not team:
            raise HTTPException(status_code=404, detail=f"Trade team {p['team_id']} not found")
        teams_by_id[p["team_id"]] = team
        rosters[p["team_id"]] = list(team.get("roster", []) or [])

    moves: list[dict] = []
    retentions: list[dict] = []

    def _find_recipient(asset: dict, sender_team_id: str) -> Optional[str]:
        if asset.get("to_team_id") and asset["to_team_id"] != sender_team_id:
            return asset["to_team_id"]
        match_pid = asset.get("player_id")
        match_pick = asset.get("pick_id")
        for q in parties:
            if q["team_id"] == sender_team_id:
                continue
            for r in q.get("receives", []):
                if match_pid and r.get("player_id") == match_pid:
                    return q["team_id"]
                if match_pick and r.get("pick_id") == match_pick:
                    return q["team_id"]
                # Loose match by year+round when pick_id absent
                if (asset.get("asset_type") == "pick" and not match_pick
                        and r.get("asset_type") == "pick"
                        and r.get("pick_year") == asset.get("pick_year")
                        and str(r.get("pick_round")) == str(asset.get("pick_round"))):
                    return q["team_id"]
        return None

    for p in parties:
        sender_id = p["team_id"]
        sender = teams_by_id[sender_id]
        for a in p.get("sends", []):
            recipient_id = _find_recipient(a, sender_id)
            if not recipient_id:
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot route asset from {sender.get('name')}: no matching recipient party",
                )
            recipient = teams_by_id[recipient_id]

            if a.get("asset_type") == "player" and a.get("player_id"):
                pid = a["player_id"]
                if pid in rosters[sender_id]:
                    rosters[sender_id].remove(pid)
                if pid not in rosters[recipient_id]:
                    rosters[recipient_id].append(pid)
                moves.append({
                    "asset_type": "player", "player_id": pid,
                    "from": sender_id, "from_name": sender.get("name"),
                    "to": recipient_id, "to_name": recipient.get("name"),
                })
                if a.get("salary_retained_pct", 0) > 0:
                    retentions.append({
                        "player_id": pid, "retainer_team_id": sender_id,
                        "pct": a["salary_retained_pct"],
                    })
            elif a.get("asset_type") == "pick":
                query = {"league_id": league_id, "current_team_id": sender_id}
                if a.get("pick_id"):
                    query["_id"] = ObjectId(a["pick_id"])
                else:
                    if a.get("pick_year"):
                        query["year"] = int(a["pick_year"])
                    if a.get("pick_round"):
                        try:
                            query["round"] = int(str(a["pick_round"]).replace("R", "").strip())
                        except Exception:
                            pass
                pick_doc = await db.draft_picks.find_one(query)
                if pick_doc:
                    await db.draft_picks.update_one(
                        {"_id": pick_doc["_id"]},
                        {
                            "$set": {
                                "current_team_id": recipient_id,
                                "current_team_name": recipient.get("name"),
                            },
                            "$push": {"trade_history": {
                                "trade_id": str(trade["_id"]),
                                "from_team_id": sender_id,
                                "from_team_name": sender.get("name"),
                                "to_team_id": recipient_id,
                                "to_team_name": recipient.get("name"),
                                "traded_at": datetime.now(timezone.utc),
                            }},
                        },
                    )
                    moves.append({
                        "asset_type": "pick", "pick_id": str(pick_doc["_id"]),
                        "year": pick_doc["year"], "round": pick_doc["round"],
                        "from": sender_id, "from_name": sender.get("name"),
                        "to": recipient_id, "to_name": recipient.get("name"),
                    })

    # Persist all roster updates
    for tid, roster in rosters.items():
        await db.teams.update_one({"_id": ObjectId(tid)}, {"$set": {"roster": roster}})

    for r in retentions:
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

    description = "Multi-team trade executed: " + " ↔ ".join(p["team_name"] for p in parties)
    # ── Clear trade-block entries for any player that just changed hands ──
    # Multi-party path. `moves` is a list of asset movements; each player move
    # carries `player_id` directly.
    multi_traded_pids = list({
        m["player_id"]
        for m in moves
        if m.get("asset_type") == "player" and m.get("player_id")
    })
    if multi_traded_pids:
        try:
            await db.trade_block.delete_many({
                "league_id": league_id,
                "player_id": {"$in": multi_traded_pids},
            })
            await broadcast_to_room(
                f"league_{league_id}",
                "trade_block_changed",
                {"action": "cleared_after_trade", "player_ids": multi_traded_pids},
            )
        except Exception:
            pass
    try:
        await db.activity_feed.insert_one({
            "league_id": league_id,
            "event_type": "trade_executed",
            "description": description,
            "message": description,
            "created_at": datetime.now(timezone.utc),
        })
    except Exception:
        pass
    await _post_trade_chat_messages(trade, moves)
    # Initial pick-upgrade eval. Mid-season / not-yet-finalized triggers stay
    # pending and re-evaluate on every award toggle + weekly simulation.
    refreshed = await db.trades.find_one({"_id": trade["_id"]})
    if refreshed:
        await _apply_pick_upgrades(refreshed, final_eval=False)
    return {"executed": True, "moves": moves, "parties": [p["team_name"] for p in parties]}


async def _execute_trade(trade: dict) -> dict:
    if trade.get("status") == "executed":
        return {"already_executed": True}

    # ── Multi-party (3+ teams) execution path ────────────────
    parties = trade.get("parties") or []
    if parties and trade.get("is_multi_party"):
        return await _execute_multi_party_trade(trade)

    league_id = trade["league_id"]
    proposer_tid = trade["proposer_team_id"]
    target_tid = trade["target_team_id"]
    proposer = await db.teams.find_one({"_id": ObjectId(proposer_tid)})
    target = await db.teams.find_one({"_id": ObjectId(target_tid)})
    if not proposer or not target:
        raise HTTPException(status_code=404, detail="Trade team(s) not found")
    proposer_roster = list(proposer.get("roster", []) or [])
    target_roster = list(target.get("roster", []) or [])

    # ── Position-limit pre-flight (iter 83) ────────────────────────
    # Before committing the swap, simulate the post-trade rosters and ensure
    # neither side ends up over `position_limits` when `enforce_position_maxes`
    # is enabled. Loads each player once so the check is O(N+M).
    league_doc = await db.leagues.find_one({"_id": ObjectId(league_id)}) or {}
    if league_doc.get("enforce_position_maxes") and (league_doc.get("position_limits") or {}):
        from utils.roster_rules import check_position_limits, _position_of
        offered_ids = [a["player_id"] for a in trade.get("assets_offered", [])
                       if a.get("asset_type") == "player" and a.get("player_id")]
        requested_ids = [a["player_id"] for a in trade.get("assets_requested", [])
                         if a.get("asset_type") == "player" and a.get("player_id")]
        # Final rosters after the trade
        final_proposer_ids = [p for p in proposer_roster if p not in offered_ids] + requested_ids
        final_target_ids = [p for p in target_roster if p not in requested_ids] + offered_ids
        all_pid_strs = set(final_proposer_ids) | set(final_target_ids)
        all_oids = []
        for pid in all_pid_strs:
            try:
                all_oids.append(ObjectId(pid))
            except Exception:
                pass
        player_map = {}
        if all_oids:
            async for p in db.players.find(
                {"_id": {"$in": all_oids}},
                {"name": 1, "position": 1, "primary_position": 1,
                 "eligible_positions": 1, "player_type": 1},
            ):
                player_map[str(p["_id"])] = p

        def _validate(side_name: str, post_ids: list, incoming_ids: list):
            for incoming_pid in incoming_ids:
                incoming = player_map.get(incoming_pid)
                if not incoming:
                    continue
                existing = [
                    player_map[pid] for pid in post_ids
                    if pid != incoming_pid and pid in player_map
                ]
                err = check_position_limits(league_doc, existing, incoming)
                if err:
                    raise HTTPException(
                        status_code=400,
                        detail=f"{side_name} would exceed position limits after this trade: {err}",
                    )

        _validate(proposer.get("name", "Proposer"), final_proposer_ids, requested_ids)
        _validate(target.get("name", "Target"), final_target_ids, offered_ids)

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

    # ── Clear trade-block entries for any player that just changed hands ──
    # Two-team path. If a traded player was on the original owner's block, we
    # remove the listing on execution: they're no longer on the previous
    # roster and the new owner hasn't expressed interest in shopping them.
    traded_player_ids = list({
        m["player_id"]
        for m in (moves.get("players_out") or []) + (moves.get("players_in") or [])
        if m.get("player_id")
    })
    if traded_player_ids:
        try:
            await db.trade_block.delete_many({
                "league_id": league_id,
                "player_id": {"$in": traded_player_ids},
            })
            await broadcast_to_room(
                f"league_{league_id}",
                "trade_block_changed",
                {"action": "cleared_after_trade", "player_ids": traded_player_ids},
            )
        except Exception:
            pass

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
    await _post_trade_chat_messages(trade, moves)
    refreshed = await db.trades.find_one({"_id": trade["_id"]})
    if refreshed:
        await _apply_pick_upgrades(refreshed, final_eval=False)
    return {"executed": True, "moves": moves}




# ─── Draft Picks → moved to routes/drafts.py ──────────────────
# ─── Team Awards (set_team_awards) → moved to routes/awards.py ────



# Waiver routes extracted to routes/waivers.py

# ═══════════════════════════════════════════════════════════════
# Roster Management Endpoints
# ═══════════════════════════════════════════════════════════════

@api_router.get("/roster/{team_id}")
async def get_roster(team_id: str):
    team = await db.teams.find_one({"_id": ObjectId(team_id)})
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    roster_players = team.get("roster", [])
    lineup = team.get("lineup") or {}
    players = []
    for pid in roster_players:
        player = await db.players.find_one({"_id": ObjectId(pid)})
        if player:
            # Calculate fantasy points
            config = await db.scoring_configs.find_one({"league_id": team["league_id"]})
            fpts = calculate_fantasy_points(player, config)
            section_info = lineup.get(pid) or {}
            section = (section_info.get("section") or "active").lower()
            players.append({
                "player_id": str(player["_id"]),
                "name": player["name"],
                "position": player["position"],
                "player_type": player.get("player_type") or ("goalie" if player.get("position") == "G" else "skater"),
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
                "losses": player.get("losses", 0),
                "saves": player.get("saves", 0),
                "shots_against": player.get("shots_against", 0),
                "goals_against": player.get("goals_against", 0),
                "save_pct": player.get("save_pct", 0),
                "goals_against_avg": player.get("goals_against_avg", 0),
                "shutouts": player.get("shutouts", 0),
                "fantasy_points": fpts,
                "roster_section": section,
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
        # G slots removed — goalies route to dedicated "goalies" section.
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
                # Goalies still occupy their roster slot but are routed to the
                # dedicated "goalies" section so the Roster UI can render them
                # in a separate card with goalie-only stat columns.
                cand["rosterSection"] = "goalies" if cand.get("is_goalie") else "starting"
                assigned_ids.add(cand["id"])
                break

    # Put remaining into bench / minors / goalies / goalies_minors
    for cand in enriched:
        if cand["id"] in assigned_ids:
            continue
        cand["rosterSlotId"] = None
        if cand.get("is_goalie"):
            # Spillover goalies → goalies section if there's room (max 4),
            # else goalies_minors pool.
            goalie_count = sum(1 for c in enriched if c.get("rosterSection") == "goalies")
            cand["rosterSection"] = "goalies" if goalie_count < 4 else "goalies_minors"
        else:
            bench_count = sum(1 for c in enriched if c.get("rosterSection") == "bench")
            if bench_count < 6:
                cand["rosterSection"] = "bench"
            else:
                cand["rosterSection"] = "minors"
        assigned_ids.add(cand["id"])

    # Honor team.lineup overrides (commissioner-set sections — minors, ir, etc.)
    lineup = team.get("lineup") or {}
    for cand in enriched:
        ln = lineup.get(cand["id"])
        if ln and ln.get("section"):
            sec = ln["section"].lower()
            if sec == "minors":
                cand["rosterSection"] = "goalies_minors" if cand.get("is_goalie") else "minors"
            elif sec == "ir":
                cand["rosterSection"] = "ir"

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
        raise HTTPException(
            status_code=400,
            detail=f"Roster full ({len(current_roster)}/{max_roster}). Drop a player before adding.",
        )

    # Validate player
    player = await db.players.find_one({"_id": ObjectId(input.player_id)})
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")

    if input.player_id in current_roster:
        raise HTTPException(status_code=400, detail="Player already on roster")

    # ── Position-limit pre-check (league.enforce_position_maxes) ────
    from utils.roster_rules import check_position_limits
    roster_obj_ids = []
    for pid in current_roster:
        try:
            roster_obj_ids.append(ObjectId(pid))
        except Exception:
            pass
    roster_players = (
        await db.players.find(
            {"_id": {"$in": roster_obj_ids}},
            {"name": 1, "position": 1, "primary_position": 1,
             "eligible_positions": 1, "player_type": 1},
        ).to_list(200) if roster_obj_ids else []
    )
    pos_err = check_position_limits(league, roster_players, player)
    if pos_err:
        raise HTTPException(status_code=400, detail=pos_err)

    # ── Illegal roster pre-check ────────────────────────────────────
    # If the league has an IR-compliance mode that locks adds when the team
    # is non-compliant (e.g. healthy player on IR, minors-ineligible player
    # on minors), block the add until the violations are resolved.
    ir_mode = (league.get("injury_reserve_compliance_mode") or "none").lower()
    if ir_mode in ("lock_adds", "lock_adds_trades", "lock_all", "illegal_roster"):
        lineup = team.get("lineup") or {}
        if lineup:
            lookup_obj_ids = []
            for pid in current_roster:
                try:
                    lookup_obj_ids.append(ObjectId(pid))
                except Exception:
                    pass
            existing = await db.players.find(
                {"_id": {"$in": lookup_obj_ids}},
                {"name": 1, "games_played": 1, "birth_date": 1,
                 "injury_status": 1, "status": 1},
            ).to_list(200) if lookup_obj_ids else []
            illegal_msgs: list[str] = []
            for p in existing:
                pid = str(p["_id"])
                slot = lineup.get(pid)
                if not slot:
                    continue
                section = (slot.get("section") or "").lower()
                if section == "ir":
                    inj = (p.get("injury_status") or p.get("status") or "").lower()
                    if not inj or inj in ("healthy", "active", "ok"):
                        illegal_msgs.append(f"{p.get('name')} is on IR but healthy")
            if illegal_msgs:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Add denied: illegal roster — {'; '.join(illegal_msgs[:3])}. "
                        f"League IR rule: {ir_mode.replace('_', ' ')}."
                    ),
                )

    # ── Salary cap pre-check ────────────────────────────────────────
    # Recompute salary_used from the current roster (using the same
    # synthesis formula as /roster/{id}/detail). This keeps the cap honest
    # and matches what the user sees on the roster page row-by-row.
    cap_enabled = bool(league.get("salary_cap_enabled"))
    salary_cap = league.get("salary_cap")
    if cap_enabled and salary_cap:
        config = await db.scoring_configs.find_one({"league_id": team["league_id"]})
        new_player_salary = _synthesize_player_salary(player, config)
        roster_obj_ids = []
        for pid in current_roster:
            try:
                roster_obj_ids.append(ObjectId(pid))
            except Exception:
                pass
        rostered_players = []
        if roster_obj_ids:
            rostered_players = await db.players.find(
                {"_id": {"$in": roster_obj_ids}},
                {"contract": 1, "salary": 1, "cap_hit": 1, "position": 1,
                 "player_type": 1, "points": 1, "games_played": 1,
                 "goals": 1, "assists": 1, "shots": 1, "saves": 1,
                 "wins": 1, "losses": 1, "overtime_losses": 1,
                 "goals_against": 1, "shutouts": 1, "plus_minus": 1,
                 "penalty_minutes": 1, "power_play_points": 1,
                 "power_play_goals": 1, "short_handed_goals": 1,
                 "short_handed_points": 1, "game_winning_goals": 1},
            ).to_list(200)
        current_used = sum(_synthesize_player_salary(p, config) for p in rostered_players)
        retentions = team.get("salary_retentions") or []
        retention_total = sum(float(r.get("amount") or 0.0) for r in retentions)
        projected_used = current_used + new_player_salary + retention_total
        if projected_used > float(salary_cap):
            over_by = projected_used - float(salary_cap)
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Add denied: over the salary cap by ${over_by:,.0f}. "
                    f"Adding {player['name']} (${new_player_salary:,.0f}) would put you at "
                    f"${projected_used:,.0f} vs ${float(salary_cap):,.0f} cap."
                ),
            )

    await db.teams.update_one(
        {"_id": ObjectId(team_id)},
        {"$push": {"roster": input.player_id}}
    )

    # Refresh salary_used so the compliance + UI numbers track immediately.
    await _recompute_team_salary_used(team_id)

    await log_activity(
        team["league_id"], "roster_add",
        f"{team['name']} adds {player['name']} ({player['position']})",
        user["_id"],
        metadata={
            "team_id": team_id, "team_name": team["name"],
            "player_id": input.player_id, "player_name": player["name"],
            "position": player.get("position"),
        },
    )

    return {"message": f"Added {player['name']} to roster"}


async def _recompute_team_salary_used(team_id: str) -> float:
    """Sum the synthesized cap hit (mirroring `/roster/{id}/detail` formula)
    across every player on the team's roster + any salary_retentions the team
    is paying for other teams' players. Persists the result to
    `team.salary_used` so subsequent /compliance + /roster reads return the
    live number.

    Salary synthesis lives in `_synthesize_player_salary` so the same dollar
    amount appears on the roster row UI and in the cap calculation.
    """
    team = await db.teams.find_one({"_id": ObjectId(team_id)})
    if not team:
        return 0.0
    roster_obj_ids = []
    for pid in (team.get("roster") or []):
        try:
            roster_obj_ids.append(ObjectId(pid))
        except Exception:
            pass
    rostered_players = []
    if roster_obj_ids:
        rostered_players = await db.players.find(
            {"_id": {"$in": roster_obj_ids}},
            {"contract": 1, "salary": 1, "cap_hit": 1, "position": 1,
             "player_type": 1, "points": 1, "games_played": 1,
             "goals": 1, "assists": 1, "shots": 1, "saves": 1,
             "wins": 1, "losses": 1, "overtime_losses": 1,
             "goals_against": 1, "shutouts": 1, "plus_minus": 1,
             "penalty_minutes": 1, "power_play_points": 1,
             "power_play_goals": 1, "short_handed_goals": 1,
             "short_handed_points": 1, "game_winning_goals": 1},
        ).to_list(200)

    # Use scoring config of the league this team belongs to for goalie tier
    config = await db.scoring_configs.find_one({"league_id": team["league_id"]})
    used = sum(_synthesize_player_salary(p, config) for p in rostered_players)
    retentions = team.get("salary_retentions") or []
    used += sum(float(r.get("amount") or 0.0) for r in retentions)
    await db.teams.update_one(
        {"_id": ObjectId(team_id)},
        {"$set": {"salary_used": float(used)}},
    )
    return float(used)


def _synthesize_player_salary(p: dict, config: Optional[dict] = None) -> float:
    """Single source of truth for player salary synthesis.

    Mirrors the tiered formula used in `/roster/{id}/detail` so the cap usage
    on the team page matches the per-row salary chip exactly.
    """
    # Honour any explicit salary stored on the player document first
    explicit = (
        (p.get("contract") or {}).get("aav")
        or (p.get("contract") or {}).get("salary")
        or p.get("salary")
        or p.get("cap_hit")
    )
    if explicit:
        return float(explicit)

    is_g = p.get("player_type") == "goalie" or p.get("position") == "G"
    points = int(p.get("points") or 0)
    fpts_season = float(calculate_fantasy_points(p, config) or 0.0)
    if is_g:
        if fpts_season >= 300:
            salary = 9_500_000
        elif fpts_season >= 180:
            salary = 6_000_000
        elif fpts_season >= 100:
            salary = 3_500_000
        else:
            salary = 1_200_000
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
    return float(min(13_500_000, max(775_000, salary)))


@api_router.post("/teams/{team_id}/lineup")
async def save_team_lineup(team_id: str, payload: dict, request: Request):
    """Persist a team's active-lineup mapping.

    Body: {"lineup": {"<player_id>": {"section": "forward|defense|goalie|bench|ir|minors", "slot": "C|LW|RW|D|G|BN|IR|MIN"}}}

    Sections drive the `% Start` calculation (only forward/defense/goalie count
    as starting). Persisted on the team document so PlayerRoster's existing
    Save Roster button can call this from any client.
    """
    user = await get_current_user(request)
    team = await db.teams.find_one({"_id": ObjectId(team_id)})
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    league = await db.leagues.find_one({"_id": ObjectId(team["league_id"])})
    is_owner = team.get("owner_id") == user["_id"]
    is_commish = league and (
        league.get("commissioner_id") == user["_id"]
        or user["_id"] in (league.get("co_commissioners") or [])
        or (user.get("role") == "admin")
    )
    if not (is_owner or is_commish):
        raise HTTPException(status_code=403, detail="Only the team owner or commissioner may edit lineups")

    raw = payload.get("lineup") or {}
    lineup: dict[str, dict] = {}
    valid_sections = {"forward", "defense", "goalie", "bench", "ir", "ir-plus", "taxi", "minors"}
    starting_sections = {"forward", "defense", "goalie"}
    starter_ids: list[str] = []
    section_counts: dict[str, int] = {}
    for pid, info in raw.items():
        if not isinstance(info, dict):
            continue
        section = (info.get("section") or "bench").lower()
        if section not in valid_sections:
            section = "bench"
        slot = info.get("slot") or section.upper()[:3]
        lineup[str(pid)] = {"section": section, "slot": slot}
        section_counts[section] = section_counts.get(section, 0) + 1
        if section in starting_sections:
            starter_ids.append(str(pid))

    # ── Roster-section caps (iter 84) ───────────────────────────
    # Hard-cap each special section against the league's configured slot
    # counts. `ir_slots` and `ir_plus_slots` are separate counters; legacy
    # leagues that mash them together still work because both default 0.
    cap_checks = [
        ("ir", int((league or {}).get("ir_slots") or 0), "IR"),
        ("ir-plus", int((league or {}).get("ir_plus_slots") or 0), "IR+"),
        ("taxi", int((league or {}).get("taxi_squad_size") or 0), "Taxi Squad"),
        ("minors", int((league or {}).get("minors_spots") or 0), "Minors Pool"),
        ("bench", int((league or {}).get("bench_spots") or 0), "Bench"),
    ]
    for section_key, cap, friendly in cap_checks:
        used = section_counts.get(section_key, 0)
        if cap > 0 and used > cap:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"{friendly} has {used} player{'s' if used != 1 else ''} but the "
                    f"league only allows {cap}. Move {used - cap} to another section."
                ),
            )
        if cap == 0 and used > 0 and section_key in ("ir", "ir-plus", "taxi", "minors"):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"{friendly} is disabled for this league (size = 0). "
                    f"Move the {used} player{'s' if used != 1 else ''} you placed "
                    f"there to another section."
                ),
            )

    # ── League rule enforcement (iter 83) ────────────────────────
    # `min_active_players` blocks saves that would drop the team below the
    # league's required count of scoring starters. `min_games_played` is a
    # per-player warning — gathered but not blocking (warnings returned to
    # the caller so the UI can surface a yellow chip per ineligible player).
    from utils.roster_rules import check_min_active_players
    from bson.errors import InvalidId
    enforce_block = (league or {}).get("allow_illegal_rosters") is False
    active_err = check_min_active_players(league or {}, len(starter_ids))
    if active_err and enforce_block:
        raise HTTPException(status_code=400, detail=active_err)

    warnings: list[dict] = []
    if active_err:
        warnings.append({"code": "min_active_players", "message": active_err})
    min_gp = int((league or {}).get("min_games_played") or 0)
    if min_gp > 0 and starter_ids:
        oids: list = []
        for sid in starter_ids:
            try:
                oids.append(ObjectId(sid))
            except InvalidId:
                pass
        if oids:
            async for p in db.players.find(
                {"_id": {"$in": oids}},
                {"name": 1, "games_played": 1, "stats.games_played": 1},
            ):
                gp = int(p.get("games_played") or (p.get("stats") or {}).get("games_played") or 0)
                if gp < min_gp:
                    warnings.append({
                        "code": "min_games_played",
                        "player_id": str(p["_id"]),
                        "player_name": p.get("name") or "Unknown",
                        "games_played": gp,
                        "required": min_gp,
                        "message": (
                            f"{p.get('name') or 'Player'} has only {gp} GP — "
                            f"below the league's {min_gp} GP minimum."
                        ),
                    })

    await db.teams.update_one(
        {"_id": ObjectId(team_id)},
        {"$set": {"lineup": lineup, "lineup_updated_at": datetime.now(timezone.utc)}},
    )
    return {
        "team_id": team_id,
        "lineup_size": len(lineup),
        "starter_count": len(starter_ids),
        "saved": True,
        "warnings": warnings,
    }


@api_router.get("/teams/{team_id}/lineup")
async def get_team_lineup(team_id: str, request: Request):
    team = await db.teams.find_one({"_id": ObjectId(team_id)})
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    return {"team_id": team_id, "lineup": team.get("lineup") or {}}


@api_router.get("/teams/{team_id}/compliance")
async def get_team_compliance(team_id: str):
    """Return roster compliance status and reasons.

    Reasons checked:
      - roster_size_exceeded: roster_count > league.roster_spots
      - over_salary_cap: salary_used > league.salary_cap (if enabled)
      - healthy_on_ir: a player in lineup section 'ir' has no active injury status
      - minor_ineligible_in_minors: a player in section 'minors' is NOT minors-eligible

    Includes the league's `injury_reserve_compliance_mode` so the UI can drive
    its system response (lock waivers, lock adds, drop player automatically, etc).
    """
    team = await db.teams.find_one({"_id": ObjectId(team_id)})
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    league = await db.leagues.find_one({"_id": ObjectId(team["league_id"])})

    reasons: list[dict] = []
    roster_ids = team.get("roster") or []
    roster_count = len(roster_ids)
    max_roster = int((league or {}).get("roster_spots") or 25)

    if roster_count > max_roster:
        reasons.append({
            "code": "too_many_players",
            "label": "Too many players on the roster",
            "detail": f"{roster_count} on roster vs limit {max_roster}",
        })

    salary_used = float(team.get("salary_used") or 0.0)
    salary_cap = (league or {}).get("salary_cap")
    # Live-recompute salary_used so a stale team.salary_used (from before the
    # roster /add /drop endpoints maintained it) doesn't mask an over-cap state.
    if (league or {}).get("salary_cap_enabled") and salary_cap:
        try:
            salary_used = await _recompute_team_salary_used(team_id)
        except Exception:
            pass
    if (league or {}).get("salary_cap_enabled") and salary_cap and salary_used > salary_cap:
        reasons.append({
            "code": "over_salary_cap",
            "label": "Over the salary cap",
            "detail": f"${salary_used:,.0f} used vs ${salary_cap:,.0f} cap",
        })

    # Lineup-derived checks
    lineup = team.get("lineup") or {}
    if lineup and roster_ids:
        try:
            obj_ids = [ObjectId(pid) for pid in roster_ids]
        except Exception:
            obj_ids = []
        players = await db.players.find(
            {"_id": {"$in": obj_ids}},
            {"name": 1, "position": 1, "games_played": 1, "birth_date": 1,
             "injury_status": 1, "injury_type": 1, "status": 1},
        ).to_list(200)
        max_age = int((league or {}).get("minors_max_age") or 22)
        max_games = int((league or {}).get("minors_max_career_games") or 25)

        def _age_of(p):
            bd = p.get("birth_date")
            if not bd:
                return None
            try:
                bd_dt = datetime.fromisoformat(bd.split("T")[0]) if isinstance(bd, str) else bd
                return (datetime.now(timezone.utc).replace(tzinfo=None) - bd_dt).days // 365
            except Exception:
                return None

        for p in players:
            pid = str(p["_id"])
            slot_info = lineup.get(pid)
            if not slot_info:
                continue
            section = (slot_info.get("section") or "").lower()
            if section == "ir":
                injury = (p.get("injury_status") or p.get("status") or "").lower()
                if not injury or injury in ("healthy", "active", "ok"):
                    reasons.append({
                        "code": "healthy_on_ir",
                        "label": "Healthy player on IR",
                        "detail": f"{p.get('name')} is on IR but has no injury status",
                        "player_id": pid,
                        "player_name": p.get("name"),
                    })
            elif section == "minors":
                gp = int(p.get("games_played") or 0)
                age = _age_of(p)
                eligible = (gp <= max_games) or (age is not None and age <= max_age)
                if not eligible:
                    reasons.append({
                        "code": "minor_ineligible",
                        "label": "Minor league player ineligible to be on minors",
                        "detail": f"{p.get('name')} ({age}y, {gp} GP) exceeds league minors caps ({max_age}y / {max_games} GP)",
                        "player_id": pid,
                        "player_name": p.get("name"),
                    })

    compliant = len(reasons) == 0

    # Salary retention slots: how many other teams' players this team is
    # currently paying retention dollars on, plus the league-configured cap
    # (default 3 — matches NHL CBA convention). Also report the total amount
    # being retained in this team's books.
    retentions_list = team.get("salary_retentions") or []
    retention_slots_total = int((league or {}).get("salary_retention_slots") or 3)
    retention_slots_used = len(retentions_list)
    retained_salary_total = sum(float(r.get("amount") or 0.0) for r in retentions_list)

    return {
        "team_id": team_id,
        "compliant": compliant,
        "reasons": reasons,
        "roster_count": roster_count,
        "max_roster": max_roster,
        "salary_used": salary_used,
        "salary_cap": salary_cap,
        "salary_cap_enabled": bool((league or {}).get("salary_cap_enabled")),
        "salary_retention_slots_total": retention_slots_total,
        "salary_retention_slots_used": retention_slots_used,
        "salary_retention_slots_remaining": max(0, retention_slots_total - retention_slots_used),
        "retained_salary_total": retained_salary_total,
        "injury_reserve_compliance_mode": (league or {}).get("injury_reserve_compliance_mode") or "none",
    }


@api_router.put("/leagues/{league_id}/injury-reserve-compliance-mode")
async def set_injury_reserve_compliance_mode(league_id: str, payload: dict, request: Request):
    """Commissioner-only setter for league-wide IR compliance enforcement.

    Mode values:
      none, lock_all, lock_waivers, lock_adds, lock_adds_trades,
      illegal_roster, drop_player
    """
    user = await get_current_user(request)
    league = await db.leagues.find_one({"_id": ObjectId(league_id)})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    if league.get("commissioner_id") != user["_id"] and user["_id"] not in (league.get("co_commissioners") or []):
        raise HTTPException(status_code=403, detail="Only the commissioner may change this setting")

    mode = (payload.get("mode") or "none").lower()
    valid = {"none", "lock_all", "lock_waivers", "lock_adds",
             "lock_adds_trades", "illegal_roster", "drop_player"}
    if mode not in valid:
        raise HTTPException(status_code=400, detail=f"Invalid mode. Valid: {sorted(valid)}")
    await db.leagues.update_one(
        {"_id": ObjectId(league_id)},
        {"$set": {"injury_reserve_compliance_mode": mode}},
    )
    return {"league_id": league_id, "injury_reserve_compliance_mode": mode}


# ownership-bulk extracted to routes/players.py


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

    # Refresh salary_used so the compliance + UI numbers track immediately.
    await _recompute_team_salary_used(team_id)

    player = await db.players.find_one({"_id": ObjectId(input.player_id)})
    name = player["name"] if player else "Unknown"
    await log_activity(
        team["league_id"], "roster_drop",
        f"{team['name']} drops {name}",
        user["_id"],
        metadata={
            "team_id": team_id, "team_name": team["name"],
            "player_id": input.player_id, "player_name": name,
        },
    )
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


# Health check
@api_router.get("/")
async def root():
    return {"message": "Dynasty Dreams API", "version": "1.0.0"}

@api_router.get("/health")
async def health():
    return {"status": "healthy"}

# ─── Wire modular routers (awards, drafts, matchups) ──────────
from routes import awards as awards_routes, drafts as drafts_routes, matchups as matchups_routes, analytics as analytics_routes, waivers as waivers_routes, players as players_routes, trades as trades_routes, comparisons as comparisons_routes, chat as chat_routes, auth as auth_routes, trade_analyzer as trade_analyzer_routes, users as users_routes, leagues as leagues_routes, push as push_routes, seasons as seasons_routes, teams as teams_routes, ratings as ratings_routes, notifications as notifications_routes

_router_deps = {
    "db": db,
    "sio": sio,
    "logger": logger,
    "get_current_user": get_current_user,
    "_safe_object_id": _safe_object_id,
    "_evaluate_conditions": _evaluate_conditions,
    "_execute_trade": _execute_trade,
    "_apply_pick_upgrades": _apply_pick_upgrades,
    "_recompute_team_salary_used": _recompute_team_salary_used,
    "get_team_week_summary": None,  # set after endpoint defined below (late-bind via module lookup)
    "calculate_fantasy_points": calculate_fantasy_points,
    "broadcast_to_room": broadcast_to_room,
    "log_activity": log_activity,
    "create_notification": create_notification,
    # Auth deps
    "hash_password": hash_password,
    "verify_password": verify_password,
    "create_access_token": create_access_token,
    "create_refresh_token": create_refresh_token,
    "get_jwt_secret": get_jwt_secret,
    "JWT_ALGORITHM": JWT_ALGORITHM,
    "COOKIE_SECURE": COOKIE_SECURE,
    "COOKIE_SAMESITE": COOKIE_SAMESITE,
    "auth_models": {
        "UserRegister": UserRegister, "UserLogin": UserLogin,
        "UserResponse": UserResponse, "UserRole": UserRole,
        "ForgotPassword": ForgotPassword, "ResetPassword": ResetPassword,
    },
}
awards_routes.setup(_router_deps)
drafts_routes.setup(_router_deps)
matchups_routes.setup(_router_deps)
analytics_routes.setup(_router_deps)
waivers_routes.setup(_router_deps)
players_routes.setup(_router_deps)
trades_routes.setup(_router_deps)
comparisons_routes.setup(_router_deps)
chat_routes.setup(_router_deps)
auth_routes.setup(_router_deps)
trade_analyzer_routes.setup(_router_deps)
# Late-bind get_team_week_summary (defined above as an endpoint handler)
_router_deps["get_team_week_summary"] = get_team_week_summary
users_routes.setup(_router_deps)
leagues_routes.setup(_router_deps)
push_routes.setup(_router_deps)
seasons_routes.setup(_router_deps)
teams_routes.setup(_router_deps)
ratings_routes.setup(_router_deps)
notifications_routes.setup(_router_deps)
api_router.include_router(awards_routes.router)
api_router.include_router(drafts_routes.router)
api_router.include_router(matchups_routes.router)
api_router.include_router(analytics_routes.router)
api_router.include_router(waivers_routes.router)
api_router.include_router(players_routes.router)
api_router.include_router(trades_routes.router)
api_router.include_router(comparisons_routes.router)
api_router.include_router(chat_routes.router)
api_router.include_router(auth_routes.router)
api_router.include_router(trade_analyzer_routes.router)
api_router.include_router(users_routes.router)
api_router.include_router(leagues_routes.router)
api_router.include_router(push_routes.router)
api_router.include_router(seasons_routes.router)
api_router.include_router(teams_routes.router)
api_router.include_router(ratings_routes.router)
api_router.include_router(notifications_routes.router)


@api_router.post("/admin/snapshot-ownership")
async def admin_snapshot_ownership(request: Request):
    """Site-admin trigger to capture an ownership snapshot RIGHT NOW.

    Useful when site operators want the % Change column to populate before
    the natural 24h tick fires. Auth: only the user with email ==
    ADMIN_EMAIL can call this.
    """
    user = await get_current_user(request)
    admin_email = os.environ.get("ADMIN_EMAIL", "admin@dynastydreams.com")
    if user.get("email") != admin_email:
        raise HTTPException(status_code=403, detail="Site admin only")
    from ownership_snapshot_worker import snapshot_once
    return await snapshot_once(db)


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

    # Kick off daily ownership snapshot worker (writes one row per player
    # per day to `ownership_snapshots`, used by /players → pct_change_7d).
    try:
        from ownership_snapshot_worker import ownership_snapshot_loop
        loop = asyncio.get_event_loop()
        fastapi_app.state.ownership_snapshot_task = loop.create_task(ownership_snapshot_loop(db))
        logger.info("Ownership snapshot worker scheduled")
    except Exception as e:
        logger.warning(f"Could not start ownership snapshot worker: {e}")


@fastapi_app.on_event("shutdown")
async def shutdown():
    task = getattr(fastapi_app.state, "live_scoring_task", None)
    if task:
        task.cancel()
    snap_task = getattr(fastapi_app.state, "ownership_snapshot_task", None)
    if snap_task:
        snap_task.cancel()
    client.close()

# Wrap FastAPI with Socket.IO
socket_app = socketio.ASGIApp(sio, other_asgi_app=fastapi_app, socketio_path='/api/socket.io')
app = socket_app
