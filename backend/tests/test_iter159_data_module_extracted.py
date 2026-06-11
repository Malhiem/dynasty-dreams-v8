"""
Iter 159 — Consolidated data module `commissionerData.tsx` extracted from
CommissionerSettings.tsx. Drops parent from ~1,380 LOC to ~640 LOC.
"""
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ADMIN = REPO / "frontend/src/lovable/pages/CommissionerSettings.tsx"
DATA = REPO / "frontend/src/lovable/pages/commissioner/data/commissionerData.tsx"


def test_data_module_exists_with_all_exports():
    assert DATA.exists(), "commissionerData.tsx must exist"
    src = DATA.read_text()
    # Static lists
    assert "export const nhlTeams" in src
    # Scoring categories + type
    assert "export interface ScoringCategory" in src
    assert "export const scoringCategories: ScoringCategory[]" in src
    # Tank monitor
    assert "export interface TeamTankData" in src
    assert "export const TOTAL_WEEKS" in src
    assert "export const generateWeeklyData" in src
    assert "export const weeklyTankData" in src
    assert "export const aggregateWeeks" in src
    assert "export const TankMonitorTable" in src
    # Roster monitor
    assert "export interface RosterPlayer" in src
    assert "export interface TeamRoster" in src
    assert "export const ROSTER_LIMITS" in src
    assert "export const generateRosterData" in src
    assert "export const rosterMonitorData" in src
    assert "export const generateWeeklyRosterFlags" in src
    assert "export const weeklyRosterFlags" in src
    assert "export const CAP_LIMIT" in src
    assert "export const teamCapUsage" in src
    assert "export interface AutoFixResult" in src
    assert "export const evaluateAutoFix" in src
    assert "export const RosterMonitorTable" in src
    # Audit log
    assert "export interface AuditLogEntry" in src
    assert "export const generateMockAuditLog" in src


def test_admin_imports_from_data_module():
    src = ADMIN.read_text()
    assert 'from "@/lovable/pages/commissioner/data/commissionerData"' in src
    for sym in (
        "nhlTeams",
        "scoringCategories",
        "ScoringCategory",
        "AuditLogEntry",
        "generateMockAuditLog",
        "TankMonitorTable",
        "RosterMonitorTable",
    ):
        assert sym in src, f"Parent must reference {sym} (consumed from data module)"


def test_admin_no_longer_defines_data_inline():
    """Parent file must NOT redefine any of the extracted constants/components."""
    src = ADMIN.read_text()
    # Negative assertions — old inline declarations are gone
    assert "const TOTAL_WEEKS = 22" not in src
    assert "const generateWeeklyData =" not in src
    assert "const TankMonitorTable =" not in src
    assert "const RosterMonitorTable =" not in src
    assert "const generateMockAuditLog =" not in src
    assert "const CAP_LIMIT = 88000000" not in src
    assert "const teamCapUsage:" not in src
    # Dead imports cleaned up
    assert "ScrollText" in src  # still used in TabsTrigger
    # Confirm no leftover ScrollArea/Table imports (moved to data module)
    assert 'from "@/components/ui/scroll-area"' not in src
    assert 'from "@/components/ui/table"' not in src
    assert 'from "@/components/ui/tooltip"' not in src


def test_admin_line_count_under_700():
    """Parent must be under 700 lines after Iter 159 consolidation."""
    n = len(ADMIN.read_text().splitlines())
    assert n < 700, f"CommissionerSettings.tsx is {n} lines — Iter 159 target was < 700"
