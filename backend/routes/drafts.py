"""Draft router — full draft engine.

Extracted from server.py during iter 98 modularization. Covers the entire
draft lifecycle (snake + auction): create, get, board, eligible-players,
start, pick, pause, chat, config, plus the auction sub-routes (nominate,
bid, resolve, state, init-budgets) and the picks endpoint (lottery /
protections).

Wiring via the standard `setup(deps)` pattern. All collection access goes
through `_db()` so the same module can be tested in isolation against a
throwaway database.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from draft_engine import (
    CreateDraftRequest, MakeDraftPickRequest, DraftChatRequest,
    UpdateDraftConfigRequest, get_team_for_pick, get_draft_order, build_draft_board,
)


router = APIRouter()
_deps: dict = {}
logger = logging.getLogger(__name__)


def setup(deps: dict) -> None:
    _deps.update(deps)


def _db(): return _deps["db"]
def _sio(): return _deps.get("sio")
async def _get_user(request): return await _deps["get_current_user"](request)
async def _log_activity(*a, **kw): return await _deps["log_activity"](*a, **kw)
async def _broadcast(room, event, payload):
    return await _deps["broadcast_to_room"](room, event, payload)
def _calculate_fantasy_points(*a, **kw): return _deps["calculate_fantasy_points"](*a, **kw)


def _send_email(to_email: str, subject: str, html_content: str) -> dict:
    """Iter 230y / 230ab — Thin wrapper around the SendGrid send fn
    registered on `_deps`. Falls back to a mocked `{status: skipped}`
    if the dependency wasn't injected (test envs, server startup
    before `_deps` is populated). Used by the early-start
    notification path to email the on-the-clock manager.
    """
    fn = _deps.get("send_sendgrid_email")
    if not fn:
        return {"status": "skipped", "reason": "send_sendgrid_email not injected"}
    try:
        return fn(to_email, subject, html_content)
    except Exception as e:
        logger.debug(f"_send_email failed for {to_email}: {e}")
        return {"status": "error", "error": str(e)}


# ─── Iter 170g — Team abbr derivation aligned with the frontend ────────
# Matches `team_to_response` (routes/teams.py) which honours
# `logo_abbr_override` then hyphen-aware initials, AND dedupes collisions
# by appending a 2/3/… suffix so two teams that share initials (e.g.
# "Crease Crashers" + "Checkmate Chiefs") get unique board columns.
def _derive_team_abbr(team: dict) -> str:
    name = team.get("name") or ""
    override = (team.get("logo_abbr_override") or "").strip().upper()
    if override:
        return override[:4]
    words = [w for w in name.replace("-", " ").split() if w and w[0].isalnum()]
    if len(words) >= 2:
        return (words[0][0] + words[1][0] + (words[2][0] if len(words) > 2 else "")).upper()[:4]
    return (name[:3].upper() if name else "TBD")


def _abbrs_with_dedup(teams: list[dict]) -> tuple[list[str], dict]:
    """Return (abbrs_in_order, team_map_by_abbr) with collision dedup."""
    seen: dict[str, int] = {}
    abbrs: list[str] = []
    team_map: dict[str, dict] = {}
    for t in teams:
        base = _derive_team_abbr(t)
        count = seen.get(base, 0)
        seen[base] = count + 1
        abbr = base if count == 0 else f"{base}{count + 1}"
        abbrs.append(abbr)
        team_map[abbr] = {
            "id": str(t["_id"]),
            "name": t.get("name"),
            "owner_id": t.get("owner_id"),
        }
    return abbrs, team_map


# ─── Iter 231v — get_draft_picks, get_draft_related_trades,
#     get_draft_player_stats, get_team_draft_picks extracted to
#     routes/draft_inspection.py.
# ─── Iter 231v — get_league_draft_order + DraftOrderConfigRequest +
#     update_league_draft_order_config extracted to routes/draft_order.py.


# Iter 231 — Keeper / Expansion / Protection list / NHL lottery endpoints
# extracted to routes/draft_config.py to keep this file under the maintain-
# ability ceiling. SystemNhlLotteryRequest, KEEPER_COST_METHODS, the
# Expansion enums, KeeperConfigRequest, ExpansionConfigRequest,
# NextDraftTypeRequest, FirstDraftFlagRequest, ProtectionToggleRequest,
# AutoProtectRequest, VALID_NEXT_DRAFT_TYPES and _resolve_draft_type now
# all live in that module. See server.py for the wiring.


# ─── Iter 231t — create_draft extracted to routes/draft_admin.py.


async def _seed_draft_picks_for_draft(
    draft_id: str, league_id: str, rounds: int, year: int,
) -> int:
    """Iter 231n — Thin re-export shim. The real implementation moved
    to `routes/draft_helpers.py` so both drafts.py and draft_pick_actions.py
    can plain-import it without late-binding workarounds. Kept here as a
    shim because internal call-sites at multiple lines in this file (and
    third-party tests that grep for `async def _seed_draft_picks_for_draft`
    in drafts.py source) rely on the name being defined here.
    """
    from routes.draft_helpers import seed_draft_picks_for_draft as _impl
    return await _impl(draft_id, league_id, rounds, year)

# ─── Iter 231t — delete_draft, restore_draft, patch_draft extracted to
#     routes/draft_admin.py.


# ─── Iter 231r — auto_init_draft + start_draft + auto_pick_for_on_clock_team
#     extracted to routes/draft_lifecycle.py.


async def _early_start_clock_msg(draft: dict) -> str:
    """Iter 231n — Thin re-export shim. Real impl in `routes/draft_helpers.py`."""
    from routes.draft_helpers import early_start_clock_msg as _impl
    return await _impl(draft)

# ─── Iter 170g/170h — make-pick, undo-pick, swap-pick, pause endpoints
#     extracted to routes/draft_pick_actions.py (iter 231m).


# ─── Iter 170j — Auto-pick on Timeout ─────────────────────────────────


async def _perform_one_auto_pick(draft_id: str, *, source: str = "timeout") -> dict:
    """Iter 231n — Thin re-export shim. Real impl in `routes/draft_helpers.py`.

    Kept as a shim because (a) `auto_pick_for_on_clock_team` (extracted
    in iter 231r) and admin_user_actions both used to import it from
    here, and (b) several pytest files grep for
    `async def _perform_one_auto_pick` in drafts.py source as a
    regression guard.
    """
    from routes.draft_helpers import perform_one_auto_pick as _impl
    return await _impl(draft_id, source=source)


# Iter 231r — auto_pick_for_on_clock_team extracted to draft_lifecycle.py.


# Iter 170j Draft Queue + Iter 170m Shortlist endpoints extracted to
# `routes/draft_queue.py` (iter 231k).

# ─── Iter 231w — send_draft_chat, get_draft_chat, update_draft_config
#     extracted to routes/draft_chat_config.py.


# ═══════════════════════════════════════════════════════════════
# Notifications Engine
# ═══════════════════════════════════════════════════════════════

class NotificationType(str, Enum):
    TRADE_PROPOSED = "trade_proposed"
    TRADE_ACCEPTED = "trade_accepted"
    TRADE_REJECTED = "trade_rejected"
    TRADE_VETOED = "trade_vetoed"
    WAIVER_WON = "waiver_won"
    WAIVER_LOST = "waiver_lost"
    WAIVERS_PROCESSED = "waivers_processed"
    DRAFT_STARTED = "draft_started"
    DRAFT_PICK = "draft_pick"
    DRAFT_YOUR_TURN = "draft_your_turn"
    DRAFT_COMPLETED = "draft_completed"
    WEEK_SIMULATED = "week_simulated"
    TEAM_JOINED = "team_joined"


async def create_notification(user_id: str, notif_type: str, title: str, message: str, league_id: str = None, link: str = None, reason: dict = None):
    """Create a notification and broadcast it via WebSocket + Expo push.

    Iter 230 — Honours per-user preferences from `notification_preferences`.
    The `in_app` channel gates the DB write + socket broadcast; `push` gates
    the Expo task. The catalog's default_channels list seeds new users.

    Iter 230h — `reason` (optional dict) is persisted alongside the
    notification so the frontend's "Why am I being notified?" affordance
    can explain the source: signal type, originating service, player
    matched, team rostering, etc. Free-form, no schema enforcement so
    each emitter can include whatever helps the user.
    """
    # Lazy import to avoid an init-time cycle (notification_preferences may
    # not be wired yet during module import).
    try:
        from routes.notification_preferences import channel_enabled
    except Exception:
        channel_enabled = None  # type: ignore

    in_app_on = True
    push_on = True
    if channel_enabled is not None:
        try:
            in_app_on = await channel_enabled(user_id, notif_type, "in_app", league_id)
            push_on = await channel_enabled(user_id, notif_type, "push", league_id)
        except Exception as e:
            logger.debug(f"channel_enabled check failed: {e}")

    if not in_app_on:
        # User opted out — don't persist or broadcast in-app.
        return None

    doc = {
        "user_id": user_id,
        "type": notif_type,
        "title": title,
        "message": message,
        "league_id": league_id,
        "link": link,
        "reason": reason or None,
        "read": False,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    result = await _db().notifications.insert_one(doc)
    doc["_id"] = str(result.inserted_id)
    # Broadcast to user's personal room (socket.io)
    sio = _sio()
    if sio is not None:
        try:
            await sio.emit("notification", doc, room=f"user_{user_id}")
        except Exception as e:
            logger.debug(f"sio notify skipped: {e}")
    # Fire an Expo push in parallel (non-blocking best-effort) — only when
    # the user has the push channel enabled for this event type.
    if push_on:
        try:
            from routes.push import send_push
            asyncio.create_task(send_push(
                [user_id],
                title=title,
                body=message,
                data={"type": notif_type, "league_id": league_id, "link": link, "notification_id": doc["_id"]},
            ))
        except Exception as e:
            logger.debug(f"push notify skipped: {e}")
    return doc


async def notify_league(league_id: str, notif_type: str, title: str, message: str, link: str = None, exclude_user: str = None):
    """Send notification to all team owners in a league."""
    teams = await _db().teams.find({"league_id": league_id}, {"owner_id": 1}).to_list(100)
    for team in teams:
        if team["owner_id"] != exclude_user:
            await create_notification(team["owner_id"], notif_type, title, message, league_id, link)


# Notifications routes moved to routes/notifications.py (iter 85).





# Auction Draft Engine endpoints extracted to routes/draft_auction.py (iter 231k).



# ─── Iter 228e — Per-pick defer_user_options endpoints extracted to
#     `routes/draft_picks.py` (iter 231l). DeferPickChoiceRequest and
#     both /picks/{pick_no}/defer endpoints now live there.


# ─── Iter 228i — Retroactive pick seeding endpoint extracted to
#     routes/draft_pick_actions.py (iter 231m).
