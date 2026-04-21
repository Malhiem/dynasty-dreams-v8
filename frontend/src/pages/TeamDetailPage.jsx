import { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { AppLayout } from '@/components/layout/AppLayout';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table';
import { ArrowLeft, Trophy, Users, Calendar, Loader2, Flame } from 'lucide-react';
import api from '@/lib/api';

export default function TeamDetailPage() {
  const { id } = useParams();
  const [team, setTeam] = useState(null);
  const [league, setLeague] = useState(null);
  const [liveData, setLiveData] = useState(null);
  const [weekData, setWeekData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      setLoading(true);
      try {
        const { data: t } = await api.get(`/teams/${id}`);
        if (cancelled) return;
        setTeam(t);
        const [leagueRes, liveRes, weekRes] = await Promise.all([
          api.get(`/leagues/${t.league_id}`),
          api.get(`/live-scoring/team/${id}`).catch(() => ({ data: null })),
          api.get(`/live-scoring/team/${id}/week`).catch(() => ({ data: null })),
        ]);
        if (cancelled) return;
        setLeague(leagueRes.data);
        setLiveData(liveRes.data);
        setWeekData(weekRes.data);
      } catch (e) {
        console.error('team load failed', e);
      }
      if (!cancelled) setLoading(false);
    };
    load();
    return () => { cancelled = true; };
  }, [id]);

  if (loading) {
    return (
      <AppLayout>
        <div className="max-w-6xl mx-auto flex items-center gap-2 text-[#A1A1AA] p-8">
          <Loader2 size={16} className="animate-spin" /> Loading team…
        </div>
      </AppLayout>
    );
  }

  if (!team) {
    return (
      <AppLayout>
        <div className="max-w-6xl mx-auto surface p-8 text-center">
          <p className="text-white mb-3">Team not found.</p>
          <Link to="/dashboard" className="text-[#00D2FF]">Back to dashboard</Link>
        </div>
      </AppLayout>
    );
  }

  const players = liveData?.players || [];
  const activePlayers = players.filter(p => p.games > 0);

  return (
    <AppLayout>
      <div data-testid="team-detail-page" className="max-w-6xl mx-auto">
        <Link
          to={`/leagues/${team.league_id}`}
          data-testid="team-detail-back-to-league"
          className="inline-flex items-center gap-2 text-[#A1A1AA] hover:text-white text-sm mb-4"
        >
          <ArrowLeft size={14} /> Back to {league?.name || 'League'}
        </Link>

        <div className="flex items-start justify-between flex-wrap gap-4 mb-8">
          <div>
            <Link
              to={`/leagues/${team.league_id}`}
              className="text-xs uppercase tracking-widest text-[#52525B] hover:text-[#00D2FF] transition-colors"
            >
              {league?.name || 'League'}
            </Link>
            <h1 className="font-heading text-4xl sm:text-5xl font-bold tracking-tight text-white mt-1">
              {team.name}
            </h1>
            <p className="text-[#A1A1AA] text-sm mt-2 flex items-center gap-2 flex-wrap">
              <Users size={14} />
              Owner: <span className="text-white">{team.owner_name}</span>
              <span>·</span>
              <span>{team.wins}–{team.losses}–{team.ties}</span>
              <span>·</span>
              <span>{team.points_for.toFixed(1)} PF</span>
            </p>
          </div>
          {weekData && (
            <div className="flex gap-3">
              <div className="surface px-5 py-3 min-w-[110px]">
                <div className="text-[10px] uppercase text-[#52525B]">Today</div>
                <div className="text-2xl font-bold text-[#00D2FF] tabular-nums">
                  {weekData.daily_fpts.toFixed(1)}
                </div>
              </div>
              <div className="surface px-5 py-3 min-w-[110px]">
                <div className="text-[10px] uppercase text-[#52525B]">Week</div>
                <div className="text-2xl font-bold text-white tabular-nums">
                  {weekData.weekly_fpts.toFixed(1)}
                </div>
              </div>
              <div className="surface px-5 py-3 min-w-[110px]">
                <div className="text-[10px] uppercase text-[#52525B]">Rank</div>
                <div className="text-2xl font-bold text-white tabular-nums">
                  {weekData.rank ?? '—'}
                  <span className="text-[#52525B] text-sm">/{weekData.total_teams ?? '?'}</span>
                </div>
              </div>
            </div>
          )}
        </div>

        {weekData?.top_performer && (
          <Card className="bg-gradient-to-br from-orange-500/10 to-transparent border-orange-500/30 mb-6" data-testid="team-detail-top-performer-card">
            <CardContent className="p-5 flex items-center justify-between gap-4 flex-wrap">
              <div className="flex items-center gap-3">
                <Flame size={24} className="text-orange-400" />
                <div>
                  <div className="text-[10px] uppercase text-[#A1A1AA] tracking-wider">Top Performer Today</div>
                  <Link
                    to={`/players/${weekData.top_performer.id}`}
                    className="text-white font-bold text-lg hover:text-[#00D2FF]"
                  >
                    {weekData.top_performer.name}
                  </Link>
                  <div className="text-[#A1A1AA] text-xs">
                    {weekData.top_performer.team} · {weekData.top_performer.position} ·{' '}
                    {weekData.top_performer.goals}G {weekData.top_performer.assists}A {weekData.top_performer.shots}SOG
                  </div>
                </div>
              </div>
              <div className="text-4xl font-bold text-orange-300 tabular-nums">
                +{weekData.top_performer.fpts.toFixed(1)}
              </div>
            </CardContent>
          </Card>
        )}

        <Card className="bg-white/5 border-white/10">
          <CardHeader className="flex-row items-center justify-between gap-4">
            <CardTitle className="text-white flex items-center gap-2">
              <Trophy size={16} className="text-[#00D2FF]" /> Roster
              <Badge className="bg-white/10 text-white border-white/10 text-[10px]">
                {players.length} total
              </Badge>
              <Badge className="bg-emerald-500/20 text-emerald-400 border-emerald-500/40 text-[10px]">
                {activePlayers.length} scoring
              </Badge>
            </CardTitle>
            {liveData?.live_points != null && (
              <div className="text-right">
                <div className="text-[10px] uppercase text-[#52525B]">Season FPTS</div>
                <div className="text-2xl font-bold text-[#00D2FF] tabular-nums">
                  {liveData.live_points.toFixed(2)}
                </div>
              </div>
            )}
          </CardHeader>
          <CardContent>
            {players.length === 0 ? (
              <div className="text-[#A1A1AA] text-sm py-4">No rostered players yet.</div>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow className="border-white/5">
                    <TableHead className="text-[#52525B] uppercase tracking-wider text-xs">Player</TableHead>
                    <TableHead className="text-[#52525B] uppercase tracking-wider text-xs">Pos</TableHead>
                    <TableHead className="text-[#52525B] uppercase tracking-wider text-xs text-right">G</TableHead>
                    <TableHead className="text-[#52525B] uppercase tracking-wider text-xs text-right">A</TableHead>
                    <TableHead className="text-[#52525B] uppercase tracking-wider text-xs text-right">SOG</TableHead>
                    <TableHead className="text-[#52525B] uppercase tracking-wider text-xs text-right">Games</TableHead>
                    <TableHead className="text-[#52525B] uppercase tracking-wider text-xs text-right">FPTS</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {players.map(p => (
                    <TableRow key={p.id} className="border-white/5 hover:bg-white/5">
                      <TableCell>
                        <Link
                          to={`/players/${p.id}`}
                          className="text-white hover:text-[#00D2FF]"
                          data-testid={`team-roster-player-${p.id}`}
                        >
                          {p.name}
                        </Link>
                        <div className="text-xs text-[#52525B]">{p.team}</div>
                      </TableCell>
                      <TableCell className="text-[#A1A1AA]">{p.position}</TableCell>
                      <TableCell className="text-white tabular-nums text-right">{p.goals}</TableCell>
                      <TableCell className="text-white tabular-nums text-right">{p.assists}</TableCell>
                      <TableCell className="text-white tabular-nums text-right">{p.shots}</TableCell>
                      <TableCell className="text-[#A1A1AA] tabular-nums text-right">{p.games}</TableCell>
                      <TableCell className="text-[#00D2FF] font-bold tabular-nums text-right">{p.fpts.toFixed(2)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      </div>
    </AppLayout>
  );
}
