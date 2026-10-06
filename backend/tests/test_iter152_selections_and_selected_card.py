"""Iter 152 — Selections tab + own-team-only TB add + SelectedPlayerCard."""
from tests.source_tree import read_source
from pathlib import Path
FRONTEND = Path("/app/frontend/src")


def _read(rel: str) -> str:
    # Iter 171 — DraftRoom.tsx was split into sub-components. To keep
    # grep-style legacy assertions working, returning the concatenation
    # of the parent + extracted draftroom/* files when asked for it.
    if rel.endswith('lovable/pages/DraftRoom.tsx'):
        parts = []
        for sub in (
            'lovable/pages/DraftRoom.tsx',
            'lovable/pages/draftroom/DraftLiveTile.tsx',
            'lovable/pages/draftroom/DraftBoard.tsx',
            'lovable/pages/draftroom/PlayerSearchPanel.tsx',
            'lovable/pages/draftroom/draftConstants.ts',
        ):
            fp = FRONTEND / sub
            if fp.exists():
                parts.append(read_source(fp, encoding='utf-8'))
        return chr(10).join(parts)
    return read_source(FRONTEND / rel, encoding='utf-8')


def test_draft_chat_has_selections_tab():
    src = _read("lovable/pages/draftroom/DraftChatPanel.tsx")
    # 4-column TabsList + new tab + feed body + counter chip
    assert 'grid-cols-4' in src
    assert 'data-testid="draft-chat-tab-selections"' in src
    assert 'data-testid="draft-chat-feed-selections"' in src
    # Selections filter only "pick" type chat messages
    assert 'selectionsOnly' in src
    assert 'm.type === "pick"' in src
    # Chat input is hidden on Selections + Trades tabs
    assert 'tab !== "trades" && tab !== "selections"' in src


def test_trade_block_add_buttons_only_on_my_team_picks():
    src = _read("lovable/pages/DraftRoom.tsx")
    # The gate is back to isMyTile-only — non-owner tiles do NOT render the add button
    assert "tradeBlockMode && !onBlock && isMyTile" in src
    # The OR-on-everything form is gone
    assert 'You can only mark your own picks available' not in src
    # On-block megaphones (display) remain un-gated (visible regardless)
    assert "onBlock = isPlayerOnBlock || isPickOnBlock" in src


def test_selected_player_card_mounted_above_draft_board():
    src = _read("lovable/pages/DraftRoom.tsx")
    assert "import SelectedPlayerCard" in src
    assert "<SelectedPlayerCard" in src
    # State + selection wiring
    assert "selectedPlayerId" in src
    assert "setSelectedPlayerId" in src
    # Component has the required testids
    panel = _read("lovable/pages/draftroom/SelectedPlayerCard.tsx")
    for tid in (
        "draft-room-selected-card-empty",
        "draft-room-selected-card-headshot",
        "draft-room-selected-card-name",
        "draft-room-selected-card-adp",
        "draft-room-selected-card-statline",
        "draft-room-selected-card-draft-btn",
        "draft-room-selected-card-shortlist",
        "draft-room-selected-card-queue",
        "draft-room-selected-card-close",
    ):
        assert f'data-testid="{tid}"' in panel, f"Missing {tid}"
    # Stat line includes minor-league fields
    for label in ('"GP"', '"G"', '"A"', '"P"', '"+/-"', '"PIM"', '"SOG"'):
        assert label in panel
    # ADP surfaced
    assert "ADP" in panel


def test_eligible_player_row_click_selects_player():
    src = _read("lovable/pages/DraftRoom.tsx")
    # Clicking the row sets selectedPlayerId
    assert "onClick={() => setSelectedPlayerId(String(player.id))}" in src
    # Star + ListOrdered button clicks stop bubble so they don't trigger row-select
    assert "e.stopPropagation(); toggleShortlist(player.id)" in src
    assert "e.stopPropagation(); toggleQueue(player.id)" in src
