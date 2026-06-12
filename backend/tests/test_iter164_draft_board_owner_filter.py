"""
Iter 164 — Draft Board owner-pick filter.

Commissioners can multi-toggle team chips at the top of the Draft Board
to highlight that team's owned picks (and dim others) — useful when
verifying which picks each franchise controls heading into the draft.

Static-asserts the toggle UI is wired and the highlight/dim classes are
applied based on the active selection.
"""
from pathlib import Path

DR = Path("/app/frontend/src/lovable/pages/DraftRoom.tsx")


def test_draft_board_owner_filter_state_declared():
    src = DR.read_text()
    # State hook
    assert "const [selectedOwnerAbbrs, setSelectedOwnerAbbrs] = useState<Set<string>>(new Set())" in src
    # Multi-select toggle (add/remove from Set)
    assert "if (next.has(abbr)) next.delete(abbr);" in src
    assert "else next.add(abbr);" in src


def test_draft_board_owner_chip_row_renders_per_team():
    src = DR.read_text()
    # Filter container testid
    assert 'data-testid="draft-board-owner-filter"' in src
    # Per-team chip
    assert "draft-board-owner-chip-${abbr}" in src
    # Aria pressed state
    assert "aria-pressed={isOn}" in src
    # Clear-all button shown when selection is non-empty
    assert 'data-testid="draft-board-owner-clear"' in src


def test_tile_dim_and_highlight_classes_applied():
    src = DR.read_text()
    # Iter 166 — filter now resolves via _currentOwnerAbbrs (current owner),
    # not the column header abbr. Test the new logic.
    assert "currentOwnerAbbrs.some((a: string) => selectedOwnerAbbrs.has(a))" in src
    assert "isDimmedByFilter = ownerFilterActive && !isOwnedBySelected" in src
    # Visual classes still applied
    assert 'isOwnedBySelected && "ring-2 ring-primary/70 border-primary/50"' in src
    assert 'isDimmedByFilter && "opacity-30"' in src
