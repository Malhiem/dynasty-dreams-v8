"""
Iter 181 — Four follow-up requests after the iter 180 round:

  (1) MinorEligibleBadge component renders next to a player wherever
      they appear (Rosters, Waivers / Players, Transactions, Trade
      Block, Draft Room, Depth Chart). Backend now ships
      `minor_eligible` + `player_type` on `/waivers/available` and
      `/players` so the badge surfaces uniformly.

  (2) The "Position Breakdown" matrix is now nested INSIDE the
      "Roster Size" card so commissioners see per-position caps
      alongside the section sizes they constrain.

  (3) Per-row caps cannot exceed the section's overall size. Both
      backend (`check_position_breakdown_within_caps`) and frontend
      (inline error banner + disabled Save button) reject saves
      where caps sum to more than `roster_spots` / `bench_spots` /
      `minors_spots`. The error message tells the commissioner WHICH
      section overflowed and BY how much, plus the fix.

  (4) "Prospect Pool Size" label renamed to "Minors Team Size" to
      match the rest of the app's "Minors" naming convention.
      Schema field stays as `minors_spots` for backward compat.
"""
from pathlib import Path

BADGE = Path("/app/frontend/src/lovable/components/MinorEligibleBadge.tsx")
ROSTERS_TAB = Path("/app/frontend/src/lovable/pages/commissioner/RostersTab.tsx")
PLAYER_ROSTER = Path("/app/frontend/src/lovable/components/dashboard/PlayerRoster.tsx")
WAIVERS = Path("/app/frontend/src/lovable/pages/Waivers.tsx")
DEPTH_CHART = Path("/app/frontend/src/lovable/pages/DepthChart.tsx")
TRADE_BLOCK = Path("/app/frontend/src/lovable/pages/TradeBlock.tsx")
TRANSACTIONS = Path("/app/frontend/src/lovable/pages/Transactions.tsx")
PLAYERS_PAGE = Path("/app/frontend/src/pages/PlayersPage.jsx")
ROSTER_RULES = Path("/app/backend/utils/roster_rules.py")
LEAGUES_PY = Path("/app/backend/routes/leagues.py")
WAIVERS_PY = Path("/app/backend/routes/waivers.py")
PLAYERS_PY = Path("/app/backend/routes/players.py")


# ── (1) MinorEligibleBadge component + surfaces ─────────────────────

def test_badge_component_exists_and_is_render_safe_for_falsy_eligible():
    """A reusable, render-safe badge component. Returns null when
    `eligible` is falsy so callers can drop the prop unconditionally."""
    assert BADGE.exists()
    src = BADGE.read_text()
    assert "export const MinorEligibleBadge = (" in src
    assert "if (!eligible) return null;" in src
    # Title attribute carries the explainer so a hover reveals it
    # without needing a tooltip portal.
    assert 'title="Minor-eligible prospect"' in src
    # Stable testid for QA.
    assert 'data-testid="minor-eligible-badge"' in src


def test_badge_imported_by_every_player_surface():
    """The badge must surface wherever a player can appear so the
    Minors indicator is consistent across the app."""
    surfaces = [PLAYER_ROSTER, WAIVERS, DEPTH_CHART, TRADE_BLOCK, TRANSACTIONS, PLAYERS_PAGE]
    for f in surfaces:
        src = f.read_text()
        assert "MinorEligibleBadge" in src, f"badge import missing in {f}"
        assert "<MinorEligibleBadge" in src, f"badge JSX missing in {f}"


def test_backend_waivers_available_returns_minor_eligible():
    """Surface the field in the waiver / free-agency listing so the
    badge has data to render on Waivers / Players."""
    src = WAIVERS_PY.read_text()
    assert "from utils.roster_rules import compute_minor_eligible" in src
    assert '"minor_eligible": compute_minor_eligible(p, league_doc)' in src
    assert '"player_type": p.get("player_type") or "skater"' in src


def test_backend_players_directory_returns_minor_eligible():
    src = PLAYERS_PY.read_text()
    assert "from utils.roster_rules import compute_minor_eligible" in src
    assert 'player["minor_eligible"] = compute_minor_eligible(player, league_doc)' in src


# ── (2) Position Breakdown nested inside Roster Size ───────────────

def test_position_breakdown_now_inside_roster_size_card():
    """The standalone `rosters-positions-card` is gone — the matrix
    lives inside the Roster Size card alongside the section sizes."""
    src = ROSTERS_TAB.read_text()
    assert 'data-testid="rosters-positions-card"' not in src
    # The merge comment is present so future refactors know why.
    assert "Iter 181 — Position Breakdown is now nested inside the" in src
    # Single card boundary count (6 total: Header + Size + Reqs +
    # Aging + Eligibility + IR cards, which matches the file). The
    # important check is open == close.
    opens = src.count("<Card ")
    closes = src.count("</Card>")
    assert opens == closes, f"unbalanced Card open/close: {opens}/{closes}"


# ── (3) Cap enforcement ─────────────────────────────────────────────

def test_backend_helper_check_position_breakdown_within_caps_exists():
    src = ROSTER_RULES.read_text()
    assert "def check_position_breakdown_within_caps(" in src
    # Helpful error string mentions which section overflowed and the
    # fix ("increase the section size first").
    assert "Increase {label} size first" in src


def test_leagues_put_imports_and_calls_cap_check():
    src = LEAGUES_PY.read_text()
    assert "from utils.roster_rules import check_position_breakdown_within_caps" in src
    # Called against EFFECTIVE values (post-update merge) so a save
    # that resizes rosters and per-position caps in one go isn't
    # punished by stale DB state.
    assert "effective_breakdown = (" in src
    assert "cap_err = check_position_breakdown_within_caps(" in src
    assert "raise HTTPException(status_code=400, detail=cap_err)" in src


def test_frontend_inline_cap_validation():
    src = ROSTERS_TAB.read_text()
    # Per-row error string computed reactively so the message
    # surfaces the instant the commissioner edits a cell.
    assert "const breakdownCapErrors: Record<string, string | null> = (() => {" in src
    assert "const hasBreakdownCapError = Object.values(breakdownCapErrors).some(Boolean);" in src
    # Save button disabled until the user resolves the conflict.
    assert "disabled={saving || hasBreakdownCapError}" in src
    # Per-row inline error testids for QA.
    assert "rosters-position-${row.key}-cap-error" in src
    # Top-level banner for screen-readers / scroll context.
    assert 'data-testid="rosters-cap-error-banner"' in src


# ── (4) "Prospect Pool Size" renamed to "Minors Team Size" ─────────

def test_label_renamed_to_minors_team_size():
    src = ROSTERS_TAB.read_text()
    assert "Minors Team Size (0–100)" in src
    # Old label is gone (would be confusing alongside the new one).
    assert "Prospect Pool Size" not in src
    # Schema field stays `minors_spots` for backward compat — only
    # the user-facing label changed.
    assert '["minors_spots", prospectPool, 0, 100]' in src
