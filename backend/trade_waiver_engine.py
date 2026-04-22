"""
Trade & Waiver Wire Engine for Dynasty Dreams.
Handles trade proposals, voting, processing, trade block,
FAAB waivers, claims, and waiver order.
"""
from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


# ─── Trade Models ────────────────────────────────────────────

class TradeStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    VETOED = "vetoed"
    WITHDRAWN = "withdrawn"
    PROCESSED = "processed"


class TradeAssetType(str, Enum):
    PLAYER = "player"
    PICK = "pick"


class TradeBlockItemCreate(BaseModel):
    player_id: Optional[str] = None
    item_type: str = "player"  # player, pick
    looking_for: list[str] = Field(default_factory=list)
    pick_year: Optional[int] = None
    pick_round: Optional[str] = None


class TradeBlockItemRemove(BaseModel):
    item_id: str


class TradeAsset(BaseModel):
    asset_type: str  # "player" or "pick"
    player_id: Optional[str] = None
    player_name: Optional[str] = None
    position: Optional[str] = None
    nhl_team: Optional[str] = None
    pick_year: Optional[int] = None
    pick_round: Optional[str] = None
    pick_id: Optional[str] = None  # ObjectId of the draft_pick row when trading a specific pick
    salary_retained_pct: float = 0


class TradeConditionMetric(str, Enum):
    FANTASY_POINTS = "fantasy_points"
    NHL_POINTS = "nhl_points"
    NHL_GOALS = "nhl_goals"
    NHL_ASSISTS = "nhl_assists"
    NHL_WINS = "nhl_wins"
    GAMES_PLAYED = "games_played"
    LIVE_FANTASY_POINTS = "live_fantasy_points"


class TradeCondition(BaseModel):
    subject: str = "offered"  # "offered" or "requested" — which side the condition applies to
    player_id: Optional[str] = None  # Specific asset; if None, applies to any asset on that side
    metric: TradeConditionMetric
    operator: str = "gte"  # "gte" | "lte" | "eq"
    threshold: float
    by_date: Optional[str] = None  # ISO date string; evaluate by this date (optional)
    description: Optional[str] = None  # Human-readable, e.g. "If McDavid scores 100+ pts by trade deadline"


class TradeProposalCreate(BaseModel):
    league_id: str
    target_team_id: str
    assets_offered: list[TradeAsset]
    assets_requested: list[TradeAsset]
    message: Optional[str] = None
    conditions: list[TradeCondition] = Field(default_factory=list)


class TradeVote(BaseModel):
    vote: str  # "approve" or "veto"


# ─── Waiver Models ────────────────────────────────────────────

class WaiverClaimCreate(BaseModel):
    league_id: str
    player_id: str
    bid_amount: float = Field(ge=0)
    drop_player_id: Optional[str] = None


class WaiverClaimCancel(BaseModel):
    claim_id: str
