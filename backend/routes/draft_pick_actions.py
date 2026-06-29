"""Draft pick actions router — extracted from `routes/drafts.py` (iter 231m).

Owns the per-pick mutation endpoints for live drafts:

  • POST  /api/drafts/{draft_id}/pick                   — record a pick
  • POST  /api/drafts/{draft_id}/undo                   — commissioner undo
  • PATCH /api/drafts/{draft_id}/picks/{overall}        — commissioner swap
  • POST  /api/drafts/{draft_id}/pause                  — commissioner pause
  • POST  /api/drafts/{draft_id}/seed-picks             — retroactive seeding

The shared helpers `perform_one_auto_pick`, `seed_draft_picks_for_draft`,
`early_start_clock_msg` live in `routes/draft_helpers.py` (extracted in
iter 231n) and are imported plainly here. Iter 231m used a late-binding
workaround because the helpers were still inside drafts.py; iter 231n
removed that smell by moving them to a dedicated module.

Wired via the `setup(deps)` injection pattern; see `server.py`.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

# Pure helpers / models that live elsewhere; safe to import at module load.
from draft_engine import MakeDraftPickRequest, get_team_for_pick
# Iter 231n — Direct (non-late-bound) imports of the cross-module helpers.
from routes.draft_helpers import (
    early_start_clock_msg,
    seed_draft_picks_for_draft,
)
# Iter 231ad — Shared `is_league_admin` helper (commish OR co-commish OR
# platform admin). Replaces 5 inline copies of the same check that
# previously lived in this file.
from routes._authz import is_league_admin


router = APIRouter()
_deps: dict = {}
logger = logging.getLogger(__name__)


def setup(deps: dict) -> None:
    _deps.update(deps)


def _db():
    return _deps["db"]


async def _get_user(request: Request):
    return await _deps["get_current_user"](request)


async def _broadcast(room: str, event: str, payload: dict):
    fn = _deps.get("broadcast_to_room")
    if fn is None:
        return None
    return await fn(room, event, payload)


async def _create_notification(*args, **kwargs):
    """Delegates to `routes.drafts.create_notification` (the live impl)
    via the dep injection map so we get the same retry / debounce policy."""
    fn = _deps.get("create_notification")
    if fn is None:
        return None
    return await fn(*args, **kwargs)


# ─── Request models ───────────────────────────────────────────────


class UndoDraftPicksRequest(BaseModel):
    count: int = Field(default=1, ge=1, le=50, description="How many of the most recent picks to undo.")


class SwapPickPlayerRequest(BaseModel):
    new_player_id: str = Field(..., description="Mongo ObjectId of the replacement player.")


# ─── Endpoints ────────────────────────────────────────────────────


@router.post("/drafts/{draft_id}/pick")
async def make_draft_pick(draft_id: str, input: MakeDraftPickRequest, request: Request):
    user = await _get_user(request)

    draft = await _db().drafts.find_one({"_id": ObjectId(draft_id)})
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")

    if draft["status"] != "active":
        raise HTTPException(status_code=400, detail="Draft is not active")

    # Iter 170g — abbr derivation aligned with the draft's stored team_map.
    team = await _db().teams.find_one({"league_id": draft["league_id"], "owner_id": user["_id"]})
    on_clock = get_team_for_pick(draft["team_abbrs"], draft["current_pick"], draft["snake_draft"])
    on_clock_team_id = (draft.get("team_map") or {}).get(on_clock, {}).get("id")

    # Commissioner / co-commissioner / platform admin can pick for any team,
    # otherwise it must be the user's turn.
    # Iter 231ad — Pulled the role check into `routes._authz.is_league_admin`.
    league = await _db().leagues.find_one({"_id": ObjectId(draft["league_id"])})
    is_admin = is_league_admin(user, league)

    if not is_admin:
        if not team:
            raise HTTPException(status_code=403, detail="You don't have a team in this league")
        if str(team["_id"]) != on_clock_team_id:
            raise HTTPException(status_code=403, detail=f"Not your turn. {on_clock} is on the clock.")

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
        "team_id": on_clock_team_id,
        "player_id": str(player["_id"]),
        "player": {
            "id": str(player["_id"]),
            "name": player["name"],
            "position": player["position"],
            "nhlTeam": player.get("team", ""),
            "team_name": player.get("team_name", ""),
            "pts": player.get("points", 0),
            "g": player.get("goals", 0),
            "a": player.get("assists", 0),
            "gp": player.get("games_played", 0),
            "league": "NHL",
            "headshot": (
                f"https://assets.nhle.com/mugs/nhl/20252026/{player.get('team', 'NHL')}/{player.get('nhl_id', '')}.png"
                if player.get("nhl_id") else None
            ),
        },
        "picked_by": user["_id"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    next_pick = current_pick + 1
    total_picks = draft["total_rounds"] * total_teams
    new_status = "completed" if next_pick > total_picks else "active"

    await _db().drafts.update_one(
        {"_id": ObjectId(draft_id)},
        {
            "$push": {"picks": pick_doc},
            "$set": {
                "current_pick": next_pick,
                "status": new_status,
                # Iter 230ar — server-authoritative remaining time anchor.
                "current_pick_started_at": datetime.now(timezone.utc).isoformat(),
            },
        },
    )

    # Iter 170g — also push the picked player onto the on-clock team's
    # roster so the Roster page + My Roster tile in the Draft Room both
    # reflect the pick without a separate manual step. Idempotent via
    # `$addToSet`.
    if on_clock_team_id:
        await _db().teams.update_one(
            {"_id": ObjectId(on_clock_team_id)},
            {"$addToSet": {"roster": str(player["_id"])}},
        )

    await _broadcast(f"draft_{draft_id}", "draft_pick", {
        **pick_doc,
        "next_pick": next_pick,
        "on_the_clock": get_team_for_pick(draft["team_abbrs"], next_pick, draft["snake_draft"]) if new_status == "active" else None,
        "draft_complete": new_status == "completed",
    })

    # Iter 230an — System chat message FIRST so the EVT_DRAFT_PICK_MADE
    # body can reference it without the try/except swallowing the entire
    # block (including on-deck / coming-up notifications).
    pick_msg = {
        "id": f"pick-{current_pick}",
        "type": "pick",
        "sender": "System",
        "text": f"Pick #{current_pick} (Rd {round_num}, Pick {pick_in_round}): {on_clock} selects {player['name']} ({player['position']})",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    await _db().drafts.update_one({"_id": ObjectId(draft_id)}, {"$push": {"chat_messages": pick_msg}})
    await _broadcast(f"draft_{draft_id}", "draft_chat", pick_msg)

    # Iter 230 — In-app notifications for draft events.
    try:
        from routes.notification_events import (
            EVT_DRAFT_PICK_MADE,
            EVT_DRAFT_YOUR_TURN,
            EVT_DRAFT_ON_DECK,
            EVT_DRAFT_COMING_UP,
        )
        league_id_str = str(draft["league_id"])
        all_team_docs = await _db().teams.find(
            {"league_id": league_id_str},
            {"_id": 1, "owner_id": 1, "co_owner_ids": 1, "name": 1},
        ).to_list(200)
        team_by_id = {str(t["_id"]): t for t in all_team_docs}

        def _owners(team_doc: dict) -> list:
            out: list = []
            if team_doc.get("owner_id"):
                out.append(team_doc["owner_id"])
            for co in (team_doc.get("co_owner_ids") or []):
                if co:
                    out.append(co)
            return out

        # 1. "Any pick made" fanout (default OFF in user prefs).
        for t in all_team_docs:
            for uid in _owners(t):
                await _create_notification(
                    uid,
                    EVT_DRAFT_PICK_MADE,
                    "Draft pick made",
                    pick_msg["text"],
                    league_id_str,
                    "/draft-room",
                )

        # 2. Look ahead — next 5 picks; notify their owners with
        #    progressively-targeted events (turn → on deck → coming up).
        if new_status == "active":
            # Iter 230y — Append clock-activation hint to "your turn"
            # body when running in early-start / no-clock mode.
            early_clock_hint = await early_start_clock_msg(draft)
            for offset in range(0, 5):
                future_pick = next_pick + offset
                if future_pick > total_picks:
                    break
                future_abbr = get_team_for_pick(draft["team_abbrs"], future_pick, draft["snake_draft"])
                future_team_id = (draft.get("team_map") or {}).get(future_abbr, {}).get("id")
                future_team = team_by_id.get(future_team_id) if future_team_id else None
                if not future_team:
                    continue
                if offset == 0:
                    event = EVT_DRAFT_YOUR_TURN
                    title = "You're on the clock!"
                    body = f"Pick #{future_pick} — make your selection." + early_clock_hint
                elif offset == 1:
                    event = EVT_DRAFT_ON_DECK
                    title = "You're on deck"
                    body = f"Your pick (#{future_pick}) is up next."
                else:
                    event = EVT_DRAFT_COMING_UP
                    title = f"Your pick is in {offset} picks"
                    body = f"Pick #{future_pick} is coming up — get your queue ready."
                for uid in _owners(future_team):
                    await _create_notification(
                        uid,
                        event,
                        title,
                        body,
                        league_id_str,
                        "/draft-room",
                    )
    except Exception as e:
        logger.debug(f"draft pick notifications skipped: {e}")

    if new_status == "completed":
        complete_msg = {
            "id": "sys-complete",
            "type": "pick",
            "sender": "System",
            "text": "Draft is complete! All picks have been made.",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        await _db().drafts.update_one({"_id": ObjectId(draft_id)}, {"$push": {"chat_messages": complete_msg}})
        await _broadcast(f"draft_{draft_id}", "draft_chat", complete_msg)
        await _broadcast(f"draft_{draft_id}", "draft_completed", {"draft_id": draft_id})

        # Iter 218 — Auto-snapshot every team in the league after draft completes.
        try:
            draft_doc = await _db().drafts.find_one({"_id": ObjectId(draft_id)})
            if draft_doc:
                league_id = draft_doc.get("league_id")
                team_ids = [str(t["_id"]) async for t in _db().teams.find(
                    {"league_id": str(league_id)}, {"_id": 1}
                )]
                if team_ids:
                    from services.auto_snapshot import auto_snapshot
                    await auto_snapshot(_db(), team_ids,
                                        trigger="draft_complete",
                                        metadata={"draft_id": draft_id,
                                                  "league_id": str(league_id)})
        except Exception:
            pass  # snapshot failure must never block draft completion

    return pick_doc


# ─── Iter 170h — Commissioner powers: undo picks + swap picked player ─


@router.post("/drafts/{draft_id}/undo")
async def undo_draft_picks(draft_id: str, payload: UndoDraftPicksRequest, request: Request):
    """Commissioner-only: rewind the draft by N picks. Removes the
    drafted players from the picking team's roster and broadcasts the
    undo so connected managers see the rollback live."""
    user = await _get_user(request)
    draft = await _db().drafts.find_one({"_id": ObjectId(draft_id)})
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    league = await _db().leagues.find_one({"_id": ObjectId(draft["league_id"])})
    # Iter 231ad — Shared helper.
    if not is_league_admin(user, league):
        raise HTTPException(status_code=403, detail="Only commissioner / co-commissioner / admin can undo picks")

    picks = list(draft.get("picks", []))
    if not picks:
        raise HTTPException(status_code=400, detail="No picks to undo")
    count = min(payload.count, len(picks))
    removed = picks[-count:]
    kept = picks[:-count]

    for p in removed:
        tid = p.get("team_id") or (draft.get("team_map") or {}).get(p.get("team", ""), {}).get("id")
        pid = p.get("player_id")
        if tid and pid:
            await _db().teams.update_one(
                {"_id": ObjectId(tid)},
                {"$pull": {"roster": pid}},
            )

    new_current = max(1, draft.get("current_pick", 1) - count)
    new_status = "active" if draft.get("draft_started") else draft.get("status", "scheduled")
    if draft.get("status") == "completed":
        new_status = "active"

    await _db().drafts.update_one(
        {"_id": ObjectId(draft_id)},
        {"$set": {
            "picks": kept,
            "current_pick": new_current,
            "status": new_status,
            # Iter 230ar — Reset per-pick clock anchor on undo.
            "current_pick_started_at": datetime.now(timezone.utc).isoformat(),
        }},
    )

    msg = {
        "id": f"undo-{datetime.now(timezone.utc).timestamp()}",
        "type": "pick",
        "sender": "System",
        "text": (
            f"Commissioner undid {count} pick{'s' if count != 1 else ''} — "
            f"on the clock returns to {get_team_for_pick(draft['team_abbrs'], new_current, draft['snake_draft'])}"
        ),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    await _db().drafts.update_one({"_id": ObjectId(draft_id)}, {"$push": {"chat_messages": msg}})
    await _broadcast(f"draft_{draft_id}", "draft_chat", msg)
    await _broadcast(f"draft_{draft_id}", "draft_undo", {
        "count": count,
        "removed_overalls": [p.get("overall") for p in removed],
        "current_pick": new_current,
        "on_the_clock": get_team_for_pick(draft["team_abbrs"], new_current, draft["snake_draft"]),
    })
    return {
        "undone": count,
        "current_pick": new_current,
        "on_the_clock": get_team_for_pick(draft["team_abbrs"], new_current, draft["snake_draft"]),
    }


@router.patch("/drafts/{draft_id}/picks/{overall}")
async def swap_pick_player(draft_id: str, overall: int, payload: SwapPickPlayerRequest, request: Request):
    """Commissioner-only: replace the player on an existing pick.

    Use case: a mis-typed pick or a mid-draft correction. The previously
    drafted player is removed from the team's roster and the new player
    is added. Other picks + the on-the-clock pointer are unchanged.
    """
    user = await _get_user(request)
    draft = await _db().drafts.find_one({"_id": ObjectId(draft_id)})
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    league = await _db().leagues.find_one({"_id": ObjectId(draft["league_id"])})
    # Iter 231ad — Shared helper.
    if not is_league_admin(user, league):
        raise HTTPException(status_code=403, detail="Only commissioner / co-commissioner / admin can swap pick players")

    picks = list(draft.get("picks", []))
    target_idx = next((i for i, p in enumerate(picks) if p.get("overall") == overall), -1)
    if target_idx == -1:
        raise HTTPException(status_code=404, detail=f"Pick #{overall} not found")

    old_pick = picks[target_idx]
    new_player = await _db().players.find_one({"_id": ObjectId(payload.new_player_id)})
    if not new_player:
        raise HTTPException(status_code=404, detail="Replacement player not found")
    if any(p.get("player_id") == payload.new_player_id and p.get("overall") != overall for p in picks):
        raise HTTPException(status_code=400, detail="Replacement player is already drafted on another pick")

    tid = old_pick.get("team_id") or (draft.get("team_map") or {}).get(old_pick.get("team", ""), {}).get("id")
    old_player_id = old_pick.get("player_id")
    if tid and old_player_id:
        await _db().teams.update_one(
            {"_id": ObjectId(tid)},
            {"$pull": {"roster": old_player_id}},
        )
    if tid:
        await _db().teams.update_one(
            {"_id": ObjectId(tid)},
            {"$addToSet": {"roster": str(new_player["_id"])}},
        )

    picks[target_idx] = {
        **old_pick,
        "player_id": str(new_player["_id"]),
        "player": {
            "id": str(new_player["_id"]),
            "name": new_player["name"],
            "position": new_player["position"],
            "nhlTeam": new_player.get("team", ""),
            "team_name": new_player.get("team_name", ""),
            "pts": new_player.get("points", 0),
            "g": new_player.get("goals", 0),
            "a": new_player.get("assists", 0),
            "gp": new_player.get("games_played", 0),
            "league": "NHL",
            "headshot": (
                f"https://assets.nhle.com/mugs/nhl/20252026/{new_player.get('team', 'NHL')}/{new_player.get('nhl_id', '')}.png"
                if new_player.get("nhl_id") else None
            ),
        },
        "swapped_at": datetime.now(timezone.utc).isoformat(),
        "swapped_by": user["_id"],
    }
    await _db().drafts.update_one(
        {"_id": ObjectId(draft_id)},
        {"$set": {"picks": picks}},
    )
    msg = {
        "id": f"swap-{datetime.now(timezone.utc).timestamp()}",
        "type": "pick",
        "sender": "System",
        "text": (
            f"Commissioner swapped pick #{overall} ({old_pick.get('team', '')}): "
            f"{old_pick.get('player', {}).get('name', 'Unknown')} → {new_player['name']}"
        ),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    await _db().drafts.update_one({"_id": ObjectId(draft_id)}, {"$push": {"chat_messages": msg}})
    await _broadcast(f"draft_{draft_id}", "draft_chat", msg)
    await _broadcast(f"draft_{draft_id}", "draft_pick_swapped", {
        "overall": overall,
        "pick": picks[target_idx],
        "previous_player_id": old_player_id,
    })
    return {"overall": overall, "pick": picks[target_idx]}


@router.post("/drafts/{draft_id}/pause")
async def pause_draft(draft_id: str, request: Request):
    """Toggle the draft timer pause. Commissioner-only."""
    user = await _get_user(request)
    draft = await _db().drafts.find_one({"_id": ObjectId(draft_id)})
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")

    league = await _db().leagues.find_one({"_id": ObjectId(draft["league_id"])})
    # Iter 231ad — Shared helper.
    if not is_league_admin(user, league):
        raise HTTPException(status_code=403, detail="Only commissioner / co-commissioner / admin can pause draft")

    paused = not draft.get("timer_paused", False)
    await _db().drafts.update_one({"_id": ObjectId(draft_id)}, {"$set": {"timer_paused": paused}})

    await _broadcast(f"draft_{draft_id}", "draft_timer_toggle", {"paused": paused})
    return {"paused": paused}


# ─── Iter 228i — Retroactive pick seeding for pre-iter228h drafts ──


@router.post("/drafts/{draft_id}/seed-picks")
async def seed_draft_picks(draft_id: str, request: Request):
    """Commissioner-only: materialise draft_picks rows for an existing
    draft. Useful when a draft was created with `pick_trading_enabled`
    BEFORE iter228h shipped the auto-gen logic, so the picks weren't
    populated and the trade-center inventory is empty.

    Idempotent — calls `_seed_draft_picks_for_draft` which skips rows
    that already exist on `(league_id, year, round, original_team_id)`.
    """
    user = await _get_user(request)
    try:
        draft = await _db().drafts.find_one({"_id": ObjectId(draft_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid draft_id")
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")

    league = await _db().leagues.find_one({"_id": ObjectId(draft["league_id"])})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    # Iter 231ad — Shared helper.
    if not is_league_admin(user, league):
        raise HTTPException(status_code=403, detail="Commissioner or admin only")

    season = (league.get("season") or "2026").split("-")[0]
    inserted = await seed_draft_picks_for_draft(
        draft_id=draft_id,
        league_id=draft["league_id"],
        rounds=int(draft.get("total_rounds") or 1),
        year=int(season),
    )
    return {
        "draft_id": draft_id,
        "league_id": draft["league_id"],
        "picks_inserted": inserted,
        "message": (
            f"Inserted {inserted} draft pick(s)" if inserted
            else "All picks already exist (idempotent re-run)"
        ),
    }
