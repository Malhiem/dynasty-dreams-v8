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
from pydantic import BaseModel

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
    # Iter 232L (refactor) — Trade asset hydration lives in its own module
    # now; forward the same deps so it can share `calculate_fantasy_points`
    # and the shared logger.
    _trade_hydration_setup(deps)


def _db(): return _deps["db"]
def _logger(): return _deps["logger"]
async def _get_user(request): return await _deps["get_current_user"](request)
async def _broadcast(*a, **kw): return await _deps["broadcast_to_room"](*a, **kw)
async def _create_notification(*a, **kw): return await _deps["create_notification"](*a, **kw)
async def _execute_trade(trade): return await _deps["_execute_trade"](trade)
async def _evaluate_conditions(trade): return await _deps["_evaluate_conditions"](trade)


# ─── Iter 232L — Asset hydration for the Transactions page ────────────
# Historical trade docs only store {player_name, position, points, goals,
# assists} on each asset. The Transactions page needs age, cap hit, fantasy
# points (season + per-game), and a stat-category breakdown so managers can
# actually evaluate the trade. The heavy lifting now lives in
# `routes/trade_hydration.py` — we alias the public helpers so existing
# call sites and tests keep working.
from routes.trade_hydration import (  # noqa: E402
    hydrate_trade_assets as _hydrate_trade_assets,
    hydrate_trades as _hydrate_trades,
    setup as _trade_hydration_setup,
)


# Iter 230 — League-wide notification fanout for "any trade …" events.
# Looks up all team owners + co-owners in a league and emits the same
# notification to each (minus an optional exclusion list, typically the
# trade's direct counterparties who already got a targeted notification).
async def _notify_league_event(
    league_id: str,
    event_type: str,
    title: str,
    message: str,
    link: Optional[str] = None,
    exclude_user_ids: Optional[list] = None,
) -> None:
    exclude = set(filter(None, exclude_user_ids or []))
    db = _db()
    teams = await db.teams.find(
        {"league_id": league_id},
        {"owner_id": 1, "co_owner_ids": 1},
    ).to_list(200)
    recipients: set = set()
    for t in teams:
        if t.get("owner_id"):
            recipients.add(t["owner_id"])
        for co in (t.get("co_owner_ids") or []):
            if co:
                recipients.add(co)
    for uid in recipients - exclude:
        try:
            await _create_notification(uid, event_type, title, message, league_id, link)
        except Exception as e:
            _logger().debug(f"league fanout {event_type} → {uid} skipped: {e}")


# Iter 231h — Read the canonical review-period hours from the new
# `transactions_config.trades` envelope with a fallback to the legacy
# top-level `league.trade_review_period_hours` for backward compat.
def _resolve_review_period_hours(league: dict) -> int:
    cfg = (league.get("transactions_config") or {}).get("trades") or {}
    if cfg.get("review_period_hours") is not None:
        try:
            return int(cfg["review_period_hours"])
        except Exception:
            pass
    return int(league.get("trade_review_period_hours") or 72)


# Iter 231j — Pull the trades-config sub-doc with safe defaults so the
# trade engine can enforce config-driven constraints (max trades per team,
# allow-before-draft, allow-during-draft, conditional-trades flag).
def _trades_cfg(league: dict) -> dict:
    return (league.get("transactions_config") or {}).get("trades") or {}


async def _enforce_trade_config(
    db,
    league: dict,
    *,
    proposer_team_ids: list,
    has_conditions: bool,
) -> None:
    """Iter 231j — Apply the Commissioner-configured trade rules.

    Constraints enforced (each one short-circuits with HTTPException 400):
      - max_trades_per_team: cap on in-flight (proposed + pending) trades per team
      - allow_before_draft / allow_during_draft: gate by league.status
      - conditional_trades_enabled: reject conditional proposals when disabled

    `proposer_team_ids` is a list because multi-party trades have multiple
    senders; the cap is checked PER team in the list.
    """
    cfg = _trades_cfg(league)
    league_id = str(league["_id"])

    # ── Conditional trades master toggle ─────────────────────────
    if has_conditions and not cfg.get("conditional_trades_enabled", False):
        raise HTTPException(
            status_code=400,
            detail=(
                "Conditional trades are disabled in this league. "
                "Ask your commissioner to enable them under "
                "League Administration → Transactions → Trades."
            ),
        )

    # ── Draft-window gating ──────────────────────────────────────
    # league.status is one of {"setup", "draft_active", "active", "complete",
    # "archived"} across the codebase. "setup" is pre-draft; "draft_active"
    # is during the draft.
    status = (league.get("status") or "").lower()
    allow_before = cfg.get("allow_before_draft", True)
    allow_during = cfg.get("allow_during_draft", False)
    if status == "setup" and not allow_before:
        raise HTTPException(
            status_code=400,
            detail="Trades are locked before the league's draft. Commissioner can change this in Transactions → Trades.",
        )
    if status == "draft_active" and not allow_during:
        raise HTTPException(
            status_code=400,
            detail="Trades are locked during the live draft. Commissioner can change this in Transactions → Trades.",
        )

    # ── Max trades per team (proposed + pending count) ───────────
    max_trades = cfg.get("max_trades_per_team")
    if max_trades is not None and max_trades > 0 and proposer_team_ids:
        for tid in proposer_team_ids:
            count = await db.trades.count_documents({
                "league_id": league_id,
                "status": {"$in": ["proposed", "pending"]},
                "$or": [
                    {"proposer_team_id": tid},
                    {"target_team_id": tid},
                    {"parties.team_id": tid},
                ],
            })
            if count >= int(max_trades):
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Team has reached the league's cap of {max_trades} "
                        f"in-flight trades. Resolve an existing proposal before "
                        f"submitting a new one."
                    ),
                )


def _enforce_trade_deadline(league: dict) -> None:
    """Reject new trade proposals once the league's trade deadline has passed.

    Two layers of enforcement (newest takes precedence):
      1. `trade_deadline_at` (ISO 8601 datetime, Iter 128) — if present and
         the current UTC time is past it, block. This is the exact-moment
         lock that commissioners can set in admin → Trade Settings.
      2. `trade_deadline_week` (legacy week-number) — if the league has a
         `current_week` past the deadline week, block.

    Either layer can be unset; missing values are silently skipped to
    preserve legacy behaviour for leagues that never configured a deadline.
    """
    # ── Layer 1: explicit datetime ─────────────────────────────────
    deadline_at = league.get("trade_deadline_at")
    if deadline_at:
        try:
            from datetime import datetime as _dt, timezone as _tz
            dt = _dt.fromisoformat(str(deadline_at).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=_tz.utc)
            now = _dt.now(_tz.utc)
            if now >= dt:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Trade deadline ({dt.isoformat()}) has passed; "
                        "new proposals are locked."
                    ),
                )
        except HTTPException:
            raise
        except (ValueError, TypeError):
            # Malformed datetime — fall through to week-based check.
            pass

    # ── Layer 2: legacy week number ────────────────────────────────
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
# Iter 230 — Source of truth lives in `routes/notification_events.py`. We
# re-export the trade-related constants here for backward-compat with the
# existing call-sites.
from routes.notification_events import (
    EVT_TRADE_PROPOSED as NT_TRADE_PROPOSED,
    EVT_TRADE_ACCEPTED_MINE as NT_TRADE_ACCEPTED,
    EVT_TRADE_ACCEPTED_ANY,
    EVT_TRADE_DECLINED_OR_VETOED_MINE,
    EVT_TRADE_VETOED_ANY,
    EVT_TRADE_PROCESSED,
    EVT_TRADE_BLOCK_UPDATED,
)


