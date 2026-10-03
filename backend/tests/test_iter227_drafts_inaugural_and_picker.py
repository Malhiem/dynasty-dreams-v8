"""
Iter 227 — Draft scheduling + inaugural-draft safeguards.

Covers:
  • POST /drafts persists a fresh draft and GET /drafts?league_id=... returns it
  • New leagues have ZERO scheduled drafts (the TFHL "3 mock saved drafts" bug)
  • Concurrent listings only return drafts for the requested league
"""
from __future__ import annotations

import os
import uuid
import requests

API_URL = os.environ["REACT_APP_BACKEND_URL"]


def _login(email, password):
    r = requests.post(f"{API_URL}/api/auth/login", json={"email": email, "password": password})
    r.raise_for_status()
    return r.json()["access_token"]


def _register_user():
    s = uuid.uuid4().hex[:8]
    e = f"iter227_{s}@example.com"
    requests.post(f"{API_URL}/api/auth/register", json={
        "email": e, "password": "Pass123!", "username": f"iter227_{s}", "name": "Iter227",
    }).raise_for_status()
    return _login(e, "Pass123!")


def _create_league(tok):
    H = {"Authorization": f"Bearer {tok}"}
    r = requests.post(f"{API_URL}/api/leagues", headers=H, json={
        "name": "iter227 " + uuid.uuid4().hex[:6],
        "format": "dynasty", "scoring_format": "head_to_head",
        "max_teams": 4, "draft_type": "snake", "roster_spots": 20,
    })
    r.raise_for_status()
    return r.json()


def test_fresh_league_has_zero_scheduled_drafts():
    """Was leaking 3 mock drafts on every league — now must start empty."""
    tok = _register_user()
    league = _create_league(tok)
    H = {"Authorization": f"Bearer {tok}"}
    r = requests.get(f"{API_URL}/api/drafts", params={"league_id": league["id"]}, headers=H)
    assert r.status_code == 200, r.text
    rows = r.json() if isinstance(r.json(), list) else r.json().get("drafts", [])
    assert rows == [], f"expected zero drafts on fresh league, got: {rows}"


def test_create_draft_then_list_includes_it():
    """The Create Draft button used to only toast — now it must persist
    and surface in GET /drafts?league_id=..."""
    tok = _register_user()
    league = _create_league(tok)
    H = {"Authorization": f"Bearer {tok}"}
    body = {
        "league_id": league["id"],
        "draft_type": "entry",
        "scheduled_time": None,
        "total_rounds": 5,
        "time_per_pick": 60,
        "snake_draft": True,
        "player_criteria": ["all"],
        "missed_pick_action": "auto-select",
    }
    r = requests.post(f"{API_URL}/api/drafts", headers=H, json=body)
    assert r.status_code in (200, 201), r.text
    new_id = r.json().get("id") or r.json().get("_id")
    assert new_id

    r2 = requests.get(f"{API_URL}/api/drafts", params={"league_id": league["id"]}, headers=H)
    rows = r2.json() if isinstance(r2.json(), list) else r2.json().get("drafts", [])
    ids = [(d.get("id") or d.get("_id")) for d in rows]
    assert new_id in ids, f"created draft {new_id} not surfaced by GET /drafts: {ids}"


def test_drafts_list_filters_by_league_id():
    """Iter-227 — listing for league A must NOT leak league B's drafts."""
    tok = _register_user()
    league_a = _create_league(tok)
    league_b = _create_league(tok)
    H = {"Authorization": f"Bearer {tok}"}

    requests.post(f"{API_URL}/api/drafts", headers=H, json={
        "league_id": league_b["id"], "draft_type": "entry",
        "scheduled_time": None, "total_rounds": 3, "time_per_pick": 60,
        "snake_draft": True, "player_criteria": ["all"], "missed_pick_action": "auto-select",
    }).raise_for_status()

    rows = requests.get(f"{API_URL}/api/drafts", params={"league_id": league_a["id"]}, headers=H).json()
    rows = rows if isinstance(rows, list) else rows.get("drafts", [])
    assert all(d.get("league_id") == league_a["id"] for d in rows), (
        f"league_id filter leaked rows: {[d.get('league_id') for d in rows]}"
    )
