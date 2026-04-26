// @ts-nocheck
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api from "@/lib/api";
import { useActiveLeague } from "@/hooks/use-active-league";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ArrowRight, Flame, Radio } from "lucide-react";
import TeamLogo from "@/lovable/components/TeamLogo";

/**
 * Live header that sits atop the Lovable Team page.
 * Reads the user's active team from /api/live-scoring/team/{id} and surfaces
 * real roster size, live fpts, rank, and a "View full roster" CTA.
 */
export default function LiveTeamHeader() {
  const { league, leagueTeams, myTeam, myLeagues, leagueId, switchLeague } = useActiveLeague();
  const [live, setLive] = useState(null);
  const [week, setWeek] = useState(null);

  useEffect(() => {
    if (!myTeam?.id) return;
    let cancelled = false;
    Promise.all([
      api.get(`/live-scoring/team/${myTeam.id}`),
      api.get(`/live-scoring/team/${myTeam.id}/week`),
    ])
      .then(([l, w]) => {
        if (cancelled) return;
        setLive(l.data);
        setWeek(w.data);
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [myTeam?.id]);

  if (!myTeam) {
    return (
      <div className="surface p-5 mb-6 border border-white/5 text-sm text-[#A1A1AA]">
        You don't own a team in any demo league yet. Visit <Link to="/leagues" className="text-[#00D2FF]">/leagues</Link> to join one.
      </div>
    );
  }

  const top = live?.players?.filter(p => p.games > 0)?.[0];

  return (
    <div
      data-testid="live-team-header"
      className="surface p-5 mb-6 border border-[#00D2FF]/30 bg-gradient-to-br from-[#00D2FF]/5 to-transparent"
    >
      <div className="flex items-start justify-between flex-wrap gap-4">
        <div className="flex items-start gap-4 flex-1 min-w-[240px]">
          <TeamLogo
            logo={myTeam.logo_url}
            name={myTeam.name}
            abbr={myTeam.logo_abbr}
            size="lg"
            className="rounded-full mt-1"
          />
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-2">
              <Radio size={14} className="text-[#00D2FF] animate-pulse" />
              <span className="text-[10px] uppercase tracking-widest text-[#00D2FF]">LIVE · {league?.name}</span>
            </div>
            <Link
              to={`/teams/${myTeam.id}`}
              className="font-heading text-3xl font-bold text-white tracking-tight hover:text-[#00D2FF] transition-colors block"
            >
              {myTeam.name}
            </Link>
            <div className="text-[#A1A1AA] text-sm mt-1">
              Record <span className="text-white">{myTeam.wins || 0}–{myTeam.losses || 0}–{myTeam.ties || 0}</span>
              {' · '}
              Roster <span className="text-white">{(myTeam.roster || []).length} players</span>
              {' · '}
              Rank <span className="text-white">#{week?.rank || '—'}/{week?.total_teams || leagueTeams?.length || '?'}</span>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-6 flex-wrap">
          <div className="text-right">
            <div className="text-[10px] uppercase text-[#52525B]">Today</div>
            <div className="text-2xl font-bold text-[#00D2FF] tabular-nums">
              {week?.daily_fpts?.toFixed(1) || '—'}
            </div>
          </div>
          <div className="text-right">
            <div className="text-[10px] uppercase text-[#52525B]">This Week</div>
            <div className="text-2xl font-bold text-white tabular-nums">
              {week?.weekly_fpts?.toFixed(1) || '—'}
            </div>
          </div>
          <div className="text-right">
            <div className="text-[10px] uppercase text-[#52525B]">Season FPTS</div>
            <div className="text-2xl font-bold text-white tabular-nums">
              {live?.live_points?.toFixed(1) || '—'}
            </div>
          </div>
        </div>
      </div>

      {top && (
        <Link
          to={`/players/${top.id}`}
          className="mt-4 flex items-center gap-3 p-3 bg-black/30 rounded-lg hover:bg-black/50 transition-colors"
        >
          <Flame size={16} className="text-orange-400 shrink-0" />
          <div className="flex-1 min-w-0">
            <div className="text-[10px] uppercase tracking-wider text-[#A1A1AA]">Top Performer</div>
            <div className="text-white text-sm font-semibold truncate">{top.name}</div>
            <div className="text-[#52525B] text-[11px]">
              {top.team} · {top.position}
              {top.is_goalie
                ? ` · ${top.saves || 0} SV / ${top.goals_against || 0} GA`
                : ` · ${top.goals}G ${top.assists}A ${top.shots}SOG`}
            </div>
          </div>
          <div className="text-[#00D2FF] font-bold tabular-nums">+{top.fpts?.toFixed(1)}</div>
        </Link>
      )}

      <div className="mt-4 flex items-center justify-between flex-wrap gap-2">
        {myLeagues?.length > 1 && (
          <Select value={leagueId || undefined} onValueChange={switchLeague}>
            <SelectTrigger className="w-[240px] h-9 text-sm" data-testid="live-team-league-switcher">
              <SelectValue placeholder="Pick a league" />
            </SelectTrigger>
            <SelectContent>
              {myLeagues.map(l => (
                <SelectItem key={l.id} value={l.id}>{l.name}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
        <Link
          to={`/teams/${myTeam.id}`}
          data-testid="live-team-full-roster-link"
          className="ml-auto text-[#00D2FF] text-sm font-semibold flex items-center gap-1 hover:gap-2 transition-all"
        >
          View full roster <ArrowRight size={14} />
        </Link>
      </div>
    </div>
  );
}
