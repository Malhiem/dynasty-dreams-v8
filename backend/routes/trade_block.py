"""Trade Block router.

Extracted from server.py during iter 89 modularization. Bundles:
  - POST   /trade-block                              (add an item)
  - GET    /trade-block                              (list, with AAV join)
  - DELETE /trade-block/{item_id}                    (remove a listing)
  - PUT    /teams/{id}/trade-block-note              (set the team's public note)
  - GET    /teams/{id}/trade-block-note              (read the note)
  - PUT    /teams/{id}/trade-block-preference        (retention preference)
  - GET    /leagues/{id}/trade-block-summary         (top-valued items)
  - POST   /leagues/{id}/trade-block/refresh-stats   (refresh season + form)

The cascading delete on trade execution lives in server.py's
`_execute_trade` / `_execute_multi_party_trade` — it's deeply coupled to
the trade state machine and would force a larger refactor to move.
"""
from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from trade_waiver_engine import TradeBlockItemCreate

router = APIRouter()
_deps: dict = {}


def setup(deps: dict) -> None:
    _deps.update(deps)


class SalaryRetentionPrefUpdate(BaseModel):
    preference: str  # "willing_to_retain" | "no_preference" | "seeking_retention"


# ─── Add / List / Remove ───────────────────────────────────────


@router.post("/trade-block")
async def add_to_trade_block(input: TradeBlockItemCreate, request: Request):
    db = _deps["db"]
    get_current_user = _deps["get_current_user"]
    broadcast_to_room = _deps["broadcast_to_room"]

    user = await get_current_user(request)

    resolved_team_id = input.team_id
    if not resolved_team_id and input.league_id:
        owner_team = await db.teams.find_one(
            {"league_id": input.league_id, "owner_id": user["_id"]},
            {"_id": 1},
        )
        if owner_team:
            resolved_team_id = str(owner_team["_id"])

    item_doc: dict = {
        "item_type": input.item_type,
        "looking_for": input.looking_for or [],
        "owner_id": user["_id"],
        "owner_name": user["name"],
        "league_id": input.league_id,
        "team_id": resolved_team_id,
        "note": (input.note or "").strip(),
        "created_at": datetime.now(timezone.utc),
        "draft_only": bool(input.draft_only),
    }

    if resolved_team_id:
        team = await db.teams.find_one({"_id": ObjectId(resolved_team_id)})
        if team:
            item_doc["team_name"] = team.get("name")
            item_doc["salary_retention_pref"] = team.get(
                "salary_retention_pref", "no_preference"
            )

    if input.item_type == "player" and input.player_id:
        player = await db.players.find_one({"_id": ObjectId(input.player_id)})
        if not player:
            raise HTTPException(status_code=404, detail="Player not found")
        item_doc["player_id"] = input.player_id
        item_doc["name"] = player["name"]
        item_doc["position"] = player["position"]
        item_doc["nhl_team"] = player.get("team", "")

        season = player.get("season_stats") or {}
        gp = int(season.get("games_played") or player.get("games_played") or 0)
        item_doc["goals"] = int(season.get("goals") or player.get("goals") or 0)
        item_doc["assists"] = int(season.get("assists") or player.get("assists") or 0)
        item_doc["points"] = int(season.get("points") or player.get("points") or 0)
        item_doc["plus_minus"] = int(season.get("plus_minus") or player.get("plus_minus") or 0)
        item_doc["games_played"] = gp
        fpts = float(player.get("fantasy_points") or season.get("fantasy_points") or 0)
        item_doc["fantasy_points"] = round(fpts, 1)
        item_doc["fantasy_ppg"] = round(fpts / gp, 2) if gp else 0.0

        if input.team_id and input.league_id:
            recent = (
                await db.week_summaries.find({
                    "league_id": input.league_id,
                    "team_id": input.team_id,
                })
                .sort("week", -1)
                .limit(3)
                .to_list(3)
            )
            if recent:
                item_doc["recent_form_ppw"] = round(
                    sum((r.get("points_for", 0.0) or 0.0) for r in recent) / len(recent),
                    1,
                )
    elif input.item_type == "pick":
        if input.pick_id:
            pick = await db.draft_picks.find_one({"_id": ObjectId(input.pick_id)})
            if not pick:
                raise HTTPException(status_code=404, detail="Pick not found")
            item_doc["pick_id"] = input.pick_id
            item_doc["pick_year"] = pick.get("year")
            item_doc["pick_round"] = pick.get("round")
            item_doc["pick_number"] = pick.get("pick_number")
            item_doc["name"] = (
                f"{pick.get('year')} R{pick.get('round')}"
                + (f" #{pick.get('pick_number')}" if pick.get("pick_number") else "")
            )
        else:
            item_doc["name"] = f"{input.pick_year} {input.pick_round} Round"
            item_doc["pick_year"] = input.pick_year
            item_doc["pick_round"] = input.pick_round
        item_doc["position"] = "PICK"

    # Prevent duplicates (per-owner, per-league, per-asset)
    dup_query: dict = {"owner_id": user["_id"], "item_type": input.item_type}
    if input.league_id:
        dup_query["league_id"] = input.league_id
    if input.team_id:
        dup_query["team_id"] = input.team_id
    if input.player_id:
        dup_query["player_id"] = input.player_id
    elif input.pick_id:
        dup_query["pick_id"] = input.pick_id
    elif input.pick_year and input.pick_round:
        dup_query["pick_year"] = input.pick_year
        dup_query["pick_round"] = input.pick_round
    existing = await db.trade_block.find_one(dup_query)
    if existing:
        raise HTTPException(status_code=400, detail="Already on trade block")

    result = await db.trade_block.insert_one(item_doc)
    item_doc["_id"] = str(result.inserted_id)

    if input.league_id:
        await broadcast_to_room(
            f"league_{input.league_id}",
            "trade_block_changed",
            {"action": "added", "item_id": str(result.inserted_id)},
        )
    return item_doc


