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


def _send_email(to_email: str, subject: str, html_content: str) -> dict:
    """Iter 230y / 230ab — Thin wrapper around the SendGrid send fn
    registered on `_deps`. Falls back to a mocked `{status: skipped}`
    if the dependency wasn't injected (test envs, server startup
    before `_deps` is populated). Used by the early-start
    notification path to email the on-the-clock manager.
    """
    fn = _deps.get("send_sendgrid_email")
    if not fn:
        return {"status": "skipped", "reason": "send_sendgrid_email not injected"}
    try:
        return fn(to_email, subject, html_content)
    except Exception as e:
        logger.debug(f"_send_email failed for {to_email}: {e}")
        return {"status": "error", "error": str(e)}


# ─── Iter 170g — Team abbr derivation aligned with the frontend ────────
# Matches `team_to_response` (routes/teams.py) which honours
# `logo_abbr_override` then hyphen-aware initials, AND dedupes collisions
# by appending a 2/3/… suffix so two teams that share initials (e.g.
# "Crease Crashers" + "Checkmate Chiefs") get unique board columns.
def _derive_team_abbr(team: dict) -> str:
    name = team.get("name") or ""
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


# ─── Iter 204 — Related trades for a completed draft ────────────────────────
# Surfaces, for a single draft, every executed trade that affected
# either (a) a drafted player or (b) any pick used in or scheduled for
# this draft. Powers the "Related Trades" section on the Draft History
# page so managers can audit how a draft was shaped by trades.
@router.get("/drafts/{draft_id}/related-trades")
async def get_draft_related_trades(draft_id: str):
    db = _deps["db"]
    if not ObjectId.is_valid(draft_id):
        raise HTTPException(status_code=400, detail="Invalid draft id")
    draft = await db.drafts.find_one({"_id": ObjectId(draft_id)})
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")

    league_id = draft.get("league_id")
    picks = draft.get("picks") or []
    drafted_player_ids = {str(p.get("player_id")) for p in picks if p.get("player_id")}

    # Player-trade match: any executed trade where a player asset
    # references a player_id that appears in this draft.
    # Pick-trade match: any `is_in_draft_pick_trade=true` trade for the
    # league (these were proposed/executed in the context of this draft
    # cycle). Status filter is lenient — surface vetoed/expired ones
    # too so users see "what was attempted".
    all_trades = await db.trades.find({"league_id": league_id}).sort("created_at", -1).to_list(500)

    out = []
    for t in all_trades:
        proposer_assets = t.get("proposer_assets") or []
        receiver_assets = t.get("receiver_assets") or []
        is_pick_trade = bool(t.get("is_in_draft_pick_trade"))
        affected_player_ids: list[str] = []
        affected_picks: list[dict] = []

        for asset in proposer_assets + receiver_assets:
            atype = asset.get("type") or asset.get("asset_type")
            if atype == "player":
                pid = str(asset.get("player_id") or "")
                if pid and pid in drafted_player_ids:
                    affected_player_ids.append(pid)
            elif atype == "pick":
                affected_picks.append({
                    "pick_id": asset.get("pick_id"),
                    "round": asset.get("round"),
                    "year": asset.get("year"),
                    "original_team_id": asset.get("original_team_id"),
                })

        relevance = None
        if affected_player_ids and t.get("status") == "executed":
            relevance = "player"
        elif is_pick_trade:
            relevance = "pick"

        if not relevance:
            continue

        # Hydrate proposer / receiver team display names
        async def _team_name(tid):
            if not tid or not ObjectId.is_valid(str(tid)):
                return None
            doc = await db.teams.find_one({"_id": ObjectId(str(tid))}, {"name": 1, "logo_abbr": 1})
            return doc and (doc.get("name") or doc.get("logo_abbr"))

        # Hydrate affected drafted-player names (snapshot lookup from
        # the draft's picks list to avoid an extra players collection
        # round-trip).
        affected_players_meta = []
        for pid in set(affected_player_ids):
            match = next((pk for pk in picks if str(pk.get("player_id")) == pid), None)
            if match:
                affected_players_meta.append({
                    "player_id": pid,
                    "name": (match.get("player") or {}).get("name") or "Unknown",
                    "drafted_overall": match.get("overall"),
                    "drafted_by_team": match.get("team"),
                })

        out.append({
            "trade_id": str(t["_id"]),
            "relevance": relevance,
            "status": t.get("status"),
            "is_in_draft_pick_trade": is_pick_trade,
            "created_at": t.get("created_at"),
            "executed_at": t.get("executed_at"),
            "proposer_team_id": str(t.get("proposer_team_id") or ""),
            "receiver_team_id": str(t.get("receiver_team_id") or ""),
            "proposer_team_name": await _team_name(t.get("proposer_team_id")),
            "receiver_team_name": await _team_name(t.get("receiver_team_id")),
            "affected_players": affected_players_meta,
            "affected_picks": affected_picks,
            "votes": t.get("votes") or {},
            "post_review_action": t.get("post_review_action"),
        })

    return {"draft_id": draft_id, "league_id": league_id, "related_trades": out}


