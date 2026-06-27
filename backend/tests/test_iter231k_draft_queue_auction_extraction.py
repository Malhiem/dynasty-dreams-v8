"""Iter 231k — Guard tests for the drafts.py → draft_queue.py +
draft_auction.py extraction.

Ratchets `len(drafts.py)` down so future refactors cannot accidentally
re-grow the file, AND asserts the extracted routes live in their new
homes and not in drafts.py.
"""
from pathlib import Path

DRAFTS = Path("/app/backend/routes/drafts.py")
DRAFT_QUEUE = Path("/app/backend/routes/draft_queue.py")
DRAFT_AUCTION = Path("/app/backend/routes/draft_auction.py")
SERVER = Path("/app/backend/server.py")


def test_draft_queue_routes_live_in_new_module():
    src = DRAFT_QUEUE.read_text()
    for route in (
        '@router.put("/teams/{team_id}/draft-queue")',
        '@router.get("/teams/{team_id}/draft-queue")',
        '@router.put("/teams/{team_id}/shortlist")',
        '@router.get("/teams/{team_id}/shortlist")',
    ):
        assert route in src, f"missing {route} in draft_queue.py"


def test_auction_routes_live_in_new_module():
    src = DRAFT_AUCTION.read_text()
    for route in (
        '@router.post("/drafts/{draft_id}/auction/nominate")',
        '@router.post("/drafts/{draft_id}/auction/bid")',
        '@router.post("/drafts/{draft_id}/auction/resolve")',
        '@router.get("/drafts/{draft_id}/auction/state")',
        '@router.post("/drafts/{draft_id}/auction/init-budgets")',
    ):
        assert route in src, f"missing {route} in draft_auction.py"


def test_extracted_routes_no_longer_in_drafts():
    src = DRAFTS.read_text()
    for route in (
        '@router.put("/teams/{team_id}/draft-queue")',
        '@router.put("/teams/{team_id}/shortlist")',
        '@router.post("/drafts/{draft_id}/auction/nominate")',
        '@router.post("/drafts/{draft_id}/auction/bid")',
        '@router.post("/drafts/{draft_id}/auction/resolve")',
        '@router.get("/drafts/{draft_id}/auction/state")',
        '@router.post("/drafts/{draft_id}/auction/init-budgets")',
    ):
        assert route not in src, f"{route} still in drafts.py — extraction incomplete"


def test_server_wires_new_routers():
    src = SERVER.read_text()
    assert "draft_queue as draft_queue_routes" in src
    assert "draft_auction as draft_auction_routes" in src
    assert "draft_queue_routes.setup(_router_deps)" in src
    assert "draft_auction_routes.setup(_router_deps)" in src
    assert "api_router.include_router(draft_queue_routes.router)" in src
    assert "api_router.include_router(draft_auction_routes.router)" in src


def test_drafts_py_size_ratchet_under_2600():
    """Lock in the iter 231k extraction win so the next refactor pass
    must keep drafts.py at most 2600 lines (current: 2526 post-extraction).
    Raise this ceiling only when intentionally re-growing the file."""
    line_count = len(DRAFTS.read_text().splitlines())
    assert line_count < 2600, (
        f"drafts.py grew to {line_count} lines; extract more routes before raising the cap."
    )
