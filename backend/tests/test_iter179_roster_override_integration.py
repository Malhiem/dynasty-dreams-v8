"""
Iter 179 — Integration tests for the manual `roster_spots` override fix.

These tests hit the live API (REACT_APP_BACKEND_URL) using the commissioner
account (chriszarek@gmail.com) for the Frozen Dynasty league.

Covers:
  1. Manual roster_spots override wins (bug repro)
  2. Active-row derivation still fires when roster_spots omitted
  3. Iter-178 ceiling: minors_spots=95, taxi_squad_size=100 → 200
  4. Iter-178 bound: minors_spots=101 → 422
  5. Roundtrip: PUT then GET echoes position_breakdown shape
"""
import os
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://dynasty-preview.preview.emergentagent.com").rstrip("/")
LEAGUE_ID = "69e46af167999bfb85c3962a"
EMAIL = "chriszarek@gmail.com"
PASSWORD = "Chris2026!"


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def baseline(client):
    """Snapshot baseline league state so we can restore afterwards."""
    r = client.get(f"{BASE_URL}/api/leagues/{LEAGUE_ID}")
    assert r.status_code == 200, r.text
    d = r.json()
    snap = {
        "roster_spots": d.get("roster_spots"),
        "minors_spots": d.get("minors_spots"),
        "taxi_squad_size": d.get("taxi_squad_size"),
        "position_breakdown": d.get("position_breakdown"),
        "bench_spots": d.get("bench_spots"),
        "minors_enabled": d.get("minors_enabled"),
    }
    yield snap
    # restore — best effort
    try:
        client.put(f"{BASE_URL}/api/leagues/{LEAGUE_ID}", json={
            "roster_spots": snap["roster_spots"],
            "minors_spots": snap["minors_spots"],
            "taxi_squad_size": snap["taxi_squad_size"],
            "position_breakdown": snap["position_breakdown"],
        })
    except Exception:
        pass


def test_manual_roster_spots_wins_over_derived_active_sum(client, baseline):
    """Bug fix #1: payload {roster_spots:19, position_breakdown.active sums to 20}
    → response roster_spots must be 19 (manual wins)."""
    payload = {
        "roster_spots": 19,
        "position_breakdown": {
            "active": {"S": 18, "G": 2},
            "bench": {},
            "bench2": {},
            "minors": {},
        },
    }
    r = client.put(f"{BASE_URL}/api/leagues/{LEAGUE_ID}", json=payload)
    assert r.status_code == 200, r.text
    body = r.json()
    league = body.get("league") or body
    assert league.get("roster_spots") == 19, (
        f"manual override lost: expected 19, got {league.get('roster_spots')}; resp={body}"
    )
    # verify diff has no derived flag for roster_spots
    changes = body.get("changes") or {}
    if "roster_spots" in changes:
        assert changes["roster_spots"].get("derived") is not True, (
            f"derivation should be suppressed when manual value present: {changes}"
        )


def test_derivation_fires_when_roster_spots_omitted(client, baseline):
    """Bug fix #2: payload omits roster_spots → backend derives from active sum=20
    and emits changes.roster_spots.derived=True."""
    # first set roster_spots to something else so the diff is non-empty
    client.put(f"{BASE_URL}/api/leagues/{LEAGUE_ID}", json={"roster_spots": 15})
    payload = {
        "position_breakdown": {
            "active": {"S": 18, "G": 2},
            "bench": {},
            "bench2": {},
            "minors": {},
        },
    }
    r = client.put(f"{BASE_URL}/api/leagues/{LEAGUE_ID}", json=payload)
    assert r.status_code == 200, r.text
    body = r.json()
    league = body.get("league") or body
    assert league.get("roster_spots") == 20, (
        f"derivation broken: expected 20, got {league.get('roster_spots')}"
    )
    changes = body.get("changes") or {}
    assert "roster_spots" in changes, f"changes missing roster_spots: {changes}"
    assert changes["roster_spots"].get("derived") is True, (
        f"derived flag missing: {changes['roster_spots']}"
    )


def test_caps_accept_up_to_100(client, baseline):
    """Bug fix #3: minors_spots=95 and taxi_squad_size=100 accepted (iter-178 ceiling)."""
    payload = {"minors_spots": 95, "taxi_squad_size": 100}
    r = client.put(f"{BASE_URL}/api/leagues/{LEAGUE_ID}", json=payload)
    assert r.status_code == 200, f"status={r.status_code} body={r.text}"
    league = r.json().get("league") or r.json()
    assert league.get("minors_spots") == 95
    assert league.get("taxi_squad_size") == 100


def test_minors_spots_above_100_rejected(client, baseline):
    """Bug fix #4: minors_spots=101 → 422 (upper bound still enforced)."""
    r = client.put(f"{BASE_URL}/api/leagues/{LEAGUE_ID}", json={"minors_spots": 101})
    assert r.status_code == 422, f"expected 422, got {r.status_code}: {r.text}"


def test_taxi_squad_above_100_rejected(client, baseline):
    """Iter-178 upper bound also enforced for taxi_squad_size."""
    r = client.put(f"{BASE_URL}/api/leagues/{LEAGUE_ID}", json={"taxi_squad_size": 101})
    assert r.status_code == 422, f"expected 422, got {r.status_code}: {r.text}"


def test_roundtrip_preserves_position_breakdown_structure(client, baseline):
    """Bug fix #5: PUT then GET preserves all 4 rows of position_breakdown
    including blank `{}` placeholders."""
    payload = {
        "roster_spots": 19,
        "position_breakdown": {
            "active": {"C": 3, "LW": 3, "RW": 3, "D": 4, "G": 1},  # sum=14
            "bench": {"S": 4, "G": 1},
            "bench2": {},
            "minors": {},
        },
    }
    r = client.put(f"{BASE_URL}/api/leagues/{LEAGUE_ID}", json=payload)
    assert r.status_code == 200, r.text
    # roundtrip: GET
    g = client.get(f"{BASE_URL}/api/leagues/{LEAGUE_ID}")
    assert g.status_code == 200
    d = g.json()
    assert d["roster_spots"] == 19, f"manual roster_spots not persisted: {d['roster_spots']}"
    pb = d.get("position_breakdown") or {}
    assert pb.get("active") == {"C": 3, "LW": 3, "RW": 3, "D": 4, "G": 1}
    assert pb.get("bench") == {"S": 4, "G": 1}
    # blank rows preserved as dicts (may be {} or missing—test for shape)
    assert "bench2" in pb
    assert "minors" in pb
    assert isinstance(pb["bench2"], dict)
    assert isinstance(pb["minors"], dict)
