import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { AppLayout } from '@/components/layout/AppLayout';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import { Activity, Flame, RefreshCw, Radio, Trophy, Loader2 } from 'lucide-react';
import api from '@/lib/api';
import { useGlobalSocketEvent } from '@/hooks/use-global-socket';
import { useActiveLeague } from '@/hooks/use-active-league';

const STATE_BADGE = {
  LIVE: { label: 'LIVE', className: 'bg-red-500/20 text-red-400 border-red-500/40 animate-pulse' },
  CRIT: { label: 'LIVE · CRITICAL', className: 'bg-red-600/30 text-red-300 border-red-600/50 animate-pulse' },
  OFF: { label: 'FINAL', className: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30' },
  FINAL: { label: 'FINAL', className: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30' },
  FUT: { label: 'UPCOMING', className: 'bg-blue-500/15 text-blue-400 border-blue-500/30' },
  PRE: { label: 'PREGAME', className: 'bg-blue-500/15 text-blue-400 border-blue-500/30' },
};

export default function LiveScoringPage() {
  const [summary, setSummary] = useState(null);
  const [leagues, setLeagues] = useState([]);
  const [selectedLeagueId, setSelectedLeagueId] = useState(null);
  const [leaderboard, setLeaderboard] = useState([]);
  const [myTeamLive, setMyTeamLive] = useState(null);
  const [refreshing, setRefreshing] = useState(false);
  const [loading, setLoading] = useState(true);
  const [lastUpdatedAt, setLastUpdatedAt] = useState(null);
  const [currentMatchup, setCurrentMatchup] = useState(null);
  const [selectedLeague, setSelectedLeague] = useState(null);
  const { myTeam } = useActiveLeague();

  useGlobalSocketEvent('live_scoring_update', (payload) => {
    setSummary(payload);
    setLastUpdatedAt(new Date().toISOString());
    if (selectedLeagueId) loadLeague(selectedLeagueId);
  });

  useEffect(() => {
    const init = async () => {
      try {
        const [sRes, lRes] = await Promise.all([
          api.get('/live-scoring'),
          api.get('/leagues?my_leagues=true'),
        ]);
        setSummary(sRes.data);
        setLastUpdatedAt(sRes.data?.polled_at);
        setLeagues(lRes.data || []);
        if (lRes.data?.length) setSelectedLeagueId(lRes.data[0].id);
      } catch (e) { console.error(e); }
      setLoading(false);
    };
    init();
  }, []);

  const loadLeague = async (leagueId) => {
    if (!leagueId) return;
    try {
      const { data } = await api.get(`/live-scoring/league/${leagueId}`);
      setLeaderboard(data?.leaderboard || []);
      const top = data?.leaderboard?.[0];
      if (top) {
        const { data: tlv } = await api.get(`/live-scoring/team/${top.team_id}`);
        setMyTeamLive(tlv);
      } else {
        setMyTeamLive(null);
      }

      // Pull league metadata so we know the format (H2H vs roto/BB)
      const l = leagues.find(x => x.id === leagueId);
      setSelectedLeague(l || null);

      // Fetch current-week matchup and enrich my team's matchup with live points
      const isH2H = (l?.scoring_format || "").toLowerCase().includes("head") || (l?.scoring_format || "").toLowerCase() === "h2h";
      if (isH2H || !l) {
        try {
          const { data: wk } = await api.get(`/matchups/${leagueId}/current-week`);
          // Find my team from /auth/me + team listing for this league
          let meId = null;
          try {
            const [{ data: me }, { data: teams }] = await Promise.all([
              api.get('/auth/me'),
              api.get(`/teams?league_id=${leagueId}`),
            ]);
            const mine = (teams || []).find(t => t.owner_id === me?.id);
            meId = mine?.id || null;
          } catch {}
          let pair = null;
          if (meId && wk?.matchups?.length) {
            pair = wk.matchups.find(m => m.home_team_id === meId || m.away_team_id === meId) || null;
          }
          if (pair) {
            const oppId = pair.home_team_id === meId ? pair.away_team_id : pair.home_team_id;
            let oppLive = null;
            try {
              const { data: opp } = await api.get(`/live-scoring/team/${oppId}`);
              oppLive = opp;
            } catch {}
            const meLivePts = (data?.leaderboard || []).find(r => r.team_id === meId)?.live_points || 0;
            const oppLivePts = (data?.leaderboard || []).find(r => r.team_id === oppId)?.live_points || oppLive?.live_points || 0;
            setCurrentMatchup({
              week: wk.week,
              me: {
                id: meId,
                name: pair.home_team_id === meId ? pair.home_team_name : pair.away_team_name,
                live_points: meLivePts,
              },
              opponent: {
                id: oppId,
                name: pair.home_team_id === meId ? pair.away_team_name : pair.home_team_name,
                live_points: oppLivePts,
                players: oppLive?.players || [],
              },
            });
          } else {
            setCurrentMatchup(null);
          }
        } catch (e) { setCurrentMatchup(null); }
      } else {
        setCurrentMatchup(null);
      }
    } catch (e) { console.error(e); }
  };

  useEffect(() => { if (selectedLeagueId) loadLeague(selectedLeagueId); }, [selectedLeagueId]);

  const handleRefresh = async () => {
    setRefreshing(true);
    try {
      const { data } = await api.post('/live-scoring/refresh');
      setSummary(data);
      setLastUpdatedAt(data?.polled_at);
      if (selectedLeagueId) await loadLeague(selectedLeagueId);
    } catch (e) { console.error(e); }
    setRefreshing(false);
  };

  const games = summary?.games || [];
  const livePlayoffCount = games.filter(g => g.is_playoff && (g.state === 'LIVE' || g.state === 'CRIT')).length;
  const anyLive = games.some(g => g.state === 'LIVE' || g.state === 'CRIT');

  return (
    <AppLayout>
      <div data-testid="live-scoring-page" className="max-w-7xl mx-auto">
        <div className="flex items-start justify-between flex-wrap gap-4 mb-8">
          <div>
            <div className="flex items-center gap-3 mb-2">
              <Radio size={26} className={anyLive ? 'text-red-400 animate-pulse' : 'text-[#00D2FF]'} />
              <h1 className="font-heading text-4xl sm:text-5xl font-bold tracking-tight text-white">
                LIVE SCORING
              </h1>
              {anyLive && (
                <Badge className="bg-red-500/20 text-red-400 border-red-500/40 animate-pulse">
                  ON AIR
                </Badge>
              )}
              {livePlayoffCount > 0 && (
                <Badge className="bg-amber-500/20 text-amber-400 border-amber-500/40">
                  PLAYOFFS · {livePlayoffCount} LIVE
                </Badge>
              )}
            </div>
            <p className="text-[#A1A1AA] text-sm">
              {summary?.date ? `NHL games for ${summary.date}` : 'Waiting for game data…'}
              {lastUpdatedAt && <> · Last updated {new Date(lastUpdatedAt).toLocaleTimeString()}</>}
            </p>
          </div>
          <Button
            data-testid="live-scoring-refresh-btn"
            onClick={handleRefresh}
            disabled={refreshing}
            className="bg-[#00D2FF] text-black hover:bg-[#33DBFF]"
          >
            {refreshing ? (
              <><Loader2 size={16} className="mr-2 animate-spin" /> Refreshing…</>
            ) : (
              <><RefreshCw size={16} className="mr-2" /> Refresh Scores</>
            )}
          </Button>
        </div>

        {loading ? (
          <div className="surface p-8 text-center text-[#A1A1AA]">Loading live data…</div>
        ) : (
          <>
            {/* My Head-to-Head Matchup */}
            {currentMatchup && (
              <div className="surface p-5 border border-[#00D2FF]/20 mb-6" data-testid="live-my-matchup-card">
                <div className="flex items-center gap-2 mb-3">
                  <Trophy size={16} className="text-[#00D2FF]" />
                  <h2 className="font-heading text-sm uppercase tracking-wider text-[#A1A1AA]">
                    My Matchup — Week {currentMatchup.week}
                  </h2>
                  <Badge className="bg-[#00D2FF]/15 text-[#00D2FF] border-[#00D2FF]/30 ml-auto">
                    {selectedLeague?.name || ""}
                  </Badge>
                </div>
                <div className="grid grid-cols-3 items-center gap-3">
                  <div className="text-right">
                    <div className="text-xs text-[#A1A1AA] mb-1">ME</div>
                    <Link
                      to={`/teams/${currentMatchup.me.id}`}
                      className="text-white text-lg font-bold hover:text-[#00D2FF]"
                      data-testid="live-matchup-me-link"
                    >
                      {currentMatchup.me.name}
                    </Link>
                    <div className="text-3xl font-bold tabular-nums text-[#00D2FF] mt-1" data-testid="live-matchup-me-points">
                      {Number(currentMatchup.me.live_points || 0).toFixed(2)}
                    </div>
                  </div>
                  <div className="text-center text-[#A1A1AA] text-sm font-semibold">
                    VS
                    <div className="mt-1">
                      {(() => {
                        const a = Number(currentMatchup.me.live_points || 0);
                        const b = Number(currentMatchup.opponent.live_points || 0);
                        if (a > b) return <Badge className="bg-emerald-500/20 text-emerald-400 border-emerald-500/40">Winning · +{(a - b).toFixed(2)}</Badge>;
                        if (b > a) return <Badge className="bg-red-500/20 text-red-400 border-red-500/40">Losing · -{(b - a).toFixed(2)}</Badge>;
                        return <Badge className="bg-amber-500/20 text-amber-400 border-amber-500/40">Tied</Badge>;
                      })()}
                    </div>
                  </div>
                  <div className="text-left">
                    <div className="text-xs text-[#A1A1AA] mb-1">OPPONENT</div>
                    <Link
                      to={`/teams/${currentMatchup.opponent.id}`}
                      className="text-white text-lg font-bold hover:text-[#00D2FF]"
                      data-testid="live-matchup-opp-link"
                    >
                      {currentMatchup.opponent.name}
                    </Link>
                    <div className="text-3xl font-bold tabular-nums text-white mt-1" data-testid="live-matchup-opp-points">
                      {Number(currentMatchup.opponent.live_points || 0).toFixed(2)}
                    </div>
                  </div>
                </div>
                <div className="mt-3 pt-3 border-t border-white/5 text-right">
                  <Link to="/matchup" className="text-xs text-[#00D2FF] hover:underline" data-testid="live-matchup-view-full">
                    View full matchup →
                  </Link>
                </div>
              </div>
            )}

            {/* NHL Games Row */}
            <h2 className="font-heading text-xl font-bold text-white mb-3 tracking-wide">
              NHL GAMES ({games.length})
            </h2>
            {games.length === 0 ? (
              <div className="surface p-6 text-[#A1A1AA] text-sm mb-8">
                No scheduled games were picked up for this date. Click Refresh to try again.
              </div>
            ) : (
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 mb-10">
                {games.map((g) => {
                  const badge = STATE_BADGE[g.state] || { label: g.state, className: 'bg-zinc-500/20 text-zinc-300 border-zinc-500/40' };
                  return (
                    <Card
                      key={g.id}
                      data-testid={`live-game-card-${g.id}`}
                      className="bg-white/5 border-white/10"
                    >
                      <CardContent className="p-4">
                        <div className="flex items-center justify-between mb-3">
                          <Badge className={badge.className}>{badge.label}</Badge>
                          {g.is_playoff && (
                            <Badge className="bg-amber-500/20 text-amber-400 border-amber-500/40">
                              <Flame size={12} className="mr-1" /> PLAYOFFS
                            </Badge>
                          )}
                        </div>
                        <div className="flex items-center justify-between text-white">
                          <div>
                            <div className="text-sm text-[#A1A1AA]">AWAY</div>
                            <div className="text-xl font-bold">{g.away}</div>
                          </div>
                          <div className="text-3xl font-bold tabular-nums">
                            {g.away_score ?? 0}
                          </div>
                        </div>
                        <div className="flex items-center justify-between text-white mt-2 pt-2 border-t border-white/5">
                          <div>
                            <div className="text-sm text-[#A1A1AA]">HOME</div>
                            <div className="text-xl font-bold">{g.home}</div>
                          </div>
                          <div className="text-3xl font-bold tabular-nums">
                            {g.home_score ?? 0}
                          </div>
                        </div>
                      </CardContent>
                    </Card>
                  );
                })}
              </div>
            )}

            {/* League-specific fantasy scoring */}
            <div className="flex items-center justify-between mb-3 flex-wrap gap-3">
              <h2 className="font-heading text-xl font-bold text-white tracking-wide flex items-center gap-2">
                <Trophy size={18} className="text-[#00D2FF]" /> FANTASY LEADERBOARD
              </h2>
              {leagues.length > 0 && (
                <Select value={selectedLeagueId ?? undefined} onValueChange={setSelectedLeagueId}>
                  <SelectTrigger
                    data-testid="live-scoring-league-select"
                    className="w-72 bg-white/5 border-white/10 text-white"
                  >
                    <SelectValue placeholder="Choose league" />
                  </SelectTrigger>
                  <SelectContent>
                    {leagues.map(l => (
                      <SelectItem key={l.id} value={l.id}>{l.name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            </div>

            <Tabs defaultValue="leaderboard">
              <TabsList>
                <TabsTrigger value="leaderboard">Leaderboard</TabsTrigger>
                <TabsTrigger value="top-team" data-testid="live-scoring-top-team-tab">
                  Top Team Roster
                </TabsTrigger>
              </TabsList>

              <TabsContent value="leaderboard" className="mt-4">
                <div className="surface overflow-hidden">
                  <table className="w-full text-left">
                    <thead className="bg-white/5 text-[#52525B] text-xs uppercase tracking-wider">
                      <tr>
                        <th className="px-4 py-3">Rank</th>
                        <th className="px-4 py-3">Team</th>
                        <th className="px-4 py-3">Owner</th>
                        <th className="px-4 py-3 text-right">Live Points</th>
                        <th className="px-4 py-3 text-right">Roster</th>
                      </tr>
                    </thead>
                    <tbody data-testid="live-scoring-leaderboard-body">
                      {leaderboard.map((r, idx) => (
                        <tr key={r.team_id} className={`border-t border-white/5 ${idx === 0 ? 'bg-[#00D2FF]/5' : ''}`}>
                          <td className="px-4 py-3 text-white font-semibold">{idx + 1}</td>
                          <td className="px-4 py-3">
                            <Link
                              to={`/teams/${r.team_id}`}
                              data-testid={`live-leaderboard-team-${r.team_id}`}
                              className="text-white hover:text-[#00D2FF]"
                            >
                              {r.team_name}
                            </Link>
                          </td>
                          <td className="px-4 py-3 text-[#A1A1AA] text-sm">{r.owner_name}</td>
                          <td className="px-4 py-3 text-right text-white tabular-nums font-bold">
                            {r.live_points.toFixed(2)}
                          </td>
                          <td className="px-4 py-3 text-right text-[#A1A1AA] text-sm">{r.roster_count}</td>
                        </tr>
                      ))}
                      {leaderboard.length === 0 && (
                        <tr><td colSpan={5} className="p-6 text-center text-[#A1A1AA]">
                          No live points logged yet for this league. Click Refresh.
                        </td></tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </TabsContent>

              <TabsContent value="top-team" className="mt-4">
                {myTeamLive ? (
                  <div className="surface overflow-hidden">
                    <div className="p-4 border-b border-white/5 flex items-center justify-between">
                      <div>
                        <div className="text-xs text-[#52525B] uppercase tracking-wider">Top team</div>
                        <div className="text-white font-bold text-lg">{myTeamLive.team_name}</div>
                      </div>
                      <div className="text-right">
                        <div className="text-xs text-[#52525B] uppercase tracking-wider">Total fpts</div>
                        <div className="text-3xl font-bold text-[#00D2FF] tabular-nums">{myTeamLive.live_points.toFixed(2)}</div>
                      </div>
                    </div>
                    <table className="w-full text-left text-sm">
                      <thead className="bg-white/5 text-[#52525B] text-xs uppercase tracking-wider">
                        <tr>
                          <th className="px-4 py-3">Player</th>
                          <th className="px-4 py-3">Pos</th>
                          <th className="px-4 py-3 text-right">G</th>
                          <th className="px-4 py-3 text-right">A</th>
                          <th className="px-4 py-3 text-right">SOG</th>
                          <th className="px-4 py-3 text-right">Saves</th>
                          <th className="px-4 py-3 text-right">Games</th>
                          <th className="px-4 py-3 text-right">FPTS</th>
                        </tr>
                      </thead>
                      <tbody>
                        {myTeamLive.players
                          .filter(p => p.games > 0)
                          .map(p => (
                          <tr key={p.id} className="border-t border-white/5">
                            <td className="px-4 py-3">
                              <Link to={`/players/${p.id}`} className="text-white hover:text-[#00D2FF]">
                                {p.name}
                              </Link>
                              <div className="text-xs text-[#52525B]">{p.team}</div>
                            </td>
                            <td className="px-4 py-3 text-[#A1A1AA]">{p.position}</td>
                            <td className="px-4 py-3 text-right text-white tabular-nums">{p.goals}</td>
                            <td className="px-4 py-3 text-right text-white tabular-nums">{p.assists}</td>
                            <td className="px-4 py-3 text-right text-white tabular-nums">{p.shots}</td>
                            <td className="px-4 py-3 text-right text-white tabular-nums">{p.saves || '-'}</td>
                            <td className="px-4 py-3 text-right text-[#A1A1AA] tabular-nums">{p.games}</td>
                            <td className="px-4 py-3 text-right text-[#00D2FF] font-bold tabular-nums">{p.fpts.toFixed(2)}</td>
                          </tr>
                        ))}
                        {myTeamLive.players.filter(p => p.games > 0).length === 0 && (
                          <tr><td colSpan={8} className="p-6 text-center text-[#A1A1AA]">
                            No rostered players have logged stats yet. Wait for the next puck drop.
                          </td></tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <div className="surface p-6 text-[#A1A1AA] text-sm">
                    Select a league with drafted rosters to see live player performance.
                  </div>
                )}
              </TabsContent>
            </Tabs>

            <div className="mt-10 flex items-center gap-2 text-xs text-[#52525B]">
              <Activity size={12} /> Auto-refresh every 60 seconds via Socket.IO broadcast
            </div>
          </>
        )}
      </div>
    </AppLayout>
  );
}
