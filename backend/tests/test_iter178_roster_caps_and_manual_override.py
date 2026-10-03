"""
Iter 178 — Bumped Prospect Pool + Taxi Squad caps to 100; fixed the
Active Roster input getting locked read-only so a commissioner who
typed 19 silently had their value discarded.

Bug repro (pre-fix):
  1. Commissioner sets Position Breakdown → Active to {S: 18, G: 2}.
     The Active Roster input flips read-only and shows 20.
  2. They click into the input and type 19. The value never changes
     in state because the input is `readOnly`.
  3. Save sends `roster_spots: 20` (derived from the active row).
  4. Team page still shows the old roster cap; the user's manual
     override is silently discarded.

Fix: keep the input editable; manual value (if any) wins; derived sum
acts as a placeholder hint instead of a forced value.
"""
from pathlib import Path

ROSTERS_TAB = Path("/app/frontend/src/lovable/pages/commissioner/RostersTab.tsx")
LEAGUES_PY = Path("/app/backend/routes/leagues.py")
TEAM_TSX = Path("/app/frontend/src/lovable/pages/Team.tsx")


def test_prospect_and_taxi_inputs_allow_up_to_100():
    src = ROSTERS_TAB.read_text()
    # Labels updated alongside the max=100 attribute.
    # Iter 181 — "Prospect Pool Size" renamed to "Minors Team Size".
    assert "Minors Team Size (0–100)" in src
    assert "Taxi Squad Size (0–100)" in src
    # Validator block reflects the new ceiling.
    assert '["minors_spots", prospectPool, 0, 100]' in src
    assert '["taxi_squad_size", taxiSquad, 0, 100]' in src
    # Inputs themselves expose max={100} so the browser-side number
    # spinner doesn't clamp the value.
    assert "max={100}" in src


def test_pydantic_caps_widened_to_100():
    src = LEAGUES_PY.read_text()
    assert "minors_spots: Optional[int] = Field(default=None, ge=0, le=100)" in src
    assert "taxi_squad_size: Optional[int] = Field(default=None, ge=0, le=100)" in src
    # Active roster ceiling also widened so a league with a deep
    # roster (e.g. 60) can be configured.
    assert "roster_spots: int = Field(default=20, ge=10, le=100)" in src
    assert "roster_spots: Optional[int] = Field(default=None, ge=10, le=100)" in src


def test_active_roster_input_stays_editable_with_derived_placeholder():
    """The bug was that read-only locked the input when per-position
    caps were set. The fix: the input is always editable; the derived
    sum is shown as a placeholder hint."""
    src = ROSTERS_TAB.read_text()
    # No `readOnly` flag tied to the derived condition (only the
    # value/onChange wiring remains).
    assert "readOnly={derived}" not in src
    assert "!derived && setRosterSpots" not in src
    # Derived sum is communicated via placeholder, not a forced value.
    assert "placeholder={hasCaps ? String(activeSum) : \"20\"}" in src
    # New helper copy explains the override path.
    assert "Leave blank to inherit, or type a different value to override." in src


def test_save_payload_prefers_manual_roster_spots_over_derived_sum():
    """Manual value (if any) is the source of truth on save. If the
    commissioner clears the input, we fall back to the active row's
    derived sum."""
    src = ROSTERS_TAB.read_text()
    assert "const manualRoster = parseIntOrNull(rosterSpots);" in src
    assert "if (manualRoster !== null) {" in src
    assert "payload.roster_spots = manualRoster;" in src
    # Fallback to derived sum only when manual input is blank.
    assert "} else if (Object.keys(breakdown.active).length > 0 && activeSum > 0) {" in src
    assert "payload.roster_spots = activeSum;" in src


def test_team_page_roster_size_subtitle_reads_league_cap():
    """The team page used to subtract roster_count from a hardcoded
    25 ("8 spots open"). Fix: subtract from `league.roster_spots`
    (falling back to 25 only if the league config hasn't loaded yet)."""
    src = TEAM_TSX.read_text()
    assert "(league as any)?.roster_spots ?? 25" in src
    # Bare hardcoded "25 - selectedTeam.roster_count" is gone.
    assert "25 - selectedTeam.roster_count" not in src
