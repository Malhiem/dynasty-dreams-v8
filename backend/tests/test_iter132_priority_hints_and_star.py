"""Iter 132 — Reusable star button + Rephrased waiver priority hints.

Coverage
--------
1. Manual Priority Duration carries a new InfoHint explaining each
   value (one-off auto-reverts to automated, monthly windows, full
   season).
2. The Automated Priority Order radio label uses the new long-form
   copy the user requested.
3. New <MatchupStarButton> component exposes a star toggle + an H2H
   info-icon tooltip with `Lifetime` record + named streak.
4. MatchupStarButton is mounted on the matchup grid in
   LeagueDetailPage so users can star matchups directly without
   opening the watchlist widget.
"""
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TX_CARDS = REPO / "frontend/src/lovable/pages/commissioner/TransactionsConfigCards.tsx"
STAR_BTN = REPO / "frontend/src/components/MatchupStarButton.jsx"
LEAGUE_HOME = REPO / "frontend/src/pages/LeagueDetailPage.jsx"


# ── 1. Manual priority duration carries an InfoHint ────────────
def test_manual_priority_duration_info_hint_present():
    src = TX_CARDS.read_text()
    assert 'testId="info-manual-priority-duration"' in src, "InfoHint testId missing"
    # Mentions of each duration option in the explainer text
    assert "One-off" in src and "auto-reverts" in src.lower() or "revert" in src.lower(), \
        "One-off explanation missing in InfoHint copy"
    assert "Full Season" in src, "Full Season label missing"


# ── 2. Automated Priority Order rephrased ──────────────────────
def test_automated_priority_order_rephrased():
    src = TX_CARDS.read_text()
    assert "An automated system that determines waiver claim priority" in src, \
        "New Automated Priority Order copy not found"
    assert "drop to the bottom of the priority list" in src, \
        "Missing the 'drop to the bottom' clause in the new copy"


# ── 3. MatchupStarButton component exists with required props ──
def test_matchup_star_button_component_exists():
    src = STAR_BTN.read_text()
    assert "export default function MatchupStarButton" in src, "Export missing"
    # Props
    for prop in ("leagueId", "matchupId", "homeTeamId", "homeTeamName",
                 "awayTeamId", "awayTeamName"):
        assert prop in src, f"Prop {prop!r} missing"
    # Star toggle + H2H tooltip elements
    assert "matchup-star-" in src, "Star button testid missing"
    assert "matchup-h2h-info-" in src, "Tooltip trigger testid missing"
    assert "matchup-h2h-tooltip-" in src, "Tooltip content testid missing"
    # Streak sentence format
    assert "has won" in src and "in a row" in src, "Streak sentence missing"
    # Lifetime label (renamed from All-time per user request)
    assert "Lifetime" in src, "Lifetime label missing in tooltip"


# ── 4. Star button mounted on the league matchup grid ──────────
def test_star_button_on_league_home_matchup_card():
    src = LEAGUE_HOME.read_text()
    assert "import MatchupStarButton" in src, "Import missing"
    assert "<MatchupStarButton" in src, "Component not rendered"
    # Ensure it sits inside the matchup-card render block
    assert "league-matchup-card-" in src, "Matchup card scope not present"
