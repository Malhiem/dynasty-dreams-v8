// @ts-nocheck
import { useState, useCallback, useEffect, useMemo, useRef } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useActiveLeague } from "@/hooks/use-active-league";
import { useSeasonStreaks, streakChip } from "@/hooks/use-season-streaks";
import api from "@/lib/api";
import { AppLayout } from "@/components/layout/AppLayout";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Checkbox } from "@/components/ui/checkbox";
import { Button } from "@/components/ui/button";
import { Settings, ChevronUp, ChevronDown, Minus, Crown } from "lucide-react";
import TeamLogo from "@/lovable/components/TeamLogo";
import { usePullToRefresh } from "@/hooks/use-pull-to-refresh";
import PullToRefreshIndicator from "@/components/PullToRefreshIndicator";
// Iter 232b — Live "Last updated · 14s ago" pill that flashes green
// after a successful pull-to-refresh.
import LastUpdatedBadge from "@/components/LastUpdatedBadge";
// Iter 207 — Report this team's owner
import ReportUserButton from "@/components/ReportUserButton";
import { PlayoffBracketView } from "@/lovable/pages/PlayoffBracket";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";

type ClinchStatus = "presidents" | "conference" | "division" | "playoff" | "eliminated";

interface StandingsTeam {
  rank: number;
  prevRank: number;
  name: string;
  teamId?: string;
  logo_url?: string | null;
  logo_abbr?: string;
  // Iter 229k — Optional preset theme color (hex). Drives the
  // <TeamLogo> tint when there's no uploaded logo.
  theme_color?: string | null;
  wins: number;
  losses: number;
  ties: number;
  points: number;
  pointsFor: number;
  pointsAgainst: number;
  streak: string;
  last5: ("W" | "L" | "T")[];
  division: string;
  conference: string;
  divWins: number;
  divLosses: number;
  confWins: number;
  confLosses: number;
  gb?: number;
  gbDivision?: number;
  isUser?: boolean;
  clinched?: ClinchStatus[];
  capRemaining?: number | null;
  capUsed?: number | null;
  capLimit?: number | null;
  projectedSeed?: number;
}

const mockTeams: StandingsTeam[] = [
  { rank: 1,  prevRank: 1,  name: "Ice Dragons",     wins: 12, losses: 3,  ties: 1, points: 847, pointsFor: 847, pointsAgainst: 702, streak: "W3", last5: ["W","W","W","L","W"], division: "Atlantic",     conference: "Eastern", divWins: 5, divLosses: 1, confWins: 8, confLosses: 2, projectedSeed: 1,  clinched: ["presidents","conference","division","playoff"] },
  { rank: 2,  prevRank: 3,  name: "Team Frostbite",  wins: 11, losses: 4,  ties: 1, points: 812, pointsFor: 812, pointsAgainst: 718, streak: "W5", last5: ["W","W","W","W","W"], division: "Atlantic",     conference: "Eastern", divWins: 4, divLosses: 2, confWins: 7, confLosses: 3, isUser: true, projectedSeed: 2, clinched: ["playoff"] },
  { rank: 3,  prevRank: 2,  name: "Blazers",         wins: 10, losses: 5,  ties: 1, points: 789, pointsFor: 789, pointsAgainst: 745, streak: "L1", last5: ["L","W","W","L","W"], division: "Metropolitan", conference: "Eastern", divWins: 4, divLosses: 1, confWins: 7, confLosses: 3, projectedSeed: 3,  clinched: ["division","playoff"] },
  { rank: 4,  prevRank: 4,  name: "Thunder",         wins: 9,  losses: 6,  ties: 1, points: 754, pointsFor: 754, pointsAgainst: 730, streak: "W2", last5: ["W","W","L","L","W"], division: "Central",      conference: "Western", divWins: 4, divLosses: 2, confWins: 6, confLosses: 4, projectedSeed: 4,  clinched: ["conference","division","playoff"] },
  { rank: 5,  prevRank: 7,  name: "Wolverines",      wins: 8,  losses: 7,  ties: 1, points: 721, pointsFor: 721, pointsAgainst: 739, streak: "L2", last5: ["L","L","W","W","L"], division: "Pacific",      conference: "Western", divWins: 3, divLosses: 2, confWins: 5, confLosses: 5, projectedSeed: 5,  clinched: ["division","playoff"] },
  { rank: 6,  prevRank: 5,  name: "Phoenix",         wins: 7,  losses: 8,  ties: 1, points: 698, pointsFor: 698, pointsAgainst: 756, streak: "W1", last5: ["W","L","L","W","L"], division: "Metropolitan", conference: "Eastern", divWins: 3, divLosses: 3, confWins: 5, confLosses: 5, projectedSeed: 6,  clinched: ["playoff"] },
  { rank: 7,  prevRank: 6,  name: "Storm Chasers",   wins: 7,  losses: 9,  ties: 0, points: 672, pointsFor: 672, pointsAgainst: 781, streak: "L3", last5: ["L","L","L","W","W"], division: "Atlantic",     conference: "Eastern", divWins: 2, divLosses: 4, confWins: 4, confLosses: 6, projectedSeed: 7 },
  { rank: 8,  prevRank: 8,  name: "Vipers",          wins: 6,  losses: 9,  ties: 1, points: 645, pointsFor: 645, pointsAgainst: 790, streak: "W1", last5: ["W","L","L","L","W"], division: "Central",      conference: "Western", divWins: 2, divLosses: 3, confWins: 4, confLosses: 6, projectedSeed: 8 },
  { rank: 9,  prevRank: 10, name: "Avalanche",       wins: 5,  losses: 10, ties: 1, points: 598, pointsFor: 598, pointsAgainst: 812, streak: "L1", last5: ["L","W","L","L","L"], division: "Pacific",      conference: "Western", divWins: 2, divLosses: 4, confWins: 3, confLosses: 7, projectedSeed: 9,  clinched: ["eliminated"] },
  { rank: 10, prevRank: 9,  name: "Knights",         wins: 4,  losses: 11, ties: 1, points: 542, pointsFor: 542, pointsAgainst: 845, streak: "L4", last5: ["L","L","L","L","W"], division: "Central",      conference: "Western", divWins: 1, divLosses: 5, confWins: 2, confLosses: 8, projectedSeed: 10, clinched: ["eliminated"] },
];

