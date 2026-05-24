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
    # Iter 100-106: roster lock cadence, playoff format, emergency + goalie scoring
    roster_lock_type: Optional[str] = None
    roster_lock_day: Optional[str] = None
    roster_lock_second_day: Optional[str] = None
    lineup_lock_minutes_before: Optional[int] = None
    playoff_roster_lock_override: Optional[bool] = None
    playoff_roster_lock_type: Optional[str] = None
    playoff_roster_lock_day: Optional[str] = None
    playoff_roster_lock_second_day: Optional[str] = None
    playoff_lineup_lock_minutes_before: Optional[int] = None
    stats_count_start_date: Optional[str] = None
    stats_count_end_date: Optional[str] = None
    playoff_format: Optional[str] = None
    playoff_seeding_method: Optional[str] = None
    playoff_custom_matchups: Optional[List[dict]] = None
    consolation_teams: Optional[int] = None
    consolation_seeding_method: Optional[str] = None
    consolation_custom_matchups: Optional[List[dict]] = None
    emergency_changes_enabled: Optional[bool] = None
    emergency_changes_regular: Optional[int] = None
    emergency_changes_playoffs: Optional[int] = None
    emergency_eligibility: Optional[List[str]] = None
    emergency_changes_scope: Optional[str] = None
    differentiate_goalie_scoring: Optional[bool] = None
    goalie_scoring_method: Optional[str] = None
    goalie_best_x_count: Optional[int] = None
    goalie_avg_multiplier_count: Optional[int] = None
    goalie_gp_limit_enabled: Optional[bool] = None
    goalie_gp_limit: Optional[int] = None
    goalie_gp_count_method: Optional[str] = None

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
        # Iter 100-106: pass-through for lock cadence, playoff format, emergency + goalie
        roster_lock_type=league.get("roster_lock_type"),
        roster_lock_day=league.get("roster_lock_day"),
        roster_lock_second_day=league.get("roster_lock_second_day"),
        lineup_lock_minutes_before=league.get("lineup_lock_minutes_before"),
        playoff_roster_lock_override=league.get("playoff_roster_lock_override"),
        playoff_roster_lock_type=league.get("playoff_roster_lock_type"),
        playoff_roster_lock_day=league.get("playoff_roster_lock_day"),
        playoff_roster_lock_second_day=league.get("playoff_roster_lock_second_day"),
        playoff_lineup_lock_minutes_before=league.get("playoff_lineup_lock_minutes_before"),
        stats_count_start_date=league.get("stats_count_start_date"),
        stats_count_end_date=league.get("stats_count_end_date"),
        playoff_format=league.get("playoff_format"),
        playoff_seeding_method=league.get("playoff_seeding_method"),
        playoff_custom_matchups=league.get("playoff_custom_matchups"),
        consolation_teams=league.get("consolation_teams"),
        consolation_seeding_method=league.get("consolation_seeding_method"),
        consolation_custom_matchups=league.get("consolation_custom_matchups"),
        emergency_changes_enabled=league.get("emergency_changes_enabled"),
        emergency_changes_regular=league.get("emergency_changes_regular"),
        emergency_changes_playoffs=league.get("emergency_changes_playoffs"),
        emergency_eligibility=league.get("emergency_eligibility"),
        emergency_changes_scope=league.get("emergency_changes_scope"),
        differentiate_goalie_scoring=league.get("differentiate_goalie_scoring"),
        goalie_scoring_method=league.get("goalie_scoring_method"),
        goalie_best_x_count=league.get("goalie_best_x_count"),
        goalie_avg_multiplier_count=league.get("goalie_avg_multiplier_count"),
        goalie_gp_limit_enabled=league.get("goalie_gp_limit_enabled"),
        goalie_gp_limit=league.get("goalie_gp_limit"),
        goalie_gp_count_method=league.get("goalie_gp_count_method"),
    )

# ─── League Invite System ─────────────────────────────────────
import qrcode
import io
import base64
from fastapi.responses import StreamingResponse


# ─── League Constitution + Audit Log ──────────────────────────

class ConstitutionUpdate(BaseModel):
    content: str = Field(..., max_length=5000)


# Constitution + audit-log routes extracted to routes/constitution_audit.py (iter 108).


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


# ─── Live Scoring routes extracted → routes/live_scoring.py (Iter 108) ─────


# ─── Sport-Agnostic Player Fetch ──────────────────────────────

