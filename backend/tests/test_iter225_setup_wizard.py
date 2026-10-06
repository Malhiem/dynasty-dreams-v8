"""
Iter 225 — Setup-Wizard backend fixes.

Validates:
  • max_teams ≥ 2 (lowered from ≥4) so a 2-team test league validates
  • Schedule generates with PLACEHOLDER teams when len(teams) < max_teams
  • validate-setup no longer hard-blocks on teams_count < 2 when max_teams
    is set high enough
  • /matchups/preview returns `warnings` for impossible season windows
    and out-of-NHL-window calendars
  • /matchups/generate-schedule returns 400 with structured `errors` when
    the season window can't fit the requested weeks
  • Premium-trial timer is STICKY once started (the toggle-off/toggle-on
    regression that reset the trial to fresh 14 days no longer fires)
"""
from __future__ import annotations

import os
import uuid
import requests
from bson import ObjectId
from pymongo import MongoClient

API_URL = os.environ["REACT_APP_BACKEND_URL"]
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@e2e.dynastydreams.com")
ADMIN_PASS = os.environ.get("ADMIN_PASSWORD", "e2e-admin-password")
_db = MongoClient(os.environ.get("MONGO_URL", os.environ["MONGO_URL"]))[
    os.environ.get("DB_NAME", os.environ["DB_NAME"])
]


def _login(email, password):
    r = requests.post(f"{API_URL}/api/auth/login", json={"email": email, "password": password})
    r.raise_for_status()
    return r.json()["access_token"]


def _register_user(prefix="iter225"):
    s = uuid.uuid4().hex[:8]
    e = f"{prefix}_{s}@example.com"
    requests.post(f"{API_URL}/api/auth/register", json={
        "email": e, "password": "Pass123!",
        "username": f"{prefix}_{s}", "name": "Iter225",
    }).raise_for_status()
    return _login(e, "Pass123!")


def _create_league(tok, **extra):
    H = {"Authorization": f"Bearer {tok}"}
    body = {
        "name": "iter225 " + uuid.uuid4().hex[:6],
        "format": "dynasty", "scoring_format": "head_to_head",
        "max_teams": 12, "draft_type": "snake", "roster_spots": 20,
    }
    body.update(extra)
    r = requests.post(f"{API_URL}/api/leagues", headers=H, json=body)
    r.raise_for_status()
    return r.json()


# ─── max_teams + minors caps ────────────────────────────────────────────

def test_max_teams_can_be_set_to_two():
    """The wizard requires `max_teams` to be editable. ge=4 lower bound
    blocked 2- or 3-team leagues — should now accept >= 2."""
    tok = _register_user()
    league = _create_league(tok)
    r = requests.put(
        f"{API_URL}/api/leagues/{league['id']}",
        headers={"Authorization": f"Bearer {tok}"},
        json={"max_teams": 2},
    )
    assert r.status_code == 200, r.text
    assert r.json()["max_teams"] == 2


def test_minors_spots_accepts_up_to_100():
    tok = _register_user()
    league = _create_league(tok)
    r = requests.put(
        f"{API_URL}/api/leagues/{league['id']}",
        headers={"Authorization": f"Bearer {tok}"},
        json={"minors_spots": 100},
    )
    assert r.status_code == 200, r.text
    assert r.json()["minors_spots"] == 100


# ─── validate-setup no longer hard-blocks ──────────────────────────────

def test_validate_setup_passes_with_only_commish_team():
    """The wizard couldn't finish without a 2nd manager joining. With the
    iter-225 placeholder padding, validate-setup passes if max_teams ≥ 2."""
    tok = _register_user()
    league = _create_league(tok)  # max_teams=12, only the commish auto-team exists
    H = {"Authorization": f"Bearer {tok}"}
    r = requests.post(f"{API_URL}/api/leagues/{league['id']}/validate-setup", headers=H)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True, f"expected ok=True but issues: {body['issues']}"
    assert body["open_slot_count"] >= 1


