"""Draft helpers — extracted from `routes/drafts.py` (iter 231n).

Provides the three internal helpers that the make-pick / auto-pick /
seed-picks endpoints rely on:

  • `seed_draft_picks_for_draft` — materialise `rounds × team-count`
    `draft_picks` rows for a freshly-created draft (idempotent on the
    `(league_id, draft_id, year, round, original_team_id)` key).
  • `early_start_clock_msg` — render the "Clock activates at HH:MM
    (your time) — pick now if you want to" suffix appended to the
    "You're on the clock!" notification body when the commissioner
    runs `start_draft(early_start=True)`.
  • `perform_one_auto_pick` — shared core for auto-picking the team
    currently on the clock. Called from `auto_pick_for_on_clock_team`
    in drafts.py + the eviction flow in `admin_user_actions.py`.

Iter 231m left these helpers in drafts.py and made the extracted
`draft_pick_actions` module late-bind to them via
`from routes import drafts` inside helper functions. The testing-agent
code review flagged that as a smell pointing at this extraction. With
the helpers in their own module both consumers can plain-import them
and the late-binding workaround disappears.

Wired via the `setup(deps)` injection pattern; see `server.py`.

NOTE: Helpers here are intentionally **not** decorated with
`@router.*` — this module contributes no HTTP routes. It exists purely
to host the cross-module helpers.
"""
from __future__ import annotations

from datetime import datetime, timezone

from bson import ObjectId
from fastapi import HTTPException

from draft_engine import get_team_for_pick


_deps: dict = {}


def setup(deps: dict) -> None:
    _deps.update(deps)


def _db():
    return _deps["db"]


async def _broadcast(room: str, event: str, payload: dict):
    fn = _deps.get("broadcast_to_room")
    if fn is None:
        return None
    return await fn(room, event, payload)


# ─────────────────────────────────────────────────────────────────
# 1. Seed draft_picks rows for a draft (idempotent).
# ─────────────────────────────────────────────────────────────────


async def seed_draft_picks_for_draft(
    draft_id: str, league_id: str, rounds: int, year: int,
) -> int:
    """Iter 228h helper — materialises `rounds × team-count` draft_picks
    rows for a freshly-created draft so they're immediately visible in
    the trade center and draft board.

    Teams are ordered alphabetically when the league hasn't saved a
    pick order yet — deterministic and trivially overridable later.
    Idempotent on `(league_id, draft_id, year, round, original_team_id)`.
    """
    teams = await _db().teams.find({"league_id": league_id}).to_list(200)
    if not teams:
        return 0
    # Honour saved pick order when present, else alphabetical.
    saved_order_doc = await _db().draft_order_config.find_one({"league_id": league_id})
    saved_order = (saved_order_doc or {}).get("pick_order") or []
    if saved_order:
        order_index = {tid: idx for idx, tid in enumerate(saved_order)}
        teams.sort(key=lambda t: order_index.get(str(t["_id"]), 9999))
    else:
        teams.sort(key=lambda t: (t.get("name") or "").lower())

    inserted = 0
    now = datetime.now(timezone.utc)
    for r in range(1, rounds + 1):
        for slot, team in enumerate(teams, start=1):
            tid = str(team["_id"])
            # Iter 228s — Include `draft_id` in the dedup key so the
            # league can have multiple drafts in the SAME year (e.g.
            # Inaugural in May + Summer Entry in July + Winter in
            # December — all 2026) and each gets its OWN independent
            # set of pick rows. Without this guard, the second and
            # third drafts found existing rows from the first and
            # skipped every insert.
            existing = await _db().draft_picks.find_one({
                "league_id": league_id,
                "draft_id": draft_id,
                "year": year,
                "round": r,
                "original_team_id": tid,
            })
            if existing:
                continue
            await _db().draft_picks.insert_one({
                "league_id": league_id,
                "draft_id": draft_id,
                "year": year,
                "round": r,
                "slot": slot,
                "overall": (r - 1) * len(teams) + slot,
                "original_team_id": tid,
                "original_team_name": team.get("name") or "Unknown",
                "current_team_id": tid,
                "current_team_name": team.get("name") or "Unknown",
                "trade_history": [],
                "tradeable": True,
                "created_at": now,
            })
            inserted += 1
    return inserted


# ─────────────────────────────────────────────────────────────────
# 2. Early-start clock activation suffix for notifications.
# ─────────────────────────────────────────────────────────────────


async def early_start_clock_msg(draft: dict) -> str:
    """Iter 230y — Render the per-notification clock-activation hint
    used when the commissioner starts a draft with `early_start=True`.

    Returns the empty string if the clock isn't going to auto-activate
    (no `scheduled_time` set or it's already in the past). Otherwise
    returns a short " The clock will start at ISO — pick now if you
    want to, or wait." suffix the caller appends to the standard
    "You're on the clock!" body.
    """
    if not draft.get("early_start"):
        return ""
    sched = draft.get("scheduled_time")
    if not sched:
        return ""
    try:
        sched_dt = datetime.fromisoformat(str(sched).replace("Z", "+00:00"))
    except Exception:
        return ""
    if sched_dt <= datetime.now(timezone.utc):
        return ""
    iso = sched_dt.isoformat().replace("+00:00", "Z")
    return (
        " The clock will start at " + iso +
        " — pick now if you want to, or wait."
    )