@api_router.get("/sports")
async def get_supported_sports():
    return [
        {"id": "nhl", "name": "NHL", "full_name": "National Hockey League", "positions": ["C", "LW", "RW", "D", "G"], "active": True, "player_count": await db.players.count_documents({"season": "2025-2026"})},
        {"id": "nfl", "name": "NFL", "full_name": "National Football League", "positions": ["QB", "RB", "WR", "TE", "K", "DEF"], "active": False, "player_count": 0},
        {"id": "nba", "name": "NBA", "full_name": "National Basketball Association", "positions": ["PG", "SG", "SF", "PF", "C"], "active": False, "player_count": 0},
        {"id": "mlb", "name": "MLB", "full_name": "Major League Baseball", "positions": ["C", "1B", "2B", "3B", "SS", "OF", "SP", "RP"], "active": False, "player_count": 0}
    ]


# ─── Team CRUD + _team_to_response → routes/teams.py (Iter 108) ─────


# Players + watchlist routes extracted to routes/players.py


# ─── Drafts + notification helpers → moved to routes/drafts.py (iter 98)
from routes import drafts as _drafts_module  # noqa: E402
from draft_engine import DraftChatRequest, MakeDraftPickRequest, CreateDraftRequest, UpdateDraftConfigRequest  # noqa: E402
create_notification = _drafts_module.create_notification
notify_league = _drafts_module.notify_league
AuctionNominateRequest = _drafts_module.AuctionNominateRequest
AuctionBidRequest = _drafts_module.AuctionBidRequest


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


@api_router.post("/_contracts_moved")
async def _contracts_routes_marker():
    """Contracts, salary-cap, activity-feed, transactions, and trade-block
    endpoints have all moved to dedicated routers in iter 89:
      - routes/contracts.py
      - routes/activity.py
      - routes/trade_block.py
    See those files for the implementations.
    """
    raise HTTPException(status_code=410, detail="Use the dedicated routers")


# (Contracts endpoints moved to routes/contracts.py)
# (Activity-feed endpoints moved to routes/activity.py)
# (Trade-block endpoints moved to routes/trade_block.py)


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


@api_router.get("/activity/_moved_marker")
async def _activity_routes_marker():
    """Activity-feed read endpoints moved to routes/activity.py.
    `log_activity` write helper remains here — called from many places."""
    raise HTTPException(status_code=410, detail="Use routes/activity.py")


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
# All trade-block endpoints moved to routes/trade_block.py (iter 89).
# The cascading delete on trade execution remains in _execute_trade /
# _execute_multi_party_trade below.


# Trade routes extracted to routes/trades.py



# ─── Trade Execution + Conditions ─────────────────────────────

# ─── Trade engine helpers → moved to services/trade_engine.py (iter 93)
from services import trade_engine as _trade_engine_module
_metric_value_for_player = _trade_engine_module._metric_value_for_player
_evaluate_conditions = _trade_engine_module._evaluate_conditions
_evaluate_single_condition = _trade_engine_module._evaluate_single_condition
_apply_pick_upgrades = _trade_engine_module._apply_pick_upgrades
_execute_trade = _trade_engine_module._execute_trade
_execute_multi_party_trade = _trade_engine_module._execute_multi_party_trade





# ─── Draft Picks → moved to routes/drafts.py ──────────────────
# ─── Team Awards (set_team_awards) → moved to routes/awards.py ────



# Waiver routes extracted to routes/waivers.py

# ═══════════════════════════════════════════════════════════════
# Roster Management Endpoints
# ═══════════════════════════════════════════════════════════════

# ─── Roster read-side endpoints moved to routes/roster.py (iter 91).
# Write-side `/roster/{id}/add` + `/roster/{id}/drop` remain below — they
# depend on waiver-claim creation + activity-feed writes that are
# tightly coupled to the legacy code path.