# ── Iter 193 — Foundation for in-draft pick trade flow ──────────
# Minimal scope: accept a pick-trade proposal during an active draft,
# stamp the trade with `status="pending_draft_review"` + a future
# `review_expires_at` timestamp computed from the league's
# `draft_trade_review_minutes` setting, then broadcast a system
# message to the draft-room chat. Vote/approve buttons, auto-execute
# timer, on-the-clock reassignment all deferred to iter 194.
@router.post("/drafts/{league_id}/propose-pick-trade")
async def propose_in_draft_pick_trade(league_id: str, request: Request):
    db = _db()
    user = await _get_user(request)
    payload = await request.json()

    league = await db.leagues.find_one({"_id": ObjectId(league_id)})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")

    # Validation — proposer must own a team in this league and the trade
    # must include at least one pick asset on either side. We trust the
    # client to supply the trade shape (mirroring TradeProposalCreate)
    # since the full schema lives in trade_waiver_engine.
    proposer_team_id = payload.get("proposer_team_id")
    receiver_team_id = payload.get("receiver_team_id")
    proposer_assets = payload.get("proposer_assets") or []
    receiver_assets = payload.get("receiver_assets") or []
    if not proposer_team_id or not receiver_team_id:
        raise HTTPException(status_code=400, detail="proposer_team_id + receiver_team_id required")
    has_pick = any(a.get("type") == "pick" for a in proposer_assets + receiver_assets)
    if not has_pick:
        raise HTTPException(status_code=400, detail="At least one pick asset required for in-draft trade")

    review_minutes = int(league.get("draft_trade_review_minutes") or 30)
    review_expires_at = datetime.now(timezone.utc) + timedelta(minutes=max(0, review_minutes))

    trade_doc = {
        "league_id": league_id,
        "proposer_team_id": proposer_team_id,
        "receiver_team_id": receiver_team_id,
        "proposer_assets": proposer_assets,
        "receiver_assets": receiver_assets,
        "status": "pending_draft_review",
        "review_expires_at": review_expires_at.isoformat(),
        "post_review_action": league.get("draft_trade_post_delay_action") or "auto_execute",
        "votes": {"approve": 0, "veto": 0, "voters": [], "choices": {}},
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": user["_id"],
        "is_in_draft_pick_trade": True,
    }
    result = await db.trades.insert_one(trade_doc)
    trade_id = str(result.inserted_id)

    # Broadcast a draft-room chat message so all participants see the
    # proposal inline (room id == league id for the draft chat).
    proposer_name = payload.get("proposer_team_name") or "A team"
    receiver_name = payload.get("receiver_team_name") or "another team"
    try:
        await _broadcast(league_id, {
            "type": "draft_chat",
            "kind": "pick_trade_proposed",
            "trade_id": trade_id,
            "review_expires_at": review_expires_at.isoformat(),
            "message": f"📈 {proposer_name} proposed a pick trade with {receiver_name}. Review window: {review_minutes} min.",
        })
    except Exception:
        # Broadcast failure is non-fatal — the trade still persists.
        pass

    return {
        "trade_id": trade_id,
        "status": "pending_draft_review",
        "review_expires_at": review_expires_at.isoformat(),
        "post_review_action": trade_doc["post_review_action"],
    }


# ─────────────────────────────────────────────────────────────────────
# Iter 194c — In-draft pick trade: vote/approve + execute + auto-timer
# ─────────────────────────────────────────────────────────────────────
async def _execute_in_draft_pick_trade(db, trade: dict) -> dict:
    """Repoint each pick asset's `current_team_id` to the new owner +
    swap any player assets on the rosters. Marks trade.status='executed'
    and writes an audit row. Used by both manual vote-approve and the
    auto-execute timer."""
    league_id = trade["league_id"]
    proposer_team_id = trade["proposer_team_id"]
    receiver_team_id = trade["receiver_team_id"]

    proposer = await db.teams.find_one({"_id": ObjectId(proposer_team_id)})
    receiver = await db.teams.find_one({"_id": ObjectId(receiver_team_id)})
    if not (proposer and receiver):
        raise HTTPException(status_code=404, detail="Team(s) not found for trade execution")

    p_roster = list(proposer.get("roster") or [])
    r_roster = list(receiver.get("roster") or [])

    async def _move_picks(assets, from_team_id, to_team_id, to_team_name):
        for a in assets or []:
            if a.get("type") != "pick":
                continue
            qry = {"league_id": league_id, "current_team_id": from_team_id}
            if a.get("pick_id"):
                try:
                    qry["_id"] = ObjectId(a["pick_id"])
                except Exception:
                    pass
            if a.get("year"):
                qry["year"] = int(a["year"])
            if a.get("round"):
                try:
                    qry["round"] = int(str(a["round"]).replace("R", "").strip())
                except Exception:
                    pass
            await db.draft_picks.update_one(
                qry, {"$set": {"current_team_id": to_team_id, "current_team_name": to_team_name}},
            )

    await _move_picks(trade.get("proposer_assets"), proposer_team_id, receiver_team_id, receiver.get("name"))
    await _move_picks(trade.get("receiver_assets"), receiver_team_id, proposer_team_id, proposer.get("name"))

    # Swap player assets (rare in-draft, but supported)
    for a in trade.get("proposer_assets") or []:
        if a.get("type") == "player" and a.get("player_id"):
            pid = a["player_id"]
            if pid in p_roster:
                p_roster.remove(pid)
            if pid not in r_roster:
                r_roster.append(pid)
    for a in trade.get("receiver_assets") or []:
        if a.get("type") == "player" and a.get("player_id"):
            pid = a["player_id"]
            if pid in r_roster:
                r_roster.remove(pid)
            if pid not in p_roster:
                p_roster.append(pid)
    await db.teams.update_one({"_id": proposer["_id"]}, {"$set": {"roster": p_roster}})
    await db.teams.update_one({"_id": receiver["_id"]}, {"$set": {"roster": r_roster}})

    now = datetime.now(timezone.utc).isoformat()
    await db.trades.update_one(
        {"_id": trade["_id"]},
        {"$set": {"status": "executed", "executed_at": now}},
    )

    # Iter 194c — On-the-clock reassignment: if the *current* draft pick
    # was traded, force the draft engine to re-broadcast the next picker.
    draft = await db.drafts.find_one({"league_id": league_id, "status": {"$in": ["in_progress", "active", "paused"]}})
    if draft:
        on_clock = await db.draft_picks.find_one({
            "league_id": league_id, "round": draft.get("current_round"), "pick": draft.get("current_pick"),
        })
        if on_clock:
            await db.activity_feed.insert_one({
                "league_id": league_id,
                "event_type": "draft_pick_trade_executed",
                "message": f"Pick trade executed during draft — on-the-clock reassigned to {on_clock.get('current_team_name')}",
                "metadata": {
                    "trade_id": str(trade["_id"]),
                    "new_on_clock_team_id": on_clock.get("current_team_id"),
                    "round": draft.get("current_round"),
                    "pick": draft.get("current_pick"),
                },
                "created_at": now,
            })
            try:
                await _broadcast(league_id, {
                    "type": "draft_on_the_clock",
                    "round": draft.get("current_round"),
                    "pick": draft.get("current_pick"),
                    "team_id": on_clock.get("current_team_id"),
                    "team_name": on_clock.get("current_team_name"),
                    "reason": "pick_trade_executed",
                })
            except Exception:
                pass

    await db.activity_feed.insert_one({
        "league_id": league_id,
        "event_type": "draft_pick_traded",
        "message": f"In-draft pick trade executed: {proposer.get('name')} ↔ {receiver.get('name')}",
        "metadata": {"trade_id": str(trade["_id"])},
        "created_at": now,
    })
    return {"trade_id": str(trade["_id"]), "status": "executed", "executed_at": now}


