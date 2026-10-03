"""Iter 231m — Guard tests for the major drafts.py → draft_pick_actions.py
extraction (make-pick, undo, swap, pause, seed-picks).

Largest extraction in the drafts.py decomposition campaign (-462 lines
in one cut, drafts.py 2414 → 1952). Locks the gain in place so the next
refactor can't regress.
"""
from pathlib import Path

DRAFTS = Path("/app/backend/routes/drafts.py")
ACTIONS = Path("/app/backend/routes/draft_pick_actions.py")
SERVER = Path("/app/backend/server.py")


def test_extracted_routes_live_in_draft_pick_actions():
    src = ACTIONS.read_text()
    for route in (
        '@router.post("/drafts/{draft_id}/pick")',
        '@router.post("/drafts/{draft_id}/undo")',
        '@router.patch("/drafts/{draft_id}/picks/{overall}")',
        '@router.post("/drafts/{draft_id}/pause")',
        '@router.post("/drafts/{draft_id}/seed-picks")',
    ):
        assert route in src, f"{route} missing from draft_pick_actions.py"


def test_request_models_extracted_too():
    src = ACTIONS.read_text()
    assert "class UndoDraftPicksRequest" in src
    assert "class SwapPickPlayerRequest" in src


def test_extracted_routes_no_longer_in_drafts():
    src = DRAFTS.read_text()
    for route in (
        '@router.post("/drafts/{draft_id}/pick")',
        '@router.post("/drafts/{draft_id}/undo")',
        '@router.patch("/drafts/{draft_id}/picks/{overall}")',
        '@router.post("/drafts/{draft_id}/pause")',
        '@router.post("/drafts/{draft_id}/seed-picks")',
    ):
        assert route not in src, f"{route} still in drafts.py — extraction incomplete"
    # The model classes should be gone too.
    assert "class UndoDraftPicksRequest" not in src
    assert "class SwapPickPlayerRequest" not in src


def test_perform_one_auto_pick_helper_stays_in_drafts():
    """Critical regression: `_perform_one_auto_pick` and
    `_seed_draft_picks_for_draft` are still referenced from many
    non-extracted call-sites in drafts.py AND from
    routes/admin_user_actions.py. They must NOT move."""
    src = DRAFTS.read_text()
    assert "async def _perform_one_auto_pick" in src
    assert "async def _seed_draft_picks_for_draft" in src
    assert "async def _early_start_clock_msg" in src


def test_draft_pick_actions_no_longer_late_binds():
    """Iter 231n superseded this — the late-binding helpers were
    removed once `draft_helpers.py` was extracted as a dedicated module.
    Now we assert the OPPOSITE: that the late-binding workaround is
    gone and the direct import is in place."""
    src = ACTIONS.read_text()
    assert "_early_start_clock_msg_fn" not in src
    assert "_seed_draft_picks_for_draft_fn" not in src
    assert "from routes import drafts as _drafts" not in src
    # The direct import replaces it.
    assert "from routes.draft_helpers import" in src


def test_server_wires_draft_pick_actions_router():
    src = SERVER.read_text()
    assert "draft_pick_actions as draft_pick_actions_routes" in src
    assert "draft_pick_actions_routes.setup(_router_deps)" in src
    assert "api_router.include_router(draft_pick_actions_routes.router)" in src


def test_drafts_py_size_ratchet_under_2000():
    """Iter 231m extraction brings drafts.py decisively under 2000 lines
    (current: 1952). Locks the gain so future PRs cannot regress."""
    count = len(DRAFTS.read_text().splitlines())
    assert count < 2000, (
        f"drafts.py grew to {count} lines — extract more before raising the cap."
    )
