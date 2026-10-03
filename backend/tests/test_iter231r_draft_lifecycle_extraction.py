"""Iter 231r — draft_lifecycle extraction guards.

Three lifecycle endpoints (auto-init / start / auto-pick) moved out of
`routes/drafts.py` into a dedicated `routes/draft_lifecycle.py` module.
The cross-module helper shims (`_perform_one_auto_pick`,
`_early_start_clock_msg`) stay in drafts.py for backward compat with
several legacy pytests that grep for them.
"""
from pathlib import Path

DRAFTS = Path("/app/backend/routes/drafts.py")
LIFECYCLE = Path("/app/backend/routes/draft_lifecycle.py")
SERVER = Path("/app/backend/server.py")


def test_extracted_routes_live_in_draft_lifecycle():
    src = LIFECYCLE.read_text()
    assert "@router.post(\"/drafts/auto-init/{league_id}\")" in src
    assert "async def auto_init_draft(" in src
    assert "@router.post(\"/drafts/{draft_id}/start\")" in src
    assert "async def start_draft(" in src
    assert "@router.post(\"/drafts/{draft_id}/auto-pick\")" in src
    assert "async def auto_pick_for_on_clock_team(" in src


def test_extracted_routes_no_longer_in_drafts_py():
    src = DRAFTS.read_text()
    # Route decorators gone.
    assert "@router.post(\"/drafts/auto-init/{league_id}\")" not in src
    assert "@router.post(\"/drafts/{draft_id}/start\")" not in src
    assert "@router.post(\"/drafts/{draft_id}/auto-pick\")" not in src
    # Endpoint function bodies gone (no `async def auto_init_draft` etc.).
    assert "async def auto_init_draft" not in src
    assert "async def start_draft" not in src
    assert "async def auto_pick_for_on_clock_team" not in src


def test_helper_shims_remain_for_backcompat():
    """The `_perform_one_auto_pick` / `_early_start_clock_msg` shims must
    stay so a handful of legacy grep-style tests + any external importer
    of `routes.drafts._xxx` keeps working."""
    src = DRAFTS.read_text()
    assert "async def _perform_one_auto_pick" in src
    assert "async def _early_start_clock_msg" in src
    # Both shims must delegate to the real impl in draft_helpers (not
    # contain the actual logic) so drafts.py stays small.
    assert "from routes.draft_helpers import perform_one_auto_pick as _impl" in src
    assert "from routes.draft_helpers import early_start_clock_msg as _impl" in src


def test_lifecycle_imports_helpers_directly():
    """draft_lifecycle.py must `from routes.draft_helpers import ...` at
    module load — no late-binding `from routes import drafts` inside
    function bodies (that pattern was killed in iter 231n)."""
    src = LIFECYCLE.read_text()
    assert "from routes.draft_helpers import (" in src
    # No late-binding workaround inside any function body.
    assert "from routes import drafts as " not in src


def test_server_wires_draft_lifecycle_router():
    src = SERVER.read_text()
    assert "draft_lifecycle as draft_lifecycle_routes" in src
    assert "draft_lifecycle_routes.setup(_router_deps)" in src
    assert "api_router.include_router(draft_lifecycle_routes.router)" in src


def test_drafts_py_size_ratchet_under_1400_lines():
    """Iter 231m locked at <2000; iter 231n at <1800; iter 231r locks
    at <1400. Re-ratcheted with each successful extraction so the file
    can't regress."""
    n = len(DRAFTS.read_text().splitlines())
    assert n < 1400, f"drafts.py grew back to {n} lines — extract more endpoints!"


def test_perform_one_auto_pick_handles_list_player_criteria():
    """Iter 231r — Defensive coercion of legacy drafts where
    `player_criteria` was accidentally stored as a list. The helper
    should str-coerce safely instead of crashing the worker."""
    helpers = Path("/app/backend/routes/draft_helpers.py").read_text()
    assert "isinstance(raw_criteria, list)" in helpers
    assert "str(raw_criteria).lower()" in helpers
