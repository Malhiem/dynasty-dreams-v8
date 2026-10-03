"""Iter 230 — Notification event catalog.

Single source of truth for every in-app notification the platform can emit.
Each event declares an `id` (used as the `notifications.type` Mongo field), a
human-readable `label`, a `description`, a `category` (for grouping in the
settings UI), and `default_channels` — which delivery channels are ON for a
brand-new user. Channels:
  • "in_app"  — the only one that actually fires today (toast + bell badge)
  • "push"    — preference is saved, future Expo push wiring will read it
  • "email"   — preference is saved, future SendGrid wiring will read it

The settings modal reads `EVENTS` to render the toggles; the
`notification_preferences` router validates incoming PUTs against the same
list so unknown event ids are rejected with a 422.

NOTE: All emitter call-sites should reference the constants exported below
(e.g. `EVT_TRADE_PROPOSED`) instead of magic strings so we get IDE help and
a single rename surface.
"""
from typing import List, Dict

EVT_TRADE_PROPOSED = "trade_proposed"
EVT_TRADE_DECLINED_OR_VETOED_MINE = "trade_declined_or_vetoed_mine"
EVT_TRADE_VETOED_ANY = "trade_vetoed_any"
EVT_TRADE_ACCEPTED_MINE = "trade_accepted_mine"
EVT_TRADE_ACCEPTED_ANY = "trade_accepted_any"
EVT_TRADE_PROCESSED = "trade_processed"
EVT_TRADE_BLOCK_UPDATED = "trade_block_updated"

EVT_DRAFT_PICK_MADE = "draft_pick_made"
EVT_DRAFT_YOUR_TURN = "draft_your_turn"
EVT_DRAFT_ON_DECK = "draft_on_deck"
EVT_DRAFT_COMING_UP = "draft_coming_up"
EVT_DRAFT_SCHEDULED = "draft_scheduled"
EVT_DRAFT_COMMISSIONER_PING = "draft_commissioner_ping"

EVT_WAIVER_CLAIM_SUCCESS = "waiver_claim_success"
EVT_PLAYER_TO_WAIVERS = "player_to_waivers"
EVT_PLAYER_DROPPED = "player_dropped"
EVT_NEW_PLAYER_ADDED = "new_player_added"

EVT_LINEUP_LOCK_REMINDER = "lineup_lock_reminder"
EVT_LINEUP_PROBLEM = "lineup_problem"
EVT_PLAYER_INJURED = "player_injured"
EVT_PLAYER_RECOVERED = "player_recovered"
EVT_PLAYER_INJURY_STATUS = "player_injury_status"
EVT_PLAYER_SENT_DOWN = "player_sent_down"
EVT_PLAYER_CALLED_UP = "player_called_up"

EVT_REMINDER_IMPORTANT = "reminder_important"
EVT_RULE_CHANGED = "rule_changed"
EVT_LEAGUE_ADMIN_ACTION = "league_admin_action"
EVT_LEAGUE_CHAT_MESSAGE = "league_chat_message"


CATEGORIES = [
    {"id": "trades", "label": "Trades"},
    {"id": "draft", "label": "Draft Room"},
    {"id": "players", "label": "Player Pool"},
    {"id": "roster", "label": "Roster"},
    {"id": "other", "label": "Other"},
]


