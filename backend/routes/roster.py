"""Roster read-side router.

Extracted from server.py during iter 91 modularization. Bundles the two
heavy read endpoints that power the Lovable Team page + tradeable-player
selectors:

  - GET /roster/{team_id}         (light per-player list)
  - GET /roster/{team_id}/detail  (rich payload — sections, live stats,
                                   category breakdown, synthesized
                                   contracts + eligibility)

The write side (`/roster/{id}/add`, `/roster/{id}/drop`) stays in
server.py — those endpoints write to waiver/activity collections and
own pickup-priority logic that's deeply coupled to the legacy code path.

Both endpoints lean on `calculate_fantasy_points` (a sync helper in
server.py) and `live_scoring_worker._fantasy_points_from_live`. The
former is passed through `_router_deps`; the latter is imported lazily
inside the handler to avoid pulling the live-scoring graph into the
module load path (mirrors what server.py did).
"""
from bson import ObjectId
from fastapi import APIRouter, HTTPException

router = APIRouter()
_deps: dict = {}


def setup(deps: dict) -> None:
    _deps.update(deps)


@router.get("/roster/{team_id}")
async def get_roster(team_id: str):
    """Light list — used by player-picker selects + trade modals."""
    db = _deps["db"]
    calculate_fantasy_points = _deps["calculate_fantasy_points"]

    team = await db.teams.find_one({"_id": ObjectId(team_id)})
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    roster_players = team.get("roster", [])
    lineup = team.get("lineup") or {}
    config = await db.scoring_configs.find_one({"league_id": team["league_id"]})
    players = []
    for pid in roster_players:
        player = await db.players.find_one({"_id": ObjectId(pid)})
        if not player:
            continue
        fpts = calculate_fantasy_points(player, config)
        section_info = lineup.get(pid) or {}
        section = (section_info.get("section") or "active").lower()
        players.append({
            "player_id": str(player["_id"]),
            "name": player["name"],
            "position": player["position"],
            "player_type": player.get("player_type") or (
                "goalie" if player.get("position") == "G" else "skater"
            ),
            "nhl_team": player.get("team", ""),
            "team_name": player.get("team_name", ""),
            "games_played": player.get("games_played", 0),
            "goals": player.get("goals", 0),
            "assists": player.get("assists", 0),
            "points": player.get("points", 0),
            "plus_minus": player.get("plus_minus", 0),
            "penalty_minutes": player.get("penalty_minutes", 0),
            "power_play_goals": player.get("power_play_goals", 0),
            "power_play_points": player.get("power_play_points", 0),
            "shots": player.get("shots", 0),
            "wins": player.get("wins", 0),
            "losses": player.get("losses", 0),
            "saves": player.get("saves", 0),
            "shots_against": player.get("shots_against", 0),
            "goals_against": player.get("goals_against", 0),
            "save_pct": player.get("save_pct", 0),
            "goals_against_avg": player.get("goals_against_avg", 0),
            "shutouts": player.get("shutouts", 0),
            "fantasy_points": fpts,
            "roster_section": section,
        })
    players.sort(key=lambda p: -(p.get("fantasy_points") or 0))
    return {"team_id": team_id, "team_name": team["name"], "players": players}


# ─── Roster detail ──────────────────────────────────────────────


_STARTING_SLOTS = [
    ("C1", "C", ["C"]), ("C2", "C", ["C"]),
    ("LW1", "LW", ["LW"]), ("RW1", "RW", ["RW"]),
    ("W1", "W", ["LW", "RW"]),
    ("D1", "D", ["D"]), ("D2", "D", ["D"]),
    ("UTIL1", "UTIL", ["C", "LW", "RW", "D"]),
    # G slots intentionally omitted — goalies route to the dedicated
    # "goalies" section so the Roster UI can render them in a separate
    # card with goalie-only stat columns.
]


