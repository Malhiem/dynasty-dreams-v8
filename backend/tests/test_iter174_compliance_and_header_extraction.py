"""
Iter 174 — Roster compliance cleanup + DraftHeaderActions extraction.

Two unrelated tasks shipped together:

  1. Roster cleanup: any non-prospect veteran sitting in a `minors`
     section gets bumped to `bench` (`scripts/iter174_compliance_cleanup.py`).
     The script is idempotent and uses the Iter-173 binary
     eligibility rule (prospect-only = minor-eligible).

  2. Refactor: the page-header strip in DraftRoom.tsx (title +
     read-only Draft Criteria popover + Trade Mode + Trading Block
     toggles) was extracted into
     `lovable/pages/draftroom/DraftHeaderActions.tsx`.

Both pieces get static guards here.
"""
from pathlib import Path

SCRIPT = Path("/app/backend/scripts/iter174_compliance_cleanup.py")
DRAFT_ROOM = Path("/app/frontend/src/lovable/pages/DraftRoom.tsx")
HEADER_ACTIONS = Path("/app/frontend/src/lovable/pages/draftroom/DraftHeaderActions.tsx")


# ── Compliance script ──────────────────────────────────────────────


def test_cleanup_script_exists_and_runnable():
    assert SCRIPT.exists()
    src = SCRIPT.read_text()
    assert "if __name__ ==" in src
    assert "asyncio.run(main())" in src


def test_cleanup_script_uses_iter173_binary_eligibility():
    """A minors slot is only legal for player_type == 'prospect' (or
    the explicit minor_eligible flag). Veteran skaters/goalies — even
    with low GP — get bumped."""
    src = SCRIPT.read_text()
    assert "player_type == \"prospect\"" in src
    assert "minor_eligible" in src
    assert "is_prospect = player_type == \"prospect\" or bool(p.get(\"minor_eligible\"))" in src
    # Eligible prospects are skipped, not moved.
    assert "if is_prospect:\n            continue" in src


def test_cleanup_script_is_idempotent_and_safe():
    """Bench-cap guard, dry-run flag, defensive ObjectId handling."""
    src = SCRIPT.read_text()
    assert "--dry-run" in src
    assert "bench_cap > 0 and bench_used >= bench_cap" in src
    assert "summary[\"bench_full\"]" in src
    # Records each move so the operator gets an audit trail.
    assert '"team_name": team.get("name")' in src
    assert '"from": "minors"' in src
    assert '"to": "bench"' in src


def test_cleanup_script_targets_correct_lineup_section():
    src = SCRIPT.read_text()
    # We mutate the `minors` section only and write back via
    # db.teams.update_one. No collateral damage to other sections.
    assert '(info.get("section") or "").lower() == "minors"' in src
    assert 'lineup[pid] = {"section": "bench", "slot": "BN"}' in src
    assert 'await db.teams.update_one(' in src


# ── Header-actions extraction ──────────────────────────────────────


def test_header_actions_file_extracted():
    assert HEADER_ACTIONS.exists()
    src = HEADER_ACTIONS.read_text()
    # Default-exported as a single React component for tree-shake friendliness.
    assert "export default function DraftHeaderActions" in src
    for testid in (
        "draft-room-subheader",
        "draft-room-criteria-trigger",
        "draft-room-criteria-display",
        "draft-room-criteria-readonly-note",
        "draft-room-trade-toggle",
        "draft-room-trade-block-toggle",
        "draft-room-trade-block-count",
    ):
        assert testid in src, testid


def test_parent_imports_and_mounts_header_actions():
    src = DRAFT_ROOM.read_text()
    assert 'from "@/lovable/pages/draftroom/DraftHeaderActions"' in src
    assert "<DraftHeaderActions" in src
    # Sanity: all required props are forwarded.
    for prop in (
        "currentDraft={currentDraft}",
        "currentCriteria={currentCriteria}",
        "tradeMode={tradeMode}",
        "setTradeMode={setTradeMode}",
        "tradeBlockMode={tradeBlockMode}",
        "setTradeBlockMode={setTradeBlockMode}",
        "tradeBlockItems={tradeBlockItems}",
    ):
        assert prop in src, prop


def test_parent_no_longer_holds_extracted_header_jsx():
    """The 90-line inline header block (title + popover + toggles) is
    gone from the parent. We only spot-check anchors that lived inside
    that block."""
    src = DRAFT_ROOM.read_text()
    # The exact "Draft Room" h1 is only rendered by the extracted child
    # now — parent should NOT contain it.
    assert "<h1 className=\"text-2xl font-bold text-foreground flex items-center gap-2\">" not in src
    # The inline-trade toggle Button definition is gone from the parent.
    assert "{tradeMode ? \"Trade Mode: On\" : \"Trade Mode: Off\"}" not in src
    assert "{tradeBlockMode ? \"Trading Block: On\" : \"Trading Block: Off\"}" not in src
