"""
Iter 183 — Two follow-ups after iter 182:

  (1) NHL multi-stint cleanup in
      `scripts/iter182_backfill_season_stats.py`. The original
      last-wins upsert silently overwrote McDavid's 82-game 2024-25
      row with a 4-game international tournament row. Fix: filter
      to `leagueAbbrev == "NHL"` first, then aggregate any remaining
      multi-team rows (mid-season trades).

  (2) Refactor `PlayerRoster.tsx` (~2950 lines) into a smaller
      shell + extracted `player-roster/internals.tsx`
      + `player-roster/sub-components.tsx`. The 13 sub-components
      (StatsTable, CapHitTable, FantasyPointsTable, MatchupScheduleTable,
      FullScheduleTable, SectionGroup, EmptySlotRow, OpenSlotRow,
      PlayerRow, TradeButton, MegaphoneButton, DropButton, OwnershipCell)
      now live in `sub-components.tsx`; shared types + constants +
      helpers + Context + leaf components live in `internals.tsx`.

      Risks noted:
        • Cyclic import between PlayerRoster.tsx ⇄ sub-components.tsx
          was broken by routing both files through `internals.tsx`.
        • Two RosterConfigContext instances would have desynced the
          Provider from the consumers — fixed by having PlayerRoster.tsx
          import `RosterConfigContext` from `internals.tsx` (aliased
          as `SharedRosterConfigContext`) so the Provider and the
          sub-component consumers share the same identity.
        • PlayerRoster.tsx still contains in-line duplicates of some
          symbols (Player interface, slotEligibility, etc.) for
          backward compat with external consumers that import from
          PlayerRoster directly. A follow-up iter could remove those
          duplicates and have PlayerRoster.tsx re-export from
          internals.tsx.
"""
from pathlib import Path

BACKFILL = Path("/app/backend/scripts/iter182_backfill_season_stats.py")
PLAYER_ROSTER = Path("/app/frontend/src/lovable/components/dashboard/PlayerRoster.tsx")
SUBS = Path("/app/frontend/src/lovable/components/dashboard/player-roster/sub-components.tsx")
INTERNALS = Path("/app/frontend/src/lovable/components/dashboard/player-roster/internals.tsx")


# ── (1) NHL filter + aggregation in season backfill ────────────────

def test_backfill_filters_to_nhl_only():
    src = BACKFILL.read_text()
    # Non-NHL rows are skipped before aggregation.
    assert 'league_abbr = (st.get("leagueAbbrev") or "").upper()' in src
    assert 'if league_abbr != "NHL":' in src
    assert "continue" in src


def test_backfill_aggregates_multiple_rows_per_key():
    src = BACKFILL.read_text()
    # Mid-season trades produce multiple NHL rows for the same
    # (season, gameType) — we now SUM rather than last-wins.
    assert "bucket: dict[tuple[str, str], dict] = {}" in src
    assert 'row["games_played"] += int(st.get("gamesPlayed") or 0)' in src
    assert 'row["goals"] += int(st.get("goals") or 0)' in src
    assert "return list(bucket.values())" in src


# ── (2) PlayerRoster.tsx refactor ──────────────────────────────────

def test_player_roster_main_file_shrunk():
    """The monolith was ~2950 lines pre-refactor. We expect the
    main shell (with sub-components extracted) to be substantially
    smaller — at most 2200 lines. This guards against regression
    where someone inadvertently re-inlines code."""
    lines = PLAYER_ROSTER.read_text().splitlines()
    assert len(lines) < 2200, (
        f"PlayerRoster.tsx is {len(lines)} lines — refactor regressed"
    )


def test_sub_components_file_created_with_all_13_components():
    assert SUBS.exists(), "sub-components.tsx missing"
    src = SUBS.read_text()
    for name in [
        "StatsTable", "CapHitTable", "FantasyPointsTable",
        "MatchupScheduleTable", "FullScheduleTable", "SectionGroup",
        "EmptySlotRow", "OpenSlotRow", "PlayerRow",
        "TradeButton", "MegaphoneButton", "DropButton", "OwnershipCell",
    ]:
        assert f"export const {name} =" in src, f"missing export: {name}"


def test_internals_file_created_with_shared_symbols():
    assert INTERNALS.exists(), "internals.tsx missing"
    src = INTERNALS.read_text()
    # Shared types.
    for ty in ["Player", "RosterSection", "RosterSlot", "RosterSlotType",
               "ViewFilter", "IneligibilityInfo", "HighlightProps",
               "RosterConfigShape"]:
        assert f"export interface {ty}" in src or f"export type {ty}" in src, (
            f"missing type export: {ty}"
        )
    # Shared helpers.
    for fn in ["buildLeagueRosterSlots", "checkIneligibility",
               "isPositionHighlighted", "findHighlightedPlayer",
               "shouldShowOpenSlotForSection", "useRosterConfig"]:
        assert f"export const {fn} =" in src, f"missing helper export: {fn}"
    # Context.
    assert "export const RosterConfigContext = createContext" in src
    # Leaf components.
    for comp in ["TrendIndicator", "PositionBadges", "PositionButton"]:
        assert f"export const {comp} =" in src, f"missing leaf component export: {comp}"


def test_no_cyclic_imports_between_player_roster_and_subs():
    """The cycle-breaking design: PlayerRoster.tsx and
    sub-components.tsx BOTH import from internals.tsx (one-way), so
    neither directly depends on the other at module-init time.
    PlayerRoster.tsx is free to import from sub-components for the
    JSX it renders — but the helpers it needs come from internals."""
    subs_src = SUBS.read_text()
    # Sub-components MUST NOT import from PlayerRoster (the cycle).
    assert 'from "@/lovable/components/dashboard/PlayerRoster"' not in subs_src
    assert "from './PlayerRoster'" not in subs_src
    # They DO import from internals.
    assert 'from "./internals"' in subs_src


def test_shared_context_alias_in_main_so_provider_matches_consumers():
    """If PlayerRoster.tsx defined its own RosterConfigContext while
    sub-components subscribed to internals.tsx's context, the
    Provider would broadcast to nobody. The fix is a deliberate
    alias import so the Provider AND every consumer reference the
    same context identity."""
    src = PLAYER_ROSTER.read_text()
    assert (
        "import { RosterConfigContext as SharedRosterConfigContext } "
        'from "./player-roster/internals";' in src
    )
    assert "<SharedRosterConfigContext.Provider" in src
