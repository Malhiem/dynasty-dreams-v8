"""Contracts + Salary Cap router.

Extracted from server.py during iter 89 modularization. Bundles the
`/contracts` CRUD endpoints and the `/salary-cap/{league_id}` overview /
expiring-contracts endpoints because they share the `get_team_cap_used`
helper (sum of `db.contracts.aav` for a team, falling back to the synthesized
roster salary when no explicit contract exists).
"""
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter()
_deps: dict = {}


def setup(deps: dict) -> None:
    _deps.update(deps)


class ContractStatus(str, Enum):
    ACTIVE = "active"
    INJURED_RESERVE = "ir"
    BUYOUT = "buyout"
    EXPIRED = "expired"


class ContractCreate(BaseModel):
    league_id: str
    team_id: str
    player_id: str
    aav: float = Field(ge=0, description="Average Annual Value")
    total_value: float = Field(ge=0)
    signing_bonus: float = Field(default=0, ge=0)
    years: int = Field(ge=1, le=8)
    start_year: int = Field(default=2025)
    no_trade_clause: bool = False
    no_move_clause: bool = False
    player_status: str = "signed"


class ContractUpdate(BaseModel):
    aav: Optional[float] = None
    status: Optional[str] = None
    no_trade_clause: Optional[bool] = None
    no_move_clause: Optional[bool] = None


async def get_team_cap_used(team_id: str, league_id: str) -> float:
    """Returns the team's active cap usage.

    Source of truth:
      1. Sum of `db.contracts.aav` if any active contracts exist
         (legacy / commissioner-managed).
      2. Otherwise fall back to the synthesized per-player salary used
         everywhere else (`_recompute_team_salary_used`, kept consistent
         with the roster page, compliance check, and
         `/roster/{id}/detail`).
    """
    db = _deps["db"]
    _recompute = _deps["_recompute_team_salary_used"]
    pipeline = [
        {"$match": {"team_id": team_id, "league_id": league_id, "status": "active"}},
        {"$group": {"_id": None, "total": {"$sum": "$aav"}}},
    ]
    result = await db.contracts.aggregate(pipeline).to_list(1)
    if result and result[0]["total"]:
        return result[0]["total"]
    try:
        return await _recompute(team_id)
    except Exception:
        return 0.0


