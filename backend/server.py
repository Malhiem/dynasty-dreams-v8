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
from datetime import datetime, timezone, timedelta
from pydantic import BaseModel, Field, ConfigDict, EmailStr
from typing import List, Optional, Dict, Any
from enum import Enum

# Stripe Integration
from emergentintegrations.payments.stripe.checkout import (
    StripeCheckout, CheckoutSessionResponse, CheckoutStatusResponse, CheckoutSessionRequest
)

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
    name: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    id: str
    email: str
    name: str
    role: str
    created_at: datetime

class ForgotPassword(BaseModel):
    email: EmailStr

class ResetPassword(BaseModel):
    token: str
    new_password: str

class LeagueCreate(BaseModel):
    name: str
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
    format: str
    scoring_format: str
    max_teams: int
    current_teams: int
    commissioner_id: str
    commissioner_name: str
    salary_cap_enabled: bool
    salary_cap: Optional[float]
    draft_type: str
    roster_spots: int
    keepers_allowed: int
    entry_fee: Optional[float]
    is_private: bool
    status: str
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

class PaymentCreate(BaseModel):
    package_type: str  # "premium_monthly", "premium_yearly", "league_fee"
    league_id: Optional[str] = None
    origin_url: str

# Payment packages (server-side only)
PAYMENT_PACKAGES = {
    "premium_monthly": {"amount": 9.99, "name": "Premium Monthly"},
    "premium_yearly": {"amount": 79.99, "name": "Premium Yearly"},
    "league_fee": {"amount": 0.0, "name": "League Entry Fee"}  # Dynamic based on league
}

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
    existing = await db.users.find_one({"email": email})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    user_doc = {
        "email": email,
        "password_hash": hash_password(input.password),
        "name": input.name,
        "role": UserRole.USER.value,
        "subscription": None,
        "created_at": datetime.now(timezone.utc)
    }
    result = await db.users.insert_one(user_doc)
    user_id = str(result.inserted_id)
    
    access_token = create_access_token(user_id, email)
    refresh_token = create_refresh_token(user_id)
    
    response.set_cookie(key="access_token", value=access_token, httponly=True, secure=False, samesite="lax", max_age=900, path="/")
    response.set_cookie(key="refresh_token", value=refresh_token, httponly=True, secure=False, samesite="lax", max_age=604800, path="/")
    
    return UserResponse(
        id=user_id,
        email=email,
        name=input.name,
        role=UserRole.USER.value,
        created_at=user_doc["created_at"]
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
    
    response.set_cookie(key="access_token", value=access_token, httponly=True, secure=False, samesite="lax", max_age=900, path="/")
    response.set_cookie(key="refresh_token", value=refresh_token, httponly=True, secure=False, samesite="lax", max_age=604800, path="/")
    
    return UserResponse(
        id=user_id,
        email=user["email"],
        name=user["name"],
        role=user["role"],
        created_at=user["created_at"]
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
        name=user["name"],
        role=user["role"],
        created_at=user["created_at"]
    )

@api_router.post("/auth/refresh")
async def refresh_token(request: Request, response: Response):
    token = request.cookies.get("refresh_token")
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
        response.set_cookie(key="access_token", value=access_token, httponly=True, secure=False, samesite="lax", max_age=900, path="/")
        return {"message": "Token refreshed"}
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
        "invite_code": secrets.token_urlsafe(8) if input.is_private else None,
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
        format=league_doc["format"],
        scoring_format=league_doc["scoring_format"],
        max_teams=league_doc["max_teams"],
        current_teams=0,
        commissioner_id=league_doc["commissioner_id"],
        commissioner_name=league_doc["commissioner_name"],
        salary_cap_enabled=league_doc["salary_cap_enabled"],
        salary_cap=league_doc["salary_cap"],
        draft_type=league_doc["draft_type"],
        roster_spots=league_doc["roster_spots"],
        keepers_allowed=league_doc["keepers_allowed"],
        entry_fee=league_doc["entry_fee"],
        is_private=league_doc["is_private"],
        status=league_doc["status"],
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
            format=league["format"],
            scoring_format=league["scoring_format"],
            max_teams=league["max_teams"],
            current_teams=league.get("current_teams", 0),
            commissioner_id=league["commissioner_id"],
            commissioner_name=league["commissioner_name"],
            salary_cap_enabled=league["salary_cap_enabled"],
            salary_cap=league.get("salary_cap"),
            draft_type=league["draft_type"],
            roster_spots=league["roster_spots"],
            keepers_allowed=league["keepers_allowed"],
            entry_fee=league.get("entry_fee"),
            is_private=league["is_private"],
            status=league["status"],
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
        format=league["format"],
        scoring_format=league["scoring_format"],
        max_teams=league["max_teams"],
        current_teams=league.get("current_teams", 0),
        commissioner_id=league["commissioner_id"],
        commissioner_name=league["commissioner_name"],
        salary_cap_enabled=league["salary_cap_enabled"],
        salary_cap=league.get("salary_cap"),
        draft_type=league["draft_type"],
        roster_spots=league["roster_spots"],
        keepers_allowed=league["keepers_allowed"],
        entry_fee=league.get("entry_fee"),
        is_private=league["is_private"],
        status=league["status"],
        created_at=league["created_at"]
    )

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
    
    teams = await db.teams.find(query).to_list(100)
    return [
        TeamResponse(
            id=str(team["_id"]),
            name=team["name"],
            league_id=team["league_id"],
            owner_id=team["owner_id"],
            owner_name=team["owner_name"],
            salary_used=team.get("salary_used", 0.0),
            wins=team.get("wins", 0),
            losses=team.get("losses", 0),
            ties=team.get("ties", 0),
            points_for=team.get("points_for", 0.0),
            points_against=team.get("points_against", 0.0),
            created_at=team["created_at"]
        )
        for team in teams
    ]