// Mock weekly rank data for the race chart (week 1–16)
const TEAM_COLORS: Record<string, string> = {
  "Ice Dragons":      "hsl(192 82% 55%)",
  "Team Frostbite":   "hsl(45 93% 58%)",
  "Blazers":          "hsl(262 80% 65%)",
  "Thunder":          "hsl(142 71% 45%)",
  "Wolverines":       "hsl(0 72% 51%)",
  "Phoenix":          "hsl(30 90% 55%)",
  "Storm Chasers":    "hsl(200 80% 55%)",
  "Vipers":           "hsl(300 65% 60%)",
  "Avalanche":        "hsl(165 65% 45%)",
  "Knights":          "hsl(350 75% 55%)",
};

// Simulated rank-over-weeks data
function generateRaceData() {
  const weeklyRanks: Record<string, number[]> = {
    "Ice Dragons":      [3,2,2,1,1,1,2,1,1,1,1,1,1,1,1,1],
    "Team Frostbite":   [1,1,1,2,2,2,1,2,2,2,2,2,2,2,2,2],
    "Blazers":          [2,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3],
    "Thunder":          [4,4,4,4,4,5,5,4,4,4,4,4,4,4,4,4],
    "Wolverines":       [5,5,5,5,5,4,4,5,5,5,5,5,5,5,5,5],
    "Phoenix":          [7,7,6,6,6,6,6,6,6,6,6,6,6,6,6,6],
    "Storm Chasers":    [6,6,7,7,7,7,7,7,7,7,7,7,7,7,7,7],
    "Vipers":           [9,8,8,8,8,8,8,8,8,8,8,8,8,8,8,8],
    "Avalanche":        [8,9,9,9,9,9,9,9,9,9,9,9,9,9,9,9],
    "Knights":          [10,10,10,10,10,10,10,10,10,10,10,10,10,10,10,10],
  };
  return Array.from({ length: 16 }, (_, w) => {
    const row: Record<string, number | string> = { week: `Wk ${w + 1}` };
    Object.keys(weeklyRanks).forEach(team => {
      row[team] = weeklyRanks[team][w];
    });
    return row;
  });
}

const raceData = generateRaceData();

type ViewType = "league" | "division" | "conference";

interface ColumnConfig {
  wins: boolean;
  losses: boolean;
  ties: boolean;
  last5: boolean;
  pf: boolean;
  pa: boolean;
  diff: boolean;
  gb: boolean;
  divRecord: boolean;
  confRecord: boolean;
  streak: boolean;
  capRemaining: boolean;
}

const DEFAULT_COLUMNS: ColumnConfig = {
  wins: true, losses: true, ties: true, last5: true,
  pf: true, pa: true, diff: true, gb: true, divRecord: true, confRecord: true, streak: true,
  capRemaining: true,
};

const Sparkline = ({ results }: { results: ("W" | "L" | "T" | null)[] }) => {
  // Always render 5 dots; grey-out slots where no game has been played yet.
  const padded: ("W" | "L" | "T" | null)[] = [...results];
  while (padded.length < 5) padded.push(null);
  return (
    <div className="flex items-center gap-0.5">
      {padded.slice(0, 5).map((r, i) => (
        <div
          key={i}
          className={`w-2.5 h-2.5 rounded-full ${
            r === "W"
              ? "bg-success"
              : r === "L"
                ? "bg-destructive"
                : r === "T"
                  ? "bg-muted-foreground"
                  : "bg-muted/30 border border-muted"
          }`}
          title={r || "No game"}
          data-testid={`sparkline-dot-${i}-${r ?? "none"}`}
        />
      ))}
    </div>
  );
};

// ─── Customization Cog Modal ──────────────────────────────────────────────────
const CustomizationModal = ({
  open, onClose, columns, onColumnsChange,
}: {
  open: boolean;
  onClose: () => void;
  columns: ColumnConfig;
  onColumnsChange: (c: ColumnConfig) => void;
}) => {
  const [local, setLocal] = useState<ColumnConfig>(columns);
  const toggle = (key: keyof ColumnConfig) => setLocal(prev => ({ ...prev, [key]: !prev[key] }));

  const columnDefs: { key: keyof ColumnConfig; label: string }[] = [
    { key: "wins", label: "Wins (W)" },
    { key: "losses", label: "Losses (L)" },
    { key: "ties", label: "Ties (T)" },
    { key: "last5", label: "Last 5 Sparkline" },
    { key: "pf", label: "Points For (PF)" },
    { key: "pa", label: "Points Against (PA)" },
    { key: "diff", label: "Differential (+/-)" },
    { key: "divRecord", label: "Division Record" },
    { key: "confRecord", label: "Conference Record" },
    { key: "streak", label: "Streak" },
    { key: "capRemaining", label: "Cap Remaining" },
  ];

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>Customize Standings View</DialogTitle>
        </DialogHeader>
        <p className="text-sm text-muted-foreground -mt-2">Toggle which columns appear in the standings table.</p>
        <div className="space-y-3 pt-1">
          {columnDefs.map(({ key, label }) => (
            <div key={key} className="flex items-center gap-3">
              <Checkbox
                id={key}
                checked={local[key]}
                onCheckedChange={() => toggle(key)}
              />
              <label htmlFor={key} className="text-sm cursor-pointer select-none">{label}</label>
            </div>
          ))}
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <Button variant="outline" size="sm" onClick={onClose}>Cancel</Button>
          <Button size="sm" onClick={() => { onColumnsChange(local); onClose(); }}>Apply</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
};

