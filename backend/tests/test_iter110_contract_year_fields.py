"""Iter 110 — Roster `_synthesize_contract` extra fields for the salary-cap
Year / Contract-Ends columns + By-Year bar chart.

Confirms:
  - total_years >= yearsRemaining (clamped)
  - current_year = total_years - yearsRemaining + 1, always >= 1
  - end_year = current_calendar_year + (yearsRemaining - 1)
  - end_status follows ELC→RFA / age-at-expiry rule
  - Deterministic from nhl_id (same id → same total_years)
"""
from datetime import datetime

import pytest

from routes.roster import _synthesize_contract


def test_synthesize_contract_emits_year_fields():
    out = _synthesize_contract(is_g=False, fpts_season=400, points=120, nhl_id=8478402, age=27)
    # Backward-compat fields still present
    assert "salary" in out and out["salary"] > 0
    assert "yearsRemaining" in out
    assert "type" in out
    # Iter 110 additions
    assert "total_years" in out
    assert "current_year" in out
    assert "end_year" in out
    assert "end_status" in out


def test_total_years_at_least_years_remaining():
    out = _synthesize_contract(is_g=False, fpts_season=100, points=50, nhl_id=7, age=24)
    assert out["total_years"] >= out["yearsRemaining"]
    assert out["current_year"] >= 1
    assert out["current_year"] == out["total_years"] - out["yearsRemaining"] + 1


def test_end_year_matches_seasons_remaining():
    cur_year = datetime.utcnow().year
    out = _synthesize_contract(is_g=False, fpts_season=100, points=50, nhl_id=8478402, age=27)
    # end_year = cur_year + (yearsRemaining - 1)
    assert out["end_year"] == cur_year + out["yearsRemaining"] - 1


def test_end_status_elc_becomes_rfa():
    # Young + low salary → ELC; ELC ALWAYS ends as RFA
    out = _synthesize_contract(is_g=False, fpts_season=10, points=5, nhl_id=2, age=20)
    assert out["type"] == "ELC"
    assert out["end_status"] == "RFA"


def test_end_status_old_player_becomes_ufa():
    out = _synthesize_contract(is_g=False, fpts_season=400, points=120, nhl_id=10, age=30)
    # Multi-year deal but the player will be 30+ at expiry → UFA
    if out["type"] == "Signed":
        assert out["end_status"] == "UFA"


def test_deterministic_from_nhl_id():
    a = _synthesize_contract(is_g=False, fpts_season=400, points=120, nhl_id=8478402, age=27)
    b = _synthesize_contract(is_g=False, fpts_season=400, points=120, nhl_id=8478402, age=27)
    assert a == b
