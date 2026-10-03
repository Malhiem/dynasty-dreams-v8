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

    Reasons (Iter 131):
      • rivalry             — both teams share a division.
      • standings_battle    — current win totals within 1 of each other.
      • playoff_clinch      — a win clinches a playoff spot for at least one team
                               (their lead over the bubble is ≥ remaining games).
      • division_lead       — one team can clinch their division by winning.
      • conference_lead     — one team can clinch their conference by winning.
      • last_place_battle   — both teams in the bottom 2 of standings.
      • rank_jump           — a win flips standings position with the opponent.
      • playoff_implications — late season + bubble teams (legacy catch-all).
    """
    if not matchups:
        return {}

    league_id_str = str(league["_id"]) if "_id" in league else league.get("id")

    # Load teams (one query)
    teams = await db.teams.find({"league_id": league_id_str}).to_list(50)
    team_by_id = {str(t["_id"]): t for t in teams}

    playoff_teams = int(league.get("playoff_teams") or 6)
    regular_weeks = int(league.get("regular_season_weeks") or 22)

    # Standings via completed matchups
    completed = await db.matchups.find({
        "league_id": league_id_str,
        "status": "completed",
    }).to_list(2000)
    wins: dict[str, int] = {}
    for m in completed:
        winner = m.get("winner_team_id")
        if winner:
            wins[str(winner)] = wins.get(str(winner), 0) + 1

    ranked = sorted(team_by_id.keys(), key=lambda tid: wins.get(tid, 0), reverse=True)
    rank_by_team: dict[str, int] = {tid: i + 1 for i, tid in enumerate(ranked)}
    total_teams = len(ranked)
    last_two = set(ranked[-2:]) if total_teams >= 2 else set()

    # Group teams by division + conference for clinch detection
    teams_by_div: dict[str, list[str]] = {}
    teams_by_conf: dict[str, list[str]] = {}
    for tid, t in team_by_id.items():
        d = t.get("division_id") or t.get("division")
        c = t.get("conference_id") or t.get("conference")
        if d:
            teams_by_div.setdefault(d, []).append(tid)
        if c:
            teams_by_conf.setdefault(c, []).append(tid)

    def _leader_lead(tid: str, peers: list[str]) -> int:
        """How many wins the team leads the rest of `peers` by."""
        if not peers:
            return 0
        my = wins.get(tid, 0)
        rivals = [wins.get(p, 0) for p in peers if p != tid]
        if not rivals:
            return 0
        return my - max(rivals)

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

        # Standings battle: within 1 win, ranks adjacent
        h_wins = wins.get(home_id, 0)
        a_wins = wins.get(away_id, 0)
        if abs(h_wins - a_wins) <= 1 and (h_wins + a_wins) > 0:
            these_reasons.append("standings_battle")

        # Rank jump: a win flips order in standings
        if rank_by_team.get(home_id) and rank_by_team.get(away_id):
            if abs(rank_by_team[home_id] - rank_by_team[away_id]) == 1 and abs(h_wins - a_wins) <= 1:
                these_reasons.append("rank_jump")

        week = int(m.get("week") or 0)
        weeks_left = max(0, regular_weeks - week) if week else 0

        # Division / conference lead
        for tid, peers_dict, reason_name in (
            (home_id, teams_by_div, "division_lead"),
            (away_id, teams_by_div, "division_lead"),
            (home_id, teams_by_conf, "conference_lead"),
            (away_id, teams_by_conf, "conference_lead"),
        ):
            div_key = (team_by_id[tid].get("division_id") or team_by_id[tid].get("division")) \
                if reason_name == "division_lead" \
                else (team_by_id[tid].get("conference_id") or team_by_id[tid].get("conference"))
            if not div_key:
                continue
            peers = peers_dict.get(div_key, [])
            lead = _leader_lead(tid, peers)
            if lead >= max(1, weeks_left) and reason_name not in these_reasons:
                these_reasons.append(reason_name)

        # Playoff clinch: lead over bubble team ≥ weeks_left and team in playoff seeds
        bubble_team = ranked[playoff_teams] if total_teams > playoff_teams else None
        for tid in (home_id, away_id):
            if not bubble_team:
                continue
            if rank_by_team.get(tid, 999) <= playoff_teams:
                gap = wins.get(tid, 0) - wins.get(bubble_team, 0)
                if gap >= max(1, weeks_left) and "playoff_clinch" not in these_reasons:
                    these_reasons.append("playoff_clinch")

        # Last place battle: bottom 2 facing each other
        if home_id in last_two and away_id in last_two:
            these_reasons.append("last_place_battle")

        # Legacy late-season playoff implications (kept for back-compat)
        if week and week >= max(1, regular_weeks - 4):
            h_rank = rank_by_team.get(home_id, 999)
            a_rank = rank_by_team.get(away_id, 999)
            bubble_low = playoff_teams - 1
            bubble_high = playoff_teams + 2
            if ((bubble_low <= h_rank <= bubble_high) or (bubble_low <= a_rank <= bubble_high)) \
                    and "playoff_implications" not in these_reasons \
                    and "playoff_clinch" not in these_reasons:
                these_reasons.append("playoff_implications")

        if these_reasons:
            reasons[mid] = these_reasons
    return reasons


# ─── H2H records helper ──────────────────────────────────────────────
async def _compute_h2h_records(db, league_id: str, matchups: list) -> dict:
    """For each matchup, return {last_season: 'A-B', all_time: 'A-B',
    streak_wins: N, streak_team_id: '<oid>'} computed from historical
    `db.matchups` rows where status=='completed'. Streak is the longest
    current consecutive head-to-head win streak.
    """
    out: dict[str, dict] = {}
    if not matchups:
        return out

    # Collect every (home, away) pair we need to look up
    pairs: set[tuple[str, str]] = set()
    for m in matchups:
        h = str(m.get("home_team_id") or "")
        a = str(m.get("away_team_id") or "")
        if h and a:
            pairs.add(tuple(sorted([h, a])))

    # Single mongo query: all completed matchups in the league between these teams
    all_team_ids: list[str] = []
    for a, b in pairs:
        all_team_ids.extend([a, b])
    if not all_team_ids:
        return out
    completed = await db.matchups.find({
        "league_id": league_id,
        "status": "completed",
        "home_team_id": {"$in": all_team_ids},
        "away_team_id": {"$in": all_team_ids},
    }).sort([("season", -1), ("week", -1)]).to_list(5000)

    # Current season (if league has it stored) else most-recent season seen
    cur_season = None
    for c in completed:
        if c.get("season"):
            cur_season = c.get("season")
            break

    by_pair: dict[tuple[str, str], list[dict]] = {}
    for c in completed:
        h = str(c.get("home_team_id") or "")
        a = str(c.get("away_team_id") or "")
        if not (h and a):
            continue
        key = tuple(sorted([h, a]))
        by_pair.setdefault(key, []).append(c)

    for m in matchups:
        mid = str(m.get("_id"))
        h = str(m.get("home_team_id") or "")
        a = str(m.get("away_team_id") or "")
        if not (h and a):
            continue
        key = tuple(sorted([h, a]))
        rows = by_pair.get(key, [])
        if not rows:
            out[mid] = {
                "last_season": "0-0",
                "all_time": "0-0",
                "streak_wins": 0,
                "streak_team_id": None,
                "perspective_team_id": h,
            }
            continue
        # All-time wins for each team
        all_h = sum(1 for r in rows if str(r.get("winner_team_id")) == h)
        all_a = sum(1 for r in rows if str(r.get("winner_team_id")) == a)
        # Last-season wins
        if cur_season:
            ls_rows = [r for r in rows if r.get("season") == cur_season]
        else:
            ls_rows = []
        ls_h = sum(1 for r in ls_rows if str(r.get("winner_team_id")) == h)
        ls_a = sum(1 for r in ls_rows if str(r.get("winner_team_id")) == a)
        # Current streak (rows are pre-sorted newest first)
        streak_wins = 0
        streak_team = None
        for r in rows:
            w = str(r.get("winner_team_id") or "")
            if not w:
                continue
            if streak_team is None:
                streak_team = w
                streak_wins = 1
            elif w == streak_team:
                streak_wins += 1
            else:
                break
        out[mid] = {
            "last_season": f"{ls_h}-{ls_a}",
            "all_time": f"{all_h}-{all_a}",
            "streak_wins": streak_wins,
            "streak_team_id": streak_team,
            "perspective_team_id": h,  # h2h string is from home team's POV
        }
    return out


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
    h2h = await _compute_h2h_records(db, league_id, matchups)
    return {
        "league_id": league_id,
        "week": week,
        "starred_ids": starred_ids,
        "auto_watch": auto_watch,
        "h2h": h2h,
    }