// ─── Clinch Badges & Legend ───────────────────────────────────────────────────
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
    <span
      title={cfg.title}
      className={`text-[10px] font-bold px-1.5 py-0.5 rounded cursor-default ${cfg.className}`}
    >
      {cfg.label}
    </span>
  );
};

const ClinchLegend = () => (
  <div className="flex flex-wrap gap-x-5 gap-y-2 text-xs text-muted-foreground px-1">
    {CLINCH_ORDER.map(s => {
      const cfg = CLINCH_CONFIG[s];
      return (
        <div key={s} className="flex items-center gap-1.5">
          <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${cfg.className}`}>{cfg.label}</span>
          <span>{cfg.title.split(" – ")[0].replace("Clinched ", "").replace("Eliminated from ", "Elim. from ")}</span>
        </div>
      );
    })}
  </div>
);

// ─── Standings Table ──────────────────────────────────────────────────────────
const StandingsTable = ({
  teams,
  columns,
  streaks,
}: {
  teams: (StandingsTeam & { displayRank: number })[];
  columns: ColumnConfig;
  streaks?: Record<string, any>;
}) => {
  const navigate = useNavigate();
  return (
  <div className="stat-card p-0 overflow-hidden">
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border bg-secondary/30 text-xs font-medium text-muted-foreground">
            <th className="w-8 py-2.5 text-center">#</th>
            <th className="py-2.5 text-left pl-2">Team</th>
            {columns.wins && <th className="w-10 py-2.5 text-center">W</th>}
            {columns.losses && <th className="w-10 py-2.5 text-center">L</th>}
            {columns.ties && <th className="w-10 py-2.5 text-center">T</th>}
            {columns.last5 && <th className="w-14 py-2.5 text-center">Last 5</th>}
            {columns.pf && <th className="w-14 py-2.5 text-right">PF</th>}
            {columns.pa && <th className="w-14 py-2.5 text-right">PA</th>}
            {columns.diff && <th className="w-14 py-2.5 text-right">+/-</th>}
            {columns.gb && <th className="w-12 py-2.5 text-right" data-testid="standings-col-gb">GB</th>}
            {columns.divRecord && <th className="w-16 py-2.5 text-center">Div</th>}
            {columns.confRecord && <th className="w-16 py-2.5 text-center">Conf</th>}
            {columns.streak && <th className="w-14 py-2.5 text-right pr-3">Streak</th>}
            {columns.capRemaining && <th className="w-20 py-2.5 text-right pr-3" data-testid="standings-col-cap-remaining">Cap Left</th>}
          </tr>
        </thead>
        <tbody className="divide-y divide-border/50">
          {teams.map((team) => {
            const diff = team.pointsFor - team.pointsAgainst;
            return (
              <tr
                key={team.name}
                className={`hover:bg-secondary/20 transition-colors ${
                  team.isUser ? "bg-primary/5 border-l-2 border-l-primary" : ""
                }`}
              >
                <td className="py-2.5 text-center">
                  <div className="flex items-center justify-center gap-0.5" data-testid={`standings-movement-${team.teamId || team.name}`}>
                    <span className={`font-bold ${
                      team.displayRank === 1 ? "text-accent" :
                      team.displayRank <= 3 ? "text-orange-400" : "text-muted-foreground"
                    }`}>{team.displayRank}</span>
                    {(() => {
                      const move = team.prevRank - team.displayRank;
                      if (move > 0) return (
                        <span className="flex items-center text-success" title={`Up ${move} from last week`}>
                          <ChevronUp className="h-3.5 w-3.5" />
                          <span className="text-[10px] font-semibold -ml-0.5">{move}</span>
                        </span>
                      );
                      if (move < 0) return (
                        <span className="flex items-center text-destructive" title={`Down ${Math.abs(move)} from last week`}>
                          <ChevronDown className="h-3.5 w-3.5" />
                          <span className="text-[10px] font-semibold -ml-0.5">{Math.abs(move)}</span>
                        </span>
                      );
                      return <Minus className="h-3 w-3 text-muted-foreground/40" />;
                    })()}
                  </div>
                </td>
                <td className="py-2.5 pl-2">
                  <div className="flex items-center gap-2 flex-wrap">
                    <TeamLogo logo={team.logo_url} name={team.name} abbr={team.logo_abbr} themeColor={team.theme_color} size="xs" />
                    <span
                      className={`font-medium cursor-pointer hover:underline ${team.isUser ? "text-primary" : "text-foreground"}`}
                      onClick={() => {
                        const slug = team.name.toLowerCase().replace(/\s+/g, "-");
                        navigate(team.teamId ? `/roster?team_id=${team.teamId}` : `/team?team=${slug}`);
                      }}
                    >
                      {team.name}
                      {team.isUser && <span className="ml-1.5 text-xs bg-primary/20 text-primary px-1.5 py-0.5 rounded-full">You</span>}
                    </span>
                    {team.teamId && (
                      <Link
                        to={`/trophy-room/team/${team.teamId}`}
                        title="View Trophy Room"
                        data-testid={`standings-trophy-link-${team.teamId}`}
                        className="text-amber-400/70 hover:text-amber-300 inline-flex"
                      >
                        <Crown className="h-3.5 w-3.5" />
                      </Link>
                    )}
                    {team.teamId && (() => {
                      const chip = streakChip(streaks?.[team.teamId]?.active);
                      if (!chip) return null;
                      return (
                        <span
                          data-testid={`standings-streak-chip-${team.teamId}`}
                          title={`${chip.count} consecutive ${chip.label === "Hot" ? "winning" : "losing"} seasons`}
                          className={`inline-flex items-center gap-0.5 text-[10px] font-semibold uppercase tracking-wider px-1.5 py-0.5 rounded-full border ${
                            chip.tone === "hot"
                              ? "bg-orange-500/20 text-orange-300 border-orange-400/40"
                              : "bg-sky-500/20 text-sky-200 border-sky-400/40"
                          }`}
                        >
                          {chip.emoji} {chip.label} {chip.count}
                        </span>
                      );
                    })()}
                    <ClinchBadges statuses={team.clinched} />
                  </div>
                </td>
                {columns.wins && <td className="py-2.5 text-center font-medium">{team.wins}</td>}
                {columns.losses && <td className="py-2.5 text-center text-muted-foreground">{team.losses}</td>}
                {columns.ties && <td className="py-2.5 text-center text-muted-foreground">{team.ties}</td>}
                {columns.last5 && <td className="py-2.5"><div className="flex justify-center"><Sparkline results={team.last5} /></div></td>}
                {columns.pf && <td className="py-2.5 text-right font-medium">{team.pointsFor}</td>}
                {columns.pa && <td className="py-2.5 text-right text-muted-foreground">{team.pointsAgainst}</td>}
                {columns.diff && (
                  <td className={`py-2.5 text-right font-medium ${diff > 0 ? "text-success" : diff < 0 ? "text-destructive" : "text-muted-foreground"}`}>
                    {diff > 0 ? "+" : ""}{diff}
                  </td>
                )}
                {columns.gb && (
                  <td className="py-2.5 text-right text-xs font-medium" data-testid={`standings-gb-${team.teamId || team.name}`}>
                    {team.displayRank === 1 ? <span className="text-muted-foreground/60">—</span> : <span className="text-muted-foreground">{(team.gb ?? 0).toFixed(1)}</span>}
                  </td>
                )}
                {columns.divRecord && <td className="py-2.5 text-center text-xs">{team.divWins}-{team.divLosses}</td>}
                {columns.confRecord && <td className="py-2.5 text-center text-xs">{team.confWins}-{team.confLosses}</td>}
                {columns.streak && (
                  <td className="py-2.5 pr-3">
                    <div className="flex justify-end">
                      <span className={`text-xs font-medium px-1.5 py-0.5 rounded-full ${
                        team.streak.startsWith("W") ? "bg-success/20 text-success" : "bg-destructive/20 text-destructive"
                      }`}>{team.streak}</span>
                    </div>
                  </td>
                )}
                {columns.capRemaining && (
                  <td className="py-2.5 pr-3 text-right" data-testid={`standings-cap-remaining-${team.teamId || team.name}`}>
                    {team.capLimit ? (
                      <span
                        className={`text-xs font-semibold ${
                          (team.capRemaining ?? 0) < 0
                            ? "text-destructive"
                            : (team.capRemaining ?? 0) < 2_000_000
                              ? "text-amber-400"
                              : "text-success"
                        }`}
                        title={`Used $${((team.capUsed || 0) / 1_000_000).toFixed(2)}M of $${(team.capLimit / 1_000_000).toFixed(1)}M`}
                      >
                        {(team.capRemaining ?? 0) < 0 ? "−" : ""}${Math.abs((team.capRemaining ?? 0) / 1_000_000).toFixed(1)}M
                      </span>
                    ) : (
                      <span className="text-xs text-muted-foreground/40">—</span>
                    )}
                  </td>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  </div>
  );
};

// ─── Race Chart ───────────────────────────────────────────────────────────────
const RaceChart = ({ teams }: { teams: StandingsTeam[] }) => {
  const palette = [
    "hsl(192 82% 55%)", "hsl(45 93% 58%)", "hsl(262 80% 65%)", "hsl(142 71% 45%)",
    "hsl(0 72% 51%)", "hsl(30 90% 55%)", "hsl(200 80% 55%)", "hsl(300 65% 60%)",
    "hsl(165 65% 45%)", "hsl(350 75% 55%)", "hsl(220 70% 60%)", "hsl(80 65% 50%)",
  ];
  const teamNames = teams.map(t => t.name);
  const colorFor = useMemo(() => {
    const m: Record<string, string> = {};
    teamNames.forEach((n, i) => { m[n] = palette[i % palette.length]; });
    return m;
  }, [teamNames.join(",")]);
  // Synthesize weekly rank movement from current rank +/- small wiggle.
  const raceData = useMemo(() => {
    return Array.from({ length: 16 }, (_, w) => {
      const row: Record<string, number | string> = { week: `Wk ${w + 1}` };
      teams.forEach((t, idx) => {
        const wiggle = ((w + idx) % 3) - 1;
        row[t.name] = Math.max(1, Math.min(teams.length, (t.rank || idx + 1) + wiggle));
      });
      return row;
    });
  }, [teams]);
  const [visibleTeams, setVisibleTeams] = useState<Set<string>>(new Set(teamNames));
  const [hoveredTeam, setHoveredTeam] = useState<string | null>(null);

  useEffect(() => {
    setVisibleTeams(new Set(teamNames));
  }, [teamNames.join(",")]);

  const toggleTeam = useCallback((name: string) => {
    setVisibleTeams(prev => {
      const next = new Set(prev);
      if (next.has(name)) { if (next.size > 1) next.delete(name); }
      else next.add(name);
      return next;
    });
  }, []);

  const CustomTooltip = ({ active, payload, label }: any) => {
    if (!active || !payload?.length) return null;
    const sorted = [...payload].sort((a, b) => a.value - b.value);
    return (
      <div className="bg-card border border-border rounded-lg p-3 shadow-lg text-xs space-y-1">
        <p className="font-semibold text-foreground mb-1">{label}</p>
        {sorted.map((entry: any) => (
          <div key={entry.dataKey} className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: entry.color }} />
            <span className="text-muted-foreground">{entry.dataKey}</span>
            <span className="font-medium text-foreground ml-auto pl-3">#{entry.value}</span>
          </div>
        ))}
      </div>
    );
  };

  return (
    <div className="stat-card p-5 space-y-4">
      <div>
        <h3 className="font-semibold text-base">Standings Race</h3>
        <p className="text-xs text-muted-foreground">Weekly rank movement — hover a line to highlight, click legend to filter</p>
      </div>

      {/* Team filter pills */}
      <div className="flex flex-wrap gap-1.5">
        {teamNames.map(name => {
          const active = visibleTeams.has(name);
          return (
            <button
              key={name}
              onClick={() => toggleTeam(name)}
              className={`text-xs px-2.5 py-1 rounded-full border transition-all duration-200 ${
                active
                  ? "border-transparent text-background font-medium"
                  : "border-border text-muted-foreground bg-transparent"
              }`}
              style={active ? { background: colorFor[name] } : {}}
            >
              {name}
            </button>
          );
        })}
      </div>

      <ResponsiveContainer width="100%" height={360}>
        <LineChart data={raceData} margin={{ top: 8, right: 20, left: -20, bottom: 8 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" opacity={0.4} />
          <XAxis
            dataKey="week"
            tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 11 }}
            axisLine={{ stroke: "hsl(var(--border))" }}
            tickLine={false}
          />
          <YAxis
            reversed
            domain={[1, 10]}
            ticks={[1,2,3,4,5,6,7,8,9,10]}
            tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 11 }}
            axisLine={{ stroke: "hsl(var(--border))" }}
            tickLine={false}
            tickFormatter={(v) => `#${v}`}
          />
          <Tooltip content={<CustomTooltip />} />
          {teamNames.filter(name => visibleTeams.has(name)).map(name => {
            const isHovered = hoveredTeam === name;
            const anyHovered = hoveredTeam !== null;
            const opacity = anyHovered ? (isHovered ? 1 : 0.12) : 1;
            const strokeWidth = isHovered ? 3 : 1.8;
            return (
              <Line
                key={name}
                type="monotone"
                dataKey={name}
                stroke={colorFor[name]}
                strokeWidth={strokeWidth}
                strokeOpacity={opacity}
                dot={false}
                activeDot={{
                  r: 5,
                  fill: colorFor[name],
                  stroke: "hsl(var(--background))",
                  strokeWidth: 2,
                }}
                onMouseEnter={() => setHoveredTeam(name)}
                onMouseLeave={() => setHoveredTeam(null)}
              />
            );
          })}
        </LineChart>
      </ResponsiveContainer>

      <div className="flex flex-wrap gap-x-4 gap-y-1.5">
        {teamNames.filter(n => visibleTeams.has(n)).map(name => (
          <div
            key={name}
            className="flex items-center gap-1.5 cursor-pointer group"
            onMouseEnter={() => setHoveredTeam(name)}
            onMouseLeave={() => setHoveredTeam(null)}
          >
            <span className="w-3 h-0.5 rounded-full flex-shrink-0" style={{ background: colorFor[name] }} />
            <span className={`text-xs transition-colors ${hoveredTeam === name ? "text-foreground font-medium" : "text-muted-foreground"}`}>
              {name}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
};

// ─── Playoff Bracket ──────────────────────────────────────────────────────────
const PlayoffBracket = ({ teams, showProjections }: { teams: StandingsTeam[]; showProjections: boolean }) => {
  const navigate = useNavigate();
  const playoffTeams = showProjections ? teams.slice(0, 6) : [];
  const consolationTeams = showProjections ? teams.slice(6) : [];

  if (!showProjections) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="stat-card p-6 text-center">
          <h4 className="font-semibold mb-2">Playoffs</h4>
          <p className="text-sm text-muted-foreground">Standings have not been finalized. No teams have clinched a playoff position yet.</p>
        </div>
        <div className="stat-card p-6 text-center">
          <h4 className="font-semibold mb-2">Consolation Playoffs</h4>
          <p className="text-sm text-muted-foreground">Standings have not been finalized. Consolation bracket will be determined at end of regular season.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
      <div className="stat-card p-4">
        <h4 className="font-semibold mb-3 flex items-center gap-2">
          <span className="h-2 w-2 rounded-full bg-success" />
          Projected Playoffs
        </h4>
        <div className="space-y-2">
          {playoffTeams.map((team, i) => (
            <div key={team.name} className={`flex items-center justify-between p-2.5 rounded-lg border border-border/50 ${team.isUser ? "bg-primary/5 border-primary/30" : "bg-secondary/20"}`}>
              <div className="flex items-center gap-2">
                <span className="w-5 text-center text-xs font-bold text-muted-foreground">{i + 1}</span>
                <span
                  className={`text-sm font-medium cursor-pointer hover:underline ${team.isUser ? "text-primary" : "text-foreground"}`}
                  onClick={() => navigate(`/team?team=${team.name.toLowerCase().replace(/\s+/g, "-")}`)}
                >
                  {team.name}
                </span>
                {i < 2 && <span className="text-[10px] bg-accent/20 text-accent px-1.5 py-0.5 rounded">BYE</span>}
              </div>
              <span className="text-xs text-muted-foreground">{team.wins}-{team.losses}-{team.ties}</span>
            </div>
          ))}
        </div>
      </div>
      <div className="stat-card p-4">
        <h4 className="font-semibold mb-3 flex items-center gap-2">
          <span className="h-2 w-2 rounded-full bg-muted-foreground" />
          Projected Consolation
        </h4>
        <div className="space-y-2">
          {consolationTeams.map((team, i) => (
            <div key={team.name} className={`flex items-center justify-between p-2.5 rounded-lg border border-border/50 ${team.isUser ? "bg-primary/5 border-primary/30" : "bg-secondary/20"}`}>
              <div className="flex items-center gap-2">
                <span className="w-5 text-center text-xs font-bold text-muted-foreground">{i + 7}</span>
                <span
                  className={`text-sm font-medium cursor-pointer hover:underline ${team.isUser ? "text-primary" : "text-foreground"}`}
                  onClick={() => navigate(`/team?team=${team.name.toLowerCase().replace(/\s+/g, "-")}`)}
                >
                  {team.name}
                </span>
              </div>
              <span className="text-xs text-muted-foreground">{team.wins}-{team.losses}-{team.ties}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

// ─── Page ─────────────────────────────────────────────────────────────────────
const StandingsPage = () => {
  const navigate = useNavigate();
  const { league, leagueTeams, myTeam, myLeagues, leagueId, switchLeague } = useActiveLeague();
  const { streaks } = useSeasonStreaks(leagueId);
  const [view, setView] = useState<ViewType>("league");
  const viewExplicitlyChanged = useRef(false);
  const [divisionFilter, setDivisionFilter] = useState<string>("all");
  const [conferenceFilter, setConferenceFilter] = useState<string>("all");
  const [showProjections, setShowProjections] = useState(false);
  const [cogOpen, setCogOpen] = useState(false);
  const [columns, setColumns] = useState<ColumnConfig>(DEFAULT_COLUMNS);

  // ── Backend-enriched standings (real last_5 + cap remaining) ───
  // We hit /api/leagues/{id}/standings which returns the actual W/L/T
  // sequence from completed matchups + live cap_remaining for each team.
  const [backendStandings, setBackendStandings] = useState<Record<string, any>>({});
  const [standingsMeta, setStandingsMeta] = useState<{ has_divisions: boolean; has_conferences: boolean; divisions: string[]; conferences: string[]; }>({ has_divisions: false, has_conferences: false, divisions: [], conferences: [] });
  // Iter 231au — Pull-to-refresh: refactored in iter 232a so the gesture
  // (a) awaits the actual /standings network fetch, and (b) bypasses the
  // service-worker's stale-while-revalidate cache via `?nocache=1`. The
  // hook now keeps the spinner visible until `onRefresh` resolves.
  // Iter 232b — Track `lastUpdatedAt` so the page can render a
  // "Last updated · 14s ago" badge next to the title that flashes
  // green after a successful refresh.
  const [lastUpdatedAt, setLastUpdatedAt] = useState<number | null>(null);
  const fetchStandings = useCallback(async (force = false): Promise<void> => {
    if (!leagueId) return;
    try {
      const path = `/leagues/${leagueId}/standings${force ? "?nocache=1" : ""}`;
      const { data } = await api.get(path);
      const rows = Array.isArray(data) ? data : (data?.standings || []);
      const map: Record<string, any> = {};
      rows.forEach((row: any) => { map[row.team_id] = row; });
      setBackendStandings(map);
      setStandingsMeta({
        has_divisions: !!data?.has_divisions,
        has_conferences: !!data?.has_conferences,
        divisions: data?.divisions || [],
        conferences: data?.conferences || [],
      });
      // Stamp the freshness timestamp — drives the LastUpdatedBadge.
      setLastUpdatedAt(Date.now());
      // Auto-select division view when the league has REAL divisions
      // configured AND at least half the teams are assigned to one of
      // them. Otherwise leave the user on League view so they don't
      // see a near-empty divisional bracket (iter 231o — TFHL had 1/24
      // teams in a division which auto-switched to division view and
      // hid the other 23 teams behind an unassigned filter).
      if (data?.has_divisions && !viewExplicitlyChanged.current) {
        const assigned = (data.standings || []).filter(
          (t: { division: string | null }) => !!t.division,
        ).length;
        const total = (data.standings || []).length || 1;
        if (assigned / total >= 0.5) {
          setView("division");
          setDivisionFilter("all");
        }
      }
    } catch {
      /* swallow — UI keeps last-known-good standings on transient failure */
    }
  }, [leagueId]);
  const ptr = usePullToRefresh({
    onRefresh: async () => { await fetchStandings(true); },
  });
  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (cancelled) return;
      await fetchStandings(false);
    })();
    return () => { cancelled = true; };
  }, [fetchStandings]);

  // Build real-data teams list shaped like the Lovable mock so the UI below works as-is.
  const liveTeams: StandingsTeam[] = useMemo(() => {
    // Iter 232N.68 — Previously returned `mockTeams` (Ice Dragons,
    // Team Frostbite…) whenever leagueTeams was empty. That flashed
    // fake standings during initial load AND made empty sandbox
    // leagues look like they had data. Return `[]` so the UI shows
    // its natural empty state instead.
    if (!leagueTeams || leagueTeams.length === 0) return [];
    const ranked = [...leagueTeams]
      .map(t => ({ ...t, _total: (t.points_for || 0) + (t.live_points || 0) }))
      .sort((a, b) => b._total - a._total);
    // Iter 231o — Stop lying about team divisions/conferences. Previous
    // builds used `fallbackDivisions[idx % 4]` which made teams that
    // had NO real division silently get assigned to fake NHL-style
    // buckets — so a 1-division league with 23 unassigned teams
    // dropped 23 teams in division-view filtering. Now we surface
    // "Unassigned" so the user can see (and act on) the gap.
    const UNASSIGNED = "Unassigned";
    return ranked.map((t, idx) => {
      const gp = (t.wins || 0) + (t.losses || 0) + (t.ties || 0);
      const backend = backendStandings[t.id];
      const realLast5 = (backend?.last_5 || []) as ("W" | "L" | "T")[];
      const last5: ("W" | "L" | "T")[] = realLast5.length > 0 ? realLast5 : (gp > 0 ? ([
        ...Array(Math.min(t.wins || 0, 5)).fill("W"),
        ...Array(Math.min(t.losses || 0, 5)).fill("L"),
        ...Array(Math.min(t.ties || 0, 5)).fill("T"),
      ].slice(0, 5) as ("W" | "L" | "T")[]) : []);
      const displayRank = backend?.rank ?? (idx + 1);
      const rankDelta = backend?.rank_delta ?? 0;
      return {
        rank: displayRank,
        prevRank: displayRank + rankDelta,  // positive delta = moved up, so prev was higher #
        name: t.name,
        teamId: t.id,
        owner_id: t.owner_id,
        owner_email: t.owner_email || t.owner_name,
        logo_url: t.logo_url || null,
        logo_abbr: t.logo_abbr || (t.name || "").slice(0,3).toUpperCase(),
        theme_color: t.theme_color || null,
        wins: t.wins || 0,
        losses: t.losses || 0,
        ties: t.ties || 0,
        points: Math.round((t.points_for || 0) + (t.live_points || 0)),
        pointsFor: Math.round((t.points_for || 0) + (t.live_points || 0)),
        pointsAgainst: Math.round(t.points_against || 0),
        streak: gp === 0 ? "—" : ((t.wins || 0) > (t.losses || 0) ? `W${Math.min(t.wins, 5)}` : `L${Math.min(t.losses, 5)}`),
        last5,
        division: backend?.division || UNASSIGNED,
        conference: backend?.conference || UNASSIGNED,
        divWins: Math.floor((t.wins || 0) / 2),
        divLosses: Math.floor((t.losses || 0) / 2),
        confWins: Math.floor((t.wins || 0) * 0.7),
        confLosses: Math.floor((t.losses || 0) * 0.7),
        gb: backend?.games_back ?? 0,
        gbDivision: backend?.games_back_division ?? 0,
        isUser: myTeam?.id === t.id,
        projectedSeed: displayRank,
        clinched: idx === 0 ? ["presidents","conference","division","playoff"] : idx < 3 ? ["playoff"] : undefined,
        capRemaining: backend?.salary_cap_remaining ?? null,
        capUsed: backend?.salary_used ?? null,
        capLimit: backend?.salary_cap ?? null,
      };
    }) as StandingsTeam[];
  }, [leagueTeams, myTeam, backendStandings]);

  const getFilteredTeams = () => {
    let filtered = [...liveTeams];
    if (view === "division" && divisionFilter !== "all") {
      filtered = filtered.filter(t => t.division === divisionFilter);
    } else if (view === "conference" && conferenceFilter !== "all") {
      filtered = filtered.filter(t => t.conference === conferenceFilter);
    }
    return filtered.map((t, i) => ({ ...t, displayRank: i + 1 }));
  };

  // ── Division grouping ────────────────────────────────────────
  // Source the list of divisions from the live backend metadata so custom
  // setups (e.g. "South division" in Ice Kings Head-to-Head) render here
  // instead of being silently dropped by the old NHL-style hardcode. Falls
  // back to the union of divisions present on the actual team docs, then to
  // the NHL defaults, so legacy leagues without metadata still render.
  //
  // Iter 231o — Always append the "Unassigned" bucket when at least one
  // team has no division/conference; otherwise those teams disappear from
  // both the per-division view AND the league-wide "All Divisions" view.
  const UNASSIGNED = "Unassigned";

  const divisionNames = useMemo<string[]>(() => {
    const fromMeta = standingsMeta.divisions || [];
    let base: string[];
    if (fromMeta.length > 0) {
      base = [...fromMeta];
    } else {
      const fromTeams = Array.from(
        new Set(liveTeams.map((t) => t.division).filter((d) => d && d !== UNASSIGNED)),
      ) as string[];
      base = fromTeams.length > 0 ? fromTeams.sort() : ["Atlantic", "Central", "Metropolitan", "Pacific"];
    }
    const hasUnassigned = liveTeams.some((t) => t.division === UNASSIGNED);
    return hasUnassigned ? [...base, UNASSIGNED] : base;
  }, [standingsMeta.divisions, liveTeams]);

  const conferenceNames = useMemo<string[]>(() => {
    const fromMeta = standingsMeta.conferences || [];
    let base: string[];
    if (fromMeta.length > 0) {
      base = [...fromMeta];
    } else {
      const fromTeams = Array.from(
        new Set(liveTeams.map((t) => t.conference).filter((c) => c && c !== UNASSIGNED)),
      ) as string[];
      base = fromTeams.length > 0 ? fromTeams.sort() : ["Eastern", "Western"];
    }
    const hasUnassigned = liveTeams.some((t) => t.conference === UNASSIGNED);
    return hasUnassigned ? [...base, UNASSIGNED] : base;
  }, [standingsMeta.conferences, liveTeams]);

  const getDivisionGroups = () =>
    divisionNames.map(div => ({
      name: div,
      teams: liveTeams.filter(t => t.division === div).map((t, i) => ({ ...t, displayRank: i + 1 })),
    }));

  const getConferenceGroups = () =>
    conferenceNames.map(conf => ({
      name: conf,
      teams: liveTeams
        .filter(t => t.conference === conf)
        .sort((a, b) => b.points - a.points)
        .map((t, i) => ({ ...t, displayRank: i + 1 })),
    }));

  // Iter 232N.76 — Compute "no games played" once so we can hide the
  // real standings tables when the empty state banner is shown.
  const noGamesYet = (() => {
    const rows = Object.values(backendStandings) as any[];
    const totalGames = rows.reduce(
      (acc, r) => acc + (r.wins || 0) + (r.losses || 0) + (r.ties || 0),
      0,
    );
    const totalPF = rows.reduce((acc, r) => acc + (r.points_for || 0), 0);
    return liveTeams.length > 0 && totalGames === 0 && totalPF === 0;
  })();

  return (
    <AppLayout>
      <PullToRefreshIndicator distance={ptr.distance} refreshing={ptr.refreshing} engaged={ptr.engaged} />
      <div className="container py-8">
        <div className="mb-6 flex items-start justify-between flex-wrap gap-4">
          <div>
            <div className="flex items-center gap-2 flex-wrap mb-1">
              <h1 className="text-3xl font-bold">{league?.name || 'Standings'}</h1>
              {/* Iter 232b — Live "last updated" pill; flashes green
                  after a successful pull-to-refresh. */}
              <LastUpdatedBadge timestamp={lastUpdatedAt} testIdSuffix="standings" />
            </div>
            <p className="text-muted-foreground">
              {league ? `${league.format?.replace('_',' ').toUpperCase()} · ${league.current_teams}/${league.max_teams} teams · Live standings` : 'Full league standings, divisions, and playoff picture.'}
            </p>
          </div>
          {/* League switcher moved to the global header (CurrentLeagueDropdown). */}
        </div>

        <Tabs defaultValue="standings" className="space-y-6">
          <TabsList>
            <TabsTrigger value="standings">Standings</TabsTrigger>
            <TabsTrigger value="race">Race Chart</TabsTrigger>
            <TabsTrigger value="playoffs">Playoffs</TabsTrigger>
          </TabsList>

          {/* ── Standings Tab ── */}
          <TabsContent value="standings" className="space-y-4">
            <div className="flex flex-wrap items-center gap-3">
              <Select value={view} onValueChange={(v: ViewType) => { viewExplicitlyChanged.current = true; setView(v); }}>
                <SelectTrigger className="w-[130px] h-9 text-sm"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="league">League</SelectItem>
                  <SelectItem value="division">Division</SelectItem>
                  <SelectItem value="conference">Conference</SelectItem>
                </SelectContent>
              </Select>

              {view === "division" && (
                <Select value={divisionFilter} onValueChange={setDivisionFilter}>
                  <SelectTrigger className="w-[140px] h-9 text-sm"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Divisions</SelectItem>
                    {divisionNames.map(div => (
                      <SelectItem key={div} value={div}>{div}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}

              {view === "conference" && (
                <Select value={conferenceFilter} onValueChange={setConferenceFilter}>
                  <SelectTrigger className="w-[150px] h-9 text-sm"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Conferences</SelectItem>
                    {conferenceNames.map(conf => (
                      <SelectItem key={conf} value={conf}>{conf}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}

              <button
                onClick={() => setCogOpen(true)}
                className="ml-auto flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors px-2.5 py-1.5 rounded-md border border-border hover:bg-secondary/40"
              >
                <Settings className="w-3.5 h-3.5" />
                Customize
              </button>
            </div>

            {/* Clinch Legend */}
            <ClinchLegend />

            {/* Iter 232N.76 — Full-page "No games played yet" empty
                state. Replaces every standings table with a single
                friendly card when the league has literally zero
                results across every team + PF. */}
            {noGamesYet ? (
              <div
                className="rounded-lg border border-border/60 bg-card p-10 text-center space-y-3"
                data-testid="standings-page-empty-state"
              >
                <div className="mx-auto w-12 h-12 rounded-full bg-muted flex items-center justify-center">
                  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
                       stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"
                       className="w-6 h-6 text-muted-foreground">
                    <path d="M6 9H4.5a2.5 2.5 0 0 1 0-5H6" />
                    <path d="M18 9h1.5a2.5 2.5 0 0 0 0-5H18" />
                    <path d="M4 22h16" />
                    <path d="M10 14.66V17c0 .55-.47.98-.97 1.21C7.85 18.75 7 20.24 7 22" />
                    <path d="M14 14.66V17c0 .55.47.98.97 1.21C16.15 18.75 17 20.24 17 22" />
                    <path d="M18 2H6v7a6 6 0 0 0 12 0V2Z" />
                  </svg>
                </div>
                <div className="text-base font-semibold" data-testid="standings-page-empty-title">
                  No games played yet
                </div>
                <p className="text-sm text-muted-foreground max-w-md mx-auto">
                  Standings will populate once the first matchups are scored.
                  All {liveTeams.length} team{liveTeams.length === 1 ? '' : 's'} start at 0-0-0.
                </p>
              </div>
            ) : (
              <>
                {/* League view */}
                {view === "league" && <StandingsTable teams={getFilteredTeams()} columns={columns} streaks={streaks} />}

                {/* Division views */}
                {view === "division" && divisionFilter === "all" ? (
                  <div className="space-y-6">
                    {getDivisionGroups().map(group => (
                      <div key={group.name}>
                        <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider mb-2">{group.name} Division</h3>
                        <StandingsTable teams={group.teams} columns={columns} streaks={streaks} />
                      </div>
                    ))}
                  </div>
                ) : view === "division" ? (
                  <StandingsTable teams={getFilteredTeams()} columns={columns} streaks={streaks} />
                ) : null}

                {/* Conference views */}
                {view === "conference" && conferenceFilter === "all" ? (
                  <div className="space-y-6">
                    {getConferenceGroups().map(group => (
                      <div key={group.name}>
                        <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider mb-2">{group.name} Conference</h3>
                        <StandingsTable teams={group.teams} columns={columns} streaks={streaks} />
                      </div>
                    ))}
                  </div>
                ) : view === "conference" ? (
                  <StandingsTable teams={getFilteredTeams()} columns={columns} streaks={streaks} />
                ) : null}
              </>
            )}
          </TabsContent>

          {/* ── Race Chart Tab ── */}
          <TabsContent value="race">
            <RaceChart teams={liveTeams} />
          </TabsContent>

          {/* ── Playoffs Tab ── */}
          <TabsContent value="playoffs" className="space-y-4">
            <PlayoffBracketView leagueId={leagueId} />
          </TabsContent>
        </Tabs>
      </div>

      <CustomizationModal
        open={cogOpen}
        onClose={() => setCogOpen(false)}
        columns={columns}
        onColumnsChange={setColumns}
      />
    </AppLayout>
  );
};

export default StandingsPage;
