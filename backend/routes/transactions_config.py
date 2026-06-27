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
WaiverSystemType = Literal["auto_priority", "faab"]
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
    # ── Iter 126 — FAAB system settings ──
    # Surface when system_type == "faab". Per-team budget + clearing period.
    # `processing_days_count` continues to drive the clearing window for
    # both auto_priority and faab systems so existing UI bindings still
    # work end-to-end.
    faab_budget: int = Field(default=100, ge=0, le=10000)


class DraftClaimRules(BaseModel):
    allow_claims_before_draft: bool = False
    allow_drops_during_draft: bool = False


# Iter 231g — Trades configuration. Surfaces every knob the user
# requested under League Administration → Transactions → Trades. Read
# by `routes/trades.py` (state machine, voting, eligibility checks).
# Legacy `league.trade_review_period_hours` / `trade_veto_threshold_pct`
# top-level fields are kept for backward compat but the trade engine now
# prefers `transactions_config.trades.*` when present.

TradeVotingSystem = Literal["managers", "commissioners", "both"]


class TradesConfig(BaseModel):
    # Review window (proposer ↔ recipient ↔ league). Hours.
    review_period_hours: int = Field(default=72, ge=0, le=336)  # 0–14 days
    # NUMBER of teams that must vote No to veto (replaces the old % field).
    # Multiple owners of the same team still count as one vote.
    veto_threshold_teams: int = Field(default=4, ge=0, le=50)
    # Cap on simultaneously pending + completed trades per team per season.
    # `None` = unlimited.
    max_trades_per_team: Optional[int] = Field(default=None, ge=1, le=50)
    # Voting roster — who can cast vetoes.
    voting_system: TradeVotingSystem = "managers"
    # If true, vote counts (per side) are shown but individual ballots
    # are not attributed publicly. Commissioners always see the roster.
    anonymous_voting: bool = True
    # Lock trades at the moment the first NHL game of the day starts
    # (mirrors waiver lock behaviour).
    lock_at_first_game: bool = False
    # Draft-window allowances.
    allow_before_draft: bool = True
    allow_during_draft: bool = False
    # If false, the trade engine rejects executions that would leave
    # either roster in an illegal state (too few skaters, over cap, etc).
    allow_illegal_rosters: bool = False
    # If true, the comments thread on a pending trade is visible to every
    # league manager (gossip mode). Otherwise only the two trading teams
    # + commissioners see it.
    comments_visible_to_all: bool = False
    # Master toggle for conditional trades (player A if team X makes
    # playoffs, etc.). Engine support shipped iter 211; this flag
    # controls whether managers can author them.
    conditional_trades_enabled: bool = False


class TransactionsConfig(BaseModel):
    """Full envelope returned by GET / accepted by PUT."""
    claim_limits: ClaimLimits = Field(default_factory=ClaimLimits)
    claim_rules: ClaimRules = Field(default_factory=ClaimRules)
    free_agency: FreeAgency = Field(default_factory=FreeAgency)
    waiver: WaiverConfig = Field(default_factory=WaiverConfig)
    draft_claims: DraftClaimRules = Field(default_factory=DraftClaimRules)
    # Iter 231g
    trades: TradesConfig = Field(default_factory=TradesConfig)


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
    cfg_obj = TransactionsConfig(**(league.get("transactions_config") or {}))
    # Iter 122 — when the waiver section is enabled, the waiver
    # pending_visibility takes precedence over the global one. This is
    # also where the `all_teams_anonymous` audience surfaces.
    if cfg_obj.waiver.enabled:
        audience = cfg_obj.waiver.pending_visibility
    else:
        audience = rules.get("pending_visibility") or "user"

    anonymous = False
    if audience == "user" or audience == "own":
        visible = is_owner or is_comm
    elif audience == "all_teams":
        own_team = await db.teams.find_one({"league_id": team["league_id"], "owner_id": user["_id"]})
        visible = bool(own_team) or is_comm
    elif audience == "all_teams_anonymous":
        own_team = await db.teams.find_one({"league_id": team["league_id"], "owner_id": user["_id"]})
        visible = bool(own_team) or is_comm
        # Owner + commissioner still see real counts; everyone else gets
        # the anonymized treatment (visible=true but anonymous=true).
        if visible and not (is_owner or is_comm):
            anonymous = True
    else:  # "league_admin"
        visible = is_comm

    if not visible:
        return {
            "visible": False,
            "anonymous": False,
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
        "anonymous": anonymous,
        "audience": audience,
        "season": {"total": s_total, "fa": s_fa, "waivers": s_wv},
        "week": {"total": w_total, "fa": w_fa, "waivers": w_wv},
        "limits": cfg["claim_limits"],
    }


