"""Roster router (read + write side).

Extracted from server.py during iter 91 (read side) and iter 98 (write
side). Bundles the team-roster endpoints that power the Lovable Team
page + the add/drop flow:

  Read:
    - GET  /roster/{team_id}         (light per-player list)
    - GET  /roster/{team_id}/detail  (rich payload — sections, live stats,
                                       category breakdown, synthesized
                                       contracts + eligibility)
  Write:
    - POST /roster/{team_id}/add     (free-agent add with position-cap,
                                       illegal-roster, and salary-cap gates)
    - POST /roster/{team_id}/drop    (remove + activity log)

The write side persists a recomputed `team.salary_used` after every
mutation via `_recompute_team_salary_used`, the same helper used by the
compliance endpoint in server.py (re-exported via `_router_deps`).

All endpoints lean on dependency injection via `setup(deps)`.
"""
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter()
_deps: dict = {}


def setup(deps: dict) -> None:
    _deps.update(deps)


# ─── Models ─────────────────────────────────────────────────────


class RosterAction(BaseModel):
    player_id: str


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

    Iter 110 — Returns these extra fields used by the salary-cap "Year" /
    "Contract Ends" columns + the By-Year bar chart:
      - total_years   total length of the deal (1..8)
      - current_year  which year of the deal the player is in (1-indexed)
      - end_year      NHL season-end calendar year when the contract expires
      - end_status    status the player will hold when the deal ends
                      (ELC→RFA; otherwise RFA if age-at-expiry<27 else UFA)
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

    # Iter 110 — Year + Contract-Ends + Status-at-expiry surface
    total_years = max(years_remaining, 1 + (int(nhl_id or 0) % 8))
    current_year = max(1, total_years - years_remaining + 1)
    # NHL season convention: a deal with `years_remaining=N` expires after the
    # season ending in (current_calendar_year + N - 1). For example, in
    # 2025-26 a 1-year deal ends in calendar year 2026.
    from datetime import datetime as _dt
    season_end_year = _dt.utcnow().year if _dt.utcnow().month >= 8 else _dt.utcnow().year
    end_year = season_end_year + max(0, years_remaining - 1)
    age_at_expiry = age + max(0, years_remaining - 1)
    if contract_type == "ELC":
        end_status = "RFA"  # ELCs always flip to RFA
    elif contract_type in ("RFA", "UFA"):
        end_status = contract_type  # already expiring this year
    else:
        end_status = "UFA" if age_at_expiry >= 27 else "RFA"

    return {
        "salary": salary,
        "yearsRemaining": years_remaining,
        "type": contract_type,
        "total_years": total_years,
        "current_year": current_year,
        "end_year": end_year,
        "end_status": end_status,
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

        # Iter 174 — Compute a real age + surface prospect status so the
        # spillover logic (and frontend compliance flags) can tell
        # veterans apart from minor-league-eligible prospects. Falls
        # back to whatever the player doc carries; a sensible default
        # only kicks in when we have nothing at all to work with.
        player_age = p.get("age")
        bd = p.get("birth_date")
        if not player_age and bd:
            try:
                from datetime import datetime as _dt, timezone as _tz
                bd_dt = _dt.fromisoformat(bd.split("T")[0]) if isinstance(bd, str) else bd
                player_age = (_dt.now(_tz.utc).replace(tzinfo=None) - bd_dt).days // 365
            except Exception:
                player_age = None
        # Prospect bona fides: explicit type wins, then minor_eligible flag.
        player_type = (p.get("player_type") or "").lower()
        is_prospect = player_type == "prospect" or bool(p.get("minor_eligible"))

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
            # Iter 174 — Real age (or None) instead of a hard-coded 27.
            # The frontend's `checkIneligibility` uses this to flag
            # players who've aged out of minors eligibility.
            "age": player_age,
            # Iter 173/174 — surface prospect status + minor-eligibility
            # for the team page compliance check.
            "player_type": player_type or "skater",
            "minor_eligible": is_prospect,
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
    # Iter 174 — Veterans (player_type != "prospect") never spill into
    # minors. They stay on the bench even if it visually exceeds the
    # 6-slot cap — the compliance widget will surface "Bench over
    # limit" but it won't fabricate an illegal minors placement.
    for cand in enriched:
        if cand["id"] in assigned_ids:
            continue
        cand["rosterSlotId"] = None
        if cand.get("is_goalie"):
            goalie_count = sum(
                1 for c in enriched if c.get("rosterSection") == "goalies"
            )
            # Goalies-minors only accepts prospects too.
            if goalie_count < 4 or not cand.get("minor_eligible"):
                cand["rosterSection"] = "goalies"
            else:
                cand["rosterSection"] = "goalies_minors"
        else:
            bench_count = sum(
                1 for c in enriched if c.get("rosterSection") == "bench"
            )
            if bench_count < 6:
                cand["rosterSection"] = "bench"
            elif cand.get("minor_eligible"):
                cand["rosterSection"] = "minors"
            else:
                # Veteran with no bench spot — keep on bench so the page
                # doesn't fabricate an illegal minors placement. The
                # over-cap is a legitimate "Bench over limit" warning.
                cand["rosterSection"] = "bench"
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


# ═══════════════════════════════════════════════════════════════
# Write side (iter 98 extraction)
# ═══════════════════════════════════════════════════════════════


def _synthesize_player_salary(p: dict, config: Optional[dict] = None) -> float:
    """Single source of truth for player salary synthesis.

    Mirrors the tiered formula used in `/roster/{id}/detail` so the cap
    usage on the team page matches the per-row salary chip exactly.
    """
    calculate_fantasy_points = _deps["calculate_fantasy_points"]

    # Honour any explicit salary stored on the player document first
    explicit = (
        (p.get("contract") or {}).get("aav")
        or (p.get("contract") or {}).get("salary")
        or p.get("salary")
        or p.get("cap_hit")
    )
    if explicit:
        return float(explicit)

    is_g = p.get("player_type") == "goalie" or p.get("position") == "G"
    points = int(p.get("points") or 0)
    fpts_season = float(calculate_fantasy_points(p, config) or 0.0)
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
    return float(min(13_500_000, max(775_000, salary)))


async def _recompute_team_salary_used(team_id: str) -> float:
    """Sum the synthesized cap hit across every player on the team's
    roster + any salary_retentions the team is paying for other teams'
    players. Persists the result to `team.salary_used` so subsequent
    /compliance + /roster reads return the live number.
    """
    db = _deps["db"]
    team = await db.teams.find_one({"_id": ObjectId(team_id)})
    if not team:
        return 0.0
    roster_obj_ids = []
    for pid in (team.get("roster") or []):
        try:
            roster_obj_ids.append(ObjectId(pid))
        except Exception:
            pass
    rostered_players = []
    if roster_obj_ids:
        rostered_players = await db.players.find(
            {"_id": {"$in": roster_obj_ids}},
            {"contract": 1, "salary": 1, "cap_hit": 1, "position": 1,
             "player_type": 1, "points": 1, "games_played": 1,
             "goals": 1, "assists": 1, "shots": 1, "saves": 1,
             "wins": 1, "losses": 1, "overtime_losses": 1,
             "goals_against": 1, "shutouts": 1, "plus_minus": 1,
             "penalty_minutes": 1, "power_play_points": 1,
             "power_play_goals": 1, "short_handed_goals": 1,
             "short_handed_points": 1, "game_winning_goals": 1},
        ).to_list(200)

    config = await db.scoring_configs.find_one({"league_id": team["league_id"]})
    used = sum(_synthesize_player_salary(p, config) for p in rostered_players)
    retentions = team.get("salary_retentions") or []
    used += sum(float(r.get("amount") or 0.0) for r in retentions)
    await db.teams.update_one(
        {"_id": ObjectId(team_id)},
        {"$set": {"salary_used": float(used)}},
    )
    return float(used)


@router.post("/roster/{team_id}/add")
async def add_to_roster(team_id: str, input: RosterAction, request: Request):
    db = _deps["db"]
    get_current_user = _deps["get_current_user"]
    log_activity = _deps["log_activity"]

    user = await get_current_user(request)
    team = await db.teams.find_one({"_id": ObjectId(team_id)})
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    if team["owner_id"] != user["_id"]:
        raise HTTPException(status_code=403, detail="Not your team")

    # Roster-spots gate
    league = await db.leagues.find_one({"_id": ObjectId(team["league_id"])})
    max_roster = league.get("roster_spots", 20)
    current_roster = team.get("roster", [])
    if len(current_roster) >= max_roster:
        raise HTTPException(
            status_code=400,
            detail=f"Roster full ({len(current_roster)}/{max_roster}). Drop a player before adding.",
        )

    player = await db.players.find_one({"_id": ObjectId(input.player_id)})
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")

    if input.player_id in current_roster:
        raise HTTPException(status_code=400, detail="Player already on roster")

    # ── Transactions-config gates (iter 117) ────────────────────────
    # Season/week caps, injured/minors filters, lock-at-first-game,
    # non-playoff block, abuse window. Raises 400 with a human reason on
    # the first hit.
    from utils.transactions_enforce import enforce_claim
    await enforce_claim(db, team_id=team_id, league=league, player=player, tx_kind="fa")

    # ── Position-limit pre-check (league.enforce_position_maxes) ────
    from utils.roster_rules import check_position_limits
    roster_obj_ids = []
    for pid in current_roster:
        try:
            roster_obj_ids.append(ObjectId(pid))
        except Exception:
            pass
    roster_players = (
        await db.players.find(
            {"_id": {"$in": roster_obj_ids}},
            {"name": 1, "position": 1, "primary_position": 1,
             "eligible_positions": 1, "player_type": 1},
        ).to_list(200) if roster_obj_ids else []
    )
    pos_err = check_position_limits(league, roster_players, player)
    if pos_err:
        raise HTTPException(status_code=400, detail=pos_err)

    # ── Illegal-roster pre-check ────────────────────────────────────
    # If the league has an IR-compliance mode that locks adds when the
    # team is non-compliant, block until the violations are resolved.
    ir_mode = (league.get("injury_reserve_compliance_mode") or "none").lower()
    if ir_mode in ("lock_adds", "lock_adds_trades", "lock_all", "illegal_roster"):
        lineup = team.get("lineup") or {}
        if lineup:
            lookup_obj_ids = []
            for pid in current_roster:
                try:
                    lookup_obj_ids.append(ObjectId(pid))
                except Exception:
                    pass
            existing = await db.players.find(
                {"_id": {"$in": lookup_obj_ids}},
                {"name": 1, "games_played": 1, "birth_date": 1,
                 "injury_status": 1, "status": 1},
            ).to_list(200) if lookup_obj_ids else []
            illegal_msgs: list[str] = []
            for p in existing:
                pid = str(p["_id"])
                slot = lineup.get(pid)
                if not slot:
                    continue
                section = (slot.get("section") or "").lower()
                if section == "ir":
                    inj = (p.get("injury_status") or p.get("status") or "").lower()
                    if not inj or inj in ("healthy", "active", "ok"):
                        illegal_msgs.append(f"{p.get('name')} is on IR but healthy")
            if illegal_msgs:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Add denied: illegal roster — {'; '.join(illegal_msgs[:3])}. "
                        f"League IR rule: {ir_mode.replace('_', ' ')}."
                    ),
                )

    # ── Salary-cap pre-check ────────────────────────────────────────
    cap_enabled = bool(league.get("salary_cap_enabled"))
    salary_cap = league.get("salary_cap")
    if cap_enabled and salary_cap:
        config = await db.scoring_configs.find_one({"league_id": team["league_id"]})
        new_player_salary = _synthesize_player_salary(player, config)
        roster_obj_ids = []
        for pid in current_roster:
            try:
                roster_obj_ids.append(ObjectId(pid))
            except Exception:
                pass
        rostered_players = []
        if roster_obj_ids:
            rostered_players = await db.players.find(
                {"_id": {"$in": roster_obj_ids}},
                {"contract": 1, "salary": 1, "cap_hit": 1, "position": 1,
                 "player_type": 1, "points": 1, "games_played": 1,
                 "goals": 1, "assists": 1, "shots": 1, "saves": 1,
                 "wins": 1, "losses": 1, "overtime_losses": 1,
                 "goals_against": 1, "shutouts": 1, "plus_minus": 1,
                 "penalty_minutes": 1, "power_play_points": 1,
                 "power_play_goals": 1, "short_handed_goals": 1,
                 "short_handed_points": 1, "game_winning_goals": 1},
            ).to_list(200)
        current_used = sum(_synthesize_player_salary(p, config) for p in rostered_players)
        retentions = team.get("salary_retentions") or []
        retention_total = sum(float(r.get("amount") or 0.0) for r in retentions)
        projected_used = current_used + new_player_salary + retention_total
        if projected_used > float(salary_cap):
            over_by = projected_used - float(salary_cap)
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Add denied: over the salary cap by ${over_by:,.0f}. "
                    f"Adding {player['name']} (${new_player_salary:,.0f}) would put you at "
                    f"${projected_used:,.0f} vs ${float(salary_cap):,.0f} cap."
                ),
            )

    await db.teams.update_one(
        {"_id": ObjectId(team_id)},
        {"$push": {"roster": input.player_id}},
    )

    # Refresh salary_used so the compliance + UI numbers track immediately.
    await _recompute_team_salary_used(team_id)

    await log_activity(
        team["league_id"], "roster_add",
        f"{team['name']} adds {player['name']} ({player['position']})",
        user["_id"],
        metadata={
            "team_id": team_id, "team_name": team["name"],
            "player_id": input.player_id, "player_name": player["name"],
            "position": player.get("position"),
            "season": league.get("season") or "2025-2026",
            "week": int(league.get("current_week") or 1),
        },
    )
    return {"message": f"Added {player['name']} to roster"}


