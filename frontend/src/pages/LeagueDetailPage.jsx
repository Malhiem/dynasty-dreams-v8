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
import { useLeagueHomeConfig } from '@/hooks/use-league-home-config';
import LeagueHomeSettingsModal from '@/components/LeagueHomeSettingsModal';
import { SortableSections, SortableSection } from '@/components/SortableSections';

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
  const [settingsOpen, setSettingsOpen] = useState(false);
  const { visibility: widgetVis, order: widgetOrder, toggle: toggleWidget, reorder: reorderWidgets, reset: resetWidgets } = useLeagueHomeConfig(id);

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
  const [topBlock, setTopBlock] = useState([]);
  const [blockTotal, setBlockTotal] = useState(0);
  const [txnSinceKey, setTxnSinceKey] = useState("latest20");
  const [txnTeamId, setTxnTeamId] = useState("");

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

    // Build txn query based on filters
    const txnParams = new URLSearchParams();
    if (txnSinceKey === "latest20") {
      txnParams.set("limit", "20");
    } else {
      txnParams.set("limit", "200");
      const now = new Date();
      const since = new Date(now);
      if (txnSinceKey === "1w") since.setDate(now.getDate() - 7);
      else if (txnSinceKey === "1mo") since.setMonth(now.getMonth() - 1);
      else if (txnSinceKey === "3mo") since.setMonth(now.getMonth() - 3);
      else if (txnSinceKey === "season") since.setMonth(now.getMonth() - 12);
      txnParams.set("since", since.toISOString());
    }
    if (txnTeamId) txnParams.set("team_id", txnTeamId);

    Promise.all([
      api.get(`/leagues/${id}/transactions?${txnParams.toString()}`).catch(() => ({ data: { transactions: [] } })),
      api.get(`/leagues/${id}/pending-trades`).catch(() => ({ data: { pending_trades: [] } })),
      api.get(`/leagues/${id}/trade-block-summary?limit=8`).catch(() => ({ data: { items: [], count: 0 } })),
    ])
      .then(([txnsRes, ptRes, tbRes]) => {
        if (cancelled) return;
        setTransactions(txnsRes.data?.transactions || []);
        setPendingTrades(ptRes.data?.pending_trades || []);
        setTopBlock(tbRes.data?.items || []);
        setBlockTotal(tbRes.data?.count || 0);
      })
      .finally(() => { if (!cancelled) setTxnsLoading(false); });
    return () => { cancelled = true; };
  }, [id, txnSinceKey, txnTeamId]);

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
    <AppLayout onSettingsClick={() => setSettingsOpen(true)}>
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

        {/* Sortable / customizable sections — drag the grip handle in the
            top-right of any card to reorder, or use the cog in the header
            to hide widgets entirely. Section order is persisted to
            localStorage per-league. Uses CSS `order` so source JSX stays
            stable while visual order follows the user's choice. */}
        <SortableSections ids={widgetOrder} onReorder={reorderWidgets}>
        <div className="flex flex-col">

        {/* Matchups + Standings (side-by-side on desktop) */}
        {widgetVis.matchups && isH2H ? (
          <SortableSection id="matchups" className="mb-8" style={{order: widgetOrder.indexOf("matchups")}}>
          <div className="grid grid-cols-1 lg:grid-cols-[1fr,360px] gap-6" data-testid="league-matchups-section">
            {/* Matchups column */}
            <div>
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
                    // Record (regular season) or seed (playoffs)
                    const fmtRecord = (t) => m.bracket
                      ? (t.playoff_seed ? `#${t.playoff_seed} seed` : '—')
                      : `${t.wins || 0}-${t.losses || 0}-${t.ties || 0}`;
                    const homeRec = fmtRecord(home);
                    const awayRec = fmtRecord(away);
                    const homeWon = m.winner === m.home_team_id;
                    const awayWon = m.winner === m.away_team_id;
                    const isComplete = m.status === 'completed';
                    const homeScore = (typeof m.home_score === 'number' ? m.home_score : 0).toFixed(1);
                    const awayScore = (typeof m.away_score === 'number' ? m.away_score : 0).toFixed(1);
                    const TeamRow = ({ t, name, rec, score, won, side }) => (
                      <Link to={`/teams/${m[`${side}_team_id`]}`} className="flex items-center gap-3 group">
                        {t.logo_url ? (
                          <img src={t.logo_url} alt={name} className="h-9 w-9 rounded-md object-cover shrink-0" />
                        ) : (
                          <div className="h-9 w-9 rounded-md bg-[#00D2FF]/15 text-[#00D2FF] font-bold flex items-center justify-center shrink-0">
                            {(name || '?').split(/\s+/).slice(0, 2).map(s => s[0]).join('').toUpperCase()}
                          </div>
                        )}
                        <div className="flex-1 min-w-0">
                          <div className={`font-semibold truncate group-hover:underline ${won ? 'text-[#00D2FF]' : 'text-white'}`} data-testid={`matchup-${side}-name-${m._id}`}>{name}</div>
                          <div className="text-xs text-[#A1A1AA]" data-testid={`matchup-${side}-record-${m._id}`}>{rec}</div>
                        </div>
                        <div className={`text-2xl font-black tabular-nums ${won ? 'text-[#00D2FF]' : 'text-white'}`} data-testid={`matchup-${side}-score-${m._id}`}>{score}</div>
                      </Link>
                    );
                    return (
                      <div
                        key={m._id}
                        className="surface p-4 hover:border-[#00D2FF]/40 transition-colors"
                        data-testid={`league-matchup-card-${m._id}`}
                      >
                        <TeamRow t={home} name={m.home_team_name} rec={homeRec} score={homeScore} won={homeWon} side="home" />
                        <div className="my-2 flex items-center gap-2">
                          <div className="flex-1 h-px bg-white/10" />
                          <span className="text-[10px] uppercase tracking-wider text-[#52525B]">vs</span>
                          <div className="flex-1 h-px bg-white/10" />
                        </div>
                        <TeamRow t={away} name={m.away_team_name} rec={awayRec} score={awayScore} won={awayWon} side="away" />
                        {(isComplete || m.bracket) && (
                          <div className="mt-3 flex items-center justify-between">
                            {isComplete ? (
                              <span className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded bg-emerald-500/15 text-emerald-400">FINAL</span>
                            ) : <span />}
                            {m.bracket && (
                              <span className="text-[10px] font-bold uppercase tracking-wider text-amber-400">
                                {m.is_final ? '🏆 ' : ''}{(m.bracket || '').replace(/_/g, ' ')}
                              </span>
                            )}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            {/* Standings rail */}
            <div>
              <h2 className="font-heading text-2xl font-bold text-white mb-4">STANDINGS</h2>
              {standings.length === 0 ? (
                <div className="surface p-6 text-center text-[#A1A1AA]">
                  <Users size={32} className="text-[#52525B] mx-auto mb-2" />
                  No teams yet.
                </div>
              ) : (
                <div className="surface divide-y divide-white/5" data-testid="standings-table">
                  {standings.map((s, i) => (
                    <Link
                      key={s.team_id}
                      to={`/teams/${s.team_id}`}
                      className="px-3 py-2 flex items-center gap-3 hover:bg-white/[0.02] transition-colors"
                      data-testid={`standings-row-${s.team_id}`}
                    >
                      <span className="text-xs font-bold text-[#00D2FF] w-5 tabular-nums">{i + 1}</span>
                      <div className="flex-1 min-w-0">
                        <div className="text-sm text-white truncate">{s.team_name}</div>
                        <div className="text-[10px] text-[#A1A1AA] tabular-nums">{s.wins}-{s.losses}-{s.ties} · {s.points_for.toFixed(0)} PF</div>
                      </div>
                    </Link>
                  ))}
                </div>
              )}
            </div>
          </div>
          </SortableSection>
        ) : widgetVis.points_leaderboard ? (
          /* Non-H2H: just standings */
          <SortableSection id="points_leaderboard" className="mb-8" style={{order: widgetOrder.indexOf("points_leaderboard")}}>
          <div data-testid="league-points-leaderboard-section">
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
          </SortableSection>
        ) : null}

        {/* Top Trade Block */}
        {widgetVis.top_trade_block && topBlock.length > 0 && (
          <SortableSection id="top_trade_block" className="mb-8" style={{order: widgetOrder.indexOf("top_trade_block")}}>
          <div data-testid="league-top-trade-block">
            <div className="flex items-baseline justify-between mb-4">
              <h2 className="font-heading text-2xl font-bold text-white">TOP TRADE BLOCK</h2>
              <Link
                to="/trade-block"
                className="text-sm text-[#00D2FF] hover:underline"
                data-testid="league-top-trade-block-view-all"
              >
                View all {blockTotal} →
              </Link>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
              {topBlock.map(it => {
                const RET_PALETTE = {
                  willing_to_retain: { label: 'WILLING', color: 'text-emerald-400 bg-emerald-500/15' },
                  seeking_retention: { label: 'SEEKING', color: 'text-amber-400 bg-amber-500/15' },
                  no_preference:     { label: 'NEUTRAL', color: 'text-[#A1A1AA] bg-white/5' },
                }[it.salary_retention_pref] || { label: 'NEUTRAL', color: 'text-[#A1A1AA] bg-white/5' };
                return (
                  <div
                    key={it._id}
                    className="surface p-3 hover:border-[#00D2FF]/40 transition-colors"
                    data-testid={`top-trade-block-item-${it._id}`}
                  >
                    <div className="flex items-start justify-between gap-2 mb-1">
                      <div className="min-w-0 flex-1">
                        <div className="font-semibold text-white truncate text-sm">{it.name}</div>
                        <div className="text-[11px] text-[#A1A1AA] flex items-center gap-1">
                          <span className="text-[#00D2FF] font-bold">{it.position || '–'}</span>
                          {it.nhl_team && <span>· {it.nhl_team}</span>}
                          {it.item_type === 'pick' && it.pick_year && (
                            <span className="text-amber-400">· PICK</span>
                          )}
                        </div>
                      </div>
                      <span className={`text-[9px] font-bold tracking-wider px-1.5 py-0.5 rounded ${RET_PALETTE.color}`}>
                        {RET_PALETTE.label}
                      </span>
                    </div>
                    <div className="grid grid-cols-3 gap-1 mt-2 text-[11px]">
                      <div>
                        <div className="text-[#52525B] text-[9px] uppercase">FPTS</div>
                        <div className="text-white font-bold tabular-nums">
                          {(it.fantasy_points || 0).toFixed(1)}
                        </div>
                      </div>
                      <div>
                        <div className="text-[#52525B] text-[9px] uppercase">PPG</div>
                        <div className="text-white font-bold tabular-nums">
                          {(it.fantasy_ppg || 0).toFixed(2)}
                        </div>
                      </div>
                      <div>
                        <div className="text-[#52525B] text-[9px] uppercase">REC FORM</div>
                        <div className="text-white font-bold tabular-nums">
                          {it.recent_form_ppw != null ? it.recent_form_ppw.toFixed(0) : '—'}
                        </div>
                      </div>
                    </div>
                    {(it.goals != null || it.assists != null) && it.item_type === 'player' && (
                      <div className="mt-2 text-[10px] text-[#A1A1AA] flex items-center gap-2">
                        <span>{it.goals || 0}G</span>
                        <span>·</span>
                        <span>{it.assists || 0}A</span>
                        <span>·</span>
                        <span>{it.points || 0}P</span>
                        <span>·</span>
                        <span>{it.games_played || 0}GP</span>
                      </div>
                    )}
                    <div className="mt-2 pt-2 border-t border-white/5 text-[10px] text-[#A1A1AA] truncate">
                      {it.team_name || it.owner_name || ''}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
          </SortableSection>
        )}

        {/* Pending Trades */}
        {widgetVis.pending_trades && pendingTrades.length > 0 && (
          <SortableSection id="pending_trades" className="mb-8" style={{order: widgetOrder.indexOf("pending_trades")}}>
          <div data-testid="league-pending-trades-section">
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
                const isMulti = t.is_multi_party || (Array.isArray(t.parties) && t.parties.length > 2);
                const parties = Array.isArray(t.parties) ? t.parties : null;
                const acceptedCount = parties ? parties.filter(p => p.accepted).length : 0;
                const totalParties = parties ? parties.length : 2;
                return (
                  <div
                    key={t._id}
                    className="surface p-4 border-amber-500/30"
                    data-testid={`pending-trade-card-${t._id}`}
                  >
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-2">
                        <span className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded bg-amber-500/15 text-amber-400">
                          {(t.status || 'pending').toUpperCase()}
                        </span>
                        {isMulti && (
                          <span
                            className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded bg-cyan-500/15 text-cyan-400"
                            data-testid={`pending-trade-multi-badge-${t._id}`}
                          >
                            {totalParties}-TEAM · {acceptedCount}/{totalParties} ACCEPTED
                          </span>
                        )}
                      </div>
                      {expiresIn != null && (
                        <span className="text-[10px] text-[#A1A1AA]">
                          {expiresIn === 0 ? 'Expires today' : `Expires in ${expiresIn}d`}
                        </span>
                      )}
                    </div>

                    {parties ? (
                      <div className="space-y-1.5" data-testid={`pending-trade-parties-${t._id}`}>
                        {parties.map(p => (
                          <div
                            key={p.team_id}
                            className="flex items-center justify-between gap-2 text-sm"
                            data-testid={`pending-trade-party-${t._id}-${p.team_id}`}
                          >
                            <Link
                              to={`/teams/${p.team_id}`}
                              className="font-semibold text-white truncate hover:underline"
                            >
                              {p.team_name}
                            </Link>
                            <span className="text-[10px] text-[#52525B]">
                              {(p.sends || []).length} sending · {(p.receives || []).length} receiving
                            </span>
                            {p.accepted ? (
                              <span
                                className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-emerald-500/15 text-emerald-400"
                                data-testid={`pending-trade-status-accepted-${p.team_id}`}
                              >
                                ✓ ACCEPTED
                              </span>
                            ) : p.rejected ? (
                              <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-red-500/15 text-red-400">
                                ✗ REJECTED
                              </span>
                            ) : (
                              <span
                                className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-400"
                                data-testid={`pending-trade-status-pending-${p.team_id}`}
                              >
                                ⌛ AWAITING
                              </span>
                            )}
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div className="flex items-center justify-between gap-2 text-sm">
                        <Link to={`/teams/${t.proposer_team_id}`} className="font-semibold text-white truncate hover:underline">
                          {t.proposer_team_name || 'Team A'}
                        </Link>
                        <span className="text-[#52525B]">↔</span>
                        <Link to={`/teams/${t.target_team_id}`} className="font-semibold text-white truncate hover:underline">
                          {t.target_team_name || 'Team B'}
                        </Link>
                      </div>
                    )}

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
                      <Link to="/transactions" className="text-[#00D2FF] hover:underline">Review →</Link>
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
          </SortableSection>
        )}

        {/* Recent Transactions */}
        {widgetVis.transactions && (
        <SortableSection id="transactions" className="mb-8" style={{order: widgetOrder.indexOf("transactions")}}>
        <div data-testid="league-transactions-section">
          <div className="flex items-baseline justify-between mb-4 flex-wrap gap-2">
            <h2 className="font-heading text-2xl font-bold text-white">RECENT TRANSACTIONS</h2>
            <div className="flex items-center gap-2 flex-wrap text-xs">
              <select
                value={txnSinceKey}
                onChange={(e) => setTxnSinceKey(e.target.value)}
                data-testid="txn-filter-since"
                className="bg-[#0A0A0A] border border-white/10 rounded px-2 py-1 text-white"
              >
                <option value="latest20">Last 20 moves</option>
                <option value="1w">Past 1 week</option>
                <option value="1mo">Past 1 month</option>
                <option value="3mo">Past 3 months</option>
                <option value="season">This season</option>
              </select>
              <select
                value={txnTeamId}
                onChange={(e) => setTxnTeamId(e.target.value)}
                data-testid="txn-filter-team"
                className="bg-[#0A0A0A] border border-white/10 rounded px-2 py-1 text-white max-w-[180px]"
              >
                <option value="">All teams</option>
                {teams.map(t => (
                  <option key={t.id} value={t.id}>{t.name}</option>
                ))}
              </select>
              {!txnsLoading && transactions.length > 0 && (
                <span className="text-[#A1A1AA]">{transactions.length} shown</span>
              )}
            </div>
          </div>
          {txnsLoading ? (
            <div className="surface p-6 text-center text-[#A1A1AA]">Loading transactions…</div>
          ) : transactions.length === 0 ? (
            <div className="surface p-6 text-center text-[#A1A1AA]" data-testid="league-transactions-empty">
              No transactions for this filter. Try a wider time range or a different team.
            </div>
          ) : (
            <div className="surface divide-y divide-white/5" data-testid="league-transactions-list">
              {(() => {
                const ICON = {
                  roster_add: { icon: '+', color: 'text-emerald-400 bg-emerald-500/15', label: 'ADD' },
                  roster_drop: { icon: '−', color: 'text-rose-400 bg-rose-500/15', label: 'DROP' },
                  waiver_won: { icon: '★', color: 'text-violet-400 bg-violet-500/15', label: 'WAIVER' },
                  waiver_lost: { icon: '✕', color: 'text-zinc-400 bg-white/5', label: 'WAIVER LOST' },
                  trade_executed: { icon: '⇄', color: 'text-[#00D2FF] bg-[#00D2FF]/15', label: 'TRADE' },
                };
                const fmtTime = (iso) => {
                  if (!iso) return '';
                  const d = new Date(iso);
                  return d.toLocaleString(undefined, {
                    month: 'short', day: 'numeric',
                    hour: 'numeric', minute: '2-digit', second: '2-digit',
                  });
                };
                // Group consecutive same-team add/drop transactions within a 5-minute window.
                // Trades and waiver claims always render as their own row.
                const FIVE_MIN_MS = 5 * 60 * 1000;
                const GROUPABLE = new Set(['roster_add', 'roster_drop']);
                const groups = [];
                for (const tx of transactions) {
                  const last = groups[groups.length - 1];
                  const ts = tx.created_at ? new Date(tx.created_at).getTime() : 0;
                  const sameTeam = last && last.team_id && tx.team_id && last.team_id === tx.team_id;
                  const inWindow = last && Math.abs((last.firstTs || 0) - ts) <= FIVE_MIN_MS;
                  const groupable = GROUPABLE.has(tx.type) && last && last.allGroupable;
                  if (last && groupable && sameTeam && inWindow) {
                    last.entries.push(tx);
                    last.lastTs = ts;
                  } else {
                    groups.push({
                      entries: [tx],
                      team_id: tx.team_id,
                      team_name: tx.team_name,
                      firstTs: ts,
                      lastTs: ts,
                      allGroupable: GROUPABLE.has(tx.type),
                    });
                  }
                }
                return groups.map((g, gi) => {
                  if (g.entries.length === 1) {
                    const tx = g.entries[0];
                    const I = ICON[tx.type] || { icon: '·', color: 'text-[#A1A1AA] bg-white/5', label: 'TXN' };
                    return (
                      <div
                        key={tx.id}
                        className="px-4 py-3 flex items-center gap-3 hover:bg-white/[0.02] transition-colors"
                        data-testid={`league-transaction-${tx.id}`}
                      >
                        <div className={`h-8 w-8 rounded-md flex items-center justify-center text-base font-black shrink-0 ${I.color}`}>
                          {I.icon}
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className={`text-[10px] font-bold tracking-wider ${I.color.split(' ')[0]}`}>
                              {I.label}
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
                        <div
                          className="text-[10px] text-[#52525B] shrink-0 tabular-nums text-right whitespace-nowrap"
                          data-testid={`league-transaction-time-${tx.id}`}
                        >
                          {fmtTime(tx.created_at)}
                        </div>
                      </div>
                    );
                  }
                  // Grouped row — multiple adds/drops by the same team within 5 minutes
                  const adds = g.entries.filter(e => e.type === 'roster_add').length;
                  const drops = g.entries.filter(e => e.type === 'roster_drop').length;
                  return (
                    <div
                      key={`group-${gi}-${g.firstTs}`}
                      className="px-4 py-3 hover:bg-white/[0.02] transition-colors"
                      data-testid={`league-transaction-group-${gi}`}
                    >
                      <div className="flex items-center gap-3">
                        <div className="h-8 w-8 rounded-md flex items-center justify-center text-base font-black shrink-0 text-[#00D2FF] bg-[#00D2FF]/15">
                          ⇅
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="text-[10px] font-bold tracking-wider text-[#00D2FF]">
                              ROSTER MOVES
                            </span>
                            {g.team_name && (
                              <Link to={`/teams/${g.team_id}`} className="text-sm font-semibold text-white hover:underline truncate">
                                {g.team_name}
                              </Link>
                            )}
                            <span className="text-[10px] text-[#A1A1AA]">
                              {adds > 0 && `${adds} add${adds === 1 ? '' : 's'}`}
                              {adds > 0 && drops > 0 && ' · '}
                              {drops > 0 && `${drops} drop${drops === 1 ? '' : 's'}`}
                              {' · '}{g.entries.length} moves in {Math.max(1, Math.round((g.firstTs - g.lastTs) / 60000))} min window
                            </span>
                          </div>
                        </div>
                        <div
                          className="text-[10px] text-[#52525B] shrink-0 tabular-nums text-right whitespace-nowrap"
                          data-testid={`league-transaction-group-time-${gi}`}
                        >
                          {fmtTime(g.entries[0].created_at)}
                          {g.entries.length > 1 && (
                            <div className="text-[9px] opacity-70">↳ {fmtTime(g.entries[g.entries.length - 1].created_at)}</div>
                          )}
                        </div>
                      </div>
                      <ul className="ml-11 mt-2 space-y-0.5" data-testid={`league-transaction-group-${gi}-items`}>
                        {(() => {
                          // Collapse to one row per event_type with comma-separated player list
                          const byType = new Map();
                          for (const tx of g.entries) {
                            if (!byType.has(tx.type)) byType.set(tx.type, []);
                            byType.get(tx.type).push(tx);
                          }
                          const TYPE_VERB = { roster_add: 'adds', roster_drop: 'drops' };
                          return Array.from(byType.entries()).map(([type, txs]) => {
                            const I = ICON[type] || { icon: '·', color: 'text-[#A1A1AA] bg-white/5', label: 'TXN' };
                            const verb = TYPE_VERB[type] || type;
                            const playerNames = txs.map(t => t.player_name).filter(Boolean);
                            const startTs = txs[txs.length - 1]?.created_at;
                            const endTs = txs[0]?.created_at;
                            const sameMin = startTs && endTs && (
                              new Date(startTs).toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' }) ===
                              new Date(endTs).toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })
                            );
                            return (
                              <li
                                key={type}
                                className="flex items-start gap-2 text-xs text-[#A1A1AA]"
                                data-testid={`league-transaction-group-${gi}-${type}`}
                              >
                                <span className={`text-[9px] font-bold tracking-wider w-9 shrink-0 mt-0.5 ${I.color.split(' ')[0]}`}>
                                  {I.label}
                                </span>
                                <span className="flex-1">
                                  <span className="text-white font-medium">{g.team_name}</span>{' '}
                                  <span className="text-[#A1A1AA]">{verb}</span>{' '}
                                  <span className="text-white">{playerNames.join(', ')}</span>
                                </span>
                                <span className="text-[9px] text-[#52525B] tabular-nums shrink-0 mt-0.5">
                                  {fmtTime(endTs)}{!sameMin && startTs !== endTs ? ` ↔ ${fmtTime(startTs)}` : ''}
                                </span>
                              </li>
                            );
                          });
                        })()}
                      </ul>
                    </div>
                  );
                });
              })()}
            </div>
          )}
        </div>
        </SortableSection>
        )}

        {/* Quick Actions */}
        {widgetVis.quick_actions && hasTeam && (
          <SortableSection id="quick_actions" className="mb-8" style={{order: widgetOrder.indexOf("quick_actions")}}>
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
          </SortableSection>
        )}
        </div>
        </SortableSections>
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
      {/* League Home Customize Modal (triggered by the cog in AppLayout header) */}
      <LeagueHomeSettingsModal
        open={settingsOpen}
        onOpenChange={setSettingsOpen}
        visibility={widgetVis}
        onToggle={toggleWidget}
        onReset={resetWidgets}
      />
    </div>
    </AppLayout>
  );
}