# ─── Iter 122 — Waiver priority order endpoint ─────────────────────


@router.get("/leagues/{league_id}/waiver-priority")
async def get_waiver_priority(league_id: str, request: Request):
    """Returns the league's current effective waiver priority order plus,
    if the requesting user owns a team in this league, that team's rank
    in the queue (1 = picks first).

    Response
    --------
    {
      "league_id": "...",
      "enabled": bool,
      "priority_order": "reverse_standings_serpentine"|"reverse_standings"|"manual"|"random",
      "order": [{"team_id", "team_name", "rank"}, ...],
      "my_rank": int|null,
      "my_team_id": str|null,
      "total_teams": int,
    }
    """
    db = _db()
    user = await _get_user(request)
    try:
        league = await db.leagues.find_one({"_id": ObjectId(league_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid league_id")
    if not league:
        raise HTTPException(status_code=404, detail="League not found")

    cfg = TransactionsConfig(**(league.get("transactions_config") or {}))
    w = cfg.waiver
    teams = await db.teams.find({"league_id": league_id}).to_list(60)
    teams_by_id = {str(t["_id"]): t for t in teams}

    def _rank_reverse_standings() -> list[str]:
        # Lowest-ranked first (reverse of standings)
        ordered = sorted(
            teams,
            key=lambda t: (
                int(t.get("wins") or 0),
                float(t.get("points_for") or 0),
            ),
        )
        return [str(t["_id"]) for t in ordered]

    if w.priority_order == "manual":
        # Use the LM-input order; if any team is missing append them to
        # the end so we don't leave anyone out.
        order_ids = list(w.manual_priority_order or [])
        for t in teams:
            tid = str(t["_id"])
            if tid not in order_ids:
                order_ids.append(tid)
    elif w.priority_order == "random":
        # Deterministic per (league, current_week) so the page doesn't
        # reshuffle on every refresh; the actual claim processor reshuffles
        # at processing time. Seed = "{league_id}-{week}".
        import random
        seed = f"{league_id}-{int(league.get('current_week') or 1)}"
        rng = random.Random(seed)
        ids = [str(t["_id"]) for t in teams]
        rng.shuffle(ids)
        order_ids = ids
    else:
        # reverse_standings and reverse_standings_serpentine — first round
        # is the same (lowest team first). The serpentine flip only matters
        # for round 2+, which we don't predict here.
        order_ids = _rank_reverse_standings()

    my_team_id = None
    my_rank = None
    for t in teams:
        if t.get("owner_id") == user["_id"]:
            my_team_id = str(t["_id"])
            break
    if my_team_id and my_team_id in order_ids:
        my_rank = order_ids.index(my_team_id) + 1

    return {
        "league_id": league_id,
        "enabled": w.enabled,
        "priority_order": w.priority_order,
        "order": [
            {
                "team_id": tid,
                "team_name": (teams_by_id.get(tid) or {}).get("name", "?"),
                "rank": i + 1,
            }
            for i, tid in enumerate(order_ids)
        ],
        "my_rank": my_rank,
        "my_team_id": my_team_id,
        "total_teams": len(teams),
    }
