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
):
    """Get players available on waivers (not on any team roster)."""
    db = _db()
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

    result = []
    for p in players:
        active_claim = await db.waiver_claims.find_one({
            "player_id": str(p["_id"]),
            "status": "pending",
        })
        result.append({
            "id": str(p["_id"]),
            "name": p["name"],
            "position": p["position"],
            "team": p.get("team", ""),
            "team_name": p.get("team_name", ""),
            "points": p.get("points", 0),
            "goals": p.get("goals", 0),
            "assists": p.get("assists", 0),
            "games_played": p.get("games_played", 0),
            "has_active_claim": active_claim is not None,
        })

    return {"players": result, "total": total, "page": page, "pages": (total + limit - 1) // limit}


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
    if my_claims:
        try:
            user = await _get_user(request)
            query["owner_id"] = user["_id"]
        except Exception:
            pass

    claims = await db.waiver_claims.find(query).sort("created_at", -1).to_list(200)
    for c in claims:
        c["_id"] = str(c["_id"])
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
