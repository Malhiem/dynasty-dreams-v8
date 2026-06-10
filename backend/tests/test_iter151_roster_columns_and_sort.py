"""Iter 151 — Dynamic stat columns + 3-click sort + trade-block toggle in roster panel.

Validates the static structure of the rewritten TruncatedRosterPanel + the
DraftRoom mount wiring + the on-block megaphones being always-visible.
"""
from pathlib import Path

FRONTEND = Path("/app/frontend/src")
BACKEND = Path("/app/backend")


def _read(rel: str) -> str:
    return (FRONTEND / rel).read_text(encoding="utf-8")


def test_truncated_roster_panel_has_sort_three_click_cycle():
    panel = _read("lovable/pages/draftroom/TruncatedRosterPanel.tsx")
    # Cycle implemented (desc → asc → reset)
    assert "cycleSort" in panel
    assert '"desc"' in panel and '"asc"' in panel
    # Reset path: setting col to null
    assert "{ col: null, dir: null }" in panel
    # Sort-button testids (template literal)
    assert 'data-testid={`draft-room-roster-sort-${col}`}' in panel


def test_position_order_with_goalies_pinned_to_bottom():
    panel = _read("lovable/pages/draftroom/TruncatedRosterPanel.tsx")
    assert 'POSITION_ORDER = ["C", "LW", "RW", "W", "D", "G"]' in panel
    # Goalies rendered in a separated block, not interleaved
    assert 'data-testid="draft-room-roster-goalies-header"' in panel
    assert 'data-testid="draft-room-roster-skaters"' in panel
    assert 'data-testid="draft-room-roster-goalies"' in panel


def test_trade_block_toggle_in_roster_panel():
    panel = _read("lovable/pages/draftroom/TruncatedRosterPanel.tsx")
    # Toggle vs read-only by team
    assert "canToggle = isMyTeam" in panel
    # Megaphone icon beside the Repeat (trade) icon in the same flex container
    assert "onToggleTradeBlock" in panel
    # aria-pressed reflects state
    assert "aria-pressed={onBlock}" in panel

    # DraftRoom wires the handler
    dr = _read("lovable/pages/DraftRoom.tsx")
    assert "toggleMyTeamTradeBlock" in dr
    assert "onToggleTradeBlock={toggleMyTeamTradeBlock}" in dr
    # Toggle calls DELETE /trade-block/{id} or POST /trade-block
    assert "api.delete(`/trade-block/" in dr
    assert 'api.post("/trade-block"' in dr


def test_on_block_megaphones_visible_without_toggle():
    """Iter 151 user-request — on-block megaphone overlays must render
    regardless of `tradeBlockMode` (only the "Mark available" action
    buttons depend on the toggle)."""
    src = _read("lovable/pages/DraftRoom.tsx")
    # Old (gated) form is gone
    assert "tradeBlockMode && (isPlayerOnBlock || isPickOnBlock)" not in src
    # New always-on form
    assert "onBlock = isPlayerOnBlock || isPickOnBlock" in src
    # Eligible list also un-gated
    assert "isOnBlock = tradeBlockMode && tradeBlockPlayerIds.has" not in src
    assert "isOnBlock = tradeBlockPlayerIds.has(String(player.id))" in src


def test_dynamic_stat_columns_from_scoring_config():
    panel = _read("lovable/pages/draftroom/TruncatedRosterPanel.tsx")
    # Reads scoring config from the API response
    assert "data?.scoring?.skater" in panel
    assert "data?.scoring?.goalie" in panel
    # Stat columns only appear for regular / playoffs views
    assert 'statFilter === "regular" || statFilter === "playoffs"' in panel
    # Stat label dictionary exists
    assert "STAT_LABELS" in panel and '"+/-"' in panel and '"SV%"' in panel

    # Backend wires the scoring categories into the response
    bsrc = (BACKEND / "routes/teams.py").read_text(encoding="utf-8")
    assert '"scoring":' in bsrc
    assert '"skater":' in bsrc and '"goalie":' in bsrc
    # And bucketed stats per player
    assert "_bucket_stat" in bsrc
    assert '"stats": cats' in bsrc


def test_fp_and_fppg_grid_alignment():
    """FP / FP/G must render in their own grid columns (no longer share a
    cell), so they line up with their headers."""
    panel = _read("lovable/pages/draftroom/TruncatedRosterPanel.tsx")
    # Grid templates derived dynamically
    assert "skaterGridTemplate" in panel and "goalieGridTemplate" in panel
    # Both header and rows use the SAME template
    assert "gridTemplateColumns: p.position" in panel
    assert "gridTemplateColumns: isGoalieSection" in panel
