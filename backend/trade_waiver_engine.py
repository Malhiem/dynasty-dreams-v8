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
    pick_id: Optional[str] = None  # ObjectId of draft_picks row
    league_id: Optional[str] = None
    team_id: Optional[str] = None
    note: Optional[str] = None


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
    # For multi-party trades: which team this asset is being sent TO.
    # When omitted (legacy 2-party trade), the engine routes to the other party.
    to_team_id: Optional[str] = None


class TradePartyInput(BaseModel):
    """One team's role in a multi-party trade.
    `sends` are assets this team gives up; `receives` are assets it gets."""
    team_id: str
    sends: list[TradeAsset] = Field(default_factory=list)
    receives: list[TradeAsset] = Field(default_factory=list)


class MultiPartyTradeProposalCreate(BaseModel):
    league_id: str
    parties: list[TradePartyInput] = Field(min_length=2)
    message: Optional[str] = None
    conditions: list["TradeCondition"] = Field(default_factory=list)
    pick_upgrades: list["TradePickUpgrade"] = Field(default_factory=list)


class TradePartyResponse(BaseModel):
    action: str  # "accept" | "reject"


class TradeConditionMetric(str, Enum):
    # Player-level metrics
    FANTASY_POINTS = "fantasy_points"
    NHL_POINTS = "nhl_points"
    NHL_GOALS = "nhl_goals"
    NHL_ASSISTS = "nhl_assists"
    NHL_WINS = "nhl_wins"
    GAMES_PLAYED = "games_played"
    LIVE_FANTASY_POINTS = "live_fantasy_points"
    # Team-level metrics (dynasty hooks)
    TEAM_WINS = "team_wins"
    TEAM_LOSSES = "team_losses"
    TEAM_POINTS_FOR = "team_points_for"
    TEAM_RANK = "team_rank"
    MADE_PLAYOFFS = "made_playoffs"   # 1 if playoffs_reached_at set
    WON_DIVISION = "won_division"     # 1 if division_winner_at set
    WON_CHAMPIONSHIP = "won_championship"  # 1 if championship_won_at set


class TradeCondition(BaseModel):
    subject_type: str = "player"   # "player" | "team"
    subject: str = "offered"       # "offered" | "requested" — which side the condition attaches to
    player_id: Optional[str] = None  # When subject_type == player
    team_id: Optional[str] = None    # When subject_type == team. If None, resolves to that side's team.
    metric: TradeConditionMetric
    operator: str = "gte"  # "gte" | "lte" | "eq"
    threshold: float
    by_date: Optional[str] = None  # Evaluate by this date (ISO)
    description: Optional[str] = None  # Free-form label, e.g. "If team wins championship"


class TradePickUpgrade(BaseModel):
    """Outcome-modifying conditional. When `condition` evaluates true, the
    named pick is rewritten to `new_round` (and optionally `new_year`).
    Supports upgrades (round → lower) and downgrades (round → higher)."""
    pick_id: str
    new_round: int = Field(ge=1, le=10)
    new_year: Optional[int] = None
    condition: TradeCondition
    description: Optional[str] = None


class TradeProposalCreate(BaseModel):
    league_id: str
    target_team_id: str
    assets_offered: list[TradeAsset]
    assets_requested: list[TradeAsset]
    message: Optional[str] = None
    conditions: list[TradeCondition] = Field(default_factory=list)
    pick_upgrades: list[TradePickUpgrade] = Field(default_factory=list)


# Resolve forward references now that TradeCondition + TradePickUpgrade are defined
MultiPartyTradeProposalCreate.model_rebuild()


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
