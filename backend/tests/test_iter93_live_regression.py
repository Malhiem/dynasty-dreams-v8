"""Iter 93 live API regression: confirm extracted trade-engine helpers work end-to-end."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://dynasty-preview.preview.emergentagent.com").rstrip("/")
LEAGUE_ID = "69e46af167999bfb85c39628"


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": "chriszarek@gmail.com", "password": "Chris2026!"})
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:300]}"
    data = r.json()
    token = data.get("access_token") or data.get("token")
    if token:
        s.headers.update({"Authorization": f"Bearer {token}"})
    return s


def test_pending_trades(session):
    r = session.get(f"{BASE_URL}/api/leagues/{LEAGUE_ID}/pending-trades")
    assert r.status_code == 200, r.text[:300]
    data = r.json()
    trades = data.get("pending_trades") if isinstance(data, dict) else data
    assert isinstance(trades, list)
    assert len(trades) >= 1, "expected at least 1 pending trade"
    print(f"pending trades count: {len(trades)}")


def test_trades_list(session):
    r = session.get(f"{BASE_URL}/api/trades", params={"league_id": LEAGUE_ID})
    assert r.status_code == 200, r.text[:300]
    assert isinstance(r.json(), list)


def test_transactions_list(session):
    r = session.get(f"{BASE_URL}/api/leagues/{LEAGUE_ID}/transactions")
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    # could be list or dict with events
    assert isinstance(body, (list, dict))


def test_evaluate_conditions(session):
    # find a conditional trade
    r = session.get(f"{BASE_URL}/api/leagues/{LEAGUE_ID}/pending-trades")
    body = r.json()
    trades = body.get("pending_trades") if isinstance(body, dict) else body
    target = None
    for t in trades:
        if not isinstance(t, dict):
            continue
        if t.get("conditional") or t.get("conditions") or t.get("trade_type") == "conditional":
            target = t
            break
    if not target and trades:
        target = trades[0] if isinstance(trades[0], dict) else None
    if not target:
        pytest.skip("no pending trade available to evaluate")
    tid = target.get("id") or target.get("_id")
    r2 = session.post(f"{BASE_URL}/api/trades/{tid}/evaluate-conditions")
    # If non-conditional trade, endpoint may return 400; conditional should be 200 with shape
    assert r2.status_code in (200, 400), f"unexpected: {r2.status_code} {r2.text[:300]}"
    if r2.status_code == 200:
        body = r2.json()
        assert "all_met" in body
        assert "results" in body
        assert isinstance(body["results"], list)
        print(f"evaluate-conditions OK: all_met={body['all_met']}, results_n={len(body['results'])}")
