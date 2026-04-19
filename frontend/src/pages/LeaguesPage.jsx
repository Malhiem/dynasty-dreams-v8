import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import api from '@/lib/api';
import { AppLayout } from '@/components/layout/AppLayout';
import { DataTable } from '@/components/ui/data-table';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Trophy, Plus, MagnifyingGlass, Lock, Globe } from '@phosphor-icons/react';

export default function LeaguesPage() {
  const [leagues, setLeagues] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState('all'); // all, public, my
  const navigate = useNavigate();

  useEffect(() => {
    const fetchLeagues = async () => {
      try {
        const params = filter === 'my' ? '?my_leagues=true' : '';
        const { data } = await api.get(`/leagues${params}`);
        setLeagues(data);
      } catch (err) {
        console.error('Failed to fetch leagues', err);
      } finally {
        setLoading(false);
      }
    };
    fetchLeagues();
  }, [filter]);

  const filteredLeagues = leagues.filter(league =>
    league.name.toLowerCase().includes(search.toLowerCase())
  );

  const columns = [
    { 
      key: 'name', 
      label: 'League Name',
      render: (v, row) => (
        <div className="flex items-center gap-2">
          {row.is_private ? <Lock size={16} className="text-[#A1A1AA]" /> : <Globe size={16} className="text-[#00D2FF]" />}
          <span className="font-semibold">{v}</span>
        </div>
      )
    },
    { key: 'format', label: 'Format', render: (v) => v?.replace('_', ' ').toUpperCase() },
    { key: 'scoring_format', label: 'Scoring', render: (v) => v?.replace('_', ' ').toUpperCase() },
    { key: 'current_teams', label: 'Teams', render: (v, row) => `${v}/${row.max_teams}` },
    { key: 'entry_fee', label: 'Entry Fee', render: (v) => v ? `$${v.toFixed(2)}` : 'Free' },
    { 
      key: 'status', 
      label: 'Status', 
      render: (v) => (
        <span className={`badge ${v === 'active' ? 'badge-success' : v === 'setup' ? 'badge-warning' : 'badge-info'}`}>
          {v}
        </span>
      )
    }
  ];

  return (
    <AppLayout>
    <div data-testid="leagues-page">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-8">
          <div>
            <h1 className="font-heading text-4xl font-bold tracking-tight text-white">LEAGUES</h1>
            <p className="text-[#A1A1AA]">Find or create your perfect league</p>
          </div>
          <Link to="/leagues/create">
            <Button data-testid="create-league-btn" className="bg-[#00D2FF] text-black hover:bg-[#33DBFF]">
              <Plus size={18} className="mr-2" />
              Create League
            </Button>
          </Link>
        </div>

        {/* Filters */}
        <div className="flex flex-col sm:flex-row gap-4 mb-6">
          <div className="relative flex-1">
            <MagnifyingGlass size={20} className="absolute left-3 top-1/2 -translate-y-1/2 text-[#A1A1AA]" />
            <Input
              type="text"
              placeholder="Search leagues..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              data-testid="search-leagues"
              className="pl-10 bg-[#141414] border-white/10 text-white placeholder:text-[#52525B]"
            />
          </div>
          <div className="flex gap-2">
            {['all', 'public', 'my'].map((f) => (
              <Button
                key={f}
                variant={filter === f ? 'default' : 'outline'}
                onClick={() => setFilter(f)}
                data-testid={`filter-${f}`}
                className={filter === f 
                  ? 'bg-[#00D2FF] text-black' 
                  : 'border-white/10 text-white hover:bg-white/5'
                }
              >
                {f === 'all' ? 'All Leagues' : f === 'public' ? 'Public' : 'My Leagues'}
              </Button>
            ))}
          </div>
        </div>

        {/* Leagues Table */}
        {loading ? (
          <div className="surface p-8 text-center text-[#A1A1AA]">
            Loading leagues...
          </div>
        ) : filteredLeagues.length === 0 ? (
          <div className="surface p-12 text-center">
            <Trophy size={64} className="text-[#52525B] mx-auto mb-4" />
            <h3 className="text-xl text-white font-semibold mb-2">No leagues found</h3>
            <p className="text-[#A1A1AA] mb-6">Be the first to create a league!</p>
            <Link to="/leagues/create">
              <Button className="bg-[#00D2FF] text-black hover:bg-[#33DBFF]">Create League</Button>
            </Link>
          </div>
        ) : (
          <DataTable
            columns={columns}
            data={filteredLeagues}
            onRowClick={(row) => navigate(`/leagues/${row.id}`)}
            testId="leagues-table"
          />
        )}
      </div>
    </div>
    </AppLayout>
  );
}