# ─── Roster write side + salary helpers → moved to routes/roster.py (iter 98)
from routes import roster as _roster_module_writes  # noqa: E402
RosterAction = _roster_module_writes.RosterAction
_synthesize_player_salary = _roster_module_writes._synthesize_player_salary
_recompute_team_salary_used = _roster_module_writes._recompute_team_salary_used


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

    # ── Iter 101: enforce roster_lock_type / lineup_lock_minutes_before ──
    # Commissioners bypass the lock so they can still adjust lineups during
    # the freeze window (matches existing override semantics for IR/cap gates).
    # ── Iter 105: emergency_changes_* bypass — when enabled and the team has
    # remaining emergency swaps budget, allow the write through and consume a
    # swap from `team.emergency_swaps_used`.
    if league and not is_commish:
        try:
            from utils.lineup_lock import evaluate_lineup_lock
            # Current week derives from the league's most recent in-progress matchup,
            # so playoff lock override kicks in only when actually inside playoffs.
            current_wk = league.get("current_week") or league.get("playoff_start_week")
            lock = evaluate_lineup_lock(league, current_week=current_wk)
            if lock["locked"]:
                emergency_on = bool(league.get("emergency_changes_enabled"))
                in_playoffs = (
                    current_wk is not None
                    and league.get("playoff_start_week") is not None
                    and int(current_wk) >= int(league["playoff_start_week"])
                )
                budget = int(
                    (league.get("emergency_changes_playoffs") or 0) if in_playoffs
                    else (league.get("emergency_changes_regular") or 0)
                )
                # Iter 106: scope determines whether the counter resets each
                # scoring period or persists for the whole season.
                scope = league.get("emergency_changes_scope") or "per_week"
                used_field = (
                    f"emergency_swaps_used_{current_wk}"
                    if scope == "per_week" and current_wk
                    else "emergency_swaps_used_season"
                )
                used = int(team.get(used_field) or 0)
                if emergency_on and budget > 0 and used < budget:
                    # ── Iter 107: Validate eligibility BEFORE consuming the swap ──
                    # Compare old vs new lineup to find starters being benched.
                    # Each removed starter must match one of the allowed criteria
                    # (unless commissioner picked "any" which means no restriction).
                    eligibility = set(league.get("emergency_eligibility") or ["any"])
                    if "any" not in eligibility:
                        STARTER_SECTIONS = {"forward", "defense", "goalie"}
                        old_lineup = team.get("lineup") or {}
                        new_lineup = (payload.get("lineup") or {}) if isinstance(payload.get("lineup"), dict) else {}
                        # Removed starters = players who WERE in a starter section old
                        # but are NOT in a starter section in the new lineup.
                        old_starters = {
                            pid for pid, slot in old_lineup.items()
                            if isinstance(slot, dict) and slot.get("section") in STARTER_SECTIONS
                        }
                        new_starters = {
                            pid for pid, slot in new_lineup.items()
                            if isinstance(slot, dict) and slot.get("section") in STARTER_SECTIONS
                        }
                        removed_starters = old_starters - new_starters
                        if removed_starters:
                            # Map each eligibility value to player status field matchers.
                            _STATUS_MAP = {
                                "scratched": lambda p: (p.get("status") or "").lower() in {"scratched", "healthy_scratch", "hs"},
                                "injured": lambda p: (p.get("status") or "").lower() in {"injured", "ir", "ir-lt", "out", "day-to-day", "dtd"} or bool(p.get("injury_status")),
                                "minors": lambda p: (p.get("status") or "").lower() in {"minors", "ahl", "assigned"} or (p.get("assignment") or "").lower() == "minors",
                                "suspended": lambda p: (p.get("status") or "").lower() in {"suspended", "suspension"},
                                "personal": lambda p: (p.get("status") or "").lower() in {"personal", "personal_leave", "leave"},
                            }
                            allowed_matchers = [_STATUS_MAP[v] for v in eligibility if v in _STATUS_MAP]
                            for pid in removed_starters:
                                try:
                                    player = await db.players.find_one({"_id": ObjectId(pid)})
                                except Exception:
                                    player = None
                                if not player:
                                    continue
                                if not any(m(player) for m in allowed_matchers):
                                    raise HTTPException(
                                        status_code=400,
                                        detail=(
                                            f"Emergency swap denied for {player.get('full_name') or player.get('name') or pid}: "
                                            f"player status doesn't match any allowed criteria "
                                            f"({', '.join(sorted(eligibility))})."
                                        ),
                                    )
                    # Allow the save — consume one swap from the budget.
                    await db.teams.update_one(
                        {"_id": team["_id"]},
                        {"$inc": {used_field: 1}},
                    )
                    logger.info(
                        f"Emergency roster swap consumed: team={team['_id']} "
                        f"week={current_wk} used={used + 1}/{budget}"
                    )
                else:
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            f"{lock['reason']} (next unlock: {lock['next_unlock_iso']})"
                        ),
                    )
        except HTTPException:
            raise
        except Exception as e:
            logger.warning(f"lineup_lock evaluation skipped: {e}")

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


# ─── Scoring config + calculate + ROTO → routes/scoring.py (Iter 108) ─────


def _safe_object_id(value: str, label: str = "id") -> ObjectId:
    """Convert a string to ObjectId, raising HTTP 400 on malformed input."""
    try:
        return ObjectId(value)
    except Exception:
        raise HTTPException(status_code=400, detail=f"Invalid {label}: {value}")


