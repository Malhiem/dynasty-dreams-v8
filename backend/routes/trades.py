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


def _enforce_trade_deadline(league: dict) -> None:
    """Reject new trade proposals once the league's trade deadline week has
    passed. Reads `trade_deadline_week` from `db.leagues` (single source of
    truth) and the league's `current_week`. No-op when either is unset (i.e.
    the league hasn't configured a deadline yet — preserves legacy behaviour).
    """
    deadline = league.get("trade_deadline_week")
    current = league.get("current_week")
    try:
        deadline_int = int(deadline) if deadline is not None else None
        current_int = int(current) if current is not None else None
    except (TypeError, ValueError):
        return
    if deadline_int is None or current_int is None:
        return
    if current_int > deadline_int:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Trade deadline (week {deadline_int}) has passed; "
                f"new proposals are locked. Current week: {current_int}."
            ),
        )


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

    _enforce_trade_deadline(league)

    # ── Empty-trade guard (iter 82) ──────────────────────────────
    # Reject proposals with zero assets on BOTH sides. A trade must move at
    # least one player or pick. This stops the long-standing bug where
    # accidental empty trades clutter the Transactions feed.
    if not input.assets_offered and not input.assets_requested:
        raise HTTPException(
            status_code=400,
            detail=(
                "A trade must include at least one player or draft pick. "
                "Add an asset on either side before proposing."
            ),
        )

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

    review_period_hours = int(league.get("trade_review_period_hours") or 72)
    has_conditions = bool(getattr(input, "conditions", None))
    pick_upgrades = [u.dict() if hasattr(u, "dict") else u for u in (getattr(input, "pick_upgrades", None) or [])]
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
        "pick_upgrades": pick_upgrades,
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


@router.get("/trades/conditional")
async def get_conditional_trades(league_id: str, request: Request = None):
    """Return all EXECUTED conditional trades in this league.

    A "conditional trade" in our model is exclusively a clause of the form:
        (player/team metric op threshold)  →  (draft pick modification)

    Each trade in the response carries a `pick_upgrades_state` array with
    the full lifecycle of each pick-outcome clause: current state
    (pending/triggered/failed), the hydrated `pick`, the live actual value
    + met flag (when still pending), and a human-readable `outcome_text`
    describing what happens if the condition triggers.

    Whole-trade execution gates (the `conditions` array with no pick
    outcome) are deliberately NOT surfaced here — they are proposal-time
    gates and have no ongoing resolution lifecycle.

    Shape:
        {
          "trades": [
            {
              ...full trade doc (assets, parties, dates, status),
              "pick_upgrades_state": [
                {
                  ...the original pick_upgrade clause,
                  "pick": {round, year, pick_number, current_team_id, ...},
                  "actual_value": float|None,
                  "met": bool,
                  "state": "triggered" | "failed" | "pending",
                  "outcome_text": str   # human-readable "if triggered" line
                }
              ]
            },
            ...
          ]
        }
    """
    db = _db()
    # A "conditional trade" in our model is exclusively
    # (condition on player/team metric) → (draft-pick modification). Whole-
    # trade execution gates (`conditions` array with no pick outcome) are
    # NOT surfaced here — they're handled at the proposal stage and have no
    # ongoing resolution lifecycle. So we filter strictly on a non-empty
    # `pick_upgrades` array.
    query = {
        "league_id": league_id,
        "status": "executed",
        "pick_upgrades": {"$exists": True, "$ne": []},
    }
    raw_trades = await db.trades.find(query).sort("executed_at", -1).to_list(200)

    # Cache picks we touch so multi-upgrade trades don't re-fetch the same row.
    pick_cache: dict = {}

    async def _resolve_pick(pid: str):
        if not pid:
            return None
        if pid in pick_cache:
            return pick_cache[pid]
        try:
            doc = await db.draft_picks.find_one({"_id": ObjectId(pid)})
        except Exception:
            doc = None
        if doc:
            doc["_id"] = str(doc["_id"])
        pick_cache[pid] = doc
        return doc

    out = []
    eval_single = _deps.get("_evaluate_single_condition")
    for t in raw_trades:
        t["_id"] = str(t["_id"])

        # Per-pick upgrade state (pick protection clauses). Each row carries
        # its own condition; we evaluate it live when still pending so the
        # UI can render a real-time progress indicator.
        upgrades_state = []
        for up in (t.get("pick_upgrades") or []):
            cond = up.get("condition") or {}
            pick = await _resolve_pick(up.get("pick_id"))
            # Current state — applied, failed, or still pending
            if up.get("applied_at"):
                state = "triggered"
            elif up.get("failed_at"):
                state = "failed"
            else:
                state = "pending"
            actual = up.get("actual_value")
            met = None
            if state == "pending" and eval_single:
                try:
                    met, actual = await eval_single(cond, t)
                except Exception:
                    met = None
            elif state == "triggered":
                met = True
            elif state == "failed":
                met = False
            # Build a human-readable "outcome" line for the UI. We show the
            # FROM → TO comparison whenever possible so the user can read
            # "pick upgraded from 2nd to 1st" at a glance.
            new_year = up.get("new_year")
            new_round = up.get("new_round")
            new_team = up.get("new_team_id")
            cur_year = pick.get("year") if pick else None
            cur_round = pick.get("round") if pick else None
            # For triggered upgrades, the pick has already been mutated, so
            # the "from" state is captured on the upgrade itself (persisted
            # by trade_engine when the trigger fired).
            from_year = up.get("from_year") or cur_year
            from_round = up.get("from_round") or cur_round

            def _fmt(yr, rd):
                bits = []
                if yr:
                    bits.append(str(yr))
                if rd:
                    bits.append(f"R{rd}")
                return " ".join(bits) or "pick"

            target_str = _fmt(new_year or cur_year, new_round or cur_round)
            from_str = _fmt(from_year, from_round)
            current_str = _fmt(cur_year, cur_round)
            if state == "triggered":
                if from_str and target_str and from_str != target_str:
                    outcome_text = f"Pick is now {target_str} (was {from_str})"
                else:
                    outcome_text = f"Pick transferred → {target_str}"
            elif state == "failed":
                outcome_text = f"Pick remains {current_str} (condition unmet at evaluation)"
            else:
                # Pending — preview "from X to Y" using CURRENT state
                if current_str and target_str and current_str != target_str:
                    outcome_text = f"If triggered, pick upgrades from {current_str} to {target_str}"
                else:
                    outcome_text = f"If triggered, pick becomes {target_str}"

            upgrades_state.append({
                **up,
                "pick": pick,
                "actual_value": actual,
                "met": met,
                "state": state,
                "outcome_text": outcome_text,
            })
        t["pick_upgrades_state"] = upgrades_state
        out.append(t)

    return {"trades": out, "count": len(out)}


