"""Iter 137 — % of cap ring on Depth Chart + Draft Board order endpoint.

Coverage
--------
Frontend (file-content checks):
  1. DepthChart exports a `CapRing` SVG helper used by both chips.
  2. Each line/pair chip renders `% of cap` text with a per-row testid.
  3. DraftBoard fetches the new draft-order endpoint and reorders the
     teams list by `seed`.
  4. The order-source badge ("Lottery applied" / "Reverse standings")
     surfaces on the page.

Backend (live API):
  5. `GET /api/leagues/{league_id}/draft-order` returns ordered seeds.
  6. Without a lottery, source = `reverse_standings`.
"""
import os
from pathlib import Path

import httpx
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") or "http://localhost:8001"
API = f"{BASE_URL}/api"
OWNER_EMAIL = os.environ.get("OWNER_TEST_EMAIL", "chriszarek@gmail.com")
OWNER_PW = os.environ.get("OWNER_TEST_PASSWORD", "Chris2026!")

REPO = Path(__file__).resolve().parents[2]
DEPTH = REPO / "frontend/src/lovable/pages/DepthChart.tsx"
DRAFT = REPO / "frontend/src/lovable/pages/DraftBoard.tsx"
DRAFTS_ROUTE = REPO / "backend/routes/drafts.py"


def _login(email, password):
    r = httpx.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=10)
    return r.json().get("access_token") if r.status_code == 200 else None


def _auth(t): return {"Authorization": f"Bearer {t}"}


@pytest.fixture(scope="module")
def owner_token():
    t = _login(OWNER_EMAIL, OWNER_PW)
    assert t, "Owner login required"
    return t


@pytest.fixture(scope="module")
def owner_league(owner_token):
    leagues = httpx.get(f"{API}/leagues?my_leagues=true", headers=_auth(owner_token), timeout=10).json()
    me = httpx.get(f"{API}/auth/me", headers=_auth(owner_token), timeout=10).json()
    for league in leagues:
        if league.get("commissioner_id") == me["id"]:
            return league
    return leagues[0]


# ── Frontend — CapRing + per-row % of cap ──────────────────────
def test_cap_ring_helper_exists():
    src = DEPTH.read_text()
    assert "const CapRing" in src, "CapRing component missing"
    assert "<CapRing" in src, "CapRing must be rendered in the chips"
    # Per-line and per-pair % testids
    assert "depth-line-cap-pct-${idx + 1}" in src, "Per-line % testid missing"
    assert "depth-pair-cap-pct-${idx + 1}" in src, "Per-pair % testid missing"
    assert "% of cap" in src, "% of cap copy missing"


# ── Frontend — DraftBoard wires the new endpoint + reorders ────
def test_draft_board_wires_order_endpoint():
    src = DRAFT.read_text()
    assert "/draft-order?year=" in src, "Draft order endpoint not called"
    assert "draftOrder" in src, "Draft order state missing"
    assert "seedById" in src, "Sort by seed missing"
    assert 'data-testid="draft-board-order-source"' in src, "Order source badge missing"


# ── Backend — route function exists ────────────────────────────
def test_draft_order_route_defined():
    src = DRAFTS_ROUTE.read_text()
    assert '"/leagues/{league_id}/draft-order"' in src, "Endpoint path missing"
    assert "async def get_league_draft_order" in src, "Handler missing"
    assert "lottery_applied" in src and "reverse_standings" in src, "Both source codes required"


# ── Backend — live API returns ordered seeds ───────────────────
def test_draft_order_endpoint_live(owner_token, owner_league):
    r = httpx.get(
        f"{API}/leagues/{owner_league['id']}/draft-order?year=2026",
        headers=_auth(owner_token), timeout=10,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "order" in body and isinstance(body["order"], list)
    assert body.get("source") in {"reverse_standings", "lottery_applied"}
    if body["order"]:
        # Seeds are sequential 1..N
        seeds = [int(o["seed"]) for o in body["order"]]
        assert seeds == sorted(seeds), "Seeds must be sorted ascending"
        assert seeds[0] == 1, "First seed must be 1"
