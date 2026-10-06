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
    build_pick_player_payload,
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

# Iter 232N.27 — Reused by both manual + auto pick paths (via the
# shared draft_helpers `perform_one_auto_pick`) to stamp how long the
# manager took to pick. Returns None if we can't parse the clock
# anchor (fresh drafts before iter 230ar landed).
def _seconds_since_clock_start(draft: dict) -> int | None:
    raw = draft.get("current_pick_started_at")
    if not raw:
        return None
    try:
        started = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return int((datetime.now(timezone.utc) - started).total_seconds())
    except Exception:
        return None




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


class UndoSinglePickRequest(BaseModel):
    """Iter 232N.51 — Targeted pick-number undo (single-shot)."""
    reason: str | None = Field(
        None,
        max_length=500,
        description="Optional commissioner note stored on the audit row.",
    )
    allow_cascade: bool = Field(
        default=False,
        description=(
            "When true, undoing a pick that's NOT the most recent one also "
            "rewinds every pick AFTER it (returning them to eligible). "
            "When false (default), attempting to undo a middle pick returns "
            "409 to prevent accidental cascade rewinds."
        ),
    )


class SwapPickPlayerRequest(BaseModel):
    new_player_id: str = Field(..., description="Mongo ObjectId of the replacement player.")


# ─── Endpoints ────────────────────────────────────────────────────


from services.financial_lock import serialize_finances
from services.draft_salary import validate_selection, warning, entry, after_pick
from services.draft_mutation import commit_pick, recover

