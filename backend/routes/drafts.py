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
    """Iter 228h helper — materialises `rounds × team-count` draft_picks
    rows for a freshly-created draft so they're immediately visible in
    the trade center and draft board.

    Teams are ordered alphabetically when the league hasn't saved a
    pick order yet — deterministic and trivially overridable later.
    Idempotent on (league_id, year, round, original_team_id).
    """
    from datetime import datetime as _dt, timezone as _tz

    teams = await _db().teams.find({"league_id": league_id}).to_list(200)
    if not teams:
        return 0
    # Honour saved pick order when present, else alphabetical
    saved_order_doc = await _db().draft_order_config.find_one({"league_id": league_id})
    saved_order = (saved_order_doc or {}).get("pick_order") or []
    if saved_order:
        order_index = {tid: idx for idx, tid in enumerate(saved_order)}
        teams.sort(key=lambda t: order_index.get(str(t["_id"]), 9999))
    else:
        teams.sort(key=lambda t: (t.get("name") or "").lower())

    inserted = 0
    now = _dt.now(_tz.utc)
    for r in range(1, rounds + 1):
        for slot, team in enumerate(teams, start=1):
            tid = str(team["_id"])
            # Iter 228s — Include `draft_id` in the dedup key so the
            # league can have multiple drafts in the SAME year (e.g.
            # Inaugural in May + Summer Entry in July + Winter in
            # December — all 2026) and each gets its OWN independent
            # set of pick rows. Without this guard, the second and
            # third drafts found existing rows from the first and
            # skipped every insert.
            existing = await _db().draft_picks.find_one({
                "league_id": league_id,
                "draft_id": draft_id,
                "year": year,
                "round": r,
                "original_team_id": tid,
            })
            if existing:
                continue
            await _db().draft_picks.insert_one({
                "league_id": league_id,
                "draft_id": draft_id,
                "year": year,
                "round": r,
                "slot": slot,
                "overall": (r - 1) * len(teams) + slot,
                "original_team_id": tid,
                "original_team_name": team.get("name") or "Unknown",
                "current_team_id": tid,
                "current_team_name": team.get("name") or "Unknown",
                "trade_history": [],
                "tradeable": True,
                "created_at": now,
            })
            inserted += 1
    return inserted

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


# ─── Iter 170g — Auto-init draft for a league ─────────────────────────
# Used by the Draft Room on mount: returns the most-recent draft for the
# league, creating one with sensible defaults if none exists yet. Idempotent
# — re-running returns the existing draft. Commissioner-only.