@router.post("/roster/{team_id}/drop")
async def drop_from_roster(team_id: str, input: RosterAction, request: Request):
    db = _deps["db"]
    get_current_user = _deps["get_current_user"]
    log_activity = _deps["log_activity"]

    user = await get_current_user(request)
    team = await db.teams.find_one({"_id": ObjectId(team_id)})
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    if team["owner_id"] != user["_id"]:
        raise HTTPException(status_code=403, detail="Not your team")

    current_roster = team.get("roster", [])
    if input.player_id not in current_roster:
        raise HTTPException(status_code=400, detail="Player not on roster")

    # ── Transactions-config gates for drops (iter 117) ─────────────
    league = await db.leagues.find_one({"_id": ObjectId(team["league_id"])})
    from utils.transactions_enforce import enforce_drop
    await enforce_drop(db, team_id=team_id, league=league or {})

    # Iter 119 — Force-claim-on-drop: when the waiver section's
    # `force_claim_on_drop` toggle is on, drops via this standalone
    # endpoint are blocked. Owners must use the trade/claim/transaction
    # endpoints that bundle an add with the drop.
    tx_cfg = ((league or {}).get("transactions_config") or {})
    waiver_cfg = (tx_cfg.get("waiver") or {})
    if waiver_cfg.get("enabled") and waiver_cfg.get("force_claim_on_drop"):
        raise HTTPException(
            status_code=400,
            detail="This league requires you to select a replacement player when dropping. Use a roster move that includes both an add and a drop.",
        )

    await db.teams.update_one(
        {"_id": ObjectId(team_id)},
        {"$pull": {"roster": input.player_id}},
    )

    # Refresh salary_used so the compliance + UI numbers track immediately.
    await _recompute_team_salary_used(team_id)

    player = await db.players.find_one({"_id": ObjectId(input.player_id)})
    name = player["name"] if player else "Unknown"
    await log_activity(
        team["league_id"], "roster_drop",
        f"{team['name']} drops {name}",
        user["_id"],
        metadata={
            "team_id": team_id, "team_name": team["name"],
            "player_id": input.player_id, "player_name": name,
            "season": (league or {}).get("season") or "2025-2026",
            "week": int((league or {}).get("current_week") or 1),
        },
    )
    return {"message": f"Dropped {name} from roster"}
