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

# ─── League Invite System ─────────────────────────────────────
import qrcode
import io
import base64
from fastapi.responses import StreamingResponse


# ─── League Constitution + Audit Log ──────────────────────────

class ConstitutionUpdate(BaseModel):
    content: str = Field(..., max_length=5000)


# Constitution + audit-log routes extracted to routes/constitution_audit.py (iter 108).












# ─── League Premium → routes/payments.py (iter 115) ──────────


# ─── League Recommendations → routes/recommendations.py (iter 115) ──


# ─── Live Scoring routes extracted → routes/live_scoring.py (Iter 108) ─────


# ─── Sports catalogue → routes/sports.py (iter 115) ──────────


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


# /leagues/{league_id}/pending-trades + /activity/{league_id}/chat
# moved to routes/trades.py + routes/activity.py respectively (iter 115).


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


# ─── Lineup save/get/compliance + IR-compliance-mode → routes/lineup.py (Iter 109) ─




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
from routes import awards as awards_routes, drafts as drafts_routes, matchups as matchups_routes, analytics as analytics_routes, waivers as waivers_routes, players as players_routes, trades as trades_routes, comparisons as comparisons_routes, chat as chat_routes, auth as auth_routes, trade_analyzer as trade_analyzer_routes, users as users_routes, leagues as leagues_routes, push as push_routes, seasons as seasons_routes, teams as teams_routes, ratings as ratings_routes, notifications as notifications_routes, contracts as contracts_routes, activity as activity_routes, trade_block as trade_block_routes, roster as roster_routes, constitution_audit as constitution_audit_routes, live_scoring as live_scoring_routes, scoring as scoring_routes, lineup as lineup_routes, league_invites as league_invites_routes, recommendations as recommendations_routes, sports as sports_routes, admin as admin_routes, transactions_config as transactions_config_routes, cap_floor as cap_floor_routes

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
    "send_sendgrid_email": send_sendgrid_email,
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
lineup_routes.setup(_router_deps)
league_invites_routes.setup(_router_deps)
recommendations_routes.setup(_router_deps)
sports_routes.setup(_router_deps)
admin_routes.setup(_router_deps)
transactions_config_routes.setup(_router_deps)
cap_floor_routes.setup(_router_deps)
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
api_router.include_router(lineup_routes.router)
api_router.include_router(league_invites_routes.router)
api_router.include_router(payments_routes.router)
api_router.include_router(recommendations_routes.router)
api_router.include_router(sports_routes.router)
api_router.include_router(admin_routes.router)
api_router.include_router(transactions_config_routes.router)
api_router.include_router(cap_floor_routes.router)


# Admin endpoint /admin/snapshot-ownership → routes/admin.py (iter 115)


# Include router
fastapi_app.include_router(api_router)

# ─── Per-request metrics middleware (powers /api/admin/health-deep) ──
import time as _time_metrics  # noqa: E402
from metrics import record as _record_metric  # noqa: E402


@fastapi_app.middleware("http")
async def _metrics_middleware(request: Request, call_next):
    """Records (method, route_template, status, latency_ms) for every
    HTTP request handled by the API. Route template (e.g. `/api/teams/
    {team_id}/dead-cap`) is captured AFTER the route resolves so dynamic
    path params don't fragment the metrics buckets."""
    start = _time_metrics.perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        latency_ms = (_time_metrics.perf_counter() - start) * 1000.0
        route = request.scope.get("route")
        route_path = getattr(route, "path", None) or request.url.path
        # Strip socket.io polling endpoints — they fire constantly and would
        # drown the signal we actually care about.
        if "/socket.io" not in route_path:
            try:
                _record_metric(request.method, route_path, status_code, latency_ms)
            except Exception:
                pass  # Metrics must NEVER break the response path.


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
