"""
Iter 228s — Roster Draft Picks chronological sort + per-section count.

Backend portion: GET /api/teams/{id}/draft-picks now decorates each
pick with `draft_scheduled_time` so the Roster page can sort groups
by parent draft's scheduled date (soonest first).
"""
import os
import uuid
import requests
from datetime import datetime, timedelta, timezone
from bson import ObjectId
from pymongo import MongoClient

API_URL = os.environ["REACT_APP_BACKEND_URL"]


def _db():
    return MongoClient(os.environ["MONGO_URL"])[os.environ.get("DB_NAME", os.environ["DB_NAME"])]


def _register(prefix="i228s"):
    s = uuid.uuid4().hex[:8]
    e = f"{prefix}_{s}@example.com"
    requests.post(f"{API_URL}/api/auth/register", json={
        "email": e, "password": "Pass123!",
        "username": f"{prefix}_{s}", "name": prefix.title(),
    }).raise_for_status()
    r = requests.post(f"{API_URL}/api/auth/login",
                      json={"email": e, "password": "Pass123!"})
    return e, r.json()["access_token"]


def test_team_draft_picks_include_draft_scheduled_time():
    """Each pick should carry the parent draft's scheduled_time so the
    Roster page can sort groups chronologically.

    Mirrors the TFHL scenario: an Inaugural draft in May, a Summer Entry
    draft in July, and a Winter draft in December — all in 2026. The
    Roster page must list them in that chronological order regardless
    of draft name."""
    _, tok = _register()
    H = {"Authorization": f"Bearer {tok}"}
    r = requests.post(f"{API_URL}/api/leagues", headers=H, json={
        "name": f"i228s-{uuid.uuid4().hex[:6]}", "format": "dynasty",
        "scoring_format": "head_to_head", "max_teams": 4,
        "draft_type": "snake", "roster_spots": 19,
    })
    r.raise_for_status()
    league = r.json()

    drafts_to_create = [
        ("Z Winter Reserve",  "2026-12-12T19:00:00Z"),  # name starts with Z but is LAST
        ("A Inaugural",       "2026-05-01T19:00:00Z"),  # name starts with A but is FIRST
        ("M Summer Entry",    "2026-07-15T19:00:00Z"),  # middle
    ]
    for name, sched in drafts_to_create:
        rr = requests.post(f"{API_URL}/api/drafts", headers=H, json={
            "league_id": league["id"], "name": name,
            "scheduled_time": sched,
            "total_rounds": 1, "time_per_pick": 60,
            "pick_trading_enabled": True, "trading_window_opens": "immediately",
        })
        rr.raise_for_status()

    db = _db()
    team = db.teams.find_one({"league_id": league["id"]})
    assert team

    r2 = requests.get(f"{API_URL}/api/teams/{team['_id']}/draft-picks", headers=H)
    assert r2.status_code == 200, r2.text
    picks = r2.json()["picks"]
    assert len(picks) >= 3, picks

    # Build the unique-name set + assert every pick has draft_scheduled_time.
    by_name = {}
    for p in picks:
        assert "draft_scheduled_time" in p, f"Missing draft_scheduled_time: {p}"
        by_name.setdefault(p["draft_name"], []).append(p["draft_scheduled_time"])

    # Verify times match what we created.
    assert "A Inaugural" in by_name
    assert "M Summer Entry" in by_name
    assert "Z Winter Reserve" in by_name
    assert by_name["A Inaugural"][0].startswith("2026-05-01")
    assert by_name["M Summer Entry"][0].startswith("2026-07-15")
    assert by_name["Z Winter Reserve"][0].startswith("2026-12-12")


def test_team_draft_picks_count_matches_rounds_times_team_count():
    """Sanity test the user's specific scenario:
       - Inaugural: 55 rounds → 55 picks per team
       - Summer Entry: 4 rounds → 4 picks per team
       - Winter: 2 rounds → 2 picks per team

    Each team should see exactly that many picks per section.
    """
    _, tok = _register()
    H = {"Authorization": f"Bearer {tok}"}
    r = requests.post(f"{API_URL}/api/leagues", headers=H, json={
        "name": f"i228s-counts-{uuid.uuid4().hex[:6]}", "format": "dynasty",
        "scoring_format": "head_to_head", "max_teams": 4,
        "draft_type": "snake", "roster_spots": 60,
    })
    r.raise_for_status()
    league = r.json()

    schedule = [
        ("Inaugural", "2026-05-01T19:00:00Z", 55),
        ("Summer Entry", "2026-07-15T19:00:00Z", 4),
        ("Winter", "2026-12-12T19:00:00Z", 2),
    ]
    for name, sched, rounds in schedule:
        rr = requests.post(f"{API_URL}/api/drafts", headers=H, json={
            "league_id": league["id"], "name": name,
            "scheduled_time": sched,
            "total_rounds": rounds, "time_per_pick": 60,
            "pick_trading_enabled": True, "trading_window_opens": "immediately",
        })
        rr.raise_for_status()

    db = _db()
    team = db.teams.find_one({"league_id": league["id"]})
    r2 = requests.get(f"{API_URL}/api/teams/{team['_id']}/draft-picks", headers=H)
    picks = r2.json()["picks"]

    by_name: dict = {}
    for p in picks:
        by_name.setdefault(p["draft_name"], 0)
        by_name[p["draft_name"]] += 1
    assert by_name.get("Inaugural") == 55, by_name
    assert by_name.get("Summer Entry") == 4, by_name
    assert by_name.get("Winter") == 2, by_name
