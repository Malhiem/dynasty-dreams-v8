"""Live API tests for iter232N.6 + 232N.7 against preview URL."""
import os
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://dynasty-preview.preview.emergentagent.com").rstrip("/")
TFHL = "6a3a0781a842ea2f7bcdc7cb"


@pytest.fixture(scope="module")
def auth_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": "chriszarek@gmail.com", "password": "Chris2026!"})
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text[:200]}"
    return s


# ---- 232N.6: waivers limit cap ----
def test_waivers_limit_5000_clamped_to_200(auth_session):
    r = auth_session.get(f"{BASE_URL}/api/waivers/available", params={"league_id": TFHL, "limit": 5000})
    assert r.status_code == 200, r.text[:300]
    data = r.json()
    players = data if isinstance(data, list) else data.get("players", data.get("available", []))
    assert isinstance(players, list)
    assert len(players) <= 200, f"expected ≤200, got {len(players)}"


def test_waivers_limit_150(auth_session):
    r = auth_session.get(f"{BASE_URL}/api/waivers/available", params={"league_id": TFHL, "limit": 150})
    assert r.status_code == 200
    data = r.json()
    players = data if isinstance(data, list) else data.get("players", data.get("available", []))
    assert len(players) <= 150


def test_waivers_limit_zero_defaults(auth_session):
    r = auth_session.get(f"{BASE_URL}/api/waivers/available", params={"league_id": TFHL, "limit": 0})
    assert r.status_code == 200


# ---- 232N.7: player trends ----
def test_leaderboard_traded_returns_mcdavid(auth_session):
    r = auth_session.get(f"{BASE_URL}/api/player-trends/leaderboard", params={"movers": "traded", "limit": 5})
    assert r.status_code == 200, r.text[:300]
    data = r.json()
    items = data if isinstance(data, list) else data.get("items", data.get("players", []))
    assert len(items) > 0, "expected at least 1 traded player"
    top = items[0]
    name = (top.get("name") or top.get("player_name") or "").lower()
    assert "mcdavid" in name, f"expected McDavid at top; got {top}"
    assert top.get("trades_7d", 0) > 0
    assert top.get("trend") == "traded"


def test_leaderboard_hot_and_dropped_and_all(auth_session):
    for movers in ["hot", "dropped", "all"]:
        r = auth_session.get(f"{BASE_URL}/api/player-trends/leaderboard", params={"movers": movers, "limit": 5})
        assert r.status_code == 200, f"{movers}: {r.text[:200]}"


def test_players_endpoint_stamps_trends(auth_session):
    r = auth_session.get(f"{BASE_URL}/api/players", params={"league_id": TFHL, "limit": 5})
    assert r.status_code == 200
    data = r.json()
    players = data if isinstance(data, list) else data.get("players", data.get("items", []))
    assert len(players) > 0
    # Every player must have 'trends' key (may be null)
    assert all("trends" in p for p in players), "trends field missing on some players"


def test_waivers_stamps_trends(auth_session):
    r = auth_session.get(f"{BASE_URL}/api/waivers/available", params={"league_id": TFHL, "limit": 10})
    assert r.status_code == 200
    data = r.json()
    players = data if isinstance(data, list) else data.get("players", data.get("available", []))
    if players:
        assert "trends" in players[0]


def test_player_status_feed_stamps_trends(auth_session):
    r = auth_session.get(f"{BASE_URL}/api/player-status/feed", params={"league_id": TFHL})
    assert r.status_code == 200, r.text[:300]
