// @ts-nocheck
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useActiveLeague } from "@/hooks/use-active-league";
import api from "@/lib/api";
import { Trophy } from "lucide-react";

type ClinchStatus = "presidents" | "conference" | "division" | "playoff" | "eliminated";

interface Team {
  rank: number;
  name: string;
  record: string;
  points: number;
  streak: string;
  isUser?: boolean;
  division: "Atlantic" | "Metropolitan" | "Central" | "Pacific";
  conference: "Eastern" | "Western";
  pointsFor: number;
  pointsAgainst: number;
  last5: ("W" | "L" | "T")[];
  clinched?: ClinchStatus[];
}

const CLINCH_CONFIG: Record<ClinchStatus, { label: string; title: string; className: string }> = {
  presidents: { label: "P", title: "President's Trophy – Best overall record", className: "bg-gold/20 text-gold border border-gold/30" },
  conference:  { label: "Z", title: "Clinched Conference",                      className: "bg-primary/20 text-primary border border-primary/30" },
  division:    { label: "Y", title: "Clinched Division",                         className: "bg-accent/20 text-accent border border-accent/30" },
  playoff:     { label: "X", title: "Clinched Playoff Spot",                     className: "bg-success/20 text-success border border-success/30" },
  eliminated:  { label: "E", title: "Eliminated from Playoff Contention",        className: "bg-destructive/20 text-destructive border border-destructive/30" },
};
const CLINCH_ORDER: ClinchStatus[] = ["presidents", "conference", "division", "playoff", "eliminated"];

const ClinchBadges = ({ statuses }: { statuses?: ClinchStatus[] }) => {
  if (!statuses?.length) return null;
  const highest = CLINCH_ORDER.find(s => statuses.includes(s));
  if (!highest) return null;
  const cfg = CLINCH_CONFIG[highest];
  return (
    <span title={cfg.title} className={`text-[10px] font-bold px-1 py-0.5 rounded cursor-default ${cfg.className}`}>
      {cfg.label}
    </span>
  );
};

// Iter 232N.68 — `mockStandings` (Ice Dragons, Team Frostbite, Blazers…)
// removed. This widget now fetches real standings from
// `/api/leagues/{leagueId}/standings` and renders an empty state when
// no games have been played yet.

type FilterType = "league" | "division" | "conference";

const Sparkline = ({ results }: { results: ("W" | "L" | "T")[] }) => (
  <div className="flex items-center gap-0.5">
    {results.map((r, i) => (
      <div
        key={i}
        className={`w-2.5 h-2.5 rounded-full ${
          r === "W" ? "bg-success" : r === "L" ? "bg-destructive" : "bg-muted-foreground"
        }`}
        title={r}
      />
    ))}
  </div>
);

