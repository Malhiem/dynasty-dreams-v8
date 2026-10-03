"""Iter 134 — My-matchup pinned + Depth Chart year dropdown + uniform tile size.

Coverage
--------
1. MatchupSideRail pins the user's own matchup first regardless of stars.
2. LeagueDetailPage matchup grid pins the user's own matchup first too.
3. DepthChart uses a Select dropdown (not 3 buttons) for the year switch.
4. NHL Lineup view renders Defense + Goalies inside the same 3-col grid
   used by Forwards so every tile shares the same width.
"""
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SIDE_RAIL = REPO / "frontend/src/lovable/components/matchup/MatchupSideRail.tsx"
LEAGUE_HOME = REPO / "frontend/src/pages/LeagueDetailPage.jsx"
DEPTH_CHART = REPO / "frontend/src/lovable/pages/DepthChart.tsx"


# ── 1. Side rail pins MY matchup first ──────────────────────────
def test_side_rail_pins_my_matchup_first():
    src = SIDE_RAIL.read_text()
    # No longer filtering out the user's matchup
    assert "filter((m) => !myMatchupId || m.matchup_id !== myMatchupId)" not in src, \
        "Side rail must no longer filter out my matchup"
    # Sort comparator prioritises mine
    assert "aMine" in src and "bMine" in src, "MY-matchup sort branch missing"
    assert "MY MATCHUP" in src, "MY MATCHUP badge missing"
    assert "matchup-side-rail-mine-" in src, "Mine testid missing"


# ── 2. League Home matchup grid pins MY matchup first ──────────
def test_league_home_pins_my_matchup_first():
    src = LEAGUE_HOME.read_text()
    assert "myTeamId" in src, "myTeamId resolution missing"
    assert "aMine" in src and "bMine" in src, "MY-matchup sort branch missing in league home"


# ── 3. Depth Chart year switch uses a Select dropdown ──────────
def test_depth_year_selector_is_dropdown():
    src = DEPTH_CHART.read_text()
    assert 'data-testid="depth-year-select"' in src, "Year Select trigger missing"
    # SelectItem renders with template-literal testid
    assert "depth-year-option-${y}" in src, "Year option testid template missing"
    # Old three-button design removed
    assert "depth-year-tab-${y}" not in src, "Old depth-year-tab buttons must be removed"
    assert 'from "@/components/ui/select"' in src, "Select import missing"


# ── 4. Defense + Goalies share the 3-col grid (same tile size) ─
def test_defense_goalies_uniform_tile_size():
    src = DEPTH_CHART.read_text()
    # Defense uses 3-col grid (was 2-col / max-w-md before)
    # Find the Defense block and ensure no 'grid-cols-2' near it
    d_idx = src.find("depth-lineup-defense")
    assert d_idx > 0, "Defense container not found"
    d_block = src[d_idx:d_idx + 1500]
    assert "grid-cols-3" in d_block, "Defense must use grid-cols-3 for uniform width"
    assert "max-w-md" not in d_block, "Defense must drop the max-w-md cap"
    # Goalies use the same Line/Pair row structure
    g_idx = src.find("depth-lineup-goalies")
    assert g_idx > 0, "Goalies container not found"
    g_block = src[g_idx:g_idx + 1500]
    assert "grid-cols-3" in g_block, "Goalies must use grid-cols-3 for uniform width"
