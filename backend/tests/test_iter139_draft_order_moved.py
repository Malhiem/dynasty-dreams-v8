"""Iter 139 — Draft order configuration moved to League Administration.

The Draft Board's "Draft Order Results" tab is now read-only and reads
the saved settings; the configuration UI (method radio + per-method
scheduling) lives in League Administration → Draft via the new
`DraftOrderConfigCard` component.
"""
from tests.source_tree import read_source
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CARD = REPO / "frontend/src/lovable/pages/commissioner/DraftOrderConfigCard.tsx"
ADMIN = REPO / "frontend/src/lovable/pages/CommissionerSettings.tsx"
DRAFT = REPO / "frontend/src/lovable/pages/DraftBoard.tsx"


# ── 1. New reusable card exists ────────────────────────────────
def test_draft_order_config_card_exists():
    assert CARD.exists(), "DraftOrderConfigCard.tsx must exist"
    src = read_source(CARD)
    assert "export default function DraftOrderConfigCard" in src
    # All three methods
    for m in ("nhl_lottery", "lottery_generator", "manual_entry"):
        assert f'"{m}"' in src, f"Method {m!r} missing"
    # Commissioner save endpoint + system date endpoint
    assert "/leagues/${leagueId}/draft-order/config" in src
    assert "/admin/draft-lottery-date" in src
    # Card testid + per-method blocks + save buttons
    assert 'data-testid="draft-order-config-card"' in src
    assert 'data-testid="draft-order-method-radio"' in src
    assert 'data-testid="draft-order-nhl-block"' in src
    assert 'data-testid="draft-order-league-block"' in src
    assert 'data-testid="draft-order-save-config"' in src
    assert 'data-testid="draft-order-save-system-date"' in src


# ── 2. Mounted in League Administration → Draft tab ────────────
def test_card_mounted_in_league_admin():
    # Iter 157 — Draft tab body extracted to DraftTab.tsx
    draft_tab = REPO / "frontend/src/lovable/pages/commissioner/tabs/DraftTab.tsx"
    draft_src = read_source(draft_tab)
    assert 'import DraftOrderConfigCard from "@/lovable/pages/commissioner/DraftOrderConfigCard"' in draft_src, \
        "DraftOrderConfigCard import missing in DraftTab"
    assert "<DraftOrderConfigCard" in draft_src, "Card not rendered inside Draft tab"
    assert "<TransactionsDraftRulesCard" in draft_src, "Legacy draft rules card missing from Draft tab"


# ── 3. Draft Board "Draft Order Results" tab is now read-only ──
def test_draft_board_results_tab_read_only():
    src = read_source(DRAFT, include_imports=False)
    # Inline configuration UI is GONE from DraftBoard
    assert 'data-testid="draft-order-method-radio"' not in src, \
        "Method radio must no longer live on the Draft Board"
    assert 'data-testid="draft-order-save-config"' not in src, \
        "Save button must not be on the Draft Board"
    assert 'data-testid="draft-order-save-system-date"' not in src, \
        "System-admin save button must not be on the Draft Board"
    # Read-only summary is in its extracted component; configuration stays absent above.
    src = read_source(DRAFT)
    # Read-only summary card is present + link to League Admin
    assert 'data-testid="draft-order-summary-card"' in src
    assert 'data-testid="draft-order-summary-status"' in src
    assert 'data-testid="draft-order-summary-scheduled"' in src
    assert 'data-testid="draft-order-summary-method"' in src
    assert 'data-testid="draft-order-admin-hint"' in src
    assert 'data-testid="draft-order-admin-link"' in src
    assert 'href="/commissioner/settings"' in src
    # Results card with rows still rendered
    assert 'data-testid="draft-order-results-card"' in src
    assert "draft-order-row-${idx + 1}" in src
