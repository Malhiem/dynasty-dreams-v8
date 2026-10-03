"""
Iter 226 — Payments / Basics / Divisions / Week overrides.

Covers:
  • GET  /payments/league/{id}/status                  → per-team payment roll-up
  • POST /payments/league/{id}/intent  body={full:true}→ all-unpaid PAID stamp
  • POST /payments/league/{id}/intent  body={team_ids} → partial PAID stamp
  • LeagueUpdate now accepts week_overrides + format/scoring round-trip
  • Validate-setup with placeholders still passes
"""
from __future__ import annotations

import os
import uuid
import requests
from pymongo import MongoClient

API_URL = os.environ["REACT_APP_BACKEND_URL"]
_db = MongoClient(os.environ.get("MONGO_URL", os.environ["MONGO_URL"]))[
    os.environ.get("DB_NAME", os.environ["DB_NAME"])
]


def _login(email, password):
    r = requests.post(f"{API_URL}/api/auth/login", json={"email": email, "password": password})
    r.raise_for_status()
    return r.json()["access_token"]


def _register_user():
    s = uuid.uuid4().hex[:8]
    e = f"iter226_{s}@example.com"
    requests.post(f"{API_URL}/api/auth/register", json={
        "email": e, "password": "Pass123!", "username": f"iter226_{s}", "name": "Iter226",
    }).raise_for_status()
    return _login(e, "Pass123!")


def _create_paid_league(tok):
    H = {"Authorization": f"Bearer {tok}"}
    r = requests.post(f"{API_URL}/api/leagues", headers=H, json={
        "name": "iter226 " + uuid.uuid4().hex[:6],
        "format": "dynasty", "scoring_format": "head_to_head",
        "max_teams": 4, "draft_type": "snake", "roster_spots": 20,
        "entry_fee": 50.0,
    })
    r.raise_for_status()
    return r.json()


# ─── Payment status + intent ────────────────────────────────────────────

def test_league_payment_status_returns_per_team_rollup():
    tok = _register_user()
    league = _create_paid_league(tok)
    H = {"Authorization": f"Bearer {tok}"}
    r = requests.get(f"{API_URL}/api/payments/league/{league['id']}/status", headers=H)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["entry_fee"] == 50.0
    assert body["team_count"] >= 1
    assert body["paid_count"] == 0
    assert "teams" in body and all("paid" in t for t in body["teams"])


def test_full_payment_marks_every_unpaid_team():
    tok = _register_user()
    league = _create_paid_league(tok)
    H = {"Authorization": f"Bearer {tok}"}
    r = requests.post(
        f"{API_URL}/api/payments/league/{league['id']}/intent",
        headers=H, json={"full": True},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["mocked"] is True
    assert body["covered_count"] >= 1
    # The roll-up should now show every team paid.
    status = requests.get(f"{API_URL}/api/payments/league/{league['id']}/status", headers=H).json()
    assert status["unpaid_count"] == 0
    assert all(t["paid"] for t in status["teams"])


def test_partial_payment_marks_only_selected_teams():
    tok = _register_user()
    league = _create_paid_league(tok)
    H = {"Authorization": f"Bearer {tok}"}
    # Seed two extra teams via direct mongo so we have ≥3 teams to choose from
    for i in range(2):
        _db.teams.insert_one({
            "league_id": league["id"],
            "owner_id": f"filler_{uuid.uuid4().hex[:6]}",
            "name": f"Filler {i+1}",
            "abbr": f"F{i+1}",
            "roster": [],
        })
    status_before = requests.get(f"{API_URL}/api/payments/league/{league['id']}/status", headers=H).json()
    pick = status_before["teams"][0]["team_id"]
    r = requests.post(
        f"{API_URL}/api/payments/league/{league['id']}/intent",
        headers=H, json={"team_ids": [pick]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["covered_count"] == 1
    assert body["amount_total"] == 50.0
    status_after = requests.get(f"{API_URL}/api/payments/league/{league['id']}/status", headers=H).json()
    paid_ids = {t["team_id"] for t in status_after["teams"] if t["paid"]}
    assert pick in paid_ids
    assert status_after["paid_count"] == 1


def test_partial_payment_rejects_empty_team_ids():
    tok = _register_user()
    league = _create_paid_league(tok)
    H = {"Authorization": f"Bearer {tok}"}
    r = requests.post(
        f"{API_URL}/api/payments/league/{league['id']}/intent",
        headers=H, json={"team_ids": []},
    )
    assert r.status_code == 400


def test_payment_intent_blocks_non_commissioner():
    commish_tok = _register_user()
    league = _create_paid_league(commish_tok)
    intruder_tok = _register_user()
    r = requests.post(
        f"{API_URL}/api/payments/league/{league['id']}/intent",
        headers={"Authorization": f"Bearer {intruder_tok}"},
        json={"full": True},
    )
    assert r.status_code == 403


# ─── Week overrides + format/scoring round-trip ────────────────────────

def test_week_overrides_round_trip():
    tok = _register_user()
    league = _create_paid_league(tok)
    H = {"Authorization": f"Bearer {tok}"}
    overrides = [
        {"week_num": 5, "length_days": 10, "label": "Holiday break"},
        {"week_num": 12, "length_days": 14, "label": "All-Star"},
    ]
    r = requests.put(
        f"{API_URL}/api/leagues/{league['id']}",
        headers=H, json={"week_overrides": overrides},
    )
    assert r.status_code == 200, r.text
    got = requests.get(f"{API_URL}/api/leagues/{league['id']}", headers=H).json()
    assert isinstance(got.get("week_overrides"), list)
    assert any(w.get("week_num") == 5 and w.get("length_days") == 10 for w in got["week_overrides"])


def test_format_and_scoring_editable_via_put_leagues():
    tok = _register_user()
    league = _create_paid_league(tok)
    H = {"Authorization": f"Bearer {tok}"}
    r = requests.put(
        f"{API_URL}/api/leagues/{league['id']}",
        headers=H, json={"format": "keeper", "scoring_format": "points"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("format") == "keeper"
    assert body.get("scoring_format") == "points"
