"""
Iter 191 — Violations Sheet quick actions + Ice Kings cleanup +
foundation pieces for the in-draft pick trade flow (Draft Format
review-window settings + Draft Board year-grouped "via X · date"
trade subtitle).
"""
from __future__ import annotations

from pathlib import Path

REPO = Path("/app")
OPS_PY = REPO / "backend/routes/ops_console.py"
OPS_TSX = REPO / "frontend/src/lovable/pages/commissioner/OpsConsole.tsx"
DRAFT_TAB = REPO / "frontend/src/lovable/pages/commissioner/tabs/DraftTab.tsx"
DRAFT_BOARD = REPO / "frontend/src/lovable/pages/DraftBoard.tsx"
CLEANUP = REPO / "backend/scripts/iter191_cleanup_ice_kings_trades.py"


# ── Task 1 — Violations Sheet quick actions ─────────────────────
def test_notify_owners_endpoint_exists():
    src = OPS_PY.read_text()
    assert '@router.post("/leagues/{league_id}/ops-violations/notify")' in src
    # Uses the existing notification helper
    assert 'create_notification = _deps["create_notification"]' in src
    assert 'kind="roster_violation"' in src
    # Returns the count of notifications fired
    assert '"notified": notified' in src


def test_force_fix_endpoint_exists():
    src = OPS_PY.read_text()
    assert '@router.post("/leagues/{league_id}/ops-violations/force-fix")' in src
    # Only auto-fixes safe codes — cap_over is explicitly NOT auto-fixed
    # because resolving it requires owner trade activity.
    assert '"Cap breach can\'t be auto-fixed' in src
    # Returns the fix + skipped lists
    assert '"fixed_count"' in src and '"skipped_count"' in src
    # Logs the force-fix to the audit feed
    assert 'event_type="ops_force_fix"' in src


def test_violations_sheet_renders_quick_action_buttons():
    src = OPS_TSX.read_text()
    assert 'data-testid="ops-violations-actions"' in src
    assert 'data-testid="ops-violations-notify-btn"' in src
    assert 'data-testid="ops-violations-force-fix-btn"' in src
    # Confirm-then-fire safety on the destructive action
    assert "window.confirm(" in src
    # Re-loads counters + drilldown after a force-fix
    assert "await loadViolations();" in src
    assert "await load();" in src


# ── Task 2 — Ice Kings cleanup script ───────────────────────────
def test_cleanup_script_exists_and_is_idempotent():
    assert CLEANUP.exists(), "Cleanup script must be created"
    src = CLEANUP.read_text()
    # Targets the right league
    assert 'LEAGUE_NAME = "Ice Kings Head-to-Head"' in src
    # Writes a backup BEFORE destructive ops
    assert "iter191_cleanup_backup_" in src
    assert "backup_path.write_text(" in src
    # Idempotent — re-runs are no-ops
    assert "Idempotent" in src
    # Deletes trades + activity entries + resets picks
    assert "db.trades.delete_many" in src
    assert "db.activity_feed.delete_many" in src
    assert "db.draft_picks.update_one" in src


# ── Task 3 — Draft Format settings + Board year-grouped subtitle ─
def test_draft_format_has_review_window_dropdown():
    src = DRAFT_TAB.read_text()
    assert 'data-testid="draft-trade-review-section"' in src
    assert 'data-testid="draft-trade-review-minutes-select"' in src
    # Minute + hour options (no second-based values)
    for opt in ('value="0"', 'value="5"', 'value="15"', 'value="30"', 'value="60"', 'value="120"'):
        assert opt in src
    # Labels: minutes for short windows, "hour" for ≥60.
    assert "Instant (no review)" in src
    assert "30 minutes" in src
    assert "1 hour" in src
    assert "2 hours" in src


def test_draft_format_has_post_delay_action_dropdown():
    src = DRAFT_TAB.read_text()
    assert 'data-testid="draft-trade-post-delay-action-select"' in src
    # All 5 user-approved options must be present.
    for opt in ("auto_execute", "pause_draft", "extend_timer", "require_admin", "majority_vote"):
        assert f'value="{opt}"' in src


def test_draft_format_settings_state_seeded_from_league():
    """Defaults read from `activeLeague` so a future league-update
    PUT can persist the dropdown choices without re-wiring UI."""
    src = DRAFT_TAB.read_text()
    assert "draft_trade_review_minutes" in src
    assert "draft_trade_post_delay_action" in src
    assert "useState(" in src and "setDraftTradeReviewMinutes" in src
    assert "setDraftTradePostDelayAction" in src


def test_draft_board_renders_year_grouped_trade_summary():
    """User spec: 'via {original_team_name} {date}' with year
    grouping — same year shouldn't repeat the year label."""
    src = DRAFT_BOARD.read_text()
    assert 'data-testid="pick-trade-grouped-summary"' in src
    # Building blocks of the helper
    assert "const byYear: Record<string, string[]> = {};" in src
    # Renders "via {fromAbbr} ({MMM D})" segments
    assert 'via ${fromAbbr} (${mmd})' in src
    # Year header rendered once per year — ensure we group by year key
    assert 'String(d.getFullYear())' in src


def test_draft_board_mock_trades_removed():
    """User asked to wipe the static mock 'Traded' picks for
    Ice Kings; verify the legacy hardcoded blocks are gone."""
    src = DRAFT_BOARD.read_text()
    for bad in (
        'data["2025"]["FRST"][1]',
        '"FRST traded 2025 1st to ICE',
        '"NTH traded 2027 1st to BLZ',
    ):
        assert bad not in src, f"Stale mock trade still present: {bad}"
    # Replacement comment preserves the audit trail.
    assert "Mock trade injections removed" in src
