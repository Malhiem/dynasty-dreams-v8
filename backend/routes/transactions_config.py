"""League → Transactions configuration (iter 117).

Endpoints
---------
GET  /api/leagues/{id}/transactions-config
    Returns the league's full Transactions config (claims limits, claim
    rules, free-agency, waiver, draft).
PUT  /api/leagues/{id}/transactions-config
    Commissioner-only. Sparse update — only provided keys are written.
GET  /api/teams/{team_id}/claim-counts
    Returns the requesting user's claim totals (season + week) for this
    team, scoped by the league's `claim_rules.pending_visibility` /
    `failed_visibility` settings:
      • user        — only the team owner sees the chip
      • all_teams   — any league member can see it
      • league_admin — only commissioners + co-commissioners can see it

The actual ENFORCEMENT (rejecting claims when caps are hit) lives in
`routes/waivers.py` + `routes/roster.py`; this module is purely config +
read-side surface for the UI.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List, Literal, Optional

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, ConfigDict


router = APIRouter()
_deps: dict = {}


def setup(deps: dict) -> None:
    _deps.update(deps)


def _db(): return _deps["db"]
async def _get_user(request): return await _deps["get_current_user"](request)


# ─── Pydantic models ─────────────────────────────────────────────────

class ClaimLimitsBucket(BaseModel):
    """`None` for any field means UNLIMITED."""
    total: Optional[int] = Field(default=None, ge=0, le=1000)
    fa: Optional[int] = Field(default=None, ge=0, le=1000)
    waivers: Optional[int] = Field(default=None, ge=0, le=1000)


class ClaimLimits(BaseModel):
    season: ClaimLimitsBucket = Field(default_factory=ClaimLimitsBucket)
    week: ClaimLimitsBucket = Field(default_factory=ClaimLimitsBucket)


InjuredPolicy = Literal["off", "any", "nhl_ir", "all_flags"]
Visibility = Literal["user", "all_teams", "league_admin"]
FreeAgentSystem = Literal["open", "auto_priority", "manual_priority", "bidding"]
AutoPriorityBasis = Literal["reverse_live", "reverse_prev", "random", "manual"]
ManualPriorityDuration = Literal["one_off", "month", "three_month", "season"]
PicksPerRoundPolicy = Literal["top_then_next", "all_then_next"]
WaiverProcessingMode = Literal["days", "scheduled"]
PriorityRecomputeCadence = Literal["live", "weekly"]


class ClaimRules(BaseModel):
    lock_at_first_game: bool = False
    allow_non_playoff_teams_claims: bool = True
    prevent_injured: InjuredPolicy = "off"
    prevent_minors: bool = False
    pending_visibility: Visibility = "user"
    failed_visibility: Visibility = "user"


class ManualPrioritySchedule(BaseModel):
    """One row in the LM's scheduled rotation. `team_order` is the priority
    order during this window (highest-priority team first). When you only
    need a single one-off list, supply one row with `from`/`to` covering the
    league's active season."""
    model_config = ConfigDict(populate_by_name=True)
    starts_on: str  # ISO date — inclusive
    ends_on: str    # ISO date — inclusive
    team_order: List[str]  # team_ids in priority order


class FreeAgency(BaseModel):
    system_type: FreeAgentSystem = "open"
    # Auto priority
    auto_priority_basis: AutoPriorityBasis = "reverse_live"
    priority_recompute_cadence: PriorityRecomputeCadence = "live"
    # Manual priority
    manual_priority_duration: ManualPriorityDuration = "one_off"
    manual_priority_order: List[str] = Field(default_factory=list)  # team_ids
    manual_priority_schedule: List[ManualPrioritySchedule] = Field(default_factory=list)
    # Waiver wire claim policy (governs how many players a winning team
    # gets per claim cycle).
    picks_per_round_policy: PicksPerRoundPolicy = "top_then_next"
    waivers_reset_after_claim: bool = False


class WaiverProcessingSchedule(BaseModel):
    """One slot for the LM's processing schedule. `day_of_week` is 0-6 with
    0 = Monday (ISO weekday convention). `time` is a 24h "HH:MM" string in
    league-local time."""
    day_of_week: int = Field(ge=0, le=6)
    time: str  # "HH:MM"


WaiverVisibility = Literal["own", "all_teams", "all_teams_anonymous", "league_admin"]
WaiverInjuredPolicy = Literal["off", "nhl_ir", "all_flags"]
WaiverSystemType = Literal["auto_priority"]
WaiverPriorityOrder = Literal[
    "reverse_standings_serpentine",
    "reverse_standings",
    "manual",
    "random",
]


class WaiverClaimLimits(BaseModel):
    """Waiver-section per-Setting claim caps (applied when waiver.enabled).
    Each null = Unlimited; otherwise 1-500. Validation: FA and Waivers must
    not exceed Total when Total is finite."""
    total: Optional[int] = Field(default=None, ge=1, le=500)
    fa: Optional[int] = Field(default=None, ge=1, le=500)
    waivers: Optional[int] = Field(default=None, ge=1, le=500)


