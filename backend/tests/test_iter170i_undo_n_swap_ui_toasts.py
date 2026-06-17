"""Iter 170i — Polish layer on top of Iter 170h commissioner powers:

  (1) "Undo N picks" UI — a small number input next to the Undo button
      so commissioners can roll back multiple picks at once.
  (2) Swap Player UI — every drafted pick tile now has a tiny ↔ button
      that opens a Popover with a player search/list. Commissioner-only.
  (3) Toast notifications for remote WebSocket events — when ANOTHER
      manager picks / undoes / swaps, the receiver sees a toast. Self
      actions are deduped via a `lastSelfPickRef` so we don't double-
      toast our own picks (already toasted by the local handler).
"""
from pathlib import Path

# Iter 171 — DraftRoom.tsx parent was refactored. Draft Live tile + Draft Board
# JSX now live in /draftroom/DraftLiveTile.tsx + DraftBoard.tsx. We treat
# `DRAFT_ROOM.read_text()` as the concatenation of the parent and the
# extracted subcomponents so existing grep-style assertions keep passing.
def _read_draftroom_family() -> str:
    from pathlib import Path as _P
    paths = [
        _P("/app/frontend/src/lovable/pages/DraftRoom.tsx"),
        _P("/app/frontend/src/lovable/pages/draftroom/DraftLiveTile.tsx"),
        _P("/app/frontend/src/lovable/pages/draftroom/DraftBoard.tsx"),
        _P("/app/frontend/src/lovable/pages/draftroom/PlayerSearchPanel.tsx"),
        _P("/app/frontend/src/lovable/pages/draftroom/draftConstants.ts"),
    ]
    return chr(10).join(p.read_text() for p in paths if p.exists())


class _DraftRoomShim:
    def read_text(self) -> str:
        return _read_draftroom_family()


DRAFT_ROOM = _DraftRoomShim()


def _src() -> str:
    return DRAFT_ROOM.read_text()


# ─── (1) Undo N picks UI ─────────────────────────────────────────────


def test_undo_count_state_and_input():
    src = _src()
    assert "const [undoCount, setUndoCount] = useState<number>(1)" in src
    assert 'data-testid="draft-room-undo-bar"' in src
    assert 'data-testid="draft-room-undo-count"' in src
    # Button label switches between singular / plural with the count.
    assert "Undo Last Pick" in src
    assert "Undo ${undoCount} Picks" in src
    # Clamps to [1, picks.length] to prevent invalid inputs.
    assert "Math.max(1, Math.min(picks.length, parseInt(e.target.value || \"1\", 10)))" in src


def test_undo_handler_uses_state_count():
    src = _src()
    # The button calls handleUndoPicks(undoCount), not a fixed 1.
    assert "onClick={() => handleUndoPicks(undoCount)}" in src


# ─── (2) Swap Player UI ──────────────────────────────────────────────


def test_swap_state_and_popover_on_each_tile():
    src = _src()
    assert "const [swapPickOverall, setSwapPickOverall] = useState<number | null>(null)" in src
    assert 'const [swapSearch, setSwapSearch] = useState<string>("")' in src
    # Trigger button is rendered per-pick — commissioner-only.
    assert 'data-testid={`draft-board-swap-btn-${pick.overall}`}' in src
    # Search input + per-option buttons keyed by player id.
    assert 'data-testid="draft-board-swap-search"' in src
    assert 'data-testid={`draft-board-swap-option-${p.id}`}' in src
    # Calls the existing handleSwapPickPlayer with the pick + new id.
    assert "await handleSwapPickPlayer(pick.overall, String(p.id))" in src
    # Filter — undrafted only + case-insensitive name/position match.
    assert "!p.drafted && (!swapSearch || p.name.toLowerCase().includes(swapSearch.toLowerCase())" in src


def test_swap_popover_commissioner_gated():
    src = _src()
    # The Popover block is wrapped in `{isLeagueManager && (...)}`.
    swap_block = src.split('data-testid={`draft-board-swap-btn-${pick.overall}`}')[0]
    # The most recent `{isLeagueManager &&` before that testid must be
    # the gate for the popover.
    last_gate = swap_block.rfind("{isLeagueManager && (")
    assert last_gate != -1
    after_gate = swap_block[last_gate:]
    assert "Popover" in after_gate


# ─── (3) Toast notifications for remote events ───────────────────────


def test_toast_on_remote_pick_dedupes_self():
    src = _src()
    # Self-pick signature ref + stamp + dedupe check.
    assert "const lastSelfPickRef = useRef<string | null>(null)" in src
    assert "lastSelfPickRef.current = `${draftConfig.currentPick}-${nextPlayer.id}`" in src
    # The draft_pick listener forms a signature and skips when it matches.
    pick_listener = src.split("draft_pick: (p: any) => {")[1].split("draft_undo:")[0]
    assert "const sig = `${p?.overall}-${p?.player_id}`" in pick_listener
    assert "sig !== lastSelfPickRef.current" in pick_listener
    assert "toast.info(" in pick_listener


def test_toast_on_remote_undo_and_swap():
    src = _src()
    # Undo listener surfaces a warning with the new on-the-clock team.
    undo_listener = src.split("draft_undo: (p: any) => {")[1].split("draft_pick_swapped:")[0]
    assert "toast.warning(" in undo_listener
    assert "Commissioner undid ${count} pick" in undo_listener
    # Swap listener surfaces a warning with the replacement name.
    swap_listener = src.split("draft_pick_swapped: (p: any) => {")[1].split("draft_chat:")[0]
    assert "toast.warning(" in swap_listener
    assert "Commissioner swapped pick #${p?.overall}" in swap_listener
