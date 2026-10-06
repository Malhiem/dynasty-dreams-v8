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
from tests.source_tree import read_source
from pathlib import Path


HOOK = Path("/app/frontend/src/hooks/use-pull-to-refresh.ts")
INDICATOR = Path("/app/frontend/src/components/PullToRefreshIndicator.tsx")
DASHBOARD = Path("/app/frontend/src/pages/DashboardPage.jsx")
LEAGUE_DETAIL = Path("/app/frontend/src/pages/LeagueDetailPage.jsx")


def test_hook_only_engages_at_scroll_top():
    src = read_source(HOOK)
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
    src = read_source(HOOK)
    # The eased curve gives the user feedback that they're approaching
    # the release point — a flat linear track feels mushy.
    assert "threshold + (delta - threshold) * 0.4" in src
    # Hard cap so the user can't drag the indicator off-screen.
    assert "Math.min(maxStretch, eased)" in src


def test_hook_passive_false_on_touchmove_to_suppress_chrome_ptr():
    src = read_source(HOOK)
    # Android Chrome ships its own pull-to-refresh. To prevent our
    # gesture being hijacked we need to call preventDefault on
    # touchmove, which requires `passive: false`.
    assert '{ passive: false }' in src
    assert "e.preventDefault()" in src


def test_hook_runs_refresh_and_resets_state():
    src = read_source(HOOK)
    # On release past threshold: snap to threshold position, await
    # the user's `onRefresh`, then clear state.
    assert "if (dist >= threshold)" in src
    # Iter 232a — the caller's `onRefresh` is invoked through a ref so
    # stale closures from re-rendering parents don't run an outdated
    # version (e.g., before `leagueId` resolved).
    assert "await onRefreshRef.current()" in src
    # Always clears even on error so a flaky network doesn't lock
    # the indicator open.
    assert "} finally {" in src
    assert "{ distance: 0, refreshing: false, engaged: false }" in src


def test_hook_uses_distance_ref_to_avoid_stale_closure():
    """Iter 232a — the touchend handler must read the *live* drag
    distance from a ref, not the React-state closure. Reading
    `state.distance` through the effect's closure could lag the most
    recent touchmove by one commit, which caused the gesture to fail
    silently ("icon appears but nothing refreshes")."""
    src = read_source(HOOK)
    assert "const distanceRef = useRef(0);" in src
    # onEnd reads from the ref, not state.
    assert "const dist = distanceRef.current;" in src
    # And the effect no longer keeps `state.distance` in its dep
    # array — otherwise listeners rebind on every pixel of drag.
    assert "[enabled, threshold, maxStretch, minSpinnerMs]" in src


def test_hook_enforces_minimum_spinner_window():
    """Iter 232a — a SW-cached endpoint can resolve in <50ms, which
    snaps the spinner away before the user perceives it. Enforce a
    perception floor so the gesture always *feels* like it did
    something."""
    src = read_source(HOOK)
    assert "minSpinnerMs" in src
    assert "Date.now() - startedAt" in src
    assert "setTimeout(r, minSpinnerMs - elapsed)" in src


def test_indicator_respects_safe_area_inset_top():
    src = read_source(INDICATOR)
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
    src = read_source(DASHBOARD)
    # Imports both pieces.
    assert "import { usePullToRefresh } from '@/hooks/use-pull-to-refresh';" in src
    assert "import PullToRefreshIndicator from '@/components/PullToRefreshIndicator';" in src
    # `fetchData` extracted to useCallback so PTR can re-trigger it.
    assert "const fetchData = useCallback(async (_force = false) =>" in src
    # Iter 232a — pull-to-refresh path forces the SW to bypass its
    # stale-while-revalidate cache for the week-at-a-glance call.
    assert 'key={reloadTick}' in src
    assert '/users/me/week-at-a-glance' in src
    # PTR onRefresh re-runs fetchData(force=true) AND bumps the reloadTick
    # that remounts data-dependent widgets via the page-level `key`.
    assert "await fetchData(true);" in src
    assert "setReloadTick((t) => t + 1);" in src
    # Indicator rendered above the page content with engaged/distance
    # forwarded.
    assert "<PullToRefreshIndicator distance={ptr.distance} refreshing={ptr.refreshing} engaged={ptr.engaged} />" in src


def test_league_detail_wires_pull_to_refresh():
    src = read_source(LEAGUE_DETAIL)
    assert "import { usePullToRefresh }" in src
    assert "import PullToRefreshIndicator" in src
    # `refreshTick` threaded into the main fetch + matchups effect
    # dep arrays so both re-fire on PTR.
    assert "const [refreshTick, setRefreshTick] = useState(0);" in src
    assert "}, [id, refreshTick]);" in src
    assert "}, [id, isH2H, refreshTick]);" in src
    # Iter 232a — PTR awaits explicit refreshed network calls that
    # bypass the SW cache, so the spinner reflects real round-trip
    # time and the displayed data is genuinely fresh.
    assert "/leagues/${id}/standings?nocache=1" in src
    assert "/matchups/${id}/current-week?nocache=1" in src
    assert "await Promise.all(tasks)" in src
    # Indicator mounted above the page.
    assert "<PullToRefreshIndicator distance={ptr.distance} refreshing={ptr.refreshing} engaged={ptr.engaged} />" in src