// ─── Row ──────────────────────────────────────────────────────────────────────
const TeamRow = ({ team, displayRank, index }: { team: Team; displayRank: number; index: number }) => {
  const navigate = useNavigate();
  const diff = team.pointsFor - team.pointsAgainst;
  return (
    <div
      className={`flex items-center px-3 py-2.5 hover:bg-secondary/20 transition-colors animate-slide-up ${
        team.isUser ? "bg-primary/5 border-l-2 border-l-primary" : ""
      }`}
      style={{ animationDelay: `${index * 30}ms` }}
    >
      <span className={`w-6 text-center font-bold text-sm flex-shrink-0 ${
        displayRank === 1 ? "text-accent" :
        displayRank === 2 ? "text-muted-foreground" :
        displayRank === 3 ? "text-orange-400" : "text-muted-foreground"
      }`}>
        {displayRank}
      </span>

      <div className="flex-1 ml-2 flex items-center gap-1.5 min-w-0 flex-wrap">
        <p
          className={`font-medium text-sm truncate cursor-pointer hover:underline ${team.isUser ? "text-primary" : "text-foreground"}`}
          onClick={() => {
            const slug = team.name.toLowerCase().replace(/\s+/g, "-");
            navigate(`/team?team=${slug}`);
          }}
        >
          {team.name}
          {team.isUser && <span className="ml-1.5 text-xs bg-primary/20 text-primary px-1.5 py-0.5 rounded-full">You</span>}
        </p>
        <ClinchBadges statuses={team.clinched} />
        <span className="text-xs text-muted-foreground whitespace-nowrap flex-shrink-0">{team.record}</span>
      </div>

      <div className="w-16 flex justify-center flex-shrink-0">
        <Sparkline results={team.last5} />
      </div>
      <span className="w-12 text-right text-sm font-medium flex-shrink-0">{team.pointsFor}</span>
      <span className="w-12 text-right text-sm text-muted-foreground flex-shrink-0">{team.pointsAgainst}</span>
      <span className={`w-12 text-right text-sm font-medium flex-shrink-0 ${diff > 0 ? "text-success" : diff < 0 ? "text-destructive" : "text-muted-foreground"}`}>
        {diff > 0 ? "+" : ""}{diff}
      </span>
      <div className="w-12 flex justify-end flex-shrink-0">
        <span className={`text-xs font-medium px-1.5 py-0.5 rounded-full ${
          team.streak.startsWith("W") ? "bg-success/20 text-success" : "bg-destructive/20 text-destructive"
        }`}>
          {team.streak}
        </span>
      </div>
    </div>
  );
};

// ─── Division Group ───────────────────────────────────────────────────────────
const DivisionGroup = ({
  label,
  teams,
  startIndex,
}: {
  label: string;
  teams: (Team & { displayRank: number })[];
  startIndex: number;
}) => (
  <div>
    <div className="px-3 py-1.5 bg-secondary/50 border-y border-border/60">
      <span className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground">{label}</span>
    </div>
    {teams.map((team, i) => (
      <TeamRow key={team.name} team={team} displayRank={team.displayRank} index={startIndex + i} />
    ))}
  </div>
);

