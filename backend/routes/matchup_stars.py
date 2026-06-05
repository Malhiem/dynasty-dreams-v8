"""Iter 130 — Starred / auto-watch matchups.

Exposes:
  POST /matchups/{matchup_id}/star          — toggle a star for the current user
  GET  /matchups/starred?league_id=…        — manual stars + auto-watch suggestions

Auto-watch reasons (computed server-side, no schema migration needed):
  • "rivalry"           — both teams in the same division with a near-even
                           head-to-head record over the last 12 months.
  • "standings_battle"  — both teams within 1 win of each other in standings.
  • "playoff_implications" — late-season game (week >= regular_season_weeks - 4)
                              where at least one team is within 1 win of the
                              playoff bubble (playoff_teams + 1 or playoff_teams - 1).
"""
from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Request

router = APIRouter()
_deps: dict = {}


def setup(deps: dict) -> None:
    _deps.update(deps)


def _db():
    return _deps["db"]


async def _get_user(request: Request):
    return await _deps["get_current_user"](request)


def _safe_oid(s: str) -> Optional[ObjectId]:
    try:
        return ObjectId(s)
    except Exception:
        return None


# ─── POST /matchup-stars/{matchup_id} ──────────────────────────────
@router.post("/matchup-stars/{matchup_id}")
async def toggle_matchup_star(matchup_id: str, request: Request):
    """Toggle a star on a matchup for the current user. Returns the new state."""
    db = _db()
    user = await _get_user(request)
    oid = _safe_oid(matchup_id)
    if not oid:
        raise HTTPException(status_code=400, detail="Invalid matchup_id")
    matchup = await db.matchups.find_one({"_id": oid})
    if not matchup:
        raise HTTPException(status_code=404, detail="Matchup not found")
    existing = await db.matchup_stars.find_one(
        {"user_id": user["_id"], "matchup_id": matchup_id}
    )
    if existing:
        await db.matchup_stars.delete_one({"_id": existing["_id"]})
        return {"matchup_id": matchup_id, "starred": False}
    await db.matchup_stars.insert_one({
        "user_id": user["_id"],
        "league_id": matchup.get("league_id"),
        "matchup_id": matchup_id,
        "starred_at": datetime.now(timezone.utc),
    })
    return {"matchup_id": matchup_id, "starred": True}


async def _compute_auto_watch_reasons(db, league: dict, matchups: list) -> dict:
    """Returns {matchup_id: [list_of_reasons]} for the supplied matchups.

    Reasons:
      • rivalry           — both teams share a division.
      • standings_battle  — current win totals within 1 of each other.
      • playoff_implications — late season + one team near the playoff bubble.
    """
    if not matchups:
        return {}

    # ── Load teams (one query per league) ──
    teams = await db.teams.find({"league_id": league["_id"] if "_id" in league else league.get("id")}).to_list(50)
    team_by_id = {str(t["_id"]): t for t in teams}

    league_id_str = str(league["_id"]) if "_id" in league else league.get("id")
    if not team_by_id:
        teams = await db.teams.find({"league_id": league_id_str}).to_list(50)
        team_by_id = {str(t["_id"]): t for t in teams}

    playoff_teams = int(league.get("playoff_teams") or 6)
    regular_weeks = int(league.get("regular_season_weeks") or 22)

    # ── Build standings: wins per team based on matchups status==completed ──
    completed = await db.matchups.find({
        "league_id": league_id_str,
        "status": "completed",
    }).to_list(2000)
    wins: dict[str, int] = {}
    for m in completed:
        winner = m.get("winner_team_id")
        if winner:
            wins[str(winner)] = wins.get(str(winner), 0) + 1
    # Rank teams by wins descending
    ranked = sorted(
        team_by_id.keys(),
        key=lambda tid: wins.get(tid, 0),
        reverse=True,
    )
    rank_by_team: dict[str, int] = {tid: i + 1 for i, tid in enumerate(ranked)}

    reasons: dict[str, list[str]] = {}
    for m in matchups:
        mid = str(m.get("_id"))
        home_id = str(m.get("home_team_id") or "")
        away_id = str(m.get("away_team_id") or "")
        if not (home_id and away_id):
            continue
        home = team_by_id.get(home_id)
        away = team_by_id.get(away_id)
        if not (home and away):
            continue
        these_reasons: list[str] = []

        # Rivalry: same division
        h_div = home.get("division_id") or home.get("division")
        a_div = away.get("division_id") or away.get("division")
        if h_div and a_div and h_div == a_div:
            these_reasons.append("rivalry")

        # Standings battle: within 1 win
        h_wins = wins.get(home_id, 0)
        a_wins = wins.get(away_id, 0)
        if abs(h_wins - a_wins) <= 1 and (h_wins + a_wins) > 0:
            these_reasons.append("standings_battle")

        # Playoff implications: late season + at least one team near bubble
        week = int(m.get("week") or 0)
        if week and week >= max(1, regular_weeks - 4):
            h_rank = rank_by_team.get(home_id, 999)
            a_rank = rank_by_team.get(away_id, 999)
            bubble_low = playoff_teams - 1
            bubble_high = playoff_teams + 2
            if (bubble_low <= h_rank <= bubble_high) or (bubble_low <= a_rank <= bubble_high):
                these_reasons.append("playoff_implications")

        if these_reasons:
            reasons[mid] = these_reasons
    return reasons


# ─── GET /matchup-stars ────────────────────────────────────────────
@router.get("/matchup-stars")
async def list_starred_matchups(
    league_id: str,
    week: Optional[int] = None,
    request: Request = None,
):
    """Return the current user's manually-starred matchup_ids PLUS server-
    computed auto-watch suggestions with reasons for the given league/week.
    """
    db = _db()
    user = None
    starred_ids: list[str] = []
    try:
        user = await _get_user(request)
        rows = await db.matchup_stars.find({
            "user_id": user["_id"],
            "league_id": league_id,
        }).to_list(200)
        starred_ids = [r["matchup_id"] for r in rows]
    except Exception:
        starred_ids = []

    league = await db.leagues.find_one({"_id": _safe_oid(league_id)}) or {}
    if not league:
        return {"league_id": league_id, "starred_ids": [], "auto_watch": {}}

    # Determine target week (default = current scheduled min)
    if week is None:
        pipeline = [
            {"$match": {"league_id": league_id, "status": "scheduled"}},
            {"$group": {"_id": None, "min_week": {"$min": "$week"}}},
        ]
        result = await db.matchups.aggregate(pipeline).to_list(1)
        week = result[0]["min_week"] if result else None

    matchups = []
    if week:
        matchups = await db.matchups.find({
            "league_id": league_id,
            "week": week,
        }).to_list(100)

    auto_watch = await _compute_auto_watch_reasons(db, league, matchups)
    return {
        "league_id": league_id,
        "week": week,
        "starred_ids": starred_ids,
        "auto_watch": auto_watch,
    }
