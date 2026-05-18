"""Draft router — full draft engine.

Extracted from server.py during iter 98 modularization. Covers the entire
draft lifecycle (snake + auction): create, get, board, eligible-players,
start, pick, pause, chat, config, plus the auction sub-routes (nominate,
bid, resolve, state, init-budgets) and the picks endpoint (lottery /
protections).

Wiring via the standard `setup(deps)` pattern. All collection access goes
through `_db()` so the same module can be tested in isolation against a
throwaway database.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from draft_engine import (
    CreateDraftRequest, MakeDraftPickRequest, DraftChatRequest,
    UpdateDraftConfigRequest, get_team_for_pick, get_draft_order, build_draft_board,
)


router = APIRouter()
_deps: dict = {}
logger = logging.getLogger(__name__)


def setup(deps: dict) -> None:
    _deps.update(deps)


def _db(): return _deps["db"]
def _sio(): return _deps.get("sio")
async def _get_user(request): return await _deps["get_current_user"](request)
async def _log_activity(*a, **kw): return await _deps["log_activity"](*a, **kw)
async def _broadcast(room, event, payload):
    return await _deps["broadcast_to_room"](room, event, payload)
def _calculate_fantasy_points(*a, **kw): return _deps["calculate_fantasy_points"](*a, **kw)


@router.get("/drafts/{league_id}/picks")
async def get_draft_picks(league_id: str, year: Optional[int] = None):
    db = _deps["db"]
    query = {"league_id": league_id}
    if year:
        query["year"] = int(year)
    picks = await db.draft_picks.find(query).sort([("year", 1), ("round", 1)]).to_list(1000)

    # Build a lookup of pending pick-upgrade clauses (status=executed,
    # applied_at/failed_at not yet set) so the DraftBoard can render a
    # "Protected: top-N" / "Conditional upgrade" badge before the lottery
    # resolves.
    trades = await db.trades.find({
        "league_id": league_id,
        "status": "executed",
        "pick_upgrades": {"$exists": True, "$ne": []},
    }, {"_id": 1, "pick_upgrades": 1}).to_list(500)
    pending: dict = {}
    for t in trades:
        for u in (t.get("pick_upgrades") or []):
            if u.get("applied_at") or u.get("failed_at"):
                continue
            pid = u.get("pick_id")
            if not pid:
                continue
            cond = u.get("condition") or {}
            pending.setdefault(pid, []).append({
                "trade_id": str(t["_id"]),
                "new_round": u.get("new_round"),
                "new_year": u.get("new_year"),
                "subject_type": cond.get("subject_type"),
                "metric": cond.get("metric"),
                "operator": cond.get("operator"),
                "threshold": cond.get("threshold"),
                "description": cond.get("description") or u.get("description"),
            })

    for p in picks:
        p["_id"] = str(p["_id"])
        p["pending_protections"] = pending.get(p["_id"], [])
    return {"league_id": league_id, "year": year, "picks": picks}



@router.post("/drafts")
async def create_draft(input: CreateDraftRequest, request: Request):
    user = await _get_user(request)

    league = await _db().leagues.find_one({"_id": ObjectId(input.league_id)})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")

    if league["commissioner_id"] != user["_id"]:
        raise HTTPException(status_code=403, detail="Only commissioner can create drafts")

    # Get league teams for draft order
    teams = await _db().teams.find({"league_id": input.league_id}).to_list(100)
    team_abbrs = [t["name"][:4].upper() for t in teams]
    team_map = {t["name"][:4].upper(): {"id": str(t["_id"]), "name": t["name"], "owner_id": t["owner_id"]} for t in teams}

    scheduled = None
    if input.scheduled_time:
        scheduled = input.scheduled_time

    draft_doc = {
        "league_id": input.league_id,
        "league_name": league["name"],
        "draft_type": input.draft_type,
        "scheduled_time": scheduled,
        "total_rounds": input.total_rounds,
        "time_per_pick": input.time_per_pick,
        "snake_draft": input.snake_draft,
        "player_criteria": input.player_criteria,
        "missed_pick_action": input.missed_pick_action,
        "current_pick": 1,
        "status": "scheduled",
        "draft_started": False,
        "early_start": False,
        "timer_paused": False,
        "team_abbrs": team_abbrs,
        "team_map": team_map,
        "picks": [],
        "chat_messages": [],
        "created_by": user["_id"],
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    result = await _db().drafts.insert_one(draft_doc)
    draft_doc["_id"] = str(result.inserted_id)
    draft_doc.pop("team_map", None)
    return draft_doc

@router.get("/drafts")
async def get_drafts(league_id: Optional[str] = None, request: Request = None):
    query = {}
    if league_id:
        query["league_id"] = league_id
    drafts = await _db().drafts.find(query, {"team_map": 0}).sort("created_at", -1).to_list(100)
    for d in drafts:
        d["_id"] = str(d["_id"])
    return drafts

@router.get("/drafts/{draft_id}")
async def get_draft(draft_id: str):
    draft = await _db().drafts.find_one({"_id": ObjectId(draft_id)})
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    draft["_id"] = str(draft["_id"])
    return draft

@router.get("/drafts/{draft_id}/board")
async def get_draft_board(draft_id: str):
    draft = await _db().drafts.find_one({"_id": ObjectId(draft_id)})
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")

    board = build_draft_board(
        draft["team_abbrs"],
        draft["total_rounds"],
        draft["snake_draft"],
        draft["picks"]
    )
    return {
        "board": board,
        "current_pick": draft["current_pick"],
        "status": draft["status"],
        "team_abbrs": draft["team_abbrs"],
        "total_rounds": draft["total_rounds"],
        "snake_draft": draft["snake_draft"],
        "on_the_clock": get_team_for_pick(draft["team_abbrs"], draft["current_pick"], draft["snake_draft"]) if draft["team_abbrs"] else None
    }

@router.get("/drafts/{draft_id}/eligible-players")
async def get_draft_eligible_players(
    draft_id: str,
    search: Optional[str] = None,
    position: Optional[str] = None,
    page: int = 1,
    limit: int = 50
):
    draft = await _db().drafts.find_one({"_id": ObjectId(draft_id)})
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")

    # Get already-drafted player IDs
    drafted_ids = [p["player_id"] for p in draft.get("picks", []) if p.get("player_id")]

    query = {}
    if drafted_ids:
        query["_id"] = {"$nin": [ObjectId(pid) for pid in drafted_ids]}

    if search:
        query["$or"] = [
            {"name": {"$regex": search, "$options": "i"}},
            {"team": {"$regex": search, "$options": "i"}}
        ]
    if position and position != "all":
        query["position"] = position

    skip = (page - 1) * limit
    players = await _db().players.find(query).sort("points", -1).skip(skip).limit(limit).to_list(limit)
    total = await _db().players.count_documents(query)

    result = []
    for i, p in enumerate(players):
        result.append({
            "id": str(p["_id"]),
            "name": p["name"],
            "position": p["position"],
            "nhlTeam": p.get("team", ""),
            "team_name": p.get("team_name", ""),
            "age": 0,
            "league": "NHL",
            "gp": p.get("games_played", 0),
            "g": p.get("goals", 0),
            "a": p.get("assists", 0),
            "pts": p.get("points", 0),
            "plus_minus": p.get("plus_minus", 0),
            "ranking": skip + i + 1,
            "drafted": False
        })

    return {"players": result, "total": total, "page": page, "pages": (total + limit - 1) // limit}

@router.post("/drafts/{draft_id}/start")
async def start_draft(draft_id: str, request: Request, early_start: bool = False):
    user = await _get_user(request)

    draft = await _db().drafts.find_one({"_id": ObjectId(draft_id)})
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")

    league = await _db().leagues.find_one({"_id": ObjectId(draft["league_id"])})
    if league["commissioner_id"] != user["_id"]:
        raise HTTPException(status_code=403, detail="Only commissioner can start draft")

    if draft["status"] == "active":
        raise HTTPException(status_code=400, detail="Draft already active")

    update = {
        "$set": {
            "status": "active",
            "draft_started": True,
            "early_start": early_start,
            "current_pick": 1,
            "started_at": datetime.now(timezone.utc).isoformat()
        }
    }
    await _db().drafts.update_one({"_id": ObjectId(draft_id)}, update)

    # Broadcast draft start
    await _broadcast(f"draft_{draft_id}", "draft_started", {
        "draft_id": draft_id,
        "early_start": early_start,
        "team_abbrs": draft["team_abbrs"],
        "on_the_clock": draft["team_abbrs"][0] if draft["team_abbrs"] else None
    })

    # Add system chat message
    system_msg = {
        "id": f"sys-{datetime.now(timezone.utc).timestamp()}",
        "type": "pick",
        "sender": "System",
        "text": f"Draft has started! {'(No Clock)' if early_start else 'Timer is running.'}",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    await _db().drafts.update_one({"_id": ObjectId(draft_id)}, {"$push": {"chat_messages": system_msg}})
    await _broadcast(f"draft_{draft_id}", "draft_chat", system_msg)

    return {"message": "Draft started", "early_start": early_start}

@router.post("/drafts/{draft_id}/pick")
async def make_draft_pick(draft_id: str, input: MakeDraftPickRequest, request: Request):
    user = await _get_user(request)

    draft = await _db().drafts.find_one({"_id": ObjectId(draft_id)})
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")

    if draft["status"] != "active":
        raise HTTPException(status_code=400, detail="Draft is not active")

    # Validate it's the user's turn
    team = await _db().teams.find_one({"league_id": draft["league_id"], "owner_id": user["_id"]})
    if not team:
        raise HTTPException(status_code=403, detail="You don't have a team in this league")

    team_abbr = team["name"][:4].upper()
    on_clock = get_team_for_pick(draft["team_abbrs"], draft["current_pick"], draft["snake_draft"])

    # Commissioner can pick for any team, or it must be the user's turn
    league = await _db().leagues.find_one({"_id": ObjectId(draft["league_id"])})
    is_commissioner = league["commissioner_id"] == user["_id"]

    if team_abbr != on_clock and not is_commissioner:
        raise HTTPException(status_code=403, detail=f"Not your turn. {on_clock} is on the clock.")

    # Validate player exists and not already drafted
    player = await _db().players.find_one({"_id": ObjectId(input.player_id)})
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")

    already_picked = any(p.get("player_id") == input.player_id for p in draft.get("picks", []))
    if already_picked:
        raise HTTPException(status_code=400, detail="Player already drafted")

    total_teams = len(draft["team_abbrs"])
    current_pick = draft["current_pick"]
    round_num = ((current_pick - 1) // total_teams) + 1
    pick_in_round = ((current_pick - 1) % total_teams) + 1

    pick_doc = {
        "round": round_num,
        "pick_in_round": pick_in_round,
        "overall": current_pick,
        "team": on_clock,
        "player_id": str(player["_id"]),
        "player": {
            "name": player["name"],
            "position": player["position"],
            "nhlTeam": player.get("team", ""),
            "pts": player.get("points", 0)
        },
        "picked_by": user["_id"],
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

    next_pick = current_pick + 1
    total_picks = draft["total_rounds"] * total_teams
    new_status = "completed" if next_pick > total_picks else "active"

    await _db().drafts.update_one(
        {"_id": ObjectId(draft_id)},
        {
            "$push": {"picks": pick_doc},
            "$set": {"current_pick": next_pick, "status": new_status}
        }
    )

    # Broadcast pick
    await _broadcast(f"draft_{draft_id}", "draft_pick", {
        **pick_doc,
        "next_pick": next_pick,
        "on_the_clock": get_team_for_pick(draft["team_abbrs"], next_pick, draft["snake_draft"]) if new_status == "active" else None,
        "draft_complete": new_status == "completed"
    })

    # System chat for the pick
    pick_msg = {
        "id": f"pick-{current_pick}",
        "type": "pick",
        "sender": "System",
        "text": f"Pick #{current_pick} (Rd {round_num}, Pick {pick_in_round}): {on_clock} selects {player['name']} ({player['position']})",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    await _db().drafts.update_one({"_id": ObjectId(draft_id)}, {"$push": {"chat_messages": pick_msg}})
    await _broadcast(f"draft_{draft_id}", "draft_chat", pick_msg)

    if new_status == "completed":
        complete_msg = {
            "id": f"sys-complete",
            "type": "pick",
            "sender": "System",
            "text": "Draft is complete! All picks have been made.",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        await _db().drafts.update_one({"_id": ObjectId(draft_id)}, {"$push": {"chat_messages": complete_msg}})
        await _broadcast(f"draft_{draft_id}", "draft_chat", complete_msg)
        await _broadcast(f"draft_{draft_id}", "draft_completed", {"draft_id": draft_id})

    return pick_doc

@router.post("/drafts/{draft_id}/pause")
async def pause_draft(draft_id: str, request: Request):
    user = await _get_user(request)
    draft = await _db().drafts.find_one({"_id": ObjectId(draft_id)})
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")

    league = await _db().leagues.find_one({"_id": ObjectId(draft["league_id"])})
    if league["commissioner_id"] != user["_id"]:
        raise HTTPException(status_code=403, detail="Only commissioner can pause draft")

    paused = not draft.get("timer_paused", False)
    await _db().drafts.update_one({"_id": ObjectId(draft_id)}, {"$set": {"timer_paused": paused}})

    await _broadcast(f"draft_{draft_id}", "draft_timer_toggle", {"paused": paused})
    return {"paused": paused}

@router.post("/drafts/{draft_id}/chat")
async def send_draft_chat(draft_id: str, input: DraftChatRequest, request: Request):
    user = await _get_user(request)

    team = await _db().teams.find_one({"league_id": (await _db().drafts.find_one({"_id": ObjectId(draft_id)}))["league_id"], "owner_id": user["_id"]})
    sender = team["name"] if team else user["name"]

    msg = {
        "id": f"chat-{datetime.now(timezone.utc).timestamp()}",
        "type": "chat",
        "sender": sender,
        "text": input.text,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

    await _db().drafts.update_one({"_id": ObjectId(draft_id)}, {"$push": {"chat_messages": msg}})
    await _broadcast(f"draft_{draft_id}", "draft_chat", msg)
    return msg

@router.get("/drafts/{draft_id}/chat")
async def get_draft_chat(draft_id: str):
    draft = await _db().drafts.find_one({"_id": ObjectId(draft_id)}, {"chat_messages": 1})
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    return draft.get("chat_messages", [])

@router.put("/drafts/{draft_id}/config")
async def update_draft_config(draft_id: str, input: UpdateDraftConfigRequest, request: Request):
    user = await _get_user(request)
    draft = await _db().drafts.find_one({"_id": ObjectId(draft_id)})
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")

    league = await _db().leagues.find_one({"_id": ObjectId(draft["league_id"])})
    if league["commissioner_id"] != user["_id"]:
        raise HTTPException(status_code=403, detail="Only commissioner can update draft config")

    updates = {}
    if input.time_per_pick is not None:
        updates["time_per_pick"] = input.time_per_pick
    if input.total_rounds is not None:
        updates["total_rounds"] = input.total_rounds
    if input.snake_draft is not None:
        updates["snake_draft"] = input.snake_draft
    if input.player_criteria is not None:
        updates["player_criteria"] = input.player_criteria
    if input.missed_pick_action is not None:
        updates["missed_pick_action"] = input.missed_pick_action

    if updates:
        await _db().drafts.update_one({"_id": ObjectId(draft_id)}, {"$set": updates})
        await _broadcast(f"draft_{draft_id}", "draft_config_updated", updates)

    return {"updated": list(updates.keys())}

# ═══════════════════════════════════════════════════════════════
# Notifications Engine
# ═══════════════════════════════════════════════════════════════

class NotificationType(str, Enum):
    TRADE_PROPOSED = "trade_proposed"
    TRADE_ACCEPTED = "trade_accepted"
    TRADE_REJECTED = "trade_rejected"
    TRADE_VETOED = "trade_vetoed"
    WAIVER_WON = "waiver_won"
    WAIVER_LOST = "waiver_lost"
    WAIVERS_PROCESSED = "waivers_processed"
    DRAFT_STARTED = "draft_started"
    DRAFT_PICK = "draft_pick"
    DRAFT_YOUR_TURN = "draft_your_turn"
    DRAFT_COMPLETED = "draft_completed"
    WEEK_SIMULATED = "week_simulated"
    TEAM_JOINED = "team_joined"


async def create_notification(user_id: str, notif_type: str, title: str, message: str, league_id: str = None, link: str = None):
    """Create a notification and broadcast it via WebSocket + Expo push."""
    doc = {
        "user_id": user_id,
        "type": notif_type,
        "title": title,
        "message": message,
        "league_id": league_id,
        "link": link,
        "read": False,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    result = await _db().notifications.insert_one(doc)
    doc["_id"] = str(result.inserted_id)
    # Broadcast to user's personal room (socket.io)
    sio = _sio()
    if sio is not None:
        try:
            await sio.emit("notification", doc, room=f"user_{user_id}")
        except Exception as e:
            logger.debug(f"sio notify skipped: {e}")
    # Fire an Expo push in parallel (non-blocking best-effort)
    try:
        from routes.push import send_push
        asyncio.create_task(send_push(
            [user_id],
            title=title,
            body=message,
            data={"type": notif_type, "league_id": league_id, "link": link, "notification_id": doc["_id"]},
        ))
    except Exception as e:
        logger.debug(f"push notify skipped: {e}")
    return doc


async def notify_league(league_id: str, notif_type: str, title: str, message: str, link: str = None, exclude_user: str = None):
    """Send notification to all team owners in a league."""
    teams = await _db().teams.find({"league_id": league_id}, {"owner_id": 1}).to_list(100)
    for team in teams:
        if team["owner_id"] != exclude_user:
            await create_notification(team["owner_id"], notif_type, title, message, league_id, link)


# Notifications routes moved to routes/notifications.py (iter 85).





# ═══════════════════════════════════════════════════════════════
# Auction Draft Engine
# ═══════════════════════════════════════════════════════════════

class AuctionNominateRequest(BaseModel):
    player_id: str
    opening_bid: float = Field(ge=1)


class AuctionBidRequest(BaseModel):
    amount: float = Field(ge=1)


@router.post("/drafts/{draft_id}/auction/nominate")
async def auction_nominate(draft_id: str, input: AuctionNominateRequest, request: Request):
    """Nominate a player for auction bidding."""
    user = await _get_user(request)
    draft = await _db().drafts.find_one({"_id": ObjectId(draft_id)})
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    if draft["status"] != "active":
        raise HTTPException(status_code=400, detail="Draft is not active")
    if draft.get("draft_type") != "auction":
        raise HTTPException(status_code=400, detail="This is not an auction draft")

    # Check no active auction
    if draft.get("active_auction"):
        raise HTTPException(status_code=400, detail="An auction is already in progress")

    team = await _db().teams.find_one({"league_id": draft["league_id"], "owner_id": user["_id"]})
    if not team:
        raise HTTPException(status_code=403, detail="No team in this league")

    # Check budget
    team_budget = draft.get("auction_budgets", {}).get(str(team["_id"]), draft.get("salary_cap", 200))
    if input.opening_bid > team_budget:
        raise HTTPException(status_code=400, detail=f"Insufficient budget (${team_budget} remaining)")

    player = await _db().players.find_one({"_id": ObjectId(input.player_id)})
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")

    # Check player not already drafted
    drafted_ids = [p.get("player_id") for p in draft.get("picks", [])]
    if input.player_id in drafted_ids:
        raise HTTPException(status_code=400, detail="Player already drafted")

    auction = {
        "player_id": input.player_id,
        "player_name": player["name"],
        "player_position": player["position"],
        "player_team": player.get("team", ""),
        "nominator_team_id": str(team["_id"]),
        "nominator_team_name": team["name"],
        "current_bid": input.opening_bid,
        "current_bidder_team_id": str(team["_id"]),
        "current_bidder_team_name": team["name"],
        "bid_history": [{
            "team_id": str(team["_id"]),
            "team_name": team["name"],
            "amount": input.opening_bid,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }],
        "timer_seconds": 15,
        "started_at": datetime.now(timezone.utc).isoformat()
    }

    await _db().drafts.update_one(
        {"_id": ObjectId(draft_id)},
        {"$set": {"active_auction": auction}}
    )

    await _broadcast(f"draft_{draft_id}", "auction_nomination", auction)

    # System chat
    msg = {
        "id": f"auction-{datetime.now(timezone.utc).timestamp()}",
        "type": "pick",
        "sender": "System",
        "text": f"{team['name']} nominates {player['name']} ({player['position']}) - Opening bid: ${input.opening_bid}",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    await _db().drafts.update_one({"_id": ObjectId(draft_id)}, {"$push": {"chat_messages": msg}})
    await _broadcast(f"draft_{draft_id}", "draft_chat", msg)

    return auction


@router.post("/drafts/{draft_id}/auction/bid")
async def auction_bid(draft_id: str, input: AuctionBidRequest, request: Request):
    """Place a bid on the current auction."""
    user = await _get_user(request)
    draft = await _db().drafts.find_one({"_id": ObjectId(draft_id)})
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")

    auction = draft.get("active_auction")
    if not auction:
        raise HTTPException(status_code=400, detail="No active auction")

    team = await _db().teams.find_one({"league_id": draft["league_id"], "owner_id": user["_id"]})
    if not team:
        raise HTTPException(status_code=403, detail="No team in this league")

    if input.amount <= auction["current_bid"]:
        raise HTTPException(status_code=400, detail=f"Bid must be higher than ${auction['current_bid']}")

    # Check budget
    team_id_str = str(team["_id"])
    team_budget = draft.get("auction_budgets", {}).get(team_id_str, draft.get("salary_cap", 200))
    if input.amount > team_budget:
        raise HTTPException(status_code=400, detail=f"Insufficient budget (${team_budget} remaining)")

    bid_entry = {
        "team_id": team_id_str,
        "team_name": team["name"],
        "amount": input.amount,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

    await _db().drafts.update_one(
        {"_id": ObjectId(draft_id)},
        {
            "$set": {
                "active_auction.current_bid": input.amount,
                "active_auction.current_bidder_team_id": team_id_str,
                "active_auction.current_bidder_team_name": team["name"],
                "active_auction.timer_seconds": 15,
            },
            "$push": {"active_auction.bid_history": bid_entry}
        }
    )

    bid_data = {
        "team_id": team_id_str,
        "team_name": team["name"],
        "amount": input.amount,
        "player_name": auction["player_name"],
        "timer_reset": 15
    }
    await _broadcast(f"draft_{draft_id}", "auction_bid", bid_data)

    return bid_data


@router.post("/drafts/{draft_id}/auction/resolve")
async def auction_resolve(draft_id: str, request: Request):
    """Resolve current auction - timer expired, winner gets player."""
    user = await _get_user(request)
    draft = await _db().drafts.find_one({"_id": ObjectId(draft_id)})
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")

    league = await _db().leagues.find_one({"_id": ObjectId(draft["league_id"])})
    if league["commissioner_id"] != user["_id"]:
        raise HTTPException(status_code=403, detail="Only commissioner can resolve auctions")

    auction = draft.get("active_auction")
    if not auction:
        raise HTTPException(status_code=400, detail="No active auction")

    winner_team_id = auction["current_bidder_team_id"]
    winning_bid = auction["current_bid"]
    player_id = auction["player_id"]

    # Create the pick
    pick_doc = {
        "round": 0,
        "pick_in_round": len(draft.get("picks", [])) + 1,
        "overall": len(draft.get("picks", [])) + 1,
        "team": auction["current_bidder_team_name"],
        "player_id": player_id,
        "player": {
            "name": auction["player_name"],
            "position": auction["player_position"],
            "nhlTeam": auction["player_team"],
        },
        "auction_price": winning_bid,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

    # Deduct budget
    budget_key = f"auction_budgets.{winner_team_id}"
    current_budget = draft.get("auction_budgets", {}).get(winner_team_id, draft.get("salary_cap", 200))
    new_budget = current_budget - winning_bid

    await _db().drafts.update_one(
        {"_id": ObjectId(draft_id)},
        {
            "$push": {"picks": pick_doc},
            "$set": {
                "active_auction": None,
                budget_key: new_budget
            }
        }
    )

    result = {
        **pick_doc,
        "winning_bid": winning_bid,
        "winner_team": auction["current_bidder_team_name"],
        "remaining_budget": new_budget
    }
    await _broadcast(f"draft_{draft_id}", "auction_resolved", result)

    # System chat
    msg = {
        "id": f"resolved-{datetime.now(timezone.utc).timestamp()}",
        "type": "pick",
        "sender": "System",
        "text": f"SOLD! {auction['player_name']} goes to {auction['current_bidder_team_name']} for ${winning_bid}",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    await _db().drafts.update_one({"_id": ObjectId(draft_id)}, {"$push": {"chat_messages": msg}})
    await _broadcast(f"draft_{draft_id}", "draft_chat", msg)

    # Notify all league members
    await notify_league(
        draft["league_id"],
        NotificationType.DRAFT_PICK.value,
        "Auction Pick",
        f"{auction['current_bidder_team_name']} wins {auction['player_name']} for ${winning_bid}",
        link=f"/draft-room/{draft_id}"
    )

    return result


@router.get("/drafts/{draft_id}/auction/state")
async def get_auction_state(draft_id: str):
    """Get current auction state including active auction and budgets."""
    draft = await _db().drafts.find_one({"_id": ObjectId(draft_id)})
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")

    teams = await _db().teams.find({"league_id": draft["league_id"]}).to_list(100)
    budgets = []
    for t in teams:
        tid = str(t["_id"])
        budget = draft.get("auction_budgets", {}).get(tid, draft.get("salary_cap", 200))
        picks_count = sum(1 for p in draft.get("picks", []) if p.get("team") == t["name"])
        budgets.append({
            "team_id": tid,
            "team_name": t["name"],
            "budget_remaining": budget,
            "players_won": picks_count
        })

    return {
        "active_auction": draft.get("active_auction"),
        "budgets": budgets,
        "total_picks": len(draft.get("picks", [])),
        "draft_type": draft.get("draft_type"),
        "salary_cap": draft.get("salary_cap", 200)
    }


@router.post("/drafts/{draft_id}/auction/init-budgets")
async def init_auction_budgets(draft_id: str, request: Request):
    """Initialize auction budgets for all teams (commissioner only)."""
    user = await _get_user(request)
    draft = await _db().drafts.find_one({"_id": ObjectId(draft_id)})
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")

    league = await _db().leagues.find_one({"_id": ObjectId(draft["league_id"])})
    if league["commissioner_id"] != user["_id"]:
        raise HTTPException(status_code=403, detail="Only commissioner")

    cap = league.get("salary_cap") or 200
    teams = await _db().teams.find({"league_id": draft["league_id"]}).to_list(100)
    budgets = {str(t["_id"]): cap for t in teams}

    await _db().drafts.update_one(
        {"_id": ObjectId(draft_id)},
        {"$set": {"auction_budgets": budgets, "salary_cap": cap}}
    )

    return {"message": f"Initialized {len(budgets)} budgets at ${cap}", "budgets": budgets}