def _live_agg(player: dict, fantasy_points_from_live) -> dict:
    is_g = player.get("player_type") == "goalie" or player.get("position") == "G"
    live = player.get("live_stats") or {}
    goals = assists = shots = saves = ga = wins = 0
    fpts_live = 0.0
    for _gid, ls in live.items():
        goals += ls.get("goals", 0) or 0
        assists += ls.get("assists", 0) or 0
        shots += ls.get("shots", 0) or 0
        saves += ls.get("saves", 0) or 0
        ga += ls.get("goals_against", 0) or 0
        wins += ls.get("wins", 0) or 0
        fpts_live += fantasy_points_from_live(ls, is_g)
    return {
        "goals": goals, "assists": assists, "shots": shots,
        "saves": saves, "goals_against": ga, "wins": wins,
        "fpts": round(fpts_live, 2),
    }


def _synthesize_contract(*, is_g: bool, fpts_season: float, points: int, nhl_id, age: int = 27):
    """Mirror the legacy salary-tier synthesis. The roster page renders this
    directly, and the salary-cap router falls back to the same values when
    no explicit contract row exists.
    """
    if is_g:
        if fpts_season >= 300:
            salary = 9_500_000
        elif fpts_season >= 180:
            salary = 6_000_000
        elif fpts_season >= 100:
            salary = 3_500_000
        else:
            salary = 1_200_000
    elif points >= 100:
        salary = 11_000_000 + min(2_500_000, (points - 100) * 70_000)
    elif points >= 60:
        salary = 6_000_000 + (points - 60) * 100_000
    elif points >= 30:
        salary = 3_000_000 + (points - 30) * 90_000
    elif points >= 10:
        salary = 1_500_000 + (points - 10) * 75_000
    else:
        salary = 950_000 + points * 40_000
    salary = int(min(13_500_000, max(775_000, salary)))
    years_remaining = 1 + (int(nhl_id or 0) % 6)
    if age < 23 and salary < 1_200_000:
        contract_type = "ELC"
    elif years_remaining == 1 and age < 27:
        contract_type = "RFA"
    elif years_remaining == 1:
        contract_type = "UFA"
    else:
        contract_type = "Signed"
    return {
        "salary": salary,
        "yearsRemaining": years_remaining,
        "type": contract_type,
    }


