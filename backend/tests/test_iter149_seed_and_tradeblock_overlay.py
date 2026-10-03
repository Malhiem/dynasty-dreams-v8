"""Iter 149 — Seed pending-trade admin endpoint + Trading Block draft overlay."""
from tests.source_tree import read_source
from pathlib import Path

from fastapi.testclient import TestClient
import importlib
import server  # noqa: F401 — ensures server fixtures register

FRONTEND = Path("/app/frontend/src")


def _read(rel: str) -> str:
    # Iter 171 — DraftRoom.tsx was split into sub-components. To keep
    # grep-style legacy assertions working, returning the concatenation
    # of the parent + extracted draftroom/* files when asked for it.
    if rel.endswith('lovable/pages/DraftRoom.tsx'):
        parts = []
        for sub in (
            'lovable/pages/DraftRoom.tsx',
            'lovable/pages/draftroom/DraftLiveTile.tsx',
            'lovable/pages/draftroom/DraftBoard.tsx',
            'lovable/pages/draftroom/PlayerSearchPanel.tsx',
            'lovable/pages/draftroom/draftConstants.ts',
        ):
            fp = FRONTEND / sub
            if fp.exists():
                parts.append(read_source(fp, encoding='utf-8'))
        return chr(10).join(parts)
    return read_source(FRONTEND / rel, encoding='utf-8')


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
    src = read_source(Path("/app/backend") / "trade_waiver_engine.py", encoding="utf-8")
    assert "draft_only" in src
    src2 = read_source(Path("/app/backend/routes") / "trade_block.py", encoding="utf-8")
    assert 'bool(input.draft_only)' in src2 or '"draft_only": bool(input.draft_only)' in src2


# ─── Backend endpoint sanity (route registration) ────────────────────


def test_admin_seed_pending_trade_route_registered():
    from server import fastapi_app  # FastAPI instance before Socket.IO wrap
    paths = {r.path for r in fastapi_app.routes}
    assert "/api/admin/seed/pending-trade" in paths


def test_admin_seed_pending_trade_requires_admin():
    src = read_source(Path("/app/backend/routes") / "admin.py", encoding="utf-8")
    # Has the route + the site-admin gate
    assert "@router.post(\"/admin/seed/pending-trade\")" in src
    assert "_is_site_admin(user)" in src
    # Creates pending + (when seed_terminal_fixtures) vetoed + executed
    assert '"status": status' in src or 'status: str' in src
    assert "seed_terminal_fixtures" in src
    assert '"vetoed"' in src and '"executed"' in src and '"pending"' in src
