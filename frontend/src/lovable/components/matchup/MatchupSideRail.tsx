// @ts-nocheck
import { useEffect, useState, useMemo } from "react";
import { Card } from "@/components/ui/card";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Radio, ChevronRight } from "lucide-react";
import { Link } from "react-router-dom";
import api from "@/lib/api";

/**
 * Live mini-cards for every other matchup in the league this week. Shows
 * away/home logo + score + a simple win-probability bar derived from current
 * fantasy points (with a Bayesian smoothing of 25 to soften early-week gaps).
 *
 * Auto-refreshes every 30s.
 */

const POLL_MS = 30_000;
const SMOOTH = 25;

function winProb(a, b) {
  const denom = a + b + SMOOTH * 2;
  if (denom <= 0) return 0.5;
  return Math.max(0.01, Math.min(0.99, (a + SMOOTH) / denom));
}

function teamInitials(name = "") {
  return name.split(/\s+/).slice(0, 2).map((s) => s[0]?.toUpperCase()).join("");
}

export function MatchupSideRail({ leagueId, myMatchupId, currentWeek }) {
  const [matchups, setMatchups] = useState([]);
  const [scoresByTeam, setScoresByTeam] = useState({});
  const [teamLogos, setTeamLogos] = useState({});

  // 1) Pull current-week matchups
  useEffect(() => {
    if (!leagueId) return undefined;
    let cancelled = false;
    const load = async () => {
      try {
        const { data } = await api.get(`/matchups/${leagueId}/current-week`);
        if (cancelled) return;
        setMatchups(data?.matchups || []);
      } catch (e) {
        // best-effort
      }
    };
    load();
    const id = setInterval(load, POLL_MS);
    return () => { cancelled = true; clearInterval(id); };
  }, [leagueId]);

  // 2) Resolve team logos in one shot
  useEffect(() => {
    if (!leagueId) return undefined;
    let cancelled = false;
    api.get(`/teams?league_id=${leagueId}`).then(({ data }) => {
      if (cancelled) return;
      const logos = {};
      const list = Array.isArray(data) ? data : (data?.teams || []);
      for (const t of list) {
        const id = t.id || t._id;
        if (id) logos[id] = { name: t.name, logo: t.logo_url };
      }
      setTeamLogos(logos);
    }).catch(() => {});
    return () => { cancelled = true; };
  }, [leagueId]);

  // 3) Pull live FPTS per team in this matchup set
  useEffect(() => {
    if (!matchups.length) return undefined;
    let cancelled = false;
    const tids = new Set();
    for (const m of matchups) {
      tids.add(m.home_team_id);
      tids.add(m.away_team_id);
    }
    const load = async () => {
      const next = {};
      await Promise.all(Array.from(tids).map(async (tid) => {
        try {
          const { data } = await api.get(`/live-scoring/team/${tid}`);
          next[tid] = Number(data?.live_points || data?.total_fpts || 0);
        } catch {
          next[tid] = 0;
        }
      }));
      if (!cancelled) setScoresByTeam(next);
    };
    load();
    const id = setInterval(load, POLL_MS);
    return () => { cancelled = true; clearInterval(id); };
  }, [matchups]);

  const otherMatchups = useMemo(
    () => matchups.filter((m) => !myMatchupId || m.id !== myMatchupId),
    [matchups, myMatchupId],
  );

  return (
    <aside className="w-full lg:w-[300px] shrink-0 space-y-3" data-testid="matchup-side-rail">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold flex items-center gap-1.5">
          <Radio className="h-3.5 w-3.5 text-primary" />
          Other Matchups
          {currentWeek != null && (
            <span className="text-[10px] text-muted-foreground font-normal ml-1">
              · Week {currentWeek}
            </span>
          )}
        </h3>
        <Link
          to="/live"
          data-testid="matchup-live-link"
          className="text-[11px] text-primary hover:underline flex items-center gap-0.5"
        >
          League Live <ChevronRight className="h-3 w-3" />
        </Link>
      </div>

      {otherMatchups.length === 0 && (
        <p className="text-[11px] text-muted-foreground italic" data-testid="matchup-side-rail-empty">
          No other live matchups this week.
        </p>
      )}

      {otherMatchups.map((m) => {
        const a = scoresByTeam[m.away_team_id] ?? 0;
        const h = scoresByTeam[m.home_team_id] ?? 0;
        const probAway = winProb(a, h);
        const probHome = 1 - probAway;
        const aMeta = teamLogos[m.away_team_id] || { name: m.away_team_name };
        const hMeta = teamLogos[m.home_team_id] || { name: m.home_team_name };
        return (
          <Card
            key={m.id}
            data-testid={`matchup-side-rail-card-${m.id}`}
            className="p-3 bg-card/80 hover:bg-card transition-colors space-y-2"
          >
            {[{
              tid: m.away_team_id, name: aMeta.name || m.away_team_name, logo: aMeta.logo,
              score: a, prob: probAway,
            }, {
              tid: m.home_team_id, name: hMeta.name || m.home_team_name, logo: hMeta.logo,
              score: h, prob: probHome,
            }].map((row, idx) => (
              <div key={row.tid} className="flex items-center gap-2">
                <Avatar className="h-6 w-6 shrink-0">
                  {row.logo ? <AvatarImage src={row.logo} alt={row.name} /> : null}
                  <AvatarFallback className="text-[10px] bg-secondary">
                    {teamInitials(row.name)}
                  </AvatarFallback>
                </Avatar>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between gap-1">
                    <span className="text-[12px] font-medium truncate">{row.name}</span>
                    <span className="text-[12px] font-semibold tabular-nums">
                      {row.score.toFixed(1)}
                    </span>
                  </div>
                  <div className="h-1 mt-0.5 rounded-full bg-secondary overflow-hidden">
                    <div
                      className={`h-full rounded-full ${
                        row.prob >= 0.5 ? "bg-emerald-500" : "bg-rose-500"
                      }`}
                      style={{ width: `${(row.prob * 100).toFixed(0)}%` }}
                    />
                  </div>
                  <div className="flex items-center justify-between mt-0.5">
                    <span className="text-[10px] text-muted-foreground">
                      Win prob {(row.prob * 100).toFixed(0)}%
                    </span>
                    {idx === 0 && (a + h) > 0 && (
                      <Badge variant="outline" className="h-3.5 text-[9px] px-1 border-primary/30 text-primary">
                        LIVE
                      </Badge>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </Card>
        );
      })}
    </aside>
  );
}
