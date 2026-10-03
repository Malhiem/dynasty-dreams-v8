"""Iter 231c — Read-only draft endpoints extracted into `draft_inspection.py`.

Locks the split so future feature work doesn't accidentally re-merge the
inspection routes back into the already-large drafts.py.
"""
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DRAFTS = REPO / "backend/routes/drafts.py"
DRAFT_INSPECTION = REPO / "backend/routes/draft_inspection.py"
SERVER = REPO / "backend/server.py"

INSPECTION_ROUTES = [
    '@router.get("/drafts")',
    '@router.get("/drafts/{draft_id}")',
    '@router.get("/drafts/{draft_id}/board")',
    '@router.get("/drafts/{draft_id}/stats")',
    '@router.get("/drafts/{draft_id}/edit-preview")',
    '@router.get("/leagues/{league_id}/upcoming-drafts")',
]


def test_draft_inspection_module_owns_extracted_routes():
    src = DRAFT_INSPECTION.read_text()
    for route in INSPECTION_ROUTES:
        assert route in src, f"{route} should live in draft_inspection.py"
    # Function signatures preserved.
    for name in (
        "async def get_drafts",
        "async def get_draft(",
        "async def get_draft_board(",
        "async def get_draft_stats(",
        "async def edit_draft_preview(",
        "async def get_upcoming_drafts(",
    ):
        assert name in src, f"{name} should be defined in draft_inspection.py"


def test_drafts_module_no_longer_owns_inspection_routes():
    src = DRAFTS.read_text()
    for route in INSPECTION_ROUTES:
        assert route not in src, f"{route} must be moved out of drafts.py"


def test_server_wires_draft_inspection_router():
    src = SERVER.read_text()
    assert "draft_inspection as draft_inspection_routes" in src
    assert "draft_inspection_routes.setup(_router_deps)" in src
    assert "api_router.include_router(draft_inspection_routes.router)" in src


def test_drafts_py_under_line_ceiling():
    """Iter 231c — drafts.py shrank from 3212 → ~2868 lines. Lock the
    win at < 3000 so the next refactor pass can ratchet again."""
    line_count = len(DRAFTS.read_text().splitlines())
    assert line_count < 3000, (
        f"drafts.py is {line_count} lines — keep it under 3000. "
        f"Consider extracting another route group to its own module."
    )