@router.post("/drafts/{draft_id}/pick")
@serialize_finances(_db)
async def make_draft_pick(draft_id: str, input: MakeDraftPickRequest, request: Request):
    user = await _get_user(request)
    await recover(_db(), draft_id)

    draft = await _db().drafts.find_one({"_id": ObjectId(draft_id)})
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")

    if draft["status"] != "active":
        raise HTTPException(status_code=400, detail="Draft is not active")

    if input.expected_pick is not None and input.expected_pick != draft["current_pick"]:
        raise HTTPException(409, "Draft turn changed; refresh before selecting")

    # Iter 170g — abbr derivation aligned with the draft's stored team_map.
    team = await _db().teams.find_one({"league_id": draft["league_id"], "owner_id": user["_id"]})
    on_clock = get_team_for_pick(draft["team_abbrs"], draft["current_pick"], draft["snake_draft"], draft.get("bonus_picks"))
    on_clock_team_id = (draft.get("team_map") or {}).get(on_clock, {}).get("id")

    # Iter 232x — Honor traded picks: check draft_picks for current owner
    # Query by (round, original_team_id) which is stable across snake drafts.
    _total_teams = len(draft["team_abbrs"])
    _cur_pick = draft["current_pick"]
    _rnd = ((_cur_pick - 1) // _total_teams) + 1
    if on_clock_team_id:
        _traded = await _db().draft_picks.find_one({
            "league_id": draft.get("league_id"),
            "draft_id": str(draft["_id"]),
            "round": _rnd,
            "original_team_id": on_clock_team_id,
        })
        if not _traded:
            _traded = await _db().draft_picks.find_one({
                "league_id": draft.get("league_id"),
                "round": _rnd,
                "original_team_id": on_clock_team_id,
            })
        if _traded and _traded.get("current_team_id"):
            _traded_tid = str(_traded["current_team_id"])
            if _traded_tid != str(_traded.get("original_team_id")):
                on_clock_team_id = _traded_tid
                _traded_team = await _db().teams.find_one({"_id": ObjectId(_traded_tid)})
                if _traded_team:
                    on_clock = _traded_team.get("abbreviation") or _traded_team.get("name", on_clock)

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

    receiving_team = await _db().teams.find_one({"_id": ObjectId(on_clock_team_id)})
    salary_result, salary_ctx = await validate_selection(_db(), draft, receiving_team, input.player_id, input.destination)

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
        "player": build_pick_player_payload(player),
        "picked_by": user["_id"],
        "salary_validation": salary_result,
        "destination": salary_result["destination"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        # Iter 232N.27 — Stamp how long the manager took vs the clock
        # start so the leaderboard can compute avg pick time + spotlight
        # the "slow-poke" / "speed demon" categories.
        "time_taken_seconds": _seconds_since_clock_start(draft),
    }

    next_pick = current_pick + 1
    # Iter 232i — Total picks now includes any commissioner-granted
    # bonus picks (compensation / expansion) so the "draft complete"
    # transition doesn't fire early when extras are layered on top of
    # the standard rounds × teams grid.
    total_picks = draft["total_rounds"] * total_teams + len(draft.get("bonus_picks") or [])
    new_status = "completed" if next_pick > total_picks else "active"

    await commit_pick(_db(), draft, receiving_team, pick_doc, {**salary_ctx["team"].get("lineup", {}), input.player_id: entry(salary_result["destination"])}, new_status)

    # Iter 170g — also push the picked player onto the on-clock team's
    # roster so the Roster page + My Roster tile in the Draft Room both
    # reflect the pick without a separate manual step. Idempotent via
    # `$addToSet`.
    if on_clock_team_id:
        # ── Historical scoring: log draft pick ───────────────────
        try:
            from utils.scoring_roster import log_roster_change
            _league = await _db().leagues.find_one({"_id": ObjectId(draft.get("league_id") or "")}, {"current_week": 1})
            _week = int((_league or {}).get("current_week") or 1)
            await log_roster_change(_db(), team_id=on_clock_team_id,
                league_id=draft.get("league_id", ""),
                player_id=str(player["_id"]), action="add", source="draft", week=_week,
                metadata={"draft_id": draft_id})
        except Exception:
            pass

    await _broadcast(f"draft_{draft_id}", "draft_pick", {
        **pick_doc,
        "next_pick": next_pick,
        "on_the_clock": get_team_for_pick(draft["team_abbrs"], next_pick, draft["snake_draft"], draft.get("bonus_picks")) if new_status == "active" else None,
        "draft_complete": new_status == "completed",
    })

    # Iter 232N.27 — Draft-complete Speed Demon XP bonus.
    if new_status == "completed":
        try:
            from utils.xp import award_draft_completion_bonuses
            await award_draft_completion_bonuses(
                _db(),
                draft_id=draft_id,
                broadcast_fn=_deps.get("broadcast_to_room"),
            )
        except Exception as ex:
            logger.debug(f"draft_speed_champion award skipped (manual pick): {ex}")

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
                future_abbr = get_team_for_pick(draft["team_abbrs"], future_pick, draft["snake_draft"], draft.get("bonus_picks"))
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

    await after_pick(_db(), draft, receiving_team, salary_result, new_status == "completed")
    return pick_doc


# ─── Iter 170h — Commissioner powers: undo picks + swap picked player ─


@router.post("/drafts/{draft_id}/undo")
@serialize_finances(_db)
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
            # ── Ownership tracking (undo pick) ───────────────────
            try:
                from utils.scoring_roster import log_roster_change
                await log_roster_change(_db(), team_id=tid,
                    league_id=draft.get("league_id", ""),
                    player_id=pid, action="remove", source="admin",
                    metadata={"reason": "undo_picks"})
            except Exception:
                pass

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
            f"on the clock returns to {get_team_for_pick(draft['team_abbrs'], new_current, draft['snake_draft'], draft.get('bonus_picks'))}"
        ),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    await _db().drafts.update_one({"_id": ObjectId(draft_id)}, {"$push": {"chat_messages": msg}})
    await _broadcast(f"draft_{draft_id}", "draft_chat", msg)
    await _broadcast(f"draft_{draft_id}", "draft_undo", {
        "count": count,
        "removed_overalls": [p.get("overall") for p in removed],
        "current_pick": new_current,
        "on_the_clock": get_team_for_pick(draft["team_abbrs"], new_current, draft["snake_draft"], draft.get("bonus_picks")),
    })
    return {
        "undone": count,
        "current_pick": new_current,
        "on_the_clock": get_team_for_pick(draft["team_abbrs"], new_current, draft["snake_draft"], draft.get("bonus_picks")),
    }


# ─── Iter 232N.51 — Targeted single-pick undo with audit persistence ───


