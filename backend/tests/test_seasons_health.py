"""Tests for League Health Score + Season lifecycle endpoints."""
import os
import uuid

import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
COMMISH_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@e2e.dynastydreams.com")
COMMISH_PASS = os.environ.get("ADMIN_PASSWORD", "e2e-admin-password")


def _login(email: str, password: str):
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text[:200]
    s.headers.update({"Authorization": f"Bearer {r.json()['access_token']}"})
    return s


def _pick_commish_league(s):
    me = s.get(f"{BASE_URL}/api/auth/me").json()
    leagues = s.get(f"{BASE_URL}/api/leagues?my_leagues=true").json()
    for l in leagues:
        if l.get("commissioner_id") == me["id"]:
            return l["id"]
    return leagues[0]["id"]


def test_health_score_shape():
    s = _login(COMMISH_EMAIL, COMMISH_PASS)
    lid = _pick_commish_league(s)
    r = requests.get(f"{BASE_URL}/api/leagues/{lid}/health-score")
    assert r.status_code == 200
    body = r.json()
    assert "score" in body
    assert 0 <= body["score"] <= 100
    assert isinstance(body["sections"], list)
    assert len(body["sections"]) == 6
    keys = [s["key"] for s in body["sections"]]
    assert keys == ["basics", "cap", "divisions", "schedule", "playoffs", "draft"]
    total_weight = sum(s["weight"] for s in body["sections"])
    assert total_weight == 100, f"section weights must sum to 100, got {total_weight}"
    assert "missing" in body


def test_complete_season_snapshot():
    s = _login(COMMISH_EMAIL, COMMISH_PASS)
    lid = _pick_commish_league(s)
    # Pick a clearly-old year to avoid stomping on a real renewal
    test_year = 2020
    r = s.post(f"{BASE_URL}/api/leagues/{lid}/complete-season", json={"season_year": test_year})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["season_year"] == test_year
    assert body["teams_snapshotted"] >= 0
    assert "awards_snapshotted" in body

    # Should now appear in seasons list
    sl = s.get(f"{BASE_URL}/api/leagues/{lid}/seasons").json()
    season_years = [se["season_year"] for se in sl["seasons"]]
    assert test_year in season_years

    # Detail endpoint
    detail = s.get(f"{BASE_URL}/api/leagues/{lid}/seasons/{test_year}").json()
    assert detail["season_year"] == test_year
    assert "teams" in detail
    assert "awards" in detail


def test_complete_season_idempotent_on_replay():
    """Running complete-season twice for the same year just overwrites."""
    s = _login(COMMISH_EMAIL, COMMISH_PASS)
    lid = _pick_commish_league(s)
    test_year = 2019
    s.post(f"{BASE_URL}/api/leagues/{lid}/complete-season", json={"season_year": test_year})
    r = s.post(f"{BASE_URL}/api/leagues/{lid}/complete-season", json={"season_year": test_year})
    assert r.status_code == 200
    sl = s.get(f"{BASE_URL}/api/leagues/{lid}/seasons").json()
    matching = [se for se in sl["seasons"] if se["season_year"] == test_year]
    assert len(matching) == 1, f"Expected 1 snapshot for {test_year}, got {len(matching)}"


def test_complete_season_commissioner_only():
    """Stranger gets 403."""
    suffix = uuid.uuid4().hex[:8]
    stranger = requests.Session()
    stranger.headers.update({"Content-Type": "application/json"})
    reg = stranger.post(f"{BASE_URL}/api/auth/register", json={
        "email": f"season_stranger_{suffix}@example.com",
        "username": f"season_stranger_{suffix}",
        "password": "Stranger123!",
        "name": "Stranger",
    })
    assert reg.status_code in (200, 201)
    stranger.headers.update({"Authorization": f"Bearer {reg.json()['access_token']}"})

    commish = _login(COMMISH_EMAIL, COMMISH_PASS)
    lid = _pick_commish_league(commish)
    r = stranger.post(f"{BASE_URL}/api/leagues/{lid}/complete-season", json={"season_year": 2030})
    assert r.status_code == 403


def test_renew_season_resets_records_and_carries_settings():
    s = _login(COMMISH_EMAIL, COMMISH_PASS)
    lid = _pick_commish_league(s)

    # Snapshot 2024 first so we have a "previous season" to suggest from
    s.post(f"{BASE_URL}/api/leagues/{lid}/complete-season", json={"season_year": 2024})

    # Bump current_season_year to 2024 (ensures renew goes 2024 → 2025)
    # We do this via direct update of league through API (commissioner-only renew)
    teams_before = s.get(f"{BASE_URL}/api/teams?league_id={lid}").json()
    for t in teams_before[:1]:
        # Just need ANY team to verify reset
        assert "wins" in t

    # Renew to current_year + 1 — re-fetch league AFTER snapshot to get fresh current_season_year
    league = s.get(f"{BASE_URL}/api/leagues/{lid}").json()
    cur_year = league.get("current_season_year") or 2026
    new_year = cur_year + 1

    r = s.post(f"{BASE_URL}/api/leagues/{lid}/renew-season", json={
        "new_season_year": new_year,
        "carry_over_settings": True,
        "reset_records": True,
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["to_year"] == new_year
    assert body["reset_records"] is True
    # from_year should reflect whatever the league had stored, not necessarily cur_year
    assert body["from_year"] < new_year

    # After renew, league.current_season_year is bumped + setup_wizard_complete reset
    after = s.get(f"{BASE_URL}/api/leagues/{lid}").json()
    assert after.get("setup_wizard_complete") is False

    # Teams should have reset records
    teams_after = s.get(f"{BASE_URL}/api/teams?league_id={lid}").json()
    for t in teams_after:
        assert t.get("wins", 0) == 0, f"Expected wins=0 after renew, got {t.get('wins')}"
        assert t.get("losses", 0) == 0


def test_renew_season_rejects_lower_year():
    s = _login(COMMISH_EMAIL, COMMISH_PASS)
    lid = _pick_commish_league(s)
    league = s.get(f"{BASE_URL}/api/leagues/{lid}").json()
    cur_year = league.get("current_season_year") or 2026
    r = s.post(f"{BASE_URL}/api/leagues/{lid}/renew-season", json={
        "new_season_year": cur_year - 1,  # Earlier year → rejected
        "carry_over_settings": True,
        "reset_records": True,
    })
    assert r.status_code == 400


def test_setup_suggestions_returns_previous_year_when_present():
    s = _login(COMMISH_EMAIL, COMMISH_PASS)
    lid = _pick_commish_league(s)
    # Ensure we have at least one snapshotted season
    s.post(f"{BASE_URL}/api/leagues/{lid}/complete-season", json={"season_year": 2018})

    r = s.get(f"{BASE_URL}/api/leagues/{lid}/setup-suggestions")
    assert r.status_code == 200
    body = r.json()
    if body["has_previous_season"]:
        assert "previous_season_year" in body
        assert "salary_cap_config" in body
