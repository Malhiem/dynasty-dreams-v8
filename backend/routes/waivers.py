"""Waivers routes — FAAB claims, processing, budget, history.

Extracted from server.py via the standard `setup(deps)` injection pattern.
All logic is verbatim moved from server.py; helpers (db, log_activity,
broadcast_to_room, get_current_user) are injected via the `_deps` dict.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Request

from trade_waiver_engine import WaiverClaimCreate

from utils.roster_rules import compute_minor_eligible

router = APIRouter()
_deps: dict = {}


def setup(deps: dict) -> None:
    _deps.update(deps)


def _db(): return _deps["db"]
def _logger(): return _deps["logger"]
async def _get_user(request): return await _deps["get_current_user"](request)
async def _log_activity(*a, **kw): return await _deps["log_activity"](*a, **kw)
async def _broadcast(*a, **kw): return await _deps["broadcast_to_room"](*a, **kw)


@router.get("/waivers/available")
async def get_waiver_players(
    league_id: Optional[str] = None,
    search: Optional[str] = None,
    position: Optional[str] = None,
    page: int = 1,
    limit: int = 50,
    timeframe: str = "season",
):
    """Get players available on waivers (not on any team roster).

    Iter 182 — `timeframe` echoes through to the response so the
    frontend can render the "rolling out" banner when historical /
    matchup-window data isn't available yet. Real historical stats
    will be supplied by the iter 182 NHL-API backfill once the
    `player_season_stats` collection is populated.
    """
    db = _db()
    # Iter 181 — load the league so minor-eligibility is computed against
    # the same thresholds the commissioner configured (minors_max_age,
    # minors_max_career_games). Falls back to defaults when no league_id
    # is provided.
    league_doc: dict = {}
    if league_id:
        try:
            league_doc = await db.leagues.find_one({"_id": ObjectId(league_id)}) or {}
        except Exception:
            league_doc = {}
    query: dict = {}
    if search:
        query["$or"] = [
            {"name": {"$regex": search, "$options": "i"}},
            {"team": {"$regex": search, "$options": "i"}},
        ]
    if position and position != "all":
        query["position"] = position

    skip = (page - 1) * limit
    players = await db.players.find(query).sort("points", -1).skip(skip).limit(limit).to_list(limit)
    total = await db.players.count_documents(query)

    # Iter 182 — apply prior-season / playoffs stat overrides BEFORE
    # building the response so the Available Players table reflects
    # the chosen timeframe instead of the always-current season points.
    timeframe_supported = (timeframe == "season")
    season_stats_by_pid: dict = {}
    if timeframe in ("2024-25", "2023-24", "2024-playoffs", "2023-playoffs"):
        prior_match: dict
        if timeframe.endswith("-playoffs"):
            year = timeframe.split("-")[0]
            prior_match = {
                "season": "2024-25" if year == "2024" else "2023-24",
                "season_type": "playoffs",
            }
        else:
            prior_match = {"season": timeframe, "season_type": "regular"}
        pid_strs = [str(p["_id"]) for p in players]
        cached = await db.player_season_stats.find(
            {**prior_match, "player_id": {"$in": pid_strs}}
        ).to_list(len(pid_strs))
        if cached:
            timeframe_supported = True
            season_stats_by_pid = {row["player_id"]: row for row in cached}

    result = []
    for p in players:
        active_claim = await db.waiver_claims.find_one({
            "player_id": str(p["_id"]),
            "status": "pending",
        })
        # Default stats = current season values from the player doc.
        stats = {
            "points": p.get("points", 0),
            "goals": p.get("goals", 0),
            "assists": p.get("assists", 0),
            "games_played": p.get("games_played", 0),
        }
        # If the user picked a prior-season timeframe and we have a
        # cached row for this player, override with that row's
        # values. Players without cached rows (most prospects) drop
        # to all-zeros so the user can clearly see "no data".
        if timeframe in ("2024-25", "2023-24", "2024-playoffs", "2023-playoffs"):
            cached_row = season_stats_by_pid.get(str(p["_id"]))
            if cached_row:
                stats = {
                    "points": cached_row.get("points", 0),
                    "goals": cached_row.get("goals", 0),
                    "assists": cached_row.get("assists", 0),
                    "games_played": cached_row.get("games_played", 0),
                }
            else:
                stats = {"points": 0, "goals": 0, "assists": 0, "games_played": 0}
        result.append({
            "id": str(p["_id"]),
            "name": p["name"],
            "position": p["position"],
            "team": p.get("team", ""),
            "team_name": p.get("team_name", ""),
            **stats,
            "has_active_claim": active_claim is not None,
            # Iter 181 — surface prospect / minor-eligibility so the
            # Waivers / Players directory can render the same Minors
            # leaf badge as the roster, trade block, depth chart, etc.
            "player_type": p.get("player_type") or "skater",
            "minor_eligible": compute_minor_eligible(p, league_doc),
        })

    return {
        "players": result,
        "total": total,
        "page": page,
        "pages": (total + limit - 1) // limit,
        "timeframe": timeframe,
        "timeframe_supported": timeframe_supported,
    }


@router.get("/waivers/suggest")
async def suggest_free_agent(
    request: Request,
    league_id: str, position: Optional[str] = None, limit: int = 1,
):
    """Suggest the top-N free agents for the given position. Used by the
    smart drop toast on Team page — pre-loads the best replacement so the
    user can pick up a free agent in one click.

    Paywall **removed** — previously Pro-only, now available to all users.

    Excludes players already rostered in this league. Returns players sorted
    by FPTS (computed against the league's scoring config) descending.
    """
    db = _db()
    user = await _get_user(request)
    # Build set of player_ids already rostered in this league
    teams = await db.teams.find({"league_id": league_id}, {"roster": 1}).to_list(50)
    rostered_ids = set()
    for t in teams:
        for pid in (t.get("roster") or []):
            rostered_ids.add(pid)

    rostered_obj_ids = []
    for pid in rostered_ids:
        try:
            rostered_obj_ids.append(ObjectId(pid))
        except Exception:
            pass

    query: dict = {"_id": {"$nin": rostered_obj_ids}}
    if position and position not in ("all", "ALL"):
        query["position"] = position

    cursor = db.players.find(query).sort("points", -1).limit(max(1, min(limit * 5, 50)))
    players = await cursor.to_list(50)

    cfg = await db.scoring_configs.find_one({"league_id": league_id})
    from server import calculate_fantasy_points  # type: ignore

    out = []
    for p in players:
        try:
            fpts = calculate_fantasy_points(p, cfg)
        except Exception:
            fpts = float(p.get("points") or 0)
        gp = int(p.get("games_played") or 0)
        out.append({
            "id": str(p["_id"]),
            "name": p["name"],
            "position": p["position"],
            "team": p.get("team", ""),
            "team_name": p.get("team_name", ""),
            "fantasy_points": round(fpts, 1),
            "fpg": round(fpts / gp, 2) if gp > 0 else None,
            "games_played": gp,
        })

    out.sort(key=lambda r: -r["fantasy_points"])
    return {"league_id": league_id, "position": position, "suggestions": out[:max(1, limit)]}


@router.get("/waivers/precheck")
async def precheck_waiver_claim(
    league_id: str,
    player_id: str,
    request: Request,
    bid_amount: float = 0,
):
    """Returns a structured precheck report for the Waivers claim modal.

    The frontend uses this on modal open to surface roster-space, cap-space,
    and illegal-placement issues BEFORE the user commits to a claim. When
    `requires_drop` is true the modal shows a "Proceed to Drop Player"
    button that deep-links to the roster page.

    Shape:
      {
        "can_claim": bool,                  # No blocking issues remain
        "requires_drop": bool,              # Roster will overflow on win
        "roster": { current, max, has_room, taxi_count, ir_count },
        "cap":    { enabled, used, cap, would_be, fits, addition },
        "issues": [{code, severity, message, suggested_action?}],
        "team":   { id, name },
      }
    """
    db = _db()
    user = await _get_user(request)

    team = await db.teams.find_one({"league_id": league_id, "owner_id": user["_id"]})
    if not team:
        raise HTTPException(status_code=403, detail="You don't have a team in this league")
    league = await db.leagues.find_one({"_id": ObjectId(league_id)}) or {}
    player = await db.players.find_one({"_id": ObjectId(player_id)})
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")

    # ── Roster space ──
    roster_ids = team.get("roster", []) or []
    lineup = team.get("lineup") or {}
    max_roster_size = int(league.get("roster_size") or 23)
    # taxi/IR slot sizes are read but not yet enforced as blockers here —
    # we only segment counts so the modal can show the breakdown.

    # Active roster = everything NOT in taxi/ir/ir_plus sections.
    def _section_count(name: str) -> int:
        return sum(
            1 for pid in roster_ids
            if (lineup.get(pid) or {}).get("section", "").lower() == name
        )
    taxi_count = _section_count("taxi")
    ir_count = _section_count("ir")
    ir_plus_count = _section_count("ir_plus")
    active_count = len(roster_ids) - taxi_count - ir_count - ir_plus_count
    has_room = active_count < max_roster_size

    # ── Cap space ──
    cap_enabled = bool(league.get("salary_cap_enabled"))
    cap_total = float(league.get("salary_cap") or 0)
    cap_used = float(team.get("salary_used") or 0)
    # Synthesize the incoming player's salary the same way the roster page
    # does, so the precheck is consistent with what the user sees.
    p_points = int(player.get("points") or 0)
    p_fp = float(player.get("fantasy_points") or 0)
    is_g = (player.get("player_type") == "goalie") or (player.get("position") == "G")
    if is_g:
        addition = 9_500_000 if p_fp >= 300 else (
            6_000_000 if p_fp >= 180 else (3_500_000 if p_fp >= 100 else 1_200_000)
        )
    elif p_points >= 100:
        addition = 11_000_000 + min(2_500_000, (p_points - 100) * 70_000)
    elif p_points >= 60:
        addition = 6_000_000 + (p_points - 60) * 100_000
    elif p_points >= 30:
        addition = 3_000_000 + (p_points - 30) * 90_000
    elif p_points >= 10:
        addition = 1_500_000 + (p_points - 10) * 75_000
    else:
        addition = 950_000 + p_points * 40_000
    addition = int(min(13_500_000, max(775_000, addition)))
    cap_would_be = cap_used + addition
    cap_fits = (not cap_enabled) or (cap_would_be <= cap_total)

    # ── Roster legality scan ──
    # Surface known illegal placements the COMMISH usually wants flagged so
    # the user knows their roster will be flagged after the claim lands.
    issues: list[dict] = []
    player_oids = [ObjectId(pid) for pid in roster_ids]
    roster_docs = await db.players.find({"_id": {"$in": player_oids}}).to_list(100)
    by_id = {str(p["_id"]): p for p in roster_docs}
    for pid in roster_ids:
        section = (lineup.get(pid) or {}).get("section", "").lower()
        rp = by_id.get(pid)
        if not rp:
            continue
        # Healthy player on IR (allow rule may be on, but it's still worth flagging).
        if section in ("ir", "ir_plus") and not rp.get("is_injured"):
            issues.append({
                "code": "healthy_on_ir",
                "severity": "warning",
                "message": f"{rp.get('name', 'A player')} is on {section.upper()} but isn't flagged as injured.",
            })
        # Illegal player in minors — typically a non-prospect veteran sitting in
        # the minor-league slot. We treat "veteran in minors" as the heuristic
        # since prospect status isn't always set; commissioners can tune via
        # admin rules. Threshold: 30+ NHL games played.
        if section == "minors" and int(rp.get("games_played") or 0) >= 30:
            issues.append({
                "code": "illegal_minors_placement",
                "severity": "warning",
                "message": f"{rp.get('name', 'A player')} has played {rp.get('games_played')} NHL games — typically too many for Minors.",
            })

    # ── Combine into top-level blockers ──
    blockers: list[dict] = []
    if not has_room:
        blockers.append({
            "code": "no_roster_space",
            "severity": "error",
            "message": (
                f"Active roster is at {active_count}/{max_roster_size}. "
                "You must drop a player before this claim can succeed."
            ),
            "suggested_action": "drop",
        })
    if cap_enabled and not cap_fits:
        blockers.append({
            "code": "insufficient_cap",
            "severity": "error",
            "message": (
                f"Adding this player would put you at ${cap_would_be/1_000_000:.2f}M, "
                f"exceeding the ${cap_total/1_000_000:.1f}M cap."
            ),
            "suggested_action": "drop",
        })
    if bid_amount and bid_amount > 0:
        budget = await db.waiver_budgets.find_one({
            "team_id": str(team["_id"]), "league_id": league_id,
        })
        remaining = float(budget["remaining"]) if budget else float(
            league.get("waiver_faab_budget") or 100
        )
        if bid_amount > remaining:
            blockers.append({
                "code": "insufficient_faab",
                "severity": "error",
                "message": f"Bid ${bid_amount:.0f} exceeds remaining FAAB of ${remaining:.0f}.",
            })

    requires_drop = any(b.get("suggested_action") == "drop" for b in blockers)
    can_claim = len(blockers) == 0

    return {
        "can_claim": can_claim,
        "requires_drop": requires_drop,
        "roster": {
            "current": active_count,
            "max": max_roster_size,
            "has_room": has_room,
            "taxi_count": taxi_count,
            "ir_count": ir_count,
            "ir_plus_count": ir_plus_count,
        },
        "cap": {
            "enabled": cap_enabled,
            "used": cap_used,
            "cap": cap_total,
            "addition": addition,
            "would_be": cap_would_be,
            "fits": cap_fits,
        },
        "issues": issues + blockers,
        "team": {"id": str(team["_id"]), "name": team["name"]},
    }


@router.post("/waivers/claim")
async def place_waiver_claim(input: WaiverClaimCreate, request: Request):
    db = _db()
    user = await _get_user(request)

    team = await db.teams.find_one({"league_id": input.league_id, "owner_id": user["_id"]})
    if not team:
        raise HTTPException(status_code=403, detail="You don't have a team in this league")

    league = await db.leagues.find_one({"_id": ObjectId(input.league_id)}) or {}

    player = await db.players.find_one({"_id": ObjectId(input.player_id)})
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")

    team_budget = await db.waiver_budgets.find_one({
        "team_id": str(team["_id"]),
        "league_id": input.league_id,
    })
    if not team_budget:
        # FAAB budget per team is configurable via League Admin
        # (`waiver_faab_budget`). Defaults to 100 to preserve legacy behaviour.
        budget_default = float(league.get("waiver_faab_budget") or 100)
        team_budget = {
            "team_id": str(team["_id"]),
            "league_id": input.league_id,
            "total_budget": budget_default,
            "spent": 0.0,
            "remaining": budget_default,
        }
        await db.waiver_budgets.insert_one(team_budget)

    if input.bid_amount > team_budget["remaining"]:
        raise HTTPException(status_code=400, detail=f"Insufficient FAAB budget. Remaining: ${team_budget['remaining']}")

    existing = await db.waiver_claims.find_one({
        "team_id": str(team["_id"]),
        "player_id": input.player_id,
        "status": "pending",
    })
    if existing:
        raise HTTPException(status_code=400, detail="You already have a pending claim for this player")

    # ── Transactions-config gates (iter 117) ────────────────────────
    from utils.transactions_enforce import enforce_claim
    await enforce_claim(db, team_id=str(team["_id"]), league=league, player=player, tx_kind="waiver")

    # Iter 119 — Force-drop-on-claim: when the waiver section's
    # `force_drop_on_claim` toggle is on, every waiver claim MUST nominate
    # a drop_player_id (or move the player to IR — that path isn't
    # implemented yet, so we require an explicit drop for now).
    tx_cfg = (league.get("transactions_config") or {})
    waiver_cfg = (tx_cfg.get("waiver") or {})
    if waiver_cfg.get("enabled") and waiver_cfg.get("force_drop_on_claim") and not input.drop_player_id:
        raise HTTPException(
            status_code=400,
            detail="This league requires every waiver claim to include a player to drop (or move to IR).",
        )

    claim_doc = {
        "league_id": input.league_id,
        "team_id": str(team["_id"]),
        "team_name": team["name"],
        "owner_id": user["_id"],
        "player_id": input.player_id,
        "player_name": player["name"],
        "player_position": player["position"],
        "player_team": player.get("team", ""),
        "bid_amount": input.bid_amount,
        "drop_player_id": input.drop_player_id,
        "drop_player_name": None,
        "status": "pending",
        "season": league.get("season") or "2025-2026",
        "week": int(league.get("current_week") or 1),
        "created_at": datetime.now(timezone.utc).isoformat(),
        # `waiver_period_days` is configurable in League Admin. Defaults to 1
        # day (24h) to preserve legacy behaviour when unset. `0` means claims
        # process immediately on next worker cycle.
        "processes_at": (
            datetime.now(timezone.utc)
            + timedelta(hours=int((league.get("waiver_period_days") if league.get("waiver_period_days") is not None else 1)) * 24)
        ).isoformat(),
    }

    if input.drop_player_id:
        drop_player = await db.players.find_one({"_id": ObjectId(input.drop_player_id)})
        if drop_player:
            claim_doc["drop_player_name"] = drop_player["name"]

    result = await db.waiver_claims.insert_one(claim_doc)
    claim_doc["_id"] = str(result.inserted_id)
    return claim_doc


@router.get("/waivers/claims")
async def get_waiver_claims(
    league_id: Optional[str] = None,
    my_claims: bool = False,
    status: Optional[str] = None,
    request: Request = None,
):
    db = _db()
    query: dict = {}
    if league_id:
        query["league_id"] = league_id
    if status:
        query["status"] = status
    viewer = None
    if my_claims:
        try:
            user = await _get_user(request)
            viewer = user
            query["owner_id"] = user["_id"]
        except Exception:
            pass
    else:
        # Capture the viewer (if any) so we can apply anonymous masking
        try:
            viewer = await _get_user(request)
        except Exception:
            viewer = None

    claims = await db.waiver_claims.find(query).sort("created_at", -1).to_list(200)
    for c in claims:
        c["_id"] = str(c["_id"])

    # ── Iter 129: backend-side anonymous masking ──
    # When the league has `waiver.pending_visibility == "all_teams_anonymous"`,
    # mask team_name + owner_id on every claim EXCEPT:
    #   - claims owned by the viewer (they always see their own data),
    #   - the league commissioner / co-commissioners.
    # Letter labels are stable per (league_id, team_id) so the same team
    # always appears as e.g. "Team C" across pages / refreshes.
    if league_id and claims:
        league = await db.leagues.find_one({"_id": ObjectId(league_id)}) or {}
        tx_cfg = (league.get("transactions_config") or {})
        waiver_cfg = (tx_cfg.get("waiver") or {})
        visibility = waiver_cfg.get("pending_visibility") or "own"
        if visibility == "all_teams_anonymous":
            commish = league.get("commissioner_id")
            co_comms = league.get("co_commissioners") or []
            is_privileged = (
                viewer is not None
                and (viewer["_id"] == commish or viewer["_id"] in co_comms)
            )
            if not is_privileged:
                viewer_id = viewer["_id"] if viewer else None
                # Build a stable team_id → letter map for this league
                teams = await db.teams.find({"league_id": league_id}).to_list(50)
                sorted_team_ids = sorted([str(t["_id"]) for t in teams])
                letter_map: dict[str, str] = {}
                for idx, tid in enumerate(sorted_team_ids):
                    letter = chr(65 + (idx % 26))
                    suffix = "" if idx < 26 else str(idx // 26 + 1)
                    letter_map[tid] = f"Team {letter}{suffix}"
                for c in claims:
                    if c.get("owner_id") == viewer_id:
                        continue  # owner sees their own claim un-masked
                    c["team_name_real"] = c.get("team_name")  # debug-only
                    c["team_name"] = letter_map.get(c.get("team_id"), "Anonymous")
                    c["owner_id"] = None
                    # Strip the debug-only mirror before responding
                    del c["team_name_real"]

    return claims


@router.delete("/waivers/claims/{claim_id}")
async def cancel_waiver_claim(claim_id: str, request: Request):
    db = _db()
    user = await _get_user(request)
    claim = await db.waiver_claims.find_one({"_id": ObjectId(claim_id)})
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")
    if claim["owner_id"] != user["_id"]:
        raise HTTPException(status_code=403, detail="Not your claim")
    if claim["status"] != "pending":
        raise HTTPException(status_code=400, detail="Claim is not pending")

    await db.waiver_claims.update_one(
        {"_id": ObjectId(claim_id)},
        {"$set": {"status": "cancelled"}},
    )
    return {"message": "Claim cancelled"}


@router.get("/waivers/budget")
async def get_waiver_budget(league_id: str, request: Request = None):
    db = _db()
    user = await _get_user(request)
    team = await db.teams.find_one({"league_id": league_id, "owner_id": user["_id"]})
    if not team:
        raise HTTPException(status_code=403, detail="No team in this league")

    budget = await db.waiver_budgets.find_one({
        "team_id": str(team["_id"]),
        "league_id": league_id,
    })
    if not budget:
        # Honour the configured league budget instead of hardcoded $100.
        league = await db.leagues.find_one({"_id": ObjectId(league_id)})
        budget_default = float((league or {}).get("waiver_faab_budget") or 100)
        budget = {
            "team_id": str(team["_id"]),
            "league_id": league_id,
            "total_budget": budget_default,
            "spent": 0.0,
            "remaining": budget_default,
        }
        await db.waiver_budgets.insert_one(budget)

    budget["_id"] = str(budget["_id"]) if "_id" in budget else None
    return budget


@router.get("/waivers/order")
async def get_waiver_order(league_id: str):
    """Get waiver priority order (inverse of standings)."""
    db = _db()
    teams = await db.teams.find({"league_id": league_id}).to_list(100)
    teams.sort(key=lambda t: (t.get("wins", 0), t.get("points_for", 0)))

    order = []
    for i, team in enumerate(teams):
        order.append({
            "rank": i + 1,
            "team_id": str(team["_id"]),
            "team_name": team["name"],
            "owner_name": team["owner_name"],
            "wins": team.get("wins", 0),
            "losses": team.get("losses", 0),
        })
    return order


@router.get("/waivers/history")
async def get_waiver_history(league_id: Optional[str] = None, limit: int = 50):
    db = _db()
    query: dict = {"status": {"$in": ["won", "lost", "processed"]}}
    if league_id:
        query["league_id"] = league_id
    claims = await db.waiver_claims.find(query).sort("created_at", -1).to_list(limit)
    for c in claims:
        c["_id"] = str(c["_id"])
    return claims


@router.post("/waivers/process")
async def process_waivers(league_id: str, request: Request):
    """Commissioner-only: process all pending waiver claims for a league."""
    db = _db()
    logger = _logger()
    user = await _get_user(request)
    league = await db.leagues.find_one({"_id": ObjectId(league_id)})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    if league["commissioner_id"] != user["_id"]:
        raise HTTPException(status_code=403, detail="Only commissioner can process waivers")

    pending = await db.waiver_claims.find({
        "league_id": league_id,
        "status": "pending",
    }).to_list(1000)

    if not pending:
        return {"message": "No pending claims to process", "processed": 0}

    # Position-limit enforcement (iter 83) — only used when the league has
    # `enforce_position_maxes` ON; loaded once and reused per-claim. Skipped
    # losers must mirror the same DENIED disposition as winners.
    from utils.roster_rules import check_position_limits
    enforce_positions = bool(league.get("enforce_position_maxes"))
    position_limits = league.get("position_limits") or {}

    player_claims: dict = {}
    for claim in pending:
        pid = claim["player_id"]
        player_claims.setdefault(pid, []).append(claim)

    processed_count = 0
    results = []

    for player_id, claims in player_claims.items():
        claims.sort(key=lambda c: (-c["bid_amount"], c["created_at"]))

        # Pre-roll: if position-limits are on, skip claimants whose roster is
        # already at the cap for this player's position. The next-in-line bid
        # gets promoted to winner. If everyone is blocked, the claim is
        # marked `denied` instead of leaving the winner in a broken state.
        winner = None
        denied_for_positions: list = []
        if enforce_positions and position_limits:
            try:
                player_doc = await db.players.find_one({"_id": ObjectId(player_id)})
            except Exception:
                player_doc = None
            for cand in claims:
                if player_doc is None:
                    winner = cand
                    break
                team_doc = await db.teams.find_one(
                    {"_id": ObjectId(cand["team_id"])},
                    {"roster": 1},
                )
                roster_ids = (team_doc or {}).get("roster") or []
                oids = []
                for rid in roster_ids:
                    try:
                        oids.append(ObjectId(rid))
                    except Exception:
                        pass
                roster_players = (
                    await db.players.find(
                        {"_id": {"$in": oids}},
                        {"name": 1, "position": 1, "primary_position": 1,
                         "eligible_positions": 1, "player_type": 1},
                    ).to_list(200) if oids else []
                )
                err = check_position_limits(league, roster_players, player_doc)
                if err is None:
                    winner = cand
                    break
                denied_for_positions.append((cand, err))
            losers = [c for c in claims if c is not winner and c not in [d[0] for d in denied_for_positions]]
        else:
            winner = claims[0]
            losers = claims[1:]

        # Mark position-blocked claims as `denied` (audit-friendly)
        for cand, err in denied_for_positions:
            await db.waiver_claims.update_one(
                {"_id": cand["_id"]},
                {"$set": {
                    "status": "denied",
                    "denied_reason": err,
                    "processed_at": datetime.now(timezone.utc).isoformat(),
                }},
            )

        if winner is None:
            # Nobody could legally roster the player — refund attempted bids
            # and skip the player entirely.
            continue

        await db.waiver_claims.update_one(
            {"_id": winner["_id"]},
            {"$set": {"status": "won", "processed_at": datetime.now(timezone.utc).isoformat()}},
        )
        await db.waiver_budgets.update_one(
            {"team_id": winner["team_id"], "league_id": league_id},
            {"$inc": {"spent": winner["bid_amount"], "remaining": -winner["bid_amount"]}},
        )

        for loser in losers:
            await db.waiver_claims.update_one(
                {"_id": loser["_id"]},
                {"$set": {"status": "lost", "processed_at": datetime.now(timezone.utc).isoformat()}},
            )
            await _log_activity(
                league_id,
                "waiver_lost",
                f"{loser['team_name']} lost waiver claim on {loser['player_name']} (${loser['bid_amount']} FAAB) — won by {winner['team_name']} (${winner['bid_amount']})",
                None,
                metadata={
                    "team_id": loser["team_id"],
                    "team_name": loser["team_name"],
                    "player_id": loser["player_id"],
                    "player_name": loser["player_name"],
                    "bid_amount": loser["bid_amount"],
                    "winning_team_id": winner["team_id"],
                    "winning_team_name": winner["team_name"],
                    "winning_bid": winner["bid_amount"],
                },
            )

        try:
            await db.teams.update_one(
                {"_id": ObjectId(winner["team_id"])},
                {"$addToSet": {"roster": winner["player_id"]}},
            )
        except Exception as ex:
            logger.warning(
                "Failed to add waiver-won player to roster team=%s player=%s: %s",
                winner["team_id"], winner["player_id"], ex,
            )

        await _log_activity(
            league_id,
            "waiver_won",
            f"{winner['team_name']} won {winner['player_name']} on waivers (${winner['bid_amount']} FAAB)",
            None,
            metadata={
                "team_id": winner["team_id"],
                "team_name": winner["team_name"],
                "player_id": winner["player_id"],
                "player_name": winner["player_name"],
                "bid_amount": winner["bid_amount"],
                "competing_claims": [
                    {"team_id": l["team_id"], "team_name": l["team_name"], "bid_amount": l["bid_amount"]}
                    for l in losers
                ],
            },
        )

        results.append({
            "player": winner["player_name"],
            "winner": winner["team_name"],
            "bid": winner["bid_amount"],
        })
        processed_count += 1

    await _broadcast(f"league_{league_id}", "waivers_processed", {"results": results})
    return {"message": f"Processed {processed_count} waiver claims", "processed": processed_count, "results": results}