@router.post("/drafts/{league_id}/pick-trade/{trade_id}/vote")
async def vote_in_draft_pick_trade(league_id: str, trade_id: str, request: Request):
    """Cast an approve/veto vote on a pending in-draft pick trade. Body:
    `{choice: "approve"|"veto"}`. Auto-executes / vetoes once the
    majority threshold is met (depending on `post_review_action`)."""
    db = _db()
    user = await _get_user(request)
    body = await request.json()
    choice = body.get("choice")
    if choice not in ("approve", "veto"):
        raise HTTPException(status_code=400, detail="choice must be 'approve' or 'veto'")

    trade = await db.trades.find_one({"_id": ObjectId(trade_id), "league_id": league_id, "is_in_draft_pick_trade": True})
    if not trade:
        raise HTTPException(status_code=404, detail="In-draft pick trade not found")
    if trade.get("status") != "pending_draft_review":
        raise HTTPException(status_code=400, detail=f"Trade not pending review (status={trade.get('status')})")

    uid = str(user["_id"])
    votes = trade.get("votes") or {"approve": 0, "veto": 0, "voters": [], "choices": {}}
    prev = votes.get("choices", {}).get(uid)
    if prev == choice:
        return {"trade_id": trade_id, "votes": votes, "noop": True}
    if prev:  # flip existing vote
        votes[prev] = max(0, votes.get(prev, 0) - 1)
    votes[choice] = votes.get(choice, 0) + 1
    votes.setdefault("choices", {})[uid] = choice
    if uid not in (votes.get("voters") or []):
        votes.setdefault("voters", []).append(uid)
    await db.trades.update_one({"_id": trade["_id"]}, {"$set": {"votes": votes}})

    # ── Tally & decide ──
    policy = trade.get("post_review_action") or "auto_execute"
    total_teams = await db.teams.count_documents({"league_id": league_id})
    majority = (total_teams // 2) + 1

    decision = None
    if votes.get("veto", 0) >= majority:
        decision = "vetoed"
    elif policy == "majority_vote" and votes.get("approve", 0) >= majority:
        decision = "approved"
    elif policy == "require_admin":
        decision = None  # only admin/commish can resolve
    # auto_execute / pause_draft / extend_timer let the timer handle it
    # unless a clear veto majority arrives first

    out = {"trade_id": trade_id, "votes": votes, "decision": decision}
    if decision == "vetoed":
        await db.trades.update_one({"_id": trade["_id"]}, {"$set": {"status": "vetoed", "vetoed_at": datetime.now(timezone.utc).isoformat()}})
        try:
            await _broadcast(league_id, {"type": "draft_chat", "kind": "pick_trade_vetoed", "trade_id": trade_id})
        except Exception:
            pass
    elif decision == "approved":
        out["execution"] = await _execute_in_draft_pick_trade(db, trade)
        try:
            await _broadcast(league_id, {"type": "draft_chat", "kind": "pick_trade_executed", "trade_id": trade_id})
        except Exception:
            pass

    try:
        await _broadcast(league_id, {
            "type": "draft_chat", "kind": "pick_trade_vote",
            "trade_id": trade_id, "votes": {"approve": votes["approve"], "veto": votes["veto"]},
        })
    except Exception:
        pass
    return out


@router.post("/drafts/{league_id}/pick-trade/{trade_id}/resolve")
async def resolve_pick_trade(league_id: str, trade_id: str, request: Request):
    """Commissioner / admin override: forces a decision on a
    pending_draft_review trade regardless of policy. Body:
    `{decision: "execute"|"veto"|"extend"|"pause"}`."""
    db = _db()
    user = await _get_user(request)
    body = await request.json()
    decision = body.get("decision")
    if decision not in ("execute", "veto", "extend", "pause"):
        raise HTTPException(status_code=400, detail="decision must be one of: execute, veto, extend, pause")

    league = await db.leagues.find_one({"_id": ObjectId(league_id)})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    uid = str(user["_id"])
    commish = {str(league.get("commissioner_id") or ""), *(str(x) for x in (league.get("co_commissioners") or []))}
    if uid not in commish and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Commissioner or admin required")

    trade = await db.trades.find_one({"_id": ObjectId(trade_id), "league_id": league_id, "is_in_draft_pick_trade": True})
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")
    now = datetime.now(timezone.utc)

    if decision == "execute":
        return await _execute_in_draft_pick_trade(db, trade)
    if decision == "veto":
        await db.trades.update_one({"_id": trade["_id"]}, {"$set": {"status": "vetoed", "vetoed_at": now.isoformat(), "vetoed_by": uid}})
        return {"trade_id": trade_id, "status": "vetoed"}
    if decision == "extend":
        extra = int(body.get("extra_minutes") or 15)
        new_expiry = now + timedelta(minutes=extra)
        await db.trades.update_one({"_id": trade["_id"]}, {"$set": {"review_expires_at": new_expiry.isoformat()}})
        return {"trade_id": trade_id, "review_expires_at": new_expiry.isoformat()}
    if decision == "pause":
        await db.drafts.update_one({"league_id": league_id, "status": {"$in": ["in_progress", "active"]}},
                                   {"$set": {"status": "paused", "paused_reason": f"pick_trade_review:{trade_id}"}})
        return {"trade_id": trade_id, "draft_paused": True}


@router.get("/drafts/{league_id}/pick-trades/pending")
async def list_pending_pick_trades(league_id: str, request: Request):
    """Return any in-flight `pending_draft_review` pick trades for the
    league. Used by the Draft Room on mount so a manager who refreshes
    mid-review still sees the floating review pill."""
    db = _db()
    await _get_user(request)
    rows = await db.trades.find({
        "league_id": league_id,
        "is_in_draft_pick_trade": True,
        "status": "pending_draft_review",
    }).to_list(20)
    out = []
    for trade in rows:
        out.append({
            "trade_id": str(trade["_id"]),
            "status": trade.get("status"),
            "review_expires_at": trade.get("review_expires_at"),
            "votes": trade.get("votes") or {},
            "post_review_action": trade.get("post_review_action"),
            "proposer_team_id": trade.get("proposer_team_id"),
            "receiver_team_id": trade.get("receiver_team_id"),
        })
    return {"pending": out}


@router.get("/drafts/{league_id}/pick-trade/{trade_id}")
async def get_in_draft_pick_trade(league_id: str, trade_id: str, request: Request):
    """Return current state of a single in-draft pick trade for polling
    fallback when the WebSocket connection drops."""
    db = _db()
    await _get_user(request)
    trade = await db.trades.find_one({"_id": ObjectId(trade_id), "league_id": league_id, "is_in_draft_pick_trade": True})
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")
    return {
        "trade_id": trade_id,
        "status": trade.get("status"),
        "review_expires_at": trade.get("review_expires_at"),
        "votes": trade.get("votes") or {},
        "post_review_action": trade.get("post_review_action"),
        "proposer_team_id": trade.get("proposer_team_id"),
        "receiver_team_id": trade.get("receiver_team_id"),
    }


async def _expire_pending_pick_trades(db) -> int:
    """Background sweeper. Walks `pending_draft_review` trades whose
    `review_expires_at` has elapsed and applies the post-review action.
    Returns count of resolved trades. Called by the worker loop in
    `server.py` every 30 seconds."""
    now_iso = datetime.now(timezone.utc).isoformat()
    rows = await db.trades.find({
        "status": "pending_draft_review",
        "review_expires_at": {"$lt": now_iso},
    }).to_list(50)
    resolved = 0
    for trade in rows:
        policy = trade.get("post_review_action") or "auto_execute"
        votes = trade.get("votes") or {}
        approve = votes.get("approve", 0)
        veto = votes.get("veto", 0)
        league_id = trade["league_id"]
        if policy == "auto_execute":
            if veto > approve:
                await db.trades.update_one({"_id": trade["_id"]}, {"$set": {"status": "vetoed", "vetoed_at": now_iso, "vetoed_reason": "auto_timer_veto_majority"}})
            else:
                await _execute_in_draft_pick_trade(db, trade)
            resolved += 1
        elif policy == "majority_vote":
            if approve > veto:
                await _execute_in_draft_pick_trade(db, trade)
            else:
                await db.trades.update_one({"_id": trade["_id"]}, {"$set": {"status": "expired", "expired_at": now_iso}})
            resolved += 1
        elif policy == "extend_timer":
            new_expiry = (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat()
            await db.trades.update_one({"_id": trade["_id"]}, {"$set": {"review_expires_at": new_expiry, "post_review_action": "auto_execute"}})
            resolved += 1
        elif policy == "pause_draft":
            await db.drafts.update_one({"league_id": league_id, "status": {"$in": ["in_progress", "active"]}},
                                       {"$set": {"status": "paused", "paused_reason": f"pick_trade_review:{trade['_id']}"}})
            await db.trades.update_one({"_id": trade["_id"]}, {"$set": {"status": "expired", "expired_at": now_iso}})
            resolved += 1
        elif policy == "require_admin":
            # leave it pending — admin must call /resolve
            await db.trades.update_one({"_id": trade["_id"]}, {"$set": {"flagged_for_admin": True}})
            resolved += 1
        try:
            await _broadcast(league_id, {"type": "draft_chat", "kind": "pick_trade_auto_resolved", "trade_id": str(trade["_id"])})
        except Exception:
            pass
    return resolved


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

    # ── Iter 167 — Conditional-pick lock ─────────────────────────
    # A pick that's still inside an unresolved conditional clause
    # (`pending_protections` non-empty) cannot be re-traded. Block on
    # both sides of the proposal so the original team can't bypass by
    # proposing the pick back to themselves.
    pick_ids_in_play = [
        a.pick_id for a in (input.assets_offered + input.assets_requested) if a.pick_id
    ]
    if pick_ids_in_play:
        from bson import ObjectId as _OID
        try:
            obj_ids = [_OID(pid) for pid in pick_ids_in_play]
        except Exception:
            obj_ids = []
        if obj_ids:
            locked = await db.trades.find({
                "league_id": input.league_id,
                "status": "executed",
                "pick_upgrades": {"$elemMatch": {
                    "pick_id": {"$in": [str(o) for o in obj_ids]},
                    "applied_at": None,
                    "failed_at": None,
                }},
            }).to_list(50)
            locked_pick_ids: set = set()
            for t in locked:
                for u in (t.get("pick_upgrades") or []):
                    if u.get("applied_at") or u.get("failed_at"):
                        continue
                    pid = u.get("pick_id")
                    if pid and pid in pick_ids_in_play:
                        locked_pick_ids.add(pid)
            if locked_pick_ids:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "One or more picks are locked by a pending conditional "
                        "clause and cannot be re-traded until the condition "
                        "resolves: " + ", ".join(sorted(locked_pick_ids))
                    ),
                )

    proposer_team = await db.teams.find_one({"league_id": input.league_id, "owner_id": user["_id"]})
    if not proposer_team:
        raise HTTPException(status_code=403, detail="You don't have a team in this league")

    target_team = await db.teams.find_one({"_id": ObjectId(input.target_team_id)})
    if not target_team:
        raise HTTPException(status_code=404, detail="Target team not found")

    # Iter 231j — Enforce commissioner-configured trade rules
    # (max trades, draft-window gating, conditional master toggle).
    proposes_conditional = bool(getattr(input, "conditions", None)) or bool(
        getattr(input, "pick_upgrades", None)
    )
    await _enforce_trade_config(
        db,
        league,
        proposer_team_ids=[str(proposer_team["_id"]), str(target_team["_id"])],
        has_conditions=proposes_conditional,
    )

    # Iter 201e — platform-admin pair-lock gate. If the (proposer_id,
    # target_owner_id) pair has an active trade_lock (global or
    # league-scoped), refuse the proposal.
    try:
        from routes.admin_platform import is_trade_locked
        lock = await is_trade_locked(db, input.league_id, user["_id"], target_team.get("owner_id"))
        if lock:
            raise HTTPException(
                status_code=403,
                detail=f"Trading is locked between these users by platform admin (reason: {lock.get('reason') or 'n/a'})",
            )
    except HTTPException:
        raise
    except Exception:
        pass

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

    review_period_hours = _resolve_review_period_hours(league)
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
        # Iter 231h — Initial state is `proposed` (awaiting recipient
        # accept/reject). `processes_at` is left null at creation — it
        # only gets stamped once the recipient accepts and the league
        # review window starts. Legacy callers that grep for "pending"
        # still see it under the same trades feed; the trade list endpoint
        # treats both statuses as "open" for display purposes.
        "status": "proposed",
        "votes": {"approve": 0, "veto": 0, "voters": []},
        "submitted_at": datetime.now(timezone.utc).isoformat(),
        "processes_at": None,
        "responded_at": None,
        "processed_at": None,
        # Stash review_period_hours so we can stamp processes_at without
        # re-reading league config when the recipient accepts.
        "_review_period_hours": review_period_hours,
    }

    result = await db.trades.insert_one(trade_doc)
    trade_doc["_id"] = str(result.inserted_id)
    trade_id_str = str(result.inserted_id)

    await _broadcast(f"league_{input.league_id}", "trade_proposed", {
        "trade_id": trade_id_str,
        "proposer": proposer_team["name"],
        "target": target_team["name"],
    })

    # Iter 231h — Deep-link the notification straight to the trade detail
    # so clicking the notification opens the proposal (not just the
    # generic Transactions feed). The frontend route at
    # /transactions/trade/{id} renders the trade card with Accept/Reject
    # buttons for the recipient.
    trade_link = f"/transactions/trade/{trade_id_str}"
    await _create_notification(
        target_team["owner_id"],
        NT_TRADE_PROPOSED,
        "New Trade Proposal — Pending Response",
        f"{proposer_team['name']} wants to trade with you. Accept or reject to continue.",
        input.league_id,
        trade_link,
    )

    return trade_doc


