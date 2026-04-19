import { useEffect, useState } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import api, { formatApiError } from '@/lib/api';
import { AppLayout } from '@/components/layout/AppLayout';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { DataTable } from '@/components/ui/data-table';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog';
import { Trophy, Users, Calendar, Gear, ArrowLeft, Plus, Copy, Check } from '@phosphor-icons/react';

export default function LeagueDetailPage() {
  const { id } = useParams();
  const { user } = useAuth();
  const navigate = useNavigate();
  const [league, setLeague] = useState(null);
  const [teams, setTeams] = useState([]);
  const [standings, setStandings] = useState([]);
  const [loading, setLoading] = useState(true);
  const [joinModalOpen, setJoinModalOpen] = useState(false);
  const [teamName, setTeamName] = useState('');
  const [joining, setJoining] = useState(false);
  const [error, setError] = useState('');
  const [copied, setCopied] = useState(false);

  const isCommissioner = league?.commissioner_id === user?.id;
  const hasTeam = teams.some(t => t.owner_id === user?.id);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [leagueRes, teamsRes, standingsRes] = await Promise.all([
          api.get(`/leagues/${id}`),
          api.get(`/teams?league_id=${id}`),
          api.get(`/leagues/${id}/standings`),
        ]);
        setLeague(leagueRes.data);
        setTeams(teamsRes.data);
        setStandings(standingsRes.data);
      } catch (err) {
        console.error('Failed to fetch league', err);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, [id]);

  const handleJoin = async () => {
    if (!teamName.trim()) return;
    setJoining(true);
    setError('');
    try {
      await api.post('/teams', { name: teamName, league_id: id });
      // Refresh data
      const [teamsRes, standingsRes] = await Promise.all([
        api.get(`/teams?league_id=${id}`),
        api.get(`/leagues/${id}/standings`),
      ]);
      setTeams(teamsRes.data);
      setStandings(standingsRes.data);
      setLeague(prev => ({ ...prev, current_teams: prev.current_teams + 1 }));
      setJoinModalOpen(false);
      setTeamName('');
    } catch (err) {
      setError(formatApiError(err));
    } finally {
      setJoining(false);
    }
  };

  const copyInviteCode = () => {
    navigator.clipboard.writeText(league?.invite_code || '');
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const standingsColumns = [
    { key: 'rank', label: 'Rank', render: (v) => <span className="font-bold text-[#00D2FF]">{v}</span> },
    { key: 'team_name', label: 'Team' },
    { key: 'owner_name', label: 'Owner' },
    { key: 'wins', label: 'W' },
    { key: 'losses', label: 'L' },
    { key: 'ties', label: 'T' },
    { key: 'points_for', label: 'PF', render: (v) => v.toFixed(1) },
  ];

  if (loading) {
    return (
      <AppLayout>
        <div className="flex items-center justify-center h-[60vh]">
          <div className="text-[#A1A1AA]">Loading league...</div>
        </div>
      </AppLayout>
    );
  }

  if (!league) {
    return (
      <AppLayout>
        <div className="flex flex-col items-center justify-center h-[60vh]">
          <Trophy size={64} className="text-[#52525B] mb-4" />
          <h2 className="text-xl text-white mb-2">League not found</h2>
          <Link to="/leagues" className="text-[#00D2FF] hover:underline">Back to leagues</Link>
        </div>
      </AppLayout>
    );
  }

  return (
    <AppLayout>
    <div data-testid="league-detail-page">
      <div className="max-w-7xl mx-auto">
        <button
          onClick={() => navigate('/leagues')}
          className="flex items-center gap-2 text-[#A1A1AA] hover:text-white mb-6"
        >
          <ArrowLeft size={20} />
          Back to Leagues
        </button>

        {/* League Header */}
        <div className="surface p-6 mb-8">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div className="flex items-center gap-4">
              <div className="p-4 bg-[#00D2FF]/20 rounded">
                <Trophy size={40} weight="duotone" className="text-[#00D2FF]" />
              </div>
              <div>
                <h1 className="font-heading text-3xl font-bold tracking-tight text-white" data-testid="league-name">
                  {league.name}
                </h1>
                <div className="flex flex-wrap items-center gap-3 mt-2">
                  <span className="badge badge-info">{league.format.replace('_', ' ')}</span>
                  <span className="badge badge-info">{league.scoring_format.replace('_', ' ')}</span>
                  <span className={`badge ${league.status === 'active' ? 'badge-success' : 'badge-warning'}`}>
                    {league.status}
                  </span>
                </div>
              </div>
            </div>
            <div className="flex flex-wrap gap-3">
              {!hasTeam && league.current_teams < league.max_teams && (
                <Button
                  onClick={() => setJoinModalOpen(true)}
                  data-testid="join-league-btn"
                  className="bg-[#00D2FF] text-black hover:bg-[#33DBFF]"
                >
                  <Plus size={18} className="mr-2" />
                  Join League
                </Button>
              )}
              {isCommissioner && (
                <Button
                  variant="outline"
                  onClick={() => navigate(`/leagues/${id}/settings`)}
                  className="border-white/10 text-white hover:bg-white/5"
                >
                  <Gear size={18} className="mr-2" />
                  Settings
                </Button>
              )}
            </div>
          </div>

          {/* League Info Grid */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-6 pt-6 border-t border-white/10">
            <div>
              <p className="text-[#A1A1AA] text-sm">Teams</p>
              <p className="text-white font-semibold text-lg">
                {league.current_teams}/{league.max_teams}
              </p>
            </div>
            <div>
              <p className="text-[#A1A1AA] text-sm">Draft Type</p>
              <p className="text-white font-semibold text-lg capitalize">{league.draft_type}</p>
            </div>
            <div>
              <p className="text-[#A1A1AA] text-sm">Entry Fee</p>
              <p className="text-white font-semibold text-lg">
                {league.entry_fee ? `$${league.entry_fee.toFixed(2)}` : 'Free'}
              </p>
            </div>
            <div>
              <p className="text-[#A1A1AA] text-sm">Commissioner</p>
              <p className="text-white font-semibold text-lg">{league.commissioner_name}</p>
            </div>
          </div>

          {/* Invite Code for Private Leagues */}
          {isCommissioner && league.is_private && league.invite_code && (
            <div className="mt-6 p-4 bg-[#0A0A0A] rounded flex items-center justify-between">
              <div>
                <p className="text-[#A1A1AA] text-sm">Invite Code</p>
                <p className="text-white font-mono text-lg">{league.invite_code}</p>
              </div>
              <Button variant="ghost" onClick={copyInviteCode} className="text-[#00D2FF]">
                {copied ? <Check size={20} /> : <Copy size={20} />}
              </Button>
            </div>
          )}
        </div>

        {/* Standings */}
        <div className="mb-8">
          <h2 className="font-heading text-2xl font-bold text-white mb-4">STANDINGS</h2>
          {standings.length === 0 ? (
            <div className="surface p-8 text-center">
              <Users size={48} className="text-[#52525B] mx-auto mb-4" />
              <p className="text-[#A1A1AA]">No teams yet. Be the first to join!</p>
            </div>
          ) : (
            <DataTable columns={standingsColumns} data={standings} testId="standings-table" />
          )}
        </div>

        {/* Quick Actions */}
        {hasTeam && (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <Link to={`/leagues/${id}/roster`} className="surface p-6 hover:border-[#00D2FF]/50 transition-colors">
              <Users size={32} className="text-[#00D2FF] mb-3" />
              <h3 className="text-white font-semibold">My Roster</h3>
              <p className="text-[#A1A1AA] text-sm">Manage your team</p>
            </Link>
            <Link to={`/leagues/${id}/draft`} className="surface p-6 hover:border-[#00D2FF]/50 transition-colors">
              <Calendar size={32} className="text-[#00D2FF] mb-3" />
              <h3 className="text-white font-semibold">Draft Room</h3>
              <p className="text-[#A1A1AA] text-sm">View draft board</p>
            </Link>
            <Link to={`/leagues/${id}/trades`} className="surface p-6 hover:border-[#00D2FF]/50 transition-colors">
              <Trophy size={32} className="text-[#00D2FF] mb-3" />
              <h3 className="text-white font-semibold">Trade Center</h3>
              <p className="text-[#A1A1AA] text-sm">Propose and review trades</p>
            </Link>
          </div>
        )}
      </div>

      {/* Join League Modal */}
      <Dialog open={joinModalOpen} onOpenChange={setJoinModalOpen}>
        <DialogContent className="bg-[#141414] border-white/10">
          <DialogHeader>
            <DialogTitle className="text-white">Join {league.name}</DialogTitle>
            <DialogDescription className="text-[#A1A1AA]">Enter a team name to join this league</DialogDescription>
          </DialogHeader>
          <div className="py-4">
            {error && (
              <div className="bg-[#FF3B30]/20 text-[#FF3B30] px-4 py-2 rounded mb-4">
                {error}
              </div>
            )}
            <label className="text-[#A1A1AA] text-sm">Team Name</label>
            <Input
              value={teamName}
              onChange={(e) => setTeamName(e.target.value)}
              placeholder="Enter your team name"
              data-testid="team-name-input"
              className="mt-2 bg-[#0A0A0A] border-white/10 text-white"
            />
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setJoinModalOpen(false)} className="text-white">
              Cancel
            </Button>
            <Button
              onClick={handleJoin}
              disabled={joining || !teamName.trim()}
              data-testid="confirm-join-btn"
              className="bg-[#00D2FF] text-black hover:bg-[#33DBFF]"
            >
              {joining ? 'Joining...' : 'Join League'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
    </AppLayout>
  );
}
