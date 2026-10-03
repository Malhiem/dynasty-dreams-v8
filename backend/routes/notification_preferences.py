"""Iter 230 — Notification preferences router.

Per-user, per-event-type channel toggles. Channels: in_app, push, email.
Currently only `in_app` is wired end-to-end (toast + bell badge); push/email
are saved as preferences for future Expo/SendGrid wiring.

Endpoints:
  GET  /api/notifications/preferences           → current settings + catalog
  PUT  /api/notifications/preferences           → update a single event's channels
  POST /api/notifications/preferences/reset     → reset to factory defaults

The catalog (EVENTS + CATEGORIES) is included in the GET response so the
settings UI can render groups + labels without a separate fetch.
"""
from typing import Optional, Dict

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from .notification_events import EVENTS, CATEGORIES, EVENT_IDS, default_preferences


router = APIRouter()
_deps: dict = {}


def setup(deps: dict) -> None:
    _deps.update(deps)


class PreferenceUpdateInput(BaseModel):
    event_id: str
    in_app: Optional[bool] = None
    push: Optional[bool] = None
    email: Optional[bool] = None
    # Iter 230e — Critical override (bypasses Quiet Hours when True).
    critical: Optional[bool] = None


# Iter 230d — Quiet Hours + per-league mute
class QuietHoursInput(BaseModel):
    enabled: bool
    start: Optional[str] = None  # "HH:MM" 24-hour local time
    end: Optional[str] = None    # "HH:MM" 24-hour local time
    timezone_offset_minutes: Optional[int] = None  # client's UTC offset


class LeagueMuteInput(BaseModel):
    league_id: str
    muted: bool


# Iter 230h — Per-user "hide from dashboard" preference. Hidden leagues
# disappear from /users/me/week-at-a-glance + the sidebar's "My Leagues"
# list. The user can still resurface them via the Settings modal.
class LeagueHideInput(BaseModel):
    league_id: str
    hidden: bool


# Iter 230am — Per-user league display order. Persisted server-side so
# the user's preferred ordering follows them across devices instead of
# living only in localStorage. The frontend writes the full ordered
# list on every reorder.
from typing import List


class LeagueOrderInput(BaseModel):
    ordered_ids: List[str]


def _default_quiet_hours() -> dict:
    return {
        "enabled": False,
        "start": "22:00",
        "end": "07:00",
        "timezone_offset_minutes": 0,
    }


def _hhmm_to_minutes(value: str) -> Optional[int]:
    if not value or ":" not in value:
        return None
    try:
        h, m = value.split(":", 1)
        h_i = int(h)
        m_i = int(m)
        if 0 <= h_i < 24 and 0 <= m_i < 60:
            return h_i * 60 + m_i
    except Exception:
        return None
    return None


def _is_in_quiet_window(quiet: dict) -> bool:
    """Returns True if the user's current local time is inside the
    configured quiet-hours window. Cross-midnight windows are supported
    (e.g. start=22:00, end=07:00). All math is done in the user's
    self-reported local minutes-of-day so the server doesn't need to
    care about timezones beyond storing the offset.
    """
    if not quiet or not quiet.get("enabled"):
        return False
    from datetime import datetime, timezone
    tz_off = int(quiet.get("timezone_offset_minutes") or 0)
    now_utc = datetime.now(timezone.utc)
    # Convert "now" to the user's local minutes-of-day.
    local_minute = (now_utc.hour * 60 + now_utc.minute - tz_off) % (24 * 60)
    start_m = _hhmm_to_minutes(quiet.get("start") or "22:00")
    end_m = _hhmm_to_minutes(quiet.get("end") or "07:00")
    if start_m is None or end_m is None:
        return False
    if start_m == end_m:
        return False  # Zero-length window = disabled in practice.
    if start_m < end_m:
        return start_m <= local_minute < end_m
    # Cross-midnight window: start > end.
    return local_minute >= start_m or local_minute < end_m


async def _load_or_init(user_id: str) -> Dict[str, Dict[str, bool]]:
    db = _deps["db"]
    doc = await db.notification_preferences.find_one({"user_id": user_id})
    if doc and isinstance(doc.get("preferences"), dict):
        # Merge in any newly-added events with their defaults so future
        # additions auto-populate for existing users.
        defaults = default_preferences()
        merged = {**defaults, **doc["preferences"]}
        # If a new event was added since the user's last save, persist the
        # merged shape so subsequent reads are fast.
        if set(merged.keys()) != set(doc["preferences"].keys()):
            await db.notification_preferences.update_one(
                {"user_id": user_id},
                {"$set": {"preferences": merged}},
            )
        return merged
    # First-time user: seed defaults.
    prefs = default_preferences()
    await db.notification_preferences.update_one(
        {"user_id": user_id},
        {"$set": {"user_id": user_id, "preferences": prefs}},
        upsert=True,
    )
    return prefs


