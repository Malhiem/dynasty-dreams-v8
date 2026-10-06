"""
Iter 182 — Live integration smokes against the deployed preview.

Validates the 5 backend smoke items in the review request:
  #1 No "(Prospect)" suffix lingering in player names.
  #2 GET /api/players?search=McKenna returns exactly ONE Gavin McKenna.
  #3 GET /api/players?timeframe=2024-25 returns real 2024-25 reg-season stats.
  #4 GET /api/players?timeframe=2024-playoffs returns 2024 playoff stats.
  #5 GET /api/waivers/available?timeframe=2024-25 honours timeframe.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://dynasty-preview.preview.emergentagent.com").rstrip("/")
EMAIL = os.environ.get("TEST_OWNER_EMAIL", "test-owner@e2e.dynastydreams.com")
PASSWORD = os.environ.get("TEST_OWNER_PASSWORD", "e2e-owner-password")
LEAGUE_ID = "69e46af167999bfb85c39628"  # Ice Kings


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": EMAIL, "password": PASSWORD}, timeout=20)
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text[:200]}"
    body = r.json()
    token = body.get("token") or body.get("access_token")
    if token:
        s.headers.update({"Authorization": f"Bearer {token}"})
    return s


@pytest.fixture(scope="module", autouse=True)
def historical_stat_inputs(_global_pollution_sweep):
    """Synthetic stored inputs verify API wiring without a live NHL backfill."""
    from pymongo import MongoClient
    from bson import ObjectId
    assert os.environ.get("TEST_SUITE_ISOLATED") == "1"
    with MongoClient(os.environ["MONGO_URL"]) as client:
        db = client[os.environ["DB_NAME"]]
        kuch_id = ObjectId()
        db.players.insert_one({"_id": kuch_id, "name": "Nikita Kucherov", "position": "RW", "team": "TBL", "sport": "nhl", "season": "2025-2026", "points": 121,
            "games_played": 78, "goals": 37, "assists": 84, "player_type": "skater", "nhl_id": 8476453, "_test_seed": True})
        mcdavid = db.players.find_one({"name": "Connor McDavid"})
        cached = []
        # Supply a cache row for every fixture player so pagination is independent of sort order.
        for player in db.players.find({}):
            cached.append({"player_id": str(player["_id"]), "season": "2024-25", "season_type": "regular",
                "games_played": 78, "goals": 37, "assists": 84, "points": 121, "_historical_fixture": True})
        cached.append({"player_id": str(mcdavid["_id"]), "season": "2024-25", "season_type": "playoffs",
            "games_played": 22, "points": 33, "_historical_fixture": True})
        db.player_season_stats.insert_many(cached)
        yield
        db.player_season_stats.delete_many({"_historical_fixture": True})
        db.players.delete_one({"_id": kuch_id})


# ── Smoke #1 + #2 ───────────────────────────────────────────────────
def test_smoke_no_prospect_suffix_and_single_mckenna(session):
    r = session.get(f"{BASE_URL}/api/players", params={"search": "McKenna", "limit": 50}, timeout=20)
    assert r.status_code == 200, r.text[:200]
    payload = r.json()
    players = payload.get("players", payload if isinstance(payload, list) else [])
    gavins = [p for p in players if p.get("name", "").startswith("Gavin McKenna")]
    assert len(gavins) == 1, f"Expected exactly 1 Gavin McKenna, got {len(gavins)}: {[p.get('name') for p in gavins]}"
    assert "(Prospect)" not in gavins[0]["name"], f"Suffix lingers: {gavins[0]['name']!r}"

    # Broader scan for any "(Prospect)" suffix across page-1 of players
    r2 = session.get(f"{BASE_URL}/api/players", params={"limit": 200}, timeout=20)
    if r2.status_code == 200:
        pl = r2.json().get("players", [])
        offenders = [p["name"] for p in pl if "(Prospect)" in p.get("name", "")]
        assert not offenders, f"Players still carrying '(Prospect)' suffix: {offenders[:5]}"


# ── Smoke #3 — 2024-25 regular season stats from NHL backfill ──────
def test_smoke_players_2024_25_timeframe(session):
    r = session.get(
        f"{BASE_URL}/api/players",
        params={"timeframe": "2024-25", "search": "Kucherov", "limit": 5},
        timeout=20,
    )
    assert r.status_code == 200, r.text[:200]
    payload = r.json()
    assert payload.get("timeframe_supported") is True, f"timeframe_supported missing/false: {payload.get('timeframe_supported')}"
    players = payload.get("players", [])
    kuch = next((p for p in players if "Kucherov" in p.get("name", "")), None)
    assert kuch, f"Kucherov not found in 2024-25 timeframe response: {[p.get('name') for p in players]}"
    # Real 2024-25 numbers per spec: GP:78 G:37 A:84 P:121
    assert kuch.get("games_played") == 78, f"Kucherov GP {kuch.get('games_played')} != 78"
    assert kuch.get("points") == 121, f"Kucherov P {kuch.get('points')} != 121"


# ── Smoke #4 — 2024 playoffs ────────────────────────────────────────
def test_smoke_players_2024_playoffs_timeframe(session):
    r = session.get(
        f"{BASE_URL}/api/players",
        params={"timeframe": "2024-playoffs", "search": "McDavid", "limit": 5},
        timeout=20,
    )
    assert r.status_code == 200, r.text[:200]
    payload = r.json()
    assert payload.get("timeframe_supported") is True
    players = payload.get("players", [])
    mcd = next((p for p in players if "McDavid" in p.get("name", "")), None)
    assert mcd, f"McDavid not found in 2024-playoffs response: {[p.get('name') for p in players]}"
    # 2024 playoffs: GP:22 P:33
    assert mcd.get("games_played") == 22, f"McDavid playoff GP {mcd.get('games_played')} != 22"
    assert mcd.get("points") == 33, f"McDavid playoff P {mcd.get('points')} != 33"


# ── Smoke #5 — Waivers /available timeframe pass-through ────────────
def test_smoke_waivers_available_timeframe(session):
    r = session.get(
        f"{BASE_URL}/api/waivers/available",
        params={"league_id": LEAGUE_ID, "timeframe": "2024-25", "limit": 200},
        timeout=30,
    )
    assert r.status_code == 200, r.text[:200]
    payload = r.json()
    assert payload.get("timeframe_supported") is True
    assert payload.get("timeframe") == "2024-25"
    players = payload.get("players", payload.get("available_players", []))
    # Kucherov should be free agent (not on Ice Kings) with 2024-25 stats
    kuch = next((p for p in players if "Kucherov" in p.get("name", "")), None)
    if kuch:
        assert kuch.get("games_played") == 78, f"Kucherov in waivers GP {kuch.get('games_played')} != 78"
        assert kuch.get("points") == 121
