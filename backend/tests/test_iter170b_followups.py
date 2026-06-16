"""Iter 170b/c — Lock the three follow-up enhancements:

(a) DraftRoom real-league wiring: replace mock `leagueTeams` with the
    active league's `liveTeams` so columns + snake order + counter all
    use real team ids.
(b) TransactionsPage filters: per-team chips + date range, applied to
    All / Pending / Accepted tabs.
(c) Roster limits endpoint + Settings card persisting `roster_limits`
    on the league document.
"""
from pathlib import Path

DRAFT_ROOM = Path("/app/frontend/src/lovable/pages/DraftRoom.tsx")
TRANSACTIONS = Path("/app/frontend/src/lovable/pages/Transactions.tsx")
ROSTER_LIMITS_CARD = Path("/app/frontend/src/lovable/pages/commissioner/RosterLimitsCard.tsx")
LEAGUE_SETUP_TAB = Path("/app/frontend/src/lovable/pages/commissioner/tabs/LeagueSetupTab.tsx")
LEAGUES_ROUTE = Path("/app/backend/routes/leagues.py")


# ────────────────────────── (a) DraftRoom wiring ──────────────────────────


def test_draftroom_renames_mock_constants():
    """Module-level mock array is renamed; the in-component `leagueTeams`
    binding from `useActiveLeague()` is the only live one."""
    src = DRAFT_ROOM.read_text()
    assert "const mockLeagueTeams = [" in src, "mock data must be renamed so live `liveTeams` is unambiguous"
    # The legacy module-level `const leagueTeams = [` must be gone.
    assert "\nconst leagueTeams = [" not in src
    assert "\nconst teamAbbrs =" not in src


def test_draftroom_derives_board_from_live_teams():
    src = DRAFT_ROOM.read_text()
    # The new derivation uses liveTeams when present, falls back to
    # mockLeagueTeams otherwise.
    assert "const boardTeams = useMemo" in src
    assert "Array.isArray(liveTeams) && liveTeams.length > 0" in src
    assert "return mockLeagueTeams" in src
    # Derived abbr list + totalTeams come from boardTeams.
    assert "const boardTeamAbbrs = useMemo(() => boardTeams.map" in src
    assert "const totalTeams = boardTeams.length" in src


def test_draftroom_counter_prefers_id_match():
    src = DRAFT_ROOM.read_text()
    block = src.split("picksUntilMyTurn")[1].split("}, [")[0]
    # When liveTeams are present, match by team id directly.
    assert "boardTeams.find((t) => t.id && t.id === (myTeam as any).id)" in block


# ────────────────────────── (b) Transactions filters ──────────────────────


def test_transactions_filter_state_present():
    src = TRANSACTIONS.read_text()
    assert "selectedTeamIds" in src and "useState<Set<string>>(new Set())" in src
    assert 'const [dateFrom, setDateFrom] = useState<string>("")' in src
    assert 'const [dateTo, setDateTo] = useState<string>("")' in src


def test_transactions_filter_ui_present():
    src = TRANSACTIONS.read_text()
    assert 'data-testid="transactions-filters"' in src
    assert 'data-testid="transactions-team-chips"' in src
    assert 'data-testid="transactions-date-from"' in src
    assert 'data-testid="transactions-date-to"' in src
    assert 'data-testid="transactions-filters-clear"' in src
    assert "transactions-team-chip-" in src


def test_transactions_filters_applied_to_rows():
    src = TRANSACTIONS.read_text()
    # The all-trades memo must consume the filter state.
    assert "if (selectedTeamIds.size > 0)" in src
    assert "if (dateFrom || dateTo)" in src
    # The team filter must check either side of the trade.
    assert "_proposerId && selectedTeamIds.has(_proposerId)" in src
    assert "_targetId && selectedTeamIds.has(_targetId)" in src


# ────────────────────────── (c) Roster limits ─────────────────────────────


def test_roster_limits_card_exists_and_uses_endpoint():
    src = ROSTER_LIMITS_CARD.read_text()
    assert 'data-testid="roster-limits-card"' in src
    assert "/leagues/${leagueId}/roster-limits" in src
    # All 5 fields rendered.
    for key in ("starting_skaters", "starting_goalies", "bench", "ir", "minors"):
        assert f"key: \"{key}\"" in src or f'"{key}"' in src
        assert f'data-testid={{`roster-limit-input-${{f.key}}`}}' in src or f'roster-limit-input-{key}' in src
    assert 'data-testid="roster-limits-save"' in src
    assert 'data-testid="roster-limits-reset"' in src


def test_league_setup_tab_mounts_roster_limits_card():
    src = LEAGUE_SETUP_TAB.read_text()
    assert "import RosterLimitsCard" in src
    assert "<RosterLimitsCard" in src
    assert "leagueId={p.activeLeague.id}" in src


def test_backend_roster_limits_endpoints_defined():
    src = LEAGUES_ROUTE.read_text()
    assert '@router.get("/leagues/{league_id}/roster-limits")' in src
    assert '@router.put("/leagues/{league_id}/roster-limits")' in src
    # Validation rules: 0..50 + integer coercion.
    assert "must be between 0 and 50" in src
    assert "must be an integer" in src
    # Persists on league.roster_limits.
    assert '"roster_limits": new_limits' in src
    # Audit log entry on change.
    assert '"action": "roster_limits_updated"' in src
