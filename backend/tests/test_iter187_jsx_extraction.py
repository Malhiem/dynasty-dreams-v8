"""
Iter 187 — Extracted 3 JSX blocks from PlayerRoster.tsx into siblings:
  • LineupLockBanner.tsx — Iter 103 amber lock banner.
  • EmergencyBudgetChip.tsx — Iter 106 "Used X/Y emergency swaps" pill.
  • RosterColumnSettings.tsx — Settings cog popover with category +
    display-options toggles + Show All / Tracked Only / Points Only.

These tests assert each sibling file exists, exports the expected
component, and that PlayerRoster.tsx wires them in correctly. Together
with the iter103 / iter106 / iter144 / iter185 / iter186 invariants
(re-checked here) they guard against regressions where the refactor
accidentally drops a `data-testid` or breaks a prop bag.
"""
from __future__ import annotations

from pathlib import Path

REPO = Path("/app")
ROSTER_DIR = REPO / "frontend/src/lovable/components/dashboard"
PLAYER_ROSTER = ROSTER_DIR / "PlayerRoster.tsx"
LOCK_BANNER = ROSTER_DIR / "player-roster/LineupLockBanner.tsx"
EMERG_CHIP = ROSTER_DIR / "player-roster/EmergencyBudgetChip.tsx"
COLUMN_SETTINGS = ROSTER_DIR / "player-roster/RosterColumnSettings.tsx"


# ── 1. New sibling files exist and export their component ────────
def test_lineup_lock_banner_file_exists_and_exports_component():
    assert LOCK_BANNER.exists(), "LineupLockBanner.tsx must be created"
    src = LOCK_BANNER.read_text()
    assert "export const LineupLockBanner" in src
    # Critical iter103 test id preserved.
    assert 'data-testid="lineup-lock-banner"' in src
    # Returns null when not locked so callers don't need to guard.
    assert "if (!lockStatus?.locked) return null;" in src
    # Renders the localized unlock string with stable options
    assert 'weekday: "short"' in src
    assert 'hour: "numeric"' in src


def test_emergency_budget_chip_file_exists_and_exports_component():
    assert EMERG_CHIP.exists(), "EmergencyBudgetChip.tsx must be created"
    src = EMERG_CHIP.read_text()
    assert "export const EmergencyBudgetChip" in src
    assert 'data-testid="emergency-swap-chip"' in src
    assert "if (!emergencyBudget?.enabled) return null;" in src
    # Emerald / Rose colour swap is meaningful UX feedback — keep it.
    assert "bg-emerald-500/10" in src
    assert "bg-rose-500/10" in src
    # Backwards-compat: per_season message variant preserved.
    assert 'emergencyBudget.scope === "per_season"' in src


def test_roster_column_settings_file_exists_and_exports_component():
    assert COLUMN_SETTINGS.exists(), "RosterColumnSettings.tsx must be created"
    src = COLUMN_SETTINGS.read_text()
    assert "export const RosterColumnSettings" in src
    # New test ids the iter187 component introduces — these are
    # forward-compatibility hooks for upcoming smoke tests.
    for tid in (
        "roster-column-settings-trigger",
        "roster-column-settings-popover",
        "roster-column-settings-show-all",
        "roster-column-settings-tracked-only",
        "roster-column-settings-points-only",
    ):
        assert f'data-testid="{tid}"' in src
    # Imports the shared category constants so legacy behaviour is
    # preserved.
    for name in ("trackedCategories", "untrackedCategories", "allStatCategories", "categoryLabels"):
        assert name in src


# ── 2. PlayerRoster.tsx wires + no longer carries the inline JSX ─
def test_player_roster_imports_extracted_components():
    src = PLAYER_ROSTER.read_text()
    assert 'from "./player-roster/LineupLockBanner"' in src
    assert 'from "./player-roster/EmergencyBudgetChip"' in src
    assert 'from "./player-roster/RosterColumnSettings"' in src
    # Each component is mounted in the render block.
    assert "<LineupLockBanner lockStatus={lockStatus} />" in src
    assert "<EmergencyBudgetChip emergencyBudget={emergencyBudget} />" in src
    assert "<RosterColumnSettings" in src


def test_player_roster_no_inline_lock_or_chip_jsx():
    """If anyone accidentally re-inlines the JSX, the iter103/106
    invariants would still hold but the cumulative file-size win would
    silently regress. Guard against that here."""
    src = PLAYER_ROSTER.read_text()
    # The original inline expressions referenced `lockStatus?.locked &&`
    # at the JSX call site. After extraction the only occurrence inside
    # PlayerRoster.tsx is the prop forwarded to the new component.
    assert "{lockStatus?.locked && (" not in src
    assert "{emergencyBudget?.enabled && (" not in src
    # The old inline Settings <Popover> wrapper is gone.
    assert "{/* Column Settings Cog */}" not in src


def test_player_roster_under_1200_lines():
    n = sum(1 for _ in PLAYER_ROSTER.open())
    assert n < 1200, f"PlayerRoster.tsx should be < 1200 lines after iter187 (got {n})"


# ── 3. iter103 / iter106 invariants still hold (defensive) ───────
def test_iter103_lock_banner_still_renders_via_sibling():
    src = LOCK_BANNER.read_text()
    assert "Lineup locked — saves will be rejected" in src
    assert "Unlocks at" in src


def test_iter106_emergency_chip_still_renders_via_sibling():
    src = EMERG_CHIP.read_text()
    assert "Used " in src and " / " in src
    assert "emergency swaps" in src
    assert "No swaps remaining" in src


# ── 4. Column settings preserves the "Show All / Tracked Only /
#       Points Only" behaviour (iter59 + iter120 settings flow). ───
def test_column_settings_show_all_replaces_set():
    src = COLUMN_SETTINGS.read_text()
    # Show All shortcut must replace the entire set (not merge), else
    # "Points Only" can't clear stat columns.
    assert "setVisibleColumns(new Set([...allStatCategories, \"FPTS\"]))" in src
    assert "setVisibleColumns(new Set([...trackedCategories, \"FPTS\"]))" in src
    assert "setVisibleColumns(new Set([\"FPTS\"]))" in src