@router.post("/drafts/auto-init/{league_id}")
async def auto_init_draft(league_id: str, request: Request, commit: bool = False):
    """Initialise (or fetch) the league's draft.

    Iter 231 — `commit=False` (the default) returns a **preview** shape
    WITHOUT persisting to the database. The preview carries the league's
    current team_map + roster-cap-derived `total_rounds`, but `_id` is
    `None` and the response is tagged `preview: True`. This lets the
    Draft Room render correctly on first load WITHOUT creating an empty
    stub draft every time a commissioner clicks into the page.

    `commit=True` (the legacy behaviour) materialises the draft into
    `db.drafts` and runs the pick-seed safety net. The frontend
    triggers `commit=True` only when the user takes an explicit action
    (clicking *Start Draft* or *Schedule Draft*). Existing drafts are
    always returned as-is regardless of the flag — the heal-and-return
    fast path is unchanged.
    """
    user = await _get_user(request)
    league = await _db().leagues.find_one({"_id": ObjectId(league_id)})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    is_comm = league["commissioner_id"] == user["_id"]
    co_comms = league.get("co_commissioners", []) or []
    if not (is_comm or user["_id"] in co_comms):
        raise HTTPException(status_code=403, detail="Only commissioners can auto-init drafts")

    # Iter 228k — Derive total_rounds from the league's roster capacity
    # (active + bench + minors) so the Draft Board renders the full
    # roster height instead of the legacy default of 5.
    roster_cap = (
        int(league.get("roster_spots") or 0)
        + int(league.get("bench_spots") or 0)
        + int(league.get("minors_spots") or 0)
    )
    default_rounds = roster_cap if roster_cap > 0 else 5

    # Iter 231f — Bug fix: previously this looked up "any" draft for the
    # league, including ARCHIVED ones. That let the auto-init flow re-
    # surface a deleted draft (the user "thought" they had cleaned up),
    # and downstream start_draft happily flipped it back to `active`. We
    # now strictly exclude archived rows so the existing-draft fast path
    # only returns live drafts. The rogue resurrection bug is fully
    # guarded by `test_iter231f_archived_draft_guards.py`.
    existing = await _db().drafts.find_one(
        {
            "league_id": league_id,
            "status": {"$ne": "archived"},
        },
        sort=[("created_at", -1)],
    )
    if existing:
        existing_draft_id = str(existing["_id"])
        # Iter 228k — Heal legacy drafts that were auto-init'd with the
        # old `total_rounds=5` default. Only bumps when no picks have
        # been made yet (preserving in-progress drafts) and the roster
        # cap is meaningfully larger than the stored value.
        if (
            not existing.get("picks")
            and roster_cap > 0
            and int(existing.get("total_rounds") or 0) < roster_cap
            and existing.get("status") != "active"
        ):
            await _db().drafts.update_one(
                {"_id": existing["_id"]},
                {"$set": {"total_rounds": roster_cap}},
            )
            existing["total_rounds"] = roster_cap

        # Iter 228k — Auto-seed safety net. When the draft exists but
        # the `draft_picks` collection has zero rows for this league, run
        # the seed-picks helper transparently so the Draft Board /
        # Trade Center are never blank after a commissioner opens the
        # Draft Room. Broadcast so already-connected clients refresh.
        existing_picks_count = await _db().draft_picks.count_documents({
            "league_id": league_id,
        })
        if existing_picks_count == 0:
            try:
                season = str(league.get("season") or "2026").split("-")[0]
                inserted = await _seed_draft_picks_for_draft(
                    draft_id=existing_draft_id,
                    league_id=league_id,
                    rounds=int(existing.get("total_rounds") or default_rounds),
                    year=int(season),
                )
                if inserted > 0:
                    await _broadcast(
                        f"draft_{existing_draft_id}",
                        "draft_picks_seeded",
                        {
                            "draft_id": existing_draft_id,
                            "league_id": league_id,
                            "picks_inserted": inserted,
                        },
                    )
            except Exception:
                # Seeding is best-effort; never block the Draft Room load.
                pass

        existing["_id"] = existing_draft_id
        existing.pop("team_map", None)
        # Iter 173 — Surface the league's minors_enabled flag so the Draft
        # Room can render a "Minor-eligible" affordance on prospects.
        existing["league_minors_enabled"] = bool(league.get("minors_enabled"))
        return {"draft": existing, "created": False}

    teams = await _db().teams.find({"league_id": league_id}).to_list(100)
    if not teams:
        raise HTTPException(status_code=400, detail="League has no teams")
    team_abbrs, team_map = _abbrs_with_dedup(teams)

    # Iter 231 — Preview mode: return the would-be draft shape WITHOUT
    # writing to the database. The Draft Room uses this to render a
    # placeholder board so commissioners can see what their draft will
    # look like before scheduling. No `_id` is issued — the frontend
    # detects `preview: true` and disables pick / start actions until a
    # commissioner materialises the draft (commit=true).
    if not commit:
        preview_doc = {
            "_id": None,
            "league_id": league_id,
            "league_name": league.get("name"),
            "draft_type": "snake",
            "scheduled_time": None,
            "total_rounds": default_rounds,
            "time_per_pick": 120,
            "snake_draft": True,
            "player_criteria": "open",
            "missed_pick_action": "skip",
            "current_pick": 1,
            "status": "preview",
            "draft_started": False,
            "early_start": False,
            "timer_paused": False,
            "team_abbrs": team_abbrs,
            "picks": [],
            "chat_messages": [],
            "league_minors_enabled": bool(league.get("minors_enabled")),
        }
        return {"draft": preview_doc, "created": False, "preview": True}

    draft_doc = {
        "league_id": league_id,
        "league_name": league.get("name"),
        "draft_type": "snake",
        "scheduled_time": None,
        "total_rounds": default_rounds,
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
    new_draft_id = str(res.inserted_id)
    draft_doc["_id"] = new_draft_id
    draft_doc.pop("team_map", None)
    # Iter 173 — surface league minors_enabled for the Draft Room badges.
    draft_doc["league_minors_enabled"] = bool(league.get("minors_enabled"))

    # Iter 228k — Auto-seed the freshly-created draft so the trade center
    # and Draft Board have rows immediately.
    try:
        season = str(league.get("season") or "2026").split("-")[0]
        inserted = await _seed_draft_picks_for_draft(
            draft_id=new_draft_id,
            league_id=league_id,
            rounds=default_rounds,
            year=int(season),
        )
        if inserted > 0:
            await _broadcast(
                f"draft_{new_draft_id}",
                "draft_picks_seeded",
                {
                    "draft_id": new_draft_id,
                    "league_id": league_id,
                    "picks_inserted": inserted,
                },
            )
    except Exception:
        pass

    return {"draft": draft_doc, "created": True}

@router.post("/drafts/{draft_id}/start")
async def start_draft(draft_id: str, request: Request, early_start: bool = False):
    user = await _get_user(request)

    draft = await _db().drafts.find_one({"_id": ObjectId(draft_id)})
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")

    league = await _db().leagues.find_one({"_id": ObjectId(draft["league_id"])})
    is_commissioner = league["commissioner_id"] == user["_id"]

    # Iter 231f — Bug fix: previously start_draft happily activated
    # archived drafts because there was no status guard. Combined with
    # the auto_init_draft bug (which returned archived drafts as the
    # "existing" draft), this caused chriszarek's deleted Ice Kings H2H
    # E2E test draft to resurrect itself on 2026-06-26. We now reject
    # archived drafts at the start endpoint as a defense-in-depth check
    # — even if a caller somehow obtains the archived draft id, /start
    # will refuse to activate it.
    if draft.get("status") == "archived":
        raise HTTPException(
            status_code=400,
            detail="This draft has been archived. Restore it first if you need to start it again.",
        )

    # Iter 230an — Idempotency: if the draft is already active, return
    # success rather than 400. Multiple managers / browser tabs hitting
    # the auto-start endpoint at the same moment is normal — the first
    # one wins; the rest get a no-op response.
    if draft["status"] == "active":
        return {"message": "Draft already active", "early_start": draft.get("early_start", False), "already_active": True}

    # Iter 230an — Allow auto-start (non-commissioner trigger) ONLY when
    # the scheduled time has elapsed. The frontend countdown hook calls
    # this once the clock hits 0:00 so any team's manager (or
    # commissioner, or a background worker) can boot the draft without
    # the league owner needing to be online. Commissioners can always
    # start at any time.
    if not is_commissioner:
        scheduled_at = draft.get("scheduled_time")
        if not scheduled_at:
            raise HTTPException(status_code=403, detail="Only commissioner can start draft")
        try:
            from datetime import datetime as _dt
            sched_dt = _dt.fromisoformat(str(scheduled_at).replace("Z", "+00:00"))
            if sched_dt.tzinfo is None:
                sched_dt = sched_dt.replace(tzinfo=timezone.utc)
        except Exception:
            raise HTTPException(status_code=403, detail="Only commissioner can start draft")
        if sched_dt > datetime.now(timezone.utc):
            raise HTTPException(status_code=403, detail="Draft scheduled time has not yet arrived")

    # Iter 230an — Refresh team_abbrs / team_map from the CURRENT set of
    # league teams. Drafts created before all teams joined the league
    # had stale abbr lists (e.g. TFHL's Inaugural Draft had only HC
    # populated even after 24 teams joined). Re-derive on start so the
    # draft proceeds with the right team set.
    fresh_teams = await _db().teams.find({"league_id": draft["league_id"]}).to_list(200)
    if fresh_teams and len(fresh_teams) > len(draft.get("team_abbrs") or []):
        team_abbrs, team_map = _abbrs_with_dedup(fresh_teams)
    else:
        team_abbrs = draft.get("team_abbrs") or []
        team_map = draft.get("team_map") or {}

    update = {
        "$set": {
            "status": "active",
            "draft_started": True,
            "early_start": early_start,
            "current_pick": 1,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "current_pick_started_at": datetime.now(timezone.utc).isoformat(),
            "team_abbrs": team_abbrs,
            "team_map": team_map,
        }
    }
    await _db().drafts.update_one({"_id": ObjectId(draft_id)}, update)

    # Broadcast draft start
    await _broadcast(f"draft_{draft_id}", "draft_started", {
        "draft_id": draft_id,
        "early_start": early_start,
        "team_abbrs": team_abbrs,
        "on_the_clock": team_abbrs[0] if team_abbrs else None
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

    # Iter 230y / 230an — Notify pick #1 (on the clock) and pick #2
    # (on deck) the moment the draft starts. Previously this was gated
    # behind `if early_start:` so a normal clock-started draft fired
    # ZERO notifications until the first pick was made — leaving the
    # first manager unaware they were up. Now ALWAYS notify the first
    # two picks; the body adapts to early-start (clock-activation hint)
    # vs. timer-started (standard "you're on the clock") via the
    # `_early_start_clock_msg` helper which returns "" for non-early.
    try:
        from routes.notification_events import EVT_DRAFT_YOUR_TURN, EVT_DRAFT_ON_DECK
        updated_draft = await _db().drafts.find_one({"_id": ObjectId(draft_id)})
        clock_hint = await _early_start_clock_msg(updated_draft or draft)
        team_abbrs = (updated_draft or draft).get("team_abbrs") or []
        team_map = (updated_draft or draft).get("team_map") or {}
        league_name = (updated_draft or draft).get("league_name") or ""
        draft_name = (updated_draft or draft).get("name") or "your draft"
        league_id_str = str(draft["league_id"])

        # Iter 230aj — Notify BOTH pick #1 (your turn) AND pick #2 (on
        # deck) the moment the draft boots up.
        picks_to_notify = [
            (EVT_DRAFT_YOUR_TURN, 1, "You're on the clock!",   "Pick #1 — make your selection."),
            (EVT_DRAFT_ON_DECK,   2, "On deck",                 "Pick #2 — you're up next."),
        ]
        for (event, pick_no, title, body_prefix) in picks_to_notify:
            if pick_no > len(team_abbrs):
                continue  # tiny league — skip whichever notify is OOB.
            abbr = team_abbrs[pick_no - 1]
            team_id = (team_map.get(abbr) or {}).get("id")
            if not team_id:
                continue
            team_doc = await _db().teams.find_one(
                {"_id": ObjectId(team_id)},
                {"owner_id": 1, "co_owner_ids": 1, "name": 1},
            )
            if not team_doc:
                continue
            owners = [team_doc.get("owner_id")] + list(team_doc.get("co_owner_ids") or [])
            body_text = body_prefix + clock_hint
            for uid in [u for u in owners if u]:
                await create_notification(
                    uid, event, title, body_text, league_id_str, "/draft-room",
                )
                # Iter 230ab — Email pipe (only for the "your turn"
                # event — on-deck stays in-app to avoid email noise
                # before the manager is actually on the clock).
                if event != EVT_DRAFT_YOUR_TURN:
                    continue
                try:
                    owner_doc = await _db().users.find_one(
                        {"_id": ObjectId(uid)},
                        {"email": 1, "name": 1},
                    )
                    if owner_doc and owner_doc.get("email"):
                        subj = f"You're on the clock — {draft_name}"
                        clock_note = (
                            f" {clock_hint.strip()}" if (early_start and clock_hint)
                            else " The clock is running — make your selection in the Draft Room."
                        )
                        html = (
                            f"<p>Hi {owner_doc.get('name') or 'manager'},</p>"
                            f"<p><b>{draft_name}</b>"
                            f"{(' in ' + league_name) if league_name else ''} has started.</p>"
                            f"<p>You're up for <b>Pick #{pick_no}</b>.{clock_note}</p>"
                            f"<p><a href=\"/draft-room\">Open the Draft Room →</a></p>"
                        )
                        _send_email(owner_doc["email"], subj, html)
                except Exception as e:
                    logger.debug(f"start_draft email skipped for {uid}: {e}")
    except Exception as e:
        logger.debug(f"start_draft notification skipped: {e}")

    return {"message": "Draft started", "early_start": early_start}


async def _early_start_clock_msg(draft: dict) -> str:
    """Iter 230y — Render the per-notification clock-activation hint
    used when the commissioner starts a draft with `early_start=True`.

    Returns the empty string if the clock isn't going to auto-activate
    (no `scheduled_time` set or it's already in the past). Otherwise
    returns a short ` Clock activates HH:MM (your time) — pick now if
    you want to, or wait for the clock.` suffix the caller appends to
    the standard `You're on the clock!` body.
    """
    if not draft.get("early_start"):
        return ""
    sched = draft.get("scheduled_time")
    if not sched:
        return ""
    try:
        sched_dt = datetime.fromisoformat(str(sched).replace("Z", "+00:00"))
    except Exception:
        return ""
    if sched_dt <= datetime.now(timezone.utc):
        return ""
    iso = sched_dt.isoformat().replace("+00:00", "Z")
    return (
        " The clock will start at " + iso +
        " — pick now if you want to, or wait."
    )

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
            "$set": {"current_pick": next_pick, "status": new_status,
                     # Iter 230ar — Track the wall-clock moment the
                     # next pick is now ON the clock so /state can
                     # surface a server-authoritative remaining time
                     # (frontend was resetting to the full duration
                     # on every page mount).
                     "current_pick_started_at": datetime.now(timezone.utc).isoformat()},
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

    # Iter 230an — Build the system chat message BEFORE the notification
    # fan-out so the EVT_DRAFT_PICK_MADE body can reference `pick_msg`
    # without crashing the try/except (which would swallow the entire
    # block — including the on-deck / coming-up notifications that
    # depend on it).
    pick_msg = {
        "id": f"pick-{current_pick}",
        "type": "pick",
        "sender": "System",
        "text": f"Pick #{current_pick} (Rd {round_num}, Pick {pick_in_round}): {on_clock} selects {player['name']} ({player['position']})",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    await _db().drafts.update_one({"_id": ObjectId(draft_id)}, {"$push": {"chat_messages": pick_msg}})
    await _broadcast(f"draft_{draft_id}", "draft_chat", pick_msg)

    # Iter 230 — In-app notifications for draft events. Fan out
    # "any pick made" league-wide (off-by-default), then the targeted
    # "your turn"/"on deck"/"coming up within 5" notifications for
    # the upcoming pickers.
    try:
        from routes.notification_events import (
            EVT_DRAFT_PICK_MADE,
            EVT_DRAFT_YOUR_TURN,
            EVT_DRAFT_ON_DECK,
            EVT_DRAFT_COMING_UP,
        )
        league_id_str = str(draft["league_id"])
        all_team_docs = await _db().teams.find(
            {"league_id": league_id_str},
            {"_id": 1, "owner_id": 1, "co_owner_ids": 1, "name": 1},
        ).to_list(200)
        team_by_id = {str(t["_id"]): t for t in all_team_docs}

        def _owners(team_doc: dict) -> list:
            out: list = []
            if team_doc.get("owner_id"):
                out.append(team_doc["owner_id"])
            for co in (team_doc.get("co_owner_ids") or []):
                if co:
                    out.append(co)
            return out

        # 1. "Any pick made" fanout (default OFF in user prefs).
        for t in all_team_docs:
            for uid in _owners(t):
                await create_notification(
                    uid,
                    EVT_DRAFT_PICK_MADE,
                    "Draft pick made",
                    pick_msg["text"],
                    league_id_str,
                    "/draft-room",
                )

        # 2. Look ahead — find the next 5 picks and notify their owners
        # with progressively-targeted events (turn → on deck → coming up).
        if new_status == "active":
            # Iter 230y — When the draft is running in early-start /
            # no-clock mode, append the clock-activation hint to the
            # "your turn" body so the on-the-clock manager knows they
            # can take their time until the originally-scheduled clock
            # kicks in (or pick early if they want to).
            early_clock_hint = await _early_start_clock_msg(draft)
            for offset in range(0, 5):
                future_pick = next_pick + offset
                if future_pick > total_picks:
                    break
                future_abbr = get_team_for_pick(draft["team_abbrs"], future_pick, draft["snake_draft"])
                future_team_id = (draft.get("team_map") or {}).get(future_abbr, {}).get("id")
                future_team = team_by_id.get(future_team_id) if future_team_id else None
                if not future_team:
                    continue
                if offset == 0:
                    event = EVT_DRAFT_YOUR_TURN
                    title = "You're on the clock!"
                    body = f"Pick #{future_pick} — make your selection." + early_clock_hint
                elif offset == 1:
                    event = EVT_DRAFT_ON_DECK
                    title = "You're on deck"
                    body = f"Your pick (#{future_pick}) is up next."
                else:
                    event = EVT_DRAFT_COMING_UP
                    title = f"Your pick is in {offset} picks"
                    body = f"Pick #{future_pick} is coming up — get your queue ready."
                for uid in _owners(future_team):
                    await create_notification(
                        uid,
                        event,
                        title,
                        body,
                        league_id_str,
                        "/draft-room",
                    )
    except Exception as e:
        logger.debug(f"draft pick notifications skipped: {e}")

    if new_status == "completed":
        complete_msg = {
            "id": "sys-complete",
            "type": "pick",
            "sender": "System",
            "text": "Draft is complete! All picks have been made.",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        await _db().drafts.update_one({"_id": ObjectId(draft_id)}, {"$push": {"chat_messages": complete_msg}})
        await _broadcast(f"draft_{draft_id}", "draft_chat", complete_msg)
        await _broadcast(f"draft_{draft_id}", "draft_completed", {"draft_id": draft_id})

        # Iter 218 — Auto-snapshot all teams in the league after draft completes
        try:
            draft_doc = await _db().drafts.find_one({"_id": ObjectId(draft_id)})
            if draft_doc:
                league_id = draft_doc.get("league_id")
                team_ids = [str(t["_id"]) async for t in _db().teams.find(
                    {"league_id": str(league_id)}, {"_id": 1}
                )]
                if team_ids:
                    from services.auto_snapshot import auto_snapshot
                    await auto_snapshot(_db(), team_ids,
                                        trigger="draft_complete",
                                        metadata={"draft_id": draft_id,
                                                  "league_id": str(league_id)})
        except Exception:
            pass  # snapshot failure must never block draft completion

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
        {"$set": {"picks": kept, "current_pick": new_current, "status": new_status,
                  # Iter 230ar — Reset the per-pick clock anchor on
                  # undo so the timer restarts for the resurrected
                  # pick rather than continuing from the old slot's
                  # countdown.
                  "current_pick_started_at": datetime.now(timezone.utc).isoformat()}},
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
    """Toggle the draft timer pause. Commissioner-only."""
    user = await _get_user(request)
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


# ─── Iter 170j — Auto-pick on Timeout ─────────────────────────────────


async def _perform_one_auto_pick(draft_id: str, *, source: str = "timeout") -> dict:
    """Iter 221 — Shared core for auto-picking the team currently on the clock.
    Returns the recorded pick document. Raises HTTPException on bad state.
    `source` is stamped into the pick doc / broadcast for audit (timeout,
    eviction, commissioner_skip, etc.).
    """
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
        criteria = (draft.get("player_criteria") or "open").lower()
        q = {"player_type": "prospect"} if criteria == "entry" else {"player_type": {"$ne": "prospect"}}
        async for p in _db().players.find(q).sort([("points", -1), ("name", 1)]):
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
        "auto_pick_source": source,
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
    label = "Auto-pick" if source != "eviction" else "Eviction auto-pick"
    msg = {
        "id": f"autopick-{datetime.now(timezone.utc).timestamp()}",
        "type": "pick",
        "sender": "System",
        "text": (
            f"⏱ {label} — {on_clock} took {chosen_player['name']} ({chosen_player['position']}) "
            f"at #{current_pick} (via {'queue' if via == 'queue' else 'top eligible'})"
        ),
        "auto_picked": True,
        "auto_pick_via": via,
        "auto_pick_source": source,
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
    return pick_doc


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
    pick_doc = await _perform_one_auto_pick(draft_id, source="timeout")
    return {"pick": pick_doc, "via": pick_doc.get("auto_pick_via")}


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



# ─── Iter 228e — Per-pick defer_user_options ──────────────────────


class DeferPickChoiceRequest(BaseModel):
    """Owner's choice when their pick timer expires and the draft's
    missed_pick_action is "defer-to-user".
    """
    choice: str  # "auto-best" | "auto-queue" | "pick-anytime"


@router.post("/drafts/{draft_id}/picks/{pick_no}/defer")
async def set_pick_defer_choice(
    draft_id: str, pick_no: int, body: DeferPickChoiceRequest, request: Request,
):
    """Records the owner's defer-to-user choice for a specific pick.
    Only callable by the team's owner; persists onto the pick document
    (was only on the draft level before iter 228e).

    Valid choices:
      • auto-best   — engine auto-selects the best available player NOW
      • auto-queue  — engine auto-selects the next-available from the
                      team's draft queue
      • pick-anytime — the pick is skipped (other rounds continue);
                      owner can return and pick anytime before draft end
    """
    user = await _get_user(request)
    valid = {"auto-best", "auto-queue", "pick-anytime"}
    if body.choice not in valid:
        raise HTTPException(
            status_code=400,
            detail=f"choice must be one of {sorted(valid)}",
        )
    try:
        draft = await _db().drafts.find_one({"_id": ObjectId(draft_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid draft_id")
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    if draft.get("missed_pick_action") != "defer-to-user":
        raise HTTPException(
            status_code=400,
            detail="This draft's missed_pick_action is not 'defer-to-user'.",
        )

    # Find the pick (1-indexed)
    picks = draft.get("picks") or []
    pick = next((p for p in picks if int(p.get("pick_no", 0)) == int(pick_no)), None)
    if pick is None:
        # Picks might not yet be materialized — allow pre-claiming the
        # choice by storing under a `pick_defer_choices` map on the draft.
        await _db().drafts.update_one(
            {"_id": ObjectId(draft_id)},
            {"$set": {
                f"pick_defer_choices.{pick_no}": {
                    "choice": body.choice,
                    "team_id": None,  # client may not know yet
                    "claimed_at": datetime.now(timezone.utc).isoformat(),
                    "claimed_by": user["_id"],
                },
            }},
        )
        return {"draft_id": draft_id, "pick_no": pick_no,
                "choice": body.choice, "stored": "pending"}

    # Auth: only the owner of this pick can set the choice (unless admin)
    pick_team_id = pick.get("team_id")
    if user.get("role") != "admin":
        team = await _db().teams.find_one({"_id": ObjectId(pick_team_id)}) if pick_team_id else None
        if not team or team.get("owner_id") != user["_id"]:
            raise HTTPException(status_code=403, detail="Only the pick's owner can set this.")

    # Atomic update on the pick itself
    await _db().drafts.update_one(
        {"_id": ObjectId(draft_id), "picks.pick_no": int(pick_no)},
        {"$set": {
            "picks.$.defer_choice": body.choice,
            "picks.$.defer_chosen_at": datetime.now(timezone.utc).isoformat(),
        }},
    )
    return {
        "draft_id": draft_id,
        "pick_no": pick_no,
        "team_id": pick_team_id,
        "choice": body.choice,
        "stored": "on_pick",
    }


@router.get("/drafts/{draft_id}/picks/{pick_no}/defer")
async def get_pick_defer_choice(draft_id: str, pick_no: int, request: Request):
    """Returns the persisted defer choice + the draft-level options the
    user can choose from. Surfaces both the per-pick state AND the
    available defer_user_options so the draft-room dialog has a single
    fetch instead of two."""
    await _get_user(request)
    try:
        draft = await _db().drafts.find_one({"_id": ObjectId(draft_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid draft_id")
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")

    picks = draft.get("picks") or []
    pick = next((p for p in picks if int(p.get("pick_no", 0)) == int(pick_no)), None)
    pending = (draft.get("pick_defer_choices") or {}).get(str(pick_no))
    available = draft.get("defer_user_options") or [
        "auto-best", "auto-queue", "pick-anytime",
    ]
    return {
        "draft_id": draft_id,
        "pick_no": pick_no,
        "available_options": available,
        "defer_choice": (pick or {}).get("defer_choice") or (pending or {}).get("choice"),
        "defer_chosen_at": (pick or {}).get("defer_chosen_at") or (pending or {}).get("claimed_at"),
    }


# ─── Iter 228i — Retroactive pick seeding for pre-iter228h drafts ──


@router.post("/drafts/{draft_id}/seed-picks")
async def seed_draft_picks(draft_id: str, request: Request):
    """Commissioner-only: materialise draft_picks rows for an existing
    draft. Useful when a draft was created with `pick_trading_enabled`
    BEFORE iter228h shipped the auto-gen logic, so the picks weren't
    populated and the trade-center inventory is empty.

    Idempotent — calls `_seed_draft_picks_for_draft` which skips rows
    that already exist on `(league_id, year, round, original_team_id)`.
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

    season = (league.get("season") or "2026").split("-")[0]
    inserted = await _seed_draft_picks_for_draft(
        draft_id=draft_id,
        league_id=draft["league_id"],
        rounds=int(draft.get("total_rounds") or 1),
        year=int(season),
    )
    return {
        "draft_id": draft_id,
        "league_id": draft["league_id"],
        "picks_inserted": inserted,
        "message": (
            f"Inserted {inserted} draft pick(s)" if inserted
            else "All picks already exist (idempotent re-run)"
        ),
    }
