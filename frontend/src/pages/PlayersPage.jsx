import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '@/lib/api';
import { AppLayout } from '@/components/layout/AppLayout';
import { DataTable } from '@/components/ui/data-table';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Users, MagnifyingGlass, SortAscending, CaretLeft, CaretRight } from '@phosphor-icons/react';

const POSITIONS = ['All', 'C', 'LW', 'RW', 'D', 'G'];

export default function PlayersPage() {
  const [players, setPlayers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [position, setPosition] = useState('All');
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const navigate = useNavigate();

  useEffect(() => {
    const fetchPlayers = async () => {
      setLoading(true);
      try {
        const params = new URLSearchParams();
        if (search) params.append('search', search);
        if (position !== 'All') params.append('position', position);
        params.append('page', page.toString());
        params.append('limit', '25');

        const { data } = await api.get(`/players?${params.toString()}`);
        setPlayers(data.players);
        setTotalPages(data.pages);
      } catch (err) {
        console.error('Failed to fetch players', err);
      } finally {
        setLoading(false);
      }
    };
    
    const debounce = setTimeout(fetchPlayers, 300);
    return () => clearTimeout(debounce);
  }, [search, position, page]);

  const columns = [
    { 
      key: 'name', 
      label: 'Player',
      render: (v, row) => (
        <div>
          <p className="font-semibold">{v}</p>
          <p className="text-[#A1A1AA] text-sm">{row.team}</p>
        </div>
      )
    },
    { key: 'position', label: 'Pos', render: (v) => <span className="badge badge-info">{v}</span> },
    { key: 'goals', label: 'G' },
    { key: 'assists', label: 'A' },
    { key: 'points', label: 'PTS', render: (v) => <span className="font-bold text-[#00D2FF]">{v}</span> },
    { key: 'plus_minus', label: '+/-', render: (v) => (
      <span className={v > 0 ? 'text-[#34C759]' : v < 0 ? 'text-[#FF3B30]' : 'text-white'}>
        {v > 0 ? '+' : ''}{v}
      </span>
    )},
    { key: 'games_played', label: 'GP' },
  ];

  return (
    <AppLayout>
    <div data-testid="players-page">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <h1 className="font-heading text-4xl font-bold tracking-tight text-white">NHL PLAYERS</h1>
          <p className="text-[#A1A1AA]">Browse and search NHL players for your fantasy team</p>
        </div>

        {/* Filters */}
        <div className="flex flex-col sm:flex-row gap-4 mb-6">
          <div className="relative flex-1">
            <MagnifyingGlass size={20} className="absolute left-3 top-1/2 -translate-y-1/2 text-[#A1A1AA]" />
            <Input
              type="text"
              placeholder="Search players or teams..."
              value={search}
              onChange={(e) => { setSearch(e.target.value); setPage(1); }}
              data-testid="search-players"
              className="pl-10 bg-[#141414] border-white/10 text-white placeholder:text-[#52525B]"
            />
          </div>
          <Select value={position} onValueChange={(v) => { setPosition(v); setPage(1); }}>
            <SelectTrigger className="w-full sm:w-40 bg-[#141414] border-white/10 text-white" data-testid="position-filter">
              <SelectValue placeholder="Position" />
            </SelectTrigger>
            <SelectContent className="bg-[#141414] border-white/10">
              {POSITIONS.map(pos => (
                <SelectItem key={pos} value={pos} className="text-white hover:bg-white/10">
                  {pos === 'All' ? 'All Positions' : pos}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {/* Players Table */}
        {loading ? (
          <div className="surface p-8 text-center text-[#A1A1AA]">
            Loading players...
          </div>
        ) : players.length === 0 ? (
          <div className="surface p-12 text-center">
            <Users size={64} className="text-[#52525B] mx-auto mb-4" />
            <h3 className="text-xl text-white font-semibold mb-2">No players found</h3>
            <p className="text-[#A1A1AA]">Try adjusting your search or filters</p>
          </div>
        ) : (
          <>
            <DataTable
              columns={columns}
              data={players}
              onRowClick={(row) => navigate(`/players/${row._id}`)}
              testId="players-table"
            />

            {/* Pagination */}
            <div className="flex items-center justify-between mt-6">
              <p className="text-[#A1A1AA] text-sm">Page {page} of {totalPages}</p>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setPage(p => Math.max(1, p - 1))}
                  disabled={page === 1}
                  className="border-white/10 text-white disabled:opacity-50"
                >
                  <CaretLeft size={16} />
                  Previous
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                  disabled={page === totalPages}
                  className="border-white/10 text-white disabled:opacity-50"
                >
                  Next
                  <CaretRight size={16} />
                </Button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
    </AppLayout>
  );
}
