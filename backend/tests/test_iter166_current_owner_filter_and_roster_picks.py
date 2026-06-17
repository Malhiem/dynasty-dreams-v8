"""
Iter 166 — Filter-by-current-owner + Roster page live picks.

Part A:
  - Draft Board's owner filter now resolves against `current_team_id`
    (via the live picks payload's `_currentOwnerAbbrs` annotation),
    not the column header. A pick traded ICE → CRA dims on the ICE
    chip filter and lights up on the CRA chip filter.

Part B:
  - New backend endpoint `GET /api/teams/{team_id}/draft-picks` returns
    every pick currently owned by the team (with full `trade_history`).
  - `TeamDraftPicks.tsx` now fetches from that endpoint whenever the
    `teamId` looks like a Mongo ObjectId (24 hex), and renders a small
    `↔` `ArrowRightLeft` chip + the `<PickProvenance>` tooltip body on
    traded-in picks.
"""
import os
from pathlib import Path

import pytest
from httpx import AsyncClient

# Iter 171 — DraftRoom.tsx was split into sub-components. Resolve the legacy
# "read the entire draft room source" pattern as the concatenation of the
# parent + extracted draftroom/* files so existing grep-style assertions
# keep working without rewriting every spec.
def _iter171_draftroom_concat() -> str:
    from pathlib import Path as _P
    paths = [
        _P("/app/frontend/src/lovable/pages/DraftRoom.tsx"),
        _P("/app/frontend/src/lovable/pages/draftroom/DraftLiveTile.tsx"),
        _P("/app/frontend/src/lovable/pages/draftroom/DraftBoard.tsx"),
        _P("/app/frontend/src/lovable/pages/draftroom/PlayerSearchPanel.tsx"),
        _P("/app/frontend/src/lovable/pages/draftroom/draftConstants.ts"),
    ]
    return chr(10).join(p.read_text() for p in paths if p.exists())


class _Iter171DraftRoomShim:
    def read_text(self, *a, **kw) -> str:
        return _iter171_draftroom_concat()


def _iter171_install_shim_after_imports():
    pass



def _backend_url():
    env = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", ".env")
    with open(env) as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip()
    raise RuntimeError("BASE missing")


BASE = _backend_url()
ADMIN = ("admin@dynastydreams.com", "Admin123!")
LID = "69e46af167999bfb85c39628"


async def _tok(client, email, password):
    r = await client.post("/api/auth/login", json={"email": email, "password": password})
    return r.json()["access_token"]


# ── Backend ──


@pytest.mark.asyncio
async def test_team_draft_picks_endpoint_returns_currently_owned():
    async with AsyncClient(base_url=BASE, timeout=30) as client:
        token = await _tok(client, *ADMIN)
        h = {"Authorization": f"Bearer {token}"}
        # Pick any team in the league by reading all picks
        r = await client.get(f"/api/drafts/{LID}/picks", headers=h)
        picks_payload = r.json()
        teams_with_picks = list({p["current_team_id"] for p in picks_payload["picks"]})
        assert teams_with_picks, "Picks should exist for the league"
        tid = teams_with_picks[0]
        # Hit the new endpoint
        r2 = await client.get(f"/api/teams/{tid}/draft-picks", headers=h)
        assert r2.status_code == 200
        d = r2.json()
        assert d["team_id"] == tid
        # Every returned pick has current_team_id == requested team
        assert all(p["current_team_id"] == tid for p in d["picks"])
        # And carries trade_history (may be empty)
        for p in d["picks"]:
            assert "trade_history" in p


@pytest.mark.asyncio
async def test_team_draft_picks_year_filter():
    async with AsyncClient(base_url=BASE, timeout=30) as client:
        token = await _tok(client, *ADMIN)
        h = {"Authorization": f"Bearer {token}"}
        r = await client.get(f"/api/drafts/{LID}/picks?year=2026", headers=h)
        tid = r.json()["picks"][0]["current_team_id"]
        r2 = await client.get(f"/api/teams/{tid}/draft-picks?year=2026", headers=h)
        assert r2.status_code == 200
        # All picks restricted to 2026
        assert all(p["year"] == 2026 for p in r2.json()["picks"])


# ── Frontend wiring (static) ──


FRONT = Path("/app/frontend/src")


def test_draft_room_filter_uses_current_owner():
    src = _iter171_draftroom_concat()
    # Pick map carries the current-owner abbr list
    assert "_currentOwnerAbbrs: currentAbbrs" in src
    # Iter 170e — filter now spreads livePick abbrs + column abbr into
    # a deduped set so chip clicks reliably highlight their column.
    assert "...(livePick?._currentOwnerAbbrs || []),\n                            teamAbbr,\n                          ]" in src
    assert "currentOwnerAbbrs.some((a: string) => selectedOwnerAbbrs.has(a))" in src


def test_team_draft_picks_fetches_live_data_for_object_id():
    src = (FRONT / "lovable/components/dashboard/TeamDraftPicks.tsx").read_text()
    # Object-ID regex check
    assert "/^[a-f0-9]{24}$/.test(teamId)" in src
    # Fetch endpoint
    assert "api.get(`/teams/${teamId}/draft-picks`)" in src
    # Renders the PickProvenance component on traded picks
    assert 'import PickProvenance from "@/lovable/pages/draftroom/PickProvenance"' in src
    assert "<PickProvenance tradeHistory={history} />" in src
    # Traded-pick chip + testid
    assert "ArrowRightLeft" in src
    assert "roster-pick-traded-${pick.year}-${pick.round}" in src