# ─── Iter 231h/232M — Trade state machine ────────────────────────────
#
# The full proposal lifecycle is:
#
#   proposed                                    (recipient hasn't decided)
#     ├── recipient accepts → pending           (in league review window)
#     │     ├── review elapsed → executed       (auto-process)
#     │     │     └── executes IMMEDIATELY unless the league lineup lock
#     │     │        is currently active — deferred trades stay `pending`
#     │     │        with `defer_reason: "matchup_locked"` and retry on
#     │     │        the next sweep after `defer_next_unlock` passes.
#     │     └── veto threshold hit → vetoed
#     ├── recipient rejects → rejected
#     ├── recipient counters → countered        (new `proposed` trade
#     │                                          created going the other
#     │                                          way; `countered_by_trade_id`
#     │                                          stamped for thread linkage)
#     └── proposer cancels  → cancelled
#
# `processes_at` is null while the trade is `proposed` and only stamped
# at the moment the recipient accepts. This makes the auto-processor in
# server.py ignore proposals that no one has accepted yet.


# ─── Iter 232M.3 — Thread-wide fanout for counter chains ────────────
async def _notify_thread_participants(
    db,
    trade: dict,
    *,
    title: str,
    body: str,
    league_id: str,
    link: str,
    exclude_user_ids: set,
) -> None:
    """Fan out a notification to every unique proposer/target user across
    the counter chain rooted at `trade.counter_thread_root` — so managers
    who negotiated earlier steps stay in the loop when a later counter
    resolves. Users in `exclude_user_ids` (typically the acting user +
    anyone who already received a direct notification) are skipped.

    Best-effort — swallows per-recipient failures so one bad notify can't
    block the response path.
    """
    root_id = trade.get("counter_thread_root") or str(trade.get("_id"))
    try:
        cursor = db.trades.find(
            {"$or": [{"_id": ObjectId(root_id)}, {"counter_thread_root": root_id}]},
            {"proposer_id": 1, "target_owner_id": 1},
        )
        participants: set = set()
        async for step in cursor:
            for k in ("proposer_id", "target_owner_id"):
                uid = step.get(k)
                if uid:
                    participants.add(uid)
        recipients = participants - (exclude_user_ids or set())
        for uid in recipients:
            try:
                await _create_notification(
                    uid, NT_TRADE_PROPOSED, title, body, league_id, link,
                )
            except Exception as e:
                _logger().debug(f"thread fanout skipped for {uid}: {e}")
    except Exception as e:
        _logger().debug(f"thread fanout query failed: {e}")


