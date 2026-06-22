"""
Iter 199 — Health Score gating + Mark Winner auto-create synthetic matchups.

Two bug fixes from user feedback:

1. **Health Score defaulted to 100%** for freshly-created leagues because
   each section's "complete" flag inferred from default field values (e.g.,
   `playoff_teams=6`, `salary_cap_enabled=false`). Fix: gate completion
   behind an explicit `setup_progress: {<key>: true}` map stamped by the
   Setup Wizard's per-step save handlers. Legacy leagues already marked
   `setup_wizard_complete=true` retain data-inference fallback so they
   don't regress from 100% to 0%.

2. **Mark Winner skipped synthetic SF matchups**. The bracket synthesizer
   pads non-final rounds with in-memory TBD entries when DB is sparse.
   When a QF winner needed to advance into a synthetic SF slot, the
   `mark-winner` endpoint silently dropped the propagation. Fix: when
   the target next-round matchup doesn't exist in DB, create it
   on-the-fly with `auto_created=true` so subsequent Mark Winner clicks
   have a real `matchup_id` to act on.
"""
from __future__ import annotations

import os
import requests

API_URL = os.environ["REACT_APP_BACKEND_URL"]
LEAGUE_ID = "69e46af167999bfb85c39628"
EMAIL = "chriszarek@gmail.com"
PASSWORD = "Chris2026!"


def _login() -> str:
    r = requests.post(f"{API_URL}/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
    r.raise_for_status()
    return r.json()["access_token"]


# ── Bug 1 — Health Score gating ───────────────────────────────


def test_legacy_league_keeps_100_score():
    """Ice Kings has `setup_wizard_complete=true` from a prior session.
    Health score must still report 100 (data-inference fallback)."""
    r = requests.get(f"{API_URL}/api/leagues/{LEAGUE_ID}/health-score")
    r.raise_for_status()
    d = r.json()
    assert d["score"] == 100, f"Legacy league regressed: {d['score']}"


def test_new_league_starts_at_zero_score():
    """A freshly-created league must report score=0 before the wizard
    starts stamping `setup_progress`."""
    token = _login()
    headers = {"Authorization": f"Bearer {token}"}
    new = requests.post(
        f"{API_URL}/api/leagues",
        headers=headers,
        json={
            "name": "Iter199 health gate test",
            "max_teams": 8,
            "format": "dynasty",
            "scoring_format": "head_to_head",
        },
    )
    assert new.status_code == 200, new.text
    league_id = new.json()["id"]
    try:
        h = requests.get(f"{API_URL}/api/leagues/{league_id}/health-score").json()
        assert h["score"] == 0, f"Fresh league score should be 0, got {h['score']}"
        # All sections incomplete
        for s in h["sections"]:
            assert s["complete"] is False, f"Section {s['key']} unexpectedly complete on fresh league"
    finally:
        requests.delete(f"{API_URL}/api/leagues/{league_id}", headers=headers)


def test_setup_progress_endpoint_increments_score():
    token = _login()
    headers = {"Authorization": f"Bearer {token}"}
    new = requests.post(
        f"{API_URL}/api/leagues",
        headers=headers,
        json={
            "name": "Iter199 progress increment test",
            "max_teams": 8,
            "format": "dynasty",
            "scoring_format": "head_to_head",
        },
    )
    league_id = new.json()["id"]
    try:
        # Stamp basics+cap (16+16 = 32)
        r = requests.post(
            f"{API_URL}/api/leagues/{league_id}/setup-progress",
            headers=headers,
            json={"sections": ["basics", "cap"]},
        )
        assert r.status_code == 200, r.text
        h = requests.get(f"{API_URL}/api/leagues/{league_id}/health-score").json()
        assert h["score"] == 32, f"basics+cap should give 32, got {h['score']}"

        # Stamp all remaining
        r = requests.post(
            f"{API_URL}/api/leagues/{league_id}/setup-progress",
            headers=headers,
            json={"sections": ["divisions", "schedule", "playoffs", "draft"]},
        )
        assert r.status_code == 200
        h = requests.get(f"{API_URL}/api/leagues/{league_id}/health-score").json()
        assert h["score"] == 100, f"all sections should give 100, got {h['score']}"
    finally:
        requests.delete(f"{API_URL}/api/leagues/{league_id}", headers=headers)


def test_setup_progress_requires_commissioner():
    """Non-commish (no token) gets 401/403."""
    new = requests.post(
        f"{API_URL}/api/leagues/{LEAGUE_ID}/setup-progress",
        json={"sections": ["basics"]},
    )
    assert new.status_code in (401, 403), new.status_code


def test_setup_progress_rejects_unknown_sections():
    token = _login()
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.post(
        f"{API_URL}/api/leagues/{LEAGUE_ID}/setup-progress",
        headers=headers,
        json={"sections": ["bogus", "alsobogus"]},
    )
    assert r.status_code == 400, r.text


# ── Bug 2 — Mark Winner auto-creates synthetic matchups ──────


def _bracket():
    r = requests.get(f"{API_URL}/api/leagues/{LEAGUE_ID}/playoff-bracket")
    r.raise_for_status()
    return r.json()


def test_mark_winner_auto_creates_missing_next_round_matchup():
    """QF#2 + QF#3 feed into SF#1, which is purely synthetic in the
    initial DB state. After marking QF#2 winner, a real DB row for SF#1
    must exist with the winner in its home slot."""
    token = _login()
    headers = {"Authorization": f"Bearer {token}"}
    b = _bracket()
    qf2 = b["rounds"][0]["matchups"][2]
    winner_id = qf2["high_seed"]["team_id"]
    # Mark winner on QF#2
    r = requests.post(
        f"{API_URL}/api/leagues/{LEAGUE_ID}/playoffs/mark-winner",
        headers=headers,
        json={"matchup_id": qf2["matchup_id"], "winner_team_id": winner_id},
    )
    assert r.status_code == 200, r.text

    # Bracket should now show SF#1 with a real matchup_id (no longer
    # synthetic) and the winner advanced into its home slot.
    b2 = _bracket()
    sf1 = b2["rounds"][1]["matchups"][1]
    assert sf1.get("matchup_id"), "SF#1 should have a real matchup_id after auto-create"
    assert sf1.get("home_team_id") == winner_id
    assert sf1.get("is_synthetic") is False


def test_mark_winner_qf3_fills_away_slot_of_auto_created_sf():
    """After QF#2 created SF#1 with the winner in home, marking QF#3
    winner should fill the away slot — same auto_created row."""
    token = _login()
    headers = {"Authorization": f"Bearer {token}"}
    b = _bracket()
    qf3 = b["rounds"][0]["matchups"][3]
    winner_id = qf3["high_seed"]["team_id"]
    r = requests.post(
        f"{API_URL}/api/leagues/{LEAGUE_ID}/playoffs/mark-winner",
        headers=headers,
        json={"matchup_id": qf3["matchup_id"], "winner_team_id": winner_id},
    )
    assert r.status_code == 200

    b2 = _bracket()
    sf1 = b2["rounds"][1]["matchups"][1]
    assert sf1.get("away_team_id") == winner_id
    # Both teams now present → Mark Winner button should show on the
    # frontend for this matchup (frontend test verifies that).
    assert sf1.get("home_team_id") and sf1.get("away_team_id")
