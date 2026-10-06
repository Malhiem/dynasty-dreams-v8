"""
Iter 201b/c/d — Trade Fairness scoring + Collusion + Tanking + Lineup Audit.
"""
from __future__ import annotations

import os
import requests

from routes.trade_fairness import compute_fairness, compute_side_value, ALERT_THRESHOLD  # noqa: E402

API_URL = os.environ.get("REACT_APP_BACKEND_URL", "")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@e2e.dynastydreams.com")
ADMIN_PASS = os.environ.get("ADMIN_PASSWORD", "e2e-admin-password")


def _admin_token():
    r = requests.post(f"{API_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS})
    return r.json()["access_token"]


def _hdrs():
    return {"Authorization": f"Bearer {_admin_token()}"}


# ── Pure unit tests for trade_fairness module ──


def test_fairness_perfect_balance():
    """Two identical sides → 100% fairness, no alert."""
    trade = {
        "assets_offered": [{"asset_type": "player", "player_id": "p1"}],
        "assets_requested": [{"asset_type": "player", "player_id": "p2"}],
    }
    players = {
        "p1": {"points": 100, "age": 25, "position": "C", "salary": 5_000_000},
        "p2": {"points": 100, "age": 25, "position": "C", "salary": 5_000_000},
    }
    f = compute_fairness(trade, players)
    assert f["score"] == 100
    assert f["alert"] is False
    assert f["favored_side"] == "even"


def test_fairness_lopsided_triggers_alert():
    """100-point all-star for a 10-point depth piece → fairness < ALERT."""
    trade = {
        "assets_offered": [{"asset_type": "player", "player_id": "star"}],
        "assets_requested": [{"asset_type": "player", "player_id": "scrub"}],
    }
    players = {
        "star": {"points": 100, "age": 25, "position": "C", "salary": 10_000_000},
        "scrub": {"points": 10, "age": 35, "position": "C", "salary": 1_000_000},
    }
    f = compute_fairness(trade, players)
    assert f["score"] < ALERT_THRESHOLD
    assert f["alert"] is True
    assert f["favored_side"] == "requested"  # the receiver of the star (target) got more


def test_fairness_age_differential_signal():
    """Younger players favored in dynasty: same point total but 20yo vs 35yo
    should produce a clear age differential signal."""
    trade = {
        "assets_offered": [{"asset_type": "player", "player_id": "young"}],
        "assets_requested": [{"asset_type": "player", "player_id": "old"}],
    }
    players = {
        "young": {"points": 80, "age": 20, "position": "C"},
        "old": {"points": 80, "age": 35, "position": "C"},
    }
    f = compute_fairness(trade, players)
    assert f["age_differential"] == 15.0  # old - young
    assert f["favored_side"] == "requested"  # receiver of the young player got more


def test_fairness_position_scarcity():
    """Goalie (1.5×) > Forward (1.0×) for equivalent points."""
    trade = {
        "assets_offered": [{"asset_type": "player", "player_id": "goalie"}],
        "assets_requested": [{"asset_type": "player", "player_id": "fwd"}],
    }
    players = {
        "goalie": {"points": 60, "age": 28, "position": "G"},
        "fwd": {"points": 60, "age": 28, "position": "C"},
    }
    side_a = compute_side_value([{"asset_type": "player", "player_id": "goalie"}], players)
    side_b = compute_side_value([{"asset_type": "player", "player_id": "fwd"}], players)
    assert side_a["total"] > side_b["total"]


def test_fairness_pick_value_round_discount():
    """Round 1 pick > Round 3 pick > Round 7 pick."""
    players = {}
    sa = compute_side_value([{"asset_type": "pick", "pick_round": 1}], players)
    sb = compute_side_value([{"asset_type": "pick", "pick_round": 3}], players)
    sc = compute_side_value([{"asset_type": "pick", "pick_round": 7}], players)
    assert sa["total"] > sb["total"] > sc["total"]


def test_fairness_future_pick_discount():
    """Pick this year > pick next year > pick 2 years out."""
    players = {}
    now_val = compute_side_value([{"asset_type": "pick", "pick_round": 1, "pick_year": 2026}], players, current_year=2026)
    next_val = compute_side_value([{"asset_type": "pick", "pick_round": 1, "pick_year": 2027}], players, current_year=2026)
    far_val = compute_side_value([{"asset_type": "pick", "pick_round": 1, "pick_year": 2028}], players, current_year=2026)
    assert now_val["total"] > next_val["total"] > far_val["total"]


# ── Live integration tests for the admin endpoints ──


def test_trades_review_endpoint_returns_scored_entries():
    r = requests.get(f"{API_URL}/api/admin/platform/trades-review?limit=5", headers=_hdrs())
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["alert_threshold"] == ALERT_THRESHOLD
    for e in d["entries"]:
        assert "fairness" in e
        f = e["fairness"]
        assert "score" in f and "alert" in f and "favored_side" in f
        assert 0 <= f["score"] <= 100


def test_trades_review_sort_fairness_asc():
    r = requests.get(
        f"{API_URL}/api/admin/platform/trades-review?limit=10&sort_by=fairness_asc",
        headers=_hdrs(),
    )
    entries = r.json().get("entries", [])
    scores = [e["fairness"]["score"] for e in entries]
    assert scores == sorted(scores)


def test_trades_review_only_alerts_filter():
    r = requests.get(
        f"{API_URL}/api/admin/platform/trades-review?limit=20&only_alerts=true",
        headers=_hdrs(),
    )
    for e in r.json().get("entries", []):
        assert e["fairness"]["alert"] is True


def test_collusion_endpoint_returns_pairs():
    r = requests.get(
        f"{API_URL}/api/admin/platform/collusion-flags?min_trades=2&min_net_favor_pct=10",
        headers=_hdrs(),
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert "pairs" in d
    for p in d["pairs"]:
        assert p["trade_count"] >= 2
        assert abs(p["net_favor"]) >= 10
        assert "favored_user_id" in p


def test_tanking_endpoint_responds_200():
    r = requests.get(f"{API_URL}/api/admin/platform/tanking-flags", headers=_hdrs())
    assert r.status_code == 200
    assert "flagged" in r.json()


def test_lineup_audit_endpoint_responds_200():
    r = requests.get(f"{API_URL}/api/admin/platform/lineup-audit?limit=5", headers=_hdrs())
    assert r.status_code == 200
    d = r.json()
    assert "entries" in d and "multi_account_flags" in d


# ── Auth gating regression ──


def test_all_new_endpoints_require_admin():
    """Non-admin (no token) gets 401; non-admin user gets 403."""
    # Unauthenticated
    for path in [
        "/api/admin/platform/trades-review",
        "/api/admin/platform/collusion-flags",
        "/api/admin/platform/tanking-flags",
        "/api/admin/platform/lineup-audit",
    ]:
        r = requests.get(f"{API_URL}{path}")
        assert r.status_code == 401, f"{path} should require auth"

    # Non-admin user
    user_token = requests.post(
        f"{API_URL}/api/auth/login",
        json={"email": os.environ.get("TEST_OWNER_EMAIL", "test-owner@e2e.dynastydreams.com"), "password": os.environ.get("TEST_OWNER_PASSWORD", "e2e-owner-password")},
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {user_token}"}
    for path in [
        "/api/admin/platform/trades-review",
        "/api/admin/platform/collusion-flags",
        "/api/admin/platform/tanking-flags",
        "/api/admin/platform/lineup-audit",
    ]:
        r = requests.get(f"{API_URL}{path}", headers=headers)
        assert r.status_code == 403, f"{path} should 403 for non-admin"
