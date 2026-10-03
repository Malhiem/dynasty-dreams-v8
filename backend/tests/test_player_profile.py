"""Tests for the player profile detail endpoints (news / recent-games /
historical-stats / recent-performance / cross-league-ownership /
transactions / usage)."""
import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from httpx import AsyncClient


def _backend_url():
    env_path = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", ".env")
    with open(env_path) as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip()
    raise RuntimeError("REACT_APP_BACKEND_URL not found")


BASE = _backend_url()


async def _login(client, email, password):
    r = await client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


async def _mcdavid_id(client):
    r = await client.get("/api/players?search=Connor McDavid&limit=1")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["players"], "No player found"
    return body["players"][0]["_id"]


async def _league_id(client, token):
    r = await client.get("/api/leagues?my_leagues=true",
                         headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    leagues = r.json()
    assert leagues, "User has no leagues"
    return leagues[0]["id"]


@pytest.mark.asyncio
async def test_player_news_history():
    async with AsyncClient(base_url=BASE, timeout=30) as client:
        pid = await _mcdavid_id(client)
        r = await client.get(f"/api/players/{pid}/news?limit=5")
        assert r.status_code == 200
        body = r.json()
        assert body["player_id"] == pid
        assert isinstance(body["news"], list)
        # Sorted desc by published_at
        if len(body["news"]) >= 2:
            assert body["news"][0]["published_at"] >= body["news"][1]["published_at"]


@pytest.mark.asyncio
async def test_player_recent_games_with_league_scoring():
    async with AsyncClient(base_url=BASE, timeout=30) as client:
        token = await _login(client, os.environ.get("TEST_OWNER_EMAIL", "test-owner@e2e.dynastydreams.com"), os.environ.get("TEST_OWNER_PASSWORD", "e2e-owner-password"))
        pid = await _mcdavid_id(client)
        lid = await _league_id(client, token)
        r = await client.get(
            f"/api/players/{pid}/recent-games?league_id={lid}&limit=5",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert "games" in body
        if body["games"]:
            g = body["games"][0]
            for k in ("date", "team", "fantasy_points", "goals", "assists", "shots", "plus_minus"):
                assert k in g, f"missing key {k}"


@pytest.mark.asyncio
async def test_player_historical_stats_uses_league_scoring():
    async with AsyncClient(base_url=BASE, timeout=60) as client:
        token = await _login(client, os.environ.get("TEST_OWNER_EMAIL", "test-owner@e2e.dynastydreams.com"), os.environ.get("TEST_OWNER_PASSWORD", "e2e-owner-password"))
        pid = await _mcdavid_id(client)
        lid = await _league_id(client, token)
        r = await client.get(
            f"/api/players/{pid}/historical-stats?league_id={lid}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        # NHL API may be unavailable in CI; if it errored, we still get a clean
        # 200 with seasons=[] and an explanatory note. Accept either path.
        assert "seasons" in body
        if body["seasons"]:
            s = body["seasons"][0]
            for k in ("season", "team", "games_played", "fantasy_points"):
                assert k in s


@pytest.mark.asyncio
async def test_player_recent_performance_windows():
    async with AsyncClient(base_url=BASE, timeout=30) as client:
        token = await _login(client, os.environ.get("TEST_OWNER_EMAIL", "test-owner@e2e.dynastydreams.com"), os.environ.get("TEST_OWNER_PASSWORD", "e2e-owner-password"))
        pid = await _mcdavid_id(client)
        lid = await _league_id(client, token)
        r = await client.get(
            f"/api/players/{pid}/recent-performance?league_id={lid}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        body = r.json()
        for label in ("last_7d", "prev_7d", "last_14d", "last_30d"):
            assert label in body["windows"], f"missing window {label}"
            w = body["windows"][label]
            assert "fantasy_points" in w
            assert "games_played" in w
        # last_14d should be >= last_7d for any monotone-non-decreasing stat.
        assert body["windows"]["last_14d"]["games_played"] >= body["windows"]["last_7d"]["games_played"]
        assert body["windows"]["last_30d"]["games_played"] >= body["windows"]["last_14d"]["games_played"]


@pytest.mark.asyncio
async def test_cross_league_ownership_lists_user_leagues():
    async with AsyncClient(base_url=BASE, timeout=30) as client:
        token = await _login(client, os.environ.get("TEST_OWNER_EMAIL", "test-owner@e2e.dynastydreams.com"), os.environ.get("TEST_OWNER_PASSWORD", "e2e-owner-password"))
        pid = await _mcdavid_id(client)
        r = await client.get(
            f"/api/players/{pid}/cross-league-ownership",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        body = r.json()
        assert isinstance(body["leagues"], list)
        # User has multiple leagues — at least one entry expected
        assert len(body["leagues"]) >= 1
        # Owned-by-me entries must have a team_name set
        for row in body["leagues"]:
            if row["owned_by_me"]:
                assert row["owned_by_team_id"]
                assert row["owned_by_team_name"]
                assert row["is_free_agent"] is False


@pytest.mark.asyncio
async def test_player_transactions_filtered_by_league():
    async with AsyncClient(base_url=BASE, timeout=30) as client:
        token = await _login(client, os.environ.get("TEST_OWNER_EMAIL", "test-owner@e2e.dynastydreams.com"), os.environ.get("TEST_OWNER_PASSWORD", "e2e-owner-password"))
        pid = await _mcdavid_id(client)
        lid = await _league_id(client, token)
        r = await client.get(
            f"/api/players/{pid}/transactions?league_id={lid}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        body = r.json()
        assert "transactions" in body
        # Every txn must reference our league when filtered
        for t in body["transactions"]:
            assert t["league_id"] == lid


@pytest.mark.asyncio
async def test_player_usage_per_week():
    async with AsyncClient(base_url=BASE, timeout=30) as client:
        token = await _login(client, os.environ.get("TEST_OWNER_EMAIL", "test-owner@e2e.dynastydreams.com"), os.environ.get("TEST_OWNER_PASSWORD", "e2e-owner-password"))
        pid = await _mcdavid_id(client)
        lid = await _league_id(client, token)
        r = await client.get(
            f"/api/players/{pid}/usage?league_id={lid}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["league_id"] == lid
        assert isinstance(body["weeks"], list)
        for w in body["weeks"]:
            assert "week" in w
            assert "team_name" in w
            assert "section" in w
            assert "is_active" in w
