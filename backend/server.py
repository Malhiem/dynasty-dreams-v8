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
def create_access_token(user_id: str, email: str, **extra) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=15),
        "type": "access"
    }
    payload.update(extra)
    return jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)


def create_impersonation_token(
    *, target_user_id: str, target_email: str, impersonator_id: str,
    impersonator_email: str, minutes: int = 15,
) -> str:
    """Iter 215c — short-lived read-only impersonation token used by
    admins doing 'view-as' support investigations. Encoded with
    `type=impersonation` so `get_current_user` returns the target user
    decorated with `_impersonator` metadata (audit visibility) and
    `_impersonation_mode=read_only`."""
    payload = {
        "sub": target_user_id,
        "email": target_email,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=minutes),
        "type": "impersonation",
        "mode": "read_only",
        "impersonator_id": impersonator_id,
        "impersonator_email": impersonator_email,
    }
    return jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)

def create_refresh_token(user_id: str) -> str:
    # SEC P3 — Include `iat` (issued-at). The refresh endpoint compares
    # this against the user's `password_changed_at` so a password reset
    # invalidates every refresh token issued before the change.
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "iat": now,
        "exp": now + timedelta(days=7),
        "type": "refresh",
    }
    return jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)

# Auth Helper
async def get_current_user(request: Request) -> dict:
    # Iter 230ac — Prefer the explicit `Authorization: Bearer …` header
    # over the `access_token` cookie. Two user-facing bugs surfaced
    # without this precedence:
    #   1. chriszarek1 (live) saw chriszarek (gmail)'s notifications
    #      because the browser still had gmail's `access_token` cookie
    #      from an earlier never-logged-out session in the same
    #      browser — the cookie won over chriszarek1's Bearer header.
    #   2. The Team page rendered Toronto Singularity (gmail's team)
    #      for chriszarek1 for the same reason.
    # The explicit header is what the frontend manages per-user
    # (localStorage); the cookie is shared browser-wide and gets
    # stale. Making the header the source of truth means a fresh
    # login as user B can't accidentally render user A's private data
    # just because user A's cookie is still in the jar.
    bearer = None
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        bearer = auth_header[7:]
    cookie_token = request.cookies.get("access_token")
    token = bearer or cookie_token
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(token, get_jwt_secret(), algorithms=[JWT_ALGORITHM])
        token_type = payload.get("type")
        if token_type not in ("access", "impersonation"):
            raise HTTPException(status_code=401, detail="Invalid token type")
        user = await db.users.find_one({"_id": ObjectId(payload["sub"])})
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        user["_id"] = str(user["_id"])
        user.pop("password_hash", None)
        # Iter 215c — surface impersonation context so endpoints can
        # block writes when an admin is in read-only view-as mode.
        if token_type == "impersonation":
            user["_impersonator_id"] = payload.get("impersonator_id")
            user["_impersonator_email"] = payload.get("impersonator_email")
            user["_impersonation_mode"] = payload.get("mode", "read_only")
            exp = payload.get("exp")
            if exp:
                user["_impersonation_expires_at"] = datetime.fromtimestamp(exp, tz=timezone.utc).isoformat()
            # SEC P3 — Enforce read-only impersonation. Block ALL state-
            # changing HTTP methods (POST/PUT/PATCH/DELETE) so an admin
            # in "view-as" mode cannot accidentally take destructive
            # actions on the target user's behalf. Safe methods
            # (GET/HEAD/OPTIONS) fall through.
            if user["_impersonation_mode"] == "read_only" and request.method.upper() not in (
                "GET", "HEAD", "OPTIONS",
            ):
                raise HTTPException(
                    status_code=403,
                    detail="Impersonation session is read-only — writes are blocked.",
                )
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
    # Iter 207 — optional client-supplied device fingerprint for
    # multi-account detection (extra="allow" already accepts it but we
    # declare it explicitly for documentation).
    device_hash: Optional[str] = None

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
# SEC-001 fix — restrict CORS to the same FRONTEND_URL used by REST, and
# require credentials (cookies) so the auth handshake below can read the
# httpOnly access_token. Wildcard '*' would (a) allow any site to open a
# socket and (b) browsers refuse to send cookies with `*` so the
# handshake-auth path would silently break.
_SOCKET_CORS_ORIGINS = [
    o.strip()
    for o in os.environ.get(
        "SOCKET_CORS_ORIGINS",
        os.environ.get("FRONTEND_URL", "http://localhost:3000"),
    ).split(",")
    if o.strip()
]
sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins=_SOCKET_CORS_ORIGINS,
    cors_credentials=True,
)