@router.post("/contracts")
async def create_contract(input: ContractCreate, request: Request):
    db = _deps["db"]
    get_current_user = _deps["get_current_user"]
    log_activity = _deps["log_activity"]

    user = await get_current_user(request)

    league = await db.leagues.find_one({"_id": ObjectId(input.league_id)})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")

    team = await db.teams.find_one({"_id": ObjectId(input.team_id)})
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    is_commissioner = league["commissioner_id"] == user["_id"]
    if team["owner_id"] != user["_id"] and not is_commissioner:
        raise HTTPException(status_code=403, detail="Not authorized")

    player = await db.players.find_one({"_id": ObjectId(input.player_id)})
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")

    if league.get("salary_cap_enabled"):
        cap = league.get("salary_cap", 82500000)
        current_used = await get_team_cap_used(input.team_id, input.league_id)
        if current_used + input.aav > cap:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Exceeds salary cap. Used: ${current_used:,.0f}, "
                    f"Cap: ${cap:,.0f}, Contract: ${input.aav:,.0f}"
                ),
            )

    contract_doc = {
        "league_id": input.league_id,
        "team_id": input.team_id,
        "team_name": team["name"],
        "player_id": input.player_id,
        "player_name": player["name"],
        "player_position": player["position"],
        "player_nhl_team": player.get("team", ""),
        "aav": input.aav,
        "total_value": input.total_value,
        "signing_bonus": input.signing_bonus,
        "years": input.years,
        "start_year": input.start_year,
        "end_year": input.start_year + input.years - 1,
        "free_agency_year": input.start_year + input.years,
        "no_trade_clause": input.no_trade_clause,
        "no_move_clause": input.no_move_clause,
        "player_status": input.player_status,
        "status": ContractStatus.ACTIVE.value,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    result = await db.contracts.insert_one(contract_doc)
    contract_doc["_id"] = str(result.inserted_id)

    await log_activity(
        input.league_id,
        "contract_signed",
        f"{team['name']} signs {player['name']} to {input.years}-year, ${input.aav:,.0f} AAV contract",
        user["_id"],
    )

    return contract_doc


@router.get("/contracts")
async def get_contracts(
    league_id: str,
    team_id: Optional[str] = None,
    status: Optional[str] = None,
):
    db = _deps["db"]
    query: dict = {"league_id": league_id}
    if team_id:
        query["team_id"] = team_id
    if status:
        query["status"] = status
    contracts = await db.contracts.find(query).sort("aav", -1).to_list(500)
    for c in contracts:
        c["_id"] = str(c["_id"])
    return contracts


@router.get("/contracts/{contract_id}")
async def get_contract(contract_id: str):
    db = _deps["db"]
    contract = await db.contracts.find_one({"_id": ObjectId(contract_id)})
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")
    contract["_id"] = str(contract["_id"])
    return contract


@router.put("/contracts/{contract_id}")
async def update_contract(contract_id: str, input: ContractUpdate, request: Request):
    db = _deps["db"]
    get_current_user = _deps["get_current_user"]
    user = await get_current_user(request)

    contract = await db.contracts.find_one({"_id": ObjectId(contract_id)})
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")

    league = await db.leagues.find_one({"_id": ObjectId(contract["league_id"])})
    if league["commissioner_id"] != user["_id"]:
        raise HTTPException(status_code=403, detail="Only commissioner can edit contracts")

    updates: dict = {}
    if input.aav is not None:
        updates["aav"] = input.aav
    if input.status is not None:
        updates["status"] = input.status
    if input.no_trade_clause is not None:
        updates["no_trade_clause"] = input.no_trade_clause
    if input.no_move_clause is not None:
        updates["no_move_clause"] = input.no_move_clause

    if updates:
        await db.contracts.update_one({"_id": ObjectId(contract_id)}, {"$set": updates})
    return {"updated": list(updates.keys())}


# ─── Salary Cap ────────────────────────────────────────────────


@router.get("/salary-cap/{league_id}")
async def get_salary_cap_overview(league_id: str):
    db = _deps["db"]
    league = await db.leagues.find_one({"_id": ObjectId(league_id)})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")

    # Default to the historical NHL hard cap ($88M) when the league hasn't
    # explicitly configured one. Avoids ZeroDivisionError on cap_pct.
    cap = league.get("salary_cap") or 88_000_000
    teams = await db.teams.find({"league_id": league_id}).to_list(100)

    team_caps = []
    for team in teams:
        tid = str(team["_id"])
        used = await get_team_cap_used(tid, league_id)
        contracts = await db.contracts.count_documents(
            {"team_id": tid, "league_id": league_id, "status": "active"}
        )

        rfa = await db.contracts.count_documents(
            {"team_id": tid, "league_id": league_id, "player_status": "rfa"}
        )
        ufa = await db.contracts.count_documents(
            {"team_id": tid, "league_id": league_id, "player_status": "ufa"}
        )

        team_caps.append({
            "team_id": tid,
            "team_name": team["name"],
            "owner_name": team["owner_name"],
            "cap_used": round(used, 2),
            "cap_remaining": round(cap - used, 2),
            "cap_pct": round((used / cap) * 100, 1) if cap > 0 else 0,
            "active_contracts": contracts,
            "rfa_count": rfa,
            "ufa_count": ufa,
        })

    team_caps.sort(key=lambda t: -t["cap_used"])
    return {"salary_cap": cap, "teams": team_caps}


@router.get("/salary-cap/{league_id}/expiring")
async def get_expiring_contracts(league_id: str, year: int = 2026):
    db = _deps["db"]
    contracts = await db.contracts.find({
        "league_id": league_id,
        "free_agency_year": year,
        "status": "active",
    }).sort("aav", -1).to_list(200)
    for c in contracts:
        c["_id"] = str(c["_id"])
    return contracts
