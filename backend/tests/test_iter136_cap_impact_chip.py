"""Iter 136 — Per-line / per-pair cap impact chip on NHL Lineup view.

Coverage
--------
1. `lineCapImpact` memo computes per-line + per-pair committed totals
   AND a team-wide remaining room number (cap − sum of all starter
   salaries).
2. A cap-impact chip renders under every forward line row with the
   committed amount + remaining team room.
3. The same chip renders under every defense pair row.
4. Room colors flip rose when negative so over-cap states are visible.
"""
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DEPTH = REPO / "frontend/src/lovable/pages/DepthChart.tsx"


def test_line_cap_impact_memo_present():
    src = DEPTH.read_text()
    assert "lineCapImpact" in src, "Memo missing"
    assert "contract?.salary" in src, "Should read salary off the player contract"
    assert "capLimits[yearOffset].cap" in src, "Must use the selected-year cap"
    assert "totalCommitted" in src, "Team-wide committed total missing"
    assert "room" in src, "Team room missing"


def test_per_line_chip_renders():
    src = DEPTH.read_text()
    # Per-line chip testid uses idx + 1
    assert "depth-line-cap-${idx + 1}" in src, "Per-line chip testid missing"
    # Per-pair chip testid uses idx + 1
    assert "depth-pair-cap-${idx + 1}" in src, "Per-pair chip testid missing"
    # Committed + room labels both appear
    assert "committed" in src and "room" in src, "Chip copy missing"


def test_over_cap_uses_rose():
    src = DEPTH.read_text()
    # Conditional colour for over-cap state
    assert "lineCapImpact.room >= 0 ? \"text-emerald-300\" : \"text-rose-300\"" in src, \
        "Over-cap rose tint missing"
