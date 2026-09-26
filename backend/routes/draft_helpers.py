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


# ─── Iter 232N — Pick payload builder ─────────────────────────────
def build_pick_player_payload(player: dict) -> dict:
    """Shared payload the make-pick / auto-pick / seed-picks paths write
    onto every `picks[]` entry.

    Historically these three sites duplicated an inline dict with a
    HARDCODED `"league": "NHL"` — meaning a prospect drafted from the
    WHL / OHL / SHL etc. would render as an "NHL" pick on the draft
    board. That's what made the user report "the draft is picking NHL
    starters" even though the underlying `player_type == "prospect"`.
    This helper computes the correct league label:

        NHL players → "NHL"
        prospects   → their amateur league (WHL, OHL, KHL, SHL, ...)
                      falling back to "Prospect" when the amateur field
                      is missing.

    Also stamps `player_type` on the pick row so the frontend badge
    layer can render the correct chip (Prospect / NHL / Goalie).
    """
    is_prospect = (player.get("player_type") == "prospect")
    league_label = player.get("amateur_league") if is_prospect else "NHL"
    if not league_label:
        league_label = "Prospect" if is_prospect else "NHL"
    return {
        "id": str(player["_id"]),
        "name": player["name"],
        "position": player["position"],
        "nhlTeam": player.get("team", ""),
        "team_name": player.get("team_name", ""),
        "pts": player.get("points", 0),
        "g": player.get("goals", 0),
        "a": player.get("assists", 0),
        "gp": player.get("games_played", 0),
        "league": league_label,
        "player_type": player.get("player_type") or "skater",
        "amateur_league": player.get("amateur_league"),
        "age": player.get("age"),
        "headshot": (
            f"https://assets.nhle.com/mugs/nhl/20252026/{player.get('team', 'NHL')}/{player.get('nhl_id', '')}.png"
            if player.get("nhl_id") else None
        ),
    }


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


async def backfill_missing_pick_rows_for_league(league_id: str) -> int:
    """Iter 232N.37 — Called after new teams are inserted into a league
    to re-seed picks for every existing draft. Fixes the "TFHL Draft
    Board shows only Hamilton" class of bugs where drafts were seeded
    while only 1 team existed, then more teams were added later.

    Idempotent via `seed_draft_picks_for_draft`'s dedup key. Returns
    total picks inserted across all drafts in the league.
    """
    drafts = await _db().drafts.find(
        {"league_id": league_id, "status": {"$in": ["scheduled", "active"]}},
    ).to_list(200)
    if not drafts:
        return 0
    total = 0
    for draft in drafts:
        try:
            year = int(str(draft.get("year") or draft.get("season") or "0").split("-")[0]) or None
            if not year:
                # Fall back to the league's season year.
                league = await _db().leagues.find_one(
                    {"_id": draft["league_id"] if hasattr(draft["league_id"], "binary")
                     else ObjectId(str(draft["league_id"]))},
                )
                year = int((league or {}).get("season", "2026").split("-")[0])
            total += await seed_draft_picks_for_draft(
                draft_id=str(draft["_id"]),
                league_id=league_id,
                rounds=int(draft.get("total_rounds") or 1),
                year=year,
            )
        except Exception:
            # Best-effort — a single draft failing shouldn't block the
            # team-add call site.
            continue
    return total


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


