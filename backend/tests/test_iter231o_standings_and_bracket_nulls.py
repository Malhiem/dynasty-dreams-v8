"""Iter 231o — Standings shows every team + bracket serializer never
emits null team_name.

Two related fixes:

  (1) The standings page used a bogus "fallback division" — when a team
      had no real division, the frontend assigned it to a hardcoded NHL
      division name ("Atlantic"/"Metropolitan"/etc.). If the league
      then had ONE real division (e.g. TFHL has division "1" with just
      1/24 teams assigned), the divisional grouping silently dropped
      the 23 teams whose "fallback" didn't match any real division.

      The frontend fix surfaces an "Unassigned" group; this test
      asserts the backend payload that drives that frontend logic.

  (2) `_team_to_slot` in `routes/leagues.py` previously returned
      `team_name: None` when a team doc had no name. The frontend
      bracket consumers crashed with "Cannot read properties of null
      (reading 'slice')" when they tried to derive abbreviations. The
      backend now always returns a safe non-null string + a derived
      abbr, so the API contract no longer has the null-name hazard.
"""
from pathlib import Path


LEAGUES = Path("/app/backend/routes/leagues.py")
STANDINGS_PAGE = Path("/app/frontend/src/lovable/pages/Standings.tsx")
PLAYOFF_PAGE = Path("/app/frontend/src/lovable/pages/PlayoffBracket.tsx")


def test_team_to_slot_falls_back_to_open_slot_name():
    """_team_to_slot must never emit `team_name: None`."""
    src = LEAGUES.read_text()
    block = src.split("def _team_to_slot")[1].split("# ── Iter 104")[0]
    # The raw .get("name") is wrapped in a safe-fallback expression.
    assert 'raw_name = t.get("name")' in block
    assert 'safe_name = raw_name if (raw_name and str(raw_name).strip()) else f"Open Slot' in block
    # The returned dict uses the safe value.
    assert '"team_name": safe_name' in block
    # And the abbr falls back too.
    assert '"team_abbr": t.get("logo_abbr") or (safe_name[:3].upper() if safe_name else "TBD")' in block


def test_standings_drops_fake_division_fallback():
    """The previous `fallbackDivisions[idx % 4]` lie is removed — teams
    with no real division now appear in the "Unassigned" group."""
    src = STANDINGS_PAGE.read_text()
    assert 'fallbackDivisions = ["Atlantic","Metropolitan","Central","Pacific"]' not in src
    assert 'fallbackConferences = ["Eastern","Western"]' not in src
    # Constant marker for the new bucket.
    assert 'const UNASSIGNED = "Unassigned";' in src
    # liveTeams maps undefined divisions to UNASSIGNED (not fake NHL names).
    assert "division: backend?.division || UNASSIGNED," in src
    assert "conference: backend?.conference || UNASSIGNED," in src


def test_standings_only_auto_switches_when_majority_assigned():
    """Auto-switching to division view when <50% of teams are assigned
    leaves users in an empty bracket. Smart fix only switches when most
    teams have a real division."""
    src = STANDINGS_PAGE.read_text()
    assert "assigned / total >= 0.5" in src


def test_standings_appends_unassigned_to_division_names():
    src = STANDINGS_PAGE.read_text()
    # New code path: `hasUnassigned` flag short-circuits into appending
    # the Unassigned bucket to the rendered list.
    assert "const hasUnassigned = liveTeams.some((t) => t.division === UNASSIGNED);" in src
    assert "return hasUnassigned ? [...base, UNASSIGNED] : base;" in src


def test_bracket_team_type_marks_team_name_nullable():
    """Iter 231n — type now reflects backend reality. Iter 231o makes
    the backend strictly non-null but we keep the type permissive so
    legacy clients still type-check against older payloads."""
    src = PLAYOFF_PAGE.read_text()
    assert "team_name: string | null;" in src
