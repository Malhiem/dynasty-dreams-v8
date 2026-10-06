"""
Iter 186 — Trade Builder quick-jump buttons inside the per-section
summary row + extraction of `getRosterViolations`, `canOwnerFixViolations`,
`getContractTypeColor` and the entire mock-data block out of
`PlayerRoster.tsx` and into siblings.
"""
from __future__ import annotations

from pathlib import Path

REPO = Path("/app")
PLAYER_ROSTER = REPO / "frontend/src/lovable/components/dashboard/PlayerRoster.tsx"
SUBS = REPO / "frontend/src/lovable/components/dashboard/player-roster/sub-components.tsx"
INTERNALS = REPO / "frontend/src/lovable/components/dashboard/player-roster/internals.tsx"
MOCK = REPO / "frontend/src/lovable/components/dashboard/player-roster/mock-data.ts"


# ── 1. Trade Builder quick-jump buttons ───────────────────────────
def test_section_group_renders_trade_top_button():
    src = SUBS.read_text()
    assert "data-testid={`section-trade-top-${section || \"default\"}`}" in src
    assert "📈 Trade ↑ Top" in src
    # invokes the forwarded onTrade callback with the top performer
    assert "onTrade(summary.top.p);" in src


def test_section_group_renders_trade_low_button_when_distinct():
    src = SUBS.read_text()
    assert "data-testid={`section-trade-low-${section || \"default\"}`}" in src
    assert "🔻 Trade ↓ Low" in src
    # rendered only when top + bottom are different players (single-player
    # sections would render the same button twice otherwise).
    assert "summary.top.p.id !== summary.bottom.p.id" in src
    assert "onTrade(summary.bottom.p);" in src


def test_section_group_accepts_on_trade_prop():
    src = SUBS.read_text()
    # new prop in the destructure + the type bag
    assert "  onTrade,\n" in src
    assert "onTrade?: (p: Player) => void;" in src


def test_all_section_group_invocations_forward_on_trade():
    """Every <SectionGroup …> call site must forward onTrade so the
    summary row inside the table actually receives the callback."""
    src = SUBS.read_text()
    # Counted in iter185 — 8 invocations across the 5 stat tables.
    assert src.count("onTrade={onTrade}") >= 8


# ── 2. Mock data extraction ───────────────────────────────────────
def test_mock_data_file_exists():
    assert MOCK.exists(), "Iter 186 should create player-roster/mock-data.ts"


def test_mock_data_exports():
    src = MOCK.read_text()
    for name in (
        "generateSchedule",
        "seededRand",
        "frostbitePlayers",
        "playerPool",
        "slotLabels",
        "generateTeamRoster",
        "weeklyMatchups",
        "currentWeek",
        "WeekMatchup",
    ):
        assert f"export " in src and name in src, f"Missing export: {name}"


def test_player_roster_imports_mock_data_from_sibling_file():
    src = PLAYER_ROSTER.read_text()
    assert 'from "./player-roster/mock-data";' in src
    # The duplicate inline declarations must be gone.
    assert "const generateSchedule = " not in src
    assert "const frostbitePlayers" not in src.replace("import {", "")  # ensure not redeclared
    # Frostbite default seed is still wired via the re-exported helper.
    assert "frostbitePlayers" in src


# ── 3. Helper extraction ──────────────────────────────────────────
def test_internals_owns_contract_and_violation_helpers():
    src = INTERNALS.read_text()
    for name in ("getContractTypeColor", "getRosterViolations", "canOwnerFixViolations"):
        assert f"export const {name}" in src, f"internals.tsx missing {name}"


def test_player_roster_no_inline_violation_helpers():
    src = PLAYER_ROSTER.read_text()
    # The inline definitions should be gone. Re-exports + imports OK.
    # We assert there's only the import + re-export, no `const` definition.
    # The room supplies live league rules through a thin wrapper; the
    # violation calculation still lives in the extracted internals module.
    assert "defaultRosterViolations(list, LEAGUE_ROSTER_SLOTS, sectionConfig)" in src
    assert "defaultRosterViolations" in src
    assert "const canOwnerFixViolations = " not in src
    assert "const getContractTypeColor = " not in src


# ── 4. Line-count target: PlayerRoster ≤ 1350 ─────────────────────
def test_player_roster_under_1350_lines():
    n = sum(1 for _ in PLAYER_ROSTER.open())
    assert n < 1350, f"PlayerRoster.tsx should be < 1350 lines after iter186 (got {n})"


# ── 5. Backwards-compat re-exports ────────────────────────────────
def test_player_roster_re_exports_relocated_symbols():
    src = PLAYER_ROSTER.read_text()
    for name in (
        "getContractTypeColor", "getRosterViolations", "canOwnerFixViolations",
        "generateSchedule", "seededRand", "frostbitePlayers", "playerPool",
        "generateTeamRoster", "weeklyMatchups", "currentWeek",
    ):
        assert name in src, f"PlayerRoster.tsx must re-export {name}"
    assert "WeekMatchup" in src
