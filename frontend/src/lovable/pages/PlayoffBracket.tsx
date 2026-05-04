// @ts-nocheck
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/lib/api";
import TeamLogo from "@/lovable/components/TeamLogo";
import { Trophy, Crown, ChevronRight } from "lucide-react";

interface BracketTeam {
  team_id: string;
  team_name: string;
  team_abbr?: string | null;
  team_logo_url?: string | null;
  owner_name?: string;
  seed: number;
  wins?: number;
  losses?: number;
  ties?: number;
  points_for?: number;
  games_back?: number;
}

interface Matchup {
  high_seed: BracketTeam | null;
  low_seed: BracketTeam | null;
  projected_winner?: string | null;
  status?: string;
  home_score?: number;
  away_score?: number;
  week?: number;
}

interface Round {
  name: string;
  matchups: Matchup[];
  byes?: BracketTeam[];
}

interface BracketData {
  league_id: string;
  playoff_size: number;
  playoff_teams: BracketTeam[];
  bye_teams: BracketTeam[];
  rounds: Round[];
  status: string;
}

const SEED_COLOR = [
  "text-accent",
  "text-primary",
  "text-success",
  "text-foreground",
  "text-muted-foreground",
  "text-muted-foreground",
  "text-muted-foreground",
  "text-muted-foreground",
];

const TeamCard = ({ team, isWinner, isLoser }: { team: BracketTeam | null; isWinner?: boolean; isLoser?: boolean }) => {
  if (!team) {
    return (
      <div className="border border-dashed border-border rounded-md p-3 h-[56px] flex items-center gap-2 text-muted-foreground/60 text-xs italic">
        TBD
      </div>
    );
  }
  return (
    <div
      className={`flex items-center gap-2 rounded-md px-2.5 py-2 border transition-colors h-[56px] ${
        isWinner
          ? "border-accent/60 bg-accent/10"
          : isLoser
          ? "border-border/40 bg-secondary/10 opacity-60"
          : "border-border bg-secondary/30"
      }`}
      data-testid={`bracket-team-${team.team_id}`}
    >
      <span className={`text-xs font-bold w-5 text-center ${SEED_COLOR[team.seed - 1] || "text-muted-foreground"}`}>
        {team.seed}
      </span>
      <TeamLogo logo={team.team_logo_url} name={team.team_name} abbr={team.team_abbr} size="xs" />
      <div className="flex-1 min-w-0">
        <div className={`text-sm truncate ${isWinner ? "font-semibold text-foreground" : "text-foreground"}`}>
          {team.team_name}
          {isWinner && <Crown className="inline-block h-3.5 w-3.5 ml-1 text-accent" />}
        </div>
        <div className="text-[10px] text-muted-foreground leading-tight">
          {team.wins ?? 0}-{team.losses ?? 0}{team.ties ? `-${team.ties}` : ""} · {team.points_for ?? 0} PF
        </div>
      </div>
    </div>
  );
};

const MatchupCard = ({ mu, status }: { mu: Matchup; status: string }) => {
  const hs = mu.high_seed;
  const ls = mu.low_seed;
  const winnerId = mu.projected_winner;
  const hsWin = hs && winnerId === hs.team_id && mu.status && mu.status !== "projected";
  const lsWin = ls && winnerId === ls.team_id && mu.status && mu.status !== "projected";
  const hasScore = typeof mu.home_score === "number" && typeof mu.away_score === "number";
  return (
    <div className="stat-card p-2.5 space-y-1.5" data-testid="bracket-matchup">
      <TeamCard
        team={hs}
        isWinner={!!hsWin || (status === "projected" && hs && winnerId === hs.team_id)}
        isLoser={!!lsWin}
      />
      <TeamCard
        team={ls}
        isWinner={!!lsWin}
        isLoser={!!hsWin || (status === "projected" && hs && winnerId === hs.team_id)}
      />
      {hasScore && (
        <div className="text-[10px] text-center text-muted-foreground pt-0.5">
          {mu.home_score} - {mu.away_score}
          {mu.week && <span className="ml-1.5 opacity-70">· Wk {mu.week}</span>}
        </div>
      )}
      {!hasScore && status === "projected" && hs && ls && (
        <div className="text-[10px] text-center text-muted-foreground pt-0.5 italic">
          Projected: {hs.team_abbr || hs.team_name.slice(0, 3).toUpperCase()} advances
        </div>
      )}
    </div>
  );
};

/**
 * Embeddable playoff tree view (no page chrome).
 * Used inside Standings → Playoffs tab.
 */