@router.get("/trade-block")
async def get_trade_block(
    league_id: Optional[str] = None,
    team_id: Optional[str] = None,
    owner_id: Optional[str] = None,
):
    db = _deps["db"]
    query: dict = {}
    if league_id:
        query["league_id"] = league_id
    if team_id:
        query["team_id"] = team_id
    if owner_id:
        query["owner_id"] = owner_id
    items = await db.trade_block.find(query).sort("created_at", -1).to_list(500)

    # Batch-join contracts so the frontend can surface an AAV column when cap
    # is enabled. One-shot lookup avoids N+1 reads.
    player_ids = [it["player_id"] for it in items if it.get("player_id")]
    salary_map: dict = {}
    if player_ids:
        oids = []
        for pid in player_ids:
            try:
                oids.append(ObjectId(pid))
            except Exception:
                continue
        if oids:
            cursor = db.players.find(
                {"_id": {"$in": oids}},
                {"contract": 1, "salary": 1, "cap_hit": 1},
            )
            async for p in cursor:
                contract = p.get("contract") or {}
                salary_map[str(p["_id"])] = {
                    "aav": contract.get("aav"),
                    "salary": p.get("salary"),
                    "cap_hit": p.get("cap_hit"),
                }
    for item in items:
        item["_id"] = str(item["_id"])
        if item.get("player_id"):
            info = salary_map.get(item["player_id"]) or {}
            item["aav"] = info.get("aav") or info.get("salary") or info.get("cap_hit")
    return items


@router.delete("/trade-block/{item_id}")
async def remove_from_trade_block(item_id: str, request: Request):
    db = _deps["db"]
    get_current_user = _deps["get_current_user"]
    broadcast_to_room = _deps["broadcast_to_room"]

    user = await get_current_user(request)
    item = await db.trade_block.find_one({"_id": ObjectId(item_id)})
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    if item["owner_id"] != user["_id"]:
        raise HTTPException(status_code=403, detail="Not your item")
    await db.trade_block.delete_one({"_id": ObjectId(item_id)})
    if item.get("league_id"):
        await broadcast_to_room(
            f"league_{item['league_id']}",
            "trade_block_changed",
            {"action": "removed", "item_id": item_id},
        )
    return {"message": "Removed from trade block"}


# ─── Per-team note + retention preference ──────────────────────


@router.put("/teams/{team_id}/trade-block-note")
async def set_trade_block_note(team_id: str, payload: dict, request: Request):
    """Update the team's public trade-block note (max 200 chars)."""
    db = _deps["db"]
    get_current_user = _deps["get_current_user"]
    _safe_object_id = _deps["_safe_object_id"]

    user = await get_current_user(request)
    note = (payload.get("note") or "").strip()
    if len(note) > 200:
        raise HTTPException(status_code=400, detail="Note must be 200 characters or fewer")
    team = await db.teams.find_one({"_id": _safe_object_id(team_id, "team_id")})
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    if team.get("owner_id") != user["_id"]:
        raise HTTPException(status_code=403, detail="Not your team")
    await db.teams.update_one(
        {"_id": team["_id"]},
        {"$set": {
            "trade_block_note": note,
            "trade_block_note_updated_at": datetime.now(timezone.utc),
        }},
    )
    return {"team_id": team_id, "note": note}


@router.get("/teams/{team_id}/trade-block-note")
async def get_trade_block_note(team_id: str):
    db = _deps["db"]
    _safe_object_id = _deps["_safe_object_id"]
    team = await db.teams.find_one({"_id": _safe_object_id(team_id, "team_id")})
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    return {
        "team_id": team_id,
        "note": team.get("trade_block_note") or "",
        "updated_at": team.get("trade_block_note_updated_at"),
    }


