"""Awards / Consolation Prize / Team Rewards routes."""
from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter()

# Injected via setup()
_deps: dict = {}


def setup(deps: dict) -> None:
    _deps.update(deps)


def _db():  return _deps["db"]
def _logger():  return _deps["logger"]


# ─── Pydantic models ─────────────────────────────────────────────
class TeamAwardUpdate(BaseModel):
    championship_won: Optional[bool] = None
    division_winner: Optional[bool] = None
    conference_winner: Optional[bool] = None
    playoffs_reached: Optional[bool] = None
    consolation_won: Optional[bool] = None


class ConsolationPrize(BaseModel):
    type: str  # "draft_lottery_boost" | "compensation_pick" | "custom"
    description: Optional[str] = None
    lottery_boost_spots: Optional[int] = None
    fallback_pick_round: Optional[int] = None
    fallback_pick_year: Optional[int] = None
    custom_details: Optional[str] = None


class ConsolationPrizeUpdate(BaseModel):
    prize: ConsolationPrize


# ─── Helpers ────────────────────────────────────────────────────
async def apply_consolation_prize(league_id: str, team_id: str, prize: dict) -> dict:
    """Auto-apply lottery boost / compensation pick. Custom prizes left for manual fulfilment."""
    db = _db()
    applied = {"type": prize.get("type"), "steps": []}
    prize_type = prize.get("type")
    now = datetime.now(timezone.utc)
    team = await db.teams.find_one({"_id": ObjectId(team_id)})
    team_name = team.get("name") if team else None

    if prize_type == "draft_lottery_boost":
        spots = int(prize.get("lottery_boost_spots") or 0)
        if spots <= 0:
            return applied
        next_year = now.year + 1
        pick = await db.draft_picks.find_one({
            "league_id": league_id, "year": next_year, "round": 1,
            "current_team_id": team_id,
        })
        if pick:
            new_slot = max(1, (pick.get("pick_number") or 12) - spots)
            await db.draft_picks.update_one(
                {"_id": pick["_id"]},
                {"$set": {"pick_number": new_slot, "lottery_boost_applied": spots}}
            )
            applied["steps"].append(f"Moved {next_year} R1 pick up {spots} slot(s) to pick #{new_slot}")
        else:
            comp_round = prize.get("fallback_pick_round") or 2
            comp_year = prize.get("fallback_pick_year") or next_year
            await db.draft_picks.insert_one({
                "league_id": league_id, "year": comp_year, "round": int(comp_round),
                "original_team_id": team_id, "original_team_name": team_name,
                "current_team_id": team_id, "current_team_name": team_name,
                "pick_number": None, "pick_type": "compensation",
                "reason": "consolation_winner_no_r1_available", "created_at": now,
            })
            applied["steps"].append(
                f"1st-rounder unavailable — awarded compensation R{comp_round} pick in {comp_year}"
            )
    elif prize_type == "compensation_pick":
        comp_round = prize.get("fallback_pick_round") or 2
        comp_year = prize.get("fallback_pick_year") or now.year + 1
        await db.draft_picks.insert_one({
            "league_id": league_id, "year": comp_year, "round": int(comp_round),
            "original_team_id": team_id, "original_team_name": team_name,
            "current_team_id": team_id, "current_team_name": team_name,
            "pick_number": None, "pick_type": "compensation",
            "reason": "consolation_winner", "created_at": now,
        })
        applied["steps"].append(f"Awarded compensation R{comp_round} pick in {comp_year}")
    elif prize_type == "custom":
        applied["steps"].append(
            f"Custom prize '{prize.get('custom_details') or prize.get('description')}' logged for manual fulfilment"
        )
    return applied