@router.post("/drafts/{draft_id}/picks/{pick_number}/undo")
@serialize_finances(_db)
async def undo_specific_pick(
    draft_id: str,
    pick_number: int,
    payload: UndoSinglePickRequest,
    request: Request,
):
    """Commissioner-only: atomically undo a specific pick by its
    `overall` number.

    Semantics:
      • Verifies caller is commissioner / co-commissioner / platform admin.
      • Finds the pick in `draft.picks` by `overall == pick_number`.
      • If the pick is the MOST RECENT (i.e. every later overall is empty),
        undoes it cleanly: pulls the drafted player from the team's
        roster, removes the pick from `draft.picks`, clears the matching
        `draft_picks` collection row (so the Draft Board grid reflects
        an unassigned slot again), rewinds `current_pick` to the undone
        number, resets `current_pick_started_at` to now, posts a
        `System` chat message, broadcasts `draft_undo`, and writes a
        row to `draft_undo_audit`.
      • If the pick is NOT the most recent, returns 409 unless the
        request opts in via `allow_cascade=true`, in which case every
        pick with `overall >= pick_number` is undone in reverse order.

    Superset of `POST /drafts/{draft_id}/undo` — the older count-based
    route stays for backward compat but this route is the one to call
    from admin UIs going forward.
    """
    user = await _get_user(request)
    draft = await _db().drafts.find_one({"_id": ObjectId(draft_id)})
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    league = await _db().leagues.find_one({"_id": ObjectId(draft["league_id"])})
    if not is_league_admin(user, league):
        raise HTTPException(
            status_code=403,
            detail="Only commissioner / co-commissioner / admin can undo picks",
        )

    picks = list(draft.get("picks", []))
    if not picks:
        raise HTTPException(status_code=400, detail="No picks to undo in this draft")

    # `pick_number` refers to the `overall` field (1-based across the
    # whole draft). Find it and detect if any LATER picks exist.
    target_idx = next(
        (i for i, p in enumerate(picks) if int(p.get("overall") or 0) == pick_number),
        -1,
    )
    if target_idx == -1:
        raise HTTPException(status_code=404, detail=f"Pick #{pick_number} not found")

    # Determine the range of picks to undo. If the target pick is the
    # last one in the array (or all subsequent picks have empty
    # player_id), we cleanly undo just this one. Otherwise the caller
    # must opt in to `allow_cascade` because rolling back a mid-draft
    # pick removes every pick after it.
    picks_after_target = [p for p in picks[target_idx + 1:] if p.get("player_id")]
    if picks_after_target and not payload.allow_cascade:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Pick #{pick_number} is not the most recent pick "
                f"({len(picks_after_target)} pick(s) made after it). "
                "Pass `allow_cascade=true` to also undo those later picks."
            ),
        )

    # Everything from target onwards gets rewound.
    removed = picks[target_idx:]
    kept = picks[:target_idx]

    # ── 1) Pull drafted players off their teams' rosters ─────────
    for p in removed:
        tid = p.get("team_id") or (draft.get("team_map") or {}).get(
            p.get("team", ""), {}
        ).get("id")
        pid = p.get("player_id")
        if tid and pid:
            try:
                await _db().teams.update_one(
                    {"_id": ObjectId(tid)},
                    {"$pull": {"roster": pid}},
                )
                # ── Ownership tracking (undo specific pick) ──────
                from utils.scoring_roster import log_roster_change
                await log_roster_change(_db(), team_id=tid,
                    league_id=draft.get("league_id", ""),
                    player_id=pid, action="remove", source="admin",
                    metadata={"reason": "undo_specific_pick"})
            except Exception as e:
                logger.warning(f"undo_specific_pick roster pull failed for {tid}/{pid}: {e}")

    # ── 2) Clear the matching draft_picks collection rows so the ──
    #       Draft Board grid stops rendering these slots as filled.
    #       We ONLY touch fields set by pick execution — pre-seeded
    #       columns (round/pick_in_round/team_abbr/pick_number) stay.
    removed_overalls = [int(p.get("overall")) for p in removed if p.get("overall") is not None]
    if removed_overalls:
        try:
            await _db().draft_picks.update_many(
                {
                    "draft_id": draft_id,
                    "pick_number": {"$in": removed_overalls},
                },
                {"$set": {
                    "player_id": None,
                    "player_name": None,
                    "player_position": None,
                    "nhl_team": None,
                    "picked_at": None,
                    "auto_picked": False,
                    "auto_pick_via": None,
                }},
            )
        except Exception as e:
            logger.warning(f"undo_specific_pick draft_picks reset failed: {e}")

    # ── 3) Rewind the on-the-clock pointer to the undone pick ─
    new_current = pick_number
    new_status = "active" if draft.get("draft_started") else draft.get("status", "scheduled")
    if draft.get("status") == "completed":
        new_status = "active"
    now = datetime.now(timezone.utc)

    await _db().drafts.update_one(
        {"_id": ObjectId(draft_id)},
        {"$set": {
            "picks": kept,
            "current_pick": new_current,
            "status": new_status,
            "current_pick_started_at": now.isoformat(),
        }},
    )

    # ── 4) Audit trail — searchable log of every undo, so nobody has
    #       to grep worker logs to understand why a pick vanished.
    on_the_clock_after = get_team_for_pick(
        draft["team_abbrs"],
        new_current,
        draft.get("snake_draft", True),
        draft.get("bonus_picks"),
    )
    try:
        await _db().draft_undo_audit.insert_one({
            "draft_id": draft_id,
            "league_id": draft.get("league_id"),
            "pick_number": pick_number,
            "cascade": bool(picks_after_target),
            "removed_count": len(removed),
            "removed_picks": removed,
            "commissioner_id": user.get("_id"),
            "commissioner_name": user.get("name") or user.get("email"),
            "reason": (payload.reason or None),
            "undone_at": now.isoformat(),
            "on_the_clock_after": on_the_clock_after,
        })
    except Exception as e:
        logger.warning(f"undo_specific_pick audit insert failed: {e}")

    # ── 5) System chat message so managers see the rollback ───────
    commish_name = user.get("name") or user.get("email") or "Commissioner"
    if len(removed) == 1:
        text = (
            f"{commish_name} undid pick #{pick_number} — "
            f"{on_the_clock_after} is back on the clock."
        )
    else:
        text = (
            f"{commish_name} undid pick #{pick_number} and the "
            f"{len(removed) - 1} pick(s) after it — {on_the_clock_after} "
            "is back on the clock."
        )
    if payload.reason:
        text += f' (reason: "{payload.reason}")'
    msg = {
        "id": f"undo-{now.timestamp()}",
        "type": "pick",
        "sender": "System",
        "text": text,
        "timestamp": now.isoformat(),
    }
    await _db().drafts.update_one(
        {"_id": ObjectId(draft_id)},
        {"$push": {"chat_messages": msg}},
    )

    # ── 6) Real-time broadcast so open Draft Rooms rerender live ──
    await _broadcast(f"draft_{draft_id}", "draft_chat", msg)
    await _broadcast(f"draft_{draft_id}", "draft_undo", {
        "pick_number": pick_number,
        "cascade": bool(picks_after_target),
        "removed_count": len(removed),
        "removed_overalls": removed_overalls,
        "current_pick": new_current,
        "on_the_clock": on_the_clock_after,
    })

    return {
        "ok": True,
        "pick_number": pick_number,
        "removed_count": len(removed),
        "cascade": bool(picks_after_target),
        "current_pick": new_current,
        "on_the_clock": on_the_clock_after,
        "clock_reset_at": now.isoformat(),
    }



