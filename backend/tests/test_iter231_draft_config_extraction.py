"""Iter 231 — Refactor: draft_config endpoints extracted from drafts.py.

Guards the modular split so that future edits don't accidentally re-merge
the keeper/expansion/protection-list/lottery endpoints back into the
already-oversized drafts.py.
"""
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DRAFTS = REPO / "backend/routes/drafts.py"
DRAFT_CONFIG = REPO / "backend/routes/draft_config.py"
SERVER = REPO / "backend/server.py"


def test_draft_config_module_owns_extracted_routes():
    """All moved endpoints live in `routes/draft_config.py`."""
    src = DRAFT_CONFIG.read_text()
    for route in [
        '"/leagues/{league_id}/keeper-config"',
        '"/leagues/{league_id}/expansion-config"',
        '"/leagues/{league_id}/next-draft-type"',
        '"/leagues/{league_id}/first-draft-completed"',
        '"/leagues/{league_id}/protection-list/status"',
        '"/leagues/{league_id}/protection-list/{team_id}"',
        '"/leagues/{league_id}/protection-list/{team_id}/toggle"',
        '"/leagues/{league_id}/protection-list/auto-protect"',
        '"/leagues/{league_id}/expansion-draft-board"',
        '"/admin/draft-lottery-date"',
    ]:
        assert route in src, f"{route} should live in draft_config.py"
    # Shared constants live with the routes that use them
    for token in (
        "KEEPER_COST_METHODS",
        "EXPANSION_LIST_VISIBILITY",
        "VALID_NEXT_DRAFT_TYPES",
        "_resolve_draft_type",
    ):
        assert token in src, f"{token} should live in draft_config.py"


def test_drafts_module_no_longer_owns_extracted_routes():
    """`routes/drafts.py` should not re-define the moved endpoints."""
    src = DRAFTS.read_text()
    for route in [
        '"/leagues/{league_id}/keeper-config"',
        '"/leagues/{league_id}/expansion-config"',
        '"/leagues/{league_id}/next-draft-type"',
        '"/leagues/{league_id}/first-draft-completed"',
        '"/leagues/{league_id}/protection-list/status"',
        '"/leagues/{league_id}/protection-list/{team_id}"',
        '"/leagues/{league_id}/protection-list/{team_id}/toggle"',
        '"/leagues/{league_id}/protection-list/auto-protect"',
        '"/leagues/{league_id}/expansion-draft-board"',
        '"/admin/draft-lottery-date"',
    ]:
        assert route not in src, f"{route} must be moved out of drafts.py"


def test_server_wires_draft_config_router():
    src = SERVER.read_text()
    assert "draft_config as draft_config_routes" in src
    assert "draft_config_routes.setup(_router_deps)" in src
    assert "api_router.include_router(draft_config_routes.router)" in src


def test_drafts_py_under_line_ceiling():
    """Hard ratchet: drafts.py must stay under 3300 lines post-refactor.

    Iter 231 brought it from 3720 → ~3170. The ratchet locks in the win
    so future feature work doesn't quietly re-grow the file. Drop this
    further once additional extractions ship.
    """
    line_count = len(DRAFTS.read_text().splitlines())
    assert line_count < 3300, (
        f"drafts.py is {line_count} lines — keep it under 3300. "
        f"Consider extracting another route group to its own module."
    )