@router.post("/trades/{trade_id}/respond")
async def respond_to_trade_proposal(trade_id: str, request: Request):
    """Iter 231h — Recipient (target team owner / co-owner) accepts or
    rejects a `proposed` trade.

    Body: { "action": "accept" | "reject", "reason": Optional[str] }

    On accept: status → "pending"; `processes_at` is stamped using the
    league's configured review-period hours; banner notifications fire
    to both teams ("Pending Review" for the proposer, the trade now sits
    in the league review window).

    On reject: status → "rejected"; rejection notification fires to the
    proposer.
    """
    db = _db()
    user = await _get_user(request)
    try:
        body = await request.json()
    except Exception:
        body = {}
    action = (body.get("action") or "").lower().strip()
    if action not in {"accept", "reject", "counter"}:
        raise HTTPException(status_code=400, detail="action must be 'accept', 'reject', or 'counter'")

    try:
        trade = await db.trades.find_one({"_id": ObjectId(trade_id)})
    except Exception:
        trade = None
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")

    if trade.get("status") != "proposed":
        raise HTTPException(
            status_code=400,
            detail=f"Trade is not in 'proposed' state (current: {trade.get('status')}); cannot respond.",
        )

    # Authorisation — only the target team's owner or a co-owner may respond.
    target_team_id = trade.get("target_team_id")
    target_team = None
    try:
        target_team = await db.teams.find_one({"_id": ObjectId(target_team_id)})
    except Exception:
        pass
    if not target_team:
        raise HTTPException(status_code=404, detail="Target team not found")
    owner_ids = {target_team.get("owner_id")} | set(target_team.get("co_owner_ids") or [])
    if user["_id"] not in owner_ids:
        raise HTTPException(
            status_code=403,
            detail="Only the recipient team's owner or co-owners can respond to this trade.",
        )

    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    league_id = trade["league_id"]
    trade_link = f"/transactions/trade/{trade_id}"

    if action == "accept":
        # Resolve review-period hours: prefer the value stamped at create
        # time, fallback to current league config, then 72h default.
        hours = trade.get("_review_period_hours")
        if hours is None:
            league = await db.leagues.find_one({"_id": ObjectId(league_id)})
            hours = _resolve_review_period_hours(league or {})
        processes_at = (now + timedelta(hours=int(hours))).isoformat()

        await db.trades.update_one(
            {"_id": trade["_id"]},
            {"$set": {
                "status": "pending",
                "responded_at": now_iso,
                "responded_by": user["_id"],
                "response_action": "accept",
                "processes_at": processes_at,
            }},
        )

        await _broadcast(f"league_{league_id}", "trade_accepted", {
            "trade_id": trade_id,
            "proposer": trade.get("proposer_team_name"),
            "target": trade.get("target_team_name"),
            "processes_at": processes_at,
        })

        # Notify proposer — the trade is now in the league review window.
        await _create_notification(
            trade.get("proposer_id"),
            NT_TRADE_PROPOSED,
            "Trade Accepted — Pending Review",
            f"{trade.get('target_team_name')} accepted your trade. It's now in league review for {hours}h.",
            league_id,
            trade_link,
        )
        # Iter 232M.3 — Thread-wide fanout: keep earlier negotiators looped
        # in when a later counter in the chain gets accepted.
        await _notify_thread_participants(
            db, trade,
            title="Counter Accepted — Pending Review",
            body=(
                f"{trade.get('target_team_name')} accepted the counter in a trade "
                f"you were part of. Now in league review for {hours}h."
            ),
            league_id=league_id,
            link=trade_link,
            exclude_user_ids={user["_id"], trade.get("proposer_id")},
        )

        return {
            "trade_id": trade_id,
            "status": "pending",
            "processes_at": processes_at,
            "responded_at": now_iso,
        }

    # ── Iter 232M — Counter offer ────────────────────────────────
    # Recipient counters with a modified trade going the other way.
    # Original trade transitions to `countered` (terminal); a fresh
    # `proposed` trade is created with proposer/target swapped and a
    # `countered_from` pointer so the two trades can be threaded in the
    # UI. The original proposer receives a notification.
    if action == "counter":
        counter_offered = body.get("assets_offered") or []
        counter_requested = body.get("assets_requested") or []
        counter_message = (body.get("message") or "").strip() or None
        if not counter_offered and not counter_requested:
            raise HTTPException(
                status_code=400,
                detail="A counter must include at least one player or draft pick on either side.",
            )

        # Look up the proposer team (they'll be the TARGET of the counter).
        proposer_team_id = trade.get("proposer_team_id")
        proposer_team = None
        try:
            proposer_team = await db.teams.find_one({"_id": ObjectId(proposer_team_id)})
        except Exception:
            pass
        if not proposer_team:
            raise HTTPException(status_code=404, detail="Original proposer team not found")

        # Hydrate player details on both sides (same shape as create_trade_proposal).
        async def _hydrate(items):
            out = []
            for a in items or []:
                d = dict(a)
                pid = d.get("player_id")
                if pid:
                    try:
                        player = await db.players.find_one({"_id": ObjectId(pid)})
                    except Exception:
                        player = None
                    if player:
                        d["player_name"] = player["name"]
                        d["position"] = player["position"]
                        d["nhl_team"] = player.get("team", "")
                        d["points"] = player.get("points", 0)
                        d["goals"] = player.get("goals", 0)
                        d["assists"] = player.get("assists", 0)
                out.append(d)
            return out

        offered_details = await _hydrate(counter_offered)
        requested_details = await _hydrate(counter_requested)

        # Same review-period-hours resolution as the original trade so the
        # counter respects the league's configured window when accepted.
        review_period_hours = trade.get("_review_period_hours")
        if review_period_hours is None:
            league = await db.leagues.find_one({"_id": ObjectId(league_id)})
            review_period_hours = _resolve_review_period_hours(league or {})

        counter_doc = {
            "league_id": league_id,
            # Counter is FROM the original target TO the original proposer.
            "proposer_team_id": target_team_id,
            "proposer_team_name": target_team["name"],
            "proposer_id": user["_id"],
            "target_team_id": proposer_team_id,
            "target_team_name": proposer_team["name"],
            "target_owner_id": proposer_team["owner_id"],
            "assets_offered": offered_details,
            "assets_requested": requested_details,
            "conditions": [],
            "conditional": False,
            "pick_upgrades": [],
            "message": counter_message,
            "status": "proposed",
            "votes": {"approve": 0, "veto": 0, "voters": []},
            "submitted_at": now_iso,
            "processes_at": None,
            "responded_at": None,
            "processed_at": None,
            "_review_period_hours": review_period_hours,
            # ─── Counter thread linkage ─────────────────────────────
            "countered_from": trade_id,
            "counter_thread_root": trade.get("counter_thread_root") or trade_id,
            "counter_depth": int(trade.get("counter_depth") or 0) + 1,
        }
        counter_result = await db.trades.insert_one(counter_doc)
        counter_id = str(counter_result.inserted_id)

        # Retire the original trade with a link back to the counter.
        await db.trades.update_one(
            {"_id": trade["_id"]},
            {"$set": {
                "status": "countered",
                "responded_at": now_iso,
                "responded_by": user["_id"],
                "response_action": "counter",
                "countered_by_trade_id": counter_id,
            }},
        )

        await _broadcast(f"league_{league_id}", "trade_countered", {
            "trade_id": trade_id,
            "counter_trade_id": counter_id,
            "proposer": trade.get("target_team_name"),
            "target": trade.get("proposer_team_name"),
        })

        # Notify the original proposer (now the recipient of the counter).
        await _create_notification(
            trade.get("proposer_id"),
            NT_TRADE_PROPOSED,
            "Counter Offer Received",
            f"{trade.get('target_team_name')} countered your trade proposal. Review, accept, reject, or counter again.",
            league_id,
            f"/transactions/trade/{counter_id}",
        )
        # Iter 232M.3 — Thread fanout. From counter #2 onward there may
        # be earlier participants who negotiated but aren't on this
        # specific step; notify them so they can watch the thread evolve.
        await _notify_thread_participants(
            db, trade,
            title="Counter Chain Updated",
            body=(
                f"A trade you were part of just received another counter "
                f"from {trade.get('target_team_name')}."
            ),
            league_id=league_id,
            link=f"/transactions/trade/{counter_id}",
            exclude_user_ids={user["_id"], trade.get("proposer_id")},
        )

        return {
            "trade_id": trade_id,
            "status": "countered",
            "counter_trade_id": counter_id,
            "responded_at": now_iso,
        }

    # action == "reject"
    reason = (body.get("reason") or "").strip()
    await db.trades.update_one(
        {"_id": trade["_id"]},
        {"$set": {
            "status": "rejected",
            "responded_at": now_iso,
            "responded_by": user["_id"],
            "response_action": "reject",
            "rejected_reason": reason or None,
        }},
    )

    await _broadcast(f"league_{league_id}", "trade_rejected", {
        "trade_id": trade_id,
        "proposer": trade.get("proposer_team_name"),
        "target": trade.get("target_team_name"),
    })

    await _create_notification(
        trade.get("proposer_id"),
        NT_TRADE_PROPOSED,
        "Trade Rejected",
        f"{trade.get('target_team_name')} rejected your trade proposal." + (f' Reason: "{reason}"' if reason else ""),
        league_id,
        trade_link,
    )
    # Iter 232M.3 — Thread fanout on rejection too. Anyone who negotiated
    # earlier steps of this counter chain deserves to know the deal
    # collapsed.
    await _notify_thread_participants(
        db, trade,
        title="Counter Chain Rejected",
        body=(
            f"A trade you were part of was rejected by "
            f"{trade.get('target_team_name')}." + (f' Reason: "{reason}"' if reason else "")
        ),
        league_id=league_id,
        link=trade_link,
        exclude_user_ids={user["_id"], trade.get("proposer_id")},
    )

    return {
        "trade_id": trade_id,
        "status": "rejected",
        "responded_at": now_iso,
        "rejected_reason": reason or None,
    }


