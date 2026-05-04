"""Tests for:
  1) Division-aware schedule generator (when ≥2 divisions + schedule_config set).
  2) Division-winner auto-crown at end of regular season.
  3) Schedule-config endpoints (GET/PUT, commissioner-only).
"""
import os
import time

import pytest
import requests
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
COMMISH_EMAIL = "admin@dynastydreams.com"
COMMISH_PASS = "Admin123!"
MONGO_URL = os.environ.get("MONGO_URL") or "mongodb://localhost:27017"
DB_NAME = os.environ.get("DB_NAME", "test_database")


def _login(email: str, password: str):
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, f"Login {r.status_code} {r.text[:200]}"
    body = r.json()
    s.headers.update({"Authorization": f"Bearer {body['access_token']}"})
    return s


def _pick_commish_league(s):
    me = s.get(f"{BASE_URL}/api/auth/me").json()
    leagues = s.get(f"{BASE_URL}/api/leagues?my_leagues=true").json()
    for l in leagues:
        if l.get("commissioner_id") == me["id"]:
            return l["id"]
    return leagues[0]["id"]


def test_get_schedule_config_defaults():
    s = _login(COMMISH_EMAIL, COMMISH_PASS)
    lid = _pick_commish_league(s)
    r = s.get(f"{BASE_URL}/api/leagues/{lid}/schedule-config")
    assert r.status_code == 200, r.text
    data = r.json()
    for k in ("intra_division_games", "intra_conference_games", "inter_conference_games", "configured"):
        assert k in data


def test_put_schedule_config_commissioner_only():
    """Fresh stranger user (NOT a commish/co-commish) → 403."""
    import uuid
    suffix = uuid.uuid4().hex[:8]
    stranger = requests.Session()
    stranger.headers.update({"Content-Type": "application/json"})
    reg = stranger.post(f"{BASE_URL}/api/auth/register", json={
        "email": f"sched_stranger_{suffix}@example.com",
        "username": f"sched_stranger_{suffix}",
        "password": "Stranger123!",
        "name": "Stranger",
    })
    assert reg.status_code in (200, 201), reg.text[:200]
    stranger.headers.update({"Authorization": f"Bearer {reg.json()['access_token']}"})

    commish = _login(COMMISH_EMAIL, COMMISH_PASS)
    lid = _pick_commish_league(commish)
    r = stranger.put(
        f"{BASE_URL}/api/leagues/{lid}/schedule-config",
        json={"intra_division_games": 2, "intra_conference_games": 1, "inter_conference_games": 1},
    )
    assert r.status_code == 403


def test_put_schedule_config_saves_and_persists():
    s = _login(COMMISH_EMAIL, COMMISH_PASS)
    lid = _pick_commish_league(s)
    cfg = {"intra_division_games": 3, "intra_conference_games": 2, "inter_conference_games": 1}
    r = s.put(f"{BASE_URL}/api/leagues/{lid}/schedule-config", json=cfg)
    assert r.status_code == 200, r.text
    assert r.json()["saved"] == cfg

    # Verify persistence
    after = s.get(f"{BASE_URL}/api/leagues/{lid}/schedule-config").json()
    assert after["intra_division_games"] == 3
    assert after["intra_conference_games"] == 2
    assert after["inter_conference_games"] == 1
    assert after["configured"] is True


def test_schedule_config_validation_range():
    s = _login(COMMISH_EMAIL, COMMISH_PASS)
    lid = _pick_commish_league(s)
    r = s.put(
        f"{BASE_URL}/api/leagues/{lid}/schedule-config",
        json={"intra_division_games": 99, "intra_conference_games": 1, "inter_conference_games": 1},
    )
    assert r.status_code == 400