# Connected users tracking
connected_users: Dict[str, Dict[str, Any]] = {}


# ─── SEC-001: socket auth helpers ──────────────────────────────────────────
def _read_access_token_from_environ(environ: dict, auth: Optional[dict]) -> Optional[str]:
    """Extracts the access_token sent by the client during the Socket.IO
    handshake. Supports three transports, in order:
      1. Explicit `auth: { token: "<jwt>" }` payload from `io(url, { auth })`.
      2. `Authorization: Bearer <jwt>` header (used by mobile clients).
      3. Cookie header `access_token=<jwt>` (web — httpOnly so JS can't
         read it but the browser still sends it on same-origin handshake).
    """
    if auth and isinstance(auth, dict):
        tok = auth.get("token") or auth.get("access_token")
        if tok:
            return tok
    auth_header = environ.get("HTTP_AUTHORIZATION", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:]
    cookie_header = environ.get("HTTP_COOKIE", "")
    for part in cookie_header.split(";"):
        part = part.strip()
        if part.startswith("access_token="):
            return part[len("access_token=") :]
    return None


async def _authenticate_socket(environ: dict, auth: Optional[dict]) -> Optional[dict]:
    """Resolves the (verified) user behind this socket handshake.

    Returns `{"user_id": "...", "email": "...", "roles": [...]}` on
    success, or None when no/invalid token. We DO NOT raise here — the
    caller decides whether to refuse or downgrade.
    """
    token = _read_access_token_from_environ(environ, auth)
    if not token:
        return None
    try:
        payload = jwt.decode(token, get_jwt_secret(), algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None
    if payload.get("type") not in ("access", "impersonation"):
        return None
    uid = payload.get("sub")
    if not uid:
        return None
    return {
        "user_id": str(uid),
        "email": payload.get("email"),
        "token_type": payload.get("type"),
    }


async def _user_can_join_room(user_id: str, room_id: str) -> bool:
    """Server-side room membership check.

    • `user_{X}`  — only X itself may join.
    • `league_{X}` — caller must own a team in the league, be a co-owner,
                     or be the league commissioner.
    • `draft_{X}`  — caller must be in the parent league of that draft.
    • Anything else (admin-broadcast rooms, etc.) — denied by default.
    """
    if not room_id:
        return False

    if room_id.startswith("user_"):
        return room_id == f"user_{user_id}"

    if room_id.startswith("league_"):
        league_id = room_id[len("league_") :]
        return await _is_league_member(user_id, league_id)

    if room_id.startswith("draft_"):
        draft_id = room_id[len("draft_") :]
        draft = None
        if ObjectId.is_valid(draft_id):
            draft = await db.drafts.find_one(
                {"_id": ObjectId(draft_id)}, {"league_id": 1}
            )
        if not draft:
            return False
        return await _is_league_member(user_id, str(draft.get("league_id") or ""))

    # Unknown room namespace — deny. A future maintainer adding a new
    # room must explicitly extend this allowlist.
    return False


async def _is_league_member(user_id: str, league_id: str) -> bool:
    if not league_id:
        return False
    # Commissioner / admins of the league always count as members.
    lg = None
    if ObjectId.is_valid(league_id):
        lg = await db.leagues.find_one(
            {"_id": ObjectId(league_id)},
            {"commissioner_id": 1, "admin_ids": 1, "owner_id": 1},
        )
    if lg:
        if str(lg.get("commissioner_id") or "") == user_id:
            return True
        if str(lg.get("owner_id") or "") == user_id:
            return True
        admin_ids = [str(a) for a in (lg.get("admin_ids") or [])]
        if user_id in admin_ids:
            return True
    # Otherwise: must own a team or be a co-owner.
    team = await db.teams.find_one(
        {
            "league_id": league_id,
            "$or": [{"owner_id": user_id}, {"co_owner_ids": user_id}],
        },
        {"_id": 1},
    )
    return team is not None


@sio.event
async def connect(sid, environ, auth=None):
    """SEC-001 — reject unauthenticated socket connections.

    Raising ConnectionRefusedError causes socket.io to send a CONNECT
    error to the client (which our hooks already swallow), preventing
    the socket from ever entering the server's room registry.
    """
    user = await _authenticate_socket(environ, auth)
    if not user:
        logger.warning(f"Socket connect rejected (no/invalid token): {sid}")
        raise socketio.exceptions.ConnectionRefusedError("authentication required")
    # Stash the verified user on the session so join_room can trust it.
    await sio.save_session(sid, {"user_id": user["user_id"], "email": user.get("email")})
    logger.info(f"Client connected: {sid} (user_id={user['user_id']})")

@sio.event
async def disconnect(sid):
    logger.info(f"Client disconnected: {sid}")
    # Remove from all rooms and tracking + broadcast user_left to that room
    if sid in connected_users:
        info = connected_users[sid]
        del connected_users[sid]
        room_id = info.get("room_id")
        user_id = info.get("user_id")
        if room_id and user_id:
            still_online = any(
                v.get("room_id") == room_id and v.get("user_id") == user_id
                for v in connected_users.values()
            )
            if not still_online:
                await sio.emit('user_left', {"user_id": user_id, "room_id": room_id}, room=room_id)

@sio.event
async def join_room(sid, data):
    """SEC-001 — authoritative room-join.

    The `user_id` field in `data` is IGNORED — we use the verified
    user_id from `sio.save_session(sid, ...)` set during `connect`.
    The caller must pass server-side membership checks for the
    requested `room_id`.
    """
    room_id = data.get("room_id")
    if not room_id:
        logger.warning(f"join_room called without room_id for {sid}")
        return

    session = await sio.get_session(sid)
    user_id = (session or {}).get("user_id")
    if not user_id:
        # Should be impossible after `connect`'s refuse path, but defend
        # in depth: refuse the join + force the client to reconnect.
        logger.warning(f"join_room from sid={sid} without authenticated session")
        await sio.disconnect(sid)
        return

    if not await _user_can_join_room(user_id, room_id):
        logger.warning(
            f"join_room denied: user_id={user_id} room_id={room_id} sid={sid}"
        )
        # Tell the client so it doesn't sit waiting for events.
        await sio.emit(
            "room_join_denied",
            {"room_id": room_id, "reason": "not_authorized"},
            to=sid,
        )
        return

    await sio.enter_room(sid, room_id)
    # Personal notification room is always the AUTHENTICATED user's room
    # (never a client-supplied id) — prevents notification eavesdropping.
    await sio.enter_room(sid, f"user_{user_id}")
    connected_users[sid] = {"room_id": room_id, "user_id": user_id}
    logger.info(f"Client {sid} joined room {room_id} (user_id={user_id})")
    # Iter 140 — send the joining client a snapshot of who is already in the room
    existing = {
        v.get("user_id")
        for k, v in connected_users.items()
        if k != sid and v.get("room_id") == room_id and v.get("user_id")
    }
    await sio.emit(
        'presence_state',
        {"room_id": room_id, "user_ids": list(existing)},
        to=sid,
    )
    await sio.emit('user_joined', {"user_id": user_id, "room_id": room_id}, room=room_id)

@sio.event
async def leave_room(sid, data):
    room_id = data.get("room_id")
    if room_id:
        await sio.leave_room(sid, room_id)
        logger.info(f"Client {sid} left room {room_id}")
        # Iter 140 — broadcast user_left for presence tracking
        info = connected_users.get(sid) or {}
        user_id = info.get("user_id")
        if user_id:
            still_online = any(
                k != sid and v.get("room_id") == room_id and v.get("user_id") == user_id
                for k, v in connected_users.items()
            )
            if not still_online:
                await sio.emit('user_left', {"user_id": user_id, "room_id": room_id}, room=room_id)

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
from routes import awards as awards_routes, drafts as drafts_routes, draft_config as draft_config_routes, matchups as matchups_routes, analytics as analytics_routes, waivers as waivers_routes, players as players_routes, trades as trades_routes, comparisons as comparisons_routes, chat as chat_routes, auth as auth_routes, trade_analyzer as trade_analyzer_routes, users as users_routes, leagues as leagues_routes, push as push_routes, seasons as seasons_routes, teams as teams_routes, ratings as ratings_routes, notifications as notifications_routes, notification_preferences as notification_preferences_routes, contracts as contracts_routes, activity as activity_routes, trade_block as trade_block_routes, roster as roster_routes, constitution_audit as constitution_audit_routes, live_scoring as live_scoring_routes, scoring as scoring_routes, lineup as lineup_routes, league_invites as league_invites_routes, team_invites as team_invites_routes, recommendations as recommendations_routes, sports as sports_routes, admin as admin_routes, transactions_config as transactions_config_routes, cap_floor as cap_floor_routes, matchup_stars as matchup_stars_routes, monitors as monitors_routes, ops_console as ops_console_routes, admin_platform as admin_platform_routes, user_reports as user_reports_routes, moderation as moderation_routes, platform_ops as platform_ops_routes, admin_user_actions as admin_user_actions_routes, forum as forum_routes, roster_snapshots as roster_snapshots_routes, analytics_ux as analytics_ux_routes

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
    "create_impersonation_token": create_impersonation_token,
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
draft_config_routes.setup(_router_deps)
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
team_invites_routes.setup(_router_deps)
recommendations_routes.setup(_router_deps)
sports_routes.setup(_router_deps)
admin_routes.setup(_router_deps)
transactions_config_routes.setup(_router_deps)
cap_floor_routes.setup(_router_deps)
matchup_stars_routes.setup(_router_deps)
# Late-bind get_team_week_summary (now defined inside routes/live_scoring.py)
_router_deps["get_team_week_summary"] = live_scoring_routes.get_team_week_summary
users_routes.setup(_router_deps)
leagues_routes.setup(_router_deps)
push_routes.setup(_router_deps)
seasons_routes.setup(_router_deps)
teams_routes.setup(_router_deps)
ratings_routes.setup(_router_deps)
notifications_routes.setup(_router_deps)
notification_preferences_routes.setup(_router_deps)
payments_routes.setup(_router_deps)
contracts_routes.setup(_router_deps)
activity_routes.setup(_router_deps)
trade_block_routes.setup(_router_deps)
roster_routes.setup(_router_deps)
constitution_audit_routes.setup(_router_deps)
# Iter 187 — Commissioner Ops Console summary endpoint
ops_console_routes.setup(_router_deps)
# Iter 201a — platform-admin moderation dashboard
admin_platform_routes.setup(db=db, get_current_user=get_current_user)
# Iter 205 — user reports / flagging (Content Moderation Phase 1)
user_reports_routes.setup(_router_deps)
# Iter 206 — Content Moderation Phase 2 & 3 + Account Integrity
moderation_routes.setup(_router_deps)
# Iter 209 — Platform Health & Ops dashboards
platform_ops_routes.setup(_router_deps)
# Iter 215 — Admin User Actions framework
admin_user_actions_routes.setup(_router_deps)
# Iter 217 — Forum + Roster snapshots
forum_routes.setup(_router_deps)
roster_snapshots_routes.setup(_router_deps)
# Iter 218 — UX analytics
analytics_ux_routes.setup(_router_deps)
# Trade engine (extracted iter 93) shares the same deps dict
_trade_engine_module.setup(_router_deps)
api_router.include_router(awards_routes.router)
api_router.include_router(drafts_routes.router)
api_router.include_router(draft_config_routes.router)
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
api_router.include_router(notification_preferences_routes.router)
api_router.include_router(contracts_routes.router)
api_router.include_router(activity_routes.router)
api_router.include_router(trade_block_routes.router)
api_router.include_router(roster_routes.router)
api_router.include_router(constitution_audit_routes.router)
api_router.include_router(live_scoring_routes.router)
api_router.include_router(scoring_routes.router)
api_router.include_router(lineup_routes.router)
api_router.include_router(league_invites_routes.router)
api_router.include_router(team_invites_routes.router)
api_router.include_router(payments_routes.router)
api_router.include_router(recommendations_routes.router)
api_router.include_router(sports_routes.router)
api_router.include_router(admin_routes.router)
api_router.include_router(transactions_config_routes.router)
api_router.include_router(cap_floor_routes.router)
api_router.include_router(matchup_stars_routes.router)
monitors_routes.setup(_router_deps)
api_router.include_router(monitors_routes.router)
# Iter 187 — Ops Console
api_router.include_router(ops_console_routes.router)
api_router.include_router(admin_platform_routes.router)
# Iter 205 — User Reports (Content Moderation Phase 1)
api_router.include_router(user_reports_routes.router)
# Iter 206 — Content Moderation Phase 2/3 + Account Integrity (admin + public appeal router)
api_router.include_router(moderation_routes.router)
api_router.include_router(moderation_routes.appeals_router)
# Iter 209 — Platform Health & Ops
api_router.include_router(platform_ops_routes.router)
# Iter 215 — Admin User Actions framework
api_router.include_router(admin_user_actions_routes.router)
# Iter 217 — Forum + Roster snapshots
api_router.include_router(forum_routes.router)
api_router.include_router(roster_snapshots_routes.router)
# Iter 218 — UX analytics
api_router.include_router(analytics_ux_routes.router)


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
    
    # Iter 194c — background sweeper: auto-resolve expired in-draft pick
    # trades every 30 seconds. Lightweight (only touches `pending_draft_review`
    # rows with elapsed `review_expires_at`).
    async def _pick_trade_sweeper():
        from routes.trades import _expire_pending_pick_trades
        while True:
            try:
                await _expire_pending_pick_trades(db)
            except Exception as e:
                logger.error(f"pick-trade sweeper error: {e}")
            await asyncio.sleep(30)
    asyncio.create_task(_pick_trade_sweeper())

    # Iter 210 — Critical Alerts sweeper (broadcasts platform-wide alerts
    # to admins via Socket.IO every 60s).
    asyncio.create_task(platform_ops_routes.alerts_sweeper_loop())

    # Iter 219 — Empty-league sweeper.
    # When a league's team count drops to 0, mark it `empty_since` on
    # first detection and hard-delete it 2 days later. Leagues with at
    # least one team are immune (the `empty_since` field is cleared).
    async def _empty_league_sweeper():
        from datetime import timezone as _tz, timedelta as _td, datetime as _dt
        while True:
            try:
                now = _dt.now(_tz.utc)
                async for lg in db.leagues.find({}, {"_id": 1, "empty_since": 1}):
                    lid = str(lg["_id"])
                    team_count = await db.teams.count_documents({"league_id": lid})
                    empty_since = lg.get("empty_since")
                    if team_count == 0:
                        if not empty_since:
                            await db.leagues.update_one(
                                {"_id": lg["_id"]},
                                {"$set": {"empty_since": now.isoformat()}},
                            )
                        else:
                            try:
                                marked = _dt.fromisoformat(str(empty_since).replace("Z", "+00:00"))
                            except Exception:
                                marked = now
                            if (now - marked) >= _td(days=2):
                                # Hard delete the league + its detritus
                                await db.leagues.delete_one({"_id": lg["_id"]})
                                await db.teams.delete_many({"league_id": lid})
                                await db.league_invites.delete_many({"league_id": lid})
                                await db.forum_threads.delete_many({"league_id": lid})
                                await db.forum_posts.delete_many({"league_id": lid})
                                await db.roster_snapshots.delete_many({"league_id": lid})
                                logger.info(f"empty-league sweeper: deleted league {lid} after 2-day empty grace period")
                    else:
                        if empty_since:
                            await db.leagues.update_one(
                                {"_id": lg["_id"]},
                                {"$unset": {"empty_since": ""}},
                            )
            except Exception as e:
                logger.error(f"empty-league sweeper error: {e}")
            await asyncio.sleep(3600)  # check hourly
    asyncio.create_task(_empty_league_sweeper())

    # Iter 228 — Waivers scheduler.
    # Every 60s, find leagues with `transactions_config.waiver.enabled=True`
    # and call the engine to process any claims whose `processes_at` is due.
    # Engine is idempotent — claims already processed are skipped.
    async def _waivers_scheduler_loop():
        from services.waiver_engine import process_pending_claims
        while True:
            try:
                cursor = db.leagues.find(
                    {"transactions_config.waiver.enabled": True},
                    {"_id": 1},
                )
                async for lg in cursor:
                    try:
                        await process_pending_claims(
                            db,
                            str(lg["_id"]),
                            log_activity=log_activity,
                            broadcast=broadcast_to_room,
                        )
                    except Exception as ex:
                        logger.warning(
                            "waivers scheduler: league %s error: %s",
                            lg.get("_id"), ex,
                        )
            except Exception as e:
                logger.error(f"waivers scheduler error: {e}")
            await asyncio.sleep(60)
    asyncio.create_task(_waivers_scheduler_loop())

    # Iter 228d — Archived drafts sweeper (hard-delete after 15 days).
    # Iter 228f — Writes admin_user_actions audit rows BEFORE delete so
    # compliance has a record of every auto-purge.
    async def _archived_drafts_sweeper():
        from datetime import datetime as _dt, timedelta as _td, timezone as _tz
        while True:
            try:
                cutoff = _dt.now(_tz.utc) - _td(days=15)
                cutoff_iso = cutoff.isoformat()
                now_iso = _dt.now(_tz.utc).isoformat()
                # Snapshot expired drafts BEFORE deleting them so we can
                # write audit rows for each (the sweeper acts as the
                # "admin" — admin_id="__system__").
                expired = await db.drafts.find({
                    "status": "archived",
                    "archived_at": {"$lt": cutoff_iso},
                }, {"name": 1, "league_id": 1, "league_name": 1,
                    "archived_at": 1, "archived_by": 1, "total_rounds": 1,
                    "scheduled_time": 1}).to_list(500)
                for d in expired:
                    try:
                        league = await db.leagues.find_one(
                            {"_id": ObjectId(str(d.get("league_id")))},
                            {"commissioner_id": 1},
                        ) if d.get("league_id") else None
                    except Exception:
                        league = None
                    await db.admin_user_actions.insert_one({
                        "admin_id": "__system__",
                        "admin_email": "system@dynasty-sweeper",
                        "admin_tier": "system",
                        "target_user_id": (league or {}).get("commissioner_id"),
                        "action": "draft_auto_purge",
                        "reason": "15-day TTL elapsed (auto-purge sweeper)",
                        "metadata": {
                            "draft_id": str(d.get("_id")),
                            "draft_name": d.get("name"),
                            "league_id": d.get("league_id"),
                            "league_name": d.get("league_name"),
                            "archived_at": d.get("archived_at"),
                            "archived_by": d.get("archived_by"),
                            "total_rounds": d.get("total_rounds"),
                            "scheduled_time": d.get("scheduled_time"),
                        },
                        "prior_state": {"status": "archived"},
                        "mocked": False,
                        "ts": now_iso,
                    })
                res = await db.drafts.delete_many({
                    "status": "archived",
                    "archived_at": {"$lt": cutoff_iso},
                })
                if res.deleted_count:
                    logger.info(
                        f"archived-drafts sweeper: hard-deleted {res.deleted_count} draft(s) "
                        f"archived more than 15 days ago (audit rows written)"
                    )
            except Exception as e:
                logger.error(f"archived-drafts sweeper error: {e}")
            await asyncio.sleep(3600)  # hourly
    asyncio.create_task(_archived_drafts_sweeper())

    # Iter 228h — Monthly NHL Central Scouting auto-sync for the
    # upcoming draft year. Runs once per day; only triggers a fetch
    # on the 15th of each month to keep the upstream API happy.
    async def _draft_class_monthly_sync():
        import httpx
        from datetime import datetime as _dt, timezone as _tz
        CATEGORIES = [(1, "NA Skater"), (2, "INT Skater"), (3, "NA Goalie"), (4, "INT Goalie")]
        last_run_day: int | None = None
        while True:
            try:
                now = _dt.now(_tz.utc)
                if now.day == 15 and last_run_day != now.day:
                    # Sync the UPCOMING draft year (calendar Sept onwards = next year's draft)
                    target_year = now.year + 1 if now.month >= 9 else now.year
                    total_added = 0
                    async with httpx.AsyncClient(timeout=30.0) as client:
                        for cat_id, _ in CATEGORIES:
                            try:
                                r = await client.get(
                                    f"https://api-web.nhle.com/v1/draft/rankings/{target_year}/{cat_id}"
                                )
                                if r.status_code != 200:
                                    continue
                                rankings = (r.json() or {}).get("rankings") or []
                                import secrets
                                import re
                                for p in rankings:
                                    name = f"{(p.get('firstName') or '').strip()} {(p.get('lastName') or '').strip()}".strip()
                                    if not name:
                                        continue
                                    q: dict = {"name": {"$regex": f"^{re.escape(name)}$", "$options": "i"}}
                                    if p.get("birthDate"):
                                        q["date_of_birth"] = p.get("birthDate")
                                    if await db.players.find_one(q):
                                        continue
                                    position = (p.get("positionCode") or "").upper() or "C"
                                    await db.players.insert_one({
                                        "name": name,
                                        "position": position,
                                        "primary_position": position,
                                        "team": p.get("lastAmateurClub") or "",
                                        "league_status": "Draft Eligible",
                                        "player_type": "goalie" if cat_id >= 3 else "skater",
                                        "date_of_birth": p.get("birthDate"),
                                        "draft_year": target_year,
                                        "draft_rank_midterm": p.get("midtermRank"),
                                        "draft_rank_final": p.get("finalRank"),
                                        "shoots_catches": p.get("shootsCatches"),
                                        "height_inches": p.get("heightInInches"),
                                        "weight_pounds": p.get("weightInPounds"),
                                        "source": "nhl_central_scouting_auto",
                                        "nhl_id": 950_000_000 + secrets.randbelow(49_999_999),
                                        "created_at": now.isoformat(),
                                    })
                                    total_added += 1
                            except Exception as ex:
                                logger.warning(f"draft-class sync cat={cat_id} year={target_year}: {ex}")
                    if total_added:
                        logger.info(
                            f"draft-class monthly auto-sync: added {total_added} "
                            f"prospects for {target_year}"
                        )
                    last_run_day = now.day
                elif now.day != 15:
                    last_run_day = None
            except Exception as e:
                logger.error(f"draft-class monthly sync error: {e}")
            await asyncio.sleep(86400)  # daily check
    asyncio.create_task(_draft_class_monthly_sync())

    # Iter 230c — Notifications worker. Fires lineup_lock_reminder,
    # lineup_problem, and reminder_important on a 30-minute cadence.
    try:
        from services.notification_worker import notification_worker_loop
        asyncio.create_task(notification_worker_loop(db, create_notification))
    except Exception as e:
        logger.error(f"notification_worker failed to start: {e}")

    # Iter 230ao — Draft auto-start worker. Boots any draft whose
    # `scheduled_time` has elapsed but is still in `status: "scheduled"`
    # so the draft kicks off even when no manager has the room open.
    # Polls every 60s (short enough to fire within a minute of the
    # scheduled time, long enough not to thrash the DB).
    try:
        from services.draft_autostart_worker import draft_autostart_loop
        asyncio.create_task(draft_autostart_loop(db))
    except Exception as e:
        logger.error(f"draft_autostart_worker failed to start: {e}")

    # Iter 230ap — Trade-Block hygiene worker. Backfills missing names
    # on legacy trade_block rows (seed data inserted before the proper
    # /trade-block endpoint), prunes rows whose `player_id` no longer
    # resolves. Runs once at startup + every 6 hours.
    try:
        from services.trade_block_cleanup_worker import trade_block_cleanup_loop
        asyncio.create_task(trade_block_cleanup_loop(db))
    except Exception as e:
        logger.error(f"trade_block_cleanup_worker failed to start: {e}")

    # Iter 230e — NHL roster sync worker. Polls live NHL rosters every
    # 6h, routes diffs through the sync dispatcher so NHL ↔ AHL moves
    # auto-fire `player_sent_down` / `player_called_up` notifications
    # to every team that rosters the player.
    try:
        from services.nhl_roster_sync_worker import nhl_roster_sync_loop
        asyncio.create_task(nhl_roster_sync_loop(db, create_notification))
    except Exception as e:
        logger.error(f"nhl_roster_sync_worker failed to start: {e}")

    # Iter 230f — Injury news scraper. Pulls public NHL RSS feeds every
    # 15 min, matches headlines to rostered players, and dispatches
    # `player_injured` / `player_recovered` / `player_injury_status`
    # notifications via the shared NHL sync dispatcher pipeline.
    try:
        from services.injury_news_scraper import injury_news_loop
        asyncio.create_task(injury_news_loop(db, create_notification))
    except Exception as e:
        logger.error(f"injury_news_scraper failed to start: {e}")
    
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

    # Iter 175 — Daily NHL stats backfill so player ages / career-GP
    # (and the minor-eligibility flag derived from them) stay current
    # without manual ops intervention. Skipped under PYTEST_CURRENT_TEST
    # so unit tests don't bind to the public NHL endpoint.
    if not os.environ.get("PYTEST_CURRENT_TEST"):
        try:
            from player_data_backfill_worker import player_data_backfill_loop
            loop = asyncio.get_event_loop()
            fastapi_app.state.player_data_backfill_task = loop.create_task(
                player_data_backfill_loop(db)
            )
            logger.info("Player-data backfill worker scheduled (daily)")
        except Exception as e:
            logger.warning(f"Could not start player-data backfill worker: {e}")


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
    backfill_task = getattr(fastapi_app.state, "player_data_backfill_task", None)
    if backfill_task:
        backfill_task.cancel()
    client.close()

# Wrap FastAPI with Socket.IO
socket_app = socketio.ASGIApp(sio, other_asgi_app=fastapi_app, socketio_path='/api/socket.io')
app = socket_app
