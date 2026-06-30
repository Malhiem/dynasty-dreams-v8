"""Iter 232b — "Last updated · 14s ago" freshness pill on PTR pages.

User: "Add a tiny 'Last updated · 14s ago' timestamp next to the
page title that flashes green briefly after a successful pull-to-
refresh. It would give users immediate confirmation that the gesture
did its job AND tell them how stale the data they're looking at
actually is — useful during a live game day."

Implementation:
  • `LastUpdatedBadge` component lives in
    `frontend/src/components/LastUpdatedBadge.tsx`. Takes a single
    `timestamp` prop (ms epoch). Re-ticks at 1Hz so the relative-
    time string keeps updating without the parent re-rendering.
    Flashes green for ~1500ms whenever `timestamp` changes (i.e.
    after a successful refetch).
  • Wired into the four PTR-enabled pages: Standings, Matchup,
    Dashboard, LeagueDetail. Each page bumps a local
    `lastUpdatedAt = Date.now()` after every successful fetch
    (both the initial mount AND the PTR-initiated refresh).
"""
from pathlib import Path


BADGE = Path("/app/frontend/src/components/LastUpdatedBadge.tsx")
STANDINGS = Path("/app/frontend/src/lovable/pages/Standings.tsx")
MATCHUP = Path("/app/frontend/src/lovable/pages/Matchup.tsx")
DASHBOARD = Path("/app/frontend/src/pages/DashboardPage.jsx")
LEAGUE_DETAIL = Path("/app/frontend/src/pages/LeagueDetailPage.jsx")


def test_last_updated_badge_exists_and_returns_null_when_empty():
    src = BADGE.read_text()
    # Component default-exports for ergonomic import.
    assert "export default function LastUpdatedBadge(" in src
    # Renders nothing when no timestamp yet — avoids layout jumps on
    # the initial render.
    assert "if (!timestamp) return null;" in src


def test_last_updated_badge_ticks_every_second():
    """Relative-time string must keep updating without the parent
    re-rendering. We use a 1Hz interval."""
    src = BADGE.read_text()
    assert "setInterval(() => setNow(Date.now()), 1000)" in src


def test_last_updated_badge_flashes_on_timestamp_change():
    src = BADGE.read_text()
    # Compares against a ref so the initial render does NOT flash.
    assert "prevTsRef" in src
    # 1500ms default green flash window.
    assert "flashMs = 1500" in src
    # data-testid + data-flashing attributes for Playwright.
    assert "data-flashing={flashing ?" in src
    assert 'data-testid={`last-updated-badge' in src


def test_last_updated_badge_formats_relative_buckets():
    """The badge must read naturally at every scale — seconds, minutes,
    hours, days. Verify each branch is present."""
    src = BADGE.read_text()
    assert '"just now"' in src
    assert "${deltaSec}s ago" in src
    assert "${m}m ago" in src
    assert "${h}h ago" in src
    assert "${d}d ago" in src


def test_standings_wires_last_updated_badge():
    src = STANDINGS.read_text()
    assert 'import LastUpdatedBadge from "@/components/LastUpdatedBadge"' in src
    # Timestamp state declared.
    assert "const [lastUpdatedAt, setLastUpdatedAt] = useState<number | null>(null);" in src
    # Bumped after the fetch resolves.
    assert "setLastUpdatedAt(Date.now())" in src
    # Rendered next to the page title.
    assert '<LastUpdatedBadge timestamp={lastUpdatedAt} testIdSuffix="standings" />' in src


def test_matchup_wires_last_updated_badge():
    src = MATCHUP.read_text()
    assert 'import LastUpdatedBadge from "@/components/LastUpdatedBadge"' in src
    assert "const [lastUpdatedAt, setLastUpdatedAt] = useState<number | null>(null);" in src
    # Bumped both on initial mount AND on PTR refresh.
    assert src.count("setLastUpdatedAt(Date.now())") >= 2
    assert '<LastUpdatedBadge timestamp={lastUpdatedAt} testIdSuffix="matchup" />' in src


def test_dashboard_wires_last_updated_badge():
    src = DASHBOARD.read_text()
    assert "import LastUpdatedBadge from '@/components/LastUpdatedBadge'" in src
    assert "const [lastUpdatedAt, setLastUpdatedAt] = useState(null);" in src
    assert "setLastUpdatedAt(Date.now())" in src
    assert '<LastUpdatedBadge timestamp={lastUpdatedAt} testIdSuffix="dashboard" />' in src


def test_league_detail_wires_last_updated_badge():
    src = LEAGUE_DETAIL.read_text()
    assert "import LastUpdatedBadge from '@/components/LastUpdatedBadge'" in src
    assert "const [lastUpdatedAt, setLastUpdatedAt] = useState(null);" in src
    # Bumped both on initial mount AND on PTR refresh.
    assert src.count("setLastUpdatedAt(Date.now())") >= 2
    assert '<LastUpdatedBadge timestamp={lastUpdatedAt} testIdSuffix="league-detail" />' in src
