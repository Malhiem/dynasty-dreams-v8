"""
Iter 193 — Bulk Owner Invites UI + Foundation for in-draft pick trade flow.
"""
from __future__ import annotations

from pathlib import Path

REPO = Path("/app")
INVITES_PY = REPO / "backend/routes/league_invites.py"
TRADES_PY = REPO / "backend/routes/trades.py"
INVITES_TSX = REPO / "frontend/src/lovable/pages/commissioner/OwnerInvites.tsx"
APP_JS = REPO / "frontend/src/App.js"


# ── Bulk Owner Invites — backend ───────────────────────────────
def test_pending_team_invites_endpoint_exists():
    src = INVITES_PY.read_text()
    assert '@router.get("/leagues/{league_id}/pending-team-invites")' in src
    # Commissioner gate
    assert 'Commissioner access required' in src
    # Per-team status with merged invite lookup
    assert 'invites_by_email' in src
    # Statuses: accepted / sent / pending / no_email
    for status in ('"accepted"', '"sent"', '"pending"', '"no_email"'):
        assert status in src


def test_bulk_invite_endpoint_exists():
    src = INVITES_PY.read_text()
    assert '@router.post("/leagues/{league_id}/pending-team-invites/bulk")' in src
    # Validates email + team membership
    assert '"invalid_email"' in src
    assert '"team_not_found"' in src
    # Stashes invite_email on the team doc + upserts league_invites
    assert 'invite_email": row.email.lower()' in src
    assert "db.league_invites.update_one(" in src
    # Reuses existing SendGrid helper
    assert "send_sendgrid_email(row.email, subject, html_template)" in src


# ── Bulk Owner Invites — frontend ──────────────────────────────
def test_owner_invites_page_exists():
    assert INVITES_TSX.exists()
    src = INVITES_TSX.read_text()
    for tid in (
        "owner-invites",
        "owner-invites-csv-input",
        "owner-invites-send-all",
        "owner-invites-refresh",
        "owner-invites-table",
        "owner-invites-stat-total",
        "owner-invites-stat-accepted",
        "owner-invites-stat-sent",
        "owner-invites-stat-no-email",
    ):
        assert f'data-testid="{tid}"' in src, f"missing test id: {tid}"
    # Per-row dynamic ids for QA selectors
    assert 'data-testid={`owner-invites-row-${t.team_id}`}' in src
    assert 'data-testid={`owner-invites-email-${t.team_id}`}' in src
    # CSV parser supports team_name OR abbreviation + ignores header
    assert "teamByAbbr" in src and "teamByName" in src
    assert 'lines[0] && !lines[0].includes("@")' in src
    # Confirm-then-fire safety
    assert "window.confirm(" in src


def test_owner_invites_route_registered():
    src = APP_JS.read_text()
    assert "OwnerInvitesPage" in src
    assert "/commissioner/owner-invites" in src


# ── Foundation: in-draft pick trade endpoint ───────────────────
def test_propose_pick_trade_endpoint_exists():
    src = TRADES_PY.read_text()
    assert '@router.post("/drafts/{league_id}/propose-pick-trade")' in src
    # Status + computed review window
    assert 'status="pending_draft_review"' in src or '"status": "pending_draft_review"' in src
    assert 'review_expires_at' in src
    # Pulls post-review action from league config — wired to the iter191 dropdown
    assert 'league.get("draft_trade_post_delay_action")' in src
    # Validates pick asset present
    assert 'At least one pick asset required' in src
    # Broadcasts a draft chat system message
    assert '"kind": "pick_trade_proposed"' in src
    # Stamps the trade as an in-draft pick trade
    assert '"is_in_draft_pick_trade": True' in src
