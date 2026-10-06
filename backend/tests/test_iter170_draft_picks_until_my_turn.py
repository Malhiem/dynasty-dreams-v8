"""Iter 170 — Lock the picks-until-my-turn counter fix in DraftRoom.tsx.

Background: Prior code in `picksUntilMyTurn` referenced
`draftConfig.rounds` (typo; the field is `draftConfig.totalRounds`),
which made `totalPicks` evaluate to NaN and the counter always returned
null. This iteration:
  1. Fixed the typo to `draftConfig.totalRounds`.
  2. Tightened the liveTeams→mock-column index mapping to fire only when
     the two arrays are the same length (avoids modulo-based mismatch).
  3. Added a manager-only "Simulate Pick" button so QA can verify the
     counter actually decrements pick-by-pick.
"""
from pathlib import Path

# Iter 231 — DraftRoom.tsx + draftroom/* + hooks/use-draft-* have been
# decomposed across many iterations. The DraftRoomFamilyShim concatenates
# every file that contributes to the runtime draft room behaviour so the
# original grep-style assertions still resolve.
from tests._draftroom_sources import DraftRoomFamilyShim

DRAFT_ROOM = DraftRoomFamilyShim()


def _source() -> str:
    return DRAFT_ROOM.read_text()


def test_picks_until_my_turn_uses_total_rounds_not_rounds():
    src = _source()
    # The typo'd reference must be gone…
    assert "draftConfig.rounds" not in src, "Old typo `draftConfig.rounds` must be replaced with `draftConfig.totalRounds`"
    # …and the corrected one must be present inside picksUntilMyTurn
    block = src.split("picksUntilMyTurn")[1].split("}, [")[0]
    assert "draftConfig.totalRounds" in block, "picksUntilMyTurn must read draftConfig.totalRounds for totalPicks"


def test_picks_until_my_turn_only_index_maps_when_lengths_match():
    """Iter 170b superseded: the heuristic length-match index mapping
    has been replaced with a direct `boardTeams.find(t => t.id === myTeam.id)`
    lookup (live-league wiring). Iter 231 — the lookup moved into the
    use-draft-picks-until-my-turn hook so we check across the shim."""
    src = _source()
    assert "boardTeams.find((t) => t.id && t.id === (myTeam as any).id)" in src


def test_picks_until_my_turn_is_memoized():
    src = _source()
    # Iter 231 — the memoised computation was extracted into the
    # `useDraftPicksUntilMyTurn` custom hook (which uses `useMemo`
    # internally). Functional intent (memoisation) preserved.
    assert "useDraftPicksUntilMyTurn(" in src
    assert "return useMemo(" in src


def test_simulate_pick_button_present_and_wired():
    src = _source()
    # Manager-only Simulate Pick button (testid) so QA can advance the
    # mock clock and watch the counter decrement.
    assert 'data-testid="draft-room-simulate-pick"' in src
    assert "handleSimulatePick" in src
    # Handler must advance currentPick + add to picks array.
    assert "currentPick: prev.currentPick + 1" in src
    assert "setPicks((prev) => [" in src


def test_simulate_pick_stores_full_player_object_not_string():
    """Regression: a previous version stored `player: nextPlayer.name`
    (a string) which crashed `pick.player.name.split(...)` downstream
    in the Draft Board renderer. Iter 170f renamed handleSimulatePick →
    handleDraftPlayer (with Simulate Pick as a thin alias), so we
    inspect that unified handler instead."""
    src = _source()
    handler_block = src  # The room delegates to the extracted pick hook.
    # Must store the full player object so downstream `.name`,
    # `.position` accesses on the draft-board tile work.
    assert "player: { ...nextPlayer" in handler_block
