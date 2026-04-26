"""Trade routes — proposals, accept/reject/withdraw, multi-party, party-respond,
execute, evaluate-conditions, vote.

Helpers `_execute_trade`, `_evaluate_conditions`, `_metric_value_for_player`,
and `_execute_multi_party_trade` remain in server.py because the awards and
matchups modules also depend on them. The trade-route module accesses them
via the standard `_deps` dict.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Request

from trade_waiver_engine import (
    TradeProposalCreate,
    TradeVote,
    MultiPartyTradeProposalCreate,
    TradePartyResponse,
)

router = APIRouter()
_deps: dict = {}


def setup(deps: dict) -> None:
    _deps.update(deps)


def _db(): return _deps["db"]
def _logger(): return _deps["logger"]
async def _get_user(request): return await _deps["get_current_user"](request)
async def _broadcast(*a, **kw): return await _deps["broadcast_to_room"](*a, **kw)
async def _create_notification(*a, **kw): return await _deps["create_notification"](*a, **kw)
async def _execute_trade(trade): return await _deps["_execute_trade"](trade)
async def _evaluate_conditions(trade): return await _deps["_evaluate_conditions"](trade)


# Notification type literals (kept as strings to avoid importing the server enum)
NT_TRADE_PROPOSED = "trade_proposed"
NT_TRADE_ACCEPTED = "trade_accepted"


# ─── Trade Proposals (legacy 2-party) ────────────────────────────
@router.post("/trades")
async def create_trade_proposal(input: TradeProposalCreate, request: Request):
    db = _db()
    user = await _get_user(request)

    league = await db.leagues.find_one({"_id": ObjectId(input.league_id)})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")

    proposer_team = await db.teams.find_one({"league_id": input.league_id, "owner_id": user["_id"]})
    if not proposer_team:
        raise HTTPException(status_code=403, detail="You don't have a team in this league")

    target_team = await db.teams.find_one({"_id": ObjectId(input.target_team_id)})
    if not target_team:
        raise HTTPException(status_code=404, detail="Target team not found")

    offered_details = []
    for asset in input.assets_offered:
        detail = asset.dict()
        if asset.player_id:
            player = await db.players.find_one({"_id": ObjectId(asset.player_id)})
            if player:
                detail["player_name"] = player["name"]
                detail["position"] = player["position"]
                detail["nhl_team"] = player.get("team", "")
                detail["points"] = player.get("points", 0)
                detail["goals"] = player.get("goals", 0)
                detail["assists"] = player.get("assists", 0)
        offered_details.append(detail)

    requested_details = []
    for asset in input.assets_requested:
        detail = asset.dict()
        if asset.player_id:
            player = await db.players.find_one({"_id": ObjectId(asset.player_id)})
            if player:
                detail["player_name"] = player["name"]
                detail["position"] = player["position"]
                detail["nhl_team"] = player.get("team", "")
                detail["points"] = player.get("points", 0)
                detail["goals"] = player.get("goals", 0)
                detail["assists"] = player.get("assists", 0)
        requested_details.append(detail)

    review_period_hours = 72
    has_conditions = bool(getattr(input, "conditions", None))
    trade_doc = {
        "league_id": input.league_id,
        "proposer_team_id": str(proposer_team["_id"]),
        "proposer_team_name": proposer_team["name"],
        "proposer_id": user["_id"],
        "target_team_id": input.target_team_id,
        "target_team_name": target_team["name"],
        "target_owner_id": target_team["owner_id"],
        "assets_offered": offered_details,
        "assets_requested": requested_details,
        "conditions": [c.dict() if hasattr(c, "dict") else c for c in (input.conditions or [])],
        "conditional": has_conditions,
        "message": input.message,
        "status": "pending",
        "votes": {"approve": 0, "veto": 0, "voters": []},
        "submitted_at": datetime.now(timezone.utc).isoformat(),
        "processes_at": (datetime.now(timezone.utc) + timedelta(hours=review_period_hours)).isoformat(),
        "responded_at": None,
        "processed_at": None,
    }

    result = await db.trades.insert_one(trade_doc)
    trade_doc["_id"] = str(result.inserted_id)

    await _broadcast(f"league_{input.league_id}", "trade_proposed", {
        "trade_id": str(result.inserted_id),
        "proposer": proposer_team["name"],
        "target": target_team["name"],
    })

    await _create_notification(
        target_team["owner_id"],
        NT_TRADE_PROPOSED,
        "New Trade Proposal",
        f"{proposer_team['name']} wants to trade with you",
        input.league_id,
        "/transactions",
    )

    return trade_doc


@router.get("/trades")
async def get_trades(
    league_id: Optional[str] = None,
    status: Optional[str] = None,
    my_trades: bool = False,
    request: Request = None,
):
    db = _db()
    query: dict = {}
    if league_id:
        query["league_id"] = league_id
    if status:
        query["status"] = status

    if my_trades:
        try:
            user = await _get_user(request)
            query["$or"] = [
                {"proposer_id": user["_id"]},
                {"target_owner_id": user["_id"]},
            ]
        except Exception:
            pass

    trades = await db.trades.find(query).sort("submitted_at", -1).to_list(200)
    for t in trades:
        t["_id"] = str(t["_id"])
    return trades


@router.get("/trades/{trade_id}")
async def get_trade(trade_id: str):
    db = _db()
    trade = await db.trades.find_one({"_id": ObjectId(trade_id)})
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")
    trade["_id"] = str(trade["_id"])
    return trade


@router.post("/trades/{trade_id}/accept")
async def accept_trade(trade_id: str, request: Request):
    db = _db()
    logger = _logger()
    user = await _get_user(request)
    trade = await db.trades.find_one({"_id": ObjectId(trade_id)})
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")
    if trade["target_owner_id"] != user["_id"]:
        raise HTTPException(status_code=403, detail="Only the target team can accept")
    if trade["status"] != "pending":
        raise HTTPException(status_code=400, detail="Trade is not pending")

    await db.trades.update_one(
        {"_id": ObjectId(trade_id)},
        {"$set": {"status": "accepted", "responded_at": datetime.now(timezone.utc).isoformat()}},
    )
    trade = await db.trades.find_one({"_id": ObjectId(trade_id)})

    executed = None
    if not trade.get("conditions"):
        try:
            executed = await _execute_trade(trade)
        except Exception as e:
            logger.exception("Trade auto-execute failed: %s", e)

    await _broadcast(f"league_{trade['league_id']}", "trade_accepted", {
        "trade_id": trade_id,
        "proposer": trade["proposer_team_name"],
        "target": trade["target_team_name"],
    })

    await _create_notification(
        trade["proposer_id"],
        NT_TRADE_ACCEPTED,
        "Trade Accepted!",
        f"{trade['target_team_name']} accepted your trade proposal",
        trade["league_id"],
        "/transactions",
    )

    return {"message": "Trade accepted", "status": "accepted", "executed": bool(executed and executed.get("executed"))}


@router.post("/trades/{trade_id}/reject")
async def reject_trade(trade_id: str, request: Request):
    db = _db()
    user = await _get_user(request)
    trade = await db.trades.find_one({"_id": ObjectId(trade_id)})
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")
    if trade["target_owner_id"] != user["_id"]:
        raise HTTPException(status_code=403, detail="Only the target team can reject")
    if trade["status"] != "pending":
        raise HTTPException(status_code=400, detail="Trade is not pending")

    await db.trades.update_one(
        {"_id": ObjectId(trade_id)},
        {"$set": {"status": "rejected", "responded_at": datetime.now(timezone.utc).isoformat()}},
    )
    return {"message": "Trade rejected", "status": "rejected"}


@router.post("/trades/{trade_id}/withdraw")
async def withdraw_trade(trade_id: str, request: Request):
    db = _db()
    user = await _get_user(request)
    trade = await db.trades.find_one({"_id": ObjectId(trade_id)})
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")
    if trade["proposer_id"] != user["_id"]:
        raise HTTPException(status_code=403, detail="Only the proposer can withdraw")
    if trade["status"] != "pending":
        raise HTTPException(status_code=400, detail="Trade is not pending")

    await db.trades.update_one(
        {"_id": ObjectId(trade_id)},
        {"$set": {"status": "withdrawn", "responded_at": datetime.now(timezone.utc).isoformat()}},
    )
    return {"message": "Trade withdrawn", "status": "withdrawn"}


# ─── Multi-Party Trade (3+ teams) ────────────────────────────────
async def _enrich_trade_assets(assets: list[dict]) -> list[dict]:
    db = _db()
    enriched = []
    for a in assets or []:
        d = dict(a)
        if a.get("asset_type") == "player" and a.get("player_id"):
            try:
                player = await db.players.find_one({"_id": ObjectId(a["player_id"])})
            except Exception:
                player = None
            if player:
                d.setdefault("player_name", player.get("name"))
                d.setdefault("position", player.get("position"))
                d.setdefault("nhl_team", player.get("team", ""))
                d["points"] = player.get("points", 0)
                d["goals"] = player.get("goals", 0)
                d["assists"] = player.get("assists", 0)
        enriched.append(d)
    return enriched


def _all_non_proposer_accepted(trade: dict) -> bool:
    parties = trade.get("parties") or []
    if not parties:
        return False
    proposer_idx = trade.get("proposer_party_index", 0)
    for i, p in enumerate(parties):
        if i == proposer_idx:
            continue
        if not p.get("accepted"):
            return False
    return True


@router.post("/trades/multi")
async def create_multi_party_trade(input: MultiPartyTradeProposalCreate, request: Request):
    """Create a 3+ team trade. The proposer is whichever party belongs to the
    current user. All non-proposer parties must accept before execution.
    """
    db = _db()
    user = await _get_user(request)

    league = await db.leagues.find_one({"_id": ObjectId(input.league_id)})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")

    if len(input.parties) < 2:
        raise HTTPException(status_code=400, detail="A trade needs at least 2 parties")

    parties: list[dict] = []
    proposer_index: Optional[int] = None
    seen_team_ids = set()
    for idx, p in enumerate(input.parties):
        if p.team_id in seen_team_ids:
            raise HTTPException(status_code=400, detail=f"Duplicate team in parties: {p.team_id}")
        seen_team_ids.add(p.team_id)

        try:
            team = await db.teams.find_one({"_id": ObjectId(p.team_id)})
        except Exception:
            team = None
        if not team:
            raise HTTPException(status_code=404, detail=f"Team {p.team_id} not found")
        if team.get("league_id") != input.league_id:
            raise HTTPException(status_code=400, detail=f"Team {p.team_id} is not in this league")

        if team.get("owner_id") == user["_id"]:
            proposer_index = idx

        sends = await _enrich_trade_assets([a.dict() for a in p.sends])
        receives = await _enrich_trade_assets([a.dict() for a in p.receives])

        parties.append({
            "team_id": p.team_id,
            "team_name": team.get("name"),
            "owner_id": team.get("owner_id"),
            "sends": sends,
            "receives": receives,
            "accepted": False,
            "accepted_at": None,
            "rejected": False,
            "rejected_at": None,
        })

    if proposer_index is None:
        raise HTTPException(status_code=403, detail="You don't own a team in this trade")

    parties[proposer_index]["accepted"] = True
    parties[proposer_index]["accepted_at"] = datetime.now(timezone.utc).isoformat()

    legacy_target_idx = next((i for i in range(len(parties)) if i != proposer_index), proposer_index)
    proposer_team = parties[proposer_index]
    target_team = parties[legacy_target_idx]

    has_conditions = bool(input.conditions)
    review_period_hours = 72
    trade_doc = {
        "league_id": input.league_id,
        "is_multi_party": len(parties) > 2,
        "parties": parties,
        "proposer_team_id": proposer_team["team_id"],
        "proposer_team_name": proposer_team["team_name"],
        "proposer_id": user["_id"],
        "proposer_party_index": proposer_index,
        "target_team_id": target_team["team_id"],
        "target_team_name": target_team["team_name"],
        "target_owner_id": target_team["owner_id"],
        "assets_offered": proposer_team["sends"],
        "assets_requested": proposer_team["receives"],
        "conditions": [c.dict() if hasattr(c, "dict") else c for c in (input.conditions or [])],
        "conditional": has_conditions,
        "message": input.message,
        "status": "pending",
        "votes": {"approve": 0, "veto": 0, "voters": []},
        "submitted_at": datetime.now(timezone.utc).isoformat(),
        "processes_at": (datetime.now(timezone.utc) + timedelta(hours=review_period_hours)).isoformat(),
        "responded_at": None,
        "processed_at": None,
    }

    result = await db.trades.insert_one(trade_doc)
    trade_doc["_id"] = str(result.inserted_id)

    for p in parties:
        if p["owner_id"] == user["_id"]:
            continue
        try:
            await _create_notification(
                p["owner_id"],
                NT_TRADE_PROPOSED,
                "New Multi-Team Trade Proposal" if trade_doc["is_multi_party"] else "New Trade Proposal",
                f"{proposer_team['team_name']} included you in a {len(parties)}-team trade",
                input.league_id,
                "/transactions",
            )
        except Exception:
            pass

    await _broadcast(f"league_{input.league_id}", "trade_proposed", {
        "trade_id": str(result.inserted_id),
        "proposer": proposer_team["team_name"],
        "parties": [p["team_name"] for p in parties],
        "is_multi_party": trade_doc["is_multi_party"],
    })

    return trade_doc


@router.post("/trades/{trade_id}/party-respond")
async def party_respond_to_trade(trade_id: str, input: TradePartyResponse, request: Request):
    """Accept or reject the trade as the user's party."""
    db = _db()
    logger = _logger()
    user = await _get_user(request)
    trade = await db.trades.find_one({"_id": ObjectId(trade_id)})
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")

    parties = trade.get("parties") or []
    if not parties:
        raise HTTPException(status_code=400, detail="This trade does not support party-respond. Use /accept or /reject.")
    if trade.get("status") != "pending":
        raise HTTPException(status_code=400, detail=f"Trade status is {trade.get('status')}")

    party_idx = next((i for i, p in enumerate(parties) if p.get("owner_id") == user["_id"]), None)
    if party_idx is None:
        raise HTTPException(status_code=403, detail="You are not a party to this trade")

    action = input.action.lower()
    now_iso = datetime.now(timezone.utc).isoformat()

    if action == "reject":
        await db.trades.update_one(
            {"_id": ObjectId(trade_id)},
            {"$set": {
                f"parties.{party_idx}.rejected": True,
                f"parties.{party_idx}.rejected_at": now_iso,
                "status": "rejected",
                "responded_at": now_iso,
            }},
        )
        await _broadcast(f"league_{trade['league_id']}", "trade_rejected", {
            "trade_id": trade_id, "rejecter": parties[party_idx]["team_name"],
        })
        return {"status": "rejected", "rejected_by": parties[party_idx]["team_name"]}

    if action != "accept":
        raise HTTPException(status_code=400, detail="action must be 'accept' or 'reject'")

    await db.trades.update_one(
        {"_id": ObjectId(trade_id)},
        {"$set": {
            f"parties.{party_idx}.accepted": True,
            f"parties.{party_idx}.accepted_at": now_iso,
        }},
    )
    refreshed = await db.trades.find_one({"_id": ObjectId(trade_id)})

    executed = None
    if _all_non_proposer_accepted(refreshed):
        await db.trades.update_one(
            {"_id": ObjectId(trade_id)},
            {"$set": {"status": "accepted", "responded_at": now_iso}},
        )
        refreshed = await db.trades.find_one({"_id": ObjectId(trade_id)})
        if not refreshed.get("conditions"):
            try:
                executed = await _execute_trade(refreshed)
                refreshed = await db.trades.find_one({"_id": ObjectId(trade_id)})
            except Exception as e:
                logger.exception("Multi-party trade auto-execute failed: %s", e)

        try:
            party_names = [p["team_name"] for p in parties]
            is_multi = len(parties) > 2
            title = (
                f"{len(parties)}-team trade accepted"
                if is_multi else "Trade accepted"
            )
            body = (
                f"All {len(parties)} teams accepted: "
                + " ↔ ".join(party_names)
            )
            for p in parties:
                if not p.get("owner_id"):
                    continue
                await _create_notification(
                    p["owner_id"],
                    NT_TRADE_ACCEPTED,
                    title, body,
                    trade["league_id"],
                    "/transactions",
                )
        except Exception as e:
            logger.warning("trade_accepted notification failed: %s", e)

    await _broadcast(f"league_{trade['league_id']}", "trade_party_accepted", {
        "trade_id": trade_id, "accepter": parties[party_idx]["team_name"],
        "all_accepted": _all_non_proposer_accepted(refreshed),
        "executed": bool(executed and executed.get("executed")),
    })

    return {
        "status": refreshed.get("status"),
        "all_accepted": _all_non_proposer_accepted(refreshed),
        "executed": bool(executed and executed.get("executed")),
    }


