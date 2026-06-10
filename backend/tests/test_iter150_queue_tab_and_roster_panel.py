"""Iter 150 — Queue tab + Truncated Roster panel + roster-truncated endpoint."""
from pathlib import Path

FRONTEND = Path("/app/frontend/src")
BACKEND = Path("/app/backend")


def _read(rel_under_frontend: str) -> str:
    return (FRONTEND / rel_under_frontend).read_text(encoding="utf-8")


def test_queue_tab_in_draft_room():
    src = _read("lovable/pages/DraftRoom.tsx")
    # New 3-tab layout with Queue between Eligible and Shortlist
    for tid in (
        "draft-room-tab-eligible",
        "draft-room-tab-queue",
        "draft-room-tab-shortlist",
    ):
        assert f'data-testid="{tid}"' in src, f"Missing tab testid: {tid}"
    # The old col-2 LEFT "My Queue" Card is gone (no more dedicated lg:col-span-2 queue card)
    assert "lg:col-span-2" not in src
    # Queue list renders inside TabsContent
    assert 'value="queue"' in src
    assert 'data-testid="draft-room-queue-list"' in src


def test_status_icons_on_eligible_player_cards():
    src = _read("lovable/pages/DraftRoom.tsx")
    # Shortlisted + queued status indicators (template-literal testids)
    assert 'data-testid={`draft-room-status-shortlisted-${player.id}`}' in src
    assert 'data-testid={`draft-room-status-queued-${player.id}`}' in src
    # Star + ListOrdered icons used
    assert "Star" in src and "ListOrdered" in src


def test_truncated_roster_panel_mounted_with_team_switcher():
    src = _read("lovable/pages/DraftRoom.tsx")
    assert "import TruncatedRosterPanel" in src
    assert "<TruncatedRosterPanel" in src

    panel = _read("lovable/pages/draftroom/TruncatedRosterPanel.tsx")
    # Required testids
    for tid in (
        "draft-room-roster-panel",
        "draft-room-roster-team-name",
        "draft-room-roster-team-switcher",
        "draft-room-roster-stat-filter",
        "draft-room-roster-count",
    ):
        assert f'data-testid="{tid}"' in panel, f"Missing testid: {tid}"
    # Player link goes to /players/{id}
    assert 'to={`/players/${p.id}`}' in panel
    # Per-row testids (template literals)
    assert 'data-testid={`draft-room-roster-row-${p.id}`}' in panel
    assert 'data-testid={`draft-room-roster-block-${p.id}`}' in panel
    assert 'data-testid={`draft-room-roster-trade-${p.id}`}' in panel
    # Filter options
    for o in ("season", "regular", "playoffs", "l30", "l7"):
        assert f'"{o}"' in panel, f"Missing stat filter option: {o}"
    # Cap hit shown conditionally
    assert "capEnabled" in panel


def test_roster_truncated_endpoint_registered():
    from server import fastapi_app
    paths = {r.path for r in fastapi_app.routes}
    assert "/api/teams/{team_id}/roster-truncated" in paths


def test_roster_truncated_reads_canonical_team_roster_field():
    """Iter 150 bug-fix — endpoint must read from `team.roster` (same as
    /api/roster/{team_id}) instead of the secondary `db.rosters` collection
    so the Draft Room panel stays in lock-step with the Rosters page."""
    src = (BACKEND / "routes/teams.py").read_text(encoding="utf-8")
    # 1) Reads canonical team.roster first
    assert 'team.get("roster")' in src
    # 2) Falls back to legacy team.player_ids
    assert 'team.get("player_ids")' in src
    # 3) Uses the league scoring_configs for fantasy_points (matches Rosters page)
    assert "scoring_configs" in src
    # 4) Optional db.rosters fallback for older seed data
    assert "db.rosters" in src


def test_trade_block_add_icons_render_on_every_pick_tile():
    """Iter 150 bug-fix — the Mark-Available megaphone button must render on
    EVERY pick tile when Trading Block is on (mirrors Trade Mode pattern).
    Previously gated by `isMyTile` so users only saw 0 icons when the mock
    abbrs didn't match their real team's logo_abbr."""
    src = _read("lovable/pages/DraftRoom.tsx")
    # The render gate no longer includes `isMyTile`
    assert "tradeBlockMode && !onBlock && isMyTile" not in src
    # Click handler still validates ownership
    assert "You can only mark your own picks available" in src


def test_draft_board_uses_megaphone_for_on_block_picks():
    src = _read("lovable/pages/DraftBoard.tsx")
    # Old ShoppingCart in the "Available" badge is replaced with Megaphone
    assert "Megaphone" in src
    # Two new testids surfaced (traded + native)
    assert 'data-testid={`draft-board-block-icon-${team.abbr}-r${round}`}' in src
    assert 'data-testid={`draft-board-block-icon-traded-${team.abbr}-r${round}`}' in src


def test_roster_truncated_backend_logic():
    src = (BACKEND / "routes/teams.py").read_text(encoding="utf-8")
    assert "/teams/{team_id}/roster-truncated" in src
    # Stat-filter bucketed lookups
    assert "stat_filter" in src
    assert "fp_per_game" in src
    assert "cap_hit" in src
