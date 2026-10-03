"""Iter 104: GET /leagues/{id}/playoff-bracket honors persisted `is_playoff`
+ `bracket_round` matchups (instead of the legacy hardcoded high_vs_low only)."""
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
async def test_playoff_bracket_reads_persisted_matchups_when_present():
    """After generate-schedule with playoff_format=playoff_tree, the bracket
    endpoint must return rounds grouped by `bracket_round` instead of the
    legacy projected hardcoded seeding."""
    async with AsyncClient(base_url=BASE, timeout=20) as client:
        token = await _token(client)
        headers = {"Authorization": f"Bearer {token}"}

        # Snapshot then configure adjacent seeding
        before = (await client.get(f"/api/leagues/{LID}", headers=headers)).json()
        await client.put(f"/api/leagues/{LID}", headers=headers, json={
            "playoff_format": "playoff_tree",
            "playoff_seeding_method": "adjacent",
        })
        await client.post("/api/matchups/generate-schedule", headers=headers, json={
            "league_id": LID, "num_weeks": 18,
        })

        r = await client.get(f"/api/leagues/{LID}/playoff-bracket")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["status"] == "actual"
        assert d["seeding_method"] == "adjacent"
        assert d["playoff_format"] == "playoff_tree"
        # Adjacent seeding for top 8: Round 1 should be (1v2, 3v4, 5v6, 7v8)
        rounds = d["rounds"]
        assert len(rounds) >= 1
        r1 = rounds[0]
        assert "Round" in r1["name"] or "Quarterfinals" in r1["name"]
        # All Round 1 matchups must reference REAL teams (not TBD) since we
        # generated with seeded teams.
        r1_real_matchups = [m for m in r1["matchups"] if m.get("high_seed") and m.get("low_seed")]
        assert len(r1_real_matchups) >= 2
        # Verify adjacent pairing: seeds for each Round 1 matchup differ by 1
        for m in r1_real_matchups:
            hs_seed = m["high_seed"]["seed"]
            ls_seed = m["low_seed"]["seed"]
            assert abs(hs_seed - ls_seed) == 1, (
                f"Adjacent seeding expects diff=1, got {hs_seed} vs {ls_seed}"
            )

        # Later rounds (TBD placeholders) should have empty slots
        later = [r for r in rounds if r is not rounds[0]]
        if later:
            assert any(
                (m.get("high_seed") is None or m.get("low_seed") is None)
                for r in later for m in r.get("matchups", [])
            )

        # Cleanup
        await client.put(f"/api/leagues/{LID}", headers=headers, json={
            "playoff_format": before.get("playoff_format"),
            "playoff_seeding_method": before.get("playoff_seeding_method"),
        })


@pytest.mark.asyncio
async def test_playoff_bracket_high_vs_low_seeding_through_persisted_data():
    async with AsyncClient(base_url=BASE, timeout=20) as client:
        token = await _token(client)
        headers = {"Authorization": f"Bearer {token}"}

        before = (await client.get(f"/api/leagues/{LID}", headers=headers)).json()
        await client.put(f"/api/leagues/{LID}", headers=headers, json={
            "playoff_format": "playoff_tree",
            "playoff_seeding_method": "high_vs_low",
        })
        await client.post("/api/matchups/generate-schedule", headers=headers, json={
            "league_id": LID, "num_weeks": 18,
        })
        r = await client.get(f"/api/leagues/{LID}/playoff-bracket")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["seeding_method"] == "high_vs_low"
        # 8 teams high-vs-low: (1v8, 2v7, 3v6, 4v5) - seed pairs must sum to 9
        r1 = d["rounds"][0]["matchups"]
        for m in r1:
            if m.get("high_seed") and m.get("low_seed"):
                assert m["high_seed"]["seed"] + m["low_seed"]["seed"] == 9

        # Cleanup
        await client.put(f"/api/leagues/{LID}", headers=headers, json={
            "playoff_format": before.get("playoff_format"),
            "playoff_seeding_method": before.get("playoff_seeding_method"),
        })