class WaiverConfig(BaseModel):
    enabled: bool = False  # master toggle — separates waiver from FA rules
    # Iter 120 — Waiver Wire System (currently only Automated Priority
    # Order; future-extensible if we add bidding/FAAB-mode tied to waivers).
    system_type: WaiverSystemType = "auto_priority"
    priority_order: WaiverPriorityOrder = "reverse_standings_serpentine"
    # Manual ordering when priority_order = "manual". team_ids in priority
    # order, highest first. Server validates ids belong to this league.
    manual_priority_order: List[str] = Field(default_factory=list)

    processing_mode: WaiverProcessingMode = "days"
    processing_days_count: int = Field(default=2, ge=0, le=7)
    processing_schedule: List[WaiverProcessingSchedule] = Field(default_factory=list)
    abuse_window_enabled: bool = False
    abuse_window_days: int = Field(default=3, ge=1, le=7)
    # ── Iter 119 — waiver-section-specific overrides ──
    claim_limits: WaiverClaimLimits = Field(default_factory=WaiverClaimLimits)
    prevent_injured: WaiverInjuredPolicy = "off"
    prevent_minors: bool = False
    prevent_prospects: bool = False
    pending_visibility: WaiverVisibility = "own"
    failed_visibility: WaiverVisibility = "own"
    force_drop_on_claim: bool = False
    force_claim_on_drop: bool = False


class DraftClaimRules(BaseModel):
    allow_claims_before_draft: bool = False
    allow_drops_during_draft: bool = False


class TransactionsConfig(BaseModel):
    """Full envelope returned by GET / accepted by PUT."""
    claim_limits: ClaimLimits = Field(default_factory=ClaimLimits)
    claim_rules: ClaimRules = Field(default_factory=ClaimRules)
    free_agency: FreeAgency = Field(default_factory=FreeAgency)
    waiver: WaiverConfig = Field(default_factory=WaiverConfig)
    draft_claims: DraftClaimRules = Field(default_factory=DraftClaimRules)


# ─── Helpers ─────────────────────────────────────────────────────────


def _is_commissioner(league: dict, user: dict) -> bool:
    return (
        league.get("commissioner_id") == user["_id"]
        or user["_id"] in (league.get("co_commissioners") or [])
    )


def _load_config(league: dict) -> dict:
    """Merge stored fields with defaults so the UI always gets a complete
    object even on freshly-created leagues."""
    stored = league.get("transactions_config") or {}
    merged = TransactionsConfig(**stored).model_dump()
    return merged


def _validate_manual_priority(cfg: dict, team_ids_in_league: set[str]) -> None:
    """If manual priority is selected, every team_id referenced must belong
    to this league. Empty lists are allowed — the UI shows a "drag teams in"
    empty state until the LM populates the order."""
    fa = cfg.get("free_agency") or {}
    if fa.get("system_type") != "manual_priority":
        return
    bad = [tid for tid in (fa.get("manual_priority_order") or [])
           if tid not in team_ids_in_league]
    if bad:
        raise HTTPException(status_code=400,
                            detail=f"manual_priority_order has team_ids not in this league: {bad}")
    for slot in (fa.get("manual_priority_schedule") or []):
        bad = [tid for tid in (slot.get("team_order") or [])
               if tid not in team_ids_in_league]
        if bad:
            raise HTTPException(status_code=400,
                                detail=f"manual_priority_schedule team_order has unknown team_ids: {bad}")


def _validate_waiver_claim_limits(cfg: dict) -> None:
    """Per the iter 119 spec: when waiver-section claim caps are set, FA
    and Waiver buckets must not exceed Total (when Total is finite). The
    UI also flags this inline but the API is the contract-of-record."""
    w = cfg.get("waiver") or {}
    if not w.get("enabled"):
        return
    lim = w.get("claim_limits") or {}
    total = lim.get("total")
    if total is None:
        return  # Total is unlimited, no constraint
    fa = lim.get("fa")
    wv = lim.get("waivers")
    if fa is not None and fa > total:
        raise HTTPException(status_code=400,
                            detail=f"Waiver claim limits: Free Agency cap ({fa}) exceeds Total cap ({total}).")
    if wv is not None and wv > total:
        raise HTTPException(status_code=400,
                            detail=f"Waiver claim limits: Waiver Wire cap ({wv}) exceeds Total cap ({total}).")


def _validate_waiver_manual_priority(cfg: dict, team_ids_in_league: set[str]) -> None:
    """When the Waivers section uses Manual priority order, every team_id
    referenced must belong to this league."""
    w = cfg.get("waiver") or {}
    if not w.get("enabled"):
        return
    if w.get("priority_order") != "manual":
        return
    bad = [tid for tid in (w.get("manual_priority_order") or [])
           if tid not in team_ids_in_league]
    if bad:
        raise HTTPException(status_code=400,
                            detail=f"waiver.manual_priority_order has team_ids not in this league: {bad}")


