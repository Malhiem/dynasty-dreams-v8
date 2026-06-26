import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import api from '@/lib/api';
import { Badge } from '@/components/ui/badge';
import { Calendar, TrendingUp, TrendingDown, Minus, Flame, ArrowRight, Loader2 } from 'lucide-react';
import { useGlobalSocketEvent } from '@/hooks/use-global-socket';
import { useActiveLeague } from '@/hooks/use-active-league';

function RankDelta({ delta }) {
  if (delta > 0) {
    return (
      <span className="flex items-center gap-1 text-emerald-400 text-xs font-semibold">
        <TrendingUp size={12} /> +{delta}
      </span>
    );
  }
  if (delta < 0) {
    return (
      <span className="flex items-center gap-1 text-red-400 text-xs font-semibold">
        <TrendingDown size={12} /> {delta}
      </span>
    );
  }
  return (
    <span className="flex items-center gap-1 text-[#52525B] text-xs">
      <Minus size={12} /> 0
    </span>
  );
}

export default function MyWeekAtAGlance() {
  const navigate = useNavigate();
  const { switchLeague, leagueId: activeLeagueId } = useActiveLeague();

  // Iter 230r — Clicking one of my own teams should land me on the
  // Lovable Roster page (`/roster`) for THAT team, not the legacy
  // `/teams/{id}` page. If the team belongs to a different league
  // than the currently active one, switch the active league first so
  // the Roster page renders the right roster on arrival.
  const openOwnTeam = (e, s) => {
    e.preventDefault();
    if (s.league_id && s.league_id !== activeLeagueId && typeof switchLeague === "function") {
      switchLeague(s.league_id);
    }
    navigate("/roster");
  };
  const [summaries, setSummaries] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = () =>
    api
      .get('/users/me/week-at-a-glance')
      .then(({ data }) => setSummaries(data.summaries || []))
      .catch(() => setSummaries([]))
      .finally(() => setLoading(false));

  useEffect(() => {
    load();
  }, []);

  // Auto-refresh when the live-scoring worker broadcasts an update
  useGlobalSocketEvent('live_scoring_update', () => load());

  if (loading) {
    return (
      <div className="surface p-6 mb-8 border border-white/5">
        <div className="flex items-center gap-2 text-[#A1A1AA]">
          <Loader2 size={16} className="animate-spin" /> Loading your week…
        </div>
      </div>
    );
  }

  if (!summaries || summaries.length === 0) return null;

  return (
    <div data-testid="my-week-at-a-glance" className="mb-8">
      <div className="flex items-center gap-2 mb-4">
        <Calendar size={18} className="text-[#00D2FF]" />
        <h2 className="font-heading text-xl font-bold text-white tracking-wide">
          MY WEEK AT A GLANCE
        </h2>
        <Badge className="bg-white/5 border-white/10 text-[#A1A1AA] text-[10px]">
          {summaries.length} {summaries.length === 1 ? 'TEAM' : 'TEAMS'}
        </Badge>
      </div>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {summaries.map((s) => (
          <div
            key={s.team_id}
            data-testid={`week-glance-card-${s.team_id}`}
            className="surface p-5 border border-white/5 hover:border-[#00D2FF]/40 transition-colors"
          >
            <div className="flex items-start justify-between gap-2 mb-3">
              <div className="min-w-0 flex-1">
                <Link
                  to={`/leagues/${s.league_id}`}
                  data-testid={`week-glance-league-link-${s.team_id}`}
                  className="text-[11px] uppercase tracking-wider text-[#52525B] hover:text-[#00D2FF] transition-colors block"
                >
                  {s.league_name}
                </Link>
                <Link
                  to="/roster"
                  onClick={(e) => openOwnTeam(e, s)}
                  data-testid={`week-glance-team-link-${s.team_id}`}
                  className="text-white font-bold text-base hover:text-[#00D2FF] transition-colors truncate block"
                >
                  {s.team_name}
                </Link>
              </div>
              <div className="text-right shrink-0">
                <div className="text-[10px] uppercase text-[#52525B]">Rank</div>
                <div className="flex items-center gap-2">
                  <div className="text-white font-bold text-lg tabular-nums">
                    {s.rank ?? '—'}
                    <span className="text-[#52525B] text-xs">/{s.total_teams ?? '?'}</span>
                  </div>
                  <RankDelta delta={s.rank_delta || 0} />
                </div>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3 mb-3">
              <div className="bg-white/5 rounded-lg p-3">
                <div className="text-[10px] uppercase text-[#52525B] tracking-wider">Today</div>
                <div className="text-xl font-bold text-[#00D2FF] tabular-nums">
                  {s.daily_fpts.toFixed(1)}
                </div>
              </div>
              <div className="bg-white/5 rounded-lg p-3">
                <div className="text-[10px] uppercase text-[#52525B] tracking-wider">This Week</div>
                <div className="text-xl font-bold text-white tabular-nums">
                  {s.weekly_fpts.toFixed(1)}
                </div>
              </div>
            </div>

            {s.opponent && (
              <Link
                to={`/matchup?league=${s.league_id}`}
                data-testid={`week-glance-opponent-${s.team_id}`}
                className="block mb-3 bg-white/5 rounded-lg p-3 hover:bg-white/10 transition-colors"
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="min-w-0 flex-1">
                    <div className="text-[10px] uppercase text-[#52525B] tracking-wider">
                      Week {s.opponent.week} Matchup · vs
                    </div>
                    <div className="text-white text-sm font-semibold truncate">
                      {s.opponent.opponent_team_name || 'TBD'}
                    </div>
                  </div>
                  <div className="text-right shrink-0">
                    <div className="text-[10px] uppercase text-[#52525B] tracking-wider">Their wk</div>
                    <div className={`text-lg font-bold tabular-nums ${s.weekly_fpts >= s.opponent.opponent_weekly_fpts ? 'text-white' : 'text-red-400'}`}>
                      {Number(s.opponent.opponent_weekly_fpts || 0).toFixed(1)}
                    </div>
                  </div>
                </div>
                <div className="mt-1">
                  {s.weekly_fpts > s.opponent.opponent_weekly_fpts ? (
                    <Badge className="bg-emerald-500/15 text-emerald-400 border-emerald-500/30 text-[10px]">
                      Winning · +{(s.weekly_fpts - s.opponent.opponent_weekly_fpts).toFixed(1)}
                    </Badge>
                  ) : s.weekly_fpts < s.opponent.opponent_weekly_fpts ? (
                    <Badge className="bg-red-500/15 text-red-400 border-red-500/30 text-[10px]">
                      Losing · -{(s.opponent.opponent_weekly_fpts - s.weekly_fpts).toFixed(1)}
                    </Badge>
                  ) : (
                    <Badge className="bg-amber-500/15 text-amber-400 border-amber-500/30 text-[10px]">Tied</Badge>
                  )}
                </div>
              </Link>
            )}

            {s.top_performer ? (
              <Link
                to={`/players/${s.top_performer.id}`}
                data-testid={`week-glance-top-perf-${s.team_id}`}
                className="block border-t border-white/5 pt-3 hover:bg-white/5 -mx-2 px-2 rounded transition-colors"
              >
                <div className="flex items-center gap-2 text-[10px] uppercase text-[#52525B] tracking-wider mb-1">
                  <Flame size={10} className="text-orange-400" />
                  Top Performer Today
                </div>
                <div className="flex items-center justify-between">
                  <div className="min-w-0 flex-1">
                    <div className="text-white text-sm font-semibold truncate">
                      {s.top_performer.name}
                    </div>
                    <div className="text-[#A1A1AA] text-[11px]">
                      {s.top_performer.team} · {s.top_performer.position}
                      {s.top_performer.is_goalie ? (
                        <>
                          {' · '}
                          {s.top_performer.saves} SV / {s.top_performer.goals_against} GA
                          {s.top_performer.shutouts > 0 && ' · SHO'}
                          {s.top_performer.decision && ` · ${s.top_performer.decision}`}
                        </>
                      ) : (
                        <>
                          {' · '}
                          {s.top_performer.goals}G {s.top_performer.assists}A {s.top_performer.shots}SOG
                        </>
                      )}
                    </div>
                  </div>
                  <div className="text-[#00D2FF] font-bold text-sm tabular-nums">
                    +{s.top_performer.fpts.toFixed(1)}
                  </div>
                </div>
              </Link>
            ) : (
              <div className="text-[#52525B] text-xs border-t border-white/5 pt-3">
                No roster scoring today — next games will populate here.
              </div>
            )}

            <Link
              to="/roster"
              onClick={(e) => openOwnTeam(e, s)}
              data-testid={`week-glance-open-team-${s.team_id}`}
              className="mt-3 text-[#00D2FF] text-xs font-semibold flex items-center gap-1 hover:gap-2 transition-all"
            >
              Open team <ArrowRight size={12} />
            </Link>
          </div>
        ))}
      </div>
    </div>
  );
}