# ─── Conditional notification subscriptions ──────────────────────────
# Users can opt-in to receive a notification when a pending conditional
# clause resolves (trigger or fail). Both trade parties (proposer +
# target_owner) are notified automatically; this lets ANY league member
# follow a conditional clause they're interested in.

@router.get("/trades/conditional/subscriptions")
async def list_conditional_subs(league_id: str, request: Request = None):
    """Return the current user's subscription rows for this league.

    Shape: { "subscriptions": [{trade_id, pick_upgrade_idx, _id}, ...] }
    """
    db = _db()
    user = await _get_user(request)
    rows = await db.conditional_subscriptions.find({
        "league_id": league_id,
        "user_id": user["_id"],
    }).to_list(500)
    for r in rows:
        r["_id"] = str(r["_id"])
    return {"subscriptions": rows}


@router.post("/trades/conditional/{trade_id}/subscribe")
async def subscribe_conditional(trade_id: str, body: dict, request: Request = None):
    """Toggle a subscription for the current user on this conditional clause.

    Body:
        {
          "pick_upgrade_idx": int | -1 for whole-trade trigger conditions,
          "action": "subscribe" | "unsubscribe"
        }
    """
    db = _db()
    user = await _get_user(request)
    # Validate the trade exists + is conditional + is executed (no point
    # subscribing to a clause that already settled or hasn't processed).
    try:
        trade = await db.trades.find_one({"_id": ObjectId(trade_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid trade_id")
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")
    if trade.get("status") != "executed":
        raise HTTPException(status_code=400,
                            detail="Can only subscribe to executed conditional trades")

    pu_idx = int(body.get("pick_upgrade_idx", -1) if body.get("pick_upgrade_idx") is not None else -1)
    action = (body.get("action") or "subscribe").lower()

    # Defensive bounds: pu_idx must reference a real pending pick_upgrade
    # row OR be -1 (whole-trade trigger conditions).
    if pu_idx >= 0:
        upgrades = trade.get("pick_upgrades") or []
        if pu_idx >= len(upgrades):
            raise HTTPException(status_code=400, detail="pick_upgrade_idx out of range")
        u = upgrades[pu_idx]
        if u.get("applied_at") or u.get("failed_at"):
            raise HTTPException(status_code=400, detail="That clause has already settled")

    query = {
        "league_id": trade.get("league_id"),
        "trade_id": trade_id,
        "user_id": user["_id"],
        "pick_upgrade_idx": pu_idx,
    }
    if action == "unsubscribe":
        res = await db.conditional_subscriptions.delete_one(query)
        return {"subscribed": False, "removed": res.deleted_count}

    # subscribe (idempotent upsert)
    now = datetime.now(timezone.utc).isoformat()
    await db.conditional_subscriptions.update_one(
        query,
        {"$setOnInsert": {**query, "created_at": now}},
        upsert=True,
    )
    return {"subscribed": True}


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


@router.get("/leagues/{league_id}/pending-trades")
async def get_pending_trades(league_id: str):
    """Trades currently in flight (status in pending/voting/conditional).
    Powers the league homepage 'Pending Trades' panel."""
    db = _db()
    trades = await db.trades.find({
        "league_id": league_id,
        "status": {"$in": ["pending", "voting", "conditional"]},
    }).sort("submitted_at", -1).to_list(100)
    for t in trades:
        t["_id"] = str(t["_id"])
    return {"league_id": league_id, "pending_trades": trades, "count": len(trades)}


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

    _enforce_trade_deadline(league)

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
    review_period_hours = int(league.get("trade_review_period_hours") or 72)
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
        "pick_upgrades": [u.dict() if hasattr(u, "dict") else u for u in (getattr(input, "pick_upgrades", None) or [])],
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
    """Cast or change a vote on a pending trade.

    Behaviour (iter 82 update):
    * Each voter is tracked by user_id with their current choice in
      `votes.choices` ({user_id: "approve"|"veto"}). Counts in
      `votes.approve` / `votes.veto` are derived from this map so they stay
      consistent if a voter changes their mind.
    * A user may **change** their vote at any time while the trade is still
      open. Submitting the same vote twice is a no-op (idempotent).
    * The trade is auto-vetoed once **strict majority** of the league's
      `trade_veto_threshold_pct` is met. The threshold is presented in the
      UI both as a % and as an absolute team count.
    """
    db = _db()
    user = await _get_user(request)
    trade = await db.trades.find_one({"_id": ObjectId(trade_id)})
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")
    if trade["status"] not in ["pending", "accepted"]:
        raise HTTPException(status_code=400, detail="Trade is not open for voting")
    if input.vote not in ("approve", "veto"):
        raise HTTPException(status_code=400, detail="vote must be 'approve' or 'veto'")

    voter_id = user["_id"]
    choices = (trade.get("votes") or {}).get("choices") or {}
    prev_choice = choices.get(str(voter_id))
    # Idempotent: same vote → just echo current counts.
    if prev_choice == input.vote:
        return {
            "message": "Vote unchanged",
            "votes": _recount_votes(choices),
            "your_vote": prev_choice,
        }
    choices[str(voter_id)] = input.vote
    counts = _recount_votes(choices)
    await db.trades.update_one(
        {"_id": ObjectId(trade_id)},
        {"$set": {
            "votes.choices": choices,
            "votes.approve": counts["approve"],
            "votes.veto": counts["veto"],
            "votes.voters": list(choices.keys()),  # legacy field — kept in sync
        }},
    )

    league = await db.leagues.find_one({"_id": ObjectId(trade["league_id"])})
    threshold_info = _veto_threshold(league)
    if threshold_info["enabled"] and counts["veto"] >= threshold_info["teams_required"]:
        await db.trades.update_one(
            {"_id": ObjectId(trade_id)},
            {"$set": {
                "status": "vetoed",
                "processed_at": datetime.now(timezone.utc).isoformat(),
            }},
        )
        await _broadcast(
            f"league_{trade['league_id']}",
            "trade_vetoed",
            {"trade_id": trade_id, "veto_count": counts["veto"]},
        )
        return {
            "message": "Trade vetoed by league vote",
            "status": "vetoed",
            "votes": counts,
            "veto_threshold": threshold_info,
            "your_vote": input.vote,
        }

    return {
        "message": f"Vote {'changed' if prev_choice else 'recorded'}: {input.vote}",
        "votes": counts,
        "veto_threshold": threshold_info,
        "your_vote": input.vote,
    }


def _recount_votes(choices: dict) -> dict:
    """Derive {approve, veto} counts from the per-voter `choices` map."""
    return {
        "approve": sum(1 for v in choices.values() if v == "approve"),
        "veto": sum(1 for v in choices.values() if v == "veto"),
    }


def _veto_threshold(league: dict) -> dict:
    """Return {enabled, pct, total_teams, teams_required} for the league's
    veto policy. `teams_required` is the absolute number of vetoes needed to
    auto-veto a trade (uses ceil so 50% of 12 = 6, not 5)."""
    import math
    total = int(league.get("current_teams") or 0)
    pct = league.get("trade_veto_threshold_pct")
    if pct is None:
        pct = 50
    pct = int(pct)
    enabled = pct > 0 and total > 0
    if not enabled:
        return {"enabled": False, "pct": pct, "total_teams": total, "teams_required": 0}
    teams_required = max(1, math.ceil(total * pct / 100))
    return {
        "enabled": True,
        "pct": pct,
        "total_teams": total,
        "teams_required": teams_required,
    }


@router.get("/trades/{trade_id}/votes")
async def get_trade_votes(trade_id: str, request: Request):
    """Return current vote tally + threshold + the calling user's own choice.
    Frontend uses this to render the live count alongside the approve/veto
    buttons and to know whether the user has already voted (so the buttons
    can highlight their current choice and allow toggling)."""
    db = _db()
    user = await _get_user(request)
    trade = await db.trades.find_one({"_id": ObjectId(trade_id)})
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")
    choices = (trade.get("votes") or {}).get("choices") or {}
    counts = _recount_votes(choices)
    league = await db.leagues.find_one({"_id": ObjectId(trade["league_id"])})
    return {
        "trade_id": trade_id,
        "votes": counts,
        "veto_threshold": _veto_threshold(league),
        "your_vote": choices.get(str(user["_id"])),
        "status": trade["status"],
    }
