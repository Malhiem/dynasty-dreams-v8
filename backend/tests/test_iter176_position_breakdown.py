"""
Iter 176 — Position Breakdown (renamed + restructured from Position Limits).

The commissioner's Roster Settings now exposes per-section position
caps:
  • Active Roster (always shown — its row sum drives `roster_spots`)
  • Bench (only shown when the league has bench spots configured)
  • Minors (only shown when `minors_enabled` is on)

Each cell can be blank (= no limit). Categorical buckets `S` (Skater =
any non-G) and `W` (Wing = LW or RW) sit alongside the per-position
caps for leagues that lump positions together.
"""
import asyncio
import os

import pytest
from pathlib import Path

ROSTERS_TAB = Path("/app/frontend/src/lovable/pages/commissioner/RostersTab.tsx")
LEAGUES_PY = Path("/app/backend/routes/leagues.py")
ROSTER_RULES = Path("/app/backend/utils/roster_rules.py")


# ── Frontend ───────────────────────────────────────────────────────


def test_card_renamed_to_position_breakdown():
    src = ROSTERS_TAB.read_text()
    assert "Position Breakdown" in src
    # Legacy title removed everywhere.
    assert "Position Limits" not in src
    # InfoHint testid renamed alongside the title.
    assert 'testId="info-position-breakdown"' in src
    assert 'testId="info-position-limits"' not in src


def test_new_position_taxonomy_adds_skater_and_wing_buckets():
    src = ROSTERS_TAB.read_text()
    for key in ("S", "C", "LW", "RW", "W", "D", "G"):
        # Either an Input testid OR the POSITIONS array literal carries it.
        assert f'"{key}"' in src, f"position key {key!r} missing"
    # Skater/Wing helper copy is explicit so the commissioner knows
    # how the categorical buckets behave.
    assert "Any non-goalie" in src
    assert "Either LW or RW" in src


def test_three_rows_active_bench_minors_with_conditional_visibility():
    src = ROSTERS_TAB.read_text()
    # All three rows are registered.
    assert "BREAKDOWN_ROWS" in src
    assert '"active"' in src and '"bench"' in src and '"minors"' in src
    # Bench is gated on a non-zero bench cap.
    assert '(parseIntOrNull(benchSpots) || 0) > 0' in src
    # Minors is gated on league.minors_enabled.
    assert "minors_enabled" in src
    # Each row gets its own testid for the QA framework. Template literal
    # interpolates the row key at runtime.
    assert "rosters-position-breakdown-row-${row.key}" in src


def test_per_cell_inputs_have_stable_testids():
    """Each (row, position) cell must carry a unique data-testid so QA
    can drive it: rosters-position-{row}-{position}-input."""
    src = ROSTERS_TAB.read_text()
    assert "rosters-position-${row.key}-${p.key}-input" in src
    assert "rosters-position-${row.key}-total" in src


def test_blank_cells_send_no_limit_for_that_cell():
    """The save payload only carries cells the commissioner actually
    filled in. parseIntOrNull on a blank input yields null → not added
    to the row dict, which the enforcement helper treats as "no cap"."""
    src = ROSTERS_TAB.read_text()
    assert "if (n !== null) out[p.key] = n;" in src
    # No fallback default that would smuggle 0 into the row.
    assert "out[p.key] = 0;" not in src


def test_roster_spots_derived_from_active_row_sum():
    """The 'Active Roster' input flips read-only and displays the sum
    of the Active row when the commissioner has set any per-position
    caps. Save payload sends `roster_spots = activeSum` so the league
    document stays consistent."""
    src = ROSTERS_TAB.read_text()
    # UI side: derived flag + read-only + computed display.
    assert "readOnly={derived}" in src
    assert 'data-testid="rosters-roster-spots-derived-note"' in src
    assert "Derived from Position Breakdown → Active Roster" in src
    # Payload side: ships the derived total.
    assert "payload.roster_spots = activeSum" in src


def test_legacy_position_limits_mirror_for_backward_compat():
    """Until callers migrate, save still mirrors `active` into the
    legacy single-row `position_limits` field so waivers + trade
    engine helpers keep working."""
    src = ROSTERS_TAB.read_text()
    assert "payload.position_limits = breakdown.active;" in src


# ── Backend models / route ─────────────────────────────────────────


def test_league_models_register_position_breakdown_field():
    src = LEAGUES_PY.read_text()
    # Both the LeagueResponse model AND LeagueUpdate model expose the
    # new field so it survives GET + PUT round-trips.
    assert src.count("position_breakdown: Optional[dict]") >= 2
    # _LEAGUE_UPDATE_ALLOWED whitelist includes the new field.
    assert '"position_breakdown",' in src
    # Response builder hydrates the field from the Mongo doc.
    assert 'position_breakdown=league.get("position_breakdown")' in src


def test_put_derives_roster_spots_from_active_row_server_side():
    """Server-side defense-in-depth: even a direct API caller that
    forgets to send `roster_spots` gets a consistent value derived
    from `position_breakdown.active`."""
    src = LEAGUES_PY.read_text()
    assert "Iter 176: derive `roster_spots` from `position_breakdown.active`" in src
    assert 'active_sum = sum(int(v) for v in active.values()' in src
    assert 'update["roster_spots"] = active_sum' in src
    assert '"derived": True' in src


# ── Enforcement (roster_rules) ─────────────────────────────────────


def test_check_position_limits_reads_breakdown_then_legacy():
    src = ROSTER_RULES.read_text()
    # New canonical source preferred over legacy single-row.
    assert 'breakdown = league.get("position_breakdown") or {}' in src
    assert 'active_limits = breakdown.get("active") if isinstance(breakdown, dict) else None' in src
    assert 'limits = active_limits if active_limits else (league.get("position_limits") or {})' in src


def test_check_position_limits_handles_skater_and_wing_buckets():
    """A C player triggers both the C cap AND the S cap.
    An LW player triggers LW, W, and S."""
    src = ROSTER_RULES.read_text()
    assert 'triggered_buckets.add("S")' in src
    assert 'triggered_buckets.add("W")' in src
    # The matcher function correctly excludes goalies from the S bucket
    # and limits W to LW/RW.
    assert 'bucket == "S"' in src and 'existing != "G"' in src
    assert 'bucket == "W"' in src and 'existing in ("LW", "RW")' in src


# ── Runtime smoke (skipped under PYTEST in CI but useful locally) ──


@pytest.mark.skipif(
    not os.environ.get("INTEGRATION", "") == "1",
    reason="Integration smoke; set INTEGRATION=1 to run",
)
def test_enforcement_helper_runtime_smoke():
    """Quick sanity that the helper rejects an over-cap add with the
    new Position Breakdown format."""
    from utils.roster_rules import check_position_limits
    league = {
        "enforce_position_maxes": True,
        "position_breakdown": {"active": {"S": 2}, "bench": {}, "minors": {}},
    }
    roster = [
        {"position": "C"},
        {"position": "LW"},
    ]
    candidate = {"name": "Test Skater", "position": "RW"}
    err = check_position_limits(league, roster, candidate)
    assert err is not None and "S" in err
