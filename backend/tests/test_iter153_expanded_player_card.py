"""Iter 153 — Expanded player card via PlayerCardModal + layout fixes."""
from pathlib import Path
FRONTEND = Path("/app/frontend/src")


def _read(rel: str) -> str:
    return (FRONTEND / rel).read_text(encoding="utf-8")


def test_player_card_modal_has_open_full_page_link():
    src = _read("lovable/components/dashboard/PlayerCardModal.tsx")
    # External-link icon imported
    assert "ExternalLink" in src
    # Testid on the link
    assert 'data-testid="player-card-expand-link"' in src
    # Opens in a new tab
    assert 'target="_blank"' in src
    # Points at the canonical /players/{id} route
    assert "`/players/${(player as any).id}`" in src


def test_selected_player_card_invokes_modal_on_expand():
    src = _read("lovable/pages/DraftRoom.tsx")
    # Modal mounted
    assert "PlayerCardModal" in src
    assert "<PlayerCardModal" in src
    # Expanded-player state + expand wiring
    assert "expandedPlayer" in src
    assert "setExpandedPlayer" in src
    assert "onExpand={(p) => setExpandedPlayer(p)}" in src

    panel = _read("lovable/pages/draftroom/SelectedPlayerCard.tsx")
    # Expand button on the inline card
    assert 'data-testid="draft-room-selected-card-expand"' in panel
    assert "Maximize2" in panel


def test_selected_card_layout_is_constrained_and_taller():
    """Card must end where the draft clock begins — not span under it.
    It now sits *inside* the left flex item of the header row, with the
    Timer card to the right (min-w-[320px] still pins the clock width).
    The card uses h-full + min-h to fill the open vertical space."""
    src = _read("lovable/pages/DraftRoom.tsx")
    # SelectedPlayerCard mounted inside the left flex item, not as a
    # standalone full-width row above the Draft Board.
    assert "Iter 153 — SelectedPlayerCard sits *inside* the left flex item" in src
    # The old standalone placement above the Draft Board is gone
    assert "Iter 152 — Selected Player Card (above Draft Board)" not in src
    # Component itself has h-full + min-h-[200px]
    panel = _read("lovable/pages/draftroom/SelectedPlayerCard.tsx")
    assert "h-full min-h-[200px]" in panel