@router.put("/teams/{team_id}/trade-block-preference")
async def set_trade_block_preference(
    team_id: str, payload: SalaryRetentionPrefUpdate, request: Request,
):
    db = _deps["db"]
    get_current_user = _deps["get_current_user"]
    _safe_object_id = _deps["_safe_object_id"]

    user = await get_current_user(request)
    if payload.preference not in ("willing_to_retain", "no_preference", "seeking_retention"):
        raise HTTPException(status_code=400, detail="Invalid preference")
    team = await db.teams.find_one({"_id": _safe_object_id(team_id, "team_id")})
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    if team.get("owner_id") != user["_id"]:
        raise HTTPException(status_code=403, detail="Not your team")
    await db.teams.update_one(
        {"_id": team["_id"]},
        {"$set": {"salary_retention_pref": payload.preference}},
    )
    # Cascade preference to existing trade-block items so the homepage widget
    # immediately reflects the new value without a stats refresh.
    await db.trade_block.update_many(
        {"owner_id": user["_id"], "team_id": team_id},
        {"$set": {"salary_retention_pref": payload.preference}},
    )
    return {"team_id": team_id, "preference": payload.preference}


# ─── League-level summary + stats refresh ──────────────────────


@router.get("/leagues/{league_id}/trade-block-summary")
async def trade_block_summary(league_id: str, limit: int = 10):
    """Top-valued trade-block items for a league. Used by the league homepage widget."""
    db = _deps["db"]
    items = await db.trade_block.find({"league_id": league_id}).to_list(500)

    # Backfill team_name + retention pref for legacy rows that pre-date the
    # team_id field.
    needs_fill = [
        it for it in items
        if not it.get("team_name") or not it.get("salary_retention_pref")
    ]
    if needs_fill:
        owner_ids = list({it["owner_id"] for it in needs_fill if it.get("owner_id")})
        teams_in_league = await db.teams.find({
            "league_id": league_id, "owner_id": {"$in": owner_ids},
        }).to_list(100)
        by_owner = {t["owner_id"]: t for t in teams_in_league}
        for it in needs_fill:
            t = by_owner.get(it.get("owner_id"))
            if t:
                if not it.get("team_name"):
                    it["team_name"] = t.get("name")
                if not it.get("salary_retention_pref"):
                    it["salary_retention_pref"] = t.get(
                        "salary_retention_pref", "no_preference",
                    )
                if not it.get("team_id"):
                    it["team_id"] = str(t["_id"])

    items.sort(
        key=lambda x: (
            float(x.get("fantasy_points") or 0),
            float(x.get("recent_form_ppw") or 0),
        ),
        reverse=True,
    )
    out = []
    for it in items[: max(1, min(limit, 50))]:
        it["_id"] = str(it["_id"])
        out.append(it)
    return {"league_id": league_id, "items": out, "count": len(items)}


@router.post("/leagues/{league_id}/trade-block/refresh-stats")
async def refresh_trade_block_stats(league_id: str, request: Request):
    """Re-pull current player season_stats + recent-form so the homepage widget
    stays in sync as the season advances. Idempotent. Commissioner-only.
    """
    db = _deps["db"]
    get_current_user = _deps["get_current_user"]
    _safe_object_id = _deps["_safe_object_id"]

    user = await get_current_user(request)
    league = await db.leagues.find_one({"_id": _safe_object_id(league_id, "league_id")})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    is_comm = league["commissioner_id"] == user["_id"]
    co_comms = league.get("co_commissioners", []) or []
    if not (is_comm or user["_id"] in co_comms):
        raise HTTPException(
            status_code=403,
            detail="Only commissioners can refresh trade-block stats",
        )

    items = await db.trade_block.find(
        {"league_id": league_id, "item_type": "player"},
    ).to_list(500)
    updated = 0
    for it in items:
        pid = it.get("player_id")
        if not pid:
            continue
        try:
            player = await db.players.find_one({"_id": ObjectId(pid)})
        except Exception:
            continue
        if not player:
            continue
        season = player.get("season_stats") or {}
        gp = int(season.get("games_played") or player.get("games_played") or 0)
        fpts = float(player.get("fantasy_points") or season.get("fantasy_points") or 0)
        patch = {
            "goals": int(season.get("goals") or player.get("goals") or 0),
            "assists": int(season.get("assists") or player.get("assists") or 0),
            "points": int(season.get("points") or player.get("points") or 0),
            "plus_minus": int(season.get("plus_minus") or player.get("plus_minus") or 0),
            "games_played": gp,
            "fantasy_points": round(fpts, 1),
            "fantasy_ppg": round(fpts / gp, 2) if gp else 0.0,
        }
        if it.get("team_id"):
            recent = (
                await db.week_summaries.find({
                    "league_id": league_id, "team_id": it["team_id"],
                })
                .sort("week", -1)
                .limit(3)
                .to_list(3)
            )
            if recent:
                patch["recent_form_ppw"] = round(
                    sum((r.get("points_for", 0.0) or 0.0) for r in recent) / len(recent),
                    1,
                )
        await db.trade_block.update_one({"_id": it["_id"]}, {"$set": patch})
        updated += 1
    return {"league_id": league_id, "items_refreshed": updated}
