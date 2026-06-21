"""
Iter 190 — Ops Console v3 polish.

  (1) 30-second polling refresh tied to `document.visibilityState`.
  (2) Optional event-type filter chip strip on the audit log card.
  (3) Per-entry user attribution lookup (batched).
  (4) Audit log CSV export via `?format=csv`.
"""
from __future__ import annotations

from pathlib import Path

REPO = Path("/app")
OPS_CONSOLE_PY = REPO / "backend/routes/ops_console.py"
OPS_CONSOLE_TSX = REPO / "frontend/src/lovable/pages/commissioner/OpsConsole.tsx"


# ── (1) 30s polling tied to visibilityState ──────────────────────
def test_ops_console_polling_skips_when_tab_hidden():
    src = OPS_CONSOLE_TSX.read_text()
    assert "setInterval(tick, 30_000)" in src
    # Hidden tab — bail before firing the request.
    assert 'document.visibilityState !== "visible"' in src
    # Listen to visibilitychange to fire an immediate refresh on
    # re-focus so the user doesn't see stale counters.
    assert 'document.addEventListener("visibilitychange", onVisible)' in src
    # Cleanup on unmount
    assert "clearInterval(id);" in src
    assert 'document.removeEventListener("visibilitychange", onVisible)' in src


# ── (2) Event-type filter chip strip ─────────────────────────────
def test_audit_log_renders_filter_chip_strip():
    src = OPS_CONSOLE_TSX.read_text()
    assert 'data-testid="ops-audit-filter-chips"' in src
    assert 'data-testid="ops-audit-filter-chip-all"' in src
    # Per-type chip uses a dynamic testid for QA selectors
    assert 'data-testid={`ops-audit-filter-chip-${t}`}' in src
    # Filter state + toggle helper
    assert "const [auditFilter, setAuditFilter] = useState(new Set());" in src
    assert "const toggleAuditFilter" in src
    # Filter applied client-side over the in-memory entries
    assert "const filteredAuditEntries" in src
    assert "auditFilter.has(e?.event_type)" in src


def test_audit_log_empty_state_distinguishes_filter_vs_no_data():
    src = OPS_CONSOLE_TSX.read_text()
    assert "No activity recorded yet." in src
    assert "No entries match the selected filters." in src


# ── (3) Per-entry user attribution lookup ────────────────────────
def test_audit_endpoint_batch_fetches_user_attribution():
    src = OPS_CONSOLE_PY.read_text()
    # Single batched query — never a per-row round-trip.
    assert "user_ids = list({d.get(\"user_id\") for d in docs if d.get(\"user_id\")})" in src
    assert "await db.users.find(users_q).to_list(" in src
    # Tolerant of both ObjectId-shaped + raw-string ids
    assert "object_ids.append(ObjectId(uid))" in src
    # Decoration onto each returned entry
    assert '"user_name": attr["user_name"]' in src
    assert '"user_email": attr["user_email"]' in src


def test_audit_log_ui_renders_attribution():
    src = OPS_CONSOLE_TSX.read_text()
    # "· by …" affordances + system fallback
    assert "· by {entry.user_name}" in src
    assert "· system" in src


# ── (4) CSV export ───────────────────────────────────────────────
def test_audit_endpoint_supports_csv_format():
    src = OPS_CONSOLE_PY.read_text()
    # Query-param plumbing
    assert "format: Optional[str] = None" in src
    assert 'is_csv = (format or "").lower() == "csv"' in src
    # Larger cap for archival exports.
    assert "cap = 1000 if is_csv else 100" in src
    # Streaming response w/ attachment headers
    assert "StreamingResponse(" in src
    assert "media_type=\"text/csv\"" in src
    assert 'Content-Disposition' in src
    # CSV header row
    assert "created_at" in src and "user_name" in src and "metadata_json" in src


def test_audit_log_ui_offers_export_csv_button():
    src = OPS_CONSOLE_TSX.read_text()
    assert 'data-testid="ops-audit-export-csv"' in src
    assert "const exportCsv = async () => {" in src
    # Uses responseType:"blob" for the download path
    assert 'responseType: "blob"' in src
    # Filename includes the league id and today's date so multiple
    # exports don't overwrite each other.
    assert 'audit-log-${leagueId}-' in src
    # Button text reflects in-flight state
    assert "Exporting…" in src
