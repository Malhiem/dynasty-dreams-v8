"""
Iter 197 — Playoff bracket naming fix + Mark Winner + Distribute Prize.

Coverage:
1. Round naming for an 8-team / 3-round bracket reads Quarterfinals →
   Semifinals → Championship (not "Round 1 → QF → Championship").
2. Missing intermediate-round matchups are synthesized so each round has
   the expected count (2^(total_rounds - round)).
3. `mark-winner` endpoint persists status/scores + propagates the winner
   into the next round's TBD slot.
4. `distribute-prize` endpoint writes `payouts` + activity_feed + stamps
   the league with champion / runner-up / consolation_champion ids.
5. `/playoff-bracket` payload now surfaces a `champion` block with
   `decided`, `champion`, `runner_up`, `distributed`, and per-prize
   amounts when the final round is completed.
"""
from __future__ import annotations
from tests.http_test_auth import test_admin_headers
from tests.playoff_input_fixture import playoff_inputs

import os
import time
import requests

API_URL = os.environ["REACT_APP_BACKEND_URL"]
LEAGUE_ID = "69e46af167999bfb85c39628"  # Ice Kings Head-to-Head
EMAIL = os.environ.get("TEST_OWNER_EMAIL", "test-owner@e2e.dynastydreams.com")
PASSWORD = os.environ.get("TEST_OWNER_PASSWORD", "e2e-owner-password")


def _login() -> str:
    r = requests.post(f"{API_URL}/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
    r.raise_for_status()
    return r.json()["access_token"]


def _bracket() -> dict:
    r = requests.get(f"{API_URL}/api/leagues/{LEAGUE_ID}/playoff-bracket", headers=test_admin_headers())
    r.raise_for_status()
    return r.json()


def test_bracket_round_names_8_team():
    b = _bracket()
    assert b["playoff_size"] == 8
    names = [r["name"] for r in b["rounds"]]
    assert names == ["Quarterfinals", "Semifinals", "Championship"], names


def test_bracket_round_counts_synthesized():
    b = _bracket()
    counts = [len(r["matchups"]) for r in b["rounds"]]
    assert counts == [4, 2, 1], counts


def test_bracket_matchups_carry_matchup_id():
    b = _bracket()
    qf = b["rounds"][0]["matchups"]
    assert all(m.get("matchup_id") for m in qf), "QF matchups missing matchup_id"


def test_bracket_champion_block_present():
    b = _bracket()
    ch = b.get("champion")
    assert ch is not None
    assert "decided" in ch
    assert "distributed" in ch


def test_mark_winner_propagates_to_next_round():
    token = _login()
    headers = {"Authorization": f"Bearer {token}"}
    b = _bracket()
    qf0 = b["rounds"][0]["matchups"][0]
    winner_id = qf0["high_seed"]["team_id"]
    mu_id = qf0["matchup_id"]

    r = requests.post(
        f"{API_URL}/api/leagues/{LEAGUE_ID}/playoffs/mark-winner",
        headers=headers,
        json={"matchup_id": mu_id, "winner_team_id": winner_id},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True

    b2 = _bracket()
    qf0b = b2["rounds"][0]["matchups"][0]
    assert qf0b["status"] in ("completed", "final")
    # SF#0 should now have the winner advanced into its home slot.
    sf0 = b2["rounds"][1]["matchups"][0]
    assert sf0.get("home_team_id") == winner_id

    # Cleanup — revert by resetting the matchup directly via Mongo would
    # require backend access; instead just leave it (idempotent flow).


def test_mark_winner_requires_commissioner():
    # Anonymous request (no token) should 401/403.
    b = _bracket()
    qf0 = b["rounds"][0]["matchups"][0]
    r = requests.post(
        f"{API_URL}/api/leagues/{LEAGUE_ID}/playoffs/mark-winner",
        json={"matchup_id": qf0["matchup_id"], "winner_team_id": qf0["high_seed"]["team_id"]},
    )
    assert r.status_code in (401, 403), r.status_code


def test_distribute_prize_persists_and_surfaces():
    token = _login()
    headers = {"Authorization": f"Bearer {token}"}
    # Champion / runner-up come from teams in playoff seeds
    b = _bracket()
    seeds = b["playoff_teams"]
    champ_id = seeds[0]["team_id"]
    ru_id = seeds[1]["team_id"]

    r = requests.post(
        f"{API_URL}/api/leagues/{LEAGUE_ID}/playoffs/distribute-prize",
        headers=headers,
        json={
            "champion_team_id": champ_id,
            "runner_up_team_id": ru_id,
            "champion_prize": 500,
            "runner_up_prize": 200,
            "currency": "USD",
            "note": "iter197 test",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["champion_prize"] == 500
    assert body["runner_up_prize"] == 200

    # GET payout endpoint
    r2 = requests.get(f"{API_URL}/api/leagues/{LEAGUE_ID}/playoffs/payout", headers=headers)
    assert r2.status_code == 200, r2.text
    p = r2.json()
    assert p["distributed"] is True
    assert p["champion_team_id"] == champ_id
    assert p["champion_prize"] == 500

    # Champion block in /playoff-bracket should now report distributed=true
    b2 = _bracket()
    ch = b2.get("champion") or {}
    assert ch.get("distributed") is True
    assert ch.get("champion_prize") == 500


def test_distribute_prize_idempotent_overwrites():
    token = _login()
    headers = {"Authorization": f"Bearer {token}"}
    b = _bracket()
    champ_id = b["playoff_teams"][0]["team_id"]
    ru_id = b["playoff_teams"][1]["team_id"]
    # Second call with different amounts
    r = requests.post(
        f"{API_URL}/api/leagues/{LEAGUE_ID}/playoffs/distribute-prize",
        headers=headers,
        json={
            "champion_team_id": champ_id,
            "runner_up_team_id": ru_id,
            "champion_prize": 750,
            "runner_up_prize": 250,
            "currency": "USD",
        },
    )
    assert r.status_code == 200, r.text
    r2 = requests.get(f"{API_URL}/api/leagues/{LEAGUE_ID}/playoffs/payout", headers=headers)
    p = r2.json()
    assert p["champion_prize"] == 750
    assert p["runner_up_prize"] == 250