async def _load_full_doc(user_id: str) -> dict:
    """Iter 230d — Reads the user's full preference doc (events + quiet
    hours + muted leagues). Lazy-initializes missing structural sections.
    """
    db = _deps["db"]
    doc = await db.notification_preferences.find_one({"user_id": user_id}) or {}
    preferences = doc.get("preferences")
    if not isinstance(preferences, dict):
        preferences = await _load_or_init(user_id)
        doc["preferences"] = preferences
    quiet = doc.get("quiet_hours")
    if not isinstance(quiet, dict):
        quiet = _default_quiet_hours()
    muted = doc.get("muted_league_ids") or []
    hidden = doc.get("hidden_league_ids") or []
    league_order = doc.get("league_order") or []
    return {
        "preferences": preferences,
        "quiet_hours": quiet,
        "muted_league_ids": list(muted),
        "hidden_league_ids": list(hidden),
        "league_order": list(league_order),
    }


@router.get("/notifications/preferences")
async def get_preferences(request: Request):
    get_current_user = _deps["get_current_user"]
    user = await get_current_user(request)
    full = await _load_full_doc(user["_id"])
    return {
        "preferences": full["preferences"],
        "quiet_hours": full["quiet_hours"],
        "muted_league_ids": full["muted_league_ids"],
        "hidden_league_ids": full["hidden_league_ids"],
        "league_order": full["league_order"],
        "events": EVENTS,
        "categories": CATEGORIES,
    }


@router.put("/notifications/preferences/quiet-hours")
async def update_quiet_hours(input: QuietHoursInput, request: Request):
    """Iter 230d — Set quiet hours (HH:MM start + end + timezone offset).
    Both `start` and `end` are required when `enabled=True`. The window
    may cross midnight (e.g. 22:00 → 07:00)."""
    db = _deps["db"]
    get_current_user = _deps["get_current_user"]
    user = await get_current_user(request)
    quiet = _default_quiet_hours()
    quiet["enabled"] = bool(input.enabled)
    if input.start:
        if _hhmm_to_minutes(input.start) is None:
            raise HTTPException(status_code=422, detail="start must be HH:MM 24-hour")
        quiet["start"] = input.start
    if input.end:
        if _hhmm_to_minutes(input.end) is None:
            raise HTTPException(status_code=422, detail="end must be HH:MM 24-hour")
        quiet["end"] = input.end
    if input.timezone_offset_minutes is not None:
        quiet["timezone_offset_minutes"] = int(input.timezone_offset_minutes)
    await db.notification_preferences.update_one(
        {"user_id": user["_id"]},
        {"$set": {"user_id": user["_id"], "quiet_hours": quiet}},
        upsert=True,
    )
    return {"quiet_hours": quiet}


@router.put("/notifications/preferences/league-mute")
async def update_league_mute(input: LeagueMuteInput, request: Request):
    """Iter 230d — Toggle mute state for a single league. Muting a league
    silences ALL in-app + push + email notifications scoped to that
    league_id (the user can still see them after-the-fact in the bell
    dropdown — they just don't get the live toast/badge bump)."""
    db = _deps["db"]
    get_current_user = _deps["get_current_user"]
    user = await get_current_user(request)
    if input.muted:
        await db.notification_preferences.update_one(
            {"user_id": user["_id"]},
            {"$set": {"user_id": user["_id"]},
             "$addToSet": {"muted_league_ids": input.league_id}},
            upsert=True,
        )
    else:
        await db.notification_preferences.update_one(
            {"user_id": user["_id"]},
            {"$set": {"user_id": user["_id"]},
             "$pull": {"muted_league_ids": input.league_id}},
            upsert=True,
        )
    full = await _load_full_doc(user["_id"])
    return {"muted_league_ids": full["muted_league_ids"]}


@router.put("/notifications/preferences/league-hide")
async def update_league_hide(input: LeagueHideInput, request: Request):
    """Iter 230h — Hide a league from the dashboard (Week at a Glance +
    My Leagues sidebar). Reversible: the user can unhide from the
    Settings modal at any time. Distinct from `league-mute` which only
    silences notifications — `league-hide` actually removes the league
    from the user's day-to-day surface area."""
    db = _deps["db"]
    get_current_user = _deps["get_current_user"]
    user = await get_current_user(request)
    if input.hidden:
        await db.notification_preferences.update_one(
            {"user_id": user["_id"]},
            {"$set": {"user_id": user["_id"]},
             "$addToSet": {"hidden_league_ids": input.league_id}},
            upsert=True,
        )
    else:
        await db.notification_preferences.update_one(
            {"user_id": user["_id"]},
            {"$set": {"user_id": user["_id"]},
             "$pull": {"hidden_league_ids": input.league_id}},
            upsert=True,
        )
    full = await _load_full_doc(user["_id"])
    return {"hidden_league_ids": full["hidden_league_ids"]}


