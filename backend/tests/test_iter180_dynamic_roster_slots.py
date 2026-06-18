"""
Iter 180 — Active Roster slots on the team page now come from the
league's `position_breakdown.active` config, not from a hardcoded
`LEAGUE_ROSTER_SLOTS` constant.

Bug repro (pre-fix):
  1. Commissioner saves position_breakdown.active = {C: 4, LW: 4,
     RW: 4, D: 6, G: 1} via the Rosters tab.
  2. Backend persists the breakdown and derives roster_spots = 19.
  3. Team page Active Roster grid keeps showing the legacy default
     (2 C, 1 LW, 1 RW, 1 W, 1 D, 1 UTIL) — disconnected from the
     league config.

Fix: PlayerRoster.tsx now shadows the module-level
`LEAGUE_ROSTER_SLOTS` with a `useMemo` that calls
`buildLeagueRosterSlots(league.position_breakdown.active)`. Section
maxSlots (bench, IR, minors) also read from the active league.

Iter 180 (b) — Bench (Reserve) row removed from the Position
Breakdown matrix UI (state shape kept for backward compat). Minors
row visibility widened so it surfaces when the league has bench
spots configured, minors capacity, or `minors_enabled`.
"""
from pathlib import Path

PLAYER_ROSTER = Path("/app/frontend/src/lovable/components/dashboard/PlayerRoster.tsx")
ROSTERS_TAB = Path("/app/frontend/src/lovable/pages/commissioner/RostersTab.tsx")


def test_player_roster_imports_use_active_league():
    src = PLAYER_ROSTER.read_text()
    assert 'import { useActiveLeague } from "@/hooks/use-active-league";' in src


def test_build_league_roster_slots_helper_exists():
    """Module-level pure helper that maps a position_breakdown.active
    dict into an ordered list of RosterSlot objects."""
    src = PLAYER_ROSTER.read_text()
    assert "const buildLeagueRosterSlots = (" in src
    # Goalies omitted from the skater grid (rendered in dedicated section).
    assert 'const ORDER: RosterSlotType[] = ["C", "LW", "RW", "W", "F", "SK", "D", "UTIL"];' in src
    # Default fallback when no breakdown configured.
    assert "return LEAGUE_ROSTER_SLOTS;" in src


def test_player_roster_shadows_league_roster_slots_with_use_memo():
    """The component-scoped LEAGUE_ROSTER_SLOTS shadows the module
    constant and derives from the active league's
    position_breakdown.active. This is what makes the team page
    actually respond to commissioner changes."""
    src = PLAYER_ROSTER.read_text()
    assert "const { league: activeLeagueFromHook } = useActiveLeague();" in src
    assert "const LEAGUE_ROSTER_SLOTS = useMemo(" in src
    assert "buildLeagueRosterSlots((activeLeagueFromHook as any)?.position_breakdown?.active)" in src


def test_section_config_max_slots_driven_by_league():
    """bench / ir / minors maxSlots now read from league.bench_spots,
    league.ir_slots, league.minors_spots instead of hardcoded 4/3/5."""
    src = PLAYER_ROSTER.read_text()
    assert 'maxSlots: typeof l.bench_spots === "number" ? l.bench_spots : 4' in src
    assert 'maxSlots: typeof l.ir_slots === "number" ? l.ir_slots : 3' in src
    assert 'maxSlots: typeof l.minors_spots === "number" ? l.minors_spots : 5' in src


def test_module_default_roster_slots_retained_as_fallback():
    """When no breakdown is configured (legacy leagues, or before
    the active league has loaded), the module default seven slots
    keep the team page renderable."""
    src = PLAYER_ROSTER.read_text()
    # Module-level default kept for the fallback path.
    assert 'const LEAGUE_ROSTER_SLOTS: RosterSlot[] = [' in src
    assert '{ id: "C1", label: "C", eligiblePositions: slotEligibility.C },' in src
    assert '{ id: "UTIL1", label: "UTIL", eligiblePositions: slotEligibility.UTIL },' in src


def test_bench_reserve_row_dropped_from_ui():
    """Iter 180 — visible breakdown rows are Active / Bench / Minors
    only. The bench2 (Bench Reserve) row was removed."""
    src = ROSTERS_TAB.read_text()
    assert '{ key: "bench2", label: "Bench (Reserve)"' not in src
    assert '{ key: "minors", label: "Minors",' in src


def test_minors_row_visibility_includes_prospect_pool_and_bench():
    """Minors row surfaces when bench>0 OR minors_spots>0 OR minors_enabled."""
    src = ROSTERS_TAB.read_text()
    assert "const minorsOn =" in src
    assert "!!(league as any).minors_enabled" in src
    assert "(parseIntOrNull(prospectPool) || 0) > 0" in src
    assert "|| benchOn;" in src