# ─── Schedule generation with placeholders ─────────────────────────────

def test_generate_schedule_pads_with_open_slots():
    tok = _register_user()
    league = _create_league(tok, max_teams=4)
    H = {"Authorization": f"Bearer {tok}"}
    r = requests.post(
        f"{API_URL}/api/matchups/generate-schedule",
        headers=H,
        json={"league_id": league["id"], "num_weeks": 6},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    # Commish gets 1 auto-team; max_teams=4 → 3 placeholders
    assert body["placeholder_team_slots"] >= 1, body
    assert body["weeks"] == 6
    # Verify placeholder team_ids are persisted as "open_slot_*"
    placeholder = _db.matchups.find_one({
        "league_id": league["id"],
        "$or": [
            {"home_team_id": {"$regex": "^open_slot_"}},
            {"away_team_id": {"$regex": "^open_slot_"}},
        ],
    })
    assert placeholder is not None, "no placeholder matchup row written"


# ─── Calendar / NHL sanity checks ──────────────────────────────────────

def test_preview_warns_for_season_outside_nhl_window():
    r = requests.post(f"{API_URL}/api/matchups/preview", json={
        "max_teams": 10, "matchups_per_week": 1, "num_weeks": 4,
        "season_start": "2025-06-01", "season_end": "2025-08-30",
        "matchup_length_days": 7,
    })
    assert r.status_code == 200, r.text
    warnings = r.json().get("warnings") or []
    assert any("NHL" in w for w in warnings), warnings


def test_generate_rejects_when_season_too_short():
    tok = _register_user()
    league = _create_league(tok, max_teams=4)
    H = {"Authorization": f"Bearer {tok}"}
    # Set a 2-week-wide season but ask for 10 weeks
    requests.put(
        f"{API_URL}/api/leagues/{league['id']}",
        headers=H,
        json={
            "season_start_date": "2025-10-10",
            "season_end_date": "2025-10-24",
            "matchup_length_days": 7,
            "regular_season_weeks": 10,
        },
    ).raise_for_status()
    r = requests.post(
        f"{API_URL}/api/matchups/generate-schedule",
        headers=H,
        json={"league_id": league["id"], "num_weeks": 10},
    )
    assert r.status_code == 400, r.text
    detail = r.json().get("detail")
    assert isinstance(detail, dict)
    assert detail.get("errors")


# ─── Premium trial stickiness ──────────────────────────────────────────

def test_premium_trial_is_sticky_across_toggles():
    """Regression — the wizard saving with cap disabled used to wipe the
    trial timer. Re-enabling later would start a brand-new 14-day window,
    so a later wizard step appeared to 'rewind' to ~13 days left."""
    tok = _register_user()
    league = _create_league(tok)
    H = {"Authorization": f"Bearer {tok}"}

    # Start trial
    requests.put(
        f"{API_URL}/api/leagues/{league['id']}/admin/cap-settings",
        headers=H,
        json={"salary_cap_enabled": True, "salary_cap": 80_000_000},
    ).raise_for_status()
    started_at_1 = requests.get(
        f"{API_URL}/api/leagues/{league['id']}/premium-status", headers=H,
    ).json()["trial_started_at"]
    assert started_at_1

    # Toggle off
    requests.put(
        f"{API_URL}/api/leagues/{league['id']}/admin/cap-settings",
        headers=H, json={"salary_cap_enabled": False},
    ).raise_for_status()

    # Toggle back on
    requests.put(
        f"{API_URL}/api/leagues/{league['id']}/admin/cap-settings",
        headers=H,
        json={"salary_cap_enabled": True, "salary_cap": 80_000_000},
    ).raise_for_status()
    started_at_2 = requests.get(
        f"{API_URL}/api/leagues/{league['id']}/premium-status", headers=H,
    ).json()["trial_started_at"]
    assert started_at_2 == started_at_1, (
        "Trial timer was reset on re-enable — premium trial must be sticky"
    )