# ─── Execution / Conditions / Vote ───────────────────────────────
@router.post("/trades/{trade_id}/execute")
async def execute_trade_endpoint(trade_id: str, request: Request):
    db = _db()
    user = await _get_user(request)
    trade = await db.trades.find_one({"_id": ObjectId(trade_id)})
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")
    if trade.get("status") not in ("accepted", "pending", "conditional"):
        raise HTTPException(status_code=400, detail=f"Trade status is {trade.get('status')}")
    league = await db.leagues.find_one({"_id": ObjectId(trade["league_id"])})
    is_participant = user["_id"] in (trade.get("proposer_id"), trade.get("target_owner_id"))
    is_comm = league and (
        league["commissioner_id"] == user["_id"]
        or user["_id"] in (league.get("co_commissioners") or [])
    )
    if not (is_participant or is_comm):
        raise HTTPException(status_code=403, detail="Not authorized to execute this trade")
    if trade.get("conditions"):
        check = await _evaluate_conditions(trade)
        if not check["all_met"]:
            return {"executed": False, "reason": "conditions_not_met", **check}
    return await _execute_trade(trade)


@router.post("/trades/{trade_id}/evaluate-conditions")
async def evaluate_trade_conditions_endpoint(trade_id: str):
    db = _db()
    trade = await db.trades.find_one({"_id": ObjectId(trade_id)})
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")
    return await _evaluate_conditions(trade)


