"""Iter 101: Playoff Format + Seeding + Custom Matchups + Consolation Teams
limits + TBD-deadline notification scanner."""
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
EMAIL = "chriszarek@gmail.com"
PASSWORD = "Chris2026!"
LID = "69e46af167999bfb85c39628"


async def _token(client):
    r = await client.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
    return r.json()["access_token"]


@pytest.mark.asyncio
async def test_put_league_accepts_playoff_format_and_seeding():
    async with AsyncClient(base_url=BASE, timeout=15) as client:
        token = await _token(client)
        headers = {"Authorization": f"Bearer {token}"}
        before = await client.get(f"/api/leagues/{LID}", headers=headers)
        prev = before.json()

        r = await client.put(
            f"/api/leagues/{LID}",
            headers=headers,
            json={
                "playoff_format": "playoff_tree",
                "playoff_seeding_method": "high_vs_low",
            },
        )
        assert r.status_code == 200, r.text
        out = r.json()
        assert out["playoff_format"] == "playoff_tree"
        assert out["playoff_seeding_method"] == "high_vs_low"

        # Cleanup
        await client.put(f"/api/leagues/{LID}", headers=headers, json={
            "playoff_format": prev.get("playoff_format"),
            "playoff_seeding_method": prev.get("playoff_seeding_method"),
        })


@pytest.mark.asyncio
async def test_put_league_validates_format_enum():
    async with AsyncClient(base_url=BASE, timeout=15) as client:
        token = await _token(client)
        headers = {"Authorization": f"Bearer {token}"}
        r = await client.put(f"/api/leagues/{LID}", headers=headers,
                             json={"playoff_format": "single_elimination"})
        assert r.status_code == 422
        r = await client.put(f"/api/leagues/{LID}", headers=headers,
                             json={"playoff_seeding_method": "random"})
        assert r.status_code == 422


@pytest.mark.asyncio
async def test_put_league_accepts_custom_matchups():
    async with AsyncClient(base_url=BASE, timeout=15) as client:
        token = await _token(client)
        headers = {"Authorization": f"Bearer {token}"}
        custom = [
            {"week": 19, "matchups": [
                {"home": "team_a", "away": "team_b"},
                {"home": "team_c", "away": "tbd"},
            ]},
            {"week": 20, "matchups": [
                {"home": "tbd", "away": "tbd"},
            ]},
        ]
        r = await client.put(f"/api/leagues/{LID}", headers=headers,
                             json={"playoff_custom_matchups": custom})
        assert r.status_code == 200, r.text
        out = r.json()
        assert out["playoff_custom_matchups"] == custom
        # Cleanup
        await client.put(f"/api/leagues/{LID}", headers=headers,
                         json={"playoff_custom_matchups": None})


@pytest.mark.asyncio
async def test_put_league_rejects_too_many_consolation_teams():
    """Consolation teams cannot exceed (total_teams - playoff_teams)."""
    async with AsyncClient(base_url=BASE, timeout=15) as client:
        token = await _token(client)
        headers = {"Authorization": f"Bearer {token}"}
        league = (await client.get(f"/api/leagues/{LID}", headers=headers)).json()
        total = int(league.get("current_teams") or league.get("max_teams") or 12)
        playoffs = int(league.get("playoff_teams") or 8)
        # Request more consolation teams than non-playoff teams remaining
        r = await client.put(
            f"/api/leagues/{LID}",
            headers=headers,
            json={"consolation_teams": (total - playoffs) + 5},
        )
        assert r.status_code == 400
        assert "Consolation bracket can have at most" in r.json()["detail"]


@pytest.mark.asyncio
async def test_put_league_accepts_valid_consolation_teams():
    async with AsyncClient(base_url=BASE, timeout=15) as client:
        token = await _token(client)
        headers = {"Authorization": f"Bearer {token}"}
        league = (await client.get(f"/api/leagues/{LID}", headers=headers)).json()
        total = int(league.get("current_teams") or league.get("max_teams") or 12)
        playoffs = int(league.get("playoff_teams") or 8)
        valid = max(2, total - playoffs)
        r = await client.put(
            f"/api/leagues/{LID}",
            headers=headers,
            json={"consolation_teams": valid, "consolation_seeding_method": "adjacent"},
        )
        assert r.status_code == 200, r.text
        out = r.json()
        assert out["consolation_teams"] == valid
        assert out["consolation_seeding_method"] == "adjacent"
        # Cleanup
        await client.put(f"/api/leagues/{LID}", headers=headers,
                         json={"consolation_teams": league.get("consolation_teams"),
                               "consolation_seeding_method": league.get("consolation_seeding_method")})


@pytest.mark.asyncio
async def test_tbd_deadline_scanner_endpoint_responds():
    """POST /leagues/{id}/playoffs/check-tbd-deadlines must return a fired count."""
    async with AsyncClient(base_url=BASE, timeout=15) as client:
        token = await _token(client)
        headers = {"Authorization": f"Bearer {token}"}
        r = await client.post(f"/api/leagues/{LID}/playoffs/check-tbd-deadlines",
                              headers=headers)
        assert r.status_code == 200
        d = r.json()
        assert "fired" in d
        assert isinstance(d["fired"], int)
        assert d["league_id"] == LID
