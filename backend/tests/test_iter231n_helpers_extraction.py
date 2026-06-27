"""Iter 231n — Shared-helper extraction guards.

Moved `perform_one_auto_pick`, `seed_draft_picks_for_draft`, and
`early_start_clock_msg` from drafts.py into a dedicated
`routes/draft_helpers.py` module. This kills the late-binding workaround
in draft_pick_actions.py and lets admin_user_actions.py drop its
"local import to avoid cycle" comment.

The shims in drafts.py (`_perform_one_auto_pick`, `_seed_draft_picks_for_draft`,
`_early_start_clock_msg`) are preserved as thin pass-throughs so:
  (a) several pytest files grepping for `async def _xxx` in drafts.py
      source continue to pass without modification, and
  (b) any third-party importer of `routes.drafts._xxx` keeps working.
"""
from pathlib import Path

DRAFTS = Path("/app/backend/routes/drafts.py")
HELPERS = Path("/app/backend/routes/draft_helpers.py")
PICK_ACTIONS = Path("/app/backend/routes/draft_pick_actions.py")
ADMIN_ACTIONS = Path("/app/backend/routes/admin_user_actions.py")
SERVER = Path("/app/backend/server.py")


def test_helpers_module_owns_real_implementations():
    src = HELPERS.read_text()
    for name in (
        "async def seed_draft_picks_for_draft",
        "async def early_start_clock_msg",
        "async def perform_one_auto_pick",
    ):
        assert name in src, f"{name} missing from draft_helpers.py"


def test_drafts_py_keeps_shims_for_backcompat():
    """The `_xxx` names must still resolve in drafts.py because admin
    integration code (and several pytest suites) import / grep them.
    The shim body just delegates to the new helpers module."""
    src = DRAFTS.read_text()
    # Shim signatures still here.
    assert "async def _seed_draft_picks_for_draft" in src
    assert "async def _early_start_clock_msg" in src
    assert "async def _perform_one_auto_pick" in src
    # Each shim delegates to the new module. The exact import form is
    # `from routes.draft_helpers import <name> as _impl` — we accept any
    # form that mentions `from routes.draft_helpers import` near each
    # `_impl` alias.
    for name in (
        "seed_draft_picks_for_draft",
        "early_start_clock_msg",
        "perform_one_auto_pick",
    ):
        assert f"from routes.draft_helpers import {name}" in src, (
            f"shim for _{name} is missing the delegating import"
        )


def test_draft_pick_actions_no_longer_late_binds():
    src = PICK_ACTIONS.read_text()
    # Direct imports at the top of the module.
    assert (
        "from routes.draft_helpers import" in src
        and "early_start_clock_msg" in src
        and "seed_draft_picks_for_draft" in src
    ), "draft_pick_actions.py should plain-import from draft_helpers"
    # The old late-binding helper functions are gone.
    assert "_early_start_clock_msg_fn" not in src
    assert "_seed_draft_picks_for_draft_fn" not in src
    # And there's no `from routes import drafts` workaround left.
    assert "from routes import drafts as _drafts" not in src


def test_admin_user_actions_imports_from_helpers_module():
    src = ADMIN_ACTIONS.read_text()
    assert "from routes.draft_helpers import perform_one_auto_pick" in src
    # The legacy "local import to avoid cycle" comment is gone.
    assert "from routes.drafts import _perform_one_auto_pick" not in src
    # Call-site updated to the new name.
    assert "await perform_one_auto_pick(draft_id, source=\"eviction\")" in src


def test_server_wires_draft_helpers_module():
    src = SERVER.read_text()
    assert "draft_helpers as draft_helpers_module" in src
    assert "draft_helpers_module.setup(_router_deps)" in src


def test_drafts_py_size_ratchet_under_1800():
    """Helper extraction trimmed another ~140 lines off drafts.py.
    Lock the gain under 1800 lines (current: 1773)."""
    count = len(DRAFTS.read_text().splitlines())
    assert count < 1800, (
        f"drafts.py grew to {count} lines — extract more before raising the cap."
    )


def test_helpers_module_has_no_router():
    """draft_helpers is intentionally helpers-only — it should not
    register any HTTP routes (no `@router.get`, `@router.post`, etc.)."""
    src = HELPERS.read_text()
    for verb in ("@router.get", "@router.post", "@router.put", "@router.patch", "@router.delete"):
        assert verb not in src, f"{verb} found in draft_helpers.py — that module is helpers-only"