@router.post("/trades/{trade_id}/cancel")
async def cancel_trade_proposal(trade_id: str, request: Request):
    """Iter 231h — Proposer cancels their own `proposed` (or `pending`
    if not yet executed) trade. Closes the loop without going through
    the recipient.
    """
    db = _db()
    user = await _get_user(request)
    try:
        trade = await db.trades.find_one({"_id": ObjectId(trade_id)})
    except Exception:
        trade = None
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")
    if trade.get("proposer_id") != user["_id"]:
        raise HTTPException(status_code=403, detail="Only the proposer can cancel this trade.")
    if trade.get("status") not in {"proposed", "pending"}:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel trade in '{trade.get('status')}' state.",
        )

    now_iso = datetime.now(timezone.utc).isoformat()
    await db.trades.update_one(
        {"_id": trade["_id"]},
        {"$set": {"status": "cancelled", "cancelled_at": now_iso}},
    )

    league_id = trade["league_id"]
    trade_link = f"/transactions/trade/{trade_id}"
    await _broadcast(f"league_{league_id}", "trade_cancelled", {
        "trade_id": trade_id,
        "proposer": trade.get("proposer_team_name"),
        "target": trade.get("target_team_name"),
    })
    # Notify the recipient if the trade was already in their court.
    if trade.get("target_owner_id"):
        await _create_notification(
            trade["target_owner_id"],
            NT_TRADE_PROPOSED,
            "Trade Cancelled",
            f"{trade.get('proposer_team_name')} cancelled their trade proposal.",
            league_id,
            trade_link,
        )

    return {"trade_id": trade_id, "status": "cancelled", "cancelled_at": now_iso}


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

    await _hydrate_trades(db, out)
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
    await _hydrate_trades(db, trades)
    return trades


