"""
Iter 158 — SalaryCapContractsTab + LeagueAdminTab extracted from CommissionerSettings.tsx.
"""
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ADMIN = REPO / "frontend/src/lovable/pages/CommissionerSettings.tsx"
SALARY_TAB = REPO / "frontend/src/lovable/pages/commissioner/tabs/SalaryCapContractsTab.tsx"
ADMIN_TAB = REPO / "frontend/src/lovable/pages/commissioner/tabs/LeagueAdminTab.tsx"


def test_salary_cap_contracts_tab_extracted():
    assert SALARY_TAB.exists()
    src = SALARY_TAB.read_text()
    assert 'data-testid="commissioner-salary-cap-tab"' in src
    # All 3 cards rendered when activeLeague is present
    for c in ("<SalaryCapCard", "<SalaryRetentionCard", "<ContractBuyoutsCard"):
        assert c in src, f"Missing card render: {c}"
    # Empty state rendered when no league
    assert "Select a league" in src
    # Correct import source (named exports from RulesScheduleTab)
    assert 'from "@/lovable/pages/commissioner/RulesScheduleTab"' in src


def test_league_admin_tab_extracted():
    assert ADMIN_TAB.exists()
    src = ADMIN_TAB.read_text()
    assert 'data-testid="commissioner-league-admin-tab"' in src
    # Three sub-tabs
    for v in ('value="teams"', 'value="schedules"', 'value="season-awards"'):
        assert v in src, f"Missing TabsTrigger: {v}"
    # Sub-tab content components rendered
    for c in ("<TeamsTab", "<SchedulesTab", "<SeasonAwardsTab"):
        assert c in src, f"Missing component render: {c}"
    # H2H gate for schedules
    assert "Matchup scheduling is only available for Head-to-Head" in src


def test_admin_mounts_new_tabs():
    src = ADMIN.read_text()
    assert 'import SalaryCapContractsTab from "@/lovable/pages/commissioner/tabs/SalaryCapContractsTab"' in src
    assert 'import LeagueAdminTab from "@/lovable/pages/commissioner/tabs/LeagueAdminTab"' in src
    # The old inline 3-card guard is gone
    assert "<SalaryCapCard" not in src, "SalaryCapCard should now live inside SalaryCapContractsTab"
    assert "<TeamsTab" not in src, "TeamsTab should now live inside LeagueAdminTab"


def test_admin_line_count_under_1400():
    n = len(ADMIN.read_text().splitlines())
    assert n < 1400, f"CommissionerSettings.tsx is {n} lines — extraction regressed"
