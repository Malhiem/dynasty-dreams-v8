"""
Iter 181 integration smoke tests against the live deployment.

Verifies the four backend smoke items from the review request:
  1. PUT /api/leagues/{lid} rejects oversize per-position caps with
     400 + clear "Increase {section} size first" message.
  2. PUT with valid breakdown saves & echoes back.
  3. GET /api/waivers/available?league_id=... → each player carries
     `minor_eligible` (bool) + `player_type` (str).
  4. GET /api/players?league_id=... → each player carries
     `minor_eligible` (bool).
"""
import os
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://dynasty-preview.preview.emergentagent.com").rstrip("/")
ICE_KINGS_LID = "69e46af167999bfb85c39628"

EMAIL = "chriszarek@gmail.com"
PASSWORD = "Chris2026!"


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    # Try standard login. Skip auth-gated tests if it fails.
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": EMAIL, "password": PASSWORD}, timeout=20)
    if r.status_code == 200:
        body = r.json()
        token = body.get("token") or body.get("access_token")
        if token:
            s.headers.update({"Authorization": f"Bearer {token}"})
    return s


# ── (3) Waivers payload carries minor_eligible + player_type ────────

def test_waivers_available_carries_minor_eligible_and_player_type(session):
    r = session.get(f"{BASE_URL}/api/waivers/available", params={"league_id": ICE_KINGS_LID}, timeout=30)
    assert r.status_code == 200, f"unexpected status {r.status_code}: {r.text[:300]}"
    payload = r.json()
    players = payload if isinstance(payload, list) else payload.get("players") or payload.get("data") or []
    assert isinstance(players, list) and len(players) > 0, f"no players in payload: {str(payload)[:300]}"

    for p in players[:30]:
        assert "minor_eligible" in p, f"missing minor_eligible in {p.get('name')}: keys={list(p.keys())[:15]}"
        assert isinstance(p["minor_eligible"], bool)
        assert "player_type" in p, f"missing player_type in {p.get('name')}"
        assert p["player_type"] in {"skater", "goalie", "prospect"}

    # Spot-check: at least one prospect with minor_eligible=true should
    # exist in the available pool (per review request McKenna/Misa).
    prospects = [p for p in players if p.get("player_type") == "prospect" and p.get("minor_eligible") is True]
    assert len(prospects) >= 1, "expected at least one minor-eligible prospect in /waivers/available"


# ── (4) Players directory carries minor_eligible ───────────────────

def test_players_directory_carries_minor_eligible(session):
    r = session.get(f"{BASE_URL}/api/players", params={"league_id": ICE_KINGS_LID, "limit": 50}, timeout=30)
    assert r.status_code == 200, f"unexpected status {r.status_code}: {r.text[:300]}"
    payload = r.json()
    players = payload if isinstance(payload, list) else payload.get("players") or payload.get("data") or []
    assert isinstance(players, list) and len(players) > 0
    sample = players[:30]
    for p in sample:
        assert "minor_eligible" in p, f"missing minor_eligible: keys={list(p.keys())[:15]}"
        assert isinstance(p["minor_eligible"], bool)


# ── (1) & (2) PUT /leagues/{lid} cap validation ────────────────────

def test_put_league_rejects_oversize_active_caps(session):
    """Caps sum 30 vs roster_spots 19 → 400 with the helpful message."""
    payload = {
        "roster_spots": 19,
        "position_breakdown": {"active": {"C": 25, "D": 5}},
    }
    r = session.put(f"{BASE_URL}/api/leagues/{ICE_KINGS_LID}", json=payload, timeout=20)
    if r.status_code in (401, 403):
        pytest.skip(f"auth-gated; status={r.status_code}")
    assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text[:300]}"
    detail = (r.json().get("detail") or "").lower()
    assert "active roster per-position caps sum to 30" in detail
    assert "active roster size is only 19" in detail
    assert "increase active roster size first" in detail


def test_put_league_accepts_valid_breakdown_and_echoes(session):
    """Valid breakdown that matches roster_spots → 200 + echoed back."""
    payload = {
        "roster_spots": 25,
        "position_breakdown": {"active": {"C": 4, "LW": 4, "RW": 4, "D": 6, "G": 1}},
    }
    r = session.put(f"{BASE_URL}/api/leagues/{ICE_KINGS_LID}", json=payload, timeout=20)
    if r.status_code in (401, 403):
        pytest.skip(f"auth-gated; status={r.status_code}")
    assert r.status_code == 200, f"expected 200, got {r.status_code}: {r.text[:300]}"
    body = r.json()
    # Either the league doc is returned, or a wrapper with .league.
    league = body.get("league") if isinstance(body, dict) and "league" in body else body
    assert league.get("roster_spots") == 25
    pb = league.get("position_breakdown") or {}
    active = pb.get("active") or {}
    assert active.get("C") == 4 and active.get("LW") == 4 and active.get("RW") == 4
    assert active.get("D") == 6 and active.get("G") == 1


# ── (1b) verify the bench / minors helper messages still fire ──────

def test_put_league_rejects_oversize_bench_caps(session):
    payload = {
        "bench_spots": 4,
        "position_breakdown": {"bench": {"S": 99}},
    }
    r = session.put(f"{BASE_URL}/api/leagues/{ICE_KINGS_LID}", json=payload, timeout=20)
    if r.status_code in (401, 403):
        pytest.skip(f"auth-gated; status={r.status_code}")
    assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text[:300]}"
    detail = (r.json().get("detail") or "").lower()
    assert "bench" in detail
    assert "increase" in detail and "first" in detail
