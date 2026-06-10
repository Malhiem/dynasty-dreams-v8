"""Iter 149 — Seed pending-trade admin endpoint + Trading Block draft overlay."""
from pathlib import Path

from fastapi.testclient import TestClient
import importlib
import server  # noqa: F401 — ensures server fixtures register

FRONTEND = Path("/app/frontend/src")


def _read(rel: str) -> str:
    return (FRONTEND / rel).read_text(encoding="utf-8")


# ─── Frontend file-content checks ────────────────────────────────────


def test_trade_mode_button_renamed_on_draft_board_and_room():
    db = _read("lovable/pages/DraftBoard.tsx")
    dr = _read("lovable/pages/DraftRoom.tsx")
    assert 'Trade Mode: On' in db and 'Trade Mode: Off' in db
    assert 'Trade Mode: On' in dr and 'Trade Mode: Off' in dr
    # Old "Propose Trade" copy must be gone from the toggles
    assert '"Propose Trade"' not in db
    assert '"Propose Trade"' not in dr


def test_draft_room_has_trading_block_toggle_and_overlays():
    src = _read("lovable/pages/DraftRoom.tsx")
    # Toggle button testids
    assert 'data-testid="draft-room-trade-block-toggle"' in src
    assert 'data-testid="draft-room-trade-block-count"' in src
    # Megaphone icon imports
    assert "Megaphone" in src
    # Megaphone overlay testids (template literal because per-tile)
    assert 'data-testid={`draft-room-block-icon-${teamAbbr}' in src
    assert 'draft-room-eligible-block-${player.id}' in src
    # Quick-add for own tiles
    assert 'data-testid={`draft-room-block-add-${teamAbbr}' in src
    assert 'markAvailableForDraft' in src
    # Reads the league trade-block endpoint
    assert "/trade-block?league_id=" in src
    # Posts a draft-only entry
    assert 'draft_only: true' in src


def test_trade_block_create_model_has_draft_only_flag():
    src = (Path("/app/backend") / "trade_waiver_engine.py").read_text(encoding="utf-8")
    assert "draft_only" in src
    src2 = (Path("/app/backend/routes") / "trade_block.py").read_text(encoding="utf-8")
    assert 'bool(input.draft_only)' in src2 or '"draft_only": bool(input.draft_only)' in src2


# ─── Backend endpoint sanity (route registration) ────────────────────


def test_admin_seed_pending_trade_route_registered():
    from server import fastapi_app  # FastAPI instance before Socket.IO wrap
    paths = {r.path for r in fastapi_app.routes}
    assert "/api/admin/seed/pending-trade" in paths


def test_admin_seed_pending_trade_requires_admin():
    src = (Path("/app/backend/routes") / "admin.py").read_text(encoding="utf-8")
    # Has the route + the site-admin gate
    assert "@router.post(\"/admin/seed/pending-trade\")" in src
    assert "_is_site_admin(user)" in src
    # Creates pending + (when seed_terminal_fixtures) vetoed + executed
    assert '"status": status' in src or 'status: str' in src
    assert "seed_terminal_fixtures" in src
    assert '"vetoed"' in src and '"executed"' in src and '"pending"' in src
