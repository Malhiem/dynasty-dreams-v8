"""
Iter 189 — User-selected follow-ups:
  (2) Frontend cap_breach banner in the Waivers claim modal.
  (3b) Ops Console per-team violation drilldown — backend endpoint +
       Sheet slide-over hooked up to the Teams w/ Violations counter.
  (3c) Ops Console audit-log card pulling from `activity_feed`.
"""
from __future__ import annotations

from pathlib import Path

REPO = Path("/app")
WAIVERS_TSX = REPO / "frontend/src/lovable/pages/Waivers.tsx"
OPS_CONSOLE_PY = REPO / "backend/routes/ops_console.py"
OPS_CONSOLE_TSX = REPO / "frontend/src/lovable/pages/commissioner/OpsConsole.tsx"


# ── (2) Cap breach banner in Waivers claim modal ─────────────────
def test_waivers_modal_catches_422_cap_breach():
    src = WAIVERS_TSX.read_text()
    # Structured 422 parsing
    assert "e?.response?.status === 422" in src
    assert 'detail.code === "cap_breach"' in src
    # Structured payload destructure (projected + cap_total + message)
    for k in ("detail.projected", "detail.cap_total", "detail.message"):
        assert k in src
    # New state owns the banner contents
    assert "const [capBreachError, setCapBreachError]" in src
    # Reset on modal open + new claim attempt
    assert "setCapBreachError(null);" in src


def test_waivers_modal_renders_cap_breach_banner():
    src = WAIVERS_TSX.read_text()
    assert 'data-testid="claim-cap-breach-banner"' in src
    # Banner copy mirrors the backend message format
    assert "exceeding the $" in src
    assert "Pick a player to drop ↓" in src
    # Banner uses the destructive red palette
    assert "border-destructive/40 bg-destructive/10" in src


def test_waivers_modal_auto_scrolls_to_drop_picker_on_breach():
    src = WAIVERS_TSX.read_text()
    # The drop-picker div now exposes a ref for the scroll target
    assert "ref={dropPickerRef}" in src
    # The 422 handler triggers a smooth scroll into view
    assert 'scrollIntoView({ behavior: "smooth", block: "center" })' in src


# ── (3b) Per-team violation drilldown ────────────────────────────
def test_ops_violations_endpoint_exists():
    src = OPS_CONSOLE_PY.read_text()
    assert '@router.get("/leagues/{league_id}/ops-violations")' in src
    # Returns per-team payload with cap_over codes
    assert '"code": "cap_over"' in src
    # Commissioner gate uses the shared helper
    assert "def _user_is_commish(league: dict, user: dict) -> bool:" in src
    assert "_user_is_commish(league, user)" in src
    # Lineup-flag passthrough so other parts of the app can raise
    # arbitrary violations without changing the API surface.
    assert 'spot.get("flagged")' in src


def test_ops_console_makes_violations_counter_clickable():
    src = OPS_CONSOLE_TSX.read_text()
    assert "const loadViolations = async () => {" in src
    # Clickable counter card wiring
    assert "onClick={loadViolations}" in src
    assert "clickable" in src
    # Sheet slide-over and its testid
    assert 'data-testid="ops-violations-sheet"' in src
    # Empty + loading states render their own testids for QA hooks
    assert 'data-testid="ops-violations-empty"' in src
    assert 'data-testid="ops-violations-loading"' in src


# ── (3c) Audit-log viewer ────────────────────────────────────────
def test_ops_audit_log_endpoint_exists():
    src = OPS_CONSOLE_PY.read_text()
    assert '@router.get("/leagues/{league_id}/ops-audit-log")' in src
    # Optional event_types filter
    assert "event_types: Optional[str] = None" in src
    # Pulls from activity_feed sorted desc with a limit
    assert "db.activity_feed.find(q).sort(\"created_at\", -1)" in src
    # Caps the limit so abusive callers can't drain the collection.
    assert "min(int(limit or 50), 100)" in src


def test_ops_console_renders_audit_log_card():
    src = OPS_CONSOLE_TSX.read_text()
    assert 'data-testid="ops-audit-log-card"' in src
    assert "loadAuditLog" in src
    # Empty-state hook + per-entry testid for QA selectors
    assert 'data-testid="ops-audit-log-empty"' in src
    assert "ops-audit-entry-${entry.event_type}" in src


def test_load_refreshes_audit_log_alongside_summary():
    """Hitting the page-level Refresh button must also pull a fresh
    audit log, otherwise commissioners would see a stale tail."""
    src = OPS_CONSOLE_TSX.read_text()
    # `loadAuditLog()` invoked at the end of the main `load`
    assert "loadAuditLog();" in src
