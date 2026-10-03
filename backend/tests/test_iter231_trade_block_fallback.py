"""Iter 231 — Trade Block card thumbnail fallback.

Ensures `TradeBlockCard.tsx` no longer renders an empty 12×12 thumb when
a player listing is missing its NHL team abbr. We now derive initials
from the player name and ensure the list view falls back to "—" too.
"""
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CARD = REPO / "frontend/src/lovable/pages/trade-block/TradeBlockCard.tsx"
LIST = REPO / "frontend/src/lovable/pages/trade-block/TradeBlockListView.tsx"


def test_card_uses_initials_fallback():
    src = CARD.read_text()
    assert "playerInitials" in src, "TradeBlockCard must compute player initials fallback"
    assert "thumbContent" in src
    # The old direct render must be gone
    assert '{item.type === "pick" ? "📋" : item.team}' not in src
    # New testable thumb element
    assert "trade-block-thumb-" in src


def test_list_uses_dash_fallback_for_team():
    src = LIST.read_text()
    assert "{item.team || \"—\"}" in src, "Trade Block list view should show — when team is missing"
