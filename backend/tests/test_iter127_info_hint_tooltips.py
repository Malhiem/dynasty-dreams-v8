"""Iter 127 — Superscript "ⓘ" InfoHint tooltips on league administration settings.

Coverage
--------
1. `info-hint.jsx` component exists at the canonical UI library path.
2. TransactionsConfigCards imports InfoHint and wires it onto:
   - Claims Limits card title + Per Season + Per Week headers
   - Claim Rules card title + lock_at_first_game + allow_non_playoff
     + prevent_injured RadioGroup
   - Free Agency / Waivers / Draft card titles
   - Waiver Wire System dropdown
   - FAAB Customization + FAAB Budget + Waiver Clearing Period inputs
   - Priority Order section
3. RulesScheduleTab imports InfoHint and wires it onto:
   - Every helper-driven SectionSpec field (via the generic Label block)
   - Salary Cap enabled toggle + Cap Floor enabled toggle
   - Salary Retention master toggle + Contract Buyouts title
4. InfoHint renders the lucide Info icon (cyan/300) and uses Tooltip
   from the shadcn UI primitive for accessible keyboard / mobile reveal.
"""
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
INFO_HINT = REPO / "frontend/src/components/ui/info-hint.jsx"
TX_CARDS = REPO / "frontend/src/lovable/pages/commissioner/TransactionsConfigCards.tsx"
RULES_TAB = REPO / "frontend/src/lovable/pages/commissioner/RulesScheduleTab.tsx"


def test_info_hint_component_present():
    assert INFO_HINT.exists(), "info-hint.jsx must exist"
    src = INFO_HINT.read_text()
    assert "from \"lucide-react\"" in src, "InfoHint should import lucide Info icon"
    assert "Info" in src, "InfoHint must use lucide Info icon"
    assert "TooltipProvider" in src, "InfoHint must use shadcn Tooltip primitive"
    # Keyboard / a11y affordances
    assert "aria-label" in src, "InfoHint must have aria-label for screen readers"
    assert "cursor-help" in src, "InfoHint must use the help cursor"


def test_transactions_config_wires_info_hints():
    src = TX_CARDS.read_text()
    assert 'import InfoHint from "@/components/ui/info-hint"' in src, (
        "TransactionsConfigCards must import InfoHint"
    )
    expected_testids = [
        "info-claims-limits",
        "info-claims-season",
        "info-claims-week",
        "info-claim-rules",
        "info-lock-at-first-game",
        "info-allow-non-playoff",
        "info-prevent-injured",
        "info-free-agency",
        "info-waivers",
        "info-draft-day-transactions",
        "info-waiver-system-type",
        "info-faab-customization",
        "info-faab-budget",
        "info-clearing-period",
        "info-priority-order",
    ]
    for tid in expected_testids:
        assert tid in src, f"Expected InfoHint testid {tid!r} in TransactionsConfigCards"


def test_rules_schedule_tab_wires_info_hints():
    src = RULES_TAB.read_text()
    assert 'import InfoHint from "@/components/ui/info-hint"' in src, (
        "RulesScheduleTab must import InfoHint"
    )
    # Generic field helper → testId={`info-${field.key}`}
    assert "info-${field.key}" in src, "Generic per-field info hint must be wired"
    # Per-toggle hints
    for tid in (
        "info-cap-enabled",
        "info-cap-floor-enabled",
        "info-retention-enabled",
        "info-contract-buyouts",
    ):
        assert tid in src, f"Expected InfoHint testid {tid!r} in RulesScheduleTab"
