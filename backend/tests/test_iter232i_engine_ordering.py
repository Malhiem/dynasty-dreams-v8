"""Iter 232i — Functional tests for the bonus-picks-aware draft engine.

Guards the `get_team_for_pick` behaviour when bonus picks are layered
on top of the standard rounds × teams grid. Static string checks catch
regressions in wiring; these tests catch regressions in *ordering*.
"""
from draft_engine import get_team_for_pick, total_picks_in_draft


TEAMS_ABBR = ["A", "B", "C", "D"]  # 4 teams


def test_no_bonus_picks_preserves_snake_ordering():
    # Snake: R1 = A,B,C,D  R2 = D,C,B,A  R3 = A,B,C,D
    assert get_team_for_pick(TEAMS_ABBR, 1, True) == "A"
    assert get_team_for_pick(TEAMS_ABBR, 4, True) == "D"
    assert get_team_for_pick(TEAMS_ABBR, 5, True) == "D"  # first pick of R2
    assert get_team_for_pick(TEAMS_ABBR, 8, True) == "A"  # last pick of R2


def test_no_bonus_picks_preserves_linear_ordering():
    # Linear: every round A,B,C,D
    assert get_team_for_pick(TEAMS_ABBR, 1, False) == "A"
    assert get_team_for_pick(TEAMS_ABBR, 5, False) == "A"
    assert get_team_for_pick(TEAMS_ABBR, 8, False) == "D"


def test_bonus_pick_returns_that_team_at_its_overall_position():
    # Bonus pick for team A at overall #3.
    bonus = [{"team_abbr": "A", "overall": 3}]
    assert get_team_for_pick(TEAMS_ABBR, 3, True, bonus) == "A"


def test_bonus_pick_shifts_downstream_picks_by_one():
    """With a bonus at overall #3 in a snake draft, the pick that was
    at #3 (team C) shifts to #4, and every subsequent pick shifts
    forward by one. Rounds themselves don't compress — the formula
    still operates on the *effective* pick number."""
    bonus = [{"team_abbr": "A", "overall": 3}]
    # Pre-bonus positions still return their original teams.
    assert get_team_for_pick(TEAMS_ABBR, 1, True, bonus) == "A"
    assert get_team_for_pick(TEAMS_ABBR, 2, True, bonus) == "B"
    # Bonus at 3.
    assert get_team_for_pick(TEAMS_ABBR, 3, True, bonus) == "A"
    # Post-bonus: original #3 (C) shifted to #4, #4 (D) to #5.
    assert get_team_for_pick(TEAMS_ABBR, 4, True, bonus) == "C"
    assert get_team_for_pick(TEAMS_ABBR, 5, True, bonus) == "D"
    # First pick of round 2 is now at overall #6 (was #5).
    assert get_team_for_pick(TEAMS_ABBR, 6, True, bonus) == "D"


def test_multiple_bonus_picks_stack_offsets():
    """Two bonus picks before position #7 → the pick at #7 must
    behave as if it were at effective position #5 in the snake grid."""
    bonus = [
        {"team_abbr": "B", "overall": 2},
        {"team_abbr": "D", "overall": 4},
    ]
    # Bonus #2 → team B.
    assert get_team_for_pick(TEAMS_ABBR, 2, True, bonus) == "B"
    # Bonus #4 → team D.
    assert get_team_for_pick(TEAMS_ABBR, 4, True, bonus) == "D"
    # Position 7 now maps to effective 5 (first pick of R2 snake) = D.
    assert get_team_for_pick(TEAMS_ABBR, 7, True, bonus) == "D"
    # Position 8 → effective 6 (second pick of R2 snake, reversed) = C.
    assert get_team_for_pick(TEAMS_ABBR, 8, True, bonus) == "C"


def test_total_picks_helper():
    # Plain draft.
    assert total_picks_in_draft(TEAMS_ABBR, 5) == 20
    # Bonus picks add to the total.
    bonus = [{"overall": 3}, {"overall": 12}]
    assert total_picks_in_draft(TEAMS_ABBR, 5, bonus) == 22
    # No bonuses arg treats it the same as empty list.
    assert total_picks_in_draft(TEAMS_ABBR, 5, []) == 20
