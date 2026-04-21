// @ts-nocheck
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

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

const mockStandings: Team[] = [
  { rank: 1,  name: "Ice Dragons",      record: "12-3-1", points: 847, streak: "W3", division: "Atlantic",     conference: "Eastern", pointsFor: 847, pointsAgainst: 702, last5: ["W","W","W","L","W"], clinched: ["presidents","conference","division","playoff"] },
  { rank: 2,  name: "Team Frostbite",   record: "11-4-1", points: 812, streak: "W5", isUser: true, division: "Atlantic",     conference: "Eastern", pointsFor: 812, pointsAgainst: 718, last5: ["W","W","W","W","W"], clinched: ["playoff"] },
  { rank: 3,  name: "Blazers",          record: "10-5-1", points: 789, streak: "L1", division: "Metropolitan", conference: "Eastern", pointsFor: 789, pointsAgainst: 745, last5: ["L","W","W","L","W"], clinched: ["division","playoff"] },
  { rank: 4,  name: "Thunder",          record: "9-6-1",  points: 754, streak: "W2", division: "Central",      conference: "Western", pointsFor: 754, pointsAgainst: 730, last5: ["W","W","L","L","W"], clinched: ["conference","division","playoff"] },
  { rank: 5,  name: "Wolverines",       record: "8-7-1",  points: 721, streak: "L2", division: "Pacific",      conference: "Western", pointsFor: 721, pointsAgainst: 739, last5: ["L","L","W","W","L"], clinched: ["division","playoff"] },
  { rank: 6,  name: "Phoenix",          record: "7-8-1",  points: 698, streak: "W1", division: "Metropolitan", conference: "Eastern", pointsFor: 698, pointsAgainst: 756, last5: ["W","L","L","W","L"], clinched: ["playoff"] },
  { rank: 7,  name: "Storm Chasers",    record: "7-9-0",  points: 672, streak: "L3", division: "Atlantic",     conference: "Eastern", pointsFor: 672, pointsAgainst: 781, last5: ["L","L","L","W","W"] },
  { rank: 8,  name: "Vipers",           record: "6-9-1",  points: 645, streak: "W1", division: "Central",      conference: "Western", pointsFor: 645, pointsAgainst: 790, last5: ["W","L","L","L","W"] },
  { rank: 9,  name: "Avalanche",        record: "5-10-1", points: 598, streak: "L1", division: "Pacific",      conference: "Western", pointsFor: 598, pointsAgainst: 812, last5: ["L","W","L","L","L"], clinched: ["eliminated"] },
  { rank: 10, name: "Knights",          record: "4-11-1", points: 542, streak: "L4", division: "Central",      conference: "Western", pointsFor: 542, pointsAgainst: 845, last5: ["L","L","L","L","W"], clinched: ["eliminated"] },
];

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

  const getLeagueStandings = () =>
    [...mockStandings].map((team, index) => ({ ...team, displayRank: index + 1 }));

  // Alphabetically ordered divisions
  const getDivisionGroups = () => {
    const divisions = ["Atlantic", "Central", "Metropolitan", "Pacific"] as const;
    return divisions.map(div => ({
      label: `${div} Division`,
      teams: mockStandings
        .filter(t => t.division === div)
        .map((t, i) => ({ ...t, displayRank: i + 1 })),
    }));
  };

  // Alphabetically ordered conferences
  const getConferenceGroups = () => {
    const conferences = ["Eastern", "Western"] as const;
    return conferences.map(conf => ({
      label: `${conf} Conference`,
      teams: mockStandings
        .filter(t => t.conference === conf)
        .sort((a, b) => b.points - a.points)
        .map((t, i) => ({ ...t, displayRank: i + 1 })),
    }));
  };

  const getFilteredSingle = () => {
    let filtered = [...mockStandings];
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
                <SelectItem value="Atlantic">Atlantic</SelectItem>
                <SelectItem value="Central">Central</SelectItem>
                <SelectItem value="Metropolitan">Metropolitan</SelectItem>
                <SelectItem value="Pacific">Pacific</SelectItem>
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
                <SelectItem value="Eastern">Eastern</SelectItem>
                <SelectItem value="Western">Western</SelectItem>
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
      <div className="divide-y divide-border/50">
        {filter === "league" &&
          getLeagueStandings().map((team, index) => (
            <TeamRow key={team.name} team={team} displayRank={team.displayRank} index={index} />
          ))
        }

        {showDivisionGroups &&
          (() => {
            let globalIndex = 0;
            return getDivisionGroups().map(group => {
              const el = <DivisionGroup key={group.label} label={group.label} teams={group.teams} startIndex={globalIndex} />;
              globalIndex += group.teams.length;
              return el;
            });
          })()
        }

        {filter === "division" && divisionFilter !== "all" &&
          getFilteredSingle().map((team, index) => (
            <TeamRow key={team.name} team={team} displayRank={team.displayRank} index={index} />
          ))
        }

        {showConferenceGroups &&
          (() => {
            let globalIndex = 0;
            return getConferenceGroups().map(group => {
              const el = <DivisionGroup key={group.label} label={group.label} teams={group.teams} startIndex={globalIndex} />;
              globalIndex += group.teams.length;
              return el;
            });
          })()
        }

        {filter === "conference" && conferenceFilter !== "all" &&
          getFilteredSingle().map((team, index) => (
            <TeamRow key={team.name} team={team} displayRank={team.displayRank} index={index} />
          ))
        }
      </div>
    </div>
  );
};

export default Standings;
