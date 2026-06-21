"""
Iter 187/188 — Waivers & Free Agency hardening tests.

Covers four sub-features the user pulled in for Phase B:
  (a) Salary-cap enforcement on `POST /api/waivers/claim` (422 cap_breach
      payload mirrors the precheck math).
  (b) Trade veto tracking — already implemented in trades.py; assert the
      contract stays stable.
  (c) Trade Deadline countdown — backend enforcement + frontend ribbon +
      Ops Console pill.
  (d) Ops Console — new `GET /api/leagues/{league_id}/ops-summary`
      endpoint + commissioner page + route registration.
"""
from __future__ import annotations

from pathlib import Path

REPO = Path("/app")
WAIVERS = REPO / "backend/routes/waivers.py"
TRADES = REPO / "backend/routes/trades.py"
OPS_CONSOLE_PY = REPO / "backend/routes/ops_console.py"
OPS_CONSOLE_TSX = REPO / "frontend/src/lovable/pages/commissioner/OpsConsole.tsx"
SERVER = REPO / "backend/server.py"
APP_JS = REPO / "frontend/src/App.js"


# ── (a) Salary-cap enforcement on waiver claim ─────────────────────
def test_waiver_claim_extracts_synth_cap_hit_helper():
    src = WAIVERS.read_text()
    assert "def _synth_player_cap_hit(player: dict) -> int:" in src
    # Same coefficients as the precheck path so the two never drift.
    assert "9_500_000 if p_fp >= 300" in src
    assert "min(13_500_000, max(775_000, addition))" in src


def test_waiver_claim_uses_claim_would_breach_cap_helper():
    src = WAIVERS.read_text()
    assert "def _claim_would_breach_cap(" in src
    # Drop offsets cap relief.
    assert "relief = int(dp_contract.get(\"salary\") or _synth_player_cap_hit(drop_player))" in src
    # The actual claim endpoint enforces the helper and rejects with 422.
    assert "breach, projected, cap_total = _claim_would_breach_cap(league, team, player, drop_doc)" in src
    assert "status_code=422" in src
    assert '"code": "cap_breach"' in src


def test_waiver_claim_412_payload_structure():
    """The structured cap_breach payload must include projected,
    cap_total + suggested_action so the modal can render its red banner."""
    src = WAIVERS.read_text()
    for k in ('"projected": projected', '"cap_total": cap_total', '"suggested_action": "drop"'):
        assert k in src


# ── (b) Trade veto tracking — invariants ───────────────────────────
def test_trade_vote_endpoint_exists_with_veto_threshold():
    src = TRADES.read_text()
    assert "@router.post(\"/trades/{trade_id}/vote\")" in src
    assert "def _veto_threshold(league: dict) -> dict:" in src
    assert "trade_veto_threshold_pct" in src
    # Strict-majority auto-veto path.
    assert 'counts["veto"] >= threshold_info["teams_required"]' in src


# ── (c) Trade Deadline countdown — backend gate + ribbon ──────────
def test_trade_deadline_enforced_at_proposal():
    src = TRADES.read_text()
    assert "def _enforce_trade_deadline(league: dict) -> None:" in src
    assert "_enforce_trade_deadline(league)" in src


def test_trade_deadline_ribbon_mounted_in_layout():
    layouts = [
        REPO / "frontend/src/lovable/components/layout/AppLayout.tsx",
        REPO / "frontend/src/components/layout/AppLayout.jsx",
    ]
    mounted = sum(1 for p in layouts if p.exists() and "<TradeDeadlineRibbon" in p.read_text())
    assert mounted >= 1, "TradeDeadlineRibbon must be mounted in at least one AppLayout"


# ── (d) Ops Console ────────────────────────────────────────────────
def test_ops_console_backend_route_exists():
    assert OPS_CONSOLE_PY.exists(), "routes/ops_console.py must be created"
    src = OPS_CONSOLE_PY.read_text()
    assert "@router.get(\"/leagues/{league_id}/ops-summary\")" in src
    # Commissioner-only guard
    assert "Commissioner access required" in src
    # 4 counter keys
    for key in (
        "pending_waivers", "pending_trades", "vetoed_trades", "teams_with_violations",
    ):
        assert f'"{key}"' in src
    # Trade-deadline payload structure
    assert '"trade_deadline"' in src
    assert '"ms_remaining"' in src
    # Recent vetoes + recent waivers payload
    assert "recent_vetoes" in src
    assert "recent_waivers" in src


def test_ops_console_router_registered_in_server():
    src = SERVER.read_text()
    assert "ops_console as ops_console_routes" in src
    assert "ops_console_routes.setup(_router_deps)" in src
    assert "api_router.include_router(ops_console_routes.router)" in src


def test_ops_console_frontend_page_exists():
    assert OPS_CONSOLE_TSX.exists()
    src = OPS_CONSOLE_TSX.read_text()
    # Page-level test ids
    for tid in (
        "ops-console",
        "ops-trade-deadline-pill",
        "ops-force-process-btn",
        "ops-recent-vetoes-card",
        "ops-pending-waivers-card",
        "ops-refresh-btn",
    ):
        assert f'data-testid="{tid}"' in src, f"Missing test id: {tid}"
    # Counter cards pass the testid via variable interpolation; assert
    # each unique testid string flows through as a `testid="…"` prop.
    for tid in (
        "ops-counter-pending-waivers",
        "ops-counter-pending-trades",
        "ops-counter-vetoed-trades",
        "ops-counter-teams-with-violations",
    ):
        assert f'testid="{tid}"' in src, f"Missing counter testid: {tid}"
    # API call uses the centralised api helper
    assert '/leagues/${leagueId}/ops-summary' in src
    # Confirm-then-fire safety net on the destructive op
    assert "window.confirm(" in src
    # Tone-down: deadline pill shows "passed" / countdown
    assert "Trade Deadline passed" in src
    assert "Trade Deadline in " in src


def test_ops_console_route_registered_in_app_js():
    src = APP_JS.read_text()
    assert "OpsConsolePage" in src
    assert '/commissioner/ops-console' in src
