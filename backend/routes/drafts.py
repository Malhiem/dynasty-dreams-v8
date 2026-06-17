"""Draft router — full draft engine.

Extracted from server.py during iter 98 modularization. Covers the entire
draft lifecycle (snake + auction): create, get, board, eligible-players,
start, pick, pause, chat, config, plus the auction sub-routes (nominate,
bid, resolve, state, init-budgets) and the picks endpoint (lottery /
protections).

Wiring via the standard `setup(deps)` pattern. All collection access goes
through `_db()` so the same module can be tested in isolation against a
throwaway database.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from draft_engine import (
    CreateDraftRequest, MakeDraftPickRequest, DraftChatRequest,
    UpdateDraftConfigRequest, get_team_for_pick, get_draft_order, build_draft_board,
)


router = APIRouter()
_deps: dict = {}
logger = logging.getLogger(__name__)


def setup(deps: dict) -> None:
    _deps.update(deps)


def _db(): return _deps["db"]
def _sio(): return _deps.get("sio")
async def _get_user(request): return await _deps["get_current_user"](request)
async def _log_activity(*a, **kw): return await _deps["log_activity"](*a, **kw)
async def _broadcast(room, event, payload):
    return await _deps["broadcast_to_room"](room, event, payload)
def _calculate_fantasy_points(*a, **kw): return _deps["calculate_fantasy_points"](*a, **kw)


# ─── Iter 170g — Team abbr derivation aligned with the frontend ────────
# Matches `team_to_response` (routes/teams.py) which honours
# `logo_abbr_override` then hyphen-aware initials, AND dedupes collisions
# by appending a 2/3/… suffix so two teams that share initials (e.g.
# "Crease Crashers" + "Checkmate Chiefs") get unique board columns.
def _derive_team_abbr(team: dict) -> str:
    name = team.get("name", "")
    override = (team.get("logo_abbr_override") or "").strip().upper()
    if override:
        return override[:4]
    words = [w for w in name.replace("-", " ").split() if w and w[0].isalnum()]
    if len(words) >= 2:
        return (words[0][0] + words[1][0] + (words[2][0] if len(words) > 2 else "")).upper()[:4]
    return (name[:3].upper() if name else "TBD")


def _abbrs_with_dedup(teams: list[dict]) -> tuple[list[str], dict]:
    """Return (abbrs_in_order, team_map_by_abbr) with collision dedup."""
    seen: dict[str, int] = {}
    abbrs: list[str] = []
    team_map: dict[str, dict] = {}
    for t in teams:
        base = _derive_team_abbr(t)
        count = seen.get(base, 0)
        seen[base] = count + 1
        abbr = base if count == 0 else f"{base}{count + 1}"
        abbrs.append(abbr)
        team_map[abbr] = {
            "id": str(t["_id"]),
            "name": t.get("name"),
            "owner_id": t.get("owner_id"),
        }
    return abbrs, team_map


@router.get("/drafts/{league_id}/picks")
async def get_draft_picks(league_id: str, year: Optional[int] = None):
    db = _deps["db"]
    query = {"league_id": league_id}
    if year:
        query["year"] = int(year)
    picks = await db.draft_picks.find(query).sort([("year", 1), ("round", 1)]).to_list(1000)

    # Build a lookup of pending pick-upgrade clauses (status=executed,
    # applied_at/failed_at not yet set) so the DraftBoard can render a
    # "Protected: top-N" / "Conditional upgrade" badge before the lottery
    # resolves.
    trades = await db.trades.find({
        "league_id": league_id,
        "status": "executed",
        "pick_upgrades": {"$exists": True, "$ne": []},
    }, {"_id": 1, "pick_upgrades": 1}).to_list(500)
    pending: dict = {}
    for t in trades:
        for u in (t.get("pick_upgrades") or []):
            if u.get("applied_at") or u.get("failed_at"):
                continue
            pid = u.get("pick_id")
            if not pid:
                continue
            cond = u.get("condition") or {}
            pending.setdefault(pid, []).append({
                "trade_id": str(t["_id"]),
                "new_round": u.get("new_round"),
                "new_year": u.get("new_year"),
                "subject_type": cond.get("subject_type"),
                "metric": cond.get("metric"),
                "operator": cond.get("operator"),
                "threshold": cond.get("threshold"),
                "description": cond.get("description") or u.get("description"),
            })

    for p in picks:
        p["_id"] = str(p["_id"])
        p["pending_protections"] = pending.get(p["_id"], [])
    return {"league_id": league_id, "year": year, "picks": picks}


# Iter 166 — Per-team draft picks (currently owned). Powers the
# Roster page's Draft Picks section + the team's pick provenance chips.
@router.get("/teams/{team_id}/draft-picks")
async def get_team_draft_picks(team_id: str, year: Optional[int] = None):
    """Return every pick currently owned by this team.

    A pick is considered "currently owned" when its `current_team_id`
    matches the requested team_id — regardless of who held the slot
    originally. Each pick carries its full `trade_history` so the
    front-end can render the provenance chain.
    """
    db = _deps["db"]
    query = {"current_team_id": team_id}
    if year:
        query["year"] = int(year)
    picks = await db.draft_picks.find(query).sort([("year", 1), ("round", 1)]).to_list(1000)
    for p in picks:
        p["_id"] = str(p["_id"])
    return {"team_id": team_id, "year": year, "picks": picks}


@router.get("/leagues/{league_id}/draft-order")
async def get_league_draft_order(league_id: str, year: Optional[int] = None):
    """Iter 137 + 138 — compute the canonical draft order for a given year.

    Returns the ordered seeds plus the configured method + schedule so the
    Draft Board can render a "pick order: set / pending" status banner.
    """
    db = _deps["db"]
    try:
        league = await db.leagues.find_one({"_id": ObjectId(league_id)})
    except Exception:
        league = None
    if not league:
        raise HTTPException(status_code=404, detail="League not found")

    teams = await db.teams.find({"league_id": league_id}).to_list(100)

    # Iter 138 — fetch method + scheduled timestamp (per-league or global)
    method = (league.get("draft_order_method") or "manual_entry").strip()
    scheduled_at = league.get("draft_order_scheduled_at")
    schedule_source = "league"
    if method == "nhl_lottery":
        sysdoc = await db.system_settings.find_one({"_id": "draft_lottery"})
        scheduled_at = (sysdoc or {}).get("nhl_lottery_date")
        schedule_source = "system"
    # ISO-string the datetime if it's a real datetime object
    if hasattr(scheduled_at, "isoformat"):
        scheduled_at = scheduled_at.isoformat()

    # 1. Try locked-in pick_number on this year's round-1 picks
    yr = int(year) if year else None
    rd1_query: dict = {"league_id": league_id, "round": 1}
    if yr:
        rd1_query["year"] = yr
    round1 = await db.draft_picks.find(rd1_query).to_list(200)
    with_number = [p for p in round1 if p.get("pick_number") is not None]
    if with_number and len(with_number) == len(teams):
        ordered = sorted(with_number, key=lambda p: int(p["pick_number"]))
        return {
            "league_id": league_id,
            "year": yr,
            "source": "lottery_applied",
            "is_set": True,
            "method": method,
            "scheduled_at": scheduled_at,
            "schedule_source": schedule_source,
            "order": [
                {
                    "team_id": str(p.get("original_team_id")),
                    "seed": int(p["pick_number"]),
                    "source": "lottery_applied",
                }
                for p in ordered
            ],
        }

    # 2. Fall back to reverse standings (worst first).
    def _key(t: dict):
        pts = float(t.get("points_for") or 0.0)
        wins = int(t.get("wins") or 0)
        losses = int(t.get("losses") or 0)
        return (wins, -losses, pts, t.get("name", ""))
    sorted_teams = sorted(teams, key=_key)
    return {
        "league_id": league_id,
        "year": yr,
        "source": "reverse_standings",
        "is_set": False,
        "method": method,
        "scheduled_at": scheduled_at,
        "schedule_source": schedule_source,
        "order": [
            {"team_id": str(t["_id"]), "seed": i + 1, "source": "reverse_standings"}
            for i, t in enumerate(sorted_teams)
        ],
    }


# ──────────────────────────────────────────────────────────────────
# Iter 138 — draft-order configuration (method + scheduled time)
# ──────────────────────────────────────────────────────────────────

DRAFT_ORDER_METHODS = {"nhl_lottery", "lottery_generator", "manual_entry"}


class DraftOrderConfigRequest(BaseModel):
    method: Optional[str] = None  # one of DRAFT_ORDER_METHODS
    scheduled_at: Optional[str] = None  # ISO datetime, "" or null to clear


@router.put("/leagues/{league_id}/draft-order/config")
async def update_league_draft_order_config(
    league_id: str, payload: DraftOrderConfigRequest, request: Request,
):
    """Commissioner-only. Sets the league's draft-order method and the
    scheduled date (for `lottery_generator` and `manual_entry`). For
    `nhl_lottery` the date is sourced globally from system settings and
    cannot be set here.
    """
    db = _deps["db"]
    user = await _get_user(request)
    try:
        league = await db.leagues.find_one({"_id": ObjectId(league_id)})
    except Exception:
        league = None
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    is_commish = (
        league.get("commissioner_id") == user["_id"]
        or user["_id"] in (league.get("co_commissioners") or [])
        or user.get("role") == "admin"
    )
    if not is_commish:
        raise HTTPException(status_code=403, detail="Only commissioners may set the draft order config")

    update: dict = {}
    if payload.method is not None:
        if payload.method not in DRAFT_ORDER_METHODS:
            raise HTTPException(status_code=400, detail=f"method must be one of {sorted(DRAFT_ORDER_METHODS)}")
        update["draft_order_method"] = payload.method
        # If switching to nhl_lottery, clear any per-league date
        if payload.method == "nhl_lottery":
            update["draft_order_scheduled_at"] = None
    if payload.scheduled_at is not None:
        if payload.scheduled_at == "":
            update["draft_order_scheduled_at"] = None
        else:
            update["draft_order_scheduled_at"] = payload.scheduled_at
    if not update:
        return {"ok": True, "league_id": league_id, "changed": False}
    await db.leagues.update_one({"_id": ObjectId(league_id)}, {"$set": update})
    return {"ok": True, "league_id": league_id, "changed": True, **update}


class SystemNhlLotteryRequest(BaseModel):
    nhl_lottery_date: Optional[str] = None


# ──────────────────────────────────────────────────────────────────
# Iter 141 — Keeper draft configuration (per-league)
# ──────────────────────────────────────────────────────────────────

KEEPER_COST_METHODS = {"previous_round_drafted", "fixed_round_penalty", "salary_cap", "none"}


class KeeperConfigRequest(BaseModel):
    config: dict


@router.get("/leagues/{league_id}/keeper-config")
async def get_keeper_config(league_id: str):
    db = _deps["db"]
    try:
        league = await db.leagues.find_one({"_id": ObjectId(league_id)})
    except Exception:
        league = None
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    return {"league_id": league_id, "config": league.get("keeper_config") or {}}


@router.put("/leagues/{league_id}/keeper-config")
async def update_keeper_config(league_id: str, payload: KeeperConfigRequest, request: Request):
    db = _deps["db"]
    user = await _get_user(request)
    try:
        league = await db.leagues.find_one({"_id": ObjectId(league_id)})
    except Exception:
        league = None
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    is_commish = (
        league.get("commissioner_id") == user["_id"]
        or user["_id"] in (league.get("co_commissioners") or [])
        or user.get("role") == "admin"
    )
    if not is_commish:
        raise HTTPException(status_code=403, detail="Only commissioners may set keeper config")
    cfg = payload.config or {}
    # Validate enum + bounds
    method = cfg.get("cost_method")
    if method is not None and method not in KEEPER_COST_METHODS:
        raise HTTPException(
            status_code=400,
            detail=f"cost_method must be one of {sorted(KEEPER_COST_METHODS)}",
        )
    for k in ("num_keepers", "max_seasons", "declaration_deadline_days", "round_offset",
              "rookie_late_round", "waiver_default_round"):
        if k in cfg and cfg[k] is not None and not isinstance(cfg[k], (int, float)):
            raise HTTPException(status_code=400, detail=f"{k} must be numeric")
        if k in cfg and cfg[k] is not None and cfg[k] < 0:
            raise HTTPException(status_code=400, detail=f"{k} must be ≥ 0")
    for k in ("allow_rookie_exception", "waiver_pickups_keepable", "enabled"):
        if k in cfg and cfg[k] is not None and not isinstance(cfg[k], bool):
            raise HTTPException(status_code=400, detail=f"{k} must be boolean")
    await db.leagues.update_one(
        {"_id": ObjectId(league_id)},
        {"$set": {"keeper_config": cfg}},
    )
    return {"ok": True, "league_id": league_id, "config": cfg}


# ──────────────────────────────────────────────────────────────────
# Iter 142 — Expansion draft configuration (per-league)
# ──────────────────────────────────────────────────────────────────

EXPANSION_LIST_VISIBILITY = {"public", "secret"}
EXPANSION_COMP_APPLIES = {"every", "threshold"}
EXPANSION_THRESHOLD_TYPES = {"salary_cap", "aav", "fppg"}
EXPANSION_PICK_ORDER_METHODS = {"automatic", "manual"}
EXPANSION_PICK_ORDER_STYLES = {"snake", "linear"}
EXPANSION_PICK_PLACEMENTS = {"top", "bottom", "random", "lottery_odds"}


class ExpansionConfigRequest(BaseModel):
    config: dict


@router.get("/leagues/{league_id}/expansion-config")
async def get_expansion_config(league_id: str):
    db = _deps["db"]
    try:
        league = await db.leagues.find_one({"_id": ObjectId(league_id)})
    except Exception:
        league = None
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    return {"league_id": league_id, "config": league.get("expansion_config") or {}}


@router.put("/leagues/{league_id}/expansion-config")
async def update_expansion_config(league_id: str, payload: ExpansionConfigRequest, request: Request):
    db = _deps["db"]
    user = await _get_user(request)
    try:
        league = await db.leagues.find_one({"_id": ObjectId(league_id)})
    except Exception:
        league = None
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    is_commish = (
        league.get("commissioner_id") == user["_id"]
        or user["_id"] in (league.get("co_commissioners") or [])
        or user.get("role") == "admin"
    )
    if not is_commish:
        raise HTTPException(status_code=403, detail="Only commissioners may set expansion config")

    cfg = payload.config or {}
    # Enum validation
    prot = cfg.get("protection") or {}
    if prot.get("list_visibility") and prot["list_visibility"] not in EXPANSION_LIST_VISIBILITY:
        raise HTTPException(status_code=400, detail="protection.list_visibility must be public|secret")
    comp = cfg.get("compensation_pick") or {}
    if comp.get("applies_to") and comp["applies_to"] not in EXPANSION_COMP_APPLIES:
        raise HTTPException(status_code=400, detail="compensation_pick.applies_to must be every|threshold")
    if comp.get("threshold_type") and comp["threshold_type"] not in EXPANSION_THRESHOLD_TYPES:
        raise HTTPException(status_code=400, detail="compensation_pick.threshold_type must be salary_cap|aav|fppg")
    order = cfg.get("pick_order") or {}
    if order.get("method") and order["method"] not in EXPANSION_PICK_ORDER_METHODS:
        raise HTTPException(status_code=400, detail="pick_order.method must be automatic|manual")
    if order.get("style") and order["style"] not in EXPANSION_PICK_ORDER_STYLES:
        raise HTTPException(status_code=400, detail="pick_order.style must be snake|linear")
    # Bounds
    if prot.get("max_taken_per_roster") is not None and not (0 <= prot["max_taken_per_roster"] <= 5):
        raise HTTPException(status_code=400, detail="protection.max_taken_per_roster must be 0-5")
    # Extra picks
    picks = cfg.get("expansion_picks") or []
    for i, p in enumerate(picks):
        if p.get("placement") and p["placement"] not in EXPANSION_PICK_PLACEMENTS:
            raise HTTPException(status_code=400, detail=f"expansion_picks[{i}].placement invalid")
        if p.get("round") is not None and p["round"] < 1:
            raise HTTPException(status_code=400, detail=f"expansion_picks[{i}].round must be ≥ 1")
        if p.get("placement") == "lottery_odds":
            odds = p.get("lottery_odds") or []
            if not isinstance(odds, list) or not odds:
                raise HTTPException(status_code=400, detail=f"expansion_picks[{i}].lottery_odds required")

    await db.leagues.update_one(
        {"_id": ObjectId(league_id)},
        {"$set": {"expansion_config": cfg}},
    )
    return {"ok": True, "league_id": league_id, "config": cfg}


# ──────────────────────────────────────────────────────────────────
# Iter 143 — Protection list status (keeper + expansion)
# + First-draft completion + Redraft toggling
# ──────────────────────────────────────────────────────────────────


@router.get("/leagues/{league_id}/protection-list/status")
async def get_protection_list_status(league_id: str, request: Request):
    """Returns whether the active user has a protection-list deadline
    coming up. Used by the global Protection List ribbon.
    """
    db = _deps["db"]
    user = await _get_user(request)
    try:
        league = await db.leagues.find_one({"_id": ObjectId(league_id)})
    except Exception:
        league = None
    if not league:
        return {"applicable": False}

    # Resolve the user's team in this league (if any)
    my_team = await db.teams.find_one({"league_id": league_id, "owner_id": user.get("_id")})
    my_team_id = str(my_team["_id"]) if my_team else None

    scheduled = league.get("draft_order_scheduled_at")
    if hasattr(scheduled, "isoformat"):
        scheduled = scheduled.isoformat()

    # Keeper: declaration deadline = draft_date - declaration_deadline_days
    keeper_cfg = league.get("keeper_config") or {}
    expansion_cfg = league.get("expansion_config") or {}

    # Pick the active draft type for this league. The Draft Type Select
    # on League Admin persists via league.next_draft_type (added in Iter
    # 143). Fallback to inferring from configs if absent.
    draft_type = league.get("next_draft_type")
    if not draft_type:
        if expansion_cfg.get("enabled"):
            draft_type = "expansion"
        elif keeper_cfg.get("enabled"):
            draft_type = "keeper"

    deadline_at = None
    if draft_type == "keeper" and scheduled:
        try:
            from datetime import datetime as _dt, timedelta as _td
            d = _dt.fromisoformat(str(scheduled).replace("Z", "+00:00"))
            days = int(keeper_cfg.get("declaration_deadline_days") or 0)
            if days > 0:
                deadline_at = (d - _td(days=days)).isoformat()
        except Exception:
            deadline_at = None
    elif draft_type == "expansion" and scheduled:
        prot = expansion_cfg.get("protection") or {}
        if (prot.get("list_visibility") == "public") and prot.get("reveal_days_before"):
            try:
                from datetime import datetime as _dt, timedelta as _td
                d = _dt.fromisoformat(str(scheduled).replace("Z", "+00:00"))
                days = int(prot.get("reveal_days_before") or 0)
                deadline_at = (d - _td(days=days)).isoformat()
            except Exception:
                deadline_at = None
        else:
            # Secret lists: deadline is the draft itself
            deadline_at = scheduled

    submitted = False
    if my_team_id and draft_type:
        existing = await db.protection_lists.find_one({
            "league_id": league_id,
            "team_id": my_team_id,
            "draft_type": draft_type,
        })
        submitted = bool(existing)

    applicable = bool(draft_type in {"keeper", "expansion"} and my_team_id and deadline_at)
    return {
        "applicable": applicable,
        "draft_type": draft_type,
        "deadline_at": deadline_at,
        "submitted": submitted,
        "my_team_id": my_team_id,
    }


class NextDraftTypeRequest(BaseModel):
    draft_type: Optional[str] = None


VALID_NEXT_DRAFT_TYPES = {
    "startup", "entry", "supplemental", "expansion", "keeper", "redraft",
}


@router.put("/leagues/{league_id}/next-draft-type")
async def set_next_draft_type(league_id: str, payload: NextDraftTypeRequest, request: Request):
    """Iter 143 — Persist the league's selected draft format so the
    Protection List ribbon + Draft Board read from a single source. The
    "startup" (first-time) type may only be chosen once per league: once
    `first_draft_completed` is true, the API rejects further startup
    selections with 400.
    """
    db = _deps["db"]
    user = await _get_user(request)
    try:
        league = await db.leagues.find_one({"_id": ObjectId(league_id)})
    except Exception:
        league = None
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    is_commish = (
        league.get("commissioner_id") == user["_id"]
        or user["_id"] in (league.get("co_commissioners") or [])
        or user.get("role") == "admin"
    )
    if not is_commish:
        raise HTTPException(status_code=403, detail="Only commissioners may set the draft type")
    dt = (payload.draft_type or "").strip()
    if dt and dt not in VALID_NEXT_DRAFT_TYPES:
        raise HTTPException(status_code=400, detail=f"draft_type must be one of {sorted(VALID_NEXT_DRAFT_TYPES)}")
    if dt == "startup" and league.get("first_draft_completed"):
        raise HTTPException(status_code=400, detail="First-time draft has already been completed; choose Redraft instead.")
    await db.leagues.update_one({"_id": ObjectId(league_id)}, {"$set": {"next_draft_type": dt or None}})
    return {"ok": True, "league_id": league_id, "next_draft_type": dt or None}


class FirstDraftFlagRequest(BaseModel):
    completed: bool


@router.put("/leagues/{league_id}/first-draft-completed")
async def set_first_draft_completed(league_id: str, payload: FirstDraftFlagRequest, request: Request):
    db = _deps["db"]
    user = await _get_user(request)
    try:
        league = await db.leagues.find_one({"_id": ObjectId(league_id)})
    except Exception:
        league = None
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    is_commish = (
        league.get("commissioner_id") == user["_id"]
        or user["_id"] in (league.get("co_commissioners") or [])
        or user.get("role") == "admin"
    )
    if not is_commish:
        raise HTTPException(status_code=403, detail="Only commissioners may mark first-draft completed")
    await db.leagues.update_one(
        {"_id": ObjectId(league_id)},
        {"$set": {"first_draft_completed": bool(payload.completed)}},
    )
    return {"ok": True, "first_draft_completed": bool(payload.completed)}


# ──────────────────────────────────────────────────────────────────
# Iter 144 — Protection list per-team toggle + commissioner override
# ──────────────────────────────────────────────────────────────────


class ProtectionToggleRequest(BaseModel):
    player_id: str
    draft_type: Optional[str] = None  # "keeper" | "expansion"


@router.get("/leagues/{league_id}/protection-list/{team_id}")
async def get_team_protection_list(
    league_id: str, team_id: str, draft_type: Optional[str] = None,
):
    db = _deps["db"]
    dt = draft_type or "expansion"
    doc = await db.protection_lists.find_one({
        "league_id": league_id, "team_id": team_id, "draft_type": dt,
    })
    return {
        "league_id": league_id,
        "team_id": team_id,
        "draft_type": dt,
        "submitted": bool(doc),
        "protected_player_ids": (doc or {}).get("protected_player_ids", []) or [],
    }


def _resolve_draft_type(league: dict) -> str:
    """Default to whatever the league has selected; fall back to expansion."""
    nxt = (league.get("next_draft_type") or "").strip()
    if nxt in {"keeper", "expansion"}:
        return nxt
    if (league.get("expansion_config") or {}).get("enabled"):
        return "expansion"
    if (league.get("keeper_config") or {}).get("enabled"):
        return "keeper"
    return "expansion"


@router.post("/leagues/{league_id}/protection-list/{team_id}/toggle")
async def toggle_protection_player(
    league_id: str, team_id: str, payload: ProtectionToggleRequest, request: Request,
):
    db = _deps["db"]
    user = await _get_user(request)
    try:
        league = await db.leagues.find_one({"_id": ObjectId(league_id)})
        team = await db.teams.find_one({"_id": ObjectId(team_id)})
    except Exception:
        league = team = None
    if not league or not team:
        raise HTTPException(status_code=404, detail="League or team not found")
    # Owner or commissioner
    is_commish = (
        league.get("commissioner_id") == user["_id"]
        or user["_id"] in (league.get("co_commissioners") or [])
        or user.get("role") == "admin"
    )
    if team.get("owner_id") != user["_id"] and not is_commish:
        raise HTTPException(status_code=403, detail="Only the team owner or a commissioner may edit this list")
    dt = (payload.draft_type or _resolve_draft_type(league))
    if dt not in {"keeper", "expansion"}:
        raise HTTPException(status_code=400, detail="draft_type must be keeper|expansion")
    doc = await db.protection_lists.find_one({
        "league_id": league_id, "team_id": team_id, "draft_type": dt,
    }) or {
        "league_id": league_id, "team_id": team_id, "draft_type": dt,
        "protected_player_ids": [],
    }
    ids = list(doc.get("protected_player_ids") or [])
    pid = str(payload.player_id)
    if pid in ids:
        ids.remove(pid)
        action = "removed"
    else:
        ids.append(pid)
        action = "added"
    # Enforce protection cap if expansion
    if dt == "expansion":
        max_p = (((league.get("expansion_config") or {}).get("protection") or {}).get("max_protected"))
        if max_p is not None and len(ids) > int(max_p):
            raise HTTPException(
                status_code=400,
                detail=f"Cannot protect more than {max_p} players for this expansion draft.",
            )
    if dt == "keeper":
        max_k = (league.get("keeper_config") or {}).get("num_keepers")
        if max_k is not None and len(ids) > int(max_k):
            raise HTTPException(
                status_code=400,
                detail=f"Cannot keep more than {max_k} players.",
            )
    await db.protection_lists.update_one(
        {"league_id": league_id, "team_id": team_id, "draft_type": dt},
        {"$set": {
            "league_id": league_id, "team_id": team_id, "draft_type": dt,
            "protected_player_ids": ids,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "updated_by": str(user["_id"]),
        }},
        upsert=True,
    )
    return {"ok": True, "action": action, "protected_player_ids": ids, "count": len(ids)}


class AutoProtectRequest(BaseModel):
    team_id: str
    draft_type: Optional[str] = None
    metric: Optional[str] = "salary"  # "salary" | "fppg"


@router.post("/leagues/{league_id}/protection-list/auto-protect")
async def commissioner_auto_protect(
    league_id: str, payload: AutoProtectRequest, request: Request,
):
    """Iter 144 — Commissioner override: auto-protect the top-N players
    on an inactive team's roster by `metric` (salary or fppg), where N
    is `expansion.protection.max_protected` (or `keeper.num_keepers`).
    Marks the protection list as submitted on the team's behalf.
    """
    db = _deps["db"]
    user = await _get_user(request)
    try:
        league = await db.leagues.find_one({"_id": ObjectId(league_id)})
        team = await db.teams.find_one({"_id": ObjectId(payload.team_id)})
    except Exception:
        league = team = None
    if not league or not team:
        raise HTTPException(status_code=404, detail="League or team not found")
    is_commish = (
        league.get("commissioner_id") == user["_id"]
        or user["_id"] in (league.get("co_commissioners") or [])
        or user.get("role") == "admin"
    )
    if not is_commish:
        raise HTTPException(status_code=403, detail="Only commissioners may auto-protect")
    dt = (payload.draft_type or _resolve_draft_type(league))
    if dt == "expansion":
        max_n = int(((league.get("expansion_config") or {}).get("protection") or {}).get("max_protected") or 0)
    else:
        max_n = int((league.get("keeper_config") or {}).get("num_keepers") or 0)
    if max_n <= 0:
        raise HTTPException(status_code=400, detail="No protection slots configured for this draft type")

    players = await db.players.find({"league_id": league_id, "team_id": payload.team_id}).to_list(500)
    metric = (payload.metric or "salary").lower()
    def _score(p):
        if metric == "fppg":
            return float(p.get("stats", {}).get("fppg") or 0.0)
        return float((p.get("contract") or {}).get("salary") or 0.0)
    sorted_players = sorted(players, key=_score, reverse=True)
    top_ids = [str(p["_id"]) for p in sorted_players[:max_n]]

    await db.protection_lists.update_one(
        {"league_id": league_id, "team_id": payload.team_id, "draft_type": dt},
        {"$set": {
            "league_id": league_id, "team_id": payload.team_id, "draft_type": dt,
            "protected_player_ids": top_ids,
            "auto_protected_by": str(user["_id"]),
            "auto_protected_metric": metric,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }},
        upsert=True,
    )
    return {"ok": True, "draft_type": dt, "protected_player_ids": top_ids, "count": len(top_ids), "metric": metric}





@router.get("/leagues/{league_id}/expansion-draft-board")
async def get_expansion_draft_board(league_id: str):
    """For expansion drafts, return every team's players partitioned
    into `unprotected` (drafted FIRST) and `protected` (shown after).
    Protection lists are stored in `protection_lists` keyed by
    (league_id, team_id, draft_type="expansion"). Teams without a
    submitted protection list show all players as `unprotected`.
    """
    db = _deps["db"]
    try:
        league = await db.leagues.find_one({"_id": ObjectId(league_id)})
    except Exception:
        league = None
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    teams = await db.teams.find({"league_id": league_id}).to_list(100)
    rows = []
    for t in teams:
        tid = str(t["_id"])
        proto = await db.protection_lists.find_one({
            "league_id": league_id,
            "team_id": tid,
            "draft_type": "expansion",
        })
        protected_ids = set((proto or {}).get("protected_player_ids", []) or [])
        players = await db.players.find(
            {"league_id": league_id, "team_id": tid},
        ).to_list(500)
        unprotected = []
        protected_list = []
        for p in players:
            pid = str(p["_id"])
            payload = {
                "id": pid,
                "name": p.get("name"),
                "position": p.get("position"),
                "salary": p.get("contract", {}).get("salary") if p.get("contract") else None,
            }
            if pid in protected_ids:
                protected_list.append(payload)
            else:
                unprotected.append(payload)
        rows.append({
            "team_id": tid,
            "team_name": t.get("name"),
            "team_abbr": t.get("logo_abbr") or (t.get("name", "")[:3] or "TM").upper(),
            "submitted": bool(proto),
            "unprotected": unprotected,
            "protected": protected_list,
        })
    return {"league_id": league_id, "teams": rows}



@router.get("/admin/draft-lottery-date")
async def get_system_nhl_lottery_date(request: Request):
    db = _deps["db"]
    user = await _get_user(request)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="System admins only")
    doc = await db.system_settings.find_one({"_id": "draft_lottery"})
    date = (doc or {}).get("nhl_lottery_date")
    if hasattr(date, "isoformat"):
        date = date.isoformat()
    return {"nhl_lottery_date": date}


@router.put("/admin/draft-lottery-date")
async def set_system_nhl_lottery_date(payload: SystemNhlLotteryRequest, request: Request):
    """System-admin only. Sets the global NHL draft-lottery date used by
    every league configured with `draft_order_method == nhl_lottery`.
    """
    db = _deps["db"]
    user = await _get_user(request)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="System admins only")
    value = (payload.nhl_lottery_date or "").strip() or None
    await db.system_settings.update_one(
        {"_id": "draft_lottery"},
        {"$set": {"nhl_lottery_date": value, "updated_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )
    return {"ok": True, "nhl_lottery_date": value}




@router.post("/drafts")
async def create_draft(input: CreateDraftRequest, request: Request):
    user = await _get_user(request)

    league = await _db().leagues.find_one({"_id": ObjectId(input.league_id)})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")

    if league["commissioner_id"] != user["_id"]:
        raise HTTPException(status_code=403, detail="Only commissioner can create drafts")

    # Get league teams for draft order
    teams = await _db().teams.find({"league_id": input.league_id}).to_list(100)
    # Iter 170g — abbr derivation aligned with frontend (`logo_abbr` +
    # dedup) so the Draft Room board renders the same column keys the
    # backend stores against `picks.team` and broadcasts as
    # `on_the_clock`.
    team_abbrs, team_map = _abbrs_with_dedup(teams)

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
    result = await _db().drafts.insert_one(draft_doc)
    draft_doc["_id"] = str(result.inserted_id)
    draft_doc.pop("team_map", None)
    return draft_doc

@router.get("/drafts")
async def get_drafts(league_id: Optional[str] = None, request: Request = None):
    query = {}
    if league_id:
        query["league_id"] = league_id
    drafts = await _db().drafts.find(query, {"team_map": 0}).sort("created_at", -1).to_list(100)
    for d in drafts:
        d["_id"] = str(d["_id"])
    return drafts

@router.get("/drafts/{draft_id}")
async def get_draft(draft_id: str):
    draft = await _db().drafts.find_one({"_id": ObjectId(draft_id)})
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    draft["_id"] = str(draft["_id"])
    return draft

@router.get("/drafts/{draft_id}/board")
async def get_draft_board(draft_id: str):
    draft = await _db().drafts.find_one({"_id": ObjectId(draft_id)})
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

@router.get("/drafts/{draft_id}/eligible-players")
async def get_draft_eligible_players(
    draft_id: str,
    search: Optional[str] = None,
    position: Optional[str] = None,
    page: int = 1,
    limit: int = 50
):
    draft = await _db().drafts.find_one({"_id": ObjectId(draft_id)})
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
    players = await _db().players.find(query).sort("points", -1).skip(skip).limit(limit).to_list(limit)
    total = await _db().players.count_documents(query)

    result = []
    for i, p in enumerate(players):
        # Iter 170g — surface a best-effort NHL headshot URL based on
        # nhl_id + team. Frontend falls back to an initials circle if
        # the image 404s.
        headshot = (
            f"https://assets.nhle.com/mugs/nhl/20252026/{p.get('team', 'NHL')}/{p.get('nhl_id', '')}.png"
            if p.get("nhl_id") else None
        )
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
            "drafted": False,
            "headshot": headshot,
            "nhl_id": p.get("nhl_id"),
        })

    return {"players": result, "total": total, "page": page, "pages": (total + limit - 1) // limit}


# ─── Iter 170g — Auto-init draft for a league ─────────────────────────
# Used by the Draft Room on mount: returns the most-recent draft for the
# league, creating one with sensible defaults if none exists yet. Idempotent
# — re-running returns the existing draft. Commissioner-only.

@router.post("/drafts/auto-init/{league_id}")
async def auto_init_draft(league_id: str, request: Request):
    user = await _get_user(request)
    league = await _db().leagues.find_one({"_id": ObjectId(league_id)})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    is_comm = league["commissioner_id"] == user["_id"]
    co_comms = league.get("co_commissioners", []) or []
    if not (is_comm or user["_id"] in co_comms):
        raise HTTPException(status_code=403, detail="Only commissioners can auto-init drafts")

    existing = await _db().drafts.find_one({"league_id": league_id}, sort=[("created_at", -1)])
    if existing:
        existing["_id"] = str(existing["_id"])
        existing.pop("team_map", None)
        return {"draft": existing, "created": False}

    teams = await _db().teams.find({"league_id": league_id}).to_list(100)
    if not teams:
        raise HTTPException(status_code=400, detail="League has no teams")
    team_abbrs, team_map = _abbrs_with_dedup(teams)

    draft_doc = {
        "league_id": league_id,
        "league_name": league.get("name"),
        "draft_type": "snake",
        "scheduled_time": None,
        "total_rounds": 5,
        "time_per_pick": 120,
        "snake_draft": True,
        "player_criteria": "open",  # Iter 170n — the players collection
        # currently holds NHL-active players only (no prospect pool). The
        # default reflects what the data supports; once a prospect pool
        # is seeded, this can switch back to "entry" + filter
        # eligible-players accordingly.
        "missed_pick_action": "skip",
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
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    res = await _db().drafts.insert_one(draft_doc)
    draft_doc["_id"] = str(res.inserted_id)
    draft_doc.pop("team_map", None)
    return {"draft": draft_doc, "created": True}

@router.post("/drafts/{draft_id}/start")
async def start_draft(draft_id: str, request: Request, early_start: bool = False):
    user = await _get_user(request)

    draft = await _db().drafts.find_one({"_id": ObjectId(draft_id)})
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")

    league = await _db().leagues.find_one({"_id": ObjectId(draft["league_id"])})
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
    await _db().drafts.update_one({"_id": ObjectId(draft_id)}, update)

    # Broadcast draft start
    await _broadcast(f"draft_{draft_id}", "draft_started", {
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
    await _db().drafts.update_one({"_id": ObjectId(draft_id)}, {"$push": {"chat_messages": system_msg}})
    await _broadcast(f"draft_{draft_id}", "draft_chat", system_msg)

    return {"message": "Draft started", "early_start": early_start}

@router.post("/drafts/{draft_id}/pick")
async def make_draft_pick(draft_id: str, input: MakeDraftPickRequest, request: Request):
    user = await _get_user(request)

    draft = await _db().drafts.find_one({"_id": ObjectId(draft_id)})
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")

    if draft["status"] != "active":
        raise HTTPException(status_code=400, detail="Draft is not active")

    # Iter 170g — abbr derivation aligned with the draft's stored
    # team_map (which was built by `_abbrs_with_dedup` at create time).
    # The user's team_id is the source of truth; we map it back to the
    # stored abbr for the on-clock comparison.
    team = await _db().teams.find_one({"league_id": draft["league_id"], "owner_id": user["_id"]})
    on_clock = get_team_for_pick(draft["team_abbrs"], draft["current_pick"], draft["snake_draft"])
    on_clock_team_id = (draft.get("team_map") or {}).get(on_clock, {}).get("id")

    # Commissioner can pick for any team, or it must be the user's turn
    league = await _db().leagues.find_one({"_id": ObjectId(draft["league_id"])})
    is_commissioner = league["commissioner_id"] == user["_id"]

    if not is_commissioner:
        if not team:
            raise HTTPException(status_code=403, detail="You don't have a team in this league")
        if str(team["_id"]) != on_clock_team_id:
            raise HTTPException(status_code=403, detail=f"Not your turn. {on_clock} is on the clock.")

    # Validate player exists and not already drafted
    player = await _db().players.find_one({"_id": ObjectId(input.player_id)})
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
        "team_id": on_clock_team_id,
        "player_id": str(player["_id"]),
        "player": {
            "id": str(player["_id"]),
            "name": player["name"],
            "position": player["position"],
            "nhlTeam": player.get("team", ""),
            "team_name": player.get("team_name", ""),
            "pts": player.get("points", 0),
            "g": player.get("goals", 0),
            "a": player.get("assists", 0),
            "gp": player.get("games_played", 0),
            "league": "NHL",
            # Iter 170g — headshot URL from NHL's CDN. The frontend's
            # tile / SelectedPlayerCard render this when present and
            # fall back to the initial circle if it 404s.
            "headshot": (
                f"https://assets.nhle.com/mugs/nhl/20252026/{player.get('team', 'NHL')}/{player.get('nhl_id', '')}.png"
                if player.get("nhl_id") else None
            ),
        },
        "picked_by": user["_id"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    next_pick = current_pick + 1
    total_picks = draft["total_rounds"] * total_teams
    new_status = "completed" if next_pick > total_picks else "active"

    await _db().drafts.update_one(
        {"_id": ObjectId(draft_id)},
        {
            "$push": {"picks": pick_doc},
            "$set": {"current_pick": next_pick, "status": new_status},
        },
    )

    # Iter 170g — also push the picked player onto the on-clock team's
    # roster so the Roster page + My Roster tile in the Draft Room both
    # reflect the pick without a separate manual step. Idempotent via
    # `$addToSet`.
    if on_clock_team_id:
        await _db().teams.update_one(
            {"_id": ObjectId(on_clock_team_id)},
            {"$addToSet": {"roster": str(player["_id"])}},
        )

    # Broadcast pick
    await _broadcast(f"draft_{draft_id}", "draft_pick", {
        **pick_doc,
        "next_pick": next_pick,
        "on_the_clock": get_team_for_pick(draft["team_abbrs"], next_pick, draft["snake_draft"]) if new_status == "active" else None,
        "draft_complete": new_status == "completed",
    })

    # System chat for the pick
    pick_msg = {
        "id": f"pick-{current_pick}",
        "type": "pick",
        "sender": "System",
        "text": f"Pick #{current_pick} (Rd {round_num}, Pick {pick_in_round}): {on_clock} selects {player['name']} ({player['position']})",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    await _db().drafts.update_one({"_id": ObjectId(draft_id)}, {"$push": {"chat_messages": pick_msg}})
    await _broadcast(f"draft_{draft_id}", "draft_chat", pick_msg)

    if new_status == "completed":
        complete_msg = {
            "id": f"sys-complete",
            "type": "pick",
            "sender": "System",
            "text": "Draft is complete! All picks have been made.",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        await _db().drafts.update_one({"_id": ObjectId(draft_id)}, {"$push": {"chat_messages": complete_msg}})
        await _broadcast(f"draft_{draft_id}", "draft_chat", complete_msg)
        await _broadcast(f"draft_{draft_id}", "draft_completed", {"draft_id": draft_id})

    return pick_doc

# ─── Iter 170h — Commissioner powers: undo picks + swap picked player ─

class UndoDraftPicksRequest(BaseModel):
    count: int = Field(default=1, ge=1, le=50, description="How many of the most recent picks to undo.")


@router.post("/drafts/{draft_id}/undo")
async def undo_draft_picks(draft_id: str, payload: UndoDraftPicksRequest, request: Request):
    """Commissioner-only: rewind the draft by N picks. Removes the
    drafted players from the picking team's roster and broadcasts the
    undo so connected managers see the rollback live."""
    user = await _get_user(request)
    draft = await _db().drafts.find_one({"_id": ObjectId(draft_id)})
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    league = await _db().leagues.find_one({"_id": ObjectId(draft["league_id"])})
    if league["commissioner_id"] != user["_id"]:
        raise HTTPException(status_code=403, detail="Only commissioner can undo picks")

    picks = list(draft.get("picks", []))
    if not picks:
        raise HTTPException(status_code=400, detail="No picks to undo")
    count = min(payload.count, len(picks))
    removed = picks[-count:]
    kept = picks[:-count]

    # Remove the drafted players from the team rosters.
    for p in removed:
        tid = p.get("team_id") or (draft.get("team_map") or {}).get(p.get("team", ""), {}).get("id")
        pid = p.get("player_id")
        if tid and pid:
            await _db().teams.update_one(
                {"_id": ObjectId(tid)},
                {"$pull": {"roster": pid}},
            )

    new_current = max(1, draft.get("current_pick", 1) - count)
    new_status = "active" if draft.get("draft_started") else draft.get("status", "scheduled")
    if draft.get("status") == "completed":
        new_status = "active"

    await _db().drafts.update_one(
        {"_id": ObjectId(draft_id)},
        {"$set": {"picks": kept, "current_pick": new_current, "status": new_status}},
    )

    # Chat + broadcast.
    msg = {
        "id": f"undo-{datetime.now(timezone.utc).timestamp()}",
        "type": "pick",
        "sender": "System",
        "text": (
            f"Commissioner undid {count} pick{'s' if count != 1 else ''} — "
            f"on the clock returns to {get_team_for_pick(draft['team_abbrs'], new_current, draft['snake_draft'])}"
        ),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    await _db().drafts.update_one({"_id": ObjectId(draft_id)}, {"$push": {"chat_messages": msg}})
    await _broadcast(f"draft_{draft_id}", "draft_chat", msg)
    await _broadcast(f"draft_{draft_id}", "draft_undo", {
        "count": count,
        "removed_overalls": [p.get("overall") for p in removed],
        "current_pick": new_current,
        "on_the_clock": get_team_for_pick(draft["team_abbrs"], new_current, draft["snake_draft"]),
    })
    return {"undone": count, "current_pick": new_current, "on_the_clock": get_team_for_pick(draft["team_abbrs"], new_current, draft["snake_draft"])}


class SwapPickPlayerRequest(BaseModel):
    new_player_id: str = Field(..., description="Mongo ObjectId of the replacement player.")


@router.patch("/drafts/{draft_id}/picks/{overall}")
async def swap_pick_player(draft_id: str, overall: int, payload: SwapPickPlayerRequest, request: Request):
    """Commissioner-only: replace the player on an existing pick.

    Use case: a mis-typed pick or a mid-draft correction. The previously
    drafted player is removed from the team's roster and the new player
    is added. Other picks + the on-the-clock pointer are unchanged.
    """
    user = await _get_user(request)
    draft = await _db().drafts.find_one({"_id": ObjectId(draft_id)})
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    league = await _db().leagues.find_one({"_id": ObjectId(draft["league_id"])})
    if league["commissioner_id"] != user["_id"]:
        raise HTTPException(status_code=403, detail="Only commissioner can swap pick players")

    picks = list(draft.get("picks", []))
    target_idx = next((i for i, p in enumerate(picks) if p.get("overall") == overall), -1)
    if target_idx == -1:
        raise HTTPException(status_code=404, detail=f"Pick #{overall} not found")

    old_pick = picks[target_idx]
    new_player = await _db().players.find_one({"_id": ObjectId(payload.new_player_id)})
    if not new_player:
        raise HTTPException(status_code=404, detail="Replacement player not found")
    # Reject if the replacement is already drafted elsewhere.
    if any(p.get("player_id") == payload.new_player_id and p.get("overall") != overall for p in picks):
        raise HTTPException(status_code=400, detail="Replacement player is already drafted on another pick")

    tid = old_pick.get("team_id") or (draft.get("team_map") or {}).get(old_pick.get("team", ""), {}).get("id")
    old_player_id = old_pick.get("player_id")
    if tid and old_player_id:
        await _db().teams.update_one(
            {"_id": ObjectId(tid)},
            {"$pull": {"roster": old_player_id}},
        )
    if tid:
        await _db().teams.update_one(
            {"_id": ObjectId(tid)},
            {"$addToSet": {"roster": str(new_player["_id"])}},
        )

    picks[target_idx] = {
        **old_pick,
        "player_id": str(new_player["_id"]),
        "player": {
            "id": str(new_player["_id"]),
            "name": new_player["name"],
            "position": new_player["position"],
            "nhlTeam": new_player.get("team", ""),
            "team_name": new_player.get("team_name", ""),
            "pts": new_player.get("points", 0),
            "g": new_player.get("goals", 0),
            "a": new_player.get("assists", 0),
            "gp": new_player.get("games_played", 0),
            "league": "NHL",
            "headshot": (
                f"https://assets.nhle.com/mugs/nhl/20252026/{new_player.get('team', 'NHL')}/{new_player.get('nhl_id', '')}.png"
                if new_player.get("nhl_id") else None
            ),
        },
        "swapped_at": datetime.now(timezone.utc).isoformat(),
        "swapped_by": user["_id"],
    }
    await _db().drafts.update_one(
        {"_id": ObjectId(draft_id)},
        {"$set": {"picks": picks}},
    )
    msg = {
        "id": f"swap-{datetime.now(timezone.utc).timestamp()}",
        "type": "pick",
        "sender": "System",
        "text": (
            f"Commissioner swapped pick #{overall} ({old_pick.get('team', '')}): "
            f"{old_pick.get('player', {}).get('name', 'Unknown')} → {new_player['name']}"
        ),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    await _db().drafts.update_one({"_id": ObjectId(draft_id)}, {"$push": {"chat_messages": msg}})
    await _broadcast(f"draft_{draft_id}", "draft_chat", msg)
    await _broadcast(f"draft_{draft_id}", "draft_pick_swapped", {
        "overall": overall,
        "pick": picks[target_idx],
        "previous_player_id": old_player_id,
    })
    return {"overall": overall, "pick": picks[target_idx]}


@router.post("/drafts/{draft_id}/pause")
async def pause_draft(draft_id: str, request: Request):
    user = await _get_user(request)


# ─── Iter 170j — Auto-pick on Timeout ─────────────────────────────────


@router.post("/drafts/{draft_id}/auto-pick")
async def auto_pick_for_on_clock_team(draft_id: str, request: Request):
    """Auto-pick for whoever is on the clock when their timer expires.

    Resolution order:
      1. The on-clock team's `team.draft_queue` (first undrafted entry)
      2. The top-ranked undrafted player (eligible-players ordering)

    Anyone (manager) can fire this — the backend resolves the right
    team via the stored `team_map` so a missed pick can be skipped
    even when the absent manager isn't logged in.
    """
    await _get_user(request)  # auth required, but no role check
    draft = await _db().drafts.find_one({"_id": ObjectId(draft_id)})
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    if draft["status"] != "active":
        raise HTTPException(status_code=400, detail="Draft is not active")

    on_clock = get_team_for_pick(draft["team_abbrs"], draft["current_pick"], draft["snake_draft"])
    on_clock_team_id = (draft.get("team_map") or {}).get(on_clock, {}).get("id")
    if not on_clock_team_id:
        raise HTTPException(status_code=500, detail="Could not resolve on-clock team")

    drafted_ids = {p.get("player_id") for p in draft.get("picks", []) if p.get("player_id")}

    chosen_player = None
    via = "top_eligible"
    team = await _db().teams.find_one({"_id": ObjectId(on_clock_team_id)})
    queue = list((team or {}).get("draft_queue") or [])
    for pid in queue:
        if pid in drafted_ids:
            continue
        try:
            cand = await _db().players.find_one({"_id": ObjectId(pid)})
        except Exception:
            continue
        if cand:
            chosen_player = cand
            via = "queue"
            break

    if chosen_player is None:
        # Top eligible — same ordering as `get_draft_eligible_players`.
        async for p in _db().players.find().sort([("points", -1), ("name", 1)]):
            if str(p["_id"]) in drafted_ids:
                continue
            chosen_player = p
            break

    if chosen_player is None:
        raise HTTPException(status_code=400, detail="No eligible players left")

    total_teams = len(draft["team_abbrs"])
    current_pick = draft["current_pick"]
    round_num = ((current_pick - 1) // total_teams) + 1
    pick_in_round = ((current_pick - 1) % total_teams) + 1

    pick_doc = {
        "round": round_num,
        "pick_in_round": pick_in_round,
        "overall": current_pick,
        "team": on_clock,
        "team_id": on_clock_team_id,
        "player_id": str(chosen_player["_id"]),
        "player": {
            "id": str(chosen_player["_id"]),
            "name": chosen_player["name"],
            "position": chosen_player["position"],
            "nhlTeam": chosen_player.get("team", ""),
            "team_name": chosen_player.get("team_name", ""),
            "pts": chosen_player.get("points", 0),
            "g": chosen_player.get("goals", 0),
            "a": chosen_player.get("assists", 0),
            "gp": chosen_player.get("games_played", 0),
            "league": "NHL",
            "headshot": (
                f"https://assets.nhle.com/mugs/nhl/20252026/{chosen_player.get('team', 'NHL')}/{chosen_player.get('nhl_id', '')}.png"
                if chosen_player.get("nhl_id") else None
            ),
        },
        "auto_picked": True,
        "auto_pick_via": via,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    next_pick = current_pick + 1
    total_picks = draft["total_rounds"] * total_teams
    new_status = "completed" if next_pick > total_picks else "active"
    await _db().drafts.update_one(
        {"_id": ObjectId(draft_id)},
        {"$push": {"picks": pick_doc}, "$set": {"current_pick": next_pick, "status": new_status}},
    )
    await _db().teams.update_one(
        {"_id": ObjectId(on_clock_team_id)},
        {
            "$addToSet": {"roster": str(chosen_player["_id"])},
            "$pull": {"draft_queue": str(chosen_player["_id"])},
        },
    )
    msg = {
        "id": f"autopick-{datetime.now(timezone.utc).timestamp()}",
        "type": "pick",
        "sender": "System",
        "text": (
            f"⏱ Auto-pick — {on_clock} took {chosen_player['name']} ({chosen_player['position']}) "
            f"at #{current_pick} (via {'queue' if via == 'queue' else 'top eligible'})"
        ),
        "auto_picked": True,
        "auto_pick_via": via,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    await _db().drafts.update_one({"_id": ObjectId(draft_id)}, {"$push": {"chat_messages": msg}})
    await _broadcast(f"draft_{draft_id}", "draft_chat", msg)
    await _broadcast(f"draft_{draft_id}", "draft_pick", {
        **pick_doc,
        "next_pick": next_pick,
        "on_the_clock": get_team_for_pick(draft["team_abbrs"], next_pick, draft["snake_draft"]) if new_status == "active" else None,
        "draft_complete": new_status == "completed",
    })
    return {"pick": pick_doc, "via": via}


# ─── Iter 170j — Draft Queue persistence (per-team) ───────────────────


class DraftQueueRequest(BaseModel):
    player_ids: list[str] = Field(default_factory=list)


@router.put("/teams/{team_id}/draft-queue")
async def update_team_draft_queue(team_id: str, payload: DraftQueueRequest, request: Request):
    """Owner-only: persist the team's auto-pick queue (list of player ids).

    The auto-pick endpoint reads this list when a manager's clock
    expires and drafts the first undrafted entry before falling back
    to the global top-ranked eligible player.
    """
    user = await _get_user(request)
    team = await _db().teams.find_one({"_id": ObjectId(team_id)})
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    # Owner or league commissioner can edit.
    league = await _db().leagues.find_one({"_id": ObjectId(team["league_id"])})
    is_owner = team.get("owner_id") == user["_id"]
    is_comm = league and league.get("commissioner_id") == user["_id"]
    if not (is_owner or is_comm):
        raise HTTPException(status_code=403, detail="Only the team's owner or league commissioner can edit the draft queue")
    # Dedupe + cap length to avoid runaway payloads.
    seen: set[str] = set()
    cleaned: list[str] = []
    for pid in payload.player_ids:
        if pid not in seen:
            seen.add(pid)
            cleaned.append(pid)
        if len(cleaned) >= 100:
            break
    await _db().teams.update_one(
        {"_id": ObjectId(team_id)},
        {"$set": {"draft_queue": cleaned}},
    )
    return {"team_id": team_id, "draft_queue": cleaned, "size": len(cleaned)}


@router.get("/teams/{team_id}/draft-queue")
async def get_team_draft_queue(team_id: str, request: Request):
    await _get_user(request)
    team = await _db().teams.find_one({"_id": ObjectId(team_id)})
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    return {"team_id": team_id, "draft_queue": list(team.get("draft_queue") or [])}


# ─── Iter 170m — Shortlist persistence (per-team) ─────────────────────


class ShortlistRequest(BaseModel):
    player_ids: list[str] = Field(default_factory=list)


@router.put("/teams/{team_id}/shortlist")
async def update_team_shortlist(team_id: str, payload: ShortlistRequest, request: Request):
    """Owner-or-commissioner: persist the team's draft Shortlist (the
    ordered "watch list" the manager curates while scouting)."""
    user = await _get_user(request)
    team = await _db().teams.find_one({"_id": ObjectId(team_id)})
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    league = await _db().leagues.find_one({"_id": ObjectId(team["league_id"])})
    is_owner = team.get("owner_id") == user["_id"]
    is_comm = league and league.get("commissioner_id") == user["_id"]
    if not (is_owner or is_comm):
        raise HTTPException(status_code=403, detail="Only the team's owner or league commissioner can edit the shortlist")
    seen: set[str] = set()
    cleaned: list[str] = []
    for pid in payload.player_ids:
        if pid not in seen:
            seen.add(pid)
            cleaned.append(pid)
        if len(cleaned) >= 200:
            break
    await _db().teams.update_one(
        {"_id": ObjectId(team_id)},
        {"$set": {"shortlist": cleaned}},
    )
    return {"team_id": team_id, "shortlist": cleaned, "size": len(cleaned)}


@router.get("/teams/{team_id}/shortlist")
async def get_team_shortlist(team_id: str, request: Request):
    await _get_user(request)
    team = await _db().teams.find_one({"_id": ObjectId(team_id)})
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    return {"team_id": team_id, "shortlist": list(team.get("shortlist") or [])}
    draft = await _db().drafts.find_one({"_id": ObjectId(draft_id)})
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")

    league = await _db().leagues.find_one({"_id": ObjectId(draft["league_id"])})
    if league["commissioner_id"] != user["_id"]:
        raise HTTPException(status_code=403, detail="Only commissioner can pause draft")

    paused = not draft.get("timer_paused", False)
    await _db().drafts.update_one({"_id": ObjectId(draft_id)}, {"$set": {"timer_paused": paused}})

    await _broadcast(f"draft_{draft_id}", "draft_timer_toggle", {"paused": paused})
    return {"paused": paused}

@router.post("/drafts/{draft_id}/chat")
async def send_draft_chat(draft_id: str, input: DraftChatRequest, request: Request):
    user = await _get_user(request)

    team = await _db().teams.find_one({"league_id": (await _db().drafts.find_one({"_id": ObjectId(draft_id)}))["league_id"], "owner_id": user["_id"]})
    sender = team["name"] if team else user["name"]

    msg = {
        "id": f"chat-{datetime.now(timezone.utc).timestamp()}",
        "type": "chat",
        "sender": sender,
        "text": input.text,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

    await _db().drafts.update_one({"_id": ObjectId(draft_id)}, {"$push": {"chat_messages": msg}})
    await _broadcast(f"draft_{draft_id}", "draft_chat", msg)
    return msg

@router.get("/drafts/{draft_id}/chat")
async def get_draft_chat(draft_id: str):
    draft = await _db().drafts.find_one({"_id": ObjectId(draft_id)}, {"chat_messages": 1})
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    return draft.get("chat_messages", [])

@router.put("/drafts/{draft_id}/config")
async def update_draft_config(draft_id: str, input: UpdateDraftConfigRequest, request: Request):
    user = await _get_user(request)
    draft = await _db().drafts.find_one({"_id": ObjectId(draft_id)})
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")

    league = await _db().leagues.find_one({"_id": ObjectId(draft["league_id"])})
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
        await _db().drafts.update_one({"_id": ObjectId(draft_id)}, {"$set": updates})
        await _broadcast(f"draft_{draft_id}", "draft_config_updated", updates)

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
    result = await _db().notifications.insert_one(doc)
    doc["_id"] = str(result.inserted_id)
    # Broadcast to user's personal room (socket.io)
    sio = _sio()
    if sio is not None:
        try:
            await sio.emit("notification", doc, room=f"user_{user_id}")
        except Exception as e:
            logger.debug(f"sio notify skipped: {e}")
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
    teams = await _db().teams.find({"league_id": league_id}, {"owner_id": 1}).to_list(100)
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


@router.post("/drafts/{draft_id}/auction/nominate")
async def auction_nominate(draft_id: str, input: AuctionNominateRequest, request: Request):
    """Nominate a player for auction bidding."""
    user = await _get_user(request)
    draft = await _db().drafts.find_one({"_id": ObjectId(draft_id)})
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    if draft["status"] != "active":
        raise HTTPException(status_code=400, detail="Draft is not active")
    if draft.get("draft_type") != "auction":
        raise HTTPException(status_code=400, detail="This is not an auction draft")

    # Check no active auction
    if draft.get("active_auction"):
        raise HTTPException(status_code=400, detail="An auction is already in progress")

    team = await _db().teams.find_one({"league_id": draft["league_id"], "owner_id": user["_id"]})
    if not team:
        raise HTTPException(status_code=403, detail="No team in this league")

    # Check budget
    team_budget = draft.get("auction_budgets", {}).get(str(team["_id"]), draft.get("salary_cap", 200))
    if input.opening_bid > team_budget:
        raise HTTPException(status_code=400, detail=f"Insufficient budget (${team_budget} remaining)")

    player = await _db().players.find_one({"_id": ObjectId(input.player_id)})
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

    await _db().drafts.update_one(
        {"_id": ObjectId(draft_id)},
        {"$set": {"active_auction": auction}}
    )

    await _broadcast(f"draft_{draft_id}", "auction_nomination", auction)

    # System chat
    msg = {
        "id": f"auction-{datetime.now(timezone.utc).timestamp()}",
        "type": "pick",
        "sender": "System",
        "text": f"{team['name']} nominates {player['name']} ({player['position']}) - Opening bid: ${input.opening_bid}",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    await _db().drafts.update_one({"_id": ObjectId(draft_id)}, {"$push": {"chat_messages": msg}})
    await _broadcast(f"draft_{draft_id}", "draft_chat", msg)

    return auction


@router.post("/drafts/{draft_id}/auction/bid")
async def auction_bid(draft_id: str, input: AuctionBidRequest, request: Request):
    """Place a bid on the current auction."""
    user = await _get_user(request)
    draft = await _db().drafts.find_one({"_id": ObjectId(draft_id)})
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")

    auction = draft.get("active_auction")
    if not auction:
        raise HTTPException(status_code=400, detail="No active auction")

    team = await _db().teams.find_one({"league_id": draft["league_id"], "owner_id": user["_id"]})
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

    await _db().drafts.update_one(
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
    await _broadcast(f"draft_{draft_id}", "auction_bid", bid_data)

    return bid_data


@router.post("/drafts/{draft_id}/auction/resolve")
async def auction_resolve(draft_id: str, request: Request):
    """Resolve current auction - timer expired, winner gets player."""
    user = await _get_user(request)
    draft = await _db().drafts.find_one({"_id": ObjectId(draft_id)})
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")

    league = await _db().leagues.find_one({"_id": ObjectId(draft["league_id"])})
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

    await _db().drafts.update_one(
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
    await _broadcast(f"draft_{draft_id}", "auction_resolved", result)

    # System chat
    msg = {
        "id": f"resolved-{datetime.now(timezone.utc).timestamp()}",
        "type": "pick",
        "sender": "System",
        "text": f"SOLD! {auction['player_name']} goes to {auction['current_bidder_team_name']} for ${winning_bid}",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    await _db().drafts.update_one({"_id": ObjectId(draft_id)}, {"$push": {"chat_messages": msg}})
    await _broadcast(f"draft_{draft_id}", "draft_chat", msg)

    # Notify all league members
    await notify_league(
        draft["league_id"],
        NotificationType.DRAFT_PICK.value,
        "Auction Pick",
        f"{auction['current_bidder_team_name']} wins {auction['player_name']} for ${winning_bid}",
        link=f"/draft-room/{draft_id}"
    )

    return result


@router.get("/drafts/{draft_id}/auction/state")
async def get_auction_state(draft_id: str):
    """Get current auction state including active auction and budgets."""
    draft = await _db().drafts.find_one({"_id": ObjectId(draft_id)})
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")

    teams = await _db().teams.find({"league_id": draft["league_id"]}).to_list(100)
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


@router.post("/drafts/{draft_id}/auction/init-budgets")
async def init_auction_budgets(draft_id: str, request: Request):
    """Initialize auction budgets for all teams (commissioner only)."""
    user = await _get_user(request)
    draft = await _db().drafts.find_one({"_id": ObjectId(draft_id)})
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")

    league = await _db().leagues.find_one({"_id": ObjectId(draft["league_id"])})
    if league["commissioner_id"] != user["_id"]:
        raise HTTPException(status_code=403, detail="Only commissioner")

    cap = league.get("salary_cap") or 200
    teams = await _db().teams.find({"league_id": draft["league_id"]}).to_list(100)
    budgets = {str(t["_id"]): cap for t in teams}

    await _db().drafts.update_one(
        {"_id": ObjectId(draft_id)},
        {"$set": {"auction_budgets": budgets, "salary_cap": cap}}
    )

    return {"message": f"Initialized {len(budgets)} budgets at ${cap}", "budgets": budgets}