# ─── Iter 205 — Draft player stats (career totals + medal ranking) ─────────
# Aggregates career career totals + FP/FP/G for every player picked in
# a draft so the Draft History page can:
#   1. Expand a pick row to show stats-to-date
#   2. Render compact key-stat strips inline in the Pick Log
#   3. Award gold/silver/bronze medals to the top-3 producers PER
#      position group (C, W combining LW/RW, D, G), ranked by total
#      career fantasy points against the league's scoring config.
@router.get("/drafts/{draft_id}/player-stats")
async def get_draft_player_stats(draft_id: str):
    db = _deps["db"]
    if not ObjectId.is_valid(draft_id):
        raise HTTPException(status_code=400, detail="Invalid draft id")
    draft = await db.drafts.find_one({"_id": ObjectId(draft_id)})
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    league_id = draft.get("league_id")
    league = await db.leagues.find_one({"_id": ObjectId(league_id)}) if ObjectId.is_valid(str(league_id)) else None
    scoring_format = (league or {}).get("scoring_format", "head_to_head")
    is_h2h = "head_to_head" in scoring_format or "h2h" in scoring_format

    # Build the player_id → (overall, position, name) map from the
    # draft's picks list. We use the position recorded at draft time
    # (rather than re-resolving from /players) so backwards-compat is
    # preserved for legacy drafts.
    picks = draft.get("picks") or []
    rows: list[dict] = []
    for p in picks:
        pid = p.get("player_id")
        if not pid:
            continue
        rows.append({
            "overall": p.get("overall"),
            "player_id": pid,
            "drafted_pos": (p.get("player") or {}).get("position") or "—",
            "name": (p.get("player") or {}).get("name") or "Unknown",
        })

    # Pull each player's stats directly off the players collection.
    # On-doc fields (games_played, goals, assists, points, etc.) hold
    # season-to-date totals populated by the NHL sync. These are the
    # same fields powering the player browse / live scoring screens,
    # so a draft's medals stay in lockstep with the rest of the app.
    # (NHL true career totals are available via `/players/{id}/
    # historical-stats` but fetching for 60+ players inline would be
    # too slow — that endpoint stays click-through from a player's
    # profile.)
    player_object_ids = [ObjectId(r["player_id"]) for r in rows if ObjectId.is_valid(str(r["player_id"]))]
    player_docs = {}
    if player_object_ids:
        async for doc in db.players.find({"_id": {"$in": player_object_ids}}):
            player_docs[str(doc["_id"])] = doc

    # Lazy import to share the same fpts calculator the other player
    # endpoints use against league scoring config.
    from routes.players import _scoring_cfg_for, _calc_fpts
    scoring_cfg = await _scoring_cfg_for(league_id)

    out_rows: list[dict] = []
    for r in rows:
        pdoc = player_docs.get(str(r["player_id"])) or {}
        is_goalie = (r["drafted_pos"] or pdoc.get("position") or "") == "G"

        if is_goalie:
            stats = {
                "wins": pdoc.get("wins", 0),
                "losses": pdoc.get("losses", 0),
                "saves": pdoc.get("saves", 0),
                "shutouts": pdoc.get("shutouts", 0),
                "goals_against": pdoc.get("goals_against", 0),
            }
            display = {
                "games_played": pdoc.get("games_played", 0),
                "wins": pdoc.get("wins", 0),
                "losses": pdoc.get("losses", 0),
                "shutouts": pdoc.get("shutouts", 0),
                "save_pct": pdoc.get("save_pct", 0),
                "goals_against_avg": pdoc.get("goals_against_avg", 0),
            }
        else:
            stats = {
                "goals": pdoc.get("goals", 0),
                "assists": pdoc.get("assists", 0),
                "points": pdoc.get("points", 0),
                "plus_minus": pdoc.get("plus_minus", 0),
                "shots": pdoc.get("shots", 0),
                "ppg": pdoc.get("power_play_goals", 0),
                "ppp": pdoc.get("power_play_points", 0),
                "shg": pdoc.get("short_handed_goals", 0),
                "pim": pdoc.get("penalty_minutes", 0),
            }
            display = {
                "games_played": pdoc.get("games_played", 0),
                "goals": pdoc.get("goals", 0),
                "assists": pdoc.get("assists", 0),
                "points": pdoc.get("points", 0),
                "plus_minus": pdoc.get("plus_minus", 0),
                "shots": pdoc.get("shots", 0),
                "shooting_pct": pdoc.get("shooting_pct", 0),
            }
        gp = pdoc.get("games_played") or 0
        fpts = _calc_fpts(stats, is_goalie, scoring_cfg) if pdoc else 0.0
        fpts = round(float(fpts or 0), 2)
        fpg = round(fpts / gp, 2) if gp else 0.0

        out_rows.append({
            "overall": r["overall"],
            "player_id": r["player_id"],
            "name": r["name"],
            "position": r["drafted_pos"],
            "is_goalie": is_goalie,
            "career_stats": display,
            "fantasy_points": fpts,
            "fantasy_points_per_game": fpg,
            # Filled in below
            "medal": None,
            "position_group": None,
        })

    # Group by position_group (C, W [combines LW/RW], D, G).
    def _pos_group(pos: str) -> str:
        p = (pos or "").upper()
        if p == "C":
            return "C"
        if p in ("LW", "RW", "W"):
            return "W"
        if p == "D":
            return "D"
        if p == "G":
            return "G"
        return "OTHER"

    groups: dict[str, list[dict]] = {}
    for row in out_rows:
        g = _pos_group(row["position"])
        row["position_group"] = g
        groups.setdefault(g, []).append(row)

    # Award medals — top 3 by total fantasy_points in each group.
    # Ties broken by FP/G then by overall pick (earlier = higher rank).
    for g, items in groups.items():
        items.sort(
            key=lambda x: (
                -float(x["fantasy_points"] or 0),
                -float(x["fantasy_points_per_game"] or 0),
                x["overall"] or 9999,
            )
        )
        for idx, item in enumerate(items[:3]):
            # Only award if the player actually produced anything (>0 FP).
            if (item["fantasy_points"] or 0) <= 0:
                continue
            item["medal"] = ["gold", "silver", "bronze"][idx]

    return {
        "draft_id": draft_id,
        "league_id": league_id,
        "scoring_format": scoring_format,
        "is_h2h": is_h2h,
        "picks": sorted(out_rows, key=lambda x: x.get("overall") or 0),
    }


