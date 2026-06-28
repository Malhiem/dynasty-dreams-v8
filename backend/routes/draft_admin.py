"""Draft admin router — extracted from `routes/drafts.py` (iter 231t).

Owns the four CRUD endpoints commissioners use to manage drafts:

  • POST   /api/drafts              — create_draft
  • DELETE /api/drafts/{draft_id}   — delete_draft (soft archive)
  • POST   /api/drafts/{draft_id}/restore — restore_draft (within 15-day window)
  • PATCH  /api/drafts/{draft_id}   — patch_draft (edit metadata)

These four endpoints cluster naturally — same auth (commissioner/admin),
same audit-row pattern (admin_user_actions), same broadcast targets,
and they all mutate the same `drafts` collection. Pulling them out
ratchets drafts.py down past the <1200 line target while keeping
read-only and lifecycle (start/auto-init/auto-pick) endpoints in their
own modules.

Cross-module helpers:
  • `seed_draft_picks_for_draft` from `routes/draft_helpers.py` for
    auto-seeding pick rows on create + total_rounds growth on patch.
  • `_abbrs_with_dedup` from `routes/drafts.py` (lazy import inside the
    helper to avoid a server→drafts→admin→drafts module-load cycle).
  • `create_notification` resolved via `_deps["create_notification"]`
    for the EVT_DRAFT_SCHEDULED notification on create.

Wired via the `setup(deps)` injection pattern in `server.py`.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Request

from draft_engine import CreateDraftRequest
from routes.draft_helpers import seed_draft_picks_for_draft


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
    """Delegates to drafts.create_notification via the dep map."""
    fn = _deps.get("create_notification")
    if fn is None:
        return None
    return await fn(*args, **kwargs)


def _abbrs_with_dedup(teams):
    """Lazy re-bind of the helper in drafts.py — avoids server →
    drafts → draft_admin → drafts cycle at module load."""
    from routes.drafts import _abbrs_with_dedup as _impl
    return _impl(teams)


# ─── POST /drafts ──────────────────────────────────────────────────────


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
    # Iter 170g — abbr derivation aligned with frontend (`logo_abbr` +
    # dedup) so the Draft Room board renders the same column keys the
    # backend stores against `picks.team` and broadcasts as
    # `on_the_clock`.
    team_abbrs, team_map = _abbrs_with_dedup(teams)

    scheduled = None
    if input.scheduled_time:
        scheduled = input.scheduled_time

    # Iter 228d — soft-validate total_rounds against the league's actual
    # roster capacity (active + bench + minors) so a typo doesn't create
    # a 100-round draft. Cap silently at the larger of the configured
    # roster_size or 30 to keep legacy small-league behaviour intact.
    roster_cap = int(league.get("roster_spots") or 0) \
        + int(league.get("bench_spots") or 0) \
        + int(league.get("minors_spots") or 0)
    effective_max = max(roster_cap, 30)
    if input.total_rounds > effective_max:
        raise HTTPException(
            status_code=422,
            detail=(
                f"total_rounds ({input.total_rounds}) exceeds the league's "
                f"roster capacity ({effective_max}). Reduce rounds or increase "
                "roster spots."
            ),
        )

    # Iter 228h — When pick trading is enabled AND the window opens
    # immediately, generate the draft_picks rows so all teams see them
    # in the trade center / draft board right away. Without this the
    # commissioner has to manually call /admin/seed/draft-picks.
    pick_trading_enabled = bool(getattr(input, "pick_trading_enabled", False))
    trading_window_opens = str(getattr(input, "trading_window_opens", "immediately") or "immediately")

    draft_doc = {
        "league_id": input.league_id,
        "league_name": league["name"],
        # Iter 228d — name persisted on create (was being dropped, so the
        # Scheduled Drafts list always rendered "Untitled Draft").
        "name": (input.name or "").strip() or f"{league['name']} Draft",
        "draft_type": input.draft_type,
        "scheduled_time": scheduled,
        # Iter 228h — Timezone for the clock-starts / clock-stops fields
        "clock_timezone": getattr(input, "clock_timezone", None) or league.get("timezone") or "UTC",
        "clock_starts_at": getattr(input, "clock_starts_at", None),
        "clock_stops_at": getattr(input, "clock_stops_at", None),
        "total_rounds": input.total_rounds,
        "time_per_pick": input.time_per_pick,
        "round_time_overrides": input.round_time_overrides or [],
        "snake_draft": input.snake_draft,
        "player_criteria": input.player_criteria,
        "missed_pick_action": input.missed_pick_action,
        "defer_user_options": input.defer_user_options or [],
        "window_elapsed_actions": input.window_elapsed_actions or [],
        "pick_trading_enabled": pick_trading_enabled,
        "trading_window_opens": trading_window_opens,
        # Iter 228n — Eligibility filters (see CreateDraftRequest).
        "exclude_previously_drafted": bool(getattr(input, "exclude_previously_drafted", False)),
        "minors_eligibility_required": bool(getattr(input, "minors_eligibility_required", False)),
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

    # Iter 228h — Generate draft_picks rows when trading window is
    # already open. If the order isn't set yet, default to alphabetical
    # team ordering so the picks have a deterministic slot. The order
    # can be reshuffled later by saving the DraftOrderConfigCard.
    if pick_trading_enabled and trading_window_opens == "immediately":
        try:
            inserted = await seed_draft_picks_for_draft(
                draft_id=str(result.inserted_id),
                league_id=input.league_id,
                rounds=input.total_rounds,
                year=int((league.get("season") or "2026").split("-")[0]),
            )
            draft_doc["picks_generated"] = inserted
        except Exception as ex:
            logger.warning(
                f"Failed to auto-generate draft picks for {result.inserted_id}: {ex}")
            draft_doc["picks_generated"] = 0

    # Iter 230 — Notify the league that a draft has been scheduled.
    try:
        from routes.notification_events import EVT_DRAFT_SCHEDULED
        teams_for_notif = await _db().teams.find(
            {"league_id": input.league_id},
            {"owner_id": 1, "co_owner_ids": 1},
        ).to_list(200)
        recipients: set = set()
        for t in teams_for_notif:
            if t.get("owner_id"):
                recipients.add(t["owner_id"])
            for co in (t.get("co_owner_ids") or []):
                if co:
                    recipients.add(co)
        when_str = scheduled or "TBD"
        draft_label = input.name or f"{input.draft_type or 'Draft'}"
        for uid in recipients:
            await _create_notification(
                uid,
                EVT_DRAFT_SCHEDULED,
                "Draft scheduled",
                f"{draft_label} — {when_str}",
                input.league_id,
                "/draft-room",
            )
    except Exception as e:
        logger.debug(f"draft_scheduled notify skipped: {e}")

    return draft_doc


# ─── DELETE /drafts/{draft_id} ─────────────────────────────────────────


@router.delete("/drafts/{draft_id}")
async def delete_draft(draft_id: str, request: Request):
    """Iter 228d — Soft-delete a scheduled draft. Commissioner only.

    Marks the draft `status="archived"` + stamps `archived_at`. A
    background sweeper hard-deletes archived drafts after 15 days
    (recoverable until then via the admin UI).
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
    is_commish = (
        league.get("commissioner_id") == user["_id"]
        or user["_id"] in (league.get("co_commissioners") or [])
        or user.get("role") == "admin"
    )
    if not is_commish:
        raise HTTPException(status_code=403, detail="Commissioner or admin only")

    if draft.get("status") in ("in_progress", "completed"):
        raise HTTPException(
            status_code=400,
            detail=f"Can't archive a draft that's already {draft['status']}.",
        )

    now_iso = datetime.now(timezone.utc).isoformat()
    await _db().drafts.update_one(
        {"_id": ObjectId(draft_id)},
        {"$set": {
            "status": "archived",
            "archived_at": now_iso,
            "archived_by": user["_id"],
        }},
    )

    # Iter 228l — Audit row so the History drawer in the admin panel
    # can show "Archived by {commissioner} at {timestamp}" alongside
    # subsequent admin purge/restore entries.
    await _db().admin_user_actions.insert_one({
        "admin_id": str(user["_id"]),
        "admin_email": user.get("email"),
        "admin_tier": user.get("permission_tier") or user.get("role") or "commissioner",
        "target_user_id": league.get("commissioner_id"),
        "action": "draft_archive",
        "reason": "Commissioner soft-deleted a scheduled draft (15-day recovery window)",
        "metadata": {
            "draft_id": draft_id,
            "draft_name": draft.get("name"),
            "league_id": draft.get("league_id"),
            "league_name": draft.get("league_name"),
            "total_rounds": draft.get("total_rounds"),
            "scheduled_time": draft.get("scheduled_time"),
        },
        "prior_state": {"status": draft.get("status")},
        "mocked": False,
        "ts": now_iso,
    })

    return {"draft_id": draft_id, "status": "archived", "archived_at": now_iso}


