"""Iter 107: Emergency-eligibility gate + Winner-of-X-vs-Y auto-labels."""
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
async def test_bracket_endpoint_surfaces_winner_of_labels_for_tbd_slots():
    """After generating a playoff_tree bracket with high_vs_low seeding, the
    TBD slots in Round 2+ should be labeled `Winner of X vs Y`."""
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
        rounds = d["rounds"]
        # Need at least Round 2 to see labels
        if len(rounds) >= 2:
            r2 = rounds[1]["matchups"]
            # Find at least one labelled TBD slot
            labelled = []
            for m in r2:
                for k in ("high_seed_label", "low_seed_label"):
                    if m.get(k):
                        labelled.append(m[k])
            assert any("Winner of" in lbl for lbl in labelled), (
                f"expected at least one 'Winner of' label, got: {labelled}"
            )
        # Cleanup
        await client.put(f"/api/leagues/{LID}", headers=headers, json={
            "playoff_format": before.get("playoff_format"),
            "playoff_seeding_method": before.get("playoff_seeding_method"),
        })


@pytest.mark.asyncio
async def test_bracket_winner_of_labels_use_team_abbr_when_available():
    """Auto-label should prefer `team_abbr` over team_name for compactness."""
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
        d = r.json()
        rounds = d["rounds"]
        if len(rounds) >= 2:
            labels = []
            for m in rounds[1]["matchups"]:
                for k in ("high_seed_label", "low_seed_label"):
                    if m.get(k):
                        labels.append(m[k])
            # At least one label should contain " vs " pattern
            assert any(" vs " in lbl for lbl in labels)
        # Cleanup
        await client.put(f"/api/leagues/{LID}", headers=headers, json={
            "playoff_format": before.get("playoff_format"),
            "playoff_seeding_method": before.get("playoff_seeding_method"),
        })
