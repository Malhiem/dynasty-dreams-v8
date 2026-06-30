"""Iter 231au — Wire pull-to-refresh into the Matchup grid + Standings
pages (after the Dashboard + League Home rollout in iter 231at).

Iter 232a — Updated for the correctness rework:
  • `onRefresh` must now actually await the network round-trip — the
    earlier "fire-and-forget setRefreshTick" version snapped the
    spinner back instantly and gave the user no perceptible feedback.
  • For SWR-cached endpoints (`/matchups/...`, `/leagues/.../standings`)
    the refresh request must include `?nocache=1` so the service
    worker bypasses its cache instead of serving the stale copy.
"""
from pathlib import Path


MATCHUP = Path("/app/frontend/src/lovable/pages/Matchup.tsx")
STANDINGS = Path("/app/frontend/src/lovable/pages/Standings.tsx")


def test_matchup_page_wires_pull_to_refresh():
    src = MATCHUP.read_text()
    # Imports.
    assert 'import { usePullToRefresh } from "@/hooks/use-pull-to-refresh";' in src
    assert 'import PullToRefreshIndicator from "@/components/PullToRefreshIndicator";' in src
    # Refresh tick still drives the existing fetch effects.
    assert "const [refreshTick, setRefreshTick] = useState(0);" in src
    # The refresh must force a SW cache bypass on the matchups GET.
    assert "/matchups/${league.id}/current-week?nocache=1" in src
    # And must actually await the underlying fetches (not the old
    # fire-and-forget setRefreshTick that resolved instantly).
    assert "await Promise.all(tasks)" in src
    # Live-scoring rails are pulled directly inside onRefresh so the
    # spinner reflects the real network duration.
    assert "/live-scoring/team/${focusedMyTeam.id}" in src
    assert "/live-scoring/team/${opponentTeam.id}" in src
    # Existing tick-driven effects remain in place.
    assert "}, [league, refreshTick]);" in src
    assert "}, [focusedMyTeam, refreshTick]);" in src
    assert "}, [opponentTeam, refreshTick]);" in src
    # Indicator mounted above content.
    assert "<PullToRefreshIndicator distance={ptr.distance} refreshing={ptr.refreshing} engaged={ptr.engaged} />" in src


def test_standings_page_wires_pull_to_refresh():
    src = STANDINGS.read_text()
    assert 'import { usePullToRefresh } from "@/hooks/use-pull-to-refresh";' in src
    assert 'import PullToRefreshIndicator from "@/components/PullToRefreshIndicator";' in src
    # Refactored into a memoized async fetcher so PTR can await it.
    assert "const fetchStandings = useCallback" in src
    # The forced (PTR-initiated) fetch must include `?nocache=1` so the
    # service worker bypasses stale-while-revalidate and the user
    # actually sees fresh W/L/T values.
    assert '`/leagues/${leagueId}/standings${force ? "?nocache=1" : ""}`' in src
    assert "onRefresh: async () => { await fetchStandings(true); }" in src
    # Initial mount loads via the same fetcher (no force).
    assert "await fetchStandings(false);" in src
    assert "<PullToRefreshIndicator distance={ptr.distance} refreshing={ptr.refreshing} engaged={ptr.engaged} />" in src
