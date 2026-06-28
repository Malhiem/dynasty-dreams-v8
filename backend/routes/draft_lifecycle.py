"""Draft lifecycle router — extracted from `routes/drafts.py` (iter 231r).

Owns the draft activation flow:

  • POST /api/drafts/auto-init/{league_id}    — preview or materialise
  • POST /api/drafts/{draft_id}/start         — flip scheduled → active
  • POST /api/drafts/{draft_id}/auto-pick     — timer rollover endpoint

These three endpoints share the same set of deps (auth, db, broadcast,
send_email, seed_draft_picks, early_start_clock_msg, perform_one_auto_pick,
create_notification) so they cluster naturally into one module.

The cross-module helpers `perform_one_auto_pick`, `seed_draft_picks_for_draft`,
`early_start_clock_msg` live in `routes/draft_helpers.py` (iter 231n). The
team-abbr derivation helpers `_abbrs_with_dedup` + `_derive_team_abbr` are
still in `routes/drafts.py` because they're consumed by `create_draft` +
`patch_draft` (not yet extracted); we import them from there to avoid
duplicating the implementation.

Wired via the `setup(deps)` injection pattern; see `server.py`.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Request

from routes.draft_helpers import (
    early_start_clock_msg,
    perform_one_auto_pick,
    seed_draft_picks_for_draft,
)


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


def _send_email(to_email: str, subject: str, html_content: str) -> dict:
    fn = _deps.get("send_sendgrid_email")
    if not fn:
        return {"status": "skipped", "reason": "send_sendgrid_email not injected"}
    try:
        return fn(to_email, subject, html_content)
    except Exception as e:
        logger.debug(f"_send_email failed for {to_email}: {e}")
        return {"status": "error", "error": str(e)}


async def _create_notification(*args, **kwargs):
    """Delegates to `routes.drafts.create_notification` via the dep map."""
    fn = _deps.get("create_notification")
    if fn is None:
        return None
    return await fn(*args, **kwargs)


def _abbrs_with_dedup(teams):
    """Local re-bind of the helper in drafts.py — avoids a top-level
    `from routes.drafts import _abbrs_with_dedup` cycle at module load."""
    from routes.drafts import _abbrs_with_dedup as _impl
    return _impl(teams)


# ─── POST /drafts/auto-init/{league_id} ────────────────────────────────


@router.post("/drafts/auto-init/{league_id}")
async def auto_init_draft(league_id: str, request: Request, commit: bool = False):
    """Initialise (or fetch) the league's draft.

    Iter 231 — `commit=False` (the default) returns a **preview** shape
    WITHOUT persisting to the database. The preview carries the league's
    current team_map + roster-cap-derived `total_rounds`, but `_id` is
    `None` and the response is tagged `preview: True`. This lets the
    Draft Room render correctly on first load WITHOUT creating an empty
    stub draft every time a commissioner clicks into the page.

    `commit=True` (the legacy behaviour) materialises the draft into
    `db.drafts` and runs the pick-seed safety net. The frontend
    triggers `commit=True` only when the user takes an explicit action
    (clicking *Start Draft* or *Schedule Draft*). Existing drafts are
    always returned as-is regardless of the flag — the heal-and-return
    fast path is unchanged.
    """
    user = await _get_user(request)
    league = await _db().leagues.find_one({"_id": ObjectId(league_id)})
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    is_comm = league["commissioner_id"] == user["_id"]
    co_comms = league.get("co_commissioners", []) or []
    if not (is_comm or user["_id"] in co_comms):
        raise HTTPException(status_code=403, detail="Only commissioners can auto-init drafts")

    # Iter 228k — Derive total_rounds from the league's roster capacity
    # (active + bench + minors) so the Draft Board renders the full
    # roster height instead of the legacy default of 5.
    roster_cap = (
        int(league.get("roster_spots") or 0)
        + int(league.get("bench_spots") or 0)
        + int(league.get("minors_spots") or 0)
    )
    default_rounds = roster_cap if roster_cap > 0 else 5

    # Iter 231f — Bug fix: previously this looked up "any" draft for the
    # league, including ARCHIVED ones. That let the auto-init flow re-
    # surface a deleted draft (the user "thought" they had cleaned up),
    # and downstream start_draft happily flipped it back to `active`. We
    # now strictly exclude archived rows so the existing-draft fast path
    # only returns live drafts. The rogue resurrection bug is fully
    # guarded by `test_iter231f_archived_draft_guards.py`.
    existing = await _db().drafts.find_one(
        {
            "league_id": league_id,
            "status": {"$ne": "archived"},
        },
        sort=[("created_at", -1)],
    )
    if existing:
        existing_draft_id = str(existing["_id"])
        # Iter 228k — Heal legacy drafts that were auto-init'd with the
        # old `total_rounds=5` default. Only bumps when no picks have
        # been made yet (preserving in-progress drafts) and the roster
        # cap is meaningfully larger than the stored value.
        if (
            not existing.get("picks")
            and roster_cap > 0
            and int(existing.get("total_rounds") or 0) < roster_cap
            and existing.get("status") != "active"
        ):
            await _db().drafts.update_one(
                {"_id": existing["_id"]},
                {"$set": {"total_rounds": roster_cap}},
            )
            existing["total_rounds"] = roster_cap

        # Iter 228k — Auto-seed safety net. When the draft exists but
        # the `draft_picks` collection has zero rows for this league, run
        # the seed-picks helper transparently so the Draft Board /
        # Trade Center are never blank after a commissioner opens the
        # Draft Room. Broadcast so already-connected clients refresh.
        existing_picks_count = await _db().draft_picks.count_documents({
            "league_id": league_id,
        })
        if existing_picks_count == 0:
            try:
                season = str(league.get("season") or "2026").split("-")[0]
                inserted = await seed_draft_picks_for_draft(
                    draft_id=existing_draft_id,
                    league_id=league_id,
                    rounds=int(existing.get("total_rounds") or default_rounds),
                    year=int(season),
                )
                if inserted > 0:
                    await _broadcast(
                        f"draft_{existing_draft_id}",
                        "draft_picks_seeded",
                        {
                            "draft_id": existing_draft_id,
                            "league_id": league_id,
                            "picks_inserted": inserted,
                        },
                    )
            except Exception:
                # Seeding is best-effort; never block the Draft Room load.
                pass

        existing["_id"] = existing_draft_id
        existing.pop("team_map", None)
        # Iter 173 — Surface the league's minors_enabled flag so the Draft
        # Room can render a "Minor-eligible" affordance on prospects.
        existing["league_minors_enabled"] = bool(league.get("minors_enabled"))
        return {"draft": existing, "created": False}

    teams = await _db().teams.find({"league_id": league_id}).to_list(100)
    if not teams:
        raise HTTPException(status_code=400, detail="League has no teams")
    team_abbrs, team_map = _abbrs_with_dedup(teams)

    # Iter 231 — Preview mode: return the would-be draft shape WITHOUT
    # writing to the database. The Draft Room uses this to render a
    # placeholder board so commissioners can see what their draft will
    # look like before scheduling. No `_id` is issued — the frontend
    # detects `preview: true` and disables pick / start actions until a
    # commissioner materialises the draft (commit=true).
    if not commit:
        preview_doc = {
            "_id": None,
            "league_id": league_id,
            "league_name": league.get("name"),
            "draft_type": "snake",
            "scheduled_time": None,
            "total_rounds": default_rounds,
            "time_per_pick": 120,
            "snake_draft": True,
            "player_criteria": "open",
            "missed_pick_action": "skip",
            "current_pick": 1,
            "status": "preview",
            "draft_started": False,
            "early_start": False,
            "timer_paused": False,
            "team_abbrs": team_abbrs,
            "picks": [],
            "chat_messages": [],
            "league_minors_enabled": bool(league.get("minors_enabled")),
        }
        return {"draft": preview_doc, "created": False, "preview": True}

    draft_doc = {
        "league_id": league_id,
        "league_name": league.get("name"),
        "draft_type": "snake",
        "scheduled_time": None,
        "total_rounds": default_rounds,
        "time_per_pick": 120,
        "snake_draft": True,
        "player_criteria": "open",  # Iter 170n — the players collection
        # currently holds NHL-active players only (no prospect pool). The
        # default reflects what the data supports; once a prospect pool
        # is seeded, this can switch back to "entry" + filter
        # eligible-players accordingly.
        "missed_pick_action": "skip",
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
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    res = await _db().drafts.insert_one(draft_doc)
    new_draft_id = str(res.inserted_id)
    draft_doc["_id"] = new_draft_id
    draft_doc.pop("team_map", None)
    # Iter 173 — surface league minors_enabled for the Draft Room badges.
    draft_doc["league_minors_enabled"] = bool(league.get("minors_enabled"))

    # Iter 228k — Auto-seed the freshly-created draft so the trade center
    # and Draft Board have rows immediately.
    try:
        season = str(league.get("season") or "2026").split("-")[0]
        inserted = await seed_draft_picks_for_draft(
            draft_id=new_draft_id,
            league_id=league_id,
            rounds=default_rounds,
            year=int(season),
        )
        if inserted > 0:
            await _broadcast(
                f"draft_{new_draft_id}",
                "draft_picks_seeded",
                {
                    "draft_id": new_draft_id,
                    "league_id": league_id,
                    "picks_inserted": inserted,
                },
            )
    except Exception:
        pass

    return {"draft": draft_doc, "created": True}


# ─── POST /drafts/{draft_id}/start ─────────────────────────────────────


@router.post("/drafts/{draft_id}/start")
async def start_draft(draft_id: str, request: Request, early_start: bool = False):
    user = await _get_user(request)

    draft = await _db().drafts.find_one({"_id": ObjectId(draft_id)})
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")

    league = await _db().leagues.find_one({"_id": ObjectId(draft["league_id"])})
    is_commissioner = league["commissioner_id"] == user["_id"]

    # Iter 231f — Bug fix: previously start_draft happily activated
    # archived drafts because there was no status guard. Combined with
    # the auto_init_draft bug (which returned archived drafts as the
    # "existing" draft), this caused chriszarek's deleted Ice Kings H2H
    # E2E test draft to resurrect itself on 2026-06-26. We now reject
    # archived drafts at the start endpoint as a defense-in-depth check
    # — even if a caller somehow obtains the archived draft id, /start
    # will refuse to activate it.
    if draft.get("status") == "archived":
        raise HTTPException(
            status_code=400,
            detail="This draft has been archived. Restore it first if you need to start it again.",
        )

    # Iter 230an — Idempotency: if the draft is already active, return
    # success rather than 400. Multiple managers / browser tabs hitting
    # the auto-start endpoint at the same moment is normal — the first
    # one wins; the rest get a no-op response.
    if draft["status"] == "active":
        return {"message": "Draft already active", "early_start": draft.get("early_start", False), "already_active": True}

    # Iter 230an — Allow auto-start (non-commissioner trigger) ONLY when
    # the scheduled time has elapsed. The frontend countdown hook calls
    # this once the clock hits 0:00 so any team's manager (or
    # commissioner, or a background worker) can boot the draft without
    # the league owner needing to be online. Commissioners can always
    # start at any time.
    if not is_commissioner:
        scheduled_at = draft.get("scheduled_time")
        if not scheduled_at:
            raise HTTPException(status_code=403, detail="Only commissioner can start draft")
        try:
            from datetime import datetime as _dt
            sched_dt = _dt.fromisoformat(str(scheduled_at).replace("Z", "+00:00"))
            if sched_dt.tzinfo is None:
                sched_dt = sched_dt.replace(tzinfo=timezone.utc)
        except Exception:
            raise HTTPException(status_code=403, detail="Only commissioner can start draft")
        if sched_dt > datetime.now(timezone.utc):
            raise HTTPException(status_code=403, detail="Draft scheduled time has not yet arrived")

    # Iter 230an — Refresh team_abbrs / team_map from the CURRENT set of
    # league teams. Drafts created before all teams joined the league
    # had stale abbr lists (e.g. TFHL's Inaugural Draft had only HC
    # populated even after 24 teams joined). Re-derive on start so the
    # draft proceeds with the right team set.
    fresh_teams = await _db().teams.find({"league_id": draft["league_id"]}).to_list(200)
    if fresh_teams and len(fresh_teams) > len(draft.get("team_abbrs") or []):
        team_abbrs, team_map = _abbrs_with_dedup(fresh_teams)
    else:
        team_abbrs = draft.get("team_abbrs") or []
        team_map = draft.get("team_map") or {}

    update = {
        "$set": {
            "status": "active",
            "draft_started": True,
            "early_start": early_start,
            "current_pick": 1,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "current_pick_started_at": datetime.now(timezone.utc).isoformat(),
            "team_abbrs": team_abbrs,
            "team_map": team_map,
        }
    }
    await _db().drafts.update_one({"_id": ObjectId(draft_id)}, update)

    # Broadcast draft start
    await _broadcast(f"draft_{draft_id}", "draft_started", {
        "draft_id": draft_id,
        "early_start": early_start,
        "team_abbrs": team_abbrs,
        "on_the_clock": team_abbrs[0] if team_abbrs else None
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

    # Iter 230y / 230an — Notify pick #1 (on the clock) and pick #2
    # (on deck) the moment the draft starts. Previously this was gated
    # behind `if early_start:` so a normal clock-started draft fired
    # ZERO notifications until the first pick was made — leaving the
    # first manager unaware they were up. Now ALWAYS notify the first
    # two picks; the body adapts to early-start (clock-activation hint)
    # vs. timer-started (standard "you're on the clock") via the
    # `early_start_clock_msg` helper which returns "" for non-early.
    try:
        from routes.notification_events import EVT_DRAFT_YOUR_TURN, EVT_DRAFT_ON_DECK
        updated_draft = await _db().drafts.find_one({"_id": ObjectId(draft_id)})
        clock_hint = await early_start_clock_msg(updated_draft or draft)
        team_abbrs = (updated_draft or draft).get("team_abbrs") or []
        team_map = (updated_draft or draft).get("team_map") or {}
        league_name = (updated_draft or draft).get("league_name") or ""
        draft_name = (updated_draft or draft).get("name") or "your draft"
        league_id_str = str(draft["league_id"])

        # Iter 230aj — Notify BOTH pick #1 (your turn) AND pick #2 (on
        # deck) the moment the draft boots up.
        picks_to_notify = [
            (EVT_DRAFT_YOUR_TURN, 1, "You're on the clock!",   "Pick #1 — make your selection."),
            (EVT_DRAFT_ON_DECK,   2, "On deck",                 "Pick #2 — you're up next."),
        ]
        for (event, pick_no, title, body_prefix) in picks_to_notify:
            if pick_no > len(team_abbrs):
                continue  # tiny league — skip whichever notify is OOB.
            abbr = team_abbrs[pick_no - 1]
            team_id = (team_map.get(abbr) or {}).get("id")
            if not team_id:
                continue
            team_doc = await _db().teams.find_one(
                {"_id": ObjectId(team_id)},
                {"owner_id": 1, "co_owner_ids": 1, "name": 1},
            )
            if not team_doc:
                continue
            owners = [team_doc.get("owner_id")] + list(team_doc.get("co_owner_ids") or [])
            body_text = body_prefix + clock_hint
            for uid in [u for u in owners if u]:
                await _create_notification(
                    uid, event, title, body_text, league_id_str, "/draft-room",
                )
                # Iter 230ab — Email pipe (only for the "your turn"
                # event — on-deck stays in-app to avoid email noise
                # before the manager is actually on the clock).
                if event != EVT_DRAFT_YOUR_TURN:
                    continue
                try:
                    owner_doc = await _db().users.find_one(
                        {"_id": ObjectId(uid)},
                        {"email": 1, "name": 1},
                    )
                    if owner_doc and owner_doc.get("email"):
                        subj = f"You're on the clock — {draft_name}"
                        clock_note = (
                            f" {clock_hint.strip()}" if (early_start and clock_hint)
                            else " The clock is running — make your selection in the Draft Room."
                        )
                        html = (
                            f"<p>Hi {owner_doc.get('name') or 'manager'},</p>"
                            f"<p><b>{draft_name}</b>"
                            f"{(' in ' + league_name) if league_name else ''} has started.</p>"
                            f"<p>You're up for <b>Pick #{pick_no}</b>.{clock_note}</p>"
                            f"<p><a href=\"/draft-room\">Open the Draft Room →</a></p>"
                        )
                        _send_email(owner_doc["email"], subj, html)
                except Exception as e:
                    logger.debug(f"start_draft email skipped for {uid}: {e}")
    except Exception as e:
        logger.debug(f"start_draft notification skipped: {e}")

    return {"message": "Draft started", "early_start": early_start}


# ─── POST /drafts/{draft_id}/auto-pick ─────────────────────────────────


@router.post("/drafts/{draft_id}/auto-pick")
async def auto_pick_for_on_clock_team(draft_id: str, request: Request):
    """Auto-pick for whoever is on the clock when their timer expires.

    Resolution order:
      1. The on-clock team's `team.draft_queue` (first undrafted entry)
      2. The top-ranked undrafted player (eligible-players ordering)

    Anyone (manager) can fire this — the backend resolves the right
    team via the stored `team_map` so a missed pick can be skipped
    even when the absent manager isn't logged in.
    """
    await _get_user(request)  # auth required, but no role check
    pick_doc = await perform_one_auto_pick(draft_id, source="timeout")
    return {"pick": pick_doc, "via": pick_doc.get("auto_pick_via")}
