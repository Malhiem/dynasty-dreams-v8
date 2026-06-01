"""Iter 125 — Trade History endpoint with A/B Executed/Vetoed split.

Coverage
--------
1. /leagues/{id}/trade-history default returns executed trades.
2. ?status=vetoed returns only vetoed rows; ?status=executed returns
   only executed rows.
3. Each row exposes from_team_*, to_team_*, veto_count, approve_count,
   voters_total, processed_at, from_assets[], to_assets[].
4. ?team_id= filter matches proposer OR target.
5. ?position= filter matches asset positions on either side; W matches
   both LW and RW.
"""
import os
import httpx
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") or "http://localhost:8001"
API = f"{BASE_URL}/api"
OWNER_EMAIL = os.environ.get("OWNER_TEST_EMAIL", "chriszarek@gmail.com")
OWNER_PW = os.environ.get("OWNER_TEST_PASSWORD", "Chris2026!")


def _login(email, password):
    r = httpx.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=10)
    return r.json().get("access_token") if r.status_code == 200 else None


def _auth(t): return {"Authorization": f"Bearer {t}"}


@pytest.fixture(scope="module")
def owner_token():
    t = _login(OWNER_EMAIL, OWNER_PW)
    assert t, "Owner login required for iter125 tests"
    return t


@pytest.fixture(scope="module")
def owner_league(owner_token):
    leagues = httpx.get(f"{API}/leagues?my_leagues=true", headers=_auth(owner_token), timeout=10).json()
    me = httpx.get(f"{API}/auth/me", headers=_auth(owner_token), timeout=10).json()
    for league in leagues:
        if league.get("commissioner_id") == me["id"]:
            return league
    return leagues[0]


def test_trade_history_default_returns_executed(owner_token, owner_league):
    r = httpx.get(
        f"{API}/leagues/{owner_league['id']}/trade-history?limit=20",
        headers=_auth(owner_token), timeout=10,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["league_id"] == owner_league["id"]
    assert body["status"] == "executed"
    assert "trades" in body
    for t in body["trades"]:
        assert t["status"] == "executed"


def test_trade_history_status_vetoed(owner_token, owner_league):
    r = httpx.get(
        f"{API}/leagues/{owner_league['id']}/trade-history?status=vetoed&limit=20",
        headers=_auth(owner_token), timeout=10,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "vetoed"
    for t in body["trades"]:
        assert t["status"] == "vetoed"


def test_trade_history_row_shape(owner_token, owner_league):
    r = httpx.get(
        f"{API}/leagues/{owner_league['id']}/trade-history?limit=5",
        headers=_auth(owner_token), timeout=10,
    )
    body = r.json()
    if not body["trades"]:
        pytest.skip("No executed trades in league")
    row = body["trades"][0]
    required = {
        "id", "status", "from_team_id", "from_team_name",
        "to_team_id", "to_team_name", "from_assets", "to_assets",
        "veto_count", "approve_count", "voters_total",
        "submitted_at", "processed_at",
    }
    missing = required - set(row.keys())
    assert not missing, f"Row missing keys: {missing}"
    assert isinstance(row["from_assets"], list)
    assert isinstance(row["to_assets"], list)
    assert isinstance(row["veto_count"], int)


def test_trade_history_team_filter(owner_token, owner_league):
    teams = httpx.get(
        f"{API}/teams?league_id={owner_league['id']}",
        headers=_auth(owner_token), timeout=10,
    ).json()
    if not teams:
        pytest.skip("No teams")
    tid = teams[0]["id"]
    r = httpx.get(
        f"{API}/leagues/{owner_league['id']}/trade-history?team_id={tid}&limit=50",
        headers=_auth(owner_token), timeout=10,
    )
    assert r.status_code == 200
    for t in r.json()["trades"]:
        assert t["from_team_id"] == tid or t["to_team_id"] == tid, (
            f"Trade {t['id']} doesn't involve team {tid}: from={t['from_team_id']} to={t['to_team_id']}"
        )


def test_trade_history_position_W_matches_LW_RW(owner_token, owner_league):
    r = httpx.get(
        f"{API}/leagues/{owner_league['id']}/trade-history?position=W&limit=50",
        headers=_auth(owner_token), timeout=10,
    )
    assert r.status_code == 200
    body = r.json()
    for t in body["trades"]:
        all_positions = set(t["from_asset_positions"]) | set(t["to_asset_positions"])
        assert any(p in {"LW", "RW", "W"} for p in all_positions), (
            f"Trade {t['id']} has no LW/RW/W asset: {all_positions}"
        )


def test_trade_history_invalid_status_falls_back_to_executed(owner_token, owner_league):
    r = httpx.get(
        f"{API}/leagues/{owner_league['id']}/trade-history?status=bogus&limit=5",
        headers=_auth(owner_token), timeout=10,
    )
    assert r.status_code == 200
    body = r.json()
    # Invalid status silently falls back to executed (matches the docstring)
    assert body["status"] == "executed"
