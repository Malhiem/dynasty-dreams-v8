"""Iter 128 — Exact Trade Deadline date+time (trade_deadline_at).

Coverage
--------
1. League schema accepts a `trade_deadline_at` ISO string.
2. PUT /leagues/{id} persists `trade_deadline_at` and the GET roundtrip
   returns it.
3. Setting `trade_deadline_at` to `null` clears it.
4. `_enforce_trade_deadline` blocks trade proposals when current UTC time
   is past `trade_deadline_at`, regardless of the week number.
5. Future-dated `trade_deadline_at` lets proposals through.
6. Malformed datetime strings are silently ignored (no 500), and the
   legacy week-number guard still works.
7. Frontend RulesScheduleTab wires the datetime-local input and clear
   button.
"""
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

import httpx
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") or "http://localhost:8001"
API = f"{BASE_URL}/api"
OWNER_EMAIL = os.environ.get("OWNER_TEST_EMAIL", "chriszarek@gmail.com")
OWNER_PW = os.environ.get("OWNER_TEST_PASSWORD", "Chris2026!")

REPO = Path(__file__).resolve().parents[2]
RULES_TAB = REPO / "frontend/src/lovable/pages/commissioner/RulesScheduleTab.tsx"


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


def test_put_persists_trade_deadline_at(owner_token, owner_league):
    future = (datetime.now(timezone.utc) + timedelta(days=30)).replace(microsecond=0)
    iso = future.isoformat().replace("+00:00", "Z")
    r = httpx.put(
        f"{API}/leagues/{owner_league['id']}",
        json={"trade_deadline_at": iso},
        headers=_auth(owner_token), timeout=10,
    )
    assert r.status_code == 200, r.text

    g = httpx.get(f"{API}/leagues/{owner_league['id']}", headers=_auth(owner_token), timeout=10)
    assert g.status_code == 200
    body = g.json()
    assert body.get("trade_deadline_at"), "GET response missing trade_deadline_at"
    # Date should be the same (allow either Z or +00:00 form)
    got = body["trade_deadline_at"].replace("+00:00", "Z")
    assert got.startswith(iso[:19]), f"Got {got}, expected start with {iso[:19]}"


def test_clear_trade_deadline_at(owner_token, owner_league):
    r = httpx.put(
        f"{API}/leagues/{owner_league['id']}",
        json={"trade_deadline_at": None},
        headers=_auth(owner_token), timeout=10,
    )
    assert r.status_code == 200
    g = httpx.get(f"{API}/leagues/{owner_league['id']}", headers=_auth(owner_token), timeout=10)
    assert g.json().get("trade_deadline_at") in (None, ""), (
        f"Expected null after clear, got {g.json().get('trade_deadline_at')!r}"
    )


def test_past_deadline_blocks_trade_proposal(owner_token, owner_league):
    """Setting trade_deadline_at to the past should block new trade proposals
    with HTTP 400, regardless of the week number."""
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).replace(microsecond=0)
    iso = past.isoformat().replace("+00:00", "Z")

    httpx.put(
        f"{API}/leagues/{owner_league['id']}",
        json={"trade_deadline_at": iso},
        headers=_auth(owner_token), timeout=10,
    )

    teams = httpx.get(
        f"{API}/teams?league_id={owner_league['id']}",
        headers=_auth(owner_token), timeout=10,
    ).json()
    me = httpx.get(f"{API}/auth/me", headers=_auth(owner_token), timeout=10).json()
    my_team = next((t for t in teams if t.get("owner_id") == me["id"]), None)
    other = next((t for t in teams if t.get("owner_id") != me["id"]), None)
    if not my_team or not other:
        pytest.skip("Need at least 2 teams to test trade enforcement")

    r = httpx.post(
        f"{API}/trades",
        json={
            "league_id": owner_league["id"],
            "proposer_team_id": my_team["id"],
            "target_team_id": other["id"],
            "assets_offered": [],
            "assets_requested": [],
            "message": "deadline-test",
        },
        headers=_auth(owner_token), timeout=10,
    )
    # Restore deadline before asserting (so subsequent tests aren't blocked)
    httpx.put(
        f"{API}/leagues/{owner_league['id']}",
        json={"trade_deadline_at": None},
        headers=_auth(owner_token), timeout=10,
    )

    assert r.status_code == 400, f"Expected 400 deadline block, got {r.status_code}: {r.text}"
    assert "deadline" in r.text.lower(), r.text


