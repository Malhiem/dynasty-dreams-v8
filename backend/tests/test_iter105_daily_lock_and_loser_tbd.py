"""Iter 105: Daily Lock goalie method + TBD loser sentinel + runtime wiring."""
import os
import pytest
from httpx import AsyncClient


def _backend_url():
    env_path = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", ".env")
    with open(env_path) as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip()
    raise RuntimeError("REACT_APP_BACKEND_URL not found")


BASE = _backend_url()
EMAIL = os.environ.get("TEST_OWNER_EMAIL", "test-owner@e2e.dynastydreams.com")
PASSWORD = os.environ.get("TEST_OWNER_PASSWORD", "e2e-owner-password")
LID = "69e46af167999bfb85c39628"


async def _token(client):
    r = await client.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
    return r.json()["access_token"]


@pytest.mark.asyncio
async def test_put_league_accepts_daily_lock_goalie_method():
    async with AsyncClient(base_url=BASE, timeout=15) as client:
        token = await _token(client)
        headers = {"Authorization": f"Bearer {token}"}
        before = (await client.get(f"/api/leagues/{LID}", headers=headers)).json()
        r = await client.put(f"/api/leagues/{LID}", headers=headers, json={
            "differentiate_goalie_scoring": True,
            "goalie_scoring_method": "daily_lock",
        })
        assert r.status_code == 200, r.text
        assert r.json()["goalie_scoring_method"] == "daily_lock"
        # Cleanup
        await client.put(f"/api/leagues/{LID}", headers=headers, json={
            "differentiate_goalie_scoring": before.get("differentiate_goalie_scoring"),
            "goalie_scoring_method": before.get("goalie_scoring_method"),
        })


@pytest.mark.asyncio
async def test_put_league_consolation_custom_matchups_accepts_loser_sentinel():
    """Backend persists `tbd_loser` slots as-is so a loser's bracket can be formed."""
    async with AsyncClient(base_url=BASE, timeout=15) as client:
        token = await _token(client)
        headers = {"Authorization": f"Bearer {token}"}
        custom = [
            {"week": 19, "matchups": [
                {"home": "team_a", "away": "team_b"},
                {"home": "team_c", "away": "team_d"},
            ]},
            {"week": 20, "matchups": [
                # Standard winners' advance
                {"home": "tbd", "away": "tbd"},
                # Loser's bracket pair
                {"home": "tbd_loser", "away": "tbd_loser"},
            ]},
        ]
        r = await client.put(f"/api/leagues/{LID}", headers=headers, json={
            "consolation_custom_matchups": custom,
        })
        assert r.status_code == 200, r.text
        out = r.json()
        # Verify the loser sentinel survives the round-trip
        loser_rows = [
            m for entry in (out["consolation_custom_matchups"] or [])
            for m in entry["matchups"]
            if m.get("home") == "tbd_loser" or m.get("away") == "tbd_loser"
        ]
        assert len(loser_rows) >= 1, f"loser sentinel not persisted: {out['consolation_custom_matchups']}"
        # Cleanup
        await client.put(f"/api/leagues/{LID}", headers=headers,
                         json={"consolation_custom_matchups": None})


@pytest.mark.asyncio
async def test_bracket_generator_marks_loser_sentinel_with_tbd_type():
    """Custom consolation builder must distinguish winner vs loser TBD via
    `home_tbd_type` / `away_tbd_type` so the bracket UI can render the right label."""
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from routes.matchups import _build_playoff_bracket

    league = {
        "consolation_seeding_method": "custom",
        "consolation_start_week": 19,
        "consolation_end_week": 21,
        "consolation_custom_matchups": [
            {"week": 19, "matchups": [
                {"home": "t1", "away": "t2"},
                {"home": "t3", "away": "t4"},
            ]},
            {"week": 20, "matchups": [
                {"home": "tbd", "away": "tbd"},
                {"home": "tbd_loser", "away": "tbd_loser"},
            ]},
        ],
    }
    rows = _build_playoff_bracket(league, teams=[], is_consolation=True)
    week_20 = [r for r in rows if r["week"] == 20]
    assert len(week_20) == 2
    winners = [r for r in week_20 if r.get("home_tbd_type") == "winner"]
    losers = [r for r in week_20 if r.get("home_tbd_type") == "loser"]
    assert len(winners) == 1
    assert len(losers) == 1
    # Both slots in the loser row should be marked
    assert losers[0]["away_tbd_type"] == "loser"


@pytest.mark.asyncio
async def test_put_league_rejects_invalid_goalie_method_still_works():
    """Sanity: new enum value didn't accidentally widen rejection of bad values."""
    async with AsyncClient(base_url=BASE, timeout=15) as client:
        token = await _token(client)
        headers = {"Authorization": f"Bearer {token}"}
        r = await client.put(f"/api/leagues/{LID}", headers=headers,
                             json={"goalie_scoring_method": "weighted_random"})
        assert r.status_code == 422
