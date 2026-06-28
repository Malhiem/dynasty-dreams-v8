"""Iter 231t — draft_admin + eligible-players extraction guards.

Four CRUD endpoints (create_draft, delete_draft, restore_draft,
patch_draft) moved out of `routes/drafts.py` into a new
`routes/draft_admin.py` module. `get_draft_eligible_players` moved
into the existing `routes/draft_inspection.py` module (joining the
other read-only endpoints).
"""
from pathlib import Path

DRAFTS = Path("/app/backend/routes/drafts.py")
ADMIN = Path("/app/backend/routes/draft_admin.py")
INSPECTION = Path("/app/backend/routes/draft_inspection.py")
SERVER = Path("/app/backend/server.py")


def test_extracted_admin_routes_live_in_draft_admin():
    src = ADMIN.read_text()
    assert '@router.post("/drafts")' in src
    assert "async def create_draft(" in src
    assert '@router.delete("/drafts/{draft_id}")' in src
    assert "async def delete_draft(" in src
    assert '@router.post("/drafts/{draft_id}/restore")' in src
    assert "async def restore_draft(" in src
    assert '@router.patch("/drafts/{draft_id}")' in src
    assert "async def patch_draft(" in src


def test_eligible_players_lives_in_draft_inspection():
    src = INSPECTION.read_text()
    assert '@router.get("/drafts/{draft_id}/eligible-players")' in src
    assert "async def get_draft_eligible_players(" in src


def test_extracted_routes_no_longer_in_drafts_py():
    src = DRAFTS.read_text()
    # Decorator + function definitions all gone.
    assert '@router.post("/drafts")' not in src
    assert '@router.delete("/drafts/{draft_id}")' not in src
    assert '@router.post("/drafts/{draft_id}/restore")' not in src
    assert '@router.patch("/drafts/{draft_id}")' not in src
    assert '@router.get("/drafts/{draft_id}/eligible-players")' not in src
    assert "async def create_draft" not in src
    assert "async def delete_draft" not in src
    assert "async def restore_draft" not in src
    assert "async def patch_draft" not in src
    assert "async def get_draft_eligible_players" not in src


def test_seed_shim_remains_in_drafts_py():
    """The `_seed_draft_picks_for_draft` shim must stay so the helper
    shim contract for legacy importers + grep-style tests keeps working."""
    src = DRAFTS.read_text()
    assert "async def _seed_draft_picks_for_draft" in src
    # Must delegate (not contain real impl).
    assert "from routes.draft_helpers import seed_draft_picks_for_draft as _impl" in src


def test_draft_admin_imports_helpers_directly():
    """No late-binding workarounds — uses direct imports from
    routes.draft_helpers (the pattern locked in by iter 231n)."""
    src = ADMIN.read_text()
    assert "from routes.draft_helpers import seed_draft_picks_for_draft" in src
    # _abbrs_with_dedup is the ONE function still imported lazily to
    # avoid a cycle; everything else is top-of-module.
    assert "from routes.drafts import _abbrs_with_dedup as _impl" in src


def test_server_wires_draft_admin_router():
    src = SERVER.read_text()
    assert "draft_admin as draft_admin_routes" in src
    assert "draft_admin_routes.setup(_router_deps)" in src
    assert "api_router.include_router(draft_admin_routes.router)" in src


def test_drafts_py_size_ratchet_under_1200_lines():
    """Iter 231r locked at <1400; iter 231t locks at <1200.
    Cumulative target. drafts.py started at 2894 lines pre-iter231."""
    n = len(DRAFTS.read_text().splitlines())
    assert n < 1200, f"drafts.py grew back to {n} lines — extract more endpoints!"
    # Stretch target — log informationally that we're well under it.
    print(f"drafts.py is currently {n} lines (cumulative from 2894 baseline: -{2894 - n} lines, -{(2894 - n) * 100 // 2894}%)")


def test_admin_module_does_not_late_bind_create_notification():
    """create_notification is resolved via `_deps["create_notification"]`
    so we don't import `routes.drafts` at module load (would cycle)."""
    src = ADMIN.read_text()
    # Must NOT have a top-level `from routes.drafts import create_notification`.
    assert "from routes.drafts import create_notification" not in src
    # Must declare the `_create_notification` delegator that pulls from _deps.
    assert "_deps.get(\"create_notification\")" in src
