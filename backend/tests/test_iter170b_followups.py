"""Iter 170b/c — Lock the three follow-up enhancements:

(a) DraftRoom real-league wiring: replace mock `leagueTeams` with the
    active league's `liveTeams` so columns + snake order + counter all
    use real team ids.
(b) TransactionsPage filters: per-team chips + date range, applied to
    All / Pending / Accepted tabs.
(c) Roster limits endpoint + Settings card persisting `roster_limits`
    on the league document.
"""
from tests.source_tree import read_source
from pathlib import Path

DRAFT_ROOM_PATH = Path("/app/frontend/src/lovable/pages/DraftRoom.tsx")
# Iter 231 — DraftRoom logic decomposed across draftroom/* + hooks/use-draft-*;
# use the shared shim for assertions that target the broader draft-room family
# (e.g. mock constants moved to /draftroom/mocks.ts).
from tests._draftroom_sources import DraftRoomFamilyShim
DRAFT_ROOM = DraftRoomFamilyShim()
TRANSACTIONS = Path("/app/frontend/src/lovable/pages/Transactions.tsx")
# Iter 231e — RosterLimitsCard.tsx + its LeagueSetupTab mount were deleted
# (orphan since iter 228i moved roster-limits config to League Admin →
# Rosters). The backend endpoints remain wired and used by the Roster
# Monitor.
LEAGUE_SETUP_TAB = Path("/app/frontend/src/lovable/pages/commissioner/tabs/LeagueSetupTab.tsx")
LEAGUES_ROUTE = Path("/app/backend/routes/leagues.py")


# ────────────────────────── (a) DraftRoom wiring ──────────────────────────


def test_draftroom_renames_mock_constants():
    """Module-level mock array is renamed; the in-component `leagueTeams`
    binding from `useActiveLeague()` is the only live one."""
    src = read_source(DRAFT_ROOM, include_imports=False)
    assert "const mockLeagueTeams = [" in src, "mock data must be renamed so live `liveTeams` is unambiguous"
    # The legacy module-level `const leagueTeams = [` must be gone.
    assert "\nconst leagueTeams = [" not in src
    assert "\nconst teamAbbrs =" not in src


def test_draftroom_derives_board_from_live_teams():
    src = read_source(DRAFT_ROOM)
    # The new derivation uses liveTeams when present, falls back to
    # mockLeagueTeams otherwise.
    assert "const boardTeams = useMemo" in src
    assert "Array.isArray(liveTeams) && liveTeams.length > 0" in src
    assert "return mockLeagueTeams" in src
    # Derived abbr list + totalTeams come from boardTeams.
    assert "const boardTeamAbbrs = useMemo(() => boardTeams.map" in src
    assert "const totalTeams = boardTeams.length" in src


def test_draftroom_counter_prefers_id_match():
    src = read_source(DRAFT_ROOM)
    # Iter 231 — the picks-until-my-turn lookup lives in the
    # use-draft-picks-until-my-turn hook now; just confirm the
    # id-match line is present anywhere in the draft-room family.
    assert "boardTeams.find((t) => t.id && t.id === (myTeam as any).id)" in src


# ────────────────────────── (b) Transactions filters ──────────────────────


def test_transactions_filter_state_present():
    src = read_source(TRANSACTIONS)
    assert "selectedTeamIds" in src and "useState(new Set())" in src
    assert 'const [dateFrom, setDateFrom] = useState("")' in src
    assert 'const [dateTo, setDateTo] = useState("")' in src


def test_transactions_filter_ui_present():
    src = read_source(TRANSACTIONS)
    assert 'data-testid="transactions-filters"' in src
    assert 'data-testid="transactions-team-chips"' in src
    assert 'data-testid="transactions-date-from"' in src
    assert 'data-testid="transactions-date-to"' in src
    assert 'data-testid="transactions-filters-clear"' in src
    assert "transactions-team-chip-" in src


def test_transactions_filters_applied_to_rows():
    src = read_source(TRANSACTIONS)
    # The all-trades memo must consume the filter state.
    assert "if (selectedTeamIds.size > 0)" in src
    assert "if (dateFrom || dateTo)" in src
    # The team filter must check either side of the trade.
    assert "_proposerId && selectedTeamIds.has(_proposerId)" in src
    assert "_targetId && selectedTeamIds.has(_targetId)" in src


# ────────────────────────── (c) Roster limits ─────────────────────────────
# Iter 231e — The standalone RosterLimitsCard frontend component was
# DELETED. The functional UI for roster size + position breakdown lives
# under League Administration → Rosters (iter 228i moved it there;
# `commissioner/RosterLimitsCard.tsx` was orphan code with no mount).
# The backend `/leagues/{id}/roster-limits` endpoints are still alive
# (consumed by `routes/monitors.py`) — only the standalone card UI was
# removed. The card-mount-in-LeagueSetupTab assertion has been deleted
# along with the file.


def test_backend_roster_limits_endpoints_defined():
    src = read_source(LEAGUES_ROUTE)
    assert '@router.get("/leagues/{league_id}/roster-limits")' in src
    assert '@router.put("/leagues/{league_id}/roster-limits")' in src
    # Validation rules: 0..50 + integer coercion.
    assert "must be between 0 and 50" in src
    assert "must be an integer" in src
    # Persists on league.roster_limits.
    assert '"roster_limits": new_limits' in src
    # Audit log entry on change.
    assert '"action": "roster_limits_updated"' in src