@router.post("/trades/{trade_id}/vote")
async def vote_on_trade(trade_id: str, input: TradeVote, request: Request):
    db = _db()
    user = await _get_user(request)
    trade = await db.trades.find_one({"_id": ObjectId(trade_id)})
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")
    if trade["status"] not in ["pending", "accepted"]:
        raise HTTPException(status_code=400, detail="Trade is not open for voting")

    voters = trade.get("votes", {}).get("voters", [])
    if user["_id"] in voters:
        raise HTTPException(status_code=400, detail="Already voted on this trade")

    vote_field = "votes.approve" if input.vote == "approve" else "votes.veto"
    await db.trades.update_one(
        {"_id": ObjectId(trade_id)},
        {
            "$inc": {vote_field: 1},
            "$push": {"votes.voters": user["_id"]},
        },
    )

    league = await db.leagues.find_one({"_id": ObjectId(trade["league_id"])})
    total_teams = league.get("current_teams", 0)
    veto_threshold = total_teams // 2

    updated_trade = await db.trades.find_one({"_id": ObjectId(trade_id)})
    if updated_trade["votes"]["veto"] > veto_threshold:
        await db.trades.update_one(
            {"_id": ObjectId(trade_id)},
            {"$set": {"status": "vetoed", "processed_at": datetime.now(timezone.utc).isoformat()}},
        )
        await _broadcast(f"league_{trade['league_id']}", "trade_vetoed", {"trade_id": trade_id})
        return {"message": "Trade vetoed by league vote", "status": "vetoed"}

    return {"message": f"Vote recorded: {input.vote}", "votes": updated_trade["votes"]}