@router.patch("/drafts/{draft_id}/picks/{overall}")
@serialize_finances(_db)
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
    replacement_team = await _db().teams.find_one({"_id": ObjectId(tid)})
    replacement_team = {**replacement_team, "roster": [pid for pid in replacement_team.get("roster") or [] if pid != old_player_id],
        "lineup": {pid: value for pid, value in (replacement_team.get("lineup") or {}).items() if pid != old_player_id}}
    replacement_result, replacement_ctx = await validate_selection(_db(), {**draft, "picks": [p for p in picks if p.get("overall") != overall]}, replacement_team, payload.new_player_id, old_pick.get("destination"))
    if tid and old_player_id:
        await _db().teams.update_one(
            {"_id": ObjectId(tid)},
            {"$pull": {"roster": old_player_id}},
        )
        # ── Ownership tracking (swap — remove old) ───────────────
        try:
            from utils.scoring_roster import log_roster_change
            await log_roster_change(_db(), team_id=tid,
                league_id=draft.get("league_id", ""),
                player_id=old_player_id, action="remove", source="admin",
                metadata={"reason": "draft_swap_out"})
        except Exception:
            pass
    if tid:
        await _db().teams.update_one(
            {"_id": ObjectId(tid)},
            {"$addToSet": {"roster": str(new_player["_id"])}, "$set": {"lineup": {
                **replacement_ctx["team"].get("lineup", {}), str(new_player["_id"]): entry(replacement_result["destination"])}}},
        )
        # ── Ownership tracking (swap — add new) ──────────────────
        try:
            from utils.scoring_roster import log_roster_change
            await log_roster_change(_db(), team_id=tid,
                league_id=draft.get("league_id", ""),
                player_id=str(new_player["_id"]), action="add", source="admin",
                metadata={"reason": "draft_swap_in"})
        except Exception:
            pass

    picks[target_idx] = {
        **old_pick,
        "player_id": str(new_player["_id"]),
        "player": build_pick_player_payload(new_player),
        "swapped_at": datetime.now(timezone.utc).isoformat(),
        "swapped_by": user["_id"],
        "salary_validation": replacement_result,
        "destination": replacement_result["destination"],
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
