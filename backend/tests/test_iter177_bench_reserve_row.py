"""
Iter 177 — Added a second bench tier ("Bench Reserve") to the Position
Breakdown matrix so leagues that distinguish a primary bench from a
deeper reserve pool can cap each tier independently.
"""
from pathlib import Path

ROSTERS_TAB = Path("/app/frontend/src/lovable/pages/commissioner/RostersTab.tsx")


def test_breakdown_rows_include_second_bench_tier():
    src = ROSTERS_TAB.read_text()
    # Type signature widened to accept the new key.
    assert '"active" | "bench" | "bench2" | "minors"' in src
    # Row registration carries the new label + helpful copy.
    assert '{ key: "bench2", label: "Bench (Reserve)"' in src
    assert "primary bench from a deeper reserve pool" in src


def test_state_shape_carries_bench2_row():
    src = ROSTERS_TAB.read_text()
    # State init includes bench2 so React doesn't crash on a `prev[row.key]` lookup.
    assert "{ active: {}, bench: {}, bench2: {}, minors: {} }" in src
    # Hydration mirrors the new row.
    assert "bench2: hydrateRow(breakdownDoc.bench2)," in src
    # Save payload includes the new row.
    assert "bench2: rowToDict(positionBreakdown.bench2)," in src


def test_bench_and_bench2_share_visibility_predicate():
    """Both bench rows surface together when the league has bench spots
    configured. Hiding only one would leave the matrix asymmetric."""
    src = ROSTERS_TAB.read_text()
    assert '(row.key === "bench" || row.key === "bench2") && (parseIntOrNull(benchSpots) || 0) > 0' in src
