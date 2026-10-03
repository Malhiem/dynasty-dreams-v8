"""Iter 231w — Draft module-size CI guard + final chat/config extraction.

After iter 231v drafts.py decomposed into 11 balanced modules. This
iter (a) extracts the last 3 in-draft endpoints (`send_draft_chat`,
`get_draft_chat`, `update_draft_config`) into a new
`routes/draft_chat_config.py` module, dropping drafts.py to ~270 lines,
and (b) locks in the cleanliness with a `test_no_draft_module_balloons`
CI guard so the next 6 months of features can't accidentally inflate
any single draft module back into a monolith.
"""
from tests.source_tree import read_source
from pathlib import Path

DRAFTS = Path("/app/backend/routes/drafts.py")
CHAT_CONFIG = Path("/app/backend/routes/draft_chat_config.py")
SERVER = Path("/app/backend/server.py")
ROUTES = Path("/app/backend/routes")


# Per-module size cap. Keep this CONSERVATIVE — the goal is to catch
# regressions, not legislate every line. Adjust upward only if a
# justified iter requires it.
MODULE_MAX_LINES = 1000


def test_chat_config_endpoints_live_in_new_module():
    src = read_source(CHAT_CONFIG)
    assert '@router.post("/drafts/{draft_id}/chat")' in src
    assert "async def send_draft_chat(" in src
    assert '@router.get("/drafts/{draft_id}/chat")' in src
    assert "async def get_draft_chat(" in src
    assert '@router.put("/drafts/{draft_id}/config")' in src
    assert "async def update_draft_config(" in src


def test_chat_config_endpoints_no_longer_in_drafts_py():
    src = read_source(DRAFTS, include_imports=False)
    assert '@router.post("/drafts/{draft_id}/chat")' not in src
    assert '@router.get("/drafts/{draft_id}/chat")' not in src
    assert '@router.put("/drafts/{draft_id}/config")' not in src
    assert "async def send_draft_chat" not in src
    assert "async def get_draft_chat" not in src
    assert "async def update_draft_config" not in src


def test_server_wires_draft_chat_config_router():
    src = read_source(SERVER)
    assert "draft_chat_config as draft_chat_config_routes" in src
    assert "draft_chat_config_routes.setup(_router_deps)" in src
    assert "api_router.include_router(draft_chat_config_routes.router)" in src


def test_send_draft_chat_guards_against_missing_draft():
    """Iter 231w — Fixed a latent NoneType crash in `send_draft_chat`.
    The legacy implementation in drafts.py called `_db().drafts.find_one`
    inline inside a dict-key expression and subscripted the result —
    a missing draft id 500'd. The relocated version now 404s gracefully."""
    src = read_source(CHAT_CONFIG)
    block = src.split("async def send_draft_chat")[1].split("\n@router.")[0]
    assert 'raise HTTPException(status_code=404, detail="Draft not found")' in block


def test_drafts_py_final_size_under_300_lines():
    """The very last ratchet. drafts.py is now auth + helpers +
    notifications + 5 backward-compat shims — nothing else should live
    in this file."""
    n = len(read_source(DRAFTS, include_imports=False).splitlines())
    assert n < 300, f"drafts.py grew to {n} lines — extract more endpoints!"
    print(f"drafts.py: {n} lines (cumulative from 2894 baseline: -{2894 - n}, -{(2894 - n) * 100 // 2894}%)")


def test_no_draft_module_balloons():
    """CI guard: every routes/draft_*.py module + drafts.py itself
    must stay under MODULE_MAX_LINES. Catches accidental regressions
    where someone inlines hundreds of lines into a single module
    instead of decomposing further."""
    offenders = []
    for path in sorted(ROUTES.glob("draft*.py")):
        n = len(read_source(path, include_imports=False).splitlines())
        if n >= MODULE_MAX_LINES:
            offenders.append(f"{path.name}: {n} lines (>= {MODULE_MAX_LINES})")
    assert not offenders, (
        f"Draft module(s) exceeded the {MODULE_MAX_LINES}-line cap:\n  "
        + "\n  ".join(offenders)
        + "\n\nExtract endpoints into a new sibling module — see "
        "iter231k-w decomposition pattern."
    )


def test_draft_module_inventory_present():
    """Asserts the canonical set of decomposed draft modules. New
    modules can be added; renames should re-bake this list."""
    expected = {
        "drafts.py",
        "draft_admin.py",
        "draft_auction.py",
        "draft_chat_config.py",
        "draft_config.py",
        "draft_helpers.py",
        "draft_inspection.py",
        "draft_lifecycle.py",
        "draft_order.py",
        "draft_pick_actions.py",
        "draft_picks.py",
        "draft_queue.py",
    }
    present = {p.name for p in ROUTES.glob("draft*.py")}
    missing = expected - present
    assert not missing, f"Missing draft modules: {sorted(missing)}"
