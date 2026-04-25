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
  const isH2H = league?.scoring_format === 'head_to_head' || (league?.scoring_format || '').toLowerCase().includes('h2h');

  const [currentWeek, setCurrentWeek] = useState(null);
  const [weekMatchups, setWeekMatchups] = useState([]);
  const [matchupsLoading, setMatchupsLoading] = useState(false);
  const teamById = teams.reduce((acc, t) => { acc[t.id] = t; return acc; }, {});

  const [transactions, setTransactions] = useState([]);
  const [pendingTrades, setPendingTrades] = useState([]);
  const [txnsLoading, setTxnsLoading] = useState(false);

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

  useEffect(() => {
    if (!isH2H || !id) return;
    let cancelled = false;
    setMatchupsLoading(true);
    api.get(`/matchups/${id}/current-week`)
      .then(({ data }) => {
        if (cancelled) return;
        setCurrentWeek(data?.week || null);
        setWeekMatchups(data?.matchups || []);
      })
      .catch(() => {})
      .finally(() => { if (!cancelled) setMatchupsLoading(false); });
    return () => { cancelled = true; };
  }, [id, isH2H]);

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    setTxnsLoading(true);
    Promise.all([
      api.get(`/leagues/${id}/transactions?limit=20`).catch(() => ({ data: { transactions: [] } })),
      api.get(`/leagues/${id}/pending-trades`).catch(() => ({ data: { pending_trades: [] } })),
    ])
      .then(([txnsRes, ptRes]) => {
        if (cancelled) return;
        setTransactions(txnsRes.data?.transactions || []);
        setPendingTrades(ptRes.data?.pending_trades || []);
      })
      .finally(() => { if (!cancelled) setTxnsLoading(false); });
    return () => { cancelled = true; };
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
    {
      key: 'team_name',
      label: 'Team',
      render: (v, row) => (
        <Link
          to={`/teams/${row.team_id}`}
          data-testid={`league-detail-team-link-${row.team_id}`}
          className="text-white hover:text-[#00D2FF]"
        >
          {v}
        </Link>
      ),
    },
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
                  <span className="badge badge-info">{league.scoring_format.replace(/_/g, ' ')}</span>
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

        {/* Matchups (H2H only) */}
        {isH2H && (
          <div className="mb-8" data-testid="league-matchups-section">
            <div className="flex items-baseline justify-between mb-4">
              <h2 className="font-heading text-2xl font-bold text-white">
                MATCHUPS{currentWeek ? ` — WEEK ${currentWeek}` : ''}
              </h2>
              {weekMatchups.length > 0 && (
                <span className="text-[#A1A1AA] text-sm">{weekMatchups.length} game{weekMatchups.length === 1 ? '' : 's'}</span>
              )}
            </div>
            {matchupsLoading ? (
              <div className="surface p-6 text-center text-[#A1A1AA]">Loading matchups…</div>
            ) : weekMatchups.length === 0 ? (
              <div className="surface p-6 text-center text-[#A1A1AA]">
                No scheduled matchups. Commissioner can generate a schedule from <span className="text-white">League Administration</span>.
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {weekMatchups.map(m => {
                  const home = teamById[m.home_team_id] || {};
                  const away = teamById[m.away_team_id] || {};
                  const homeRec = `${home.wins || 0}-${home.losses || 0}-${home.ties || 0}`;
                  const awayRec = `${away.wins || 0}-${away.losses || 0}-${away.ties || 0}`;
                  const homeWon = m.winner === m.home_team_id;
                  const awayWon = m.winner === m.away_team_id;
                  const isComplete = m.status === 'completed';
                  const homeScore = (typeof m.home_score === 'number' ? m.home_score : 0).toFixed(1);
                  const awayScore = (typeof m.away_score === 'number' ? m.away_score : 0).toFixed(1);
                  return (
                    <div
                      key={m._id}
                      className="surface p-4 hover:border-[#00D2FF]/40 transition-colors"
                      data-testid={`league-matchup-card-${m._id}`}
                    >
                      {/* Home */}
                      <div className={`flex items-center justify-between gap-3 ${homeWon ? 'text-[#00D2FF]' : 'text-white'}`}>
                        <Link to={`/teams/${m.home_team_id}`} className="flex-1 min-w-0 hover:underline">
                          <div className="font-semibold truncate" data-testid={`matchup-home-name-${m._id}`}>
                            {m.home_team_name}
                          </div>
                          <div className="text-xs text-[#A1A1AA]" data-testid={`matchup-home-record-${m._id}`}>
                            {homeRec}{home.owner_name ? ` · ${home.owner_name}` : ''}
                          </div>
                        </Link>
                        <div
                          className={`text-2xl font-black tabular-nums ${homeWon ? 'text-[#00D2FF]' : 'text-white'}`}
                          data-testid={`matchup-home-score-${m._id}`}
                        >
                          {homeScore}
                        </div>
                      </div>

                      <div className="my-2 flex items-center gap-2">
                        <div className="flex-1 h-px bg-white/10" />
                        <span className="text-[10px] uppercase tracking-wider text-[#52525B]">vs</span>
                        <div className="flex-1 h-px bg-white/10" />
                      </div>

                      {/* Away */}
                      <div className={`flex items-center justify-between gap-3 ${awayWon ? 'text-[#00D2FF]' : 'text-white'}`}>
                        <Link to={`/teams/${m.away_team_id}`} className="flex-1 min-w-0 hover:underline">
                          <div className="font-semibold truncate" data-testid={`matchup-away-name-${m._id}`}>
                            {m.away_team_name}
                          </div>
                          <div className="text-xs text-[#A1A1AA]" data-testid={`matchup-away-record-${m._id}`}>
                            {awayRec}{away.owner_name ? ` · ${away.owner_name}` : ''}
                          </div>
                        </Link>
                        <div
                          className={`text-2xl font-black tabular-nums ${awayWon ? 'text-[#00D2FF]' : 'text-white'}`}
                          data-testid={`matchup-away-score-${m._id}`}
                        >
                          {awayScore}
                        </div>
                      </div>

                      <div className="mt-3 flex items-center justify-between">
                        <span className={`text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded ${
                          isComplete ? 'bg-emerald-500/15 text-emerald-400' : 'bg-white/5 text-[#A1A1AA]'
                        }`}>
                          {isComplete ? 'FINAL' : 'SCHEDULED'}
                        </span>
                        {m.bracket && (
                          <span className="text-[10px] font-bold uppercase tracking-wider text-amber-400">
                            {m.is_final ? '🏆 ' : ''}{(m.bracket || '').replace(/_/g, ' ')}
                          </span>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}

        {/* Pending Trades */}
        {pendingTrades.length > 0 && (
          <div className="mb-8" data-testid="league-pending-trades-section">
            <div className="flex items-baseline justify-between mb-4">
              <h2 className="font-heading text-2xl font-bold text-white flex items-center gap-2">
                <span className="inline-block h-2 w-2 rounded-full bg-amber-400 animate-pulse" />
                PENDING TRADES
              </h2>
              <span className="text-[#A1A1AA] text-sm">{pendingTrades.length} processing</span>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {pendingTrades.slice(0, 6).map(t => {
                const submittedDate = t.submitted_at ? new Date(t.submitted_at).toLocaleDateString() : '';
                const expiresIn = t.expires_at
                  ? Math.max(0, Math.ceil((new Date(t.expires_at) - new Date()) / 86400000))
                  : null;
                return (
                  <div
                    key={t._id}
                    className="surface p-4 border-amber-500/30"
                    data-testid={`pending-trade-card-${t._id}`}
                  >
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded bg-amber-500/15 text-amber-400">
                        {(t.status || 'pending').toUpperCase()}
                      </span>
                      {expiresIn != null && (
                        <span className="text-[10px] text-[#A1A1AA]">
                          {expiresIn === 0 ? 'Expires today' : `Expires in ${expiresIn}d`}
                        </span>
                      )}
                    </div>
                    <div className="flex items-center justify-between gap-2 text-sm">
                      <Link to={`/teams/${t.proposer_team_id}`} className="font-semibold text-white truncate hover:underline">
                        {t.proposer_team_name || 'Team A'}
                      </Link>
                      <span className="text-[#52525B]">↔</span>
                      <Link to={`/teams/${t.target_team_id}`} className="font-semibold text-white truncate hover:underline">
                        {t.target_team_name || 'Team B'}
                      </Link>
                    </div>
                    {Array.isArray(t.assets) && t.assets.length > 0 && (
                      <div className="mt-2 text-xs text-[#A1A1AA]">
                        {t.assets.length} asset{t.assets.length === 1 ? '' : 's'} ·{' '}
                        {t.assets.slice(0, 2).map(a => a.player_name || a.asset_type).filter(Boolean).join(', ')}
                        {t.assets.length > 2 && ` +${t.assets.length - 2} more`}
                      </div>
                    )}
                    {t.message && (
                      <div className="mt-2 text-xs italic text-[#A1A1AA] line-clamp-2">"{t.message}"</div>
                    )}
                    <div className="mt-3 flex items-center justify-between text-[11px] text-[#52525B]">
                      <span>Proposed {submittedDate}</span>
                      <Link to="/trades" className="text-[#00D2FF] hover:underline">Review →</Link>
                    </div>
                  </div>
                );
              })}
            </div>
            {pendingTrades.length > 6 && (
              <Link
                to="/trades"
                className="mt-3 inline-block text-sm text-[#00D2FF] hover:underline"
                data-testid="league-pending-trades-view-all"
              >
                View all {pendingTrades.length} pending trades →
              </Link>
            )}
          </div>
        )}

        {/* Recent Transactions */}
        <div className="mb-8" data-testid="league-transactions-section">
          <div className="flex items-baseline justify-between mb-4">
            <h2 className="font-heading text-2xl font-bold text-white">RECENT TRANSACTIONS</h2>
            {!txnsLoading && transactions.length > 0 && (
              <span className="text-[#A1A1AA] text-sm">last {transactions.length}</span>
            )}
          </div>
          {txnsLoading ? (
            <div className="surface p-6 text-center text-[#A1A1AA]">Loading transactions…</div>
          ) : transactions.length === 0 ? (
            <div className="surface p-6 text-center text-[#A1A1AA]" data-testid="league-transactions-empty">
              No transactions yet. Add or drop a player, win a waiver claim, or accept a trade — all activity shows up here.
            </div>
          ) : (
            <div className="surface divide-y divide-white/5" data-testid="league-transactions-list">
              {transactions.map(tx => {
                const ICON = {
                  roster_add: { icon: '+', color: 'text-emerald-400 bg-emerald-500/15', label: 'ADD' },
                  roster_drop: { icon: '−', color: 'text-rose-400 bg-rose-500/15', label: 'DROP' },
                  waiver_won: { icon: '★', color: 'text-violet-400 bg-violet-500/15', label: 'WAIVER' },
                  trade_executed: { icon: '⇄', color: 'text-[#00D2FF] bg-[#00D2FF]/15', label: 'TRADE' },
                }[tx.type] || { icon: '·', color: 'text-[#A1A1AA] bg-white/5', label: 'TXN' };
                return (
                  <div
                    key={tx.id}
                    className="px-4 py-3 flex items-center gap-3 hover:bg-white/[0.02] transition-colors"
                    data-testid={`league-transaction-${tx.id}`}
                  >
                    <div className={`h-8 w-8 rounded-md flex items-center justify-center text-base font-black shrink-0 ${ICON.color}`}>
                      {ICON.icon}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className={`text-[10px] font-bold tracking-wider ${ICON.color.split(' ')[0]}`}>
                          {ICON.label}
                        </span>
                        {tx.team_name && (
                          <Link to={`/teams/${tx.team_id}`} className="text-sm font-semibold text-white hover:underline truncate">
                            {tx.team_name}
                          </Link>
                        )}
                        {tx.bid_amount != null && (
                          <span className="text-[10px] text-violet-400 font-bold">${tx.bid_amount} FAAB</span>
                        )}
                      </div>
                      <div className="text-xs text-[#A1A1AA] truncate mt-0.5">{tx.description}</div>
                    </div>
                    <div className="text-[10px] text-[#52525B] shrink-0 tabular-nums">
                      {tx.created_at ? new Date(tx.created_at).toLocaleDateString() : ''}
                    </div>
                  </div>
                );
              })}
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
