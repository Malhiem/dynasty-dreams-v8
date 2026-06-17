"""Iter 170e — Draft Room polish from user feedback:

  (1) Richer pick tiles: photo/initial circle + name + position badge +
      league + pts, with the tile background washed in the position tint.
  (2) Next team in the Draft Live sidebar (under "On the Clock").
  (3) Dedupe colliding team abbrs (two teams sharing initials → second
      gets a `2` suffix) so each board column is unique.
  (4) Include backend-derived `logo_abbr` in the filter chip ↔ livePick
      matcher so chips like BAD / FHF (where the override differs from
      the name initials) actually highlight the right column.
  (5) Always append the column's own abbr to `currentOwnerAbbrs` so a
      chip click highlights the column even when livePick reports a
      different abbr derivation.

Timer reset on currentPick change was already handled by the existing
useEffect at L295 (`pickTimeLeft` resets to `draftConfig.pickTimerSeconds`
whenever `draftConfig.currentPick` changes); no new test needed for that.
"""
from pathlib import Path

DRAFT_ROOM = Path("/app/frontend/src/lovable/pages/DraftRoom.tsx")


def _src() -> str:
    return DRAFT_ROOM.read_text()


def test_position_tints_map_present():
    src = _src()
    assert "const positionTints: Record<string, string> = {" in src
    for pos in ("C", "LW", "RW", "D", "G"):
        # Each position has a soft tint variant used for the tile bg.
        assert f"  {pos}:" in src or f"\n  {pos}:" in src


def test_board_team_abbr_dedup_logic():
    src = _src()
    # The boardTeams memo must track seen abbrs and append a suffix on
    # the 2nd+ occurrence so two CC teams don't collapse onto one
    # column.
    block = src.split("const boardTeams = useMemo")[1].split("}, [liveTeams]);")[0]
    assert "const seen = new Map<string, number>()" in block
    assert "if (count > 0) abbr = `${abbr}${count + 1}`" in block
    # Hyphen-aware initials (Five-Hole Fighters → FHF) to match backend
    # `logo_abbr` derivation when the team has no explicit override.
    assert 'replace(/-/g, " ")' in block


def test_compute_abbrs_includes_logo_abbr():
    src = _src()
    block = src.split("const computeAbbrs")[1].split("for (const p of picks)")[0]
    # Backend `logo_abbr` (which honours overrides + hyphen-splits) is
    # the first abbr the matcher checks so chips line up with picks.
    assert "lt?.logo_abbr" in block
    # Hyphen-aware initials fallback also present.
    assert 'replace(/-/g, " ")' in block


def test_current_owner_abbrs_always_includes_column_abbr():
    src = _src()
    # The current-owner abbr list MUST always include the column's own
    # abbr so chip-by-chip filter highlights work even on traded picks.
    assert "...(livePick?._currentOwnerAbbrs || [])," in src
    assert "teamAbbr,\n                          ]));" in src


def test_pick_tile_has_photo_or_initial_circle():
    src = _src()
    # Photo OR initial-circle fallback render in the pick tile so a
    # drafted player reads as a mini player card.
    assert "draft-board-tile-photo-" in src
    assert "draft-board-tile-initial-" in src
    # Tile testid covers every tile (player or empty).
    assert "draft-board-tile-${teamAbbr}-${round}" in src


def test_pick_tile_uses_position_tint_background():
    src = _src()
    # The tile className picks positionTints[pos] when there's a player.
    assert "(positionTints[pick.player.position] || \"bg-secondary/60 border-border\")" in src


def test_pick_tile_renders_league_and_points():
    src = _src()
    # League / NHL team line and pts line render under the badge.
    assert "pick.player.league || pick.player.nhlTeam" in src
    assert "pick.player.pts" in src


def test_draft_live_sidebar_shows_next_team():
    src = _src()
    assert 'data-testid="draft-room-next-on-clock"' in src
    # Computed from the NEXT overall pick (not the current one).
    assert "const nextOverall = draftConfig.currentPick + 1" in src
    # Resolves the next abbr via getTeamForPick + boardTeams.find.
    assert "const nextAbbr = nextOverall <= totalTeams * draftConfig.totalRounds" in src
    assert "boardTeams.find((t) => t.abbr === nextAbbr)" in src


def test_on_the_clock_team_has_testid():
    src = _src()
    # Stable testid so QA can assert the current on-the-clock team text.
    assert 'data-testid="draft-room-on-the-clock-team"' in src
