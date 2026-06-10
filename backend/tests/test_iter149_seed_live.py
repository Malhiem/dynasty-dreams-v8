"""Iter 149 — Live HTTP integration test for seed endpoint + trade-block on the preview URL."""
import os
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # Read frontend .env directly
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL"):
                BASE_URL = line.split("=", 1)[1].strip().strip('"').rstrip("/")
                break

ADMIN_EMAIL = "admin@dynastydreams.com"
ADMIN_PASS = "Admin123!"


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=15)
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text}"
    body = r.json()
    tok = body.get("access_token") or body.get("token")
    if tok:
        s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


@pytest.fixture(scope="module")
def league_id(admin_session):
    r = admin_session.get(f"{BASE_URL}/api/leagues?my_leagues=true", timeout=15)
    assert r.status_code == 200, f"Get leagues failed: {r.status_code} {r.text}"
    data = r.json()
    leagues = data if isinstance(data, list) else data.get("items") or data.get("leagues") or []
    assert leagues, f"No leagues found for admin: {data}"
    return leagues[0]["id"]


def test_seed_pending_trade_endpoint_creates_three_trades(admin_session, league_id):
    r = admin_session.post(
        f"{BASE_URL}/api/admin/seed/pending-trade",
        json={"league_id": league_id},
        timeout=30,
    )
    assert r.status_code == 200, f"seed/pending-trade failed: {r.status_code} {r.text}"
    body = r.json()
    assert body.get("league_id") == league_id
    assert "proposer_team" in body and "target_team" in body
    trades = body.get("trades") or {}
    assert set(trades.keys()) >= {"pending", "vetoed", "executed"}, f"Missing keys: {trades}"
    for k in ("pending", "vetoed", "executed"):
        assert isinstance(trades[k], str) and len(trades[k]) >= 10, f"Bad ObjectId for {k}: {trades[k]}"

    # Verify the trades exist with correct statuses on /api/trades
    r2 = admin_session.get(f"{BASE_URL}/api/trades?league_id={league_id}", timeout=15)
    assert r2.status_code == 200, f"GET trades failed: {r2.status_code} {r2.text}"
    items = r2.json() if isinstance(r2.json(), list) else r2.json().get("items") or r2.json().get("trades") or []
    by_id = {t.get("id") or t.get("_id"): t for t in items}
    for status_key, trade_id in trades.items():
        assert trade_id in by_id, f"Seeded trade {status_key}={trade_id} not in /api/trades list"
        actual_status = (by_id[trade_id].get("status") or "").lower()
        if status_key == "executed":
            assert actual_status in ("executed", "processed"), f"executed trade has status={actual_status}"
        else:
            assert actual_status == status_key, f"{status_key} trade has status={actual_status}"


def test_seed_pending_trade_endpoint_forbidden_for_non_admin(league_id):
    """Non-admin (or anonymous) user should get 401/403."""
    s = requests.Session()
    # Try anonymous first
    r = s.post(f"{BASE_URL}/api/admin/seed/pending-trade", json={"league_id": league_id}, timeout=15)
    assert r.status_code in (401, 403), f"Anonymous should be denied, got {r.status_code}"

    # Try to register/login a non-admin to verify 403 specifically
    import uuid
    email = f"qa_iter149_{uuid.uuid4().hex[:8]}@example.com"
    reg = s.post(f"{BASE_URL}/api/auth/register", json={"email": email, "password": "TestPass123!", "full_name": "QA 149"}, timeout=15)
    if reg.status_code in (200, 201):
        body = reg.json()
        tok = body.get("access_token") or body.get("token")
        if tok:
            s.headers.update({"Authorization": f"Bearer {tok}"})
        r2 = s.post(f"{BASE_URL}/api/admin/seed/pending-trade", json={"league_id": league_id}, timeout=15)
        assert r2.status_code == 403, f"Non-admin should get 403, got {r2.status_code} {r2.text}"


def test_trade_block_endpoint_lists_items(admin_session, league_id):
    r = admin_session.get(f"{BASE_URL}/api/trade-block?league_id={league_id}", timeout=15)
    assert r.status_code == 200, f"GET /api/trade-block failed: {r.status_code} {r.text}"
    items = r.json() if isinstance(r.json(), list) else r.json().get("items") or []
    # Sanity: items should be a list (may be empty)
    assert isinstance(items, list)
    print(f"Trade block items count: {len(items)}")
