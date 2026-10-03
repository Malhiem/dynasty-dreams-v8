"""Draft configuration router — keeper / expansion / protection lists / NHL lottery.

Extracted from `routes/drafts.py` (iter 231) to keep that file under the
maintainability ceiling. Covers per-league commissioner configuration of
keeper drafts, expansion drafts, protection lists (keeper + expansion),
the draft-type selector, the first-draft-completed flag, and the
system-admin NHL lottery date.

All endpoints use the same `setup(deps)` injection pattern as the rest of
the modular routers — see `server.py` wiring.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel


router = APIRouter()
_deps: dict = {}


def setup(deps: dict) -> None:
    _deps.update(deps)


def _db(): return _deps["db"]
async def _get_user(request): return await _deps["get_current_user"](request)


# ──────────────────────────────────────────────────────────────────
# Iter 141 — Keeper draft configuration (per-league)
# ──────────────────────────────────────────────────────────────────

KEEPER_COST_METHODS = {"previous_round_drafted", "fixed_round_penalty", "salary_cap", "none"}


class KeeperConfigRequest(BaseModel):
    config: dict


@router.get("/leagues/{league_id}/keeper-config")
async def get_keeper_config(league_id: str):
    db = _db()
    try:
        league = await db.leagues.find_one({"_id": ObjectId(league_id)})
    except Exception:
        league = None
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    return {"league_id": league_id, "config": league.get("keeper_config") or {}}


@router.put("/leagues/{league_id}/keeper-config")
async def update_keeper_config(league_id: str, payload: KeeperConfigRequest, request: Request):
    db = _db()
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
    db = _db()
    try:
        league = await db.leagues.find_one({"_id": ObjectId(league_id)})
    except Exception:
        league = None
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    return {"league_id": league_id, "config": league.get("expansion_config") or {}}


@router.put("/leagues/{league_id}/expansion-config")
async def update_expansion_config(league_id: str, payload: ExpansionConfigRequest, request: Request):
    db = _db()
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
    db = _db()
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
    db = _db()
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
    db = _db()
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
    db = _db()
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
    db = _db()
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
    db = _db()
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
    db = _db()
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


# ──────────────────────────────────────────────────────────────────
# System NHL lottery date (admin-only)
# ──────────────────────────────────────────────────────────────────


class SystemNhlLotteryRequest(BaseModel):
    nhl_lottery_date: Optional[str] = None


@router.get("/admin/draft-lottery-date")
async def get_system_nhl_lottery_date(request: Request):
    db = _db()
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
    db = _db()
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
