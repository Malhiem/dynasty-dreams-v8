import { useEffect, useState, useCallback, useRef } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import api from '@/lib/api';
import { AppLayout } from '@/components/layout/AppLayout';
import { StatCard } from '@/components/ui/stat-card';
import { DataTable } from '@/components/ui/data-table';
import { Button } from '@/components/ui/button';
import RecommendedForYou from '@/components/RecommendedForYou';
import MyLeaguesOrderedList from '@/components/MyLeaguesOrderedList';
import LiveScoringWidget from '@/components/LiveScoringWidget';
import PendingTradesBanner from '@/components/PendingTradesBanner';
import { useActiveLeague } from '@/hooks/use-active-league';
import MyWeekAtAGlance from '@/components/MyWeekAtAGlance';
import YourActivityWidget from '@/components/YourActivityWidget';
// Iter 232N.5 — Cross-league player status feed on the dashboard.
import { PlayerStatusFeed } from '@/components/player/PlayerStatusFeed';
// Iter 232N.7 — Cross-league mover leaderboard widget.
import { LeagueMoversWidget } from '@/components/player/LeagueMoversWidget';
import FantasyLevelBadge from '@/components/FantasyLevelBadge';
import { usePullToRefresh } from '@/hooks/use-pull-to-refresh';
import PullToRefreshIndicator from '@/components/PullToRefreshIndicator';
// Iter 232b — "Last updated · 14s ago" freshness pill.
import LastUpdatedBadge from '@/components/LastUpdatedBadge';
import { Trophy, Users, Calendar, Rocket, Plus, ArrowRight } from '@phosphor-icons/react';
import { SortableSections, SortableSection } from '@/components/SortableSections';

// Iter 232N.16 — Dashboard widget registry.
//   • `id`: stable key used both as the localStorage entry AND the
//     `data-testid` suffix. Never rename after ship.
//   • `render`: pure component, no props — each widget is a
//     self-contained data island.
// Ordering is user-configurable; the default order is what everyone
// sees on first load. "My Leagues" is intentionally at position 0 so
// managers can jump straight into a league on page load.
const DASHBOARD_WIDGET_ORDER_KEY = "dd_dashboard_widget_order_v1";
const DASHBOARD_WIDGETS = [
  { id: "my-leagues", render: () => <MyLeaguesOrderedList /> },
  { id: "pending-trades", render: () => <PendingTradesBanner /> },
  { id: "week-at-a-glance", render: () => <MyWeekAtAGlance /> },
  { id: "your-activity", render: () => (
    <div><YourActivityWidget /></div>
  ) },
  { id: "live-scoring", render: () => <LiveScoringWidget /> },
  { id: "player-status", render: () => (
    <div className="surface p-4">
      <PlayerStatusFeed
        scope="user"
        days={14}
        heading="Player status updates across your leagues"
        emptyMessage="No player status changes in the last 14 days across your teams."
      />
    </div>
  ) },
  { id: "league-movers", render: () => (
    <div className="surface p-4">
      <LeagueMoversWidget heading="League movers · last 7 days" limit={5} />
    </div>
  ) },
];

function loadWidgetOrder() {
  try {
    const raw = localStorage.getItem(DASHBOARD_WIDGET_ORDER_KEY);
    if (!raw) return DASHBOARD_WIDGETS.map((w) => w.id);
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return DASHBOARD_WIDGETS.map((w) => w.id);
    // Drop unknown ids + append any new widgets we shipped after this
    // user last saved their order (so new additions surface at the
    // bottom rather than vanish silently).
    const known = new Set(DASHBOARD_WIDGETS.map((w) => w.id));
    const filtered = parsed.filter((id) => known.has(id));
    for (const w of DASHBOARD_WIDGETS) {
      if (!filtered.includes(w.id)) filtered.push(w.id);
    }
    return filtered;
  } catch {
    return DASHBOARD_WIDGETS.map((w) => w.id);
  }
}

