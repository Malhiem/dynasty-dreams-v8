"""Iter 231au — Wire pull-to-refresh into the Matchup grid + Standings
pages (after the Dashboard + League Home rollout in iter 231at).

Same hook, same indicator — a 5-line drop-in per page:
  • Import `usePullToRefresh` + `<PullToRefreshIndicator />`.
  • `useState<number>(0)` for the refresh tick.
  • `const ptr = usePullToRefresh({ onRefresh: () => setRefreshTick(t => t + 1) })`.
  • Thread `refreshTick` into every relevant fetch effect's dep array.
  • Mount `<PullToRefreshIndicator … />` above the page content.

Pairs naturally with the upcoming offline-first cache: PTR forces a
network round-trip while regular navigation can serve from the SW
cache. Each page must use the same hook + indicator so the gesture
behaves identically everywhere.
"""
from pathlib import Path


MATCHUP = Path("/app/frontend/src/lovable/pages/Matchup.tsx")
STANDINGS = Path("/app/frontend/src/lovable/pages/Standings.tsx")


def test_matchup_page_wires_pull_to_refresh():
    src = MATCHUP.read_text()
    # Imports.
    assert 'import { usePullToRefresh } from "@/hooks/use-pull-to-refresh";' in src
    assert 'import PullToRefreshIndicator from "@/components/PullToRefreshIndicator";' in src
    # State + hook invocation.
    assert "const [refreshTick, setRefreshTick] = useState(0);" in src
    assert "onRefresh: async () => setRefreshTick((t) => t + 1)" in src
    # Threaded into every fetch effect — current-week matchups, my-team
    # live scoring, opponent live scoring.
    assert "}, [league, refreshTick]);" in src
    assert "}, [focusedMyTeam, refreshTick]);" in src
    assert "}, [opponentTeam, refreshTick]);" in src
    # Indicator mounted above content.
    assert "<PullToRefreshIndicator distance={ptr.distance} refreshing={ptr.refreshing} engaged={ptr.engaged} />" in src


def test_standings_page_wires_pull_to_refresh():
    src = STANDINGS.read_text()
    assert 'import { usePullToRefresh } from "@/hooks/use-pull-to-refresh";' in src
    assert 'import PullToRefreshIndicator from "@/components/PullToRefreshIndicator";' in src
    assert "const [refreshTick, setRefreshTick] = useState(0);" in src
    # Standings effect now re-fires on PTR — pulls fresh W/L/T + cap
    # remaining numbers from /api/leagues/{id}/standings.
    assert "}, [leagueId, refreshTick]);" in src
    assert "<PullToRefreshIndicator distance={ptr.distance} refreshing={ptr.refreshing} engaged={ptr.engaged} />" in src
