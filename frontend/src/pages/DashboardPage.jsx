import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import api from '@/lib/api';
import { AppLayout } from '@/components/layout/AppLayout';
import { StatCard } from '@/components/ui/stat-card';
import { DataTable } from '@/components/ui/data-table';
import { Button } from '@/components/ui/button';
import RecommendedForYou from '@/components/RecommendedForYou';
import LiveScoringWidget from '@/components/LiveScoringWidget';
import { Trophy, Users, Calendar, Rocket, Plus, ArrowRight } from '@phosphor-icons/react';

export default function DashboardPage() {
  const { user } = useAuth();
  const [stats, setStats] = useState({ leagues: 0, teams: 0, upcoming: 0 });
  const [leagues, setLeagues] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [leaguesRes] = await Promise.all([
          api.get('/leagues?my_leagues=true'),
        ]);
        setLeagues(leaguesRes.data);
        setStats({
          leagues: leaguesRes.data.length,
          teams: leaguesRes.data.reduce((acc, l) => acc + (l.current_teams || 0), 0),
          upcoming: leaguesRes.data.filter(l => l.status === 'setup').length
        });
      } catch (err) {
        console.error('Failed to fetch dashboard data', err);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, []);

  const leagueColumns = [
    { key: 'name', label: 'League Name' },
    { key: 'format', label: 'Format', render: (v) => v?.replace('_', ' ').toUpperCase() },
    { key: 'scoring_format', label: 'Scoring', render: (v) => v?.replace('_', ' ').toUpperCase() },
    { key: 'current_teams', label: 'Teams', render: (v, row) => `${v}/${row.max_teams}` },
    { key: 'status', label: 'Status', render: (v) => (
      <span className={`badge ${v === 'active' ? 'badge-success' : v === 'setup' ? 'badge-warning' : 'badge-info'}`}>
        {v}
      </span>
    )}
  ];

  return (
    <AppLayout>
    <div data-testid="dashboard-page">
      <div className="max-w-7xl mx-auto">
        {/* Welcome Section */}
        <div className="mb-8">
          <h1 className="font-heading text-4xl sm:text-5xl font-bold tracking-tight text-white mb-2">
            WELCOME BACK, {user?.name?.toUpperCase()}
          </h1>
          <p className="text-[#A1A1AA]">Here's your dynasty at a glance</p>
        </div>

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

        {/* Personalized Recommendation Card */}
        <RecommendedForYou />

        {/* Live Scoring widget */}
        <LiveScoringWidget />

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
