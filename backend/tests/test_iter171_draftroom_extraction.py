"""
Iter 171 — Static guards for the Draft Room extraction.

Confirms the major presentational pieces are now in their own files,
the parent file is meaningfully smaller, and the tile / card content
matches the user-specified behavior:
  • Selected player card still shows the "P" (points) column.
  • Draft Board tile no longer renders a "{n} pts" line.
  • Draft Board tile shows the NHL team for NHL players and the feeder
    league for non-NHL players (single source of truth: the IIFE we
    inserted at Iter 171).
"""
from pathlib import Path
import re

ROOT = Path("/app/frontend/src/lovable/pages")


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def test_extracted_files_exist():
    assert (ROOT / "draftroom" / "DraftLiveTile.tsx").exists()
    assert (ROOT / "draftroom" / "DraftBoard.tsx").exists()
    assert (ROOT / "draftroom" / "PlayerSearchPanel.tsx").exists()
    assert (ROOT / "draftroom" / "draftConstants.ts").exists()


def test_parent_imports_extracted_components():
    src = read(ROOT / "DraftRoom.tsx")
    assert 'from "@/lovable/pages/draftroom/DraftLiveTile"' in src
    assert 'from "@/lovable/pages/draftroom/DraftBoard"' in src
    assert 'from "@/lovable/pages/draftroom/draftConstants"' in src
    # Parent mounts both subcomponents.
    assert "<DraftLiveTile" in src
    assert "<DraftBoard" in src


def test_parent_no_longer_holds_extracted_jsx():
    src = read(ROOT / "DraftRoom.tsx")
    # The two huge anchor strings only existed inside the extracted blocks.
    assert "Start Draft Early (No Clock)" not in src
    assert "Filter by owner" not in src
    # The local helper / constant definitions are gone (re-imported).
    assert "function formatCountdown(" not in src
    assert "function formatPickTimer(" not in src
    assert "const positionColors: Record<string, string> = {" not in src
    assert "const positionTints: Record<string, string> = {" not in src


def test_parent_line_count_under_refactor_target():
    src = read(ROOT / "DraftRoom.tsx")
    # Iter 170 baseline was 2,250 lines; Iter 171 target was "well under
    # 2,000" after extracting the Live Tile + Draft Board.
    assert src.count("\n") < 1700


def test_selected_player_card_restores_points_column():
    src = read(ROOT / "draftroom" / "SelectedPlayerCard.tsx")
    # P (points) row is back and the grid is 7-wide again.
    assert '{ label: "P", v: player.pts }' in src
    assert "grid-cols-7" in src
    assert "grid-cols-6" not in src


def test_draft_board_tile_drops_points_line():
    src = read(ROOT / "draftroom" / "DraftBoard.tsx")
    # No "{n} pts" rendering anywhere on the tile.
    assert "} pts</span>" not in src
    assert "pick.player.pts" not in src


def test_draft_board_tile_team_or_league_logic():
    """For NHL players the tile shows the nhlTeam; for non-NHL players it
    shows the league. We assert the IIFE that implements that switch is
    present verbatim (plus the new affiliation testid)."""
    src = read(ROOT / "draftroom" / "DraftBoard.tsx")
    assert 'const isNhl = (pick.player.league || "").toUpperCase() === "NHL"' in src
    assert "draft-board-tile-affiliation-" in src
    # NHL branch prefers nhlTeam, non-NHL branch prefers league.
    assert "pick.player.nhlTeam || pick.player.team || pick.player.league" in src
    assert "pick.player.league || pick.player.nhlTeam" in src


def test_draft_constants_shared_module_shape():
    src = read(ROOT / "draftroom" / "draftConstants.ts")
    for symbol in ("positionColors", "positionTints", "formatCountdown", "formatPickTimer"):
        assert f"export const {symbol}" in src or f"export function {symbol}" in src, symbol


def test_draft_live_tile_renders_known_testids():
    """Iter 170-era selectors (criteria badge, next-on-clock, picks-until-
    my-turn, undo bar) must survive the extraction so QA scripts and
    integration tests keep passing."""
    src = read(ROOT / "draftroom" / "DraftLiveTile.tsx")
    for tid in (
        "draft-room-on-the-clock-team",
        "draft-room-criteria-badge",
        "draft-room-next-on-clock",
        "draft-picks-until-my-turn",
        "draft-room-simulate-pick",
        "draft-room-undo-bar",
        "draft-room-undo-count",
        "draft-room-undo-pick",
    ):
        assert tid in src, tid


def test_draft_board_renders_known_testids():
    src = read(ROOT / "draftroom" / "DraftBoard.tsx")
    for tid in (
        "draft-board-owner-filter",
        "draft-board-owner-clear",
        "draft-board-swap-search",
        "draft-board-tile-",
        "draft-board-pick-conditional-",
        "draft-board-pick-traded-",
        "draft-board-auto-pick-",
        "draft-board-swap-btn-",
    ):
        assert tid in src, tid
