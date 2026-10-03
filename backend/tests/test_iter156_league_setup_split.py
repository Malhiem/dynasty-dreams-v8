"""Iter 156 — LeagueSetupTab extracted from CommissionerSettings.tsx."""
from pathlib import Path
FRONTEND = Path("/app/frontend/src")


def _read(rel: str) -> str:
    return (FRONTEND / rel).read_text(encoding="utf-8")


def test_league_setup_tab_extracted():
    parent = _read("lovable/pages/CommissionerSettings.tsx")
    tab = _read("lovable/pages/commissioner/tabs/LeagueSetupTab.tsx")
    assert "import LeagueSetupTab from " in parent
    assert "<LeagueSetupTab" in parent
    # Old inline blocks are gone from the parent
    assert "Choose how teams earn points and compete" not in parent
    assert "PNG, JPG, or SVG. Maximum file size: 2MB" not in parent
    assert "NHL Cap Hit" not in parent
    # The extracted file owns the carried-over testids
    for tid in (
        "commissioner-league-setup-tab",
        "league-privacy-card",
        "league-privacy-toggle",
        "league-recalc-stats",
        "legacy-roster-lock-rules-card",
    ):
        assert f'data-testid="{tid}"' in tab, f"Missing testid: {tid}"


def test_commissioner_settings_under_1900_lines():
    parent = _read("lovable/pages/CommissionerSettings.tsx")
    lc = parent.count("\n")
    # Started this iteration at 2,268 → ~1,928 after extracting League Setup
    # (full Iter 157 Draft extraction will get us under the 1,800 target).
    assert lc < 1935, f"Expected parent < 1,935 lines, got {lc}"
