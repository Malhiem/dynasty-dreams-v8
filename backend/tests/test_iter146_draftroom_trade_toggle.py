"""Iter 146 — Propose Trade toggle in Draft Room (mirrors Draft Board).

When the toggle is ON, every pick cell (made or upcoming) renders a
small Repeat icon that opens the TradeBuilder and queues that pick.

This test pins the wiring to the file so future refactors can't drop
the trade flow without notice.
"""
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DRAFT_ROOM = REPO / "frontend/src/pages/DraftRoomPage.jsx"


def test_draft_room_trade_toggle_present():
    src = DRAFT_ROOM.read_text()
    # Toggle button + label states
    assert 'data-testid="draft-room-trade-toggle"' in src
    assert "Trade Mode: ON" in src
    assert '"Propose Trade"' in src
    # Trade-mode state + handler
    assert "const [tradeMode" in src
    assert "handleAddDraftPickToTrade" in src
    # Trade builder + sonner imports
    assert "useTradeBuilder" in src
    assert 'from "sonner"' in src
    # Per-pick trade icon testid with template literal
    assert "draft-room-pick-trade-${pick.team}-${pick.overall}" in src
    # Repeat icon imported
    assert "Repeat" in src


def test_handler_uses_trade_builder_api():
    src = DRAFT_ROOM.read_text()
    # The handler must call openBuilder + addPick — same API as Draft Board
    assert "tradeBuilder.openBuilder(" in src
    assert "tradeBuilder.addPick(" in src
    # Adds round + overall + ownerTeamName for the trade label
    assert "ownerTeamName" in src
    assert "originalTeamName" in src
