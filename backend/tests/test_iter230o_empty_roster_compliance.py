"""
Iter 230o — Empty roster surfaces as non-compliant.

Hamilton Coyotes (and other expansion / abandoned teams) used to render
as "Compliant" in the Roster Status tile because the compliance endpoint
only checked for over-roster, salary, IR, and minors violations — it
silently passed when `roster_count == 0`. This left UX surfaces (e.g.
LeagueDetailPage standings, Team page) misleading users into thinking
the team was ready to play.

This iteration adds an `empty_roster` reason code so the
`RosterStatusTile` dropdown explicitly tells the user *why* the team is
not in compliance and what action to take.
"""
import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from httpx import AsyncClient


def _backend_url():
    env = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", ".env")
    with open(env) as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip()
    raise RuntimeError("REACT_APP_BACKEND_URL not found")


BASE = _backend_url()
COMMISSIONER_EMAIL = "chriszarek@gmail.com"
COMMISSIONER_PASSWORD = "Chris2026!"
# Hamilton Coyotes — Iter 230o seed team with an empty roster, used as
# the canonical regression fixture for the "empty roster must be
# non-compliant" rule. Resolved at test run time so test data churn
# (re-seeds, ID changes) doesn't break the assertion.
EMPTY_TEAM_NAME = "Hamilton Coyotes"


async def _login(client, email, password):
    r = await client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


async def _resolve_empty_team_id():
    """Pull the Hamilton Coyotes team_id directly from Mongo so the
    test stays robust against re-seeds / ObjectId changes."""
    from motor.motor_asyncio import AsyncIOMotorClient
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    doc = await db.teams.find_one(
        {"name": EMPTY_TEAM_NAME},
        {"_id": 1, "roster": 1},
    )
    assert doc is not None, f"{EMPTY_TEAM_NAME} not seeded — test fixture missing"
    assert not (doc.get("roster") or []), (
        f"{EMPTY_TEAM_NAME} has players now; pick a different empty-roster fixture"
    )
    return str(doc["_id"])


@pytest.mark.asyncio
async def test_empty_roster_team_is_non_compliant():
    team_id = await _resolve_empty_team_id()
    async with AsyncClient(base_url=BASE, timeout=30) as client:
        token = await _login(client, COMMISSIONER_EMAIL, COMMISSIONER_PASSWORD)
        h = {"Authorization": f"Bearer {token}"}
        r = await client.get(f"/api/teams/{team_id}/compliance", headers=h)
        assert r.status_code == 200, r.text
        body = r.json()

        # The whole point: 0 players → non-compliant.
        assert body["roster_count"] == 0
        assert body["compliant"] is False, (
            "Empty roster must surface as non-compliant so the Roster Status tile "
            "doesn't lie to expansion / abandoned team owners."
        )

        # And the user-facing dropdown must include a clear, actionable
        # reason — not just a silent illegal flag.
        codes = [r.get("code") for r in body.get("reasons") or []]
        assert "empty_roster" in codes, codes

        reason = next(r for r in body["reasons"] if r["code"] == "empty_roster")
        assert reason["label"] == "Roster is empty"
        # Detail tells the user WHY (count vs cap) and WHAT to do (draft/claim).
        assert "0 players" in reason["detail"]
        assert "Draft or claim" in reason["detail"]


@pytest.mark.asyncio
async def test_empty_roster_takes_precedence_over_too_many_players():
    """The `empty_roster` and `too_many_players` checks are mutually
    exclusive — same `roster_count` field — so we just verify the
    over-cap branch isn't accidentally triggered when count == 0."""
    team_id = await _resolve_empty_team_id()
    async with AsyncClient(base_url=BASE, timeout=30) as client:
        token = await _login(client, COMMISSIONER_EMAIL, COMMISSIONER_PASSWORD)
        h = {"Authorization": f"Bearer {token}"}
        r = await client.get(f"/api/teams/{team_id}/compliance", headers=h)
        codes = [x.get("code") for x in r.json().get("reasons") or []]
        assert "too_many_players" not in codes
