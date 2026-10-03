"""Iter 135 — Depth Chart NHL Lineup quick action: Copy from current year.

Coverage
--------
1. `copyFromCurrentYear` handler exists, only runs when `yearOffset !== 0`.
2. Handler filters by `eligibleForYear` so ineligible players are skipped.
3. UI surfaces a "Copy from current year" button (testid
   `depth-lineup-copy-current`) ONLY when the user is viewing a future
   year (yearOffset !== 0).
4. The Copy icon from lucide-react is imported.
"""
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DEPTH_CHART = REPO / "frontend/src/lovable/pages/DepthChart.tsx"


def test_copy_handler_defined():
    src = DEPTH_CHART.read_text()
    assert "const copyFromCurrentYear" in src, "Handler missing"
    assert "if (yearOffset === 0) return" in src, "Should be a no-op on current year"
    assert "lineups.y0" in src, "Must read source from year 0 lineup"
    assert "eligibleForYear(p, yearOffset)" in src, \
        "Must filter source assignments by future-year eligibility"


def test_copy_button_rendered_for_future_years_only():
    src = DEPTH_CHART.read_text()
    assert 'data-testid="depth-lineup-copy-current"' in src, "Button testid missing"
    # Guarded by `yearOffset !== 0`
    assert "yearOffset !== 0 &&" in src, "Button must only render for future years"
    # Copy icon imported from lucide-react
    assert "Copy" in src.split("from \"lucide-react\"")[0], "Copy icon import missing"


def test_skipped_message_path_present():
    src = DEPTH_CHART.read_text()
    # Toast surfaces a skipped count when contracts expire
    assert "ineligible skipped" in src, \
        "Toast must surface the skipped count when some players don't fit"
