"""
Iter 221 — POST /api/matchups/preview dry-run endpoint for Create-League wizard.

Validates:
  • Returns the requested number of weeks
  • Honours `matchups_per_week` (each team plays N times per week)
  • No DB writes (calling twice with same input returns equivalent shapes)
  • Defaults clamp out-of-range inputs
"""
from __future__ import annotations

import os
import requests

API_URL = os.environ["REACT_APP_BACKEND_URL"]


def _preview(payload):
    r = requests.post(f"{API_URL}/api/matchups/preview", json=payload)
    r.raise_for_status()
    return r.json()


def test_preview_returns_requested_weeks():
    d = _preview({"max_teams": 10, "matchups_per_week": 1, "num_weeks": 4})
    assert d["team_count"] == 10
    assert len(d["weeks"]) == 4
    assert all(w["week"] == idx + 1 for idx, w in enumerate(d["weeks"]))
    # 10 teams → 5 matchups per week with mpw=1
    assert all(len(w["matchups"]) == 5 for w in d["weeks"])
    assert d["matchups_per_week"] == 1
    assert d["total_matchups"] == 4 * 5


def test_preview_doubles_with_matchups_per_week_2():
    d = _preview({"max_teams": 10, "matchups_per_week": 2, "num_weeks": 4})
    # Each team plays 2 opponents per week → 10 matchups/week for 10 teams
    assert d["matchups_per_week"] == 2
    assert all(len(w["matchups"]) == 10 for w in d["weeks"])


def test_preview_caps_matchups_per_week_to_n_minus_1():
    # 4 teams → max opponents per week = 3. Send the largest accepted value.
    d = _preview({"max_teams": 4, "matchups_per_week": 31, "num_weeks": 2})
    assert d["matchups_per_week"] == 3


def test_preview_no_db_writes_idempotent():
    a = _preview({"max_teams": 8, "matchups_per_week": 1, "num_weeks": 3})
    b = _preview({"max_teams": 8, "matchups_per_week": 1, "num_weeks": 3})
    # Same number of matchups + same week count across two consecutive calls
    assert len(a["weeks"]) == len(b["weeks"]) == 3
    assert a["total_matchups"] == b["total_matchups"]


def test_preview_each_team_plays_at_most_once_per_week_when_mpw_1():
    d = _preview({"max_teams": 12, "matchups_per_week": 1, "num_weeks": 3})
    for wk in d["weeks"]:
        seen = []
        for m in wk["matchups"]:
            seen.extend([m["home_team_id"], m["away_team_id"]])
        # No duplicates → every team plays at most once
        assert len(seen) == len(set(seen)), f"Duplicate team in week {wk['week']}: {seen}"


def test_preview_rejects_invalid_team_count():
    r = requests.post(f"{API_URL}/api/matchups/preview", json={
        "max_teams": 1, "matchups_per_week": 1, "num_weeks": 4,
    })
    assert r.status_code == 422  # Pydantic ge=2 rejects
