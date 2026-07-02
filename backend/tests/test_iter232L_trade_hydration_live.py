"""Iter 232L — Live-API integration tests for trade asset hydration.

Verifies the 4 endpoints exposed to the Transactions page all return
hydrated player assets (age, cap_hit, salary, fantasy_points, FP/G,
games_played, stat_categories, player_type) plus trade.scoring_categories
{skater,goalie} — using the real preview backend.

Target league: TFHL 6a3a0781a842ea2f7bcdc7cb (chriszarek@gmail.com has a
pending McDavid trade there).
"""
from __future__ import annotations

import os

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://dynasty-preview.preview.emergentagent.com").rstrip("/")
LEAGUE_ID = "6a3a0781a842ea2f7bcdc7cb"  # TFHL — has pending McDavid trade
COMMISSIONER_EMAIL = "chriszarek@gmail.com"
COMMISSIONER_PW = "Chris2026!"


@pytest.fixture(scope="module")
def token() -> str:
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": COMMISSIONER_EMAIL, "password": COMMISSIONER_PW},
        timeout=30,
    )
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text[:200]}"
    tok = r.json().get("token") or r.json().get("access_token")
    assert tok, f"No token: {r.json()}"
    return tok


@pytest.fixture(scope="module")
def auth_headers(token) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _assert_scoring_categories(trade: dict):
    cats = trade.get("scoring_categories")
    assert isinstance(cats, dict), f"scoring_categories missing: {list(trade.keys())}"
    assert "skater" in cats and "goalie" in cats
    assert isinstance(cats["skater"], list) and len(cats["skater"]) >= 3
    for c in cats["skater"]:
        assert "key" in c and "label" in c
    # Label mapping sanity: 'goals' -> 'G'
    skater_keys = {c["key"]: c["label"] for c in cats["skater"]}
    if "goals" in skater_keys:
        assert skater_keys["goals"] == "G"
    if "plus_minus" in skater_keys:
        assert skater_keys["plus_minus"] == "+/-"


def _assert_player_asset_hydrated(a: dict, ctx: str):
    # Skip pick assets
    if a.get("asset_type") == "pick" or a.get("item_type") == "pick":
        # Picks should NOT have player fantasy fields
        assert not a.get("fantasy_points"), f"{ctx}: pick has fantasy_points"
        return
    if not a.get("player_id"):
        return  # not a player asset
    assert a.get("age") and int(a["age"]) > 0, f"{ctx}: age not populated: {a.get('age')} player={a.get('player_name')}"
    assert a.get("cap_hit") and float(a["cap_hit"]) > 0, f"{ctx}: cap_hit blank/zero: {a.get('cap_hit')}"
    assert a.get("salary") == a.get("cap_hit"), f"{ctx}: salary!=cap_hit"
    assert "fantasy_points" in a, f"{ctx}: fantasy_points missing"
    assert "fantasy_points_per_game" in a, f"{ctx}: fp_per_game missing"
    assert "games_played" in a, f"{ctx}: games_played missing"
    assert isinstance(a.get("stat_categories"), dict) and len(a["stat_categories"]) > 0, f"{ctx}: stat_categories empty"
    # each stat_category value has {label, value}
    for k, v in a["stat_categories"].items():
        assert "label" in v and "value" in v, f"{ctx}: stat_categories[{k}] shape wrong: {v}"
    assert a.get("player_type") in ("skater", "goalie"), f"{ctx}: player_type invalid: {a.get('player_type')}"


def _walk_trade_assets(trade: dict, ctx: str):
    for side in ("assets_offered", "assets_requested"):
        for i, a in enumerate(trade.get(side) or []):
            _assert_player_asset_hydrated(a, f"{ctx}.{side}[{i}]")


# ─── Test 1: GET /api/trades?league_id=... ─────────────────────────────
def test_get_trades_hydrates_assets(auth_headers):
    r = requests.get(
        f"{BASE_URL}/api/trades?league_id={LEAGUE_ID}",
        headers=auth_headers,
        timeout=30,
    )
    assert r.status_code == 200, f"{r.status_code} {r.text[:200]}"
    trades = r.json()
    assert isinstance(trades, list), f"expected list, got {type(trades)}"
    assert len(trades) > 0, "expected at least one trade in TFHL"
    for t in trades:
        _assert_scoring_categories(t)
        _walk_trade_assets(t, f"trade[{t.get('_id')}]")