EVENTS: List[Dict] = [
    # ── Trades ──────────────────────────────────────────────────────────────
    {"id": EVT_TRADE_PROPOSED, "category": "trades",
     "label": "Trade proposed to you",
     "description": "Another manager sends you a trade offer.",
     "default_channels": ["in_app", "push", "email"]},
    {"id": EVT_TRADE_DECLINED_OR_VETOED_MINE, "category": "trades",
     "label": "Your trade was declined or vetoed",
     "description": "Your trade proposal was rejected, vetoed by a league vote, or overruled by the commissioner.",
     "default_channels": ["in_app", "push", "email"]},
    {"id": EVT_TRADE_VETOED_ANY, "category": "trades",
     "label": "Any trade vetoed in the league",
     "description": "Anyone's trade is vetoed by league vote or commissioner.",
     "default_channels": ["in_app"]},
    {"id": EVT_TRADE_ACCEPTED_MINE, "category": "trades",
     "label": "A trade involving you was accepted",
     "description": "A trade your team is part of has been accepted.",
     "default_channels": ["in_app", "push", "email"]},
    {"id": EVT_TRADE_ACCEPTED_ANY, "category": "trades",
     "label": "Any trade in the league was accepted",
     "description": "Any league trade reaches the accepted state.",
     "default_channels": ["in_app"]},
    {"id": EVT_TRADE_PROCESSED, "category": "trades",
     "label": "Any trade is processed",
     "description": "A trade fully executes — assets swap, contracts move.",
     "default_channels": ["in_app"]},
    {"id": EVT_TRADE_BLOCK_UPDATED, "category": "trades",
     "label": "Trade Block updated by another team",
     "description": "A manager adds or removes a listing on the league trade block.",
     "default_channels": ["in_app"]},

    # ── Draft Room ──────────────────────────────────────────────────────────
    {"id": EVT_DRAFT_PICK_MADE, "category": "draft",
     "label": "Any draft pick made",
     "description": "A pick is registered on the draft board.",
     "default_channels": []},
    {"id": EVT_DRAFT_YOUR_TURN, "category": "draft",
     "label": "Your team is on the clock",
     "description": "It's your team's pick — clock has started.",
     "default_channels": ["in_app", "push", "email"]},
    {"id": EVT_DRAFT_ON_DECK, "category": "draft",
     "label": "Your team is on deck (next pick)",
     "description": "Your team picks immediately after the active pick.",
     "default_channels": ["in_app", "push"]},
    {"id": EVT_DRAFT_COMING_UP, "category": "draft",
     "label": "Your team picks within 5 picks",
     "description": "Get your queue ready — your turn is approaching.",
     "default_channels": ["in_app"]},
    {"id": EVT_DRAFT_SCHEDULED, "category": "draft",
     "label": "A draft has been scheduled",
     "description": "Commissioner has created or rescheduled a draft in this league.",
     "default_channels": ["in_app", "email"]},
    {"id": EVT_DRAFT_COMMISSIONER_PING, "category": "draft",
     "label": "Commissioner pinged you about a draft",
     "description": "The league commissioner nudged you to come back to the draft room while your team was on the clock.",
     "default_channels": ["in_app", "push", "email"]},

    # ── Player Pool ─────────────────────────────────────────────────────────
    {"id": EVT_WAIVER_CLAIM_SUCCESS, "category": "players",
     "label": "You won a waiver claim",
     "description": "Your waiver claim was successfully processed.",
     "default_channels": ["in_app", "push", "email"]},
    {"id": EVT_PLAYER_TO_WAIVERS, "category": "players",
     "label": "A player went on waivers",
     "description": "A new player has entered the waiver pool.",
     "default_channels": ["in_app"]},
    {"id": EVT_PLAYER_DROPPED, "category": "players",
     "label": "A player was dropped",
     "description": "A manager dropped a player to free agency.",
     "default_channels": []},
    {"id": EVT_NEW_PLAYER_ADDED, "category": "players",
     "label": "New player added to pool",
     "description": "A real-world player was added to the league's eligible pool (e.g. mid-season call-up).",
     "default_channels": ["in_app"]},

    # ── Roster ──────────────────────────────────────────────────────────────
    {"id": EVT_LINEUP_LOCK_REMINDER, "category": "roster",
     "label": "Lineup lock time reminder",
     "description": "Heads-up before your weekly/daily lineup locks.",
     "default_channels": ["in_app", "push", "email"]},
    {"id": EVT_LINEUP_PROBLEM, "category": "roster",
     "label": "Lineup problem detected",
     "description": "Your active lineup has empty/invalid slots before lock.",
     "default_channels": ["in_app", "push"]},
    {"id": EVT_PLAYER_INJURED, "category": "roster",
     "label": "Player on your team injured",
     "description": "One of your active players was placed on IR or marked OUT.",
     "default_channels": ["in_app", "push", "email"]},
    {"id": EVT_PLAYER_RECOVERED, "category": "roster",
     "label": "Player recovered from injury",
     "description": "One of your players has returned to active duty.",
     "default_channels": ["in_app"]},
    {"id": EVT_PLAYER_INJURY_STATUS, "category": "roster",
     "label": "Player injury status changed",
     "description": "Status update on a rostered player (e.g. day-to-day → IR-LT).",
     "default_channels": ["in_app"]},
    {"id": EVT_PLAYER_SENT_DOWN, "category": "roster",
     "label": "Player sent down to minors",
     "description": "One of your players was demoted to the minors in real life.",
     "default_channels": ["in_app"]},
    {"id": EVT_PLAYER_CALLED_UP, "category": "roster",
     "label": "Player called up from minors",
     "description": "One of your minor-league players was promoted.",
     "default_channels": ["in_app", "push"]},

    # ── Other ───────────────────────────────────────────────────────────────
    {"id": EVT_REMINDER_IMPORTANT, "category": "other",
     "label": "Important reminders",
     "description": "Upcoming draft, trade deadline, season start, or holiday start time changes.",
     "default_channels": ["in_app", "push", "email"]},
    {"id": EVT_RULE_CHANGED, "category": "other",
     "label": "Commissioner changed a league rule",
     "description": "Scoring, roster, or league setting was modified by the commissioner.",
     "default_channels": ["in_app", "email"]},
    {"id": EVT_LEAGUE_ADMIN_ACTION, "category": "other",
     "label": "Commissioner performed an action affecting the league",
     "description": "League-wide or per-team admin actions (e.g. force-set lineup, override trade).",
     "default_channels": ["in_app"]},
    {"id": EVT_LEAGUE_CHAT_MESSAGE, "category": "other",
     "label": "New message in league chat",
     "description": "A manager posts a new message in the league chat.",
     "default_channels": []},
]


EVENT_IDS = {e["id"] for e in EVENTS}


def default_preferences() -> Dict[str, Dict[str, bool]]:
    """Returns the default preference map for a brand-new user."""
    # Iter 230e — Events seeded with `critical: true` get a free "bypass
    # Quiet Hours" pass when the user enables this channel. We only mark
    # the highest-stakes events critical by default so users in many
    # leagues don't get pinged through their sleep window for low-stakes
    # stuff.
    _DEFAULT_CRITICAL: set = {
        "trade_proposed",
        "trade_accepted_mine",
        "trade_declined_or_vetoed_mine",
        "draft_your_turn",
        "draft_on_deck",
        "lineup_lock_reminder",
        "lineup_problem",
        "waiver_claim_success",
        "reminder_important",
    }
    return {
        e["id"]: {
            "in_app": "in_app" in e["default_channels"],
            "push":   "push"   in e["default_channels"],
            "email":  "email"  in e["default_channels"],
            "critical": e["id"] in _DEFAULT_CRITICAL,
        }
        for e in EVENTS
    }
