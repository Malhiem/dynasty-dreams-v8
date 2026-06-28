"""Iter 231v — Final drafts.py stretch (under <600 lines).

Six endpoints moved out:
  • get_draft_picks, get_draft_related_trades, get_draft_player_stats,
    get_team_draft_picks → routes/draft_inspection.py (4 reads + the
    existing inspection set live there).
  • get_league_draft_order, update_league_draft_order_config (+ the
    DRAFT_ORDER_METHODS enum + DraftOrderConfigRequest model)
    → new routes/draft_order.py module.
"""
from pathlib import Path

DRAFTS = Path("/app/backend/routes/drafts.py")
INSPECTION = Path("/app/backend/routes/draft_inspection.py")
ORDER = Path("/app/backend/routes/draft_order.py")
SERVER = Path("/app/backend/server.py")


def test_read_endpoints_relocated_to_draft_inspection():
    src = INSPECTION.read_text()
    assert '@router.get("/drafts/{league_id}/picks")' in src
    assert "async def get_draft_picks(" in src
    assert '@router.get("/drafts/{draft_id}/related-trades")' in src
    assert "async def get_draft_related_trades(" in src
    assert '@router.get("/drafts/{draft_id}/player-stats")' in src
    assert "async def get_draft_player_stats(" in src
    assert '@router.get("/teams/{team_id}/draft-picks")' in src
    assert "async def get_team_draft_picks(" in src


def test_order_endpoints_live_in_draft_order():
    src = ORDER.read_text()
    assert '@router.get("/leagues/{league_id}/draft-order")' in src
    assert "async def get_league_draft_order(" in src
    assert '@router.put("/leagues/{league_id}/draft-order/config")' in src
    assert "async def update_league_draft_order_config(" in src
    # The enum + Pydantic model travelled with the endpoints.
    assert "DRAFT_ORDER_METHODS = " in src
    assert "class DraftOrderConfigRequest(BaseModel):" in src


def test_relocated_routes_no_longer_in_drafts_py():
    src = DRAFTS.read_text()
    for decorator in (
        '@router.get("/drafts/{league_id}/picks")',
        '@router.get("/drafts/{draft_id}/related-trades")',
        '@router.get("/drafts/{draft_id}/player-stats")',
        '@router.get("/teams/{team_id}/draft-picks")',
        '@router.get("/leagues/{league_id}/draft-order")',
        '@router.put("/leagues/{league_id}/draft-order/config")',
    ):
        assert decorator not in src, f"Decorator still in drafts.py: {decorator}"
    for fn in (
        "async def get_draft_picks",
        "async def get_draft_related_trades",
        "async def get_draft_player_stats",
        "async def get_team_draft_picks",
        "async def get_league_draft_order",
        "async def update_league_draft_order_config",
    ):
        assert fn not in src, f"Function definition still in drafts.py: {fn}"


def test_server_wires_draft_order_router():
    src = SERVER.read_text()
    assert "draft_order as draft_order_routes" in src
    assert "draft_order_routes.setup(_router_deps)" in src
    assert "api_router.include_router(draft_order_routes.router)" in src


def test_drafts_py_under_600_lines():
    """Iter 231t locked at <1200; iter 231v locks at <600.
    drafts.py baseline was 2894 lines pre-iter231."""
    n = len(DRAFTS.read_text().splitlines())
    assert n < 600, f"drafts.py grew back to {n} lines — extract more!"
    # Informational log so the regression ratchet history is auditable.
    print(f"drafts.py: {n} lines (cumulative from 2894: -{2894 - n}, -{(2894 - n) * 100 // 2894}%)")


def test_draft_order_module_has_no_late_binding_imports():
    """draft_order.py is fully self-contained — no top-level
    `from routes.drafts` imports."""
    src = ORDER.read_text()
    assert "from routes.drafts" not in src
    # And uses the `setup(deps)` injection pattern, not a global db var.
    assert "def setup(deps: dict) -> None:" in src
    assert "def _db():" in src
