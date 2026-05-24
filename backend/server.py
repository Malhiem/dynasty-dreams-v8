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
from routes import awards as awards_routes, drafts as drafts_routes, matchups as matchups_routes, analytics as analytics_routes, waivers as waivers_routes, players as players_routes, trades as trades_routes, comparisons as comparisons_routes, chat as chat_routes, auth as auth_routes, trade_analyzer as trade_analyzer_routes, users as users_routes, leagues as leagues_routes, push as push_routes, seasons as seasons_routes, teams as teams_routes, ratings as ratings_routes, notifications as notifications_routes, contracts as contracts_routes, activity as activity_routes, trade_block as trade_block_routes, roster as roster_routes

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
# Late-bind get_team_week_summary (defined above as an endpoint handler)
_router_deps["get_team_week_summary"] = get_team_week_summary
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
