"""
Iter 164 — Draft Board owner-pick filter.

Commissioners can multi-toggle team chips at the top of the Draft Board
to highlight that team's owned picks (and dim others) — useful when
verifying which picks each franchise controls heading into the draft.

Static-asserts the toggle UI is wired and the highlight/dim classes are
applied based on the active selection.
"""
from pathlib import Path

# Iter 171 — DraftRoom.tsx was split into sub-components. Resolve the legacy
# "read the entire draft room source" pattern as the concatenation of the
# parent + extracted draftroom/* files so existing grep-style assertions
# keep working without rewriting every spec.
def _iter171_draftroom_concat() -> str:
    from pathlib import Path as _P
    paths = [
        _P("/app/frontend/src/lovable/pages/DraftRoom.tsx"),
        _P("/app/frontend/src/lovable/pages/draftroom/DraftLiveTile.tsx"),
        _P("/app/frontend/src/lovable/pages/draftroom/DraftBoard.tsx"),
        _P("/app/frontend/src/lovable/pages/draftroom/PlayerSearchPanel.tsx"),
        _P("/app/frontend/src/lovable/pages/draftroom/draftConstants.ts"),
    ]
    return chr(10).join(p.read_text() for p in paths if p.exists())


class _Iter171DraftRoomShim:
    def read_text(self, *a, **kw) -> str:
        return _iter171_draftroom_concat()


def _iter171_install_shim_after_imports():
    pass


DR = _Iter171DraftRoomShim()


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