@router.get("/roster/{team_id}/detail")
async def get_roster_detail(team_id: str):
    """Rich roster payload for the Lovable Team page.

    Returns per-player season + live stats, category breakdown, synthesized
    contracts/eligibility, and roster section assignment with the team's
    lineup overrides honored.
    """
    db = _deps["db"]
    calculate_fantasy_points = _deps["calculate_fantasy_points"]
    _safe_object_id = _deps["_safe_object_id"]

    team = await db.teams.find_one({"_id": _safe_object_id(team_id, "team_id")})
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    league = await db.leagues.find_one({"_id": ObjectId(team["league_id"])})
    config = await db.scoring_configs.find_one({"league_id": team["league_id"]})

    roster_ids = team.get("roster", []) or []
    if not roster_ids:
        return {
            "team_id": team_id, "team_name": team["name"],
            "league_id": team["league_id"],
            "league_name": (league or {}).get("name"),
            "players": [],
        }

    players_raw = await db.players.find(
        {"_id": {"$in": [ObjectId(pid) for pid in roster_ids]}},
    ).to_list(100)

    # Imported lazily so importing this router doesn't pull the live-scoring
    # graph at startup (heavy + side-effecting).
    from live_scoring_worker import _fantasy_points_from_live as fp_from_live

    enriched = []
    for p in players_raw:
        pos = p.get("position", "F")
        is_g = p.get("player_type") == "goalie" or pos == "G"
        live = _live_agg(p, fp_from_live)
        fpts_season = calculate_fantasy_points(p, config)
        games = p.get("games_played", 0) or 0
        points = p.get("points", 0) or 0
        dyn_val = int(max(1000, points * 80 + (fpts_season * 10)))
        trend = (
            "up" if live["fpts"] > 0
            else ("down" if games > 0 and points < 10 else "stable")
        )

        eligible = [pos] if pos in ("C", "LW", "RW", "D", "G") else ["F"]
        contract = _synthesize_contract(
            is_g=is_g, fpts_season=fpts_season,
            points=points, nhl_id=p.get("nhl_id"),
        )

        stats_by_period = {
            "season": round(fpts_season, 1),
            "1d": round(live["fpts"], 1),
            "7d": round(live["fpts"], 1),
            "14d": round(live["fpts"] * 1.3, 1),
            "30d": round(fpts_season * 0.3, 1),
            "60d": round(fpts_season * 0.55, 1),
            "100d": round(fpts_season * 0.85, 1),
        }

        category_breakdown = {
            "G": p.get("goals", 0) or 0,
            "A": p.get("assists", 0) or 0,
            "PPP": p.get("power_play_points", 0) or 0,
            "SHP": p.get("short_handed_points", 0) or 0,
            "SOG": p.get("shots", 0) or 0,
            "HIT": p.get("hits", 0) or 0,
            "BLK": p.get("blocked_shots", 0) or 0,
            "PIM": p.get("penalty_minutes", 0) or 0,
            "+/-": p.get("plus_minus", 0) or 0,
            "FOW": 0, "FOL": 0,
        }

        enriched.append({
            "id": str(p["_id"]),
            "player_id": str(p["_id"]),
            "nhl_id": p.get("nhl_id"),
            "name": p.get("name"),
            "team": p.get("team"),
            "position": pos,
            "eligiblePositions": eligible,
            "is_goalie": is_g,
            "age": 27,
            "dynastyValue": dyn_val,
            "trend": trend,
            "contract": contract,
            "games_played": games,
            "points": points,
            "fantasy_points": round(fpts_season, 2),
            "live": live,
            "statsByPeriod": stats_by_period,
            "categoryBreakdown": category_breakdown,
            "matchupGames": (
                live.get("games", 0) if isinstance(live.get("games"), int) else 0
            ),
        })

    enriched.sort(key=lambda x: -x["fantasy_points"])

    # Default-assign starting slots based on position eligibility.
    assigned_ids: set = set()
    for slot_id, _label, elig in _STARTING_SLOTS:
        for cand in enriched:
            if cand["id"] in assigned_ids:
                continue
            if cand["position"] in elig:
                cand["rosterSlotId"] = slot_id
                cand["rosterSection"] = "goalies" if cand.get("is_goalie") else "starting"
                assigned_ids.add(cand["id"])
                break

    # Spillover: bench (up to 6) → minors; goalies → goalies/goalies_minors.
    for cand in enriched:
        if cand["id"] in assigned_ids:
            continue
        cand["rosterSlotId"] = None
        if cand.get("is_goalie"):
            goalie_count = sum(
                1 for c in enriched if c.get("rosterSection") == "goalies"
            )
            cand["rosterSection"] = "goalies" if goalie_count < 4 else "goalies_minors"
        else:
            bench_count = sum(
                1 for c in enriched if c.get("rosterSection") == "bench"
            )
            cand["rosterSection"] = "bench" if bench_count < 6 else "minors"
        assigned_ids.add(cand["id"])

    # Honor team.lineup overrides (commissioner-set sections like ir, ir+, taxi).
    lineup = team.get("lineup") or {}
    for cand in enriched:
        ln = lineup.get(cand["id"])
        if not ln or not ln.get("section"):
            continue
        sec = ln["section"].lower()
        if sec == "minors":
            cand["rosterSection"] = (
                "goalies_minors" if cand.get("is_goalie") else "minors"
            )
        elif sec == "ir":
            cand["rosterSection"] = "ir"

    total_fpts = round(sum(p["fantasy_points"] for p in enriched), 2)
    total_live = round(sum(p["live"]["fpts"] for p in enriched), 2)
    return {
        "team_id": team_id,
        "team_name": team["name"],
        "owner_name": team.get("owner_name"),
        "league_id": team["league_id"],
        "league_name": (league or {}).get("name"),
        "wins": team.get("wins", 0),
        "losses": team.get("losses", 0),
        "ties": team.get("ties", 0),
        "salary_used": team.get("salary_used", 0.0),
        "season_fpts": total_fpts,
        "live_fpts": total_live,
        "players": enriched,
    }
