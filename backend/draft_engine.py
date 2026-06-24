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


def get_draft_order(team_abbrs: list[str], round_num: int, snake: bool) -> list[str]:
    """Get team order for a specific round, handling snake draft reversal."""
    if snake and round_num % 2 == 0:
        return list(reversed(team_abbrs))
    return list(team_abbrs)


def get_team_for_pick(team_abbrs: list[str], overall_pick: int, snake: bool) -> str:
    """Determine which team picks at a given overall pick number."""
    total_teams = len(team_abbrs)
    round_num = ((overall_pick - 1) // total_teams) + 1
    pick_in_round = (overall_pick - 1) % total_teams
    order = get_draft_order(team_abbrs, round_num, snake)
    return order[pick_in_round]


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