# ─── POST /drafts/{draft_id}/restore ───────────────────────────────────


@router.post("/drafts/{draft_id}/restore")
async def restore_draft(draft_id: str, request: Request):
    """Iter 228d — Restore a soft-deleted draft (within 15-day window)."""
    user = await _get_user(request)
    try:
        draft = await _db().drafts.find_one({"_id": ObjectId(draft_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid draft_id")
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    if draft.get("status") != "archived":
        raise HTTPException(status_code=400, detail="Draft is not archived")

    league = await _db().leagues.find_one({"_id": ObjectId(draft["league_id"])})
    is_commish = (
        league and (
            league.get("commissioner_id") == user["_id"]
            or user["_id"] in (league.get("co_commissioners") or [])
            or user.get("role") == "admin"
        )
    )
    if not is_commish:
        raise HTTPException(status_code=403, detail="Commissioner or admin only")

    await _db().drafts.update_one(
        {"_id": ObjectId(draft_id)},
        {"$set": {"status": "scheduled"},
         "$unset": {"archived_at": "", "archived_by": ""}},
    )

    # Iter 228l — Audit row mirrors the admin restore endpoint so the
    # History drawer covers BOTH commissioner-initiated and admin-
    # initiated restores in a single timeline.
    await _db().admin_user_actions.insert_one({
        "admin_id": str(user["_id"]),
        "admin_email": user.get("email"),
        "admin_tier": user.get("permission_tier") or user.get("role") or "commissioner",
        "target_user_id": (league or {}).get("commissioner_id"),
        "action": "draft_restore",
        "reason": "Commissioner restored archived draft within the 15-day window",
        "metadata": {
            "draft_id": draft_id,
            "draft_name": draft.get("name"),
            "league_id": draft.get("league_id"),
            "league_name": draft.get("league_name"),
        },
        "prior_state": {
            "status": "archived",
            "archived_at": draft.get("archived_at"),
        },
        "mocked": False,
        "ts": datetime.now(timezone.utc).isoformat(),
    })

    return {"draft_id": draft_id, "status": "scheduled"}


# ─── PATCH /drafts/{draft_id} ──────────────────────────────────────────


@router.patch("/drafts/{draft_id}")
async def patch_draft(draft_id: str, body: dict, request: Request):
    """Iter 228n — Edit a scheduled draft.

    Commissioners (and admins) can correct draft metadata while the
    draft is still `status="scheduled"`. Active/completed/archived
    drafts are immutable here to preserve integrity (use the dedicated
    pick-swap / restore endpoints for those flows).

    Whitelisted editable fields: name, scheduled_time, total_rounds,
    time_per_pick, missed_pick_action, defer_user_options, draft_type,
    snake_draft, player_criteria, exclude_previously_drafted,
    minors_eligibility_required, round_time_overrides.
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
    is_commish = (
        league.get("commissioner_id") == user["_id"]
        or user["_id"] in (league.get("co_commissioners") or [])
        or user.get("role") == "admin"
    )
    if not is_commish:
        raise HTTPException(status_code=403, detail="Commissioner or admin only")

    if draft.get("status") != "scheduled":
        raise HTTPException(
            status_code=400,
            detail=f"Only scheduled drafts can be edited (this draft is '{draft.get('status')}').",
        )

    EDITABLE = {
        "name", "scheduled_time", "total_rounds", "time_per_pick",
        "missed_pick_action", "defer_user_options", "draft_type",
        "snake_draft", "player_criteria", "round_time_overrides",
        # Iter 228n — New eligibility filters surfaced in the create-draft
        # form. Editing them here lets commissioners correct mid-stride
        # before the draft starts.
        "exclude_previously_drafted", "minors_eligibility_required",
    }
    update: dict = {}
    for k, v in (body or {}).items():
        if k in EDITABLE:
            update[k] = v
    if not update:
        raise HTTPException(status_code=400, detail="No editable fields supplied")

    # Range checks
    if "total_rounds" in update:
        try:
            tr = int(update["total_rounds"])
            if not (1 <= tr <= 100):
                raise ValueError()
            update["total_rounds"] = tr
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="total_rounds must be an int 1-100")
    if "time_per_pick" in update:
        try:
            tpp = int(update["time_per_pick"])
            if not (30 <= tpp <= 86400):
                raise ValueError()
            update["time_per_pick"] = tpp
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="time_per_pick must be 30-86400 seconds")

    await _db().drafts.update_one(
        {"_id": ObjectId(draft_id)}, {"$set": update}
    )

    # Iter 228p — Sync the `draft_picks` collection when total_rounds
    # changes. Previously the draft document picked up the new count
    # but the per-team Roster Draft Picks card stayed stale (root cause
    # of "edited # of picks but they didn't reduce on roster").
    if "total_rounds" in update:
        old_rounds = int(draft.get("total_rounds") or 0)
        new_rounds = int(update["total_rounds"])
        try:
            if new_rounds > old_rounds:
                # Grow: seed extra rows. `seed_draft_picks_for_draft`
                # is idempotent on (league_id, year, round, original_team_id)
                # so reseeding will only insert the missing rounds.
                season = str(league.get("season") or "2026").split("-")[0]
                await seed_draft_picks_for_draft(
                    draft_id=draft_id,
                    league_id=draft["league_id"],
                    rounds=new_rounds,
                    year=int(season),
                )
            elif new_rounds < old_rounds:
                # Shrink: drop pick rows for rounds > new_rounds, but
                # protect any pick that's been traded or used (has
                # `trade_history` entries or is referenced in a pick).
                # Scheduled drafts shouldn't have used picks, but
                # trade activity may have happened on future-round picks.
                doomed = await _db().draft_picks.find({
                    "draft_id": draft_id,
                    "round": {"$gt": new_rounds},
                }, {"_id": 1, "round": 1, "trade_history": 1}).to_list(2000)
                deletable_ids = [
                    p["_id"] for p in doomed
                    if not (p.get("trade_history") or [])
                ]
                if deletable_ids:
                    await _db().draft_picks.delete_many({
                        "_id": {"$in": deletable_ids},
                    })
        except Exception as ex:
            logger.warning(
                f"Failed to sync draft_picks for {draft_id} on total_rounds change: {ex}")

    fresh = await _db().drafts.find_one({"_id": ObjectId(draft_id)}, {"team_map": 0})
    fresh["_id"] = str(fresh["_id"])

    # Broadcast so connected Draft Room clients refresh in real time.
    # Iter 228q — Also broadcast to the league-wide channel so the
    # Rosters page (which doesn't know the active draft_id) refreshes
    # its TeamDraftPicks card on every commissioner edit.
    try:
        await _broadcast(
            f"draft_{draft_id}",
            "draft_edited",
            {"draft_id": draft_id, "fields": list(update.keys())},
        )
        await _broadcast(
            f"league_{draft['league_id']}",
            "draft_edited",
            {
                "draft_id": draft_id,
                "league_id": draft["league_id"],
                "fields": list(update.keys()),
            },
        )
    except Exception:
        pass

    return {"draft": fresh, "updated_fields": list(update.keys())}


# ─── POST /drafts/{draft_id}/restart ───────────────────────────────────


@router.post("/drafts/{draft_id}/restart")
async def restart_draft(draft_id: str, request: Request):
    """Iter 231ab — Hard reset an active or completed draft.

    Wipes all picks, removes the drafted players from every team's
    roster, resets `current_pick` to 1, and flips status back to
    `scheduled`. Commissioner / co-commissioner / platform-admin only.

    Use case: the league wants to redo the draft (e.g. mid-night
    auto-pick storm, owner disputes, test data cleanup). Trade-history
    on per-pick rows is preserved — those rows continue to exist in
    `draft_picks` so trade audit stays intact.
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
    is_admin = (
        league.get("commissioner_id") == user["_id"]
        or user["_id"] in (league.get("co_commissioners") or [])
        or user.get("role") == "admin"
    )
    if not is_admin:
        raise HTTPException(status_code=403, detail="Commissioner / co-commissioner / admin only")

    if draft.get("status") == "archived":
        raise HTTPException(
            status_code=400,
            detail="Restore the draft first before restarting it.",
        )

    # Wipe every drafted player off each team's roster.
    picks = list(draft.get("picks") or [])
    for p in picks:
        tid = p.get("team_id") or (draft.get("team_map") or {}).get(p.get("team", ""), {}).get("id")
        pid = p.get("player_id")
        if tid and pid:
            try:
                await _db().teams.update_one(
                    {"_id": ObjectId(tid)},
                    {"$pull": {"roster": pid}},
                )
            except Exception:
                pass  # roster cleanup is best-effort

    now_iso = datetime.now(timezone.utc).isoformat()
    await _db().drafts.update_one(
        {"_id": ObjectId(draft_id)},
        {
            "$set": {
                "status": "scheduled",
                "draft_started": False,
                "early_start": False,
                "timer_paused": False,
                "current_pick": 1,
                "picks": [],
                "chat_messages": [],
                "restarted_at": now_iso,
                "restarted_by": user["_id"],
            },
            "$unset": {"current_pick_started_at": "", "started_at": ""},
        },
    )

    # Audit trail row.
    await _db().admin_user_actions.insert_one({
        "admin_id": str(user["_id"]),
        "admin_email": user.get("email"),
        "admin_tier": user.get("permission_tier") or user.get("role") or "commissioner",
        "target_user_id": league.get("commissioner_id"),
        "action": "draft_restart",
        "reason": "Commissioner hard-reset the draft (wiped picks + rosters).",
        "metadata": {
            "draft_id": draft_id,
            "draft_name": draft.get("name"),
            "league_id": draft.get("league_id"),
            "league_name": draft.get("league_name"),
            "picks_wiped": len(picks),
        },
        "prior_state": {
            "status": draft.get("status"),
            "current_pick": draft.get("current_pick"),
        },
        "mocked": False,
        "ts": now_iso,
    })

    # Broadcast so all connected Draft Room clients refresh and the UI
    # flips back to its pre-draft countdown state.
    try:
        await _broadcast(
            f"draft_{draft_id}",
            "draft_restarted",
            {
                "draft_id": draft_id,
                "picks_wiped": len(picks),
                "restarted_at": now_iso,
            },
        )
    except Exception:
        pass

    return {
        "draft_id": draft_id,
        "status": "scheduled",
        "picks_wiped": len(picks),
        "restarted_at": now_iso,
    }
