"""Iter 116 — verify the /api/admin/health-deep endpoint.

Coverage:
  • Anonymous → 401
  • Non-admin user → 403
  • Admin → 200 with the expected envelope (service / database / workers / routes)
  • Hitting an endpoint then re-reading health-deep shows the bucket count incrementing
"""
import os
import secrets

import httpx
import pytest


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") or "http://localhost:8001"
API = f"{BASE_URL}/api"
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", os.environ.get("ADMIN_EMAIL", "admin@e2e.dynastydreams.com"))
ADMIN_PW = os.environ.get("ADMIN_PASSWORD", os.environ.get("ADMIN_PASSWORD", "e2e-admin-password"))


def _login(email: str, password: str) -> str | None:
    r = httpx.post(f"{API}/auth/login",
                   json={"email": email, "password": password},
                   timeout=10)
    if r.status_code != 200:
        return None
    return r.json().get("access_token")


@pytest.fixture(scope="module")
def admin_token():
    tok = _login(ADMIN_EMAIL, ADMIN_PW)
    if not tok:
        pytest.skip("admin login unavailable")
    return tok


@pytest.fixture(scope="module")
def non_admin_token():
    """Register a throwaway user so we can assert site-admin enforcement."""
    suffix = secrets.token_hex(4)
    email = f"ironhealth_{suffix}@example.com"
    pw = f"Iron-{suffix}-Heath!1"
    r = httpx.post(f"{API}/auth/register",
                   json={"email": email, "password": pw, "username": f"u{suffix}"},
                   timeout=10)
    if r.status_code not in (200, 201):
        pytest.skip(f"register failed: {r.status_code} {r.text}")
    tok = r.json().get("access_token")
    if not tok:
        tok = _login(email, pw)
    if not tok:
        pytest.skip("login post-register failed")
    return tok


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_health_deep_requires_auth():
    r = httpx.get(f"{API}/admin/health-deep", timeout=10)
    assert r.status_code == 401, r.text


def test_health_deep_rejects_non_admin(non_admin_token):
    r = httpx.get(f"{API}/admin/health-deep",
                  headers=_auth(non_admin_token), timeout=10)
    assert r.status_code == 403, r.text


def test_health_deep_envelope_for_admin(admin_token):
    r = httpx.get(f"{API}/admin/health-deep?top=10",
                  headers=_auth(admin_token), timeout=10)
    assert r.status_code == 200, r.text
    body = r.json()
    for top_key in ("ok", "checked_at", "service", "database", "workers", "routes"):
        assert top_key in body, f"missing {top_key}"

    svc = body["service"]
    for k in ("started_at", "uptime_seconds", "total_requests",
              "total_errors", "error_rate_pct"):
        assert k in svc, f"service missing {k}"

    db = body["database"]
    assert db["alive"] is True
    assert isinstance(db["ping_ms"], (int, float))
    assert db["ping_ms"] >= 0

    wk = body["workers"]
    for w in ("live_scoring", "ownership_snapshot", "tbd_deadline"):
        assert w in wk, f"workers missing {w}"

    assert isinstance(body["routes"], list)
    # The health-deep endpoint itself MUST be in the metrics by the time it
    # returns (the middleware records on the way out, but at least one prior
    # successful call from earlier tests should be in the snapshot).
    if body["routes"]:
        row = body["routes"][0]
        for k in ("method", "route", "count", "error_count",
                  "avg_latency_ms", "p50_latency_ms", "p95_latency_ms",
                  "max_latency_ms", "last_status", "last_seen_at"):
            assert k in row, f"row missing {k}"


def test_health_deep_tracks_new_traffic(admin_token):
    """Hit /api/sports a few times, then verify its count moved up."""
    # Baseline
    r0 = httpx.get(f"{API}/admin/health-deep?top=200",
                   headers=_auth(admin_token), timeout=10)
    assert r0.status_code == 200
    base_count = next(
        (row["count"] for row in r0.json()["routes"]
         if row["route"] == "/api/sports" and row["method"] == "GET"),
        0,
    )

    # Hit /api/sports 3 times
    for _ in range(3):
        httpx.get(f"{API}/sports", timeout=10)

    r1 = httpx.get(f"{API}/admin/health-deep?top=200",
                   headers=_auth(admin_token), timeout=10)
    assert r1.status_code == 200
    new_count = next(
        (row["count"] for row in r1.json()["routes"]
         if row["route"] == "/api/sports" and row["method"] == "GET"),
        0,
    )
    assert new_count >= base_count + 3, f"expected ≥ {base_count + 3}, got {new_count}"


def test_health_deep_buckets_dynamic_paths_by_template(admin_token):
    """Calls to /api/leagues/{id}/premium with different ids should
    collapse into ONE bucket keyed by the route template, not many."""
    # Pick a league id to hit twice and an obviously-bogus one to hit twice;
    # both share the route template /api/leagues/{league_id}/premium.
    leagues = httpx.get(f"{API}/leagues?public=true",
                       headers=_auth(admin_token), timeout=10)
    if leagues.status_code != 200 or not (leagues.json() or []):
        pytest.skip("no leagues to probe")
    real_id = leagues.json()[0]["id"]

    for lid in (real_id, real_id, "000000000000000000000000"):
        httpx.get(f"{API}/leagues/{lid}/premium",
                  headers=_auth(admin_token), timeout=10)

    r = httpx.get(f"{API}/admin/health-deep?top=200",
                  headers=_auth(admin_token), timeout=10)
    assert r.status_code == 200
    # Should be exactly ONE row for the template path
    matching = [row for row in r.json()["routes"]
                if row["route"] == "/api/leagues/{league_id}/premium"
                and row["method"] == "GET"]
    assert len(matching) == 1, f"expected one template bucket, got {len(matching)}: {matching}"
    assert matching[0]["count"] >= 3
