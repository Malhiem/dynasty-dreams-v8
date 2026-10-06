"""Iter 232N.27 — E2E API tests for /api/drafts/{id}/leaderboard against the live backend."""
from __future__ import annotations

from tests.legacy_draft_fixture import legacy_draft_inputs
import os
import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://dynasty-preview.preview.emergentagent.com").rstrip("/")
DRAFT_ID = "6a408dbdd93ed14d3a8fb393"  # completed draft (10 auto picks)
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@e2e.dynastydreams.com")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "e2e-admin-password")


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=15)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
    body = r.json()
    tok = body.get("token") or body.get("access_token")
    if tok:
        s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


def test_requires_auth():
    r = requests.get(f"{BASE}/api/drafts/{DRAFT_ID}/leaderboard", timeout=10)
    assert r.status_code == 401, f"expected 401 unauthenticated; got {r.status_code} — {r.text[:200]}"


def test_unknown_draft_returns_404(session):
    r = session.get(f"{BASE}/api/drafts/000000000000000000000000/leaderboard", timeout=10)
    assert r.status_code == 404


def test_leaderboard_shape(session):
    r = session.get(f"{BASE}/api/drafts/{DRAFT_ID}/leaderboard", timeout=15)
    assert r.status_code == 200, f"got {r.status_code} — {r.text[:300]}"
    data = r.json()
    for key in ("draft_id", "league_id", "is_final", "total_picks", "auto_picks_total", "rows", "awards"):
        assert key in data, f"missing key: {key}"
    assert isinstance(data["rows"], list)
    assert isinstance(data["awards"], dict)
    assert data["draft_id"] == DRAFT_ID