async def get_hidden_league_ids(user_id: str) -> list:
    """Iter 230h — Helper used by other routes (week-at-a-glance,
    leagues) to apply the hidden-league filter consistently."""
    db = _deps.get("db")
    if db is None:
        return []
    doc = await db.notification_preferences.find_one({"user_id": user_id})
    return list((doc or {}).get("hidden_league_ids") or [])


@router.put("/notifications/preferences/league-order")
async def update_league_order(input: LeagueOrderInput, request: Request):
    """Iter 230am — Persist the user's preferred league display order
    server-side so it follows them across devices. The frontend sends
    the full ordered list of league_ids on every reorder; we replace
    the stored list wholesale. Empty list is allowed (clears the order
    → consumers fall back to default sort)."""
    db = _deps["db"]
    get_current_user = _deps["get_current_user"]
    user = await get_current_user(request)
    # De-dup while preserving order (defensive — clients may glitch).
    seen = set()
    cleaned: list = []
    for lid in input.ordered_ids:
        if lid and lid not in seen:
            seen.add(lid)
            cleaned.append(lid)
    await db.notification_preferences.update_one(
        {"user_id": user["_id"]},
        {"$set": {"user_id": user["_id"], "league_order": cleaned}},
        upsert=True,
    )
    return {"league_order": cleaned}


@router.put("/notifications/preferences")
async def update_preference(input: PreferenceUpdateInput, request: Request):
    db = _deps["db"]
    get_current_user = _deps["get_current_user"]
    user = await get_current_user(request)
    if input.event_id not in EVENT_IDS:
        raise HTTPException(status_code=422, detail=f"Unknown event_id: {input.event_id}")
    prefs = await _load_or_init(user["_id"])
    current = prefs.get(input.event_id, {"in_app": False, "push": False, "email": False, "critical": False})
    if input.in_app is not None:
        current["in_app"] = bool(input.in_app)
    if input.push is not None:
        current["push"] = bool(input.push)
    if input.email is not None:
        current["email"] = bool(input.email)
    if input.critical is not None:
        current["critical"] = bool(input.critical)
    prefs[input.event_id] = current
    await db.notification_preferences.update_one(
        {"user_id": user["_id"]},
        {"$set": {f"preferences.{input.event_id}": current}},
    )
    return {"event_id": input.event_id, "preferences": current}


@router.post("/notifications/preferences/reset")
async def reset_preferences(request: Request):
    db = _deps["db"]
    get_current_user = _deps["get_current_user"]
    user = await get_current_user(request)
    prefs = default_preferences()
    await db.notification_preferences.update_one(
        {"user_id": user["_id"]},
        {"$set": {"user_id": user["_id"], "preferences": prefs}},
        upsert=True,
    )
    return {"preferences": prefs}


async def channel_enabled(user_id: str, event_id: str, channel: str, league_id: Optional[str] = None) -> bool:
    """Helper used by the emitter side. Returns True if `channel` is enabled
    for this user+event+league. Unknown events default to True (don't
    accidentally swallow notifications added before the catalog catches
    up). Channels not in the saved doc fall back to the event's
    default_channels list.

    Iter 230d — Now ALSO honours:
      • Quiet Hours (gate `in_app` + `push` deliveries while the user's
        local clock is in their configured quiet window).
      • Per-league mute (gate ALL channels when `league_id` is in the
        user's `muted_league_ids` list).
    """
    db = _deps.get("db")
    if db is None:
        return True
    if event_id not in EVENT_IDS:
        return True

    doc = await db.notification_preferences.find_one({"user_id": user_id})
    full_doc = doc or {}
    prefs = full_doc.get("preferences") or {}

    # Per-league mute kills every channel.
    if league_id:
        muted = full_doc.get("muted_league_ids") or []
        if league_id in muted:
            return False

    # Quiet hours mute in_app + push (email still gets through —
    # treated like a digest). Iter 230e — Per-event `critical` flag
    # bypasses the quiet-hours gate when the user has opted in (e.g.
    # "I never want to miss being on the clock during a draft").
    cfg = prefs.get(event_id)
    if channel in ("in_app", "push"):
        quiet = full_doc.get("quiet_hours")
        if isinstance(quiet, dict) and _is_in_quiet_window(quiet):
            is_critical = bool((cfg or {}).get("critical", False)) if cfg else False
            # When the saved config is missing entirely, fall back to the
            # catalog's "default_critical" set so brand-new users still
            # get the right behaviour out of the box.
            if cfg is None:
                for e in EVENTS:
                    if e["id"] == event_id:
                        is_critical = event_id in {
                            "trade_proposed", "trade_accepted_mine",
                            "trade_declined_or_vetoed_mine", "draft_your_turn",
                            "draft_on_deck", "lineup_lock_reminder",
                            "lineup_problem", "waiver_claim_success",
                            "reminder_important",
                        }
                        break
            if not is_critical:
                return False

    if cfg is None:
        # Fall back to catalog defaults.
        for e in EVENTS:
            if e["id"] == event_id:
                return channel in e["default_channels"]
        return True
    return bool(cfg.get(channel, False))