@api_router.get("/teams/{team_id}", response_model=TeamResponse)
async def get_team(team_id: str):
    team = await db.teams.find_one({"_id": ObjectId(team_id)})
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    
    return TeamResponse(
        id=str(team["_id"]),
        name=team["name"],
        league_id=team["league_id"],
        owner_id=team["owner_id"],
        owner_name=team["owner_name"],
        salary_used=team.get("salary_used", 0.0),
        wins=team.get("wins", 0),
        losses=team.get("losses", 0),
        ties=team.get("ties", 0),
        points_for=team.get("points_for", 0.0),
        points_against=team.get("points_against", 0.0),
        created_at=team["created_at"]
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
# Trade Center Endpoints
# ═══════════════════════════════════════════════════════════════
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
    query = {}
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

    await broadcast_to_room(f"league_{trade['league_id']}", "trade_accepted", {
        "trade_id": trade_id,
        "proposer": trade["proposer_team_name"],
        "target": trade["target_team_name"]
    })

    return {"message": "Trade accepted", "status": "accepted"}

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


async def create_checkout(input: PaymentCreate, request: Request):
    user = await get_current_user(request)
    
    if input.package_type not in PAYMENT_PACKAGES:
        raise HTTPException(status_code=400, detail="Invalid package type")
    
    package = PAYMENT_PACKAGES[input.package_type]
    amount = package["amount"]
    
    # For league fees, get amount from league
    if input.package_type == "league_fee" and input.league_id:
        league = await db.leagues.find_one({"_id": ObjectId(input.league_id)})
        if not league or not league.get("entry_fee"):
            raise HTTPException(status_code=400, detail="League has no entry fee")
        amount = float(league["entry_fee"])
    
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
    
    # Check with Stripe
    api_key = os.environ.get("STRIPE_API_KEY")
    webhook_url = f"{str(request.base_url).rstrip('/')}/api/webhook/stripe"
    stripe_checkout = StripeCheckout(api_key=api_key, webhook_url=webhook_url)
    
    status = await stripe_checkout.get_checkout_status(session_id)
    
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
import random as _random
import itertools


def generate_round_robin(team_ids):
    """Generate a full round-robin schedule. Returns list of rounds, each a list of (home, away) tuples."""
    teams = list(team_ids)
    if len(teams) % 2 == 1:
        teams.append(None)  # bye
    n = len(teams)
    schedule = []
    for r in range(n - 1):
        round_matchups = []
        for i in range(n // 2):
            home = teams[i]
            away = teams[n - 1 - i]
            if home is not None and away is not None:
                round_matchups.append((home, away))
        schedule.append(round_matchups)
        teams.insert(1, teams.pop())
    return schedule


class GenerateScheduleRequest(BaseModel):
    league_id: str
    num_weeks: int = Field(default=18, ge=1, le=52)


class SimulateWeekRequest(BaseModel):
    league_id: str
    week: int


@api_router.post("/matchups/generate-schedule")
async def generate_schedule(input: GenerateScheduleRequest, request: Request):
    """Commissioner generates the full season schedule."""
    user = await get_current_user(request)
    league = await db.leagues.find_one({"_id": ObjectId(input.league_id)})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    if league["commissioner_id"] != user["_id"]:
        raise HTTPException(status_code=403, detail="Only commissioner can generate schedule")

    teams = await db.teams.find({"league_id": input.league_id}).to_list(100)
    if len(teams) < 2:
        raise HTTPException(status_code=400, detail="Need at least 2 teams")

    team_ids = [str(t["_id"]) for t in teams]
    team_map = {str(t["_id"]): t["name"] for t in teams}

    scoring_format = league.get("scoring_format", "head_to_head")

    # Generate round-robin and repeat to fill weeks
    base_schedule = generate_round_robin(team_ids)
    full_schedule = []
    week = 1
    cycle = itertools.cycle(base_schedule)
    while week <= input.num_weeks:
        round_matchups = next(cycle)
        _random.shuffle(round_matchups)
        matchups = []
        for home_id, away_id in round_matchups:
            matchups.append({
                "week": week,
                "home_team_id": home_id,
                "home_team_name": team_map.get(home_id, ""),
                "away_team_id": away_id,
                "away_team_name": team_map.get(away_id, ""),
                "home_score": 0,
                "away_score": 0,
                "status": "scheduled",
                "winner": None
            })
        full_schedule.extend(matchups)
        week += 1

    # Clear existing and save
    await db.matchups.delete_many({"league_id": input.league_id})
    if full_schedule:
        for m in full_schedule:
            m["league_id"] = input.league_id
            m["scoring_format"] = scoring_format
        await db.matchups.insert_many(full_schedule)

    return {"message": f"Generated {len(full_schedule)} matchups for {input.num_weeks} weeks", "weeks": input.num_weeks}


@api_router.get("/matchups/{league_id}")
async def get_matchups(league_id: str, week: Optional[int] = None):
    query = {"league_id": league_id}
    if week:
        query["week"] = week
    matchups = await db.matchups.find(query).sort("week", 1).to_list(1000)
    for m in matchups:
        m["_id"] = str(m["_id"])
    return matchups


@api_router.get("/matchups/{league_id}/current-week")
async def get_current_week(league_id: str):
    # Find the latest unplayed week
    pipeline = [
        {"$match": {"league_id": league_id, "status": "scheduled"}},
        {"$group": {"_id": None, "min_week": {"$min": "$week"}}},
    ]
    result = await db.matchups.aggregate(pipeline).to_list(1)
    current = result[0]["min_week"] if result else 1
    matchups = await db.matchups.find({"league_id": league_id, "week": current}).to_list(100)
    for m in matchups:
        m["_id"] = str(m["_id"])
    return {"week": current, "matchups": matchups}


@api_router.post("/matchups/simulate-week")
async def simulate_week(input: SimulateWeekRequest, request: Request):
    """Simulate a week's matchups using roster fantasy points."""
    user = await get_current_user(request)
    league = await db.leagues.find_one({"_id": ObjectId(input.league_id)})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    if league["commissioner_id"] != user["_id"]:
        raise HTTPException(status_code=403, detail="Only commissioner can simulate")

    matchups = await db.matchups.find({
        "league_id": input.league_id,
        "week": input.week,
        "status": "scheduled"
    }).to_list(100)

    if not matchups:
        raise HTTPException(status_code=400, detail="No scheduled matchups for this week")

    config = await db.scoring_configs.find_one({"league_id": input.league_id})
    scoring_format = league.get("scoring_format", "head_to_head")

    # Calculate each team's score from their roster
    async def calc_team_score(team_id):
        team = await db.teams.find_one({"_id": ObjectId(team_id)})
        if not team:
            return 0.0
        roster = team.get("roster", [])
        total = 0.0
        for pid in roster:
            player = await db.players.find_one({"_id": ObjectId(pid)})
            if player:
                total += calculate_fantasy_points(player, config)
        return round(total, 1)

    results = []
    for m in matchups:
        home_score = await calc_team_score(m["home_team_id"])
        away_score = await calc_team_score(m["away_team_id"])

        winner = None
        if home_score > away_score:
            winner = m["home_team_id"]
        elif away_score > home_score:
            winner = m["away_team_id"]

        await db.matchups.update_one(
            {"_id": m["_id"]},
            {"$set": {
                "home_score": home_score,
                "away_score": away_score,
                "winner": winner,
                "status": "completed",
                "simulated_at": datetime.now(timezone.utc).isoformat()
            }}
        )

        # Update team records
        if winner == m["home_team_id"]:
            await db.teams.update_one({"_id": ObjectId(m["home_team_id"])}, {"$inc": {"wins": 1, "points_for": home_score, "points_against": away_score}})
            await db.teams.update_one({"_id": ObjectId(m["away_team_id"])}, {"$inc": {"losses": 1, "points_for": away_score, "points_against": home_score}})
        elif winner == m["away_team_id"]:
            await db.teams.update_one({"_id": ObjectId(m["away_team_id"])}, {"$inc": {"wins": 1, "points_for": away_score, "points_against": home_score}})
            await db.teams.update_one({"_id": ObjectId(m["home_team_id"])}, {"$inc": {"losses": 1, "points_for": home_score, "points_against": away_score}})
        else:
            # Tie
            await db.teams.update_one({"_id": ObjectId(m["home_team_id"])}, {"$inc": {"ties": 1, "points_for": home_score, "points_against": away_score}})
            await db.teams.update_one({"_id": ObjectId(m["away_team_id"])}, {"$inc": {"ties": 1, "points_for": away_score, "points_against": home_score}})

        results.append({
            "home": m["home_team_name"],
            "away": m["away_team_name"],
            "home_score": home_score,
            "away_score": away_score,
            "winner": m["home_team_name"] if winner == m["home_team_id"] else m["away_team_name"] if winner else "Tie"
        })

    # For All-Play: every team plays every other team (calculated separately)
    if scoring_format == "all_play":
        all_teams = await db.teams.find({"league_id": input.league_id}).to_list(100)
        scores = {}
        for t in all_teams:
            scores[str(t["_id"])] = await calc_team_score(str(t["_id"]))

        for team_id, score in scores.items():
            ap_wins = sum(1 for oid, oscore in scores.items() if oid != team_id and score > oscore)
            ap_losses = sum(1 for oid, oscore in scores.items() if oid != team_id and score < oscore)
            await db.teams.update_one(
                {"_id": ObjectId(team_id)},
                {"$inc": {"wins": ap_wins, "losses": ap_losses}}
            )

    # For Guillotine: find lowest scorer and mark eliminated
    if scoring_format == "guillotine":
        all_teams = await db.teams.find({"league_id": input.league_id, "eliminated": {"$ne": True}}).to_list(100)
        scores = []
        for t in all_teams:
            s = await calc_team_score(str(t["_id"]))
            scores.append((str(t["_id"]), t["name"], s))
        if scores:
            scores.sort(key=lambda x: x[2])
            eliminated = scores[0]
            await db.teams.update_one({"_id": ObjectId(eliminated[0])}, {"$set": {"eliminated": True}})
            results.append({"eliminated": eliminated[1], "score": eliminated[2]})

    await broadcast_to_room(f"league_{input.league_id}", "week_simulated", {
        "week": input.week,
        "results": results
    })

    return {"week": input.week, "results": results, "matchups_simulated": len(matchups)}


@api_router.get("/matchups/{league_id}/results")
async def get_week_results(league_id: str, week: int):
    matchups = await db.matchups.find({
        "league_id": league_id,
        "week": week
    }).to_list(100)
    for m in matchups:
        m["_id"] = str(m["_id"])
    return matchups

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

@fastapi_app.on_event("shutdown")
async def shutdown():
    client.close()

# Wrap FastAPI with Socket.IO
socket_app = socketio.ASGIApp(sio, other_asgi_app=fastapi_app, socketio_path='/api/socket.io')
app = socket_app