# ─── Endpoints ─────────────────────────────────────────────────
@router.put("/leagues/{league_id}/teams/{team_id}/awards")
async def set_team_awards(league_id: str, team_id: str, payload: TeamAwardUpdate, request: Request):
    """Commissioner tool: mark a team with season-end awards (triggers conditional trades)."""
    db = _db()
    get_current_user = _deps["get_current_user"]
    _safe_object_id = _deps["_safe_object_id"]
    _evaluate_conditions = _deps["_evaluate_conditions"]
    _execute_trade = _deps["_execute_trade"]
    logger = _logger()

    user = await get_current_user(request)
    league = await db.leagues.find_one({"_id": _safe_object_id(league_id, "league_id")})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    is_comm = league["commissioner_id"] == user["_id"]
    co_comms = league.get("co_commissioners", []) or []
    is_co_comm = user["_id"] in co_comms
    if not (is_comm or is_co_comm):
        raise HTTPException(status_code=403, detail="Only commissioners can set team awards")

    team = await db.teams.find_one({"_id": _safe_object_id(team_id, "team_id"), "league_id": league_id})
    if not team:
        raise HTTPException(status_code=404, detail="Team not found in this league")

    now = datetime.now(timezone.utc)
    update_set: dict = {}
    update_unset: dict = {}
    changes: list = []
    field_map = [
        ("championship_won", "championship_won_at"),
        ("division_winner", "division_winner_at"),
        ("conference_winner", "conference_winner_at"),
        ("playoffs_reached", "playoffs_reached_at"),
        ("consolation_won", "consolation_won_at"),
    ]
    for attr, db_field in field_map:
        v = getattr(payload, attr)
        if v is True:
            update_set[db_field] = now
            changes.append(f"{db_field} set")
        elif v is False:
            update_unset[db_field] = ""
            changes.append(f"{db_field} cleared")

    ops: dict = {}
    if update_set:
        ops["$set"] = update_set
    if update_unset:
        ops["$unset"] = update_unset
    if ops:
        await db.teams.update_one({"_id": team["_id"]}, ops)

    await db.audit_log.insert_one({
        "league_id": league_id,
        "actor_id": user["_id"],
        "actor_name": user.get("name", user.get("email", "Unknown")),
        "action": "team_award_updated",
        "role": "commissioner" if is_comm else "co_commissioner",
        "diff": {"team_id": team_id, "team_name": team.get("name"), "changes": changes},
        "created_at": now,
    })

    # Evaluate any conditional trades in this league that might now unlock
    unlocked = 0
    pending = await db.trades.find({
        "league_id": league_id, "conditional": True,
        "status": {"$in": ["pending", "accepted", "conditional"]}
    }).to_list(500)
    for t in pending:
        try:
            res = await _evaluate_conditions(t)
            if res["all_met"] and t.get("status") == "accepted":
                await _execute_trade(t)
                unlocked += 1
        except Exception as ex:
            logger.warning("Conditional trade re-eval failed league=%s trade=%s: %s",
                           league_id, str(t.get("_id")), ex)

    fresh = await db.teams.find_one({"_id": team["_id"]})
    return {
        "team_id": team_id,
        "team_name": fresh.get("name"),
        "championship_won_at": fresh.get("championship_won_at"),
        "division_winner_at": fresh.get("division_winner_at"),
        "conference_winner_at": fresh.get("conference_winner_at"),
        "playoffs_reached_at": fresh.get("playoffs_reached_at"),
        "consolation_won_at": fresh.get("consolation_won_at"),
        "changes": changes,
        "unlocked_trades": unlocked,
    }


@router.put("/leagues/{league_id}/consolation-prize")
async def set_consolation_prize(league_id: str, payload: ConsolationPrizeUpdate, request: Request):
    db = _db()
    get_current_user = _deps["get_current_user"]
    _safe_object_id = _deps["_safe_object_id"]

    user = await get_current_user(request)
    league = await db.leagues.find_one({"_id": _safe_object_id(league_id, "league_id")})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    is_comm = league["commissioner_id"] == user["_id"]
    co_comms = league.get("co_commissioners", []) or []
    if not (is_comm or user["_id"] in co_comms):
        raise HTTPException(status_code=403, detail="Only commissioners can set the consolation prize")

    prize_dict = payload.prize.dict()
    await db.leagues.update_one({"_id": league["_id"]}, {"$set": {"consolation_prize": prize_dict}})
    await db.audit_log.insert_one({
        "league_id": league_id,
        "actor_id": user["_id"],
        "actor_name": user.get("name", user.get("email", "Unknown")),
        "action": "consolation_prize_configured",
        "role": "commissioner" if is_comm else "co_commissioner",
        "diff": prize_dict,
        "created_at": datetime.now(timezone.utc),
    })
    return {"league_id": league_id, "consolation_prize": prize_dict}


@router.get("/leagues/{league_id}/consolation-prize")
async def get_consolation_prize(league_id: str):
    db = _db()
    _safe_object_id = _deps["_safe_object_id"]

    league = await db.leagues.find_one(
        {"_id": _safe_object_id(league_id, "league_id")},
        {"consolation_prize": 1}
    )
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    return {"league_id": league_id, "consolation_prize": league.get("consolation_prize")}


@router.get("/leagues/{league_id}/team-rewards")
async def list_team_rewards(league_id: str):
    db = _db()
    rewards = await db.team_rewards.find({"league_id": league_id}).sort("awarded_at", -1).to_list(200)
    for r in rewards:
        r["_id"] = str(r["_id"])
    return {"league_id": league_id, "rewards": rewards}