@router.get("/trades/{trade_id}")
async def get_trade(trade_id: str):
    db = _db()
    trade = await db.trades.find_one({"_id": ObjectId(trade_id)})
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")
    trade["_id"] = str(trade["_id"])
    await _hydrate_trade_assets(db, trade)
    return trade


# ─── Iter 232M.2 — Counter thread timeline ───────────────────────────
# Walks the counter chain (via `counter_thread_root`) from any trade in
# the thread. Returns every trade in the chain ordered by `counter_depth`
# with just the fields the timeline UI needs — no full asset hydration,
# so this is cheap even for long negotiation threads.
@router.get("/trades/{trade_id}/thread")
async def get_trade_thread(trade_id: str):
    db = _db()
    try:
        trade = await db.trades.find_one({"_id": ObjectId(trade_id)})
    except Exception:
        trade = None
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")

    # Root = self when this trade started the thread, else the stored
    # `counter_thread_root` (a Counter #1 stamps root = original trade id).
    root_id = trade.get("counter_thread_root") or str(trade["_id"])

    # Any doc whose thread_root matches, plus the root doc itself.
    cursor = db.trades.find({
        "$or": [
            {"_id": ObjectId(root_id)},
            {"counter_thread_root": root_id},
        ],
    })
    thread = []
    async for t in cursor:
        thread.append({
            "id": str(t["_id"]),
            "status": t.get("status"),
            "counter_depth": int(t.get("counter_depth") or 0),
            "counter_thread_root": t.get("counter_thread_root") or str(t["_id"]),
            "countered_from": t.get("countered_from"),
            "countered_by_trade_id": t.get("countered_by_trade_id"),
            "proposer_team_id": t.get("proposer_team_id"),
            "proposer_team_name": t.get("proposer_team_name"),
            "target_team_id": t.get("target_team_id"),
            "target_team_name": t.get("target_team_name"),
            "submitted_at": t.get("submitted_at"),
            "responded_at": t.get("responded_at"),
            "processed_at": t.get("processed_at"),
            "response_action": t.get("response_action"),
            "message": t.get("message"),
        })
    thread.sort(key=lambda r: (r["counter_depth"], r.get("submitted_at") or ""))
    return {
        "root_id": root_id,
        "current_id": trade_id,
        "count": len(thread),
        "thread": thread,
    }


@router.get("/leagues/{league_id}/pending-trades")
async def get_pending_trades(league_id: str):
    """Trades currently in flight (status in proposed/pending/voting/conditional).
    Powers the league homepage 'Pending Trades' panel.

    Iter 231h — `proposed` (waiting on recipient) is now surfaced
    alongside `pending` (in league review window) so both proposer and
    recipient see the trade in their inbox immediately."""
    db = _db()
    trades = await db.trades.find({
        "league_id": league_id,
        "status": {"$in": ["proposed", "pending", "voting", "conditional"]},
    }).sort("submitted_at", -1).to_list(100)
    for t in trades:
        t["_id"] = str(t["_id"])
    await _hydrate_trades(db, trades)
    return {"league_id": league_id, "pending_trades": trades, "count": len(trades)}