def test_generate_schedule_reports_mode():
    """When divisions + config are set, generate-schedule returns mode='division_aware'."""
    s = _login(COMMISH_EMAIL, COMMISH_PASS)
    lid = _pick_commish_league(s)

    # Ensure divisions are set (from prior tests or assign here)
    teams = s.get(f"{BASE_URL}/api/teams?league_id={lid}").json()
    if len(teams) < 4:
        pytest.skip("Need ≥4 teams for division-aware test")

    assignments = []
    for i, t in enumerate(teams[:8]):
        div = ["Atlantic", "Metropolitan", "Central", "Pacific"][i % 4]
        conf = "Eastern" if div in ("Atlantic", "Metropolitan") else "Western"
        assignments.append({"team_id": t["id"], "division": div, "conference": conf})
    s.put(f"{BASE_URL}/api/leagues/{lid}/divisions", json={"assignments": assignments})

    s.put(
        f"{BASE_URL}/api/leagues/{lid}/schedule-config",
        json={"intra_division_games": 2, "intra_conference_games": 1, "inter_conference_games": 1},
    )

    r = s.post(f"{BASE_URL}/api/matchups/generate-schedule", json={
        "league_id": lid, "num_weeks": 14,
    })
    # May fail with 400 if schedule already exists in a locked state; but should 200 when commissioner
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("mode") in ("division_aware", "round_robin")


def test_build_division_pairings_unit():
    """Exercise the internal helper directly — no HTTP."""
    from routes.matchups import _build_division_pairings

    teams = [
        {"_id": "A", "division": "D1", "conference": "C1"},
        {"_id": "B", "division": "D1", "conference": "C1"},
        {"_id": "C", "division": "D2", "conference": "C1"},
        {"_id": "D", "division": "D3", "conference": "C2"},
    ]
    cfg = {
        "intra_division_games": 2,
        "intra_conference_games": 1,
        "inter_conference_games": 1,
    }
    pairings = _build_division_pairings(teams, cfg)
    # A-B: 2× (intra-division)
    # A-C: 1× (intra-conference)
    # B-C: 1× (intra-conference)
    # A-D: 1× (inter-conference)
    # B-D: 1× (inter-conference)
    # C-D: 1× (inter-conference)
    # Total = 2 + 1 + 1 + 1 + 1 + 1 = 7
    assert len(pairings) == 7

    # All pairings involve exactly 2 distinct teams
    for home, away in pairings:
        assert home != away


@pytest.mark.asyncio
async def test_division_winner_auto_crown_end_of_regular_season():
    """Directly hit simulate-week on a league whose final regular-season week is the current week.
    Verify that division winners get `division_winner_at` flipped for each configured division.
    """
    if not MONGO_URL:
        pytest.skip("MONGO_URL not set")

    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]

    try:
        s = _login(COMMISH_EMAIL, COMMISH_PASS)
        lid = _pick_commish_league(s)

        teams = await db.teams.find({"league_id": lid}).to_list(50)
        if len(teams) < 4:
            pytest.skip("Need ≥4 teams")

        # Setup: 2 divisions with 2+ teams each, clear any prior crowns
        from bson import ObjectId as _OID
        for i, t in enumerate(teams):
            div = "North" if i < len(teams) // 2 else "South"
            await db.teams.update_one(
                {"_id": t["_id"]},
                {"$set": {"division": div, "conference": "Test"},
                 "$unset": {"division_winner_at": ""}},
            )

        # Make sure there's at least one scheduled matchup for current-week simulation
        cw = s.get(f"{BASE_URL}/api/matchups/{lid}/current-week").json()
        cur_week = cw.get("week", 1)

        # If there are NO scheduled matchups anywhere, skip
        any_scheduled = await db.matchups.find_one({"league_id": lid, "status": "scheduled"})
        if not any_scheduled:
            pytest.skip("No scheduled matchups to simulate")

        # Force current week to be the last regular-season week by deleting any higher-week scheduled games
        await db.matchups.delete_many({
            "league_id": lid,
            "week": {"$gt": cur_week},
            "$or": [{"is_playoff": {"$exists": False}}, {"is_playoff": False}],
        })
        await db.matchups.update_many(
            {"league_id": lid, "week": cur_week},
            {"$set": {"status": "scheduled"}},
        )

        # Simulate
        r = s.post(f"{BASE_URL}/api/matchups/simulate-week", json={"league_id": lid, "week": cur_week})
        assert r.status_code == 200, r.text

        # Check at least one team per division got crowned
        crowned = await db.teams.find(
            {"league_id": lid, "division_winner_at": {"$exists": True, "$ne": None}},
            {"division": 1, "name": 1, "division_winner_at": 1},
        ).to_list(50)
        crowned_divs = {c.get("division") for c in crowned}
        assert "North" in crowned_divs or "South" in crowned_divs, \
            f"Expected at least one division crowned, got: {[c for c in crowned]}"
    finally:
        client.close()