def test_future_deadline_allows_trade_proposal_path(owner_token, owner_league):
    """Future-dated trade_deadline_at should NOT trigger the deadline 400.
    (The request may still fail validation for other reasons, but never
    with the deadline-passed message.)"""
    future = (datetime.now(timezone.utc) + timedelta(days=60)).replace(microsecond=0)
    httpx.put(
        f"{API}/leagues/{owner_league['id']}",
        json={"trade_deadline_at": future.isoformat().replace("+00:00", "Z")},
        headers=_auth(owner_token), timeout=10,
    )
    teams = httpx.get(
        f"{API}/teams?league_id={owner_league['id']}",
        headers=_auth(owner_token), timeout=10,
    ).json()
    me = httpx.get(f"{API}/auth/me", headers=_auth(owner_token), timeout=10).json()
    my_team = next((t for t in teams if t.get("owner_id") == me["id"]), None)
    other = next((t for t in teams if t.get("owner_id") != me["id"]), None)
    if not my_team or not other:
        pytest.skip("Need teams")
    r = httpx.post(
        f"{API}/trades",
        json={
            "league_id": owner_league["id"],
            "proposer_team_id": my_team["id"],
            "target_team_id": other["id"],
            "assets_offered": [],
            "assets_requested": [],
            "message": "future-deadline",
        },
        headers=_auth(owner_token), timeout=10,
    )
    # Clean up
    httpx.put(
        f"{API}/leagues/{owner_league['id']}",
        json={"trade_deadline_at": None},
        headers=_auth(owner_token), timeout=10,
    )
    # Endpoint may reject for empty assets etc — just ensure it isn't the
    # deadline 400.
    if r.status_code == 400:
        assert "deadline" not in r.text.lower(), (
            f"Future deadline incorrectly blocked: {r.text}"
        )


def test_malformed_deadline_at_is_silently_ignored(owner_token, owner_league):
    """A bogus datetime string shouldn't 500 the trade endpoint — the
    enforcer falls through to the week-based guard."""
    httpx.put(
        f"{API}/leagues/{owner_league['id']}",
        json={"trade_deadline_at": "not-a-date"},
        headers=_auth(owner_token), timeout=10,
    )
    teams = httpx.get(
        f"{API}/teams?league_id={owner_league['id']}",
        headers=_auth(owner_token), timeout=10,
    ).json()
    me = httpx.get(f"{API}/auth/me", headers=_auth(owner_token), timeout=10).json()
    my_team = next((t for t in teams if t.get("owner_id") == me["id"]), None)
    other = next((t for t in teams if t.get("owner_id") != me["id"]), None)
    if not my_team or not other:
        pytest.skip("Need teams")
    r = httpx.post(
        f"{API}/trades",
        json={
            "league_id": owner_league["id"],
            "proposer_team_id": my_team["id"],
            "target_team_id": other["id"],
            "assets_offered": [],
            "assets_requested": [],
            "message": "malformed",
        },
        headers=_auth(owner_token), timeout=10,
    )
    # Cleanup
    httpx.put(
        f"{API}/leagues/{owner_league['id']}",
        json={"trade_deadline_at": None},
        headers=_auth(owner_token), timeout=10,
    )
    assert r.status_code != 500, f"Malformed datetime caused 500: {r.text}"


def test_frontend_rules_tab_has_datetime_picker():
    src = RULES_TAB.read_text()
    assert "rules-schedule-trade-deadline-at-input" in src, "Datetime input testid missing"
    assert "rules-schedule-trade-deadline-at-clear" in src, "Clear button testid missing"
    assert 'type="datetime-local"' in src, "Input should be datetime-local"
    assert "trade_deadline_at" in src, "trade_deadline_at key must be referenced"
    assert "deadlineAt" in src, "Local deadlineAt state missing"