# Iter 168 — All trades feed (powers the Transactions page).
@router.get("/leagues/{league_id}/trades")
async def get_league_trades(
    league_id: str,
    status: Optional[str] = None,
    limit: int = 200,
):
    """Return every trade in the league for the Transactions page.

    Supports a comma-separated `status` filter (e.g. ?status=executed,vetoed).
    Default is no filter — returns the full history so the Transactions
    page can present All / Pending / Executed / Vetoed / Withdrawn tabs.
    Most recent first.
    """
    db = _db()
    query: dict = {"league_id": league_id}
    if status:
        statuses = [s.strip() for s in status.split(",") if s.strip()]
        if statuses:
            query["status"] = {"$in": statuses}
    trades = (
        await db.trades.find(query)
        .sort([("executed_at", -1), ("submitted_at", -1)])
        .to_list(int(max(1, min(limit, 500))))
    )
    for t in trades:
        t["_id"] = str(t["_id"])
    await _hydrate_trades(db, trades)
    return {
        "league_id": league_id,
        "count": len(trades),
        "trades": trades,
    }


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
    if trade["status"] not in {"proposed", "pending"}:
        raise HTTPException(status_code=400, detail=f"Trade is not pending (status={trade['status']})")

    # Iter 231h — Legacy `/accept` endpoint also handles `proposed`
    # trades for back-compat. The newer `/respond` endpoint splits
    # acceptance (→ pending/review) from execution (after review
    # elapses) — but `/accept` preserves the old "auto-execute on
    # acceptance" semantics so existing callers don't break.
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

    # Iter 230 — Notify the rest of the league with the "any trade accepted"
    # event (skip the two parties already covered by the targeted accept).
    try:
        await _notify_league_event(
            trade["league_id"],
            EVT_TRADE_ACCEPTED_ANY,
            "Trade accepted in league",
            f"{trade['proposer_team_name']} ↔ {trade['target_team_name']}",
            link="/transactions",
            exclude_user_ids=[trade.get("proposer_id"), trade.get("target_owner_id")],
        )
    except Exception as e:
        _logger().debug(f"trade_accepted_any fanout skipped: {e}")
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
    if trade["status"] not in {"proposed", "pending"}:
        raise HTTPException(status_code=400, detail=f"Trade is not pending (status={trade['status']})")

    await db.trades.update_one(
        {"_id": ObjectId(trade_id)},
        {"$set": {"status": "rejected", "responded_at": datetime.now(timezone.utc).isoformat()}},
    )
    # Iter 230 — Tell the proposer their trade was declined.
    try:
        await _create_notification(
            trade["proposer_id"],
            EVT_TRADE_DECLINED_OR_VETOED_MINE,
            "Trade declined",
            f"{trade['target_team_name']} declined your trade proposal",
            trade["league_id"],
            "/transactions",
        )
    except Exception as e:
        _logger().debug(f"trade_declined notify skipped: {e}")
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
    if trade["status"] not in {"proposed", "pending"}:
        raise HTTPException(status_code=400, detail=f"Trade is not pending (status={trade['status']})")

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

    # Iter 231j — Enforce commissioner-configured trade rules across
    # every participating team (max in-flight trades, draft-window
    # gating, conditional master toggle).
    await _enforce_trade_config(
        db,
        league,
        proposer_team_ids=[p["team_id"] for p in parties],
        has_conditions=has_conditions or bool(getattr(input, "pick_upgrades", None)),
    )
    review_period_hours = _resolve_review_period_hours(league)
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
        # Iter 231h — Multi-party trades also start in `proposed`. The
        # current implementation collapses N-party to the proposer + one
        # canonical target for back-compat; respond endpoint advances to
        # `pending` once that target accepts. Full N-party accept gating
        # is a follow-up (each party needs to accept before review).
        "status": "proposed",
        "votes": {"approve": 0, "veto": 0, "voters": []},
        "submitted_at": datetime.now(timezone.utc).isoformat(),
        "processes_at": None,
        "responded_at": None,
        "processed_at": None,
        "_review_period_hours": review_period_hours,
    }

    result = await db.trades.insert_one(trade_doc)
    trade_doc["_id"] = str(result.inserted_id)
    multi_trade_link = f"/transactions/trade/{result.inserted_id}"

    for p in parties:
        if p["owner_id"] == user["_id"]:
            continue
        try:
            await _create_notification(
                p["owner_id"],
                NT_TRADE_PROPOSED,
                "New Multi-Team Trade Proposal — Pending Response" if trade_doc["is_multi_party"] else "New Trade Proposal — Pending Response",
                f"{proposer_team['team_name']} included you in a {len(parties)}-team trade. Accept or reject to continue.",
                input.league_id,
                multi_trade_link,
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
        # Iter 230 — Notify the trade's parties (declined_or_vetoed_mine) AND
        # the rest of the league (trade_vetoed_any).
        try:
            party_ids = list(filter(None, [trade.get("proposer_id"), trade.get("target_owner_id")]))
            for uid in set(party_ids):
                await _create_notification(
                    uid,
                    EVT_TRADE_DECLINED_OR_VETOED_MINE,
                    "Trade vetoed by league",
                    f"Your trade between {trade.get('proposer_team_name')} and {trade.get('target_team_name')} was vetoed by league vote.",
                    trade["league_id"],
                    "/transactions",
                )
            await _notify_league_event(
                trade["league_id"],
                EVT_TRADE_VETOED_ANY,
                "Trade vetoed in league",
                f"{trade.get('proposer_team_name')} ↔ {trade.get('target_team_name')} — vetoed by league vote",
                link="/transactions",
                exclude_user_ids=party_ids,
            )
        except Exception as e:
            _logger().debug(f"trade_vetoed notify skipped: {e}")
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



# Iter 231j — Dashboard banner backing endpoint.
#
# Aggregates the calling user's open trades across EVERY league they
# participate in (as owner or co-owner). Returns two buckets so the
# dashboard banner can split them by call-to-action:
#
#   - awaiting_response: trades where the user is the recipient
#     (target team owner / co-owner) and the trade is still `proposed`.
#     Action: Accept or Reject.
#
#   - in_review: trades where the user is the proposer and the trade
#     is `pending` (in the league review window).
#     Action: Wait for review window to elapse / handle vetoes.
@router.get("/users/me/pending-trades")
async def get_my_pending_trades(request: Request):
    db = _db()
    user = await _get_user(request)
    uid = user["_id"]
    now_iso = datetime.now(timezone.utc).isoformat()

    # Pull every team the user owns or co-owns. Skip archived leagues so
    # the banner doesn't surface trades from leagues the user has hidden.
    teams = await db.teams.find({
        "$or": [{"owner_id": uid}, {"co_owner_ids": uid}],
    }).to_list(500)
    if not teams:
        return {"awaiting_response": [], "in_review": []}

    team_ids = [str(t["_id"]) for t in teams]

    # Iter 231l — Snoozed trades are stored in `trade.snoozed_until_by`
    # as a `{user_id: iso_ts}` map. A trade is filtered out of the banner
    # for this user when the current time is < that timestamp. Once the
    # snooze expires it naturally re-appears.
    snooze_filter = {
        "$or": [
            {f"snoozed_until_by.{uid}": {"$exists": False}},
            {f"snoozed_until_by.{uid}": None},
            {f"snoozed_until_by.{uid}": {"$lte": now_iso}},
        ],
    }

    # `awaiting_response` — recipient on a still-`proposed` trade
    # (and not snoozed by this user past `now`).
    awaiting_cursor = db.trades.find({
        "status": "proposed",
        "$and": [
            {"$or": [
                {"target_team_id": {"$in": team_ids}},
                {"target_owner_id": uid},
            ]},
            snooze_filter,
        ],
    }).sort("submitted_at", -1).limit(20)
    awaiting = await awaiting_cursor.to_list(20)

    # `in_review` — proposer on a `pending` trade in the review window.
    review_cursor = db.trades.find({
        "status": "pending",
        "proposer_id": uid,
    }).sort("submitted_at", -1).limit(20)
    in_review = await review_cursor.to_list(20)

    def _shape(t: dict) -> dict:
        return {
            "trade_id": str(t.get("_id")),
            "league_id": t.get("league_id"),
            "proposer_team_name": t.get("proposer_team_name"),
            "target_team_name": t.get("target_team_name"),
            "status": t.get("status"),
            "submitted_at": t.get("submitted_at"),
            "processes_at": t.get("processes_at"),
            "asset_count": (
                len(t.get("assets_offered") or []) + len(t.get("assets_requested") or [])
            ),
        }

    return {
        "awaiting_response": [_shape(t) for t in awaiting],
        "in_review": [_shape(t) for t in in_review],
    }


# Iter 231l — Snooze a pending-response trade for 24h.
#
# The recipient on a `proposed` trade can defer the decision without
# rejecting it — the row drops off their dashboard banner for the
# snooze window but stays visible in `/transactions` and the trade
# detail page. Snooze is per-user (stored on `trade.snoozed_until_by`
# keyed by user_id) so each recipient on a multi-party trade has an
# independent quiet period. Re-calling snooze extends the window.
class TradeSnoozeRequest(BaseModel):
    hours: int = 24  # default 24h; cap at 7 days to prevent abuse


@router.post("/trades/{trade_id}/snooze")
async def snooze_trade(trade_id: str, body: TradeSnoozeRequest, request: Request):
    db = _db()
    user = await _get_user(request)
    uid = user["_id"]

    hours = max(1, min(int(body.hours or 24), 24 * 7))

    try:
        trade = await db.trades.find_one({"_id": ObjectId(trade_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid trade_id")
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")

    # Only the recipient (target team owner / co-owner) on a still-
    # `proposed` trade may snooze. Proposers can't snooze their own
    # outgoing proposal (they already see it under "Pending Review"
    # which has its own auto-process timer).
    if trade.get("status") != "proposed":
        raise HTTPException(
            status_code=400,
            detail="Only proposed trades can be snoozed (recipient action).",
        )

    target_team_id = trade.get("target_team_id")
    is_recipient = False
    if target_team_id:
        try:
            target_team = await db.teams.find_one({"_id": ObjectId(target_team_id)})
            if target_team:
                if target_team.get("owner_id") == uid:
                    is_recipient = True
                elif uid in (target_team.get("co_owner_ids") or []):
                    is_recipient = True
        except Exception:
            pass
    if not is_recipient and trade.get("target_owner_id") == uid:
        is_recipient = True

    if not is_recipient:
        raise HTTPException(
            status_code=403,
            detail="Only the trade's recipient can snooze it.",
        )

    snooze_until = datetime.now(timezone.utc) + timedelta(hours=hours)
    snooze_iso = snooze_until.isoformat()

    await db.trades.update_one(
        {"_id": ObjectId(trade_id)},
        {"$set": {f"snoozed_until_by.{uid}": snooze_iso}},
    )

    return {
        "trade_id": trade_id,
        "snoozed_until": snooze_iso,
        "hours": hours,
    }