export const PlayoffBracketView = ({ leagueId }: { leagueId?: string | null }) => {
  const navigate = useNavigate();
  const [bracket, setBracket] = useState<BracketData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!leagueId) { setLoading(false); return; }
    let cancelled = false;
    setLoading(true);
    api.get(`/leagues/${leagueId}/playoff-bracket`)
      .then(({ data }) => { if (!cancelled) setBracket(data); })
      .catch(() => {})
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [leagueId]);

  if (loading) {
    return <div className="p-4 text-muted-foreground text-sm">Loading playoff tree...</div>;
  }

  if (!bracket || (bracket.rounds?.length || 0) === 0) {
    return (
      <div className="stat-card p-6 text-center" data-testid="playoff-bracket-empty">
        <Trophy className="h-8 w-8 text-muted-foreground/40 mx-auto mb-2" />
        <p className="text-sm text-muted-foreground">
          Not enough teams to generate a playoff bracket yet.
        </p>
      </div>
    );
  }

  const badgeColor = bracket.status === "actual"
    ? "bg-success/20 text-success border-success/30"
    : "bg-primary/15 text-primary border-primary/30";

  return (
    <div className="space-y-5" data-testid="playoff-bracket-page">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-2">
          <Trophy className="h-5 w-5 text-accent" />
          <h2 className="text-lg font-bold text-foreground">
            Playoff Tree <span className="text-sm font-normal text-muted-foreground">· {bracket.playoff_size}-team bracket</span>
          </h2>
        </div>
        <span
          className={`text-xs font-semibold px-2.5 py-1 rounded-full border ${badgeColor}`}
          data-testid="playoff-bracket-status"
        >
          {bracket.status === "actual" ? "LIVE · Actual Playoffs" : "PROJECTED · If season ended today"}
        </span>
      </div>

      <div className="overflow-x-auto" data-testid="playoff-bracket-rounds">
        <div className="flex gap-4 min-w-max items-stretch">
          {bracket.rounds.map((rd, rdx) => (
            <div
              key={rd.name}
              className="flex-1 min-w-[260px] space-y-3"
              data-testid={`bracket-round-${rdx}`}
            >
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-bold text-foreground uppercase tracking-wide">
                  {rd.name}
                </h3>
                {rdx < bracket.rounds.length - 1 && (
                  <ChevronRight className="h-4 w-4 text-muted-foreground/40" />
                )}
              </div>
              {rd.byes && rd.byes.length > 0 && (
                <div className="space-y-1.5">
                  <div className="text-[10px] uppercase tracking-wider text-muted-foreground/70 font-semibold">
                    Byes to Semis
                  </div>
                  {rd.byes.map(t => (
                    <div
                      key={t.team_id}
                      className="flex items-center gap-2 rounded-md px-2.5 py-1.5 bg-accent/10 border border-accent/30"
                      data-testid={`bracket-bye-${t.team_id}`}
                    >
                      <span className="text-xs font-bold text-accent w-5 text-center">{t.seed}</span>
                      <TeamLogo logo={t.team_logo_url} name={t.team_name} abbr={t.team_abbr} size="xs" />
                      <span className="text-xs font-medium truncate">{t.team_name}</span>
                    </div>
                  ))}
                </div>
              )}
              <div
                className="space-y-4 justify-around flex flex-col"
                style={{ minHeight: `${120 * (bracket.rounds[0]?.matchups.length || 1)}px` }}
              >
                {rd.matchups.map((mu, i) => (
                  <MatchupCard key={i} mu={mu} status={bracket.status} />
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="stat-card p-4 space-y-2">
        <h3 className="text-sm font-bold text-foreground">Playoff Seeds</h3>
        <div className="flex flex-wrap gap-2">
          {bracket.playoff_teams.map((t) => (
            <button
              key={t.team_id}
              onClick={() => navigate(`/teams/${t.team_id}`)}
              className="flex items-center gap-2 rounded-md px-2.5 py-1.5 bg-secondary/30 border border-border hover:bg-secondary/50 transition-colors text-xs"
              data-testid={`bracket-seed-chip-${t.seed}`}
            >
              <span className={`font-bold ${SEED_COLOR[t.seed - 1] || "text-muted-foreground"}`}>#{t.seed}</span>
              <TeamLogo logo={t.team_logo_url} name={t.team_name} abbr={t.team_abbr} size="xs" />
              <span className="font-medium">{t.team_name}</span>
              <span className="text-muted-foreground">({t.wins}-{t.losses}{t.ties ? `-${t.ties}` : ""})</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
};

export default PlayoffBracketView;