// ─── Widget ───────────────────────────────────────────────────────────────────
const Standings = () => {
  const [filter, setFilter] = useState<FilterType>("league");
  const [divisionFilter, setDivisionFilter] = useState<string>("all");
  const [conferenceFilter, setConferenceFilter] = useState<string>("all");

  // Iter 232N.68 — Pull real standings from the API for the ACTIVE
  // league. Previously this widget rendered `mockStandings` — a hard-
  // coded set of fake team names (Ice Dragons, Team Frostbite,
  // Blazers…) with fake W-L records. In a fresh sandbox league where
  // no games have played, that produced the "why are standings
  // showing data if the league hasn't played a game yet?" bug.
  const { leagueId, myTeam } = useActiveLeague();
  const [rows, setRows] = useState<any[]>([]);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let cancelled = false;
    if (!leagueId) { setRows([]); setLoaded(true); return; }
    const fetchStandings = async () => {
      try {
        const { data } = await api.get(`/leagues/${leagueId}/standings`);
        if (!cancelled) setRows(data?.standings ?? []);
      } catch {
        if (!cancelled) setRows([]);
      } finally {
        if (!cancelled) setLoaded(true);
      }
    };
    fetchStandings();
    // Iter 232N.69 — refetch when the sandbox top-bar simulates or
    // resets a week (fires a custom `sandbox:sim-week` event).
    const onSim = () => fetchStandings();
    window.addEventListener('sandbox:sim-week', onSim);
    return () => {
      cancelled = true;
      window.removeEventListener('sandbox:sim-week', onSim);
    };
  }, [leagueId]);

  // Map API rows to the row shape the rest of this widget already
  // understands. `myTeam` marks the highlighted row.
  const teams: Team[] = useMemo(() => rows.map((r: any) => {
    const gp = (r.wins || 0) + (r.losses || 0) + (r.ties || 0);
    const streak = gp === 0 ? "—" : ((r.wins || 0) > (r.losses || 0)
      ? `W${Math.min(r.wins || 0, 5)}`
      : `L${Math.min(r.losses || 0, 5)}`);
    return {
      rank: r.rank,
      name: r.team_name,
      record: `${r.wins || 0}-${r.losses || 0}-${r.ties || 0}`,
      points: Math.round(r.points_for || 0),
      streak,
      isUser: myTeam?.id && r.team_id === myTeam.id,
      division: r.division || "Unassigned",
      conference: r.conference || "Unassigned",
      pointsFor: Math.round(r.points_for || 0),
      pointsAgainst: Math.round(r.points_against || 0),
      last5: (r.last_5 || []) as ("W" | "L" | "T")[],
      clinched: r.clinched || undefined,
    };
  }), [rows, myTeam]);

  const gamesPlayedTotal = useMemo(
    () => teams.reduce((acc, t) => acc + (t.pointsFor || 0) + (t.pointsAgainst || 0), 0)
        + rows.reduce((acc: number, r: any) => acc + (r.wins || 0) + (r.losses || 0) + (r.ties || 0), 0),
    [teams, rows],
  );

  const getLeagueStandings = () =>
    teams.map((team, index) => ({ ...team, displayRank: index + 1 }));

  // Groups derived from real divisions / conferences on the teams.
  const divisionNames = useMemo(
    () => Array.from(new Set(teams.map(t => t.division))).sort(),
    [teams],
  );
  const conferenceNames = useMemo(
    () => Array.from(new Set(teams.map(t => t.conference))).sort(),
    [teams],
  );

  const getDivisionGroups = () => divisionNames.map(div => ({
    label: `${div} Division`,
    teams: teams
      .filter(t => t.division === div)
      .map((t, i) => ({ ...t, displayRank: i + 1 })),
  }));

  const getConferenceGroups = () => conferenceNames.map(conf => ({
    label: `${conf} Conference`,
    teams: teams
      .filter(t => t.conference === conf)
      .sort((a, b) => b.points - a.points)
      .map((t, i) => ({ ...t, displayRank: i + 1 })),
  }));

  const getFilteredSingle = () => {
    let filtered = [...teams];
    if (filter === "division") filtered = filtered.filter(t => t.division === divisionFilter);
    else if (filter === "conference") filtered = filtered.filter(t => t.conference === conferenceFilter);
    return filtered.map((t, i) => ({ ...t, displayRank: i + 1 }));
  };

  const showDivisionGroups = filter === "division" && divisionFilter === "all";
  const showConferenceGroups = filter === "conference" && conferenceFilter === "all";

  return (
    <div className="stat-card p-0 overflow-hidden">
      {/* Header */}
      <div className="p-4 border-b border-border">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-lg font-semibold">League Standings</h3>
          <a href="/standings" className="text-xs text-primary font-medium cursor-pointer hover:underline">View All →</a>
        </div>
        <div className="flex flex-wrap gap-2">
          <Select value={filter} onValueChange={(value: FilterType) => setFilter(value)}>
            <SelectTrigger className="w-[120px] h-8 text-xs">
              <SelectValue placeholder="View by" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="league">League</SelectItem>
              <SelectItem value="division">Division</SelectItem>
              <SelectItem value="conference">Conference</SelectItem>
            </SelectContent>
          </Select>
          {filter === "division" && (
            <Select value={divisionFilter} onValueChange={setDivisionFilter}>
              <SelectTrigger className="w-[130px] h-8 text-xs">
                <SelectValue placeholder="Division" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Divisions</SelectItem>
                {divisionNames.map(d => (
                  <SelectItem key={d} value={d}>{d}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
          {filter === "conference" && (
            <Select value={conferenceFilter} onValueChange={setConferenceFilter}>
              <SelectTrigger className="w-[130px] h-8 text-xs">
                <SelectValue placeholder="Conference" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Conferences</SelectItem>
                {conferenceNames.map(c => (
                  <SelectItem key={c} value={c}>{c}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        </div>
        {/* Clinch Legend */}
        <div className="flex flex-wrap gap-x-4 gap-y-1 mt-3 pt-3 border-t border-border/50">
          {CLINCH_ORDER.map(s => {
            const cfg = CLINCH_CONFIG[s];
            return (
              <div key={s} className="flex items-center gap-1">
                <span className={`text-[10px] font-bold px-1 py-0.5 rounded ${cfg.className}`}>{cfg.label}</span>
                <span className="text-[10px] text-muted-foreground">{cfg.title.split(" – ")[0].replace("Clinched ","").replace("Eliminated from ","Elim. from ")}</span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Column headers */}
      <div className="flex items-center px-3 py-2 text-xs font-medium text-muted-foreground border-b border-border bg-secondary/30">
        <span className="w-6 text-center flex-shrink-0">#</span>
        <span className="flex-1 ml-2">Team</span>
        <span className="w-16 text-center flex-shrink-0">Last 5</span>
        <span className="w-12 text-right flex-shrink-0">PF</span>
        <span className="w-12 text-right flex-shrink-0">PA</span>
        <span className="w-12 text-right flex-shrink-0">+/-</span>
        <span className="w-12 text-right flex-shrink-0">Streak</span>
      </div>

      {/* Rows */}
      <div className="divide-y divide-border/50" data-testid="standings-widget-rows">
        {/* Iter 232N.68 — Honest empty state. In a sandbox (or any
            league that hasn't played yet) all teams have 0 wins, 0
            losses, 0 points. Showing a table of zeros is confusing —
            show a friendly hint instead. */}
        {loaded && teams.length === 0 && (
          <div className="flex flex-col items-center justify-center gap-2 py-10 px-4 text-center"
               data-testid="standings-widget-empty">
            <Trophy className="h-8 w-8 text-muted-foreground/50" />
            <p className="text-sm font-medium">No league selected</p>
            <p className="text-xs text-muted-foreground max-w-xs">
              Pick a league from the switcher to see its standings.
            </p>
          </div>
        )}
        {loaded && teams.length > 0 && gamesPlayedTotal === 0 && (
          <div className="flex flex-col items-center justify-center gap-2 py-8 px-4 text-center"
               data-testid="standings-widget-no-games">
            <Trophy className="h-8 w-8 text-muted-foreground/50" />
            <p className="text-sm font-medium">No games played yet</p>
            <p className="text-xs text-muted-foreground max-w-xs">
              Standings will populate once the first matchups are scored.
              All {teams.length} team{teams.length === 1 ? "" : "s"} start at 0-0-0.
            </p>
          </div>
        )}

        {loaded && teams.length > 0 && gamesPlayedTotal > 0 && filter === "league" &&
          getLeagueStandings().map((team, index) => (
            <TeamRow key={team.name} team={team} displayRank={team.displayRank} index={index} />
          ))
        }

        {loaded && teams.length > 0 && gamesPlayedTotal > 0 && showDivisionGroups &&
          (() => {
            let globalIndex = 0;
            return getDivisionGroups().map(group => {
              const el = <DivisionGroup key={group.label} label={group.label} teams={group.teams} startIndex={globalIndex} />;
              globalIndex += group.teams.length;
              return el;
            });
          })()
        }

        {loaded && teams.length > 0 && gamesPlayedTotal > 0 && filter === "division" && divisionFilter !== "all" &&
          getFilteredSingle().map((team, index) => (
            <TeamRow key={team.name} team={team} displayRank={team.displayRank} index={index} />
          ))
        }

        {loaded && teams.length > 0 && gamesPlayedTotal > 0 && showConferenceGroups &&
          (() => {
            let globalIndex = 0;
            return getConferenceGroups().map(group => {
              const el = <DivisionGroup key={group.label} label={group.label} teams={group.teams} startIndex={globalIndex} />;
              globalIndex += group.teams.length;
              return el;
            });
          })()
        }

        {loaded && teams.length > 0 && gamesPlayedTotal > 0 && filter === "conference" && conferenceFilter !== "all" &&
          getFilteredSingle().map((team, index) => (
            <TeamRow key={team.name} team={team} displayRank={team.displayRank} index={index} />
          ))
        }
      </div>
    </div>
  );
};

export default Standings;