# Iter 166 — Per-team draft picks (currently owned). Powers the
# Roster page's Draft Picks section + the team's pick provenance chips.
@router.get("/teams/{team_id}/draft-picks")
async def get_team_draft_picks(team_id: str, year: Optional[int] = None):
    """Return every pick currently owned by this team.

    A pick is considered "currently owned" when its `current_team_id`
    matches the requested team_id — regardless of who held the slot
    originally. Each pick carries its full `trade_history` so the
    front-end can render the provenance chain.

    Iter 228o — Each pick is decorated with `draft_id` + `draft_name`
    so the Roster page can group picks by parent draft (e.g. "TFHL
    Inaugural Draft" vs "TFHL 2026 Entry Draft") instead of just by
    calendar year. Mapping prefers an explicit `pick.draft_id` field
    (set on newly-seeded picks), then falls back to matching the pick's
    `(league_id, year)` against the league's drafts collection.
    """
    db = _deps["db"]
    query = {"current_team_id": team_id}
    if year:
        query["year"] = int(year)
    picks = await db.draft_picks.find(query).sort([("year", 1), ("round", 1)]).to_list(1000)

    # ─── Build a year → (draft_id, draft_name) lookup for fallback ────
    league_ids = list({p.get("league_id") for p in picks if p.get("league_id")})
    drafts_by_year: dict = {}     # (league_id, year) → (draft_id, name)
    drafts_by_id: dict = {}       # draft_id → name
    drafts_meta_by_id: dict = {}  # draft_id → {name, scheduled_time}
    if league_ids:
        all_drafts = await db.drafts.find(
            {"league_id": {"$in": league_ids},
             "status": {"$ne": "archived"}},
            {"_id": 1, "league_id": 1, "name": 1, "scheduled_time": 1,
             "season": 1, "draft_type": 1},
        ).to_list(500)
        for d in all_drafts:
            did = str(d["_id"])
            name = d.get("name") or "Untitled Draft"
            drafts_by_id[did] = name
            # Iter 228s — also stash scheduled_time for chronological sort.
            drafts_meta_by_id[did] = {
                "name": name,
                "scheduled_time": d.get("scheduled_time"),
            }
            # Derive year for the draft
            yr = None
            sched = d.get("scheduled_time")
            if sched:
                try:
                    yr = int(str(sched)[:4])
                except Exception:
                    pass
            if yr is None and d.get("season"):
                try:
                    yr = int(str(d["season"]).split("-")[0])
                except Exception:
                    pass
            if yr is not None:
                key = (d["league_id"], yr)
                # Pick the most recently-created draft for a given (league, year)
                # — older inaugural drafts get bumped only if there's a tie.
                if key not in drafts_by_year:
                    drafts_by_year[key] = (did, name)

    for p in picks:
        p["_id"] = str(p["_id"])
        explicit_did = p.get("draft_id")
        if explicit_did and explicit_did in drafts_by_id:
            p["draft_name"] = drafts_by_id[explicit_did]
            # Iter 228s — surface scheduled_time so the Roster page can sort
            # chronologically (soonest draft on top).
            p["draft_scheduled_time"] = (drafts_meta_by_id.get(explicit_did) or {}).get("scheduled_time")
        else:
            key = (p.get("league_id"), int(p.get("year") or 0))
            mapped = drafts_by_year.get(key)
            if mapped:
                p["draft_id"] = mapped[0]
                p["draft_name"] = mapped[1]
                p["draft_scheduled_time"] = (drafts_meta_by_id.get(mapped[0]) or {}).get("scheduled_time")
            else:
                p["draft_name"] = f"{p.get('year') or 'Unknown'} Draft"
                p["draft_scheduled_time"] = None

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


