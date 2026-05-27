"""Iter 115 — verify extracted routes still resolve correctly after the
final batch of server.py modularisation. We don't reach into deep business
state; we just confirm the moved endpoints respond from their new homes
with the expected shape.

Routes verified:
- GET  /api/sports                      → routes/sports.py
- GET  /api/recommendations/leagues     → routes/recommendations.py
- GET  /api/leagues/{id}/premium        → routes/payments.py
- GET  /api/leagues/{id}/pending-trades → routes/trades.py
- POST /api/admin/snapshot-ownership    → routes/admin.py (403 for non-admin
                                          is enough proof the route is wired)
"""
import os
import pytest
import httpx


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") or "http://localhost:8001"
API = f"{BASE_URL}/api"

ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@dynastydreams.com")
ADMIN_PW = os.environ.get("ADMIN_PASSWORD", "Admin123!")


@pytest.fixture(scope="module")
def admin_token():
    r = httpx.post(f"{API}/auth/login",
                   json={"email": ADMIN_EMAIL, "password": ADMIN_PW},
                   timeout=10)
    if r.status_code != 200:
        pytest.skip(f"admin login unavailable: {r.status_code}")
    return r.json().get("access_token")


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_sports_endpoint_resolves():
    r = httpx.get(f"{API}/sports", timeout=10)
    assert r.status_code == 200, r.text
    data = r.json()
    ids = {s["id"] for s in data}
    assert "nhl" in ids and "nfl" in ids and "nba" in ids and "mlb" in ids
    nhl = next(s for s in data if s["id"] == "nhl")
    assert nhl["active"] is True
    assert nhl["player_count"] >= 0


def test_recommendations_endpoint_resolves(admin_token):
    r = httpx.get(f"{API}/recommendations/leagues?limit=3",
                  headers=_auth(admin_token), timeout=10)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "recommendations" in data and "has_active_leagues" in data
    assert "preferences" in data
    for rec in data["recommendations"]:
        assert "id" in rec and "name" in rec and "match_score" in rec


def test_league_premium_endpoint_resolves(admin_token):
    # Find any league to query premium status against. If the test DB has
    # zero leagues, skip — extraction proof is the 404 path below.
    r = httpx.get(f"{API}/leagues?owner_id=any&public=true", headers=_auth(admin_token), timeout=10)
    if r.status_code != 200 or not (r.json() or []):
        # Try an obviously-bad id to prove the route is wired
        r404 = httpx.get(f"{API}/leagues/000000000000000000000000/premium",
                         headers=_auth(admin_token), timeout=10)
        # Either 404 (route hit, league missing) or 400 (invalid id) — both
        # prove the endpoint is reachable.
        assert r404.status_code in (400, 404), r404.text
        return
    league_id = r.json()[0]["id"]
    r = httpx.get(f"{API}/leagues/{league_id}/premium",
                  headers=_auth(admin_token), timeout=10)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["league_id"] == league_id
    assert "premium" in body and "features" in body and "price_usd" in body


def test_pending_trades_endpoint_resolves(admin_token):
    # Same approach — any league id will do; the endpoint always returns
    # an empty list rather than 404 if league has no trades.
    r = httpx.get(f"{API}/leagues?public=true", headers=_auth(admin_token), timeout=10)
    if r.status_code != 200 or not (r.json() or []):
        pytest.skip("no leagues in test DB")
    league_id = r.json()[0]["id"]
    r = httpx.get(f"{API}/leagues/{league_id}/pending-trades",
                  headers=_auth(admin_token), timeout=10)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["league_id"] == league_id
    assert isinstance(body["pending_trades"], list)
    assert "count" in body


def test_admin_snapshot_ownership_wired(admin_token):
    # The admin endpoint is gated to ADMIN_EMAIL. Logged-in admin should
    # succeed; if env's ADMIN_EMAIL differs from logged-in user we get 403
    # (still proves the route is wired through the new admin router).
    r = httpx.post(f"{API}/admin/snapshot-ownership",
                   headers=_auth(admin_token), timeout=20)
    assert r.status_code in (200, 403), r.text
