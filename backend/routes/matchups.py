"""Matchups: schedule generation, get-current-week, simulate-week (with auto-crown)."""
import itertools
import random as _random
from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from routes import awards as awards_module

router = APIRouter()
_deps: dict = {}


def setup(deps: dict) -> None:
    _deps.update(deps)


# ─── Pydantic ─────────────────────────────────────────────────
class GenerateScheduleRequest(BaseModel):
    league_id: str
    # Defaults to the league's configured `regular_season_weeks` when omitted,
    # falling back to 18 only if the league has no configured value. This keeps
    # league administration the single source of truth for schedule length.
    num_weeks: Optional[int] = Field(default=None, ge=1, le=52)


class SimulateWeekRequest(BaseModel):
    league_id: str
    week: int


# ─── Helpers ─────────────────────────────────────────────────
def generate_round_robin(team_ids):
    """Generate a full round-robin schedule. Returns list of rounds, each a list of (home, away) tuples."""
    teams = list(team_ids)
    if len(teams) % 2 == 1:
        teams.append(None)
    n = len(teams)
    schedule = []
    for _ in range(n - 1):
        round_matchups = []
        for i in range(n // 2):
            home = teams[i]
            away = teams[n - 1 - i]
            if home is not None and away is not None:
                round_matchups.append((home, away))
        schedule.append(round_matchups)
        teams.insert(1, teams.pop())
    return schedule


def _build_division_pairings(teams: list, cfg: dict) -> list:
    """Build a flat list of (home, away) pairings per the division-aware schedule config.

    For each unordered pair (A,B), choose a "times to play" based on:
      - same division → cfg.intra_division_games
      - same conference (diff division) → cfg.intra_conference_games
      - different conference → cfg.inter_conference_games
    Home/away alternates when a pair plays multiple times.
    Returns [(home_id, away_id), ...] — not yet distributed into weeks.
    """
    pairings = []
    n = len(teams)
    for i in range(n):
        for j in range(i + 1, n):
            a, b = teams[i], teams[j]
            same_div = a.get("division") and a.get("division") == b.get("division")
            same_conf = a.get("conference") and a.get("conference") == b.get("conference")
            if same_div:
                games = int(cfg.get("intra_division_games") or 0)
            elif same_conf:
                games = int(cfg.get("intra_conference_games") or 0)
            else:
                games = int(cfg.get("inter_conference_games") or 0)
            for g in range(games):
                if g % 2 == 0:
                    pairings.append((str(a["_id"]), str(b["_id"])))
                else:
                    pairings.append((str(b["_id"]), str(a["_id"])))
    return pairings


def _distribute_to_weeks(pairings: list, team_ids: list, num_weeks: int) -> list:
    """Spread pairings across weeks so each team plays at most once per week.

    Greedy: iterate pairings in random order, placing each in the earliest
    week where neither team already has a game. If all weeks are full,
    evenly overflow the earliest weeks (rare for normal configs).
    """
    import random as _random
    weeks: list[list] = [[] for _ in range(num_weeks)]
    teams_in_week: list[set] = [set() for _ in range(num_weeks)]

    shuffled = pairings[:]
    _random.shuffle(shuffled)

    placed = []
    unplaced = []
    for home, away in shuffled:
        placed_flag = False
        for w in range(num_weeks):
            if home not in teams_in_week[w] and away not in teams_in_week[w]:
                weeks[w].append((home, away))
                teams_in_week[w].add(home)
                teams_in_week[w].add(away)
                placed.append((w + 1, home, away))
                placed_flag = True
                break
        if not placed_flag:
            unplaced.append((home, away))
    # Overflow: append leftovers into the sparsest weeks round-robin
    if unplaced:
        for home, away in unplaced:
            w = min(range(num_weeks), key=lambda x: len(weeks[x]))
            weeks[w].append((home, away))
            placed.append((w + 1, home, away))
    return placed  # list of (week, home, away)


# ─── Endpoints ───────────────────────────────────────────────
@router.post("/matchups/generate-schedule")
async def generate_schedule(input: GenerateScheduleRequest, request: Request):
    """Commissioner generates the full season schedule."""
    db = _deps["db"]
    get_current_user = _deps["get_current_user"]

    user = await get_current_user(request)
    league = await db.leagues.find_one({"_id": ObjectId(input.league_id)})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    if league["commissioner_id"] != user["_id"]:
        raise HTTPException(status_code=403, detail="Only commissioner can generate schedule")

    teams = await db.teams.find({"league_id": input.league_id}).to_list(100)
    if len(teams) < 2:
        raise HTTPException(status_code=400, detail="Need at least 2 teams")

    team_ids = [str(t["_id"]) for t in teams]
    team_map = {str(t["_id"]): t["name"] for t in teams}
    scoring_format = league.get("scoring_format", "head_to_head")

    # Resolve schedule length from league config when caller omits it,
    # so league administration is the single source of truth.
    num_weeks = input.num_weeks
    if num_weeks is None:
        num_weeks = int(league.get("regular_season_weeks") or 18)

    # Division-aware? Only opt-in via league.schedule_config AND ≥2 distinct
    # divisions configured. Otherwise fall back to vanilla round-robin.
    schedule_cfg = league.get("schedule_config")
    div_names = {t.get("division") for t in teams if t.get("division")}
    use_divisional = bool(schedule_cfg) and len(div_names) >= 2

    full_schedule: list = []
    if use_divisional:
        pairings = _build_division_pairings(teams, schedule_cfg)
        distributed = _distribute_to_weeks(pairings, team_ids, num_weeks)
        for week, home_id, away_id in distributed:
            if week > num_weeks:
                continue
            full_schedule.append({
                "week": week,
                "home_team_id": home_id,
                "home_team_name": team_map.get(home_id, ""),
                "away_team_id": away_id,
                "away_team_name": team_map.get(away_id, ""),
                "home_score": 0,
                "away_score": 0,
                "status": "scheduled",
                "winner": None,
            })
    else:
        base_schedule = generate_round_robin(team_ids)
        week = 1
        cycle = itertools.cycle(base_schedule)
        while week <= num_weeks:
            round_matchups = next(cycle)
            _random.shuffle(round_matchups)
            for home_id, away_id in round_matchups:
                full_schedule.append({
                    "week": week,
                    "home_team_id": home_id,
                    "home_team_name": team_map.get(home_id, ""),
                    "away_team_id": away_id,
                    "away_team_name": team_map.get(away_id, ""),
                    "home_score": 0,
                    "away_score": 0,
                    "status": "scheduled",
                    "winner": None,
                })
            week += 1

    await db.matchups.delete_many({"league_id": input.league_id})
    if full_schedule:
        for m in full_schedule:
            m["league_id"] = input.league_id
            m["scoring_format"] = scoring_format
        await db.matchups.insert_many(full_schedule)

    return {
        "message": f"Generated {len(full_schedule)} matchups for {num_weeks} weeks",
        "weeks": num_weeks,
        "mode": "division_aware" if use_divisional else "round_robin",
    }


@router.get("/matchups/{league_id}")
async def get_matchups(league_id: str, week: Optional[int] = None):
    db = _deps["db"]
    query = {"league_id": league_id}
    if week:
        query["week"] = week
    matchups = await db.matchups.find(query).sort("week", 1).to_list(1000)
    for m in matchups:
        m["_id"] = str(m["_id"])
    return matchups


@router.get("/matchups/{league_id}/current-week")
async def get_current_week(league_id: str):
    db = _deps["db"]
    pipeline = [
        {"$match": {"league_id": league_id, "status": "scheduled"}},
        {"$group": {"_id": None, "min_week": {"$min": "$week"}}},
    ]
    result = await db.matchups.aggregate(pipeline).to_list(1)
    current = result[0]["min_week"] if result else 1
    matchups = await db.matchups.find({"league_id": league_id, "week": current}).to_list(100)
    for m in matchups:
        m["_id"] = str(m["_id"])
    return {"week": current, "matchups": matchups}


@router.get("/matchups/{league_id}/results")
async def get_week_results(league_id: str, week: int):
    db = _deps["db"]
    matchups = await db.matchups.find({"league_id": league_id, "week": week}).to_list(100)
    for m in matchups:
        m["_id"] = str(m["_id"])
    return matchups


@router.post("/matchups/simulate-week")
async def simulate_week(input: SimulateWeekRequest, request: Request):
    """Simulate a week's matchups using roster fantasy points + auto-crown playoff finals."""
    db = _deps["db"]
    sio = _deps["sio"]
    logger = _deps["logger"]
    get_current_user = _deps["get_current_user"]
    calculate_fantasy_points = _deps["calculate_fantasy_points"]
    _evaluate_conditions = _deps["_evaluate_conditions"]
    _execute_trade = _deps["_execute_trade"]
    broadcast_to_room = _deps["broadcast_to_room"]

    user = await get_current_user(request)
    league = await db.leagues.find_one({"_id": ObjectId(input.league_id)})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    if league["commissioner_id"] != user["_id"]:
        raise HTTPException(status_code=403, detail="Only commissioner can simulate")

    matchups = await db.matchups.find({
        "league_id": input.league_id,
        "week": input.week,
        "status": "scheduled",
    }).to_list(100)
    if not matchups:
        raise HTTPException(status_code=400, detail="No scheduled matchups for this week")

    config = await db.scoring_configs.find_one({"league_id": input.league_id})
    scoring_format = league.get("scoring_format", "head_to_head")

    async def calc_team_score(team_id):
        team = await db.teams.find_one({"_id": ObjectId(team_id)})
        if not team:
            return 0.0
        roster = team.get("roster", [])
        total = 0.0
        for pid in roster:
            player = await db.players.find_one({"_id": ObjectId(pid)})
            if player:
                total += calculate_fantasy_points(player, config)
        return round(total, 1)

    results = []
    for m in matchups:
        home_score = await calc_team_score(m["home_team_id"])
        away_score = await calc_team_score(m["away_team_id"])

        winner = None
        if home_score > away_score:
            winner = m["home_team_id"]
        elif away_score > home_score:
            winner = m["away_team_id"]

        await db.matchups.update_one(
            {"_id": m["_id"]},
            {"$set": {
                "home_score": home_score,
                "away_score": away_score,
                "winner": winner,
                "status": "completed",
                "simulated_at": datetime.now(timezone.utc).isoformat(),
            }}
        )

        # ─── Apply ELO ratings update for this matchup ──────────────
        try:
            from routes.ratings import apply_matchup_elo
            m_fresh = await db.matchups.find_one({"_id": m["_id"]})
            await apply_matchup_elo(input.league_id, m_fresh)
        except Exception as ex:
            logger.warning("ELO update failed for matchup %s: %s", str(m["_id"]), ex)

        # Snapshot per-team week summary for analytics rollup (idempotent upsert)
        from routes.analytics import _current_season
        _season = league.get("season") or _current_season()
        for side, opp in (("home", "away"), ("away", "home")):
            tid = m[f"{side}_team_id"]
            _doc = {
                "league_id": input.league_id, "season": _season, "week": input.week,
                "team_id": tid, "team_name": m[f"{side}_team_name"],
                "opponent_team_id": m[f"{opp}_team_id"],
                "points_for": float(home_score if side == "home" else away_score),
                "points_against": float(away_score if side == "home" else home_score),
                "win": winner == tid,
                "loss": bool(winner) and winner != tid,
                "tie": winner is None,
                "matchup_id": str(m["_id"]),
            }
            await db.week_summaries.update_one(
                {"league_id": input.league_id, "season": _season,
                 "week": input.week, "team_id": tid},
                {"$set": _doc},
                upsert=True,
            )

        if winner == m["home_team_id"]:
            await db.teams.update_one({"_id": ObjectId(m["home_team_id"])},
                                      {"$inc": {"wins": 1, "points_for": home_score, "points_against": away_score}})
            await db.teams.update_one({"_id": ObjectId(m["away_team_id"])},
                                      {"$inc": {"losses": 1, "points_for": away_score, "points_against": home_score}})
        elif winner == m["away_team_id"]:
            await db.teams.update_one({"_id": ObjectId(m["away_team_id"])},
                                      {"$inc": {"wins": 1, "points_for": away_score, "points_against": home_score}})
            await db.teams.update_one({"_id": ObjectId(m["home_team_id"])},
                                      {"$inc": {"losses": 1, "points_for": home_score, "points_against": away_score}})
        else:
            await db.teams.update_one({"_id": ObjectId(m["home_team_id"])},
                                      {"$inc": {"ties": 1, "points_for": home_score, "points_against": away_score}})
            await db.teams.update_one({"_id": ObjectId(m["away_team_id"])},
                                      {"$inc": {"ties": 1, "points_for": away_score, "points_against": home_score}})

        # Auto-crown for playoff finals
        if m.get("is_final") and winner:
            bracket = m.get("bracket", "championship")
            now = datetime.now(timezone.utc)
            loser_id = m["away_team_id"] if winner == m["home_team_id"] else m["home_team_id"]
            winner_name = m["home_team_name"] if winner == m["home_team_id"] else m["away_team_name"]
            if bracket == "championship":
                await db.teams.update_one({"_id": ObjectId(winner)},
                                          {"$set": {"championship_won_at": now}})
                # Mark the runner-up so the profile trophy case can show it
                await db.teams.update_one({"_id": ObjectId(loser_id)},
                                          {"$set": {"playoff_runner_up_at": now}})
                await db.activity_feed.insert_one({
                    "league_id": input.league_id, "event_type": "championship_awarded",
                    "description": f"🏆 {winner_name} won the championship!",
                    "message": f"Champion crowned: {winner_name}",
                    "created_at": now,
                })
                await db.audit_log.insert_one({
                    "league_id": input.league_id, "actor_id": "system",
                    "actor_name": "System (auto-crown)",
                    "action": "championship_awarded", "role": "system",
                    "diff": {"winner_team_id": winner, "runner_up_team_id": loser_id,
                             "matchup_id": str(m["_id"]), "score": f"{home_score}-{away_score}"},
                    "created_at": now,
                })
                pending = await db.trades.find({
                    "league_id": input.league_id, "conditional": True,
                    "status": {"$in": ["pending", "accepted", "conditional"]},
                }).to_list(500)
                unlocked = 0
                for t in pending:
                    try:
                        res = await _evaluate_conditions(t)
                        if res["all_met"] and t.get("status") == "accepted":
                            await _execute_trade(t)
                            unlocked += 1
                    except Exception as ex:
                        logger.warning("Conditional trade re-eval (auto-crown) failed league=%s trade=%s: %s",
                                       input.league_id, str(t.get("_id")), ex)
                # Re-evaluate pick-upgrade clauses on executed trades. Final
                # eval at championship → unmet upgrades lock as `failed`.
                apply_pu = _deps.get("_apply_pick_upgrades")
                if apply_pu:
                    executed = await db.trades.find({
                        "league_id": input.league_id, "status": "executed",
                        "pick_upgrades": {"$exists": True, "$ne": []},
                    }).to_list(500)
                    for t in executed:
                        try:
                            await apply_pu(t, final_eval=True)
                        except Exception as ex:
                            logger.warning("Pick-upgrade final-eval failed league=%s trade=%s: %s",
                                           input.league_id, str(t.get("_id")), ex)
                await sio.emit("championship_crowned", {
                    "league_id": input.league_id,
                    "team_id": winner, "team_name": winner_name,
                    "runner_up_team_id": loser_id,
                    "score": f"{home_score}-{away_score}",
                    "unlocked_trades": unlocked,
                    "crowned_at": now.isoformat(),
                })
            elif bracket == "consolation":
                await db.teams.update_one({"_id": ObjectId(winner)},
                                          {"$set": {"consolation_won_at": now}})
                applied_steps: list = []
                prize = (league.get("consolation_prize") or {})
                if prize.get("type"):
                    await db.team_rewards.insert_one({
                        "league_id": input.league_id, "team_id": winner,
                        "team_name": winner_name, "source": "consolation_winner",
                        "prize": prize, "awarded_at": now,
                        "status": "pending_commissioner_fulfillment",
                    })
                    applied = await awards_module.apply_consolation_prize(input.league_id, winner, prize)
                    applied_steps = applied.get("steps", [])
                await db.activity_feed.insert_one({
                    "league_id": input.league_id, "event_type": "consolation_awarded",
                    "description": f"Consolation bracket won by {winner_name}" + (
                        f" — {applied_steps[0]}" if applied_steps else ""
                    ),
                    "message": "Consolation bracket concluded",
                    "created_at": now,
                })
                await db.audit_log.insert_one({
                    "league_id": input.league_id, "actor_id": "system",
                    "actor_name": "System (auto-crown)",
                    "action": "consolation_awarded", "role": "system",
                    "diff": {"winner_team_id": winner, "runner_up_team_id": loser_id,
                             "matchup_id": str(m["_id"]), "score": f"{home_score}-{away_score}",
                             "prize": prize or None, "applied_steps": applied_steps},
                    "created_at": now,
                })
                await sio.emit("consolation_crowned", {
                    "league_id": input.league_id,
                    "team_id": winner, "team_name": winner_name,
                    "prize": prize or None,
                    "applied_steps": applied_steps,
                    "crowned_at": now.isoformat(),
                })
            elif bracket in ("conference_final", "conference"):
                await db.teams.update_one({"_id": ObjectId(winner)},
                                          {"$set": {"conference_winner_at": now}})
                await db.activity_feed.insert_one({
                    "league_id": input.league_id, "event_type": "conference_awarded",
                    "description": f"🥇 {winner_name} won the conference!",
                    "message": f"Conference champion crowned: {winner_name}",
                    "created_at": now,
                })
                await db.audit_log.insert_one({
                    "league_id": input.league_id, "actor_id": "system",
                    "actor_name": "System (auto-crown)",
                    "action": "conference_awarded", "role": "system",
                    "diff": {"winner_team_id": winner, "runner_up_team_id": loser_id,
                             "matchup_id": str(m["_id"]), "score": f"{home_score}-{away_score}"},
                    "created_at": now,
                })
                await sio.emit("conference_crowned", {
                    "league_id": input.league_id,
                    "team_id": winner, "team_name": winner_name,
                    "score": f"{home_score}-{away_score}",
                    "crowned_at": now.isoformat(),
                })
            elif bracket in ("division_final", "division"):
                await db.teams.update_one({"_id": ObjectId(winner)},
                                          {"$set": {"division_winner_at": now}})
                await db.activity_feed.insert_one({
                    "league_id": input.league_id, "event_type": "division_awarded",
                    "description": f"🏅 {winner_name} won the division!",
                    "message": f"Division champion crowned: {winner_name}",
                    "created_at": now,
                })
                await db.audit_log.insert_one({
                    "league_id": input.league_id, "actor_id": "system",
                    "actor_name": "System (auto-crown)",
                    "action": "division_awarded", "role": "system",
                    "diff": {"winner_team_id": winner, "runner_up_team_id": loser_id,
                             "matchup_id": str(m["_id"]), "score": f"{home_score}-{away_score}"},
                    "created_at": now,
                })
                await sio.emit("division_crowned", {
                    "league_id": input.league_id,
                    "team_id": winner, "team_name": winner_name,
                    "score": f"{home_score}-{away_score}",
                    "crowned_at": now.isoformat(),
                })

        results.append({
            "home": m["home_team_name"],
            "away": m["away_team_name"],
            "home_score": home_score,
            "away_score": away_score,
            "winner": m["home_team_name"] if winner == m["home_team_id"]
                      else m["away_team_name"] if winner else "Tie",
        })

    if scoring_format == "all_play":
        all_teams = await db.teams.find({"league_id": input.league_id}).to_list(100)
        scores = {str(t["_id"]): await calc_team_score(str(t["_id"])) for t in all_teams}
        for team_id, score in scores.items():
            ap_wins = sum(1 for oid, oscore in scores.items() if oid != team_id and score > oscore)
            ap_losses = sum(1 for oid, oscore in scores.items() if oid != team_id and score < oscore)
            await db.teams.update_one({"_id": ObjectId(team_id)},
                                      {"$inc": {"wins": ap_wins, "losses": ap_losses}})

    if scoring_format == "guillotine":
        all_teams = await db.teams.find({"league_id": input.league_id, "eliminated": {"$ne": True}}).to_list(100)
        scores = []
        for t in all_teams:
            s = await calc_team_score(str(t["_id"]))
            scores.append((str(t["_id"]), t["name"], s))
        if scores:
            scores.sort(key=lambda x: x[2])
            eliminated = scores[0]
            await db.teams.update_one({"_id": ObjectId(eliminated[0])}, {"$set": {"eliminated": True}})
            results.append({"eliminated": eliminated[1], "score": eliminated[2]})

    await broadcast_to_room(f"league_{input.league_id}", "week_simulated", {
        "week": input.week,
        "results": results,
    })

    # ─── Division-winner auto-crown ──────────────────────────────
    # Fire when the just-simulated week is the FINAL regular-season week:
    #   last_regular_season_week = max(week) among matchups with is_playoff != True
    # Uses tiebreakers: (wins desc, division_wins desc, points_for desc).
    # Idempotent: skips teams that already have `division_winner_at` set.
    try:
        rs_agg = await db.matchups.aggregate([
            {"$match": {
                "league_id": input.league_id,
                "$or": [{"is_playoff": {"$exists": False}}, {"is_playoff": False}],
            }},
            {"$group": {"_id": None, "max_week": {"$max": "$week"}}},
        ]).to_list(1)
        last_rs_week = rs_agg[0]["max_week"] if rs_agg else None

        if last_rs_week is not None and input.week >= last_rs_week:
            all_league_teams = await db.teams.find({"league_id": input.league_id}).to_list(100)
            divisions_seen = {t.get("division") for t in all_league_teams if t.get("division")}
            if len(divisions_seen) >= 2:
                now = datetime.now(timezone.utc)
                # Compute each team's division-win count from completed matchups
                completed = await db.matchups.find({
                    "league_id": input.league_id,
                    "status": {"$in": ["completed", "final"]},
                }).to_list(5000)
                team_div = {str(t["_id"]): t.get("division") for t in all_league_teams}
                div_wins: dict = {str(t["_id"]): 0 for t in all_league_teams}
                for mm in completed:
                    hid = mm.get("home_team_id")
                    aid = mm.get("away_team_id")
                    if not hid or not aid:
                        continue
                    # Only count intra-division games
                    if team_div.get(hid) and team_div.get(hid) == team_div.get(aid):
                        hs = float(mm.get("home_score") or 0)
                        as_ = float(mm.get("away_score") or 0)
                        if hs > as_:
                            div_wins[hid] = div_wins.get(hid, 0) + 1
                        elif as_ > hs:
                            div_wins[aid] = div_wins.get(aid, 0) + 1

                for div_name in divisions_seen:
                    div_teams = [t for t in all_league_teams if t.get("division") == div_name]
                    if not div_teams:
                        continue
                    # Skip if someone in this division already crowned this season
                    if any(t.get("division_winner_at") for t in div_teams):
                        continue
                    div_teams_sorted = sorted(
                        div_teams,
                        key=lambda t: (
                            int(t.get("wins", 0) or 0),
                            int(div_wins.get(str(t["_id"]), 0) or 0),
                            float(t.get("points_for", 0.0) or 0.0),
                        ),
                        reverse=True,
                    )
                    winner_team = div_teams_sorted[0]
                    winner_id = str(winner_team["_id"])
                    winner_name = winner_team.get("name", "Unknown")
                    await db.teams.update_one(
                        {"_id": winner_team["_id"]},
                        {"$set": {"division_winner_at": now}},
                    )
                    await db.activity_feed.insert_one({
                        "league_id": input.league_id,
                        "event_type": "division_awarded",
                        "description": f"🏅 {winner_name} won the {div_name} Division!",
                        "message": f"Division champion crowned: {winner_name} ({div_name})",
                        "created_at": now,
                    })
                    await db.audit_log.insert_one({
                        "league_id": input.league_id,
                        "actor_id": "system",
                        "actor_name": "System (auto-crown)",
                        "action": "division_awarded_regular_season",
                        "role": "system",
                        "diff": {
                            "winner_team_id": winner_id,
                            "division": div_name,
                            "wins": winner_team.get("wins", 0),
                            "division_wins": div_wins.get(winner_id, 0),
                            "points_for": winner_team.get("points_for", 0.0),
                            "reason": "end_of_regular_season",
                        },
                        "created_at": now,
                    })
                    await sio.emit("division_crowned", {
                        "league_id": input.league_id,
                        "team_id": winner_id,
                        "team_name": winner_name,
                        "division": div_name,
                        "reason": "end_of_regular_season",
                        "crowned_at": now.isoformat(),
                    })
    except Exception as e:
        logger.warning(f"Division auto-crown skipped: {e}")

    # ─── Auto-snapshot season when last playoff week completes ──────
    try:
        from routes.seasons import _maybe_auto_snapshot_season
        await _maybe_auto_snapshot_season(input.league_id)
    except Exception as e:
        logger.warning(f"Auto-snapshot skipped: {e}")

    return {"week": input.week, "results": results, "matchups_simulated": len(matchups)}
