"""Tests for GET /api/leagues/{id}/transactions — limit / since / team_id filters."""
import os
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # try frontend/.env
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL"):
                    BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
                    break
    except Exception:
        pass

LEAGUE_ID = "69e46af167999bfb85c39628"
TXN_URL = f"{BASE_URL}/api/leagues/{LEAGUE_ID}/transactions"


@pytest.fixture(scope="module")
def one_team_id():
    r = requests.get(f"{BASE_URL}/api/teams?league_id={LEAGUE_ID}", timeout=30)
    assert r.status_code == 200, r.text
    teams = r.json()
    assert isinstance(teams, list) and teams, "expected teams for league"
    return teams[0]["id"]


def test_default_limit_backcompat():
    """Regression: default limit=30, response has old shape (league_id, transactions, count)."""
    r = requests.get(TXN_URL, timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "transactions" in data and "count" in data and "league_id" in data
    assert data["league_id"] == LEAGUE_ID
    assert isinstance(data["transactions"], list)
    assert data["count"] == len(data["transactions"])
    assert len(data["transactions"]) <= 30


def test_limit_20_returns_at_most_20():
    r = requests.get(TXN_URL, params={"limit": 20}, timeout=30)
    assert r.status_code == 200
    data = r.json()
    assert len(data["transactions"]) <= 20
    assert data["count"] == len(data["transactions"])


def test_since_filter_applied():
    """since cutoff — all returned events must be >= the cutoff."""
    cutoff_iso = "2026-04-25T00:00:00Z"
    r = requests.get(TXN_URL, params={"since": cutoff_iso, "limit": 200}, timeout=30)
    assert r.status_code == 200
    data = r.json()
    from datetime import datetime, timezone
    cutoff = datetime.fromisoformat(cutoff_iso.replace("Z", "+00:00"))
    for tx in data["transactions"]:
        ts = tx.get("created_at")
        if not ts:
            continue
        if isinstance(ts, str):
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        else:
            dt = ts
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        assert dt >= cutoff, f"event {tx.get('id')} created_at {ts} is before cutoff"


def test_team_id_filter(one_team_id):
    r = requests.get(TXN_URL, params={"team_id": one_team_id, "limit": 200}, timeout=30)
    assert r.status_code == 200
    data = r.json()
    # Every returned event must be tagged with that team_id
    for tx in data["transactions"]:
        assert tx.get("team_id") == one_team_id, (
            f"event {tx.get('id')} has team_id={tx.get('team_id')} but expected {one_team_id}"
        )


def test_combined_filters(one_team_id):
    r = requests.get(
        TXN_URL,
        params={"limit": 200, "since": "2025-01-01T00:00:00Z", "team_id": one_team_id},
        timeout=30,
    )
    assert r.status_code == 200
    data = r.json()
    assert len(data["transactions"]) <= 200
    for tx in data["transactions"]:
        assert tx.get("team_id") == one_team_id


def test_no_empty_pending_trades_zarek_icebreakers():
    """Verify the 47 empty trades between Zarek's Frozen and Ice Breakers were cleaned."""
    r = requests.get(f"{BASE_URL}/api/leagues/{LEAGUE_ID}/pending-trades", timeout=30)
    assert r.status_code == 200
    data = r.json()
    trades = data.get("pending_trades", [])
    zarek_ice_empty = []
    for t in trades:
        parties = t.get("parties") or []
        party_names = {p.get("team_name", "") for p in parties}
        # Only flag 2-party Zarek<->Ice Breakers trades that are empty
        if "Zarek's Frozen" in party_names and "Ice Breakers" in party_names and len(parties) == 2:
            all_empty = True
            for p in parties:
                sends = p.get("sends") or p.get("giving_player_ids") or p.get("giving_pick_ids") or []
                if sends:
                    all_empty = False
                    break
            if all_empty:
                zarek_ice_empty.append(t.get("_id"))
    assert len(zarek_ice_empty) == 0, (
        f"Found {len(zarek_ice_empty)} empty Zarek<->IceBreakers trades: {zarek_ice_empty}"
    )
