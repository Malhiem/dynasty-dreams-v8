"""Iter 232N.24 regression: /users/me/level shape + PATCH dashboard-layout."""
import os
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://dynasty-preview.preview.emergentagent.com").rstrip("/")

ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@e2e.dynastydreams.com")
ADMIN_PW = os.environ.get("ADMIN_PASSWORD", "e2e-admin-password")
CHRIS_EMAIL = os.environ.get("TEST_OWNER_EMAIL", "test-owner@e2e.dynastydreams.com")
CHRIS_PW = os.environ.get("TEST_OWNER_PASSWORD", "e2e-owner-password")

CHRIS_LAYOUT = [
    "pending-trades",
    "week-at-a-glance",
    "my-leagues",
    "your-activity",
    "live-scoring",
    "player-status",
    "league-movers",
    "fantasy-level",
]


def _login(email, pw):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": pw}, timeout=15)
    assert r.status_code == 200, f"login {email}: {r.status_code} {r.text}"
    return s


def test_admin_level_endpoint_shape():
    s = _login(ADMIN_EMAIL, ADMIN_PW)
    r = s.get(f"{BASE_URL}/api/users/me/level", timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    for key in ("level", "title", "xp_in_level", "xp_required_for_next", "stats"):
        assert key in data, f"missing key {key} in {data}"
    stats = data["stats"]
    for k in ("total_wins", "trades_accepted"):
        assert k in stats, f"missing stats.{k} in {stats}"
    assert isinstance(data["level"], int)
    assert isinstance(data["title"], str)


def test_chris_dashboard_layout_restore():
    s = _login(CHRIS_EMAIL, CHRIS_PW)
    r = s.patch(
        f"{BASE_URL}/api/users/me/dashboard-layout",
        json={"widget_order": CHRIS_LAYOUT},
        timeout=15,
    )
    assert r.status_code in (200, 204), r.text
    body = r.json()
    assert body.get("widget_order") == CHRIS_LAYOUT
    # Verify persistence via GET
    g = s.get(f"{BASE_URL}/api/users/me/dashboard-layout", timeout=15)
    assert g.status_code == 200
    assert g.json().get("widget_order") == CHRIS_LAYOUT