export default function DashboardPage() {
  const { user } = useAuth();
  const { league: activeLeague } = useActiveLeague();
  const [stats, setStats] = useState({ leagues: 0, teams: 0, upcoming: 0 });
  const [leagues, setLeagues] = useState([]);
  const [loading, setLoading] = useState(true);
  // Iter 231at — Bump a reload tick to force every dependent widget
  // (LiveScoringWidget, MyWeekAtAGlance, etc.) to re-fetch. Cheaper
  // than threading a refresh handle into each child.
  const [reloadTick, setReloadTick] = useState(0);
  // Iter 232b — Freshness timestamp for the LastUpdatedBadge.
  const [lastUpdatedAt, setLastUpdatedAt] = useState(null);
  // Iter 232N.16 — Persisted widget order (drag-and-drop across all
  // widget sections). Layout preference is per-user server-side (iter
  // 232N.19) with localStorage as first-paint cache + offline fallback.
  const [widgetOrder, setWidgetOrder] = useState(() => loadWidgetOrder());
  const layoutSaveTimer = useRef(null);
  const handleWidgetReorder = useCallback((next) => {
    setWidgetOrder(next);
    try { localStorage.setItem(DASHBOARD_WIDGET_ORDER_KEY, JSON.stringify(next)); } catch { /* noop */ }
    // Iter 232N.19 — Debounced server sync so a rapid drag flurry
    // fires one PATCH instead of N. 400ms is long enough for a
    // multi-move reorder to settle without feeling laggy.
    if (layoutSaveTimer.current) clearTimeout(layoutSaveTimer.current);
    layoutSaveTimer.current = setTimeout(() => {
      api.patch("/users/me/dashboard-layout", { widget_order: next })
        .catch(() => { /* offline / auth blip — localStorage is authoritative */ });
    }, 400);
  }, []);
  // Iter 232N.19 — On mount, hydrate the order from the server.
  // If the server has a saved layout, it wins over localStorage so
  // desktop → mobile handoffs match. If not, we keep the local
  // default. Runs once per session (no polling).
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const { data } = await api.get("/users/me/dashboard-layout");
        if (cancelled) return;
        const remote = Array.isArray(data?.widget_order) ? data.widget_order : [];
        if (remote.length === 0) return;  // nothing saved server-side
        // Reconcile against the registry the same way loadWidgetOrder
        // does — drops unknown ids, appends any newer widgets so users
        // whose saved order predates a shipped widget still see it.
        const known = new Set(DASHBOARD_WIDGETS.map((w) => w.id));
        const filtered = remote.filter((id) => known.has(id));
        for (const w of DASHBOARD_WIDGETS) {
          if (!filtered.includes(w.id)) filtered.push(w.id);
        }
        setWidgetOrder(filtered);
        try { localStorage.setItem(DASHBOARD_WIDGET_ORDER_KEY, JSON.stringify(filtered)); } catch { /* noop */ }
      } catch { /* offline / unauth — keep local */ }
    })();
    return () => { cancelled = true; };
  }, []);
  // Iter 232N.17 — Customize-layout mode. When ON, every widget gets a
  // dashed cyan outline + a big pulsing grip handle so users discover
  // that the whole dashboard is drag-to-reorder. Off by default.
  const [customizing, setCustomizing] = useState(false);

  const fetchData = useCallback(async (force = false) => {
    try {
      // Iter 230g — `/teams?owner_id=me` returns the user's actual teams
      // (including co-owned, excluding archived/test leagues), so the
      // "Total Teams" stat reflects the dashboard's Week at a Glance
      // exactly. Falls back to summing league.current_teams ONLY if
      // the dedicated endpoint isn't available.
      // Iter 232a — `force=true` (pull-to-refresh path) appends
      // `?nocache=1` to the service-worker-cached week-at-a-glance
      // request so the user actually sees fresh data, not the
      // stale-while-revalidate copy.
      const wagPath = force
        ? '/users/me/week-at-a-glance?nocache=1'
        : '/users/me/week-at-a-glance';
      const [leaguesRes, wagRes] = await Promise.all([
        api.get('/leagues?my_leagues=true'),
        api.get(wagPath).catch(() => ({ data: { summaries: [] } })),
      ]);
      setLeagues(leaguesRes.data);
      const myTeamsCount = (wagRes.data?.summaries || []).length;
      setStats({
        leagues: leaguesRes.data.length,
        teams: myTeamsCount,
        upcoming: leaguesRes.data.filter(l => l.status === 'setup').length
      });
      setLastUpdatedAt(Date.now());
    } catch (err) {
      console.error('Failed to fetch dashboard data', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Iter 231at — Pull-to-refresh wiring. The hook is a no-op on
  // non-touch devices, so desktop users keep their existing flow.
  const ptr = usePullToRefresh({
    onRefresh: async () => {
      await fetchData(true);
      setReloadTick((t) => t + 1);
    },
  });

  const leagueColumns = [
    {
      key: 'name',
      label: 'League Name',
      render: (v, row) => (
        <Link
          to={`/leagues/${row.id}`}
          data-testid={`dashboard-league-link-${row.id}`}
          className="text-white hover:text-[#00D2FF] font-semibold"
        >
          {v}
        </Link>
      ),
    },
    { key: 'format', label: 'Format', render: (v) => v?.replace('_', ' ').toUpperCase() },
    { key: 'scoring_format', label: 'Scoring', render: (v) => v?.replace(/_/g, ' ').toUpperCase() },
    { key: 'current_teams', label: 'Teams', render: (v, row) => `${v}/${row.max_teams}` },
    { key: 'status', label: 'Status', render: (v) => (
      <span className={`badge ${v === 'active' ? 'badge-success' : v === 'setup' ? 'badge-warning' : 'badge-info'}`}>
        {v}
      </span>
    )}
  ];

  return (
    <AppLayout>
    <PullToRefreshIndicator distance={ptr.distance} refreshing={ptr.refreshing} engaged={ptr.engaged} />
    <div data-testid="dashboard-page" key={reloadTick}>
      <div className="max-w-7xl mx-auto">
        {/* Welcome Section */}
        <div className="mb-6 sm:mb-8 flex items-start justify-between gap-4 flex-wrap">
          <div className="flex-1 min-w-0">
            {/* Iter 231k — Mobile-friendly heading: text-3xl on small screens
                so "WELCOME BACK, <USERNAME>" fits on 1-2 lines instead of 3+. */}
            <h1 className="font-heading text-3xl sm:text-4xl lg:text-5xl font-bold tracking-tight text-white mb-2">
              WELCOME BACK, {user?.name?.toUpperCase()}
            </h1>
            <div className="flex items-center gap-2 flex-wrap">
              <p className="text-sm sm:text-base text-[#A1A1AA]">Here&apos;s your dynasty at a glance</p>
              {/* Iter 232b — Last-updated pill (flashes green after a
                  successful pull-to-refresh). */}
              <LastUpdatedBadge timestamp={lastUpdatedAt} testIdSuffix="dashboard" />
            </div>
            {/* Iter 232N.18 — Customize button inline under the tagline
                on mobile so it stays in the initial viewport without
                being pushed below the Fantasy Level card. Hidden here on
                sm+ where the desktop copy renders next to the badge. */}
            <button
              type="button"
              onClick={() => setCustomizing((v) => !v)}
              className={`mt-3 sm:hidden inline-flex items-center gap-2 rounded-md px-3 py-1.5 text-xs font-semibold uppercase tracking-wider border transition-colors ${
                customizing
                  ? "bg-[#00D2FF] text-black border-[#00D2FF]"
                  : "bg-transparent border-white/15 text-[#A1A1AA]"
              }`}
              data-testid="dashboard-customize-toggle-mobile"
              aria-pressed={customizing}
            >
              <span>{customizing ? "Done" : "Customize layout"}</span>
            </button>
          </div>
          <div className="w-full sm:w-80 flex flex-col items-end gap-2 order-last sm:order-none">
            <FantasyLevelBadge />
            {/* Iter 232N.17 — Customize layout button. Toggles a
                reorder mode where every widget gets a dashed outline
                + a pulsing grip so the drag affordance is obvious.
                Iter 232N.18 — Hidden on mobile (see the inline copy
                above the Fantasy Level card) so the button stays
                above-the-fold on small screens. */}
            <button
              type="button"
              onClick={() => setCustomizing((v) => !v)}
              className={`hidden sm:inline-flex items-center gap-2 rounded-md px-3 py-1.5 text-xs font-semibold uppercase tracking-wider border transition-colors ${
                customizing
                  ? "bg-[#00D2FF] text-black border-[#00D2FF]"
                  : "bg-transparent border-white/15 text-[#A1A1AA] hover:text-white hover:border-white/40"
              }`}
              data-testid="dashboard-customize-toggle"
              aria-pressed={customizing}
            >
              <span>{customizing ? "Done" : "Customize layout"}</span>
            </button>
          </div>
        </div>

        {customizing && (
          <div
            className="mb-6 rounded-lg border border-[#00D2FF]/40 bg-[#00D2FF]/10 px-4 py-3 text-sm text-[#00D2FF] flex items-start gap-3"
            data-testid="dashboard-customize-hint"
          >
            <span className="text-lg">↕</span>
            <div>
              <p className="font-semibold">Reorder mode</p>
              <p className="text-[#00D2FF]/80 text-xs mt-0.5">
                Drag any section by its highlighted handle to reorder
                the dashboard. Preferences save automatically. Click
                <span className="font-semibold text-white/90"> Done </span>
                when finished.
              </p>
            </div>
          </div>
        )}

        {/* Iter 232N.16 + 232N.17 — Sortable widget stack. Now the
            FIRST content after the welcome header, so managers see
            "My Leagues" (the default top entry) immediately without
            scrolling past a huge Pending Trades banner. The banner
            itself is now part of the sortable set — users can drag it
            below My Leagues (default) or hoist it back up if they
            prefer trade-first triage. */}
        <SortableSections
          ids={widgetOrder}
          onReorder={handleWidgetReorder}
          customize={customizing}
        >
          {widgetOrder.map((id) => {
            const widget = DASHBOARD_WIDGETS.find((w) => w.id === id);
            if (!widget) return null;
            return (
              <SortableSection key={id} id={id} className="mb-8">
                {widget.render()}
              </SortableSection>
            );
          })}
        </SortableSections>

        {/* Stats Grid */}
        <div className="control-room-grid mb-8">
          <StatCard label="My Leagues" value={stats.leagues} icon={Trophy} />
          <StatCard label="Total Teams" value={stats.teams} icon={Users} />
          <StatCard label="Upcoming Drafts" value={stats.upcoming} icon={Calendar} />
          <StatCard label="Win Rate" value="--" icon={Rocket} />
        </div>

        {/* Quick Actions */}
        <div className="flex flex-wrap gap-4 mb-8">
          <Link to="/leagues/create">
            <Button data-testid="create-league-btn" className="bg-[#00D2FF] text-black hover:bg-[#33DBFF]">
              <Plus size={18} className="mr-2" />
              Create League
            </Button>
          </Link>
          <Link to="/leagues">
            <Button variant="outline" data-testid="browse-leagues-btn" className="border-white/10 text-white hover:bg-white/5">
              Browse Leagues
              <ArrowRight size={18} className="ml-2" />
            </Button>
          </Link>
        </div>

        {/* Iter 232N.16 — Sortable widget stack moved above (see the
            block just after the header). The stats grid + quick
            actions sit BELOW leagues now so managers land on the
            "pick a league" path first. */}

        {/* My Leagues Table */}
        <div className="mb-8">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-heading text-2xl font-bold text-white">MY LEAGUES</h2>
            <Link to="/leagues" className="text-[#00D2FF] text-sm hover:underline">View All</Link>
          </div>
          {loading ? (
            <div className="surface p-8 text-center text-[#A1A1AA]">
              Loading leagues...
            </div>
          ) : leagues.length === 0 ? (
            <div className="surface p-8 text-center">
              <Trophy size={48} className="text-[#52525B] mx-auto mb-4" />
              <h3 className="text-white font-semibold mb-2">No leagues yet</h3>
              <p className="text-[#A1A1AA] mb-4">Create your first league or join an existing one</p>
              <Link to="/leagues/create">
                <Button className="bg-[#00D2FF] text-black hover:bg-[#33DBFF]">Create League</Button>
              </Link>
            </div>
          ) : (
            <DataTable
              columns={leagueColumns}
              data={leagues}
              testId="my-leagues-table"
            />
          )}
        </div>
      </div>
    </div>
    </AppLayout>
  );
}