# ─── Endpoints ───────────────────────────────────────────────────────


@router.get("/leagues/{league_id}/transactions-config")
async def get_transactions_config(league_id: str, request: Request):
    db = _db()
    await _get_user(request)
    try:
        league = await db.leagues.find_one({"_id": ObjectId(league_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid league_id")
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    return _load_config(league)


@router.put("/leagues/{league_id}/transactions-config")
async def update_transactions_config(league_id: str, payload: TransactionsConfig, request: Request):
    db = _db()
    user = await _get_user(request)
    try:
        league = await db.leagues.find_one({"_id": ObjectId(league_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid league_id")
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    if not _is_commissioner(league, user):
        raise HTTPException(status_code=403, detail="Commissioner only")

    # Per-team membership validation (manual priority can only reference
    # teams that are actually in this league).
    teams = await db.teams.find({"league_id": league_id}, {"_id": 1}).to_list(60)
    team_ids = {str(t["_id"]) for t in teams}
    cfg_dict = payload.model_dump()
    _validate_manual_priority(cfg_dict, team_ids)
    _validate_waiver_claim_limits(cfg_dict)
    _validate_waiver_manual_priority(cfg_dict, team_ids)

    await db.leagues.update_one(
        {"_id": ObjectId(league_id)},
        {"$set": {"transactions_config": cfg_dict,
                  "transactions_config_updated_at": datetime.now(timezone.utc)}},
    )

    # Audit-log entry (best-effort).
    try:
        await db.audit_log.insert_one({
            "league_id": league_id,
            "actor_id": user["_id"],
            "actor_email": user.get("email"),
            "action": "transactions_config_updated",
            "description": "Transactions configuration updated",
            "created_at": datetime.now(timezone.utc),
        })
    except Exception:
        pass

    return cfg_dict


@router.get("/teams/{team_id}/claim-counts")
async def get_team_claim_counts(team_id: str, request: Request):
    """Returns the calling user's view of the team's claim counts:

    {
      "visible": bool,
      "audience": "user" | "all_teams" | "league_admin",
      "season": {"total": int, "fa": int, "waivers": int},
      "week": {"total": int, "fa": int, "waivers": int},
      "limits": ClaimLimits,
    }

    `visible` is false (and `season`/`week` are zeroed out) when the
    requesting user is NOT entitled to see the team's counts under the
    league's `claim_rules.pending_visibility` setting.
    """
    db = _db()
    user = await _get_user(request)
    try:
        team = await db.teams.find_one({"_id": ObjectId(team_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid team_id")
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    league = await db.leagues.find_one({"_id": ObjectId(team["league_id"])})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    cfg = _load_config(league)
    rules = cfg["claim_rules"]
    audience = rules.get("pending_visibility") or "user"

    is_owner = team.get("owner_id") == user["_id"]
    is_comm = _is_commissioner(league, user)
    if audience == "user":
        visible = is_owner or is_comm
    elif audience == "all_teams":
        # Any league member counts. We assume a logged-in user with a team
        # in the league qualifies; otherwise treat as no-access.
        own_team = await db.teams.find_one({"league_id": team["league_id"], "owner_id": user["_id"]})
        visible = bool(own_team) or is_comm
    else:  # "league_admin"
        visible = is_comm

    if not visible:
        return {
            "visible": False,
            "audience": audience,
            "season": {"total": 0, "fa": 0, "waivers": 0},
            "week": {"total": 0, "fa": 0, "waivers": 0},
            "limits": cfg["claim_limits"],
        }

    # Count claims for current season + current week.
    season = league.get("season") or "2025-2026"
    current_week = int(league.get("current_week") or 1)
    base_q = {"team_id": team_id, "season": season}
    week_q = {**base_q, "week": current_week}

    async def _count(q):
        # `tx_kind` ∈ {fa, waiver}. Activity rows from /api/activity also
        # work but waiver_claims is the single source of truth for claim
        # counters; roster_adds drive FA counts.
        try:
            fa = await db.activity_feed.count_documents({
                **{k: v for k, v in q.items() if k != "team_id"},
                "metadata.team_id": team_id,
                "event_type": {"$in": ["roster_add"]},
            })
        except Exception:
            fa = 0
        try:
            wv = await db.waiver_claims.count_documents({
                **q, "status": {"$in": ["won", "lost", "pending"]},
            })
        except Exception:
            wv = 0
        return fa, wv, fa + wv

    s_fa, s_wv, s_total = await _count(base_q)
    w_fa, w_wv, w_total = await _count(week_q)

    return {
        "visible": True,
        "audience": audience,
        "season": {"total": s_total, "fa": s_fa, "waivers": s_wv},
        "week": {"total": w_total, "fa": w_fa, "waivers": w_wv},
        "limits": cfg["claim_limits"],
    }
