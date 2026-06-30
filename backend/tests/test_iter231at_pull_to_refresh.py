"""Iter 231at — Pull-to-refresh on Dashboard + League Home.

User: "Add iOS-style pull-to-refresh on the Dashboard + League Home?
A subtle drag-down gesture would feel native after install and pairs
nicely with the upcoming offline-first cache idea."

Two artefacts:
  • `hooks/use-pull-to-refresh.ts` — lightweight touch-only hook.
    Engages only when the page is at scroll-top, throttles past
    threshold for resistance feel, runs the caller's async refresh,
    snaps back when done.
  • `components/PullToRefreshIndicator.tsx` — the visual chevron /
    spinner that follows the finger and respects `safe-area-inset-top`
    so it never collides with the iOS notch.

Wired into `DashboardPage.jsx` (re-fetches league + week-at-a-glance,
bumps a `reloadTick` to remount data-dependent widgets) and
`LeagueDetailPage.jsx` (bumps `refreshTick` threaded into the main
fetch + matchups effect dep arrays).
"""
from pathlib import Path


HOOK = Path("/app/frontend/src/hooks/use-pull-to-refresh.ts")
INDICATOR = Path("/app/frontend/src/components/PullToRefreshIndicator.tsx")
DASHBOARD = Path("/app/frontend/src/pages/DashboardPage.jsx")
LEAGUE_DETAIL = Path("/app/frontend/src/pages/LeagueDetailPage.jsx")


def test_hook_only_engages_at_scroll_top():
    src = HOOK.read_text()
    # Read scroll position via `window.scrollY` so it covers both
    # `body` and `html` scroll roots — different layouts use different
    # roots and we need the same gesture to work on both.
    assert "window.scrollY || document.documentElement.scrollTop" in src
    # Bail out (no arm) when scrollTop > 0.
    assert "if (scrollTop > 0)" in src
    # Touch-only — touchpads on laptops sometimes synthesize touch
    # events and we DON'T want random drags firing a refresh.
    assert 'if (!("ontouchstart" in window)) return;' in src


def test_hook_applies_resistance_past_threshold():
    src = HOOK.read_text()
    # The eased curve gives the user feedback that they're approaching
    # the release point — a flat linear track feels mushy.
    assert "threshold + (delta - threshold) * 0.4" in src
    # Hard cap so the user can't drag the indicator off-screen.
    assert "Math.min(maxStretch, eased)" in src


def test_hook_passive_false_on_touchmove_to_suppress_chrome_ptr():
    src = HOOK.read_text()
    # Android Chrome ships its own pull-to-refresh. To prevent our
    # gesture being hijacked we need to call preventDefault on
    # touchmove, which requires `passive: false`.
    assert '{ passive: false }' in src
    assert "e.preventDefault()" in src


def test_hook_runs_refresh_and_resets_state():
    src = HOOK.read_text()
    # On release past threshold: snap to threshold position, await
    # the user's `onRefresh`, then clear state.
    assert "if (dist >= threshold)" in src
    assert "await onRefresh()" in src
    # Always clears even on error so a flaky network doesn't lock
    # the indicator open.
    assert "} finally {" in src
    assert "{ distance: 0, refreshing: false, engaged: false }" in src


def test_indicator_respects_safe_area_inset_top():
    src = INDICATOR.read_text()
    # The chevron pill is offset by `safe-area-inset-top` so it
    # never collides with the iOS notch / status bar.
    assert "mt-[max(env(safe-area-inset-top),0.5rem)]" in src
    # Spinner state for the refresh window + chevron rotation for
    # the drag window.
    assert 'data-testid="pull-to-refresh-spinner"' in src
    assert 'data-testid="pull-to-refresh-chevron"' in src
    # ARIA live region so screen-readers announce the state change.
    assert 'aria-live="polite"' in src


def test_dashboard_wires_pull_to_refresh():
    src = DASHBOARD.read_text()
    # Imports both pieces.
    assert "import { usePullToRefresh } from '@/hooks/use-pull-to-refresh';" in src
    assert "import PullToRefreshIndicator from '@/components/PullToRefreshIndicator';" in src
    # `fetchData` extracted to useCallback so PTR can re-trigger it.
    assert "const fetchData = useCallback(async () =>" in src
    # PTR onRefresh re-runs fetchData AND bumps the reloadTick that
    # remounts data-dependent widgets via the page-level `key`.
    assert "await fetchData();" in src
    assert "setReloadTick((t) => t + 1);" in src
    # Indicator rendered above the page content with engaged/distance
    # forwarded.
    assert "<PullToRefreshIndicator distance={ptr.distance} refreshing={ptr.refreshing} engaged={ptr.engaged} />" in src


def test_league_detail_wires_pull_to_refresh():
    src = LEAGUE_DETAIL.read_text()
    assert "import { usePullToRefresh }" in src
    assert "import PullToRefreshIndicator" in src
    # `refreshTick` threaded into the main fetch + matchups effect
    # dep arrays so both re-fire on PTR.
    assert "const [refreshTick, setRefreshTick] = useState(0);" in src
    assert "}, [id, refreshTick]);" in src
    assert "}, [id, isH2H, refreshTick]);" in src
    # Indicator mounted above the page.
    assert "<PullToRefreshIndicator distance={ptr.distance} refreshing={ptr.refreshing} engaged={ptr.engaged} />" in src
