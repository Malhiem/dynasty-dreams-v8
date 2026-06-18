"""
Iter 182 — Three follow-ups after iter 181:

  (1) Strip the legacy " (Prospect)" suffix from prospect names. The
      MinorEligibleBadge (iter 181) already differentiates prospects
      from veterans, so the suffix is redundant clutter. Also dedupe
      stale Gavin-McKenna orphan record.

  (2) Restructure player tables: dedicated "Team" column AFTER the
      player name on `/waivers/available` (already there on
      `/players`).

  (3) Expand the timeframe dropdown: prior seasons + playoffs +
      current matchup period, alongside YTD + rolling windows.
      Backend now reads cached historical stats from a
      `player_season_stats` collection populated by
      `scripts/iter182_backfill_season_stats.py`.
"""
from pathlib import Path

WAIVERS_TSX = Path("/app/frontend/src/lovable/pages/Waivers.tsx")
PLAYERS_PAGE = Path("/app/frontend/src/pages/PlayersPage.jsx")
SEED_SCRIPT = Path("/app/backend/scripts/iter170o_seed_prospects.py")
CLEANUP_SCRIPT = Path("/app/backend/scripts/iter182_strip_prospect_suffix.py")
SEASON_BACKFILL = Path("/app/backend/scripts/iter182_backfill_season_stats.py")
PLAYERS_PY = Path("/app/backend/routes/players.py")
WAIVERS_PY = Path("/app/backend/routes/waivers.py")


# ── (1) Prospect suffix cleanup ────────────────────────────────────

def test_prospect_seed_no_longer_appends_suffix():
    src = SEED_SCRIPT.read_text()
    assert 'prospect_name = f"{name} (Prospect)"' not in src
    assert "prospect_name = name" in src


def test_iter182_cleanup_script_exists_and_handles_collisions():
    assert CLEANUP_SCRIPT.exists()
    src = CLEANUP_SCRIPT.read_text()
    # The script must (a) delete prospect-vs-prospect orphan dupes,
    # (b) rename rather than skip on NHL-veteran collisions (the
    # MinorEligibleBadge differentiates them now), (c) record an
    # `iter182_renamed_at` audit field.
    assert 'await db.players.delete_one({"_id": collision["_id"]})' in src
    assert "renamed += 1" in src
    assert "iter182_renamed_at" in src
    # No "skip" path that leaves the suffix in place.
    assert "Skipped {legacy_name!r}: NHL veteran" not in src


# ── (2) "Team" column on /waivers ───────────────────────────────────

def test_waivers_available_table_has_dedicated_team_column():
    src = WAIVERS_TSX.read_text()
    # The Player column no longer renders the team-logo div block —
    # the team is rendered in its own dedicated column.
    assert "<TableHead>Player</TableHead>" in src
    assert '<TableHead className="text-center">Team</TableHead>' in src
    # And a per-row Team cell with a stable testid for QA.
    assert 'data-testid={`waiver-team-${player.id}`}' in src
    # Empty-state colspan bumped from 7 → 8 to match the new column.
    assert 'colSpan={8}' in src


# ── (3) Timeframe dropdown expanded ─────────────────────────────────

def test_waivers_timeframe_dropdown_exposes_expanded_options():
    src = WAIVERS_TSX.read_text()
    assert 'data-testid="waiver-available-timeframe"' in src
    # All required options surface in the dropdown.
    for v in [
        '<SelectItem value="season">YTD (2025-26)</SelectItem>',
        '<SelectItem value="matchup">Current Matchup</SelectItem>',
        '<SelectItem value="7d">Last 7 Days</SelectItem>',
        '<SelectItem value="2024-25">2024-25 Regular</SelectItem>',
        '<SelectItem value="2024-playoffs">2024 Playoffs</SelectItem>',
        '<SelectItem value="2023-24">2023-24 Regular</SelectItem>',
        '<SelectItem value="2023-playoffs">2023 Playoffs</SelectItem>',
    ]:
        assert v in src, f"missing timeframe option: {v}"
    # State + dep array wire the dropdown into the live fetch.
    assert "availableTimeframe" in src
    assert "[league?.id, myTeam?.id, availableTimeframe]" in src
    assert "encodeURIComponent(availableTimeframe)" in src


def test_players_page_timeframe_dropdown_includes_prior_seasons_and_matchup():
    src = PLAYERS_PAGE.read_text()
    for v in [
        '{ value: "season", label: "YTD (2025-26)" }',
        '{ value: "matchup", label: "Current Matchup" }',
        '{ value: "2024-25",       label: "2024-25 Regular" }',
        '{ value: "2024-playoffs", label: "2024 Playoffs" }',
        '{ value: "2023-24",       label: "2023-24 Regular" }',
        '{ value: "2023-playoffs", label: "2023 Playoffs" }',
    ]:
        assert v in src, f"missing timeframe option: {v}"


def test_backend_players_route_accepts_prior_season_and_matchup_timeframes():
    src = PLAYERS_PY.read_text()
    # Prior-season + playoffs branches resolve via the cached
    # `player_season_stats` collection.
    assert 'prior_season_match: Optional[dict] = None' in src
    assert 'timeframe in ("2024-25", "2023-24"):' in src
    assert 'timeframe in ("2024-playoffs", "2023-playoffs"):' in src
    assert 'await db.player_season_stats.find(' in src
    # "matchup" branch reads the active league's current matchup
    # window from schedule_metadata.
    assert 'timeframe == "matchup" and league_doc:' in src
    assert 'md.get("current_matchup_period")' in src


def test_iter182_season_backfill_script_exists():
    assert SEASON_BACKFILL.exists()
    src = SEASON_BACKFILL.read_text()
    # Targets the NHL stats landing endpoint that iter 175 already uses.
    assert "api-web.nhle.com/v1/player/{nhl_id}/landing" in src
    # Pulls both 2024-25 + 2023-24 regular AND playoffs.
    assert "20242025" in src and "20232024" in src
    assert "GAME_TYPE_MAP = {2: \"regular\", 3: \"playoffs\"}" in src
    # Idempotent compound-key upserts.
    assert "unique=True" in src
    assert "$set" in src


def test_waivers_endpoint_accepts_timeframe_param():
    src = WAIVERS_PY.read_text()
    assert 'timeframe: str = "season"' in src
    assert '"timeframe": timeframe,' in src
    # Iter 182 — also honours prior-season + playoffs by reading
    # the cached `player_season_stats` collection so the table
    # reflects the chosen timeframe instead of season totals.
    assert "season_stats_by_pid: dict = {}" in src
    assert "await db.player_season_stats.find(" in src