# Iter 231 — Keeper / Expansion / Protection list / NHL lottery endpoints
# extracted to routes/draft_config.py to keep this file under the maintain-
# ability ceiling. SystemNhlLotteryRequest, KEEPER_COST_METHODS, the
# Expansion enums, KeeperConfigRequest, ExpansionConfigRequest,
# NextDraftTypeRequest, FirstDraftFlagRequest, ProtectionToggleRequest,
# AutoProtectRequest, VALID_NEXT_DRAFT_TYPES and _resolve_draft_type now
# all live in that module. See server.py for the wiring.


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

    # Iter 228d — soft-validate total_rounds against the league's actual
    # roster capacity (active + bench + minors) so a typo doesn't create
    # a 100-round draft. Cap silently at the larger of the configured
    # roster_size or 30 to keep legacy small-league behaviour intact.
    roster_cap = int(league.get("roster_spots") or 0) \
        + int(league.get("bench_spots") or 0) \
        + int(league.get("minors_spots") or 0)
    effective_max = max(roster_cap, 30)
    if input.total_rounds > effective_max:
        raise HTTPException(
            status_code=422,
            detail=(
                f"total_rounds ({input.total_rounds}) exceeds the league's "
                f"roster capacity ({effective_max}). Reduce rounds or increase "
                "roster spots."
            ),
        )

    # Iter 228h — When pick trading is enabled AND the window opens
    # immediately, generate the draft_picks rows so all teams see them
    # in the trade center / draft board right away. Without this the
    # commissioner has to manually call /admin/seed/draft-picks.
    pick_trading_enabled = bool(getattr(input, "pick_trading_enabled", False))
    trading_window_opens = str(getattr(input, "trading_window_opens", "immediately") or "immediately")

    draft_doc = {
        "league_id": input.league_id,
        "league_name": league["name"],
        # Iter 228d — name persisted on create (was being dropped, so the
        # Scheduled Drafts list always rendered "Untitled Draft").
        "name": (input.name or "").strip() or f"{league['name']} Draft",
        "draft_type": input.draft_type,
        "scheduled_time": scheduled,
        # Iter 228h — Timezone for the clock-starts / clock-stops fields
        "clock_timezone": getattr(input, "clock_timezone", None) or league.get("timezone") or "UTC",
        "clock_starts_at": getattr(input, "clock_starts_at", None),
        "clock_stops_at": getattr(input, "clock_stops_at", None),
        "total_rounds": input.total_rounds,
        "time_per_pick": input.time_per_pick,
        "round_time_overrides": input.round_time_overrides or [],
        "snake_draft": input.snake_draft,
        "player_criteria": input.player_criteria,
        "missed_pick_action": input.missed_pick_action,
        "defer_user_options": input.defer_user_options or [],
        "window_elapsed_actions": input.window_elapsed_actions or [],
        "pick_trading_enabled": pick_trading_enabled,
        "trading_window_opens": trading_window_opens,
        # Iter 228n — Eligibility filters (see CreateDraftRequest).
        "exclude_previously_drafted": bool(getattr(input, "exclude_previously_drafted", False)),
        "minors_eligibility_required": bool(getattr(input, "minors_eligibility_required", False)),
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

    # Iter 228h — Generate draft_picks rows when trading window is
    # already open. If the order isn't set yet, default to alphabetical
    # team ordering so the picks have a deterministic slot. The order
    # can be reshuffled later by saving the DraftOrderConfigCard.
    if pick_trading_enabled and trading_window_opens == "immediately":
        try:
            inserted = await _seed_draft_picks_for_draft(
                draft_id=str(result.inserted_id),
                league_id=input.league_id,
                rounds=input.total_rounds,
                year=int((league.get("season") or "2026").split("-")[0]),
            )
            draft_doc["picks_generated"] = inserted
        except Exception as ex:
            import logging
            logging.getLogger("drafts").warning(
                f"Failed to auto-generate draft picks for {result.inserted_id}: {ex}")
            draft_doc["picks_generated"] = 0

    # Iter 230 — Notify the league that a draft has been scheduled.
    try:
        from routes.notification_events import EVT_DRAFT_SCHEDULED
        teams_for_notif = await _db().teams.find(
            {"league_id": input.league_id},
            {"owner_id": 1, "co_owner_ids": 1},
        ).to_list(200)
        recipients: set = set()
        for t in teams_for_notif:
            if t.get("owner_id"):
                recipients.add(t["owner_id"])
            for co in (t.get("co_owner_ids") or []):
                if co:
                    recipients.add(co)
        when_str = scheduled or "TBD"
        draft_label = input.name or f"{input.draft_type or 'Draft'}"
        for uid in recipients:
            await create_notification(
                uid,
                EVT_DRAFT_SCHEDULED,
                "Draft scheduled",
                f"{draft_label} — {when_str}",
                input.league_id,
                "/draft-room",
            )
    except Exception as e:
        logger.debug(f"draft_scheduled notify skipped: {e}")

    return draft_doc


async def _seed_draft_picks_for_draft(
    draft_id: str, league_id: str, rounds: int, year: int,
) -> int:
    """Iter 231n — Thin re-export shim. The real implementation moved
    to `routes/draft_helpers.py` so both drafts.py and draft_pick_actions.py
    can plain-import it without late-binding workarounds. Kept here as a
    shim because internal call-sites at multiple lines in this file (and
    third-party tests that grep for `async def _seed_draft_picks_for_draft`
    in drafts.py source) rely on the name being defined here.
    """
    from routes.draft_helpers import seed_draft_picks_for_draft as _impl
    return await _impl(draft_id, league_id, rounds, year)

@router.delete("/drafts/{draft_id}")
async def delete_draft(draft_id: str, request: Request):
    """Iter 228d — Soft-delete a scheduled draft. Commissioner only.

    Marks the draft `status="archived"` + stamps `archived_at`. A
    background sweeper hard-deletes archived drafts after 15 days
    (recoverable until then via the admin UI).
    """
    user = await _get_user(request)
    try:
        draft = await _db().drafts.find_one({"_id": ObjectId(draft_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid draft_id")
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")

    league = await _db().leagues.find_one({"_id": ObjectId(draft["league_id"])})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    is_commish = (
        league.get("commissioner_id") == user["_id"]
        or user["_id"] in (league.get("co_commissioners") or [])
        or user.get("role") == "admin"
    )
    if not is_commish:
        raise HTTPException(status_code=403, detail="Commissioner or admin only")

    if draft.get("status") in ("in_progress", "completed"):
        raise HTTPException(
            status_code=400,
            detail=f"Can't archive a draft that's already {draft['status']}.",
        )

    now_iso = datetime.now(timezone.utc).isoformat()
    await _db().drafts.update_one(
        {"_id": ObjectId(draft_id)},
        {"$set": {
            "status": "archived",
            "archived_at": now_iso,
            "archived_by": user["_id"],
        }},
    )

    # Iter 228l — Audit row so the History drawer in the admin panel
    # can show "Archived by {commissioner} at {timestamp}" alongside
    # subsequent admin purge/restore entries.
    await _db().admin_user_actions.insert_one({
        "admin_id": str(user["_id"]),
        "admin_email": user.get("email"),
        "admin_tier": user.get("permission_tier") or user.get("role") or "commissioner",
        "target_user_id": league.get("commissioner_id"),
        "action": "draft_archive",
        "reason": "Commissioner soft-deleted a scheduled draft (15-day recovery window)",
        "metadata": {
            "draft_id": draft_id,
            "draft_name": draft.get("name"),
            "league_id": draft.get("league_id"),
            "league_name": draft.get("league_name"),
            "total_rounds": draft.get("total_rounds"),
            "scheduled_time": draft.get("scheduled_time"),
        },
        "prior_state": {"status": draft.get("status")},
        "mocked": False,
        "ts": now_iso,
    })

    return {"draft_id": draft_id, "status": "archived", "archived_at": now_iso}


@router.post("/drafts/{draft_id}/restore")
async def restore_draft(draft_id: str, request: Request):
    """Iter 228d — Restore a soft-deleted draft (within 15-day window)."""
    user = await _get_user(request)
    try:
        draft = await _db().drafts.find_one({"_id": ObjectId(draft_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid draft_id")
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    if draft.get("status") != "archived":
        raise HTTPException(status_code=400, detail="Draft is not archived")

    league = await _db().leagues.find_one({"_id": ObjectId(draft["league_id"])})
    is_commish = (
        league and (
            league.get("commissioner_id") == user["_id"]
            or user["_id"] in (league.get("co_commissioners") or [])
            or user.get("role") == "admin"
        )
    )
    if not is_commish:
        raise HTTPException(status_code=403, detail="Commissioner or admin only")

    await _db().drafts.update_one(
        {"_id": ObjectId(draft_id)},
        {"$set": {"status": "scheduled"},
         "$unset": {"archived_at": "", "archived_by": ""}},
    )

    # Iter 228l — Audit row mirrors the admin restore endpoint so the
    # History drawer covers BOTH commissioner-initiated and admin-
    # initiated restores in a single timeline.
    from datetime import datetime as _dt, timezone as _tz
    await _db().admin_user_actions.insert_one({
        "admin_id": str(user["_id"]),
        "admin_email": user.get("email"),
        "admin_tier": user.get("permission_tier") or user.get("role") or "commissioner",
        "target_user_id": (league or {}).get("commissioner_id"),
        "action": "draft_restore",
        "reason": "Commissioner restored archived draft within the 15-day window",
        "metadata": {
            "draft_id": draft_id,
            "draft_name": draft.get("name"),
            "league_id": draft.get("league_id"),
            "league_name": draft.get("league_name"),
        },
        "prior_state": {
            "status": "archived",
            "archived_at": draft.get("archived_at"),
        },
        "mocked": False,
        "ts": _dt.now(_tz.utc).isoformat(),
    })

    return {"draft_id": draft_id, "status": "scheduled"}


@router.patch("/drafts/{draft_id}")
async def patch_draft(draft_id: str, body: dict, request: Request):
    """Iter 228n — Edit a scheduled draft.

    Commissioners (and admins) can correct draft metadata while the
    draft is still `status="scheduled"`. Active/completed/archived
    drafts are immutable here to preserve integrity (use the dedicated
    pick-swap / restore endpoints for those flows).

    Whitelisted editable fields: name, scheduled_time, total_rounds,
    time_per_pick, missed_pick_action, defer_user_options, draft_type,
    snake_draft, player_criteria, exclude_previously_drafted,
    minors_eligibility_required, round_time_overrides.
    """
    user = await _get_user(request)
    try:
        draft = await _db().drafts.find_one({"_id": ObjectId(draft_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid draft_id")
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")

    league = await _db().leagues.find_one({"_id": ObjectId(draft["league_id"])})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    is_commish = (
        league.get("commissioner_id") == user["_id"]
        or user["_id"] in (league.get("co_commissioners") or [])
        or user.get("role") == "admin"
    )
    if not is_commish:
        raise HTTPException(status_code=403, detail="Commissioner or admin only")

    if draft.get("status") != "scheduled":
        raise HTTPException(
            status_code=400,
            detail=f"Only scheduled drafts can be edited (this draft is '{draft.get('status')}').",
        )

    EDITABLE = {
        "name", "scheduled_time", "total_rounds", "time_per_pick",
        "missed_pick_action", "defer_user_options", "draft_type",
        "snake_draft", "player_criteria", "round_time_overrides",
        # Iter 228n — New eligibility filters surfaced in the create-draft
        # form. Editing them here lets commissioners correct mid-stride
        # before the draft starts.
        "exclude_previously_drafted", "minors_eligibility_required",
    }
    update: dict = {}
    for k, v in (body or {}).items():
        if k in EDITABLE:
            update[k] = v
    if not update:
        raise HTTPException(status_code=400, detail="No editable fields supplied")

    # Range checks
    if "total_rounds" in update:
        try:
            tr = int(update["total_rounds"])
            if not (1 <= tr <= 100):
                raise ValueError()
            update["total_rounds"] = tr
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="total_rounds must be an int 1-100")
    if "time_per_pick" in update:
        try:
            tpp = int(update["time_per_pick"])
            if not (30 <= tpp <= 86400):
                raise ValueError()
            update["time_per_pick"] = tpp
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="time_per_pick must be 30-86400 seconds")

    await _db().drafts.update_one(
        {"_id": ObjectId(draft_id)}, {"$set": update}
    )

    # Iter 228p — Sync the `draft_picks` collection when total_rounds
    # changes. Previously the draft document picked up the new count
    # but the per-team Roster Draft Picks card stayed stale (root cause
    # of "edited # of picks but they didn't reduce on roster").
    if "total_rounds" in update:
        old_rounds = int(draft.get("total_rounds") or 0)
        new_rounds = int(update["total_rounds"])
        try:
            if new_rounds > old_rounds:
                # Grow: seed extra rows. `_seed_draft_picks_for_draft`
                # is idempotent on (league_id, year, round, original_team_id)
                # so reseeding will only insert the missing rounds.
                season = str(league.get("season") or "2026").split("-")[0]
                await _seed_draft_picks_for_draft(
                    draft_id=draft_id,
                    league_id=draft["league_id"],
                    rounds=new_rounds,
                    year=int(season),
                )
            elif new_rounds < old_rounds:
                # Shrink: drop pick rows for rounds > new_rounds, but
                # protect any pick that's been traded or used (has
                # `trade_history` entries or is referenced in a pick).
                # Scheduled drafts shouldn't have used picks, but
                # trade activity may have happened on future-round picks.
                doomed = await _db().draft_picks.find({
                    "draft_id": draft_id,
                    "round": {"$gt": new_rounds},
                }, {"_id": 1, "round": 1, "trade_history": 1}).to_list(2000)
                deletable_ids = [
                    p["_id"] for p in doomed
                    if not (p.get("trade_history") or [])
                ]
                if deletable_ids:
                    await _db().draft_picks.delete_many({
                        "_id": {"$in": deletable_ids},
                    })
        except Exception as ex:
            import logging
            logging.getLogger("drafts").warning(
                f"Failed to sync draft_picks for {draft_id} on total_rounds change: {ex}")

    fresh = await _db().drafts.find_one({"_id": ObjectId(draft_id)}, {"team_map": 0})
    fresh["_id"] = str(fresh["_id"])

    # Broadcast so connected Draft Room clients refresh in real time.
    # Iter 228q — Also broadcast to the league-wide channel so the
    # Rosters page (which doesn't know the active draft_id) refreshes
    # its TeamDraftPicks card on every commissioner edit.
    try:
        await _broadcast(
            f"draft_{draft_id}",
            "draft_edited",
            {"draft_id": draft_id, "fields": list(update.keys())},
        )
        await _broadcast(
            f"league_{draft['league_id']}",
            "draft_edited",
            {
                "draft_id": draft_id,
                "league_id": draft["league_id"],
                "fields": list(update.keys()),
            },
        )
    except Exception:
        pass

    return {"draft": fresh, "updated_fields": list(update.keys())}



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

    # Get already-drafted player IDs (in THIS draft only)
    drafted_ids = [p["player_id"] for p in draft.get("picks", []) if p.get("player_id")]

    # Iter 228n — Optional eligibility filters surfaced as draft-config
    # checkboxes. `exclude_previously_drafted` removes any player ever
    # drafted by ANY team in this league (full historical audit, per the
    # user's preference). `minors_eligibility_required` keeps only
    # players flagged `minor_eligible: true`.
    league_id_str = draft.get("league_id")
    if draft.get("exclude_previously_drafted") and league_id_str:
        historical = await _db().drafts.find(
            {
                "league_id": league_id_str,
                "_id": {"$ne": draft["_id"]},
                "status": {"$in": ["scheduled", "active", "completed"]},
            },
            {"picks": 1},
        ).to_list(500)
        for past in historical:
            for p in past.get("picks") or []:
                pid = p.get("player_id")
                if pid:
                    drafted_ids.append(pid)

    query = {}
    if drafted_ids:
        unique_oids = list({pid for pid in drafted_ids})
        query["_id"] = {"$nin": [ObjectId(pid) for pid in unique_oids]}

    if draft.get("minors_eligibility_required"):
        query["minor_eligible"] = True

    # Iter 170o — Criteria-aware filter. "entry" → prospect pool only;
    # "open" / anything else → all NHL skaters/goalies (no prospects).
    # `player_criteria` can be either a legacy string OR a list (modern
    # multi-select); normalise to a single canonical lowercase string.
    raw_crit = draft.get("player_criteria")
    if isinstance(raw_crit, list):
        criteria = (raw_crit[0] if raw_crit else "open")
    else:
        criteria = raw_crit or "open"
    criteria = str(criteria).lower()
    if criteria == "entry":
        query["player_type"] = "prospect"
    else:
        query["player_type"] = {"$ne": "prospect"}

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
        # Iter 173 — Prospects don't have NHL headshots; skip the URL so
        # the frontend renders the initials avatar instead of a broken img.
        player_type = p.get("player_type") or "skater"
        is_prospect = player_type == "prospect"
        headshot = (
            f"https://assets.nhle.com/mugs/nhl/20252026/{p.get('team', 'NHL')}/{p.get('nhl_id', '')}.png"
            if p.get("nhl_id") and not is_prospect else None
        )
        # For prospects, the "league" they play in is their amateur league
        # (OHL/WHL/SHL/…), not "NHL". For NHL players, fall back to "NHL".
        league_label = p.get("amateur_league") if is_prospect else "NHL"
        if not league_label:
            league_label = "NHL"
        # display_name strips the "(Prospect)" suffix added at seed time so
        # the UI shows the real human name.
        display_name = p.get("display_name") or p["name"]
        result.append({
            "id": str(p["_id"]),
            "name": display_name,
            "position": p["position"],
            "nhlTeam": p.get("team", ""),
            "team_name": p.get("team_name", ""),
            "age": p.get("age", 0),
            "league": league_label,
            "gp": p.get("games_played", 0),
            "g": p.get("goals", 0),
            "a": p.get("assists", 0),
            "pts": p.get("points", 0),
            "plus_minus": p.get("plus_minus", 0),
            "ranking": skip + i + 1,
            "drafted": False,
            "headshot": headshot,
            "nhl_id": p.get("nhl_id"),
            # Iter 173 — expose prospect status so the Draft Room + Player
            # Cards can render a "Minor-eligible" affordance when the
            # league has minors_enabled. `minor_eligible` is a derived
            # convenience flag that mirrors `player_type == "prospect"`.
            "player_type": player_type,
            "minor_eligible": is_prospect,
        })

    return {"players": result, "total": total, "page": page, "pages": (total + limit - 1) // limit}


# ─── Iter 231r — auto_init_draft + start_draft + auto_pick_for_on_clock_team
#     extracted to routes/draft_lifecycle.py.


async def _early_start_clock_msg(draft: dict) -> str:
    """Iter 231n — Thin re-export shim. Real impl in `routes/draft_helpers.py`."""
    from routes.draft_helpers import early_start_clock_msg as _impl
    return await _impl(draft)

# ─── Iter 170g/170h — make-pick, undo-pick, swap-pick, pause endpoints
#     extracted to routes/draft_pick_actions.py (iter 231m).


# ─── Iter 170j — Auto-pick on Timeout ─────────────────────────────────


async def _perform_one_auto_pick(draft_id: str, *, source: str = "timeout") -> dict:
    """Iter 231n — Thin re-export shim. Real impl in `routes/draft_helpers.py`.

    Kept as a shim because (a) `auto_pick_for_on_clock_team` (extracted
    in iter 231r) and admin_user_actions both used to import it from
    here, and (b) several pytest files grep for
    `async def _perform_one_auto_pick` in drafts.py source as a
    regression guard.
    """
    from routes.draft_helpers import perform_one_auto_pick as _impl
    return await _impl(draft_id, source=source)


# Iter 231r — auto_pick_for_on_clock_team extracted to draft_lifecycle.py.


# Iter 170j Draft Queue + Iter 170m Shortlist endpoints extracted to
# `routes/draft_queue.py` (iter 231k).

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


async def create_notification(user_id: str, notif_type: str, title: str, message: str, league_id: str = None, link: str = None, reason: dict = None):
    """Create a notification and broadcast it via WebSocket + Expo push.

    Iter 230 — Honours per-user preferences from `notification_preferences`.
    The `in_app` channel gates the DB write + socket broadcast; `push` gates
    the Expo task. The catalog's default_channels list seeds new users.

    Iter 230h — `reason` (optional dict) is persisted alongside the
    notification so the frontend's "Why am I being notified?" affordance
    can explain the source: signal type, originating service, player
    matched, team rostering, etc. Free-form, no schema enforcement so
    each emitter can include whatever helps the user.
    """
    # Lazy import to avoid an init-time cycle (notification_preferences may
    # not be wired yet during module import).
    try:
        from routes.notification_preferences import channel_enabled
    except Exception:
        channel_enabled = None  # type: ignore

    in_app_on = True
    push_on = True
    if channel_enabled is not None:
        try:
            in_app_on = await channel_enabled(user_id, notif_type, "in_app", league_id)
            push_on = await channel_enabled(user_id, notif_type, "push", league_id)
        except Exception as e:
            logger.debug(f"channel_enabled check failed: {e}")

    if not in_app_on:
        # User opted out — don't persist or broadcast in-app.
        return None

    doc = {
        "user_id": user_id,
        "type": notif_type,
        "title": title,
        "message": message,
        "league_id": league_id,
        "link": link,
        "reason": reason or None,
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
    # Fire an Expo push in parallel (non-blocking best-effort) — only when
    # the user has the push channel enabled for this event type.
    if push_on:
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





# Auction Draft Engine endpoints extracted to routes/draft_auction.py (iter 231k).



# ─── Iter 228e — Per-pick defer_user_options endpoints extracted to
#     `routes/draft_picks.py` (iter 231l). DeferPickChoiceRequest and
#     both /picks/{pick_no}/defer endpoints now live there.


# ─── Iter 228i — Retroactive pick seeding endpoint extracted to
#     routes/draft_pick_actions.py (iter 231m).
