"""
Iter 177 — Added a second bench tier ("Bench Reserve") to the Position
Breakdown matrix so leagues that distinguish a primary bench from a
deeper reserve pool can cap each tier independently.

Iter 180 — User feedback: the "Bench (Reserve)" tier was confusingly
redundant with the Minors row. Dropped from the visible UI rows but
kept in state shape + save payload for backward compat with any
leagues that wrote bench2 caps under iter 177.
"""
from pathlib import Path

ROSTERS_TAB = Path("/app/frontend/src/lovable/pages/commissioner/RostersTab.tsx")


def test_breakdown_rows_no_longer_render_bench_reserve_label():
    """Iter 180 — the user-facing 'Bench (Reserve)' label was
    removed from BREAKDOWN_ROWS. Visible rows are now just Active,
    Bench, and Minors."""
    src = ROSTERS_TAB.read_text()
    # The visible row registration MUST NOT include the bench2 entry.
    # (The bench2 KEY remains in the union type + state shape for
    # backward compat — see test below — but no longer renders.)
    assert '{ key: "bench2", label: "Bench (Reserve)"' not in src


def test_state_shape_still_carries_bench2_for_backward_compat():
    """Iter 177 schema retained so leagues that saved bench2 caps
    under iter 177 don't lose data. State shape + hydration + save
    payload still mention bench2 — it's just not editable in the UI."""
    src = ROSTERS_TAB.read_text()
    # Type union still includes bench2.
    assert '"active" | "bench" | "bench2" | "minors"' in src
    # State init / hydration / save payload still mention bench2.
    assert "{ active: {}, bench: {}, bench2: {}, minors: {} }" in src
    assert "bench2: hydrateRow(breakdownDoc.bench2)," in src
    assert "bench2: rowToDict(positionBreakdown.bench2)," in src


def test_minors_row_visibility_widened_under_iter180():
    """Iter 180 — the Minors row now surfaces when bench is on, when
    `minors_spots > 0`, or when `minors_enabled` is true (any of the
    three). Previously it required the premium `minors_enabled` flag,
    which made the row mysteriously disappear for non-premium leagues."""
    src = ROSTERS_TAB.read_text()
    assert "(row.key === \"minors\" && minorsOn)" in src
    assert "const minorsOn =" in src
    assert "(parseIntOrNull(prospectPool) || 0) > 0" in src
