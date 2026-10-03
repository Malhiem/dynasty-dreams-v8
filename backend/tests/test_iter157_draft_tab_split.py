"""
Iter 157 — DraftTab.tsx extracted from CommissionerSettings.tsx.

Validates:
1. DraftTab.tsx file exists with the testid + context-bundle prop signature.
2. CommissionerSettings.tsx imports + mounts DraftTab inside the draft TabsContent.
3. Parent passes the complete context object including `scheduledDrafts`.
4. Required identifiers (X icon, toast) are imported in DraftTab.
5. Parent line count under the agreed cap so the refactor stays effective.
"""
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ADMIN = REPO / "frontend/src/lovable/pages/CommissionerSettings.tsx"
DRAFT_TAB = REPO / "frontend/src/lovable/pages/commissioner/tabs/DraftTab.tsx"


def test_draft_tab_file_exists():
    assert DRAFT_TAB.exists(), "DraftTab.tsx must exist"
    src = DRAFT_TAB.read_text()
    assert 'data-testid="commissioner-draft-tab"' in src
    assert "export interface DraftTabContext" in src
    assert "export default function DraftTab" in src


def test_draft_tab_imports_required_identifiers():
    src = DRAFT_TAB.read_text()
    # X icon (lucide) used by the Player Criteria chip remove
    assert ", X }" in src or "X," in src, "Lucide X icon must be imported"
    # toast (sonner) used by the Create Draft button success
    assert 'from "sonner"' in src, "toast import from sonner missing"


def test_admin_mounts_draft_tab_with_full_context():
    src = ADMIN.read_text()
    assert 'import DraftTab from "@/lovable/pages/commissioner/tabs/DraftTab"' in src
    # DraftTab rendered inside the draft TabsContent
    draft_tab_idx = src.find('TabsContent value="draft"')
    assert draft_tab_idx > 0
    block = src[draft_tab_idx:draft_tab_idx + 1500]
    assert "<DraftTab" in block, "DraftTab must be mounted in the draft TabsContent"
    # All ctx fields the body references must be passed
    for field in (
        "draftType", "firstDraftCompleted", "draftRounds", "setDraftRounds",
        "roundTimes", "setRoundTimes",
        "draftClockEnabled", "setDraftClockEnabled",
        "selectedPlayerCriteria", "setSelectedPlayerCriteria",
        "createDraftPickTrading", "setCreateDraftPickTrading",
        "expandedDraft", "setExpandedDraft",
        "expandedDraftResults", "setExpandedDraftResults",
        "activeLeague", "persistDraftType", "completedDraftResults",
        "playerCriteriaOptions", "scheduledDrafts",
    ):
        assert field in block, f"Missing ctx field: {field}"


def test_admin_line_count_under_cap():
    """Parent must stay slim after Iter 157 extraction (~1,500 LOC cap)."""
    n = len(ADMIN.read_text().splitlines())
    assert n < 1500, f"CommissionerSettings.tsx grew back to {n} lines — refactor regression"