# ─────────────────────────────────────────────────────────────────
# 3. Auto-pick the team currently on the clock.
# ─────────────────────────────────────────────────────────────────


async def perform_one_auto_pick(draft_id: str, *, source: str = "timeout") -> dict:
    """Iter 221 — Shared core for auto-picking the team currently on the clock.
    Returns the recorded pick document. Raises HTTPException on bad state.
    `source` is stamped into the pick doc / broadcast for audit (timeout,
    eviction, commissioner_skip, etc.).
    """
    draft = await _db().drafts.find_one({"_id": ObjectId(draft_id)})
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    if draft["status"] != "active":
        raise HTTPException(status_code=400, detail="Draft is not active")

    on_clock = get_team_for_pick(draft["team_abbrs"], draft["current_pick"], draft["snake_draft"])
    on_clock_team_id = (draft.get("team_map") or {}).get(on_clock, {}).get("id")
    if not on_clock_team_id:
        raise HTTPException(status_code=500, detail="Could not resolve on-clock team")

    drafted_ids = {p.get("player_id") for p in draft.get("picks", []) if p.get("player_id")}

    chosen_player = None
    via = "top_eligible"
    team = await _db().teams.find_one({"_id": ObjectId(on_clock_team_id)})
    queue = list((team or {}).get("draft_queue") or [])
    for pid in queue:
        if pid in drafted_ids:
            continue
        try:
            cand = await _db().players.find_one({"_id": ObjectId(pid)})
        except Exception:
            continue
        if cand:
            chosen_player = cand
            via = "queue"
            break

    if chosen_player is None:
        # Iter 231r — Defensive: some legacy drafts have `player_criteria`
        # stored as a list instead of a string. Coerce to str so `.lower()`
        # never crashes the worker.
        raw_criteria = (draft.get("player_criteria") or "open")
        if isinstance(raw_criteria, list):
            raw_criteria = raw_criteria[0] if raw_criteria else "open"
        criteria = str(raw_criteria).lower()
        q = {"player_type": "prospect"} if criteria == "entry" else {"player_type": {"$ne": "prospect"}}
        async for p in _db().players.find(q).sort([("points", -1), ("name", 1)]):
            if str(p["_id"]) in drafted_ids:
                continue
            chosen_player = p
            break

    if chosen_player is None:
        raise HTTPException(status_code=400, detail="No eligible players left")

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
        "player_id": str(chosen_player["_id"]),
        "player": {
            "id": str(chosen_player["_id"]),
            "name": chosen_player["name"],
            "position": chosen_player["position"],
            "nhlTeam": chosen_player.get("team", ""),
            "team_name": chosen_player.get("team_name", ""),
            "pts": chosen_player.get("points", 0),
            "g": chosen_player.get("goals", 0),
            "a": chosen_player.get("assists", 0),
            "gp": chosen_player.get("games_played", 0),
            "league": "NHL",
            "headshot": (
                f"https://assets.nhle.com/mugs/nhl/20252026/{chosen_player.get('team', 'NHL')}/{chosen_player.get('nhl_id', '')}.png"
                if chosen_player.get("nhl_id") else None
            ),
        },
        "auto_picked": True,
        "auto_pick_via": via,
        "auto_pick_source": source,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    next_pick = current_pick + 1
    total_picks = draft["total_rounds"] * total_teams
    new_status = "completed" if next_pick > total_picks else "active"
    await _db().drafts.update_one(
        {"_id": ObjectId(draft_id)},
        {"$push": {"picks": pick_doc}, "$set": {"current_pick": next_pick, "status": new_status}},
    )
    await _db().teams.update_one(
        {"_id": ObjectId(on_clock_team_id)},
        {
            "$addToSet": {"roster": str(chosen_player["_id"])},
            "$pull": {"draft_queue": str(chosen_player["_id"])},
        },
    )
    label = "Auto-pick" if source != "eviction" else "Eviction auto-pick"
    msg = {
        "id": f"autopick-{datetime.now(timezone.utc).timestamp()}",
        "type": "pick",
        "sender": "System",
        "text": (
            f"⏱ {label} — {on_clock} took {chosen_player['name']} ({chosen_player['position']}) "
            f"at #{current_pick} (via {'queue' if via == 'queue' else 'top eligible'})"
        ),
        "auto_picked": True,
        "auto_pick_via": via,
        "auto_pick_source": source,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    await _db().drafts.update_one({"_id": ObjectId(draft_id)}, {"$push": {"chat_messages": msg}})
    await _broadcast(f"draft_{draft_id}", "draft_chat", msg)
    await _broadcast(f"draft_{draft_id}", "draft_pick", {
        **pick_doc,
        "next_pick": next_pick,
        "on_the_clock": get_team_for_pick(draft["team_abbrs"], next_pick, draft["snake_draft"]) if new_status == "active" else None,
        "draft_complete": new_status == "completed",
    })
    return pick_doc
