"""League-scoped draft salary statuses and manager roster controls."""
from datetime import datetime, timezone
from typing import Optional
from bson import ObjectId
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from routes.league_guards import require_league_member
from routes._authz import is_league_admin
from services.financial_lock import serialize_finances
from services.draft_salary import (load_context, evaluate, evaluate_roster, team_summary,
    entry, validate_lineup, mode, warning)
from draft_engine import get_team_for_pick

router = APIRouter()
_deps = {}
def setup(deps):
    _deps.update(deps)
def _db():
    return _deps["db"]

async def resource(draft_id, request):
    user = await _deps["get_current_user"](request)
    if not user:
        raise HTTPException(401, "Authentication required")
    if not ObjectId.is_valid(draft_id):
        raise HTTPException(400, "Invalid draft ID")
    draft = await _db().drafts.find_one({"_id": ObjectId(draft_id)})
    if not draft:
        raise HTTPException(404, "Draft not found")
    league = await require_league_member(_db(), user, draft["league_id"])
    return user, draft, league

async def on_clock_team(db, draft):
    abbr = get_team_for_pick(draft.get("team_abbrs") or [], draft.get("current_pick", 1), draft.get("snake_draft", True), draft.get("bonus_picks"))
    tid = (draft.get("team_map") or {}).get(abbr, {}).get("id")
    if not tid:
        return None
    original = tid
    round_number = (draft.get("current_pick", 1) - 1) // max(1, len(draft.get("team_abbrs") or [])) + 1
    asset = await db.draft_picks.find_one({"draft_id": str(draft["_id"]), "league_id": draft["league_id"],
        "original_team_id": original, "round": round_number})
    tid = (asset or {}).get("current_team_id") or original
    return await db.teams.find_one({"_id": ObjectId(tid)})

@router.get("/drafts/{draft_id}/roster-status")
async def roster_status(draft_id: str, request: Request):
    user, draft, league = await resource(draft_id, request)
    raw = await _db().teams.find({"league_id": draft["league_id"]}).to_list(None)
    teams = [await team_summary(_db(), draft, t, league) for t in raw]
    uid = str(user["_id"])
    for t, original in zip(teams, raw):
        t["can_edit"] = t["owner_id"] == uid or uid in [str(p) for p in original.get("co_owner_ids") or []] or is_league_admin(user, league)
    return {"teams": teams, "mode": mode(league), "salary_cap_enabled": bool(league.get("salary_cap_enabled")),
            "salary_cap": league.get("salary_cap"), "my_team_id": next((t["team_id"] for t in teams if t["owner_id"] == str(user["_id"])), None),
            "version": datetime.now(timezone.utc).isoformat()}

class EligibilityRequest(BaseModel):
    player_ids: list[str] = Field(max_length=200)
    destination: Optional[str] = None

@router.post("/drafts/{draft_id}/salary-eligibility")
async def salary_eligibility(draft_id: str, payload: EligibilityRequest, request: Request):
    _, draft, league = await resource(draft_id, request)
    team = await on_clock_team(_db(), draft)
    if not team:
        return {"players": {}, "mode": mode(league)}
    ctx = await load_context(_db(), draft, team, league)
    from services.draft_salary import capacities, fits
    results = {}
    for pid in payload.player_ids:
        result = evaluate(ctx, pid, payload.destination)
        destinations = {s: evaluate(ctx, pid, s) for s, n in capacities(league).items()
            if n and fits(ctx["players"].get(pid, {}), s, league)}
        result["destinations"] = destinations
        if not payload.destination and not result.get("allowed"):
            alternate = next((r for r in destinations.values() if r.get("allowed")), None)
            if alternate:
                result = {**alternate, "destinations": destinations}
        results[pid] = result
    return {"players": results,
            "team_id": str(team["_id"]), "mode": mode(league), "current_pick": draft.get("current_pick")}

class MoveRequest(BaseModel):
    team_id: str
    player_id: str
    destination: str

@router.post("/drafts/{draft_id}/roster-move")
@serialize_finances(_db)
async def roster_move(draft_id: str, payload: MoveRequest, request: Request):
    user, draft, league = await resource(draft_id, request)
    if not ObjectId.is_valid(payload.team_id):
        raise HTTPException(400, "Invalid team ID")
    team = await _db().teams.find_one({"_id": ObjectId(payload.team_id), "league_id": draft["league_id"]})
    if not team:
        raise HTTPException(404, "Team not found")
    if str(team.get("owner_id")) != str(user["_id"]) and str(user["_id"]) not in [str(p) for p in team.get("co_owner_ids") or []] and not is_league_admin(user, league):
        raise HTTPException(403, "Only the owner or commissioner may edit this roster")
    if payload.player_id not in (team.get("roster") or []):
        raise HTTPException(400, "Player is not owned by this team")
    ctx = await load_context(_db(), draft, team, league)
    proposed = {**ctx["team"], "lineup": {**ctx["team"].get("lineup", {}), payload.player_id: entry(payload.destination)}}
    validate_lineup(proposed, ctx["players"], league)
    ctx = await load_context(_db(), draft, proposed, league)
    result = evaluate_roster(ctx)
    if not result["allowed"]:
        raise HTTPException(409, detail=result)
    await _db().teams.update_one({"_id": team["_id"]}, {"$set": {"lineup": proposed["lineup"], "salary_used": ctx["state"]["used"]}})
    await _db().league_audit.insert_one({"league_id": draft["league_id"], "actor_id": str(user["_id"]),
        "action": "draft_roster_move", "team_id": payload.team_id, "player_id": payload.player_id,
        "destination": payload.destination, "created_at": datetime.now(timezone.utc)})
    await _db().drafts.update_one({"_id": draft["_id"]}, {"$set": {"salary_blocked": False}})
    await warning(_db(), draft, team, result)
    broadcast = _deps.get("broadcast_to_room")
    if broadcast:
        await broadcast(f"league_{draft['league_id']}", "roster_updated", {"team_id": payload.team_id})
    return {"team": await team_summary(_db(), draft, proposed, league), "salary_validation": result}