# ─── Test 2: GET /api/leagues/{league_id}/trades ───────────────────────
def test_get_league_trades_hydrates_assets(auth_headers):
    r = requests.get(
        f"{BASE_URL}/api/leagues/{LEAGUE_ID}/trades",
        headers=auth_headers,
        timeout=30,
    )
    assert r.status_code == 200, f"{r.status_code} {r.text[:200]}"
    body = r.json()
    assert "trades" in body
    assert body["count"] >= 1
    for t in body["trades"]:
        _assert_scoring_categories(t)
        _walk_trade_assets(t, f"league_trade[{t.get('_id')}]")


# ─── Test 3: GET /api/leagues/{league_id}/pending-trades ───────────────
def test_get_pending_trades_hydrates_assets(auth_headers):
    r = requests.get(
        f"{BASE_URL}/api/leagues/{LEAGUE_ID}/pending-trades",
        headers=auth_headers,
        timeout=30,
    )
    assert r.status_code == 200, f"{r.status_code} {r.text[:200]}"
    body = r.json()
    assert "pending_trades" in body
    # Iter 231h: proposed status trades appear here too
    for t in body["pending_trades"]:
        _assert_scoring_categories(t)
        _walk_trade_assets(t, f"pending[{t.get('_id')}]")


# ─── Test 4: GET /api/trades/{trade_id} ────────────────────────────────
def test_get_trade_by_id_hydrates(auth_headers):
    lst = requests.get(
        f"{BASE_URL}/api/trades?league_id={LEAGUE_ID}",
        headers=auth_headers, timeout=30,
    ).json()
    assert lst, "no trades to pick from"
    tid = lst[0]["_id"]
    r = requests.get(f"{BASE_URL}/api/trades/{tid}", headers=auth_headers, timeout=30)
    assert r.status_code == 200
    t = r.json()
    _assert_scoring_categories(t)
    _walk_trade_assets(t, f"single[{tid}]")


# ─── Test 5: GET /api/trades/conditional?league_id=... ─────────────────
def test_get_conditional_trades_hydrates(auth_headers):
    r = requests.get(
        f"{BASE_URL}/api/trades/conditional?league_id={LEAGUE_ID}",
        headers=auth_headers,
        timeout=30,
    )
    # Endpoint should exist and return 200 even if no conditional trades
    assert r.status_code == 200, f"{r.status_code} {r.text[:200]}"
    body = r.json()
    assert "trades" in body
    for t in body["trades"]:
        _assert_scoring_categories(t)
        _walk_trade_assets(t, f"conditional[{t.get('_id')}]")


# ─── Test 6: McDavid values sanity — expected age~29, cap~$13.5M ───────
def test_mcdavid_values_in_tfhl(auth_headers):
    r = requests.get(
        f"{BASE_URL}/api/trades?league_id={LEAGUE_ID}",
        headers=auth_headers,
        timeout=30,
    )
    trades = r.json()
    mcd = None
    for t in trades:
        for side in ("assets_offered", "assets_requested"):
            for a in (t.get(side) or []):
                if "mcdavid" in (a.get("player_name") or "").lower():
                    mcd = a
                    break
            if mcd:
                break
        if mcd:
            break
    if not mcd:
        pytest.skip("McDavid not found in TFHL trades — skipping value sanity check")
    # Age & cap sanity (approximate — allow a few years/millions slack)
    assert 25 <= int(mcd.get("age", 0)) <= 35, f"McDavid age unexpected: {mcd.get('age')}"
    assert 5_000_000 <= float(mcd.get("cap_hit", 0)) <= 20_000_000, f"McDavid cap unexpected: {mcd.get('cap_hit')}"
    assert float(mcd.get("fantasy_points", 0)) > 0
    assert float(mcd.get("fantasy_points_per_game", 0)) > 0


# ─── Test 7: Pick assets are NOT hydrated with player fields ──────────
def test_pick_assets_not_hydrated(auth_headers):
    r = requests.get(
        f"{BASE_URL}/api/trades?league_id={LEAGUE_ID}",
        headers=auth_headers, timeout=30,
    )
    trades = r.json()
    found_pick = False
    for t in trades:
        for side in ("assets_offered", "assets_requested"):
            for a in (t.get(side) or []):
                if a.get("asset_type") == "pick" or a.get("item_type") == "pick":
                    found_pick = True
                    assert not a.get("fantasy_points"), f"pick has fantasy_points: {a}"
                    assert not a.get("stat_categories"), f"pick has stat_categories: {a}"
    if not found_pick:
        pytest.skip("no pick assets found in TFHL trades")