# ─── Stripe payments → moved to routes/payments.py (iter 98)
from routes import payments as payments_routes  # noqa: E402
PaymentCreate = payments_routes.PaymentCreate
PAYMENT_PACKAGES = payments_routes.PAYMENT_PACKAGES
LEAGUE_PREMIUM_FEATURES = payments_routes.LEAGUE_PREMIUM_FEATURES


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
from routes import awards as awards_routes, drafts as drafts_routes, matchups as matchups_routes, analytics as analytics_routes, waivers as waivers_routes, players as players_routes, trades as trades_routes, comparisons as comparisons_routes, chat as chat_routes, auth as auth_routes, trade_analyzer as trade_analyzer_routes, users as users_routes, leagues as leagues_routes, push as push_routes, seasons as seasons_routes, teams as teams_routes, ratings as ratings_routes, notifications as notifications_routes, contracts as contracts_routes, activity as activity_routes, trade_block as trade_block_routes, roster as roster_routes, constitution_audit as constitution_audit_routes, live_scoring as live_scoring_routes, scoring as scoring_routes

_router_deps = {
    "db": db,
    "sio": sio,
    "logger": logger,
    "get_current_user": get_current_user,
    "_safe_object_id": _safe_object_id,
    "_evaluate_conditions": _evaluate_conditions,
    "_evaluate_single_condition": _evaluate_single_condition,
    "_execute_trade": _execute_trade,
    "_apply_pick_upgrades": _apply_pick_upgrades,
    "_recompute_team_salary_used": _recompute_team_salary_used,
    "get_team_week_summary": None,  # set after endpoint defined below (late-bind via module lookup)
    "calculate_fantasy_points": calculate_fantasy_points,
    "broadcast_to_room": broadcast_to_room,
    "sio": sio,
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
# Live-scoring routes (extracted iter 108) — set up BEFORE users.py so we can
# late-bind get_team_week_summary from the new module instead of the in-file
# handler that no longer exists.
live_scoring_routes.setup(_router_deps)
scoring_routes.setup(_router_deps)
# Late-bind get_team_week_summary (now defined inside routes/live_scoring.py)
_router_deps["get_team_week_summary"] = live_scoring_routes.get_team_week_summary
users_routes.setup(_router_deps)
leagues_routes.setup(_router_deps)
push_routes.setup(_router_deps)
seasons_routes.setup(_router_deps)
teams_routes.setup(_router_deps)
ratings_routes.setup(_router_deps)
notifications_routes.setup(_router_deps)
payments_routes.setup(_router_deps)
contracts_routes.setup(_router_deps)
activity_routes.setup(_router_deps)
trade_block_routes.setup(_router_deps)
roster_routes.setup(_router_deps)
constitution_audit_routes.setup(_router_deps)
# Trade engine (extracted iter 93) shares the same deps dict
_trade_engine_module.setup(_router_deps)
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
api_router.include_router(contracts_routes.router)
api_router.include_router(activity_routes.router)
api_router.include_router(trade_block_routes.router)
api_router.include_router(roster_routes.router)
api_router.include_router(constitution_audit_routes.router)
api_router.include_router(live_scoring_routes.router)
api_router.include_router(scoring_routes.router)
api_router.include_router(payments_routes.router)


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

    # Kick off the TBD-deadline scanner (every 6h, pings commissioners with
    # custom playoff/consolation brackets whose next-week TBD slots need to
    # be finalized in the next 0..2 days).
    try:
        from playoff_tbd_worker import tbd_deadline_loop
        loop = asyncio.get_event_loop()
        fastapi_app.state.tbd_deadline_task = loop.create_task(
            tbd_deadline_loop(db, create_notification)
        )
        logger.info("TBD deadline worker scheduled")
    except Exception as e:
        logger.warning(f"Could not start TBD deadline worker: {e}")


@fastapi_app.on_event("shutdown")
async def shutdown():
    task = getattr(fastapi_app.state, "live_scoring_task", None)
    if task:
        task.cancel()
    snap_task = getattr(fastapi_app.state, "ownership_snapshot_task", None)
    if snap_task:
        snap_task.cancel()
    tbd_task = getattr(fastapi_app.state, "tbd_deadline_task", None)
    if tbd_task:
        tbd_task.cancel()
    client.close()

# Wrap FastAPI with Socket.IO
socket_app = socketio.ASGIApp(sio, other_asgi_app=fastapi_app, socketio_path='/api/socket.io')
app = socket_app
