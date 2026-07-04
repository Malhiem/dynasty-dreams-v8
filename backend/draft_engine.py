"""
Draft Engine - Backend logic for the Dynasty Dreams draft room.
Handles draft lifecycle, pick management, timer, snake ordering, and WebSocket events.
"""
from datetime import datetime, timezone, timedelta
from typing import Optional
from pydantic import BaseModel, Field
from enum import Enum


class DraftType(str, Enum):
    STARTUP = "startup"
    ENTRY = "entry"
    SUPPLEMENTAL = "supplemental"
    EXPANSION = "expansion"


class DraftStatus(str, Enum):
    SCHEDULED = "scheduled"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"


class MissedPickAction(str, Enum):
    AUTO_SELECT = "auto-select"
    PICK_ANYTIME = "pick-anytime"


# Request/Response models
class CreateDraftRequest(BaseModel):
    league_id: str
    draft_type: str = "entry"
    # Iter 228d — optional human-readable name (e.g. "TFHL Inaugural Draft")
    name: Optional[str] = None
    scheduled_time: Optional[str] = None
    # Iter 228d — raise rounds cap from 30 → 100 so dynasty leagues can
    # draft the FULL roster (active + bench + minors). Backend enforces
    # the league's actual roster_size at create-time as a soft validation.
    total_rounds: int = Field(default=5, ge=1, le=100)
    time_per_pick: int = Field(default=3600, ge=30, le=86400)
    # Iter 232N.26 — Optional per-manager pick-timer cap that runs
    # CONCURRENTLY with `time_per_pick`. When shorter than the main
    # clock (e.g. 10h personal on a 15h league clock), auto-pick fires
    # as soon as the personal timer expires — using the on-clock team's
    # `auto_pick_preference` (queue-then-best OR best-only). None or
    # zero disables the feature (legacy behaviour).
    personal_pick_timer_seconds: Optional[int] = Field(default=None, ge=30, le=86400)
    # Iter 228d — per-round time overrides. Each entry: {from, to, seconds}.
    # Inclusive range. Frontend lets commissioners define tiered defaults
    # (e.g. R1-5 = 7200s, R6-30 = 3600s) via the multi-row + button.
    round_time_overrides: list[dict] = Field(default_factory=list)
    snake_draft: bool = True
    player_criteria: list[str] = Field(default_factory=lambda: ["all"])
    missed_pick_action: str = "auto-select"
    # Iter 228d — new sub-options for missed_pick_action="defer-to-user".
    # Picked by the manager in the draft room. Default kept here so the
    # frontend can pre-fill.
    defer_user_options: list[str] = Field(default_factory=lambda: [
        "auto-best", "auto-queue", "pick-anytime",
    ])
    # Iter 228d — multi-criteria "When window elapses" (OR semantics).
    # Values: "admin_approval", "majority_vote".
    window_elapsed_actions: list[str] = Field(default_factory=list)
    # Iter 228h — Pick trading + when the window opens to teams.
    pick_trading_enabled: bool = False
    trading_window_opens: str = "immediately"
    # Iter 228h — Draft clock daily window with timezone awareness
    clock_timezone: Optional[str] = None  # IANA name, e.g. "America/New_York"
    clock_starts_at: Optional[str] = None  # "HH:MM"
    clock_stops_at: Optional[str] = None   # "HH:MM"
    # Iter 228n — Eligibility filters surfaced as draft-config checkboxes.
    # `exclude_previously_drafted` removes any player ever drafted by ANY
    # team in this league (full historical audit). `minors_eligibility_required`
    # restricts the eligible pool to players flagged `minor_eligible: true`.
    exclude_previously_drafted: bool = False
    minors_eligibility_required: bool = False


class MakeDraftPickRequest(BaseModel):
    player_id: str


class DraftChatRequest(BaseModel):
    text: str


class UpdateDraftConfigRequest(BaseModel):
    time_per_pick: Optional[int] = None
    total_rounds: Optional[int] = None
    snake_draft: Optional[bool] = None
    player_criteria: Optional[list[str]] = None
    missed_pick_action: Optional[str] = None
    # Iter 232N.26 — Commissioner can retune the personal timer mid-draft.
    personal_pick_timer_seconds: Optional[int] = Field(default=None, ge=0, le=86400)


def get_draft_order(team_abbrs: list[str], round_num: int, snake: bool) -> list[str]:
    """Get team order for a specific round, handling snake draft reversal."""
    if snake and round_num % 2 == 0:
        return list(reversed(team_abbrs))
    return list(team_abbrs)


def get_team_for_pick(
    team_abbrs: list[str],
    overall_pick: int,
    snake: bool,
    bonus_picks: Optional[list[dict]] = None,
) -> str:
    """Determine which team picks at a given overall pick number.

    Iter 232i — Extended to honour commissioner-granted **bonus picks**
    (compensation / expansion). A bonus pick is a `{overall, team_abbr}`
    record layered on top of the standard snake ordering:

      • If `overall_pick` matches a bonus pick's `overall`, the bonus
        team is on the clock — return its abbr directly.
      • Otherwise, we still consult the snake formula but on the
        *effective* pick number, which is `overall_pick` minus the
        count of bonus picks that fall BEFORE it. That way inserting
        a bonus at overall=13 doesn't distort the round-2 slot order
        that would otherwise have started at 13 — those picks simply
        shift forward by one and the original snake pattern resumes.

    `bonus_picks` is optional so every existing call site continues
    to work unchanged.
    """
    total_teams = len(team_abbrs)
    if bonus_picks:
        # Exact match — bonus team is on the clock.
        for bp in bonus_picks:
            if int(bp.get("overall", 0)) == overall_pick:
                return str(bp.get("team_abbr") or "")
        # Subtract the count of bonus picks that fall BEFORE us so
        # the standard formula operates on the un-inserted pick #.
        offset = sum(1 for bp in bonus_picks if int(bp.get("overall", 0)) < overall_pick)
        effective_pick = overall_pick - offset
    else:
        effective_pick = overall_pick
    round_num = ((effective_pick - 1) // total_teams) + 1
    pick_in_round = (effective_pick - 1) % total_teams
    order = get_draft_order(team_abbrs, round_num, snake)
    return order[pick_in_round]


def total_picks_in_draft(
    team_abbrs: list[str],
    total_rounds: int,
    bonus_picks: Optional[list[dict]] = None,
) -> int:
    """Iter 232i — Total number of picks the draft will ultimately
    make, honouring any commissioner-granted bonus picks. Used to
    detect the draft-complete transition when a league has extras
    layered on top of the standard `rounds × teams` grid."""
    base = int(total_rounds) * len(team_abbrs)
    extras = len(bonus_picks or [])
    return base + extras


def build_draft_board(team_abbrs: list[str], total_rounds: int, snake: bool, picks: list[dict]) -> list[list[dict]]:
    """Build the full draft board grid with picks filled in."""
    total_teams = len(team_abbrs)
    board = []

    pick_map = {}
    for p in picks:
        pick_map[p["overall"]] = p

    for r in range(1, total_rounds + 1):
        order = get_draft_order(team_abbrs, r, snake)
        round_picks = []
        for idx, team in enumerate(order):
            overall = (r - 1) * total_teams + idx + 1
            existing = pick_map.get(overall)
            if existing:
                round_picks.append(existing)
            else:
                round_picks.append({
                    "round": r,
                    "pick_in_round": idx + 1,
                    "overall": overall,
                    "team": team,
                    "player": None
                })
        board.append(round_picks)

    return board