async def perform_one_auto_pick(draft_id: str, *, source: str = "timeout", preference: str | None = None) -> dict:
    """Iter 221 — Shared core for auto-picking the team currently on the clock.
    Returns the recorded pick document. Raises HTTPException on bad state.
    `source` is stamped into the pick doc / broadcast for audit (timeout,
    eviction, commissioner_skip, etc.).

    Iter 232N.26 — `preference` overrides the on-clock team's stored
    `auto_pick_preference`. When "best_available", the queue walk is
    skipped and we jump straight to the top-eligible player. When None
    (default), the team's own field is used, defaulting to
    "queue_then_best" for legacy compatibility.

    Iter 232x — Honors traded picks: checks `draft_picks` collection
    for current_team_id override before falling back to the standard
    draft order.
    """
    draft = await _db().drafts.find_one({"_id": ObjectId(draft_id)})
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    if draft["status"] != "active":
        raise HTTPException(status_code=400, detail="Draft is not active")

    # Determine on-clock team, honoring traded picks
    on_clock = get_team_for_pick(draft["team_abbrs"], draft["current_pick"], draft["snake_draft"])
    on_clock_team_id = (draft.get("team_map") or {}).get(on_clock, {}).get("id")

    # Iter 232x — Check if this pick was traded to a different team.
    # Query by (round, original_team_id) since slot ordering doesn't
    # account for snake draft reversal.  `on_clock` from
    # `get_team_for_pick` already handles snake ordering, so it gives
    # us the correct *original* team that owns this slot.
    total_teams = len(draft["team_abbrs"])
    current_pick = draft["current_pick"]
    round_num = ((current_pick - 1) // total_teams) + 1
    if on_clock_team_id:
        traded_pick = await _db().draft_picks.find_one({
            "league_id": draft.get("league_id"),
            "draft_id": str(draft["_id"]),
            "round": round_num,
            "original_team_id": on_clock_team_id,
        })
        if not traded_pick:
            # Fallback: try without draft_id for older leagues
            traded_pick = await _db().draft_picks.find_one({
                "league_id": draft.get("league_id"),
                "round": round_num,
                "original_team_id": on_clock_team_id,
            })
        if traded_pick and traded_pick.get("current_team_id"):
            traded_team_id = str(traded_pick["current_team_id"])
            if traded_team_id != str(traded_pick.get("original_team_id")):
                on_clock_team_id = traded_team_id
                traded_team = await _db().teams.find_one({"_id": ObjectId(traded_team_id)})
                if traded_team:
                    on_clock = traded_team.get("abbreviation") or traded_team.get("name", on_clock)

    if not on_clock_team_id:
        raise HTTPException(status_code=500, detail="Could not resolve on-clock team")

    drafted_ids = {p.get("player_id") for p in draft.get("picks", []) if p.get("player_id")}

    chosen_player = None
    via = "top_eligible"
    team = await _db().teams.find_one({"_id": ObjectId(on_clock_team_id)})
    effective_pref = preference or (team or {}).get("auto_pick_preference") or "queue_then_best"
    # Iter 232N.26 — Skip the queue walk when the manager opted into
    # "best available" as their fallback. Both preferences still fall
    # back to top-eligible when no player matches — never fail-open.
    if effective_pref != "best_available":
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
        # Iter 231aj — Same 3-way criteria mapping as
        # `get_draft_eligible_players`: entry/prospects → prospects
        # only; all → no filter; else → non-prospects only.
        if criteria in ("entry", "prospects"):
            q = {"player_type": "prospect"}
        elif criteria == "all":
            q = {}
        else:
            q = {"player_type": {"$ne": "prospect"}}
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
        "player": build_pick_player_payload(chosen_player),
        "auto_picked": True,
        "auto_pick_via": via,
        "auto_pick_source": source,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        # Iter 232N.27 — Auto-picks also record the elapsed time so the
        # "slow-poke" leaderboard can weight full-clock stalls against
        # fast manual picks.
        "time_taken_seconds": (
            (lambda raw: (
                int((datetime.now(timezone.utc) -
                     datetime.fromisoformat(raw.replace("Z", "+00:00"))).total_seconds())
                if raw else None
            ))(draft.get("current_pick_started_at"))
        ),
    }
    next_pick = current_pick + 1
    total_picks = draft["total_rounds"] * total_teams
    new_status = "completed" if next_pick > total_picks else "active"
    # Iter 231x — Optimistic concurrency control. Without this guard
    # two concurrent invocations (the timer worker + a manual UI
    # auto-pick, or two timer ticks racing each other on a single
    # expired clock) both read `current_pick=N`, both compute the same
    # on-clock team, and both `$push` a pick with `overall=N` — yielding
    # duplicate picks. Conditioning the update on `current_pick == N`
    # AND `status == "active"` makes the second writer's match_count=0
    # and we abort cleanly instead of polluting the picks array.
    # Iter 231ab — Reset `current_pick_started_at` so the worker doesn't
    # immediately re-fire on the next tick (was stuck on the original
    # `started` value and treated every following pick as "already
    # expired", producing the rapid-fire auto-pick incident the user
    # reported on 2026-02 — even after the clock-window guard landed).
    result = await _db().drafts.update_one(
        {"_id": ObjectId(draft_id), "current_pick": current_pick, "status": "active"},
        {
            "$push": {"picks": pick_doc},
            "$set": {
                "current_pick": next_pick,
                "status": new_status,
                "current_pick_started_at": datetime.now(timezone.utc).isoformat(),
            },
        },
    )
    if result.matched_count == 0:
        # Another writer beat us — refuse silently so the caller can
        # observe via an HTTP 409. The timer worker catches this and
        # increments its `errors` counter; the manual /auto-pick
        # endpoint surfaces the 409 to the client.
        raise HTTPException(
            status_code=409,
            detail=f"Pick #{current_pick} was already made by another process (concurrent update)",
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
    # Iter 232N.27 — When the auto-pick just completed the draft,
    # hand out the "Speed Demon" XP badge before we return.
    if new_status == "completed":
        try:
            from utils.xp import award_draft_completion_bonuses
            await award_draft_completion_bonuses(
                _db(),
                draft_id=draft_id,
                broadcast_fn=_deps.get("broadcast_to_room"),
            )
        except Exception as ex:
            import logging
            logging.getLogger(__name__).debug(
                f"draft_speed_champion award skipped (auto-pick path): {ex}"
            )
    return pick_doc
