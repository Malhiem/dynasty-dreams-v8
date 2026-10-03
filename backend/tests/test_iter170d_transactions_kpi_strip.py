"""Iter 170d — Lock the KPI strip on Transactions page (this week / this
month / most active team) and verify it respects the active filters."""
from pathlib import Path

TRANSACTIONS = Path("/app/frontend/src/lovable/pages/Transactions.tsx")


def _src() -> str:
    return TRANSACTIONS.read_text()


def test_kpi_memo_present_and_respects_filters():
    src = _src()
    # The memo must derive from mappedWithIds (raw filtered rows with
    # proposer/target ids + createdAt) and re-apply the same team-chip
    # + date-range predicates so the numbers always match what's
    # rendered below in the tabs.
    block = src.split("const kpis = useMemo")[1].split("}, [")[0]
    assert "selectedTeamIds.size > 0" in block
    assert "selectedTeamIds.has(_proposerId)" in block
    assert "selectedTeamIds.has(_targetId)" in block
    assert "dateFrom" in block and "dateTo" in block
    # 7-day and 30-day windows
    assert "7 * 24 * 60 * 60 * 1000" in block
    assert "30 * 24 * 60 * 60 * 1000" in block
    # Most-active counts both proposer + target appearances
    assert "row._proposerId" in block and "row._targetId" in block


def test_kpi_memo_deps_include_filter_state():
    src = _src()
    # Just after the kpis block, the dep array must list mappedWithIds
    # + selectedTeamIds + dateFrom + dateTo so the strip updates live
    # whenever filters change.
    after = src.split("const kpis = useMemo")[1]
    deps = after.split("}, [")[1].split("])")[0]
    for dep in ("mappedWithIds", "selectedTeamIds", "dateFrom", "dateTo"):
        assert dep in deps, f"kpis useMemo dep array must include {dep}"


def test_kpi_strip_jsx_has_three_tiles():
    src = _src()
    assert 'data-testid="transactions-kpi-strip"' in src
    assert 'data-testid="transactions-kpi-week"' in src
    assert 'data-testid="transactions-kpi-month"' in src
    assert 'data-testid="transactions-kpi-most-active"' in src
    # Strip must sit above the filter card (KPIs first, then filters).
    strip_idx = src.index('data-testid="transactions-kpi-strip"')
    filter_idx = src.index('data-testid="transactions-filters"')
    assert strip_idx < filter_idx
