"""Iter 133 — Watchlist integrated (no separate widget) + NHL Lineup stacked.

Coverage
--------
1. The standalone `MatchupWatchlistWidget` is removed.
2. `MatchupStarButton` is the canonical entry point for starring matchups.
3. `LeagueDetailPage` matchup grid sorts by starred + auto-watch.
4. `MatchupSideRail` ("League Live") imports the star button + sorts.
5. DepthChart NHL Lineup renders Forwards as one row per line and
   Defense as one row per pair (data-testids `depth-lineup-line-{n}` /
   `depth-lineup-pair-{n}`).
6. Automated Priority Order copy uses the latest wording.
"""
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
LEAGUE_HOME = REPO / "frontend/src/pages/LeagueDetailPage.jsx"
LIVE_PAGE = REPO / "frontend/src/pages/LiveScoringPage.jsx"
DASHBOARD = REPO / "frontend/src/pages/DashboardPage.jsx"
SIDE_RAIL = REPO / "frontend/src/lovable/components/matchup/MatchupSideRail.tsx"
STAR_BTN = REPO / "frontend/src/components/MatchupStarButton.jsx"
DEPTH_CHART = REPO / "frontend/src/lovable/pages/DepthChart.tsx"
TX_CARDS = REPO / "frontend/src/lovable/pages/commissioner/TransactionsConfigCards.tsx"
OLD_WIDGET = REPO / "frontend/src/components/MatchupWatchlistWidget.jsx"


# ── 1. Old widget file deleted, no consumers remain ────────────
def test_watchlist_widget_deleted():
    assert not OLD_WIDGET.exists(), "Old MatchupWatchlistWidget.jsx must be removed"


def test_no_widget_imports_remain():
    for f in (LEAGUE_HOME, LIVE_PAGE, DASHBOARD):
        src = f.read_text()
        assert "MatchupWatchlistWidget" not in src, f"{f.name} still references the deleted widget"


# ── 2. LeagueDetailPage sorts matchups by starred + auto-watch ─
def test_league_home_sorts_by_starred():
    src = LEAGUE_HOME.read_text()
    assert "sortedWeekMatchups" in src, "Sort memo missing"
    assert "matchup-stars?league_id=" in src, "Stars endpoint not wired"
    assert "matchup-star-changed" in src, "Custom-event listener missing"


# ── 3. MatchupSideRail integrates star + sort ──────────────────
def test_side_rail_has_star_and_sort():
    src = SIDE_RAIL.read_text()
    assert "import MatchupStarButton" in src, "Star button import missing"
    assert "<MatchupStarButton" in src, "Star button not rendered"
    assert "sortedMatchups" in src, "Sort memo missing"
    assert "matchup-stars?league_id=" in src, "Stars endpoint not wired"


# ── 4. DepthChart NHL Lineup uses per-line + per-pair rows ─────
def test_depth_chart_lineup_stacked_rows():
    src = DEPTH_CHART.read_text()
    assert "depth-lineup-forwards" in src, "Forwards container testid missing"
    assert "depth-lineup-defense" in src, "Defense container testid missing"
    # Line/Pair labels rendered in the row prefix
    assert "depth-lineup-line-" in src, "Per-line row testid missing"
    assert "depth-lineup-pair-" in src, "Per-pair row testid missing"
    assert "Line {idx + 1}" in src, "Line label not in component"
    assert "Pair {idx + 1}" in src, "Pair label not in component"


# ── 5. Latest automated copy is live ───────────────────────────
def test_automated_priority_copy_v3():
    src = TX_CARDS.read_text()
    assert "An automated system that determines waiver claim priority" in src
    assert "drop to the bottom of the priority list" in src


# ── 6. MatchupStarButton dispatches custom event on toggle ─────
def test_star_button_dispatches_event():
    src = STAR_BTN.read_text()
    assert "matchup-star-changed" in src, "Toggle must dispatch custom event"
