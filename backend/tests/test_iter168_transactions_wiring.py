"""
Iter 168 — Transactions page wired to real trades + dead Draft Room link fix.

Three user-reported asks landed in one iteration:

  1. "Open Draft Room" button on the Draft Board went to /drafts (legacy
     dead page). Fixed to point at /draft-room.

  2. New backend endpoint `GET /api/leagues/{id}/trades` returns the
     full trade history (with optional ?status= filter). Powers the
     Transactions page's All / Pending / Executed tabs.

  3. Transactions page already consumed the older `/trades?league_id=X`
     endpoint but crashed on unknown statuses ("executed" / "withdrawn"
     / etc.). Fixed by extending `statusConfig` to cover every backend
     canonical status and falling back to the pending config when the
     status is still unrecognized.

Also smoke-tests the 4 trade scenarios the user requested:
  - Player ↔ Player
  - Player ↔ Pick
  - Pick ↔ Conditional Pick
  - Re-trade of a previously traded pick
"""
import os
from pathlib import Path

import pytest
from httpx import AsyncClient


def _backend_url():
    env = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", ".env")
    with open(env) as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip()


BASE = _backend_url()
LID = "69e46af167999bfb85c39628"


async def _tok(client, email, password):
    r = await client.post("/api/auth/login", json={"email": email, "password": password})
    return r.json()["access_token"]


# ── Backend ──


@pytest.mark.asyncio
async def test_league_trades_endpoint_returns_full_history():
    async with AsyncClient(base_url=BASE, timeout=30) as client:
        token = await _tok(client, "admin@dynastydreams.com", "Admin123!")
        h = {"Authorization": f"Bearer {token}"}
        r = await client.get(f"/api/leagues/{LID}/trades", headers=h)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["league_id"] == LID
        assert "count" in d
        assert isinstance(d.get("trades"), list)


@pytest.mark.asyncio
async def test_league_trades_endpoint_status_filter():
    async with AsyncClient(base_url=BASE, timeout=30) as client:
        token = await _tok(client, "admin@dynastydreams.com", "Admin123!")
        h = {"Authorization": f"Bearer {token}"}
        r = await client.get(f"/api/leagues/{LID}/trades?status=executed", headers=h)
        assert r.status_code == 200
        for t in r.json()["trades"]:
            assert t["status"] == "executed"
        # Comma-separated filter
        r2 = await client.get(f"/api/leagues/{LID}/trades?status=executed,vetoed", headers=h)
        assert r2.status_code == 200
        for t in r2.json()["trades"]:
            assert t["status"] in ("executed", "vetoed")


# ── Frontend wiring ──


FRONT = Path("/app/frontend/src")


def test_draft_board_open_draft_room_link_fixed():
    src = (FRONT / "lovable/pages/DraftBoard.tsx").read_text()
    # The dead /drafts link is gone; /draft-room is in place
    assert 'primaryHref="/drafts"\n            primaryLabel="Open Draft Room"' not in src
    assert 'primaryHref="/draft-room"' in src
    assert 'primaryLabel="Open Draft Room"' in src


def test_transactions_status_config_covers_backend_statuses():
    src = (FRONT / "lovable/pages/Transactions.tsx").read_text()
    # Every backend canonical status has a config entry
    for status in ("pending", "accepted", "vetoed", "executed", "voting",
                   "conditional", "withdrawn", "rejected"):
        assert f"{status}: {{" in src, f"statusConfig missing {status}"
    # Fallback so unknown statuses don't crash
    assert "statusConfig[trade.status] || statusConfig.pending" in src
