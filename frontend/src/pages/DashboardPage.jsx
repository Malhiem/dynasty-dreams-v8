import { useEffect, useState, useCallback } from 'react';
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
          <div>
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
          </div>
          <div className="w-full sm:w-80">
            <FantasyLevelBadge />
          </div>
        </div>

        {/* Iter 231j — Pending trades banner: surfaces "Pending Response"
            (recipient) + "Pending Review" (proposer) trades across all
            leagues so users see open trades immediately on load. */}
        <PendingTradesBanner />

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

        {/* My Leagues — drag and drop to reorder */}
        <MyLeaguesOrderedList />

        {/* My Week at a Glance — per-league daily/weekly/top performer/rank */}
        <MyWeekAtAGlance />

        {/* Iter 218 — Your Activity (personal UX engagement signal) */}
        <div className="mb-6">
          <YourActivityWidget />
        </div>

        {/* Live Scoring widget */}
        <LiveScoringWidget />

        {/* Iter 232N.5 — Cross-league player status feed. Aggregates
            every `player_status_change` notification the user has
            received in the last 14 days across ALL their leagues,
            grouped by player for scannable milestone audit. */}
        <div className="mb-8 surface p-4">
          <PlayerStatusFeed
            scope="user"
            days={14}
            heading="Player status updates across your leagues"
            emptyMessage="No player status changes in the last 14 days across your teams."
          />
        </div>

        {/* Iter 232N.7 — Cross-league movers. Nightly-aggregated view
            of the hottest / most-dropped / most-traded players over
            the last 7 days across every league in the system. Helps
            managers spot smart-money signals fast. */}
        <div className="mb-8 surface p-4">
          <LeagueMoversWidget heading="League movers · last 7 days" limit={5} />
        </div>

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
