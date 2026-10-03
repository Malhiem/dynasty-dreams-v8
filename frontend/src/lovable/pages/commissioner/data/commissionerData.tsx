// @ts-nocheck
/**
 * Iter 159 — Consolidated data module for CommissionerSettings.
 *
 * Houses all the static data, generators, types, and the two read-only
 * monitor tables that the parent component delegated to via prop injection.
 * Extracting them shrinks CommissionerSettings.tsx by ~640 lines without
 * changing any behavior — every consumer still imports the same identifiers.
 */
import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { Flag, Wrench } from "lucide-react";
import api from "@/lib/api";

// ── Static lists ─────────────────────────────────────────────────
export const nhlTeams = [
  "Anaheim Ducks", "Arizona Coyotes", "Boston Bruins", "Buffalo Sabres", "Calgary Flames",
  "Carolina Hurricanes", "Chicago Blackhawks", "Colorado Avalanche", "Columbus Blue Jackets",
  "Dallas Stars", "Detroit Red Wings", "Edmonton Oilers", "Florida Panthers", "Los Angeles Kings",
  "Minnesota Wild", "Montreal Canadiens", "Nashville Predators", "New Jersey Devils",
  "New York Islanders", "New York Rangers", "Ottawa Senators", "Philadelphia Flyers",
  "Pittsburgh Penguins", "San Jose Sharks", "Seattle Kraken", "St. Louis Blues",
  "Tampa Bay Lightning", "Toronto Maple Leafs", "Vancouver Canucks", "Vegas Golden Knights",
  "Washington Capitals", "Winnipeg Jets"
];

// ── Scoring categories ───────────────────────────────────────────
export interface ScoringCategory {
  id: string;
  name: string;
  abbr: string;
  defaultPoints: number;
  description: string;
  type: "skater" | "goalie" | "both";
}

export const scoringCategories: ScoringCategory[] = [
  // Basic Skating Stats
  { id: "goals", name: "Goals", abbr: "G", defaultPoints: 3, description: "Goal scored", type: "skater" },
  { id: "assists", name: "Assists", abbr: "A", defaultPoints: 2, description: "Primary or secondary assist", type: "skater" },
  { id: "points", name: "Points", abbr: "PTS", defaultPoints: 0, description: "Goal or assist (use if not scoring G/A separately)", type: "skater" },
  { id: "plus_minus", name: "Plus/Minus", abbr: "+/-", defaultPoints: 0.5, description: "Per plus or minus", type: "skater" },
  { id: "games_played", name: "Games Played", abbr: "GP", defaultPoints: 0, description: "Per game played", type: "both" },
  
  // Physical Stats
  { id: "hits", name: "Hits", abbr: "HIT", defaultPoints: 0.2, description: "Per hit delivered", type: "skater" },
  { id: "hits_per_game", name: "Hits per Game", abbr: "HIT/G", defaultPoints: 0, description: "Average hits per game", type: "skater" },
  { id: "blocks", name: "Blocked Shots", abbr: "BLK", defaultPoints: 0.3, description: "Per blocked shot", type: "skater" },
  { id: "blocks_per_game", name: "Blocks per Game", abbr: "BLK/G", defaultPoints: 0, description: "Average blocks per game", type: "skater" },
  { id: "penalty_minutes", name: "Penalty Minutes", abbr: "PIM", defaultPoints: 0.1, description: "Per penalty minute", type: "skater" },
  { id: "giveaways", name: "Giveaways", abbr: "GV", defaultPoints: -0.5, description: "Per giveaway", type: "skater" },
  { id: "takeaways", name: "Takeaways", abbr: "TK", defaultPoints: 0.5, description: "Per takeaway", type: "skater" },
  
  // Faceoffs
  { id: "faceoffs_won", name: "Faceoffs Won", abbr: "FOW", defaultPoints: 0.1, description: "Per faceoff won", type: "skater" },
  { id: "faceoffs_lost", name: "Faceoffs Lost", abbr: "FOL", defaultPoints: -0.1, description: "Per faceoff lost", type: "skater" },
  { id: "faceoffs_won_per_game", name: "Faceoffs Won per Game", abbr: "FOW/G", defaultPoints: 0, description: "Average faceoffs won per game", type: "skater" },
  
  // Shooting Stats
  { id: "shots_on_goal", name: "Shots on Goal", abbr: "SOG", defaultPoints: 0.3, description: "Per shot on goal", type: "skater" },
  { id: "shots_on_goal_per_game", name: "Shots on Goal per Game", abbr: "SOG/G", defaultPoints: 0, description: "Average shots per game", type: "skater" },
  { id: "shots_missed", name: "Shots Missed", abbr: "SMS", defaultPoints: 0, description: "Shots that missed the net", type: "skater" },
  { id: "shots_blocked", name: "Shots Blocked (by opponent)", abbr: "SB", defaultPoints: 0, description: "Shots blocked by opposing players", type: "skater" },
  { id: "shooting_percentage", name: "Shooting Percentage", abbr: "SH%", defaultPoints: 0, description: "Goals / Shots on Goal", type: "skater" },
  { id: "shooting_accuracy", name: "Shooting Accuracy", abbr: "SA%", defaultPoints: 0, description: "SOG / (SOG + Shots Missed)", type: "skater" },
  
  // Power Play Stats
  { id: "power_play_points", name: "Power Play Points", abbr: "PPP", defaultPoints: 1, description: "Bonus for PP goals/assists", type: "skater" },
  { id: "power_play_goals", name: "Power Play Goals", abbr: "PPG", defaultPoints: 0, description: "Goals scored on power play", type: "skater" },
  { id: "power_play_assists", name: "Power Play Assists", abbr: "PPA", defaultPoints: 0, description: "Assists on power play", type: "skater" },
  
  // Shorthanded Stats
  { id: "shorthanded_points", name: "Short-Handed Points", abbr: "SHP", defaultPoints: 2, description: "Bonus for SH goals/assists", type: "skater" },
  { id: "shorthanded_goals", name: "Short-Handed Goals", abbr: "SHG", defaultPoints: 0, description: "Goals scored shorthanded", type: "skater" },
  { id: "shorthanded_assists", name: "Short-Handed Assists", abbr: "SHA", defaultPoints: 0, description: "Assists while shorthanded", type: "skater" },
  
  // Special Teams Combined
  { id: "special_teams_points", name: "Special Team Points", abbr: "STP", defaultPoints: 0, description: "PP or SH points combined", type: "skater" },
  { id: "special_teams_goals", name: "Special Team Goals", abbr: "STG", defaultPoints: 0, description: "PP or SH goals combined", type: "skater" },
  { id: "special_teams_assists", name: "Special Team Assists", abbr: "STA", defaultPoints: 0, description: "PP or SH assists combined", type: "skater" },
  
  // Game Winners & Milestones
  { id: "game_winning_goals", name: "Game-Winning Goals", abbr: "GWG", defaultPoints: 2, description: "Bonus for game winners", type: "skater" },
  { id: "hat_trick", name: "Hat Trick", abbr: "HT", defaultPoints: 5, description: "Bonus for 3+ goals in a game", type: "skater" },
  
  // Advanced Stats
  { id: "points_per_60", name: "Points per 60 Minutes", abbr: "P/60", defaultPoints: 0, description: "Points per 60 min of ice time", type: "skater" },
  { id: "assists_per_game", name: "Assists per Game", abbr: "A/G", defaultPoints: 0, description: "Average assists per game", type: "skater" },
  { id: "time_on_ice_skaters", name: "Time on Ice (Skaters)", abbr: "TOI", defaultPoints: 0, description: "Total time on ice", type: "skater" },
  { id: "shifts", name: "Shifts", abbr: "SFT", defaultPoints: 0, description: "Number of shifts played", type: "skater" },
  
  // Shootout Stats
  { id: "shootout_goals", name: "Shootout Goals", abbr: "SOG*", defaultPoints: 0.5, description: "Goals in shootout", type: "skater" },
  { id: "shootout_attempts", name: "Shootout Attempts", abbr: "SOA", defaultPoints: 0, description: "Shootout attempts taken", type: "skater" },
  { id: "shootout_missed", name: "Shootout Missed Shots", abbr: "SOM", defaultPoints: 0, description: "Shootout attempts missed or saved", type: "skater" },
  
  // Goalie Stats
  { id: "wins", name: "Wins", abbr: "W", defaultPoints: 5, description: "Goalie win", type: "goalie" },
  { id: "losses", name: "Losses", abbr: "L", defaultPoints: -2, description: "Goalie loss", type: "goalie" },
  { id: "saves", name: "Saves", abbr: "SV", defaultPoints: 0.2, description: "Per save", type: "goalie" },
  { id: "goals_against", name: "Goals Against", abbr: "GA", defaultPoints: -1, description: "Per goal allowed", type: "goalie" },
  { id: "shutouts", name: "Shutouts", abbr: "SO", defaultPoints: 5, description: "Bonus for shutout", type: "goalie" },
  { id: "overtime_losses", name: "Overtime Losses", abbr: "OTL", defaultPoints: 1, description: "Point for OT loss", type: "goalie" },
  { id: "shootout_saves", name: "Shootout Attempts Saved", abbr: "SOSV", defaultPoints: 0.5, description: "Shootout saves", type: "goalie" },
  { id: "time_on_ice_goalies", name: "Time on Ice (Goalies)", abbr: "TOI-G", defaultPoints: 0, description: "Total time on ice for goalies", type: "goalie" },
];
// Tank monitoring mock data per week
export interface TeamTankData {
  team: string;
  startingPts: number;
  benchPts: number;
  irPts: number;
  minorsPts: number;
}

export const TOTAL_WEEKS = 22;

// Generate per-week data with some variance per team
export const generateWeeklyData = (): Record<number, TeamTankData[]> => {
  const baseTeams = [
    { team: "Team Frostbite", s: 142.5, b: 38.2, ir: 12.0, m: 8.5 },
    { team: "Polar Bears", s: 156.3, b: 22.1, ir: 5.4, m: 3.8 },
    { team: "Ice Dragons", s: 88.7, b: 95.3, ir: 22.1, m: 14.6 },
    { team: "Frost Giants", s: 134.2, b: 41.0, ir: 8.3, m: 6.1 },
    { team: "Arctic Wolves", s: 102.4, b: 72.8, ir: 18.5, m: 11.2 },
    { team: "Blizzard", s: 148.9, b: 29.5, ir: 7.2, m: 4.3 },
    { team: "Snow Hawks", s: 91.3, b: 88.6, ir: 25.4, m: 18.9 },
    { team: "Glaciers", s: 161.7, b: 18.9, ir: 3.1, m: 2.5 },
    { team: "Tundra Kings", s: 127.6, b: 45.3, ir: 10.8, m: 7.7 },
    { team: "Avalanche", s: 138.1, b: 35.7, ir: 9.4, m: 5.9 },
    { team: "Icebreakers", s: 95.8, b: 82.4, ir: 20.7, m: 15.3 },
    { team: "Northern Lights", s: 152.0, b: 25.3, ir: 6.0, m: 3.2 },
  ];

  // Use a seeded-like approach with fixed offsets per week
  const data: Record<number, TeamTankData[]> = {};
  for (let w = 1; w <= TOTAL_WEEKS; w++) {
    data[w] = baseTeams.map((t, i) => {
      const seed = w * 7 + i * 13;
      const sVar = ((seed % 30) - 15);
      const bVar = ((seed * 3 % 20) - 10);
      const irVar = ((seed * 5 % 10) - 5);
      const mVar = ((seed * 7 % 8) - 4);
      return {
        team: t.team,
        startingPts: Math.max(50, +(t.s + sVar).toFixed(1)),
        benchPts: Math.max(5, +(t.b + bVar).toFixed(1)),
        irPts: Math.max(0, +(t.ir + irVar).toFixed(1)),
        minorsPts: Math.max(0, +(t.m + mVar).toFixed(1)),
      };
    });
  }
  return data;
};

export const weeklyTankData = generateWeeklyData();

export const aggregateWeeks = (fromWeek: number, toWeek: number): TeamTankData[] => {
  const teams = weeklyTankData[1].map(t => t.team);
  return teams.map(team => {
    let s = 0, b = 0, ir = 0, m = 0;
    for (let w = fromWeek; w <= toWeek; w++) {
      const row = weeklyTankData[w]?.find(t => t.team === team);
      if (row) { s += row.startingPts; b += row.benchPts; ir += row.irPts; m += row.minorsPts; }
    }
    return { team, startingPts: +s.toFixed(1), benchPts: +b.toFixed(1), irPts: +ir.toFixed(1), minorsPts: +m.toFixed(1) };
  });
};

export const TankMonitorTable = ({ leagueId }: { leagueId?: string }) => {
  const [fromWeek, setFromWeek] = useState(1);
  const [toWeek, setToWeek] = useState(TOTAL_WEEKS);
  const [liveTeams, setLiveTeams] = useState<TeamTankData[] | null>(null);
  const [liveMode, setLiveMode] = useState<"live" | "weekly_aggregate" | null>(null);
  const [liveWeeksAvailable, setLiveWeeksAvailable] = useState<number>(0);
  const [loading, setLoading] = useState(false);
  const [backfilling, setBackfilling] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [useWeekRange, setUseWeekRange] = useState(false);

  const fetchLive = (range: boolean) => {
    if (!leagueId) { setLiveTeams(null); setLiveMode(null); return; }
    setLoading(true);
    setLoadError(null);
    const url = range
      ? `/leagues/${leagueId}/tank-monitor?from_week=${fromWeek}&to_week=${toWeek}`
      : `/leagues/${leagueId}/tank-monitor`;
    api.get(url)
      .then((res) => {
        setLiveTeams((res.data?.teams || []) as TeamTankData[]);
        setLiveMode(res.data?.mode || "live");
        setLiveWeeksAvailable(res.data?.weeks_available || 0);
      })
      .catch((err) => {
        setLoadError(err?.response?.data?.detail || "Failed to load live tank data");
        setLiveTeams(null); setLiveMode(null);
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => { fetchLive(useWeekRange); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [leagueId, useWeekRange, fromWeek, toWeek]);

  const triggerBackfill = async () => {
    if (!leagueId) return;
    setBackfilling(true);
    try {
      await api.post(`/leagues/${leagueId}/tank-monitor/backfill?weeks=${TOTAL_WEEKS}`);
      fetchLive(useWeekRange);
    } catch (err: any) {
      setLoadError(err?.response?.data?.detail || "Backfill failed");
    } finally {
      setBackfilling(false);
    }
  };

  const isLive = !!leagueId && liveTeams !== null;
  const data = isLive
    ? (liveTeams as TeamTankData[])
    : (fromWeek === toWeek ? (weeklyTankData[fromWeek] || []) : aggregateWeeks(fromWeek, toWeek));

  const calcRatio = (d: TeamTankData) => ((d.startingPts + d.benchPts + d.irPts + d.minorsPts) / d.startingPts * 100);
  const calcBenchPct = (d: TeamTankData) => (d.benchPts / d.startingPts * 100);
  const calcIrPct = (d: TeamTankData) => (d.irPts / d.startingPts * 100);
  const calcMinorsPct = (d: TeamTankData) => (d.minorsPts / d.startingPts * 100);

  const avgStarting = data.length ? data.reduce((s, d) => s + d.startingPts, 0) / data.length : 0;
  const avgBench = data.length ? data.reduce((s, d) => s + d.benchPts, 0) / data.length : 0;
  const avgIr = data.length ? data.reduce((s, d) => s + d.irPts, 0) / data.length : 0;
  const avgMinors = data.length ? data.reduce((s, d) => s + d.minorsPts, 0) / data.length : 0;
  const avgRow: TeamTankData = { team: "League Average", startingPts: avgStarting, benchPts: avgBench, irPts: avgIr, minorsPts: avgMinors };

  const sorted = [...data].sort((a, b) => calcRatio(b) - calcRatio(a));

  const getRatioColor = (ratio: number) => {
    if (ratio >= 200) return "text-red-400 font-bold";
    if (ratio >= 150) return "text-yellow-400 font-semibold";
    return "text-emerald-400";
  };

  const getFlagLevel = (ratio: number) => {
    if (ratio >= 200) return <Badge variant="destructive" className="text-[10px]">High Risk</Badge>;
    if (ratio >= 150) return <Badge className="bg-yellow-500/20 text-yellow-400 border-yellow-500/30 text-[10px]">Monitor</Badge>;
    return <Badge variant="secondary" className="text-[10px]">Normal</Badge>;
  };

  const weekOptions = Array.from({ length: TOTAL_WEEKS }, (_, i) => i + 1);

  return (
    <div className="space-y-4" data-testid="tank-monitor-table">
      {/* Live status banner */}
      {leagueId && (
        <div className="flex items-center gap-2 text-xs flex-wrap" data-testid="tank-monitor-mode">
          {loading && <Badge variant="outline" className="text-xs animate-pulse">Loading live league data…</Badge>}
          {!loading && isLive && (
            <Badge className="bg-emerald-500/15 text-emerald-400 border-emerald-500/30 text-xs" data-testid="tank-monitor-live-badge">
              {liveMode === "weekly_aggregate"
                ? `Weekly aggregate · ${liveWeeksAvailable} week${liveWeeksAvailable === 1 ? "" : "s"} · ${liveTeams?.length ?? 0} teams`
                : `Live · ${liveTeams?.length ?? 0} teams`}
            </Badge>
          )}
          {!loading && loadError && (
            <Badge variant="destructive" className="text-xs" data-testid="tank-monitor-error">{loadError}</Badge>
          )}
          {/* Week-range toggle and (optional) backfill action */}
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="ml-auto text-xs h-7"
            onClick={() => setUseWeekRange((v) => !v)}
            data-testid="tank-monitor-toggle-week-range"
          >
            {useWeekRange ? "Show current snapshot" : "Show week range"}
          </Button>
          {useWeekRange && liveMode === "weekly_aggregate" && liveWeeksAvailable === 0 && (
            <Button
              type="button"
              variant="default"
              size="sm"
              disabled={backfilling}
              className="text-xs h-7"
              onClick={triggerBackfill}
              data-testid="tank-monitor-backfill-button"
            >
              {backfilling ? "Backfilling…" : `Backfill ${TOTAL_WEEKS} weeks`}
            </Button>
          )}
        </div>
      )}

      {/* Week range filters — visible in mock mode AND in live mode when week-range is enabled */}
      {(!isLive || useWeekRange) && (
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2">
          <Label className="text-sm whitespace-nowrap">From Week</Label>
          <Select value={fromWeek.toString()} onValueChange={(v) => { const w = parseInt(v); setFromWeek(w); if (w > toWeek) setToWeek(w); }}>
            <SelectTrigger className="w-24 bg-secondary border-border">
              <SelectValue />
            </SelectTrigger>
            <SelectContent className="bg-popover border-border z-50">
              {weekOptions.map(w => (
                <SelectItem key={w} value={w.toString()}>Week {w}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <span className="text-muted-foreground">→</span>
        <div className="flex items-center gap-2">
          <Label className="text-sm whitespace-nowrap">To Week</Label>
          <Select value={toWeek.toString()} onValueChange={(v) => { const w = parseInt(v); setToWeek(w); if (w < fromWeek) setFromWeek(w); }}>
            <SelectTrigger className="w-24 bg-secondary border-border">
              <SelectValue />
            </SelectTrigger>
            <SelectContent className="bg-popover border-border z-50">
              {weekOptions.filter(w => w >= fromWeek).map(w => (
                <SelectItem key={w} value={w.toString()}>Week {w}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <Badge variant="outline" className="text-xs ml-auto">
          {fromWeek === toWeek ? `Week ${fromWeek}` : `Weeks ${fromWeek}–${toWeek} (${toWeek - fromWeek + 1} weeks)`}
        </Badge>
      </div>
      )}

      <ScrollArea className="w-full" data-testid="roster-monitor-scroll-area">
        <Table className="min-w-[900px]">
          <TableHeader>
            <TableRow className="border-border">
              <TableHead className="text-muted-foreground">Team</TableHead>
              <TableHead className="text-right text-muted-foreground">Starting</TableHead>
              <TableHead className="text-right text-muted-foreground">Bench</TableHead>
              <TableHead className="text-right text-muted-foreground">IR</TableHead>
              <TableHead className="text-right text-muted-foreground">Minors</TableHead>
              <TableHead className="text-right text-muted-foreground">Bench %</TableHead>
              <TableHead className="text-right text-muted-foreground">IR %</TableHead>
              <TableHead className="text-right text-muted-foreground">Minors %</TableHead>
              <TableHead className="text-right text-muted-foreground">Total Ratio %</TableHead>
              <TableHead className="text-center text-muted-foreground">Flag</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            <TableRow className="border-border bg-muted/30 font-medium">
              <TableCell className="font-semibold text-muted-foreground">📊 League Average</TableCell>
              <TableCell className="text-right tabular-nums">{avgRow.startingPts.toFixed(1)}</TableCell>
              <TableCell className="text-right tabular-nums">{avgRow.benchPts.toFixed(1)}</TableCell>
              <TableCell className="text-right tabular-nums">{avgRow.irPts.toFixed(1)}</TableCell>
              <TableCell className="text-right tabular-nums">{avgRow.minorsPts.toFixed(1)}</TableCell>
              <TableCell className="text-right tabular-nums">{calcBenchPct(avgRow).toFixed(1)}%</TableCell>
              <TableCell className="text-right tabular-nums">{calcIrPct(avgRow).toFixed(1)}%</TableCell>
              <TableCell className="text-right tabular-nums">{calcMinorsPct(avgRow).toFixed(1)}%</TableCell>
              <TableCell className="text-right tabular-nums">{calcRatio(avgRow).toFixed(1)}%</TableCell>
              <TableCell className="text-center">—</TableCell>
            </TableRow>
            {sorted.map((d) => {
              const ratio = calcRatio(d);
              return (
                <TableRow key={d.team} className="border-border">
                  <TableCell className="font-medium">{d.team}</TableCell>
                  <TableCell className="text-right tabular-nums">{d.startingPts.toFixed(1)}</TableCell>
                  <TableCell className="text-right tabular-nums">{d.benchPts.toFixed(1)}</TableCell>
                  <TableCell className="text-right tabular-nums">{d.irPts.toFixed(1)}</TableCell>
                  <TableCell className="text-right tabular-nums">{d.minorsPts.toFixed(1)}</TableCell>
                  <TableCell className={`text-right tabular-nums ${calcBenchPct(d) > calcBenchPct(avgRow) ? "text-yellow-400" : ""}`}>{calcBenchPct(d).toFixed(1)}%</TableCell>
                  <TableCell className={`text-right tabular-nums ${calcIrPct(d) > calcIrPct(avgRow) ? "text-yellow-400" : ""}`}>{calcIrPct(d).toFixed(1)}%</TableCell>
                  <TableCell className={`text-right tabular-nums ${calcMinorsPct(d) > calcMinorsPct(avgRow) ? "text-yellow-400" : ""}`}>{calcMinorsPct(d).toFixed(1)}%</TableCell>
                  <TableCell className={`text-right tabular-nums ${getRatioColor(ratio)}`}>{ratio.toFixed(1)}%</TableCell>
                  <TableCell className="text-center">{getFlagLevel(ratio)}</TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </ScrollArea>
      <div className="flex items-center gap-4 text-xs text-muted-foreground pt-2 border-t border-border">
        <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-emerald-400" /> Normal (&lt;150%)</span>
        <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-yellow-400" /> Monitor (150-200%)</span>
        <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-red-400" /> High Risk (&gt;200%)</span>
      </div>
      <p className="text-xs text-muted-foreground">
        <strong>Total Ratio %</strong> = (Starting + Bench + IR + Minors) / Starting × 100. A ratio significantly above 100% suggests a team may have disproportionate talent sitting outside their starting lineup.
      </p>
    </div>
  );
};

// Roster Monitor data
export interface RosterPlayer {
  name: string;
  position: string;
  slot: "starting" | "bench" | "ir" | "minors";
  irEligible: boolean; // true = legitimately injured
  minorsEligible: boolean; // true = meets minors criteria
  playedLastWeek: boolean; // true = played a game in last week's matchup
}

export interface TeamRoster {
  team: string;
  players: RosterPlayer[];
}

export const ROSTER_LIMITS = { starting: 18, bench: 4, ir: 3, minors: 6 };

export const generateRosterData = (): TeamRoster[] => {
  const positions = ["C", "LW", "RW", "D", "G"];
  const firstNames = ["Connor", "Auston", "Nathan", "Cale", "Leon", "Sidney", "Alex", "Nikita", "Jack", "Mitch", "Brady", "Quinn", "Elias", "Andrei", "Sebastian", "Igor", "Ilya", "Adam", "Kirill", "Tage", "Trevor", "Brock", "Kyle", "David", "Tim", "Rasmus", "Jason", "Jesper", "Filip", "Cole"];
  const lastNames = ["McDavid", "Matthews", "MacKinnon", "Makar", "Draisaitl", "Crosby", "Ovechkin", "Kucherov", "Eichel", "Marner", "Tkachuk", "Hughes", "Pettersson", "Svechnikov", "Aho", "Shesterkin", "Sorokin", "Fox", "Kaprizov", "Thompson", "Zegras", "Boeser", "Connor", "Pastrnak", "Stutzle", "Dahlin", "Robertson", "Bratt", "Forsberg", "Caufield"];

  const teams = ["Team Frostbite", "Polar Bears", "Ice Dragons", "Frost Giants", "Arctic Wolves", "Blizzard", "Snow Hawks", "Glaciers", "Tundra Kings", "Avalanche", "Icebreakers", "Northern Lights"];

  return teams.map((team, ti) => {
    const players: RosterPlayer[] = [];
    let nameIdx = 0;

    // Starting lineup
    const startCount = ti === 2 ? 20 : ti === 6 ? 19 : 18; // Ice Dragons & Snow Hawks over limit
    for (let i = 0; i < startCount; i++) {
      const idx = (ti * 7 + nameIdx) % firstNames.length;
      const didPlay = ti === 4 && i >= 16 ? false : ti === 9 && i >= 15 ? false : true; // Arctic Wolves & Avalanche have inactive starters
      players.push({
        name: `${firstNames[idx]} ${lastNames[(idx + ti) % lastNames.length]}`,
        position: positions[i % positions.length],
        slot: "starting",
        irEligible: false,
        minorsEligible: false,
        playedLastWeek: didPlay,
      });
      nameIdx++;
    }

    // Bench
    const benchCount = ti === 3 ? 5 : ti === 5 ? 2 : ti === 8 ? 3 : 4; // Frost Giants over limit; Blizzard & Tundra Kings have room
    for (let i = 0; i < benchCount; i++) {
      const idx = (ti * 11 + nameIdx) % firstNames.length;
      players.push({
        name: `${firstNames[idx]} ${lastNames[(idx + ti + 3) % lastNames.length]}`,
        position: positions[(i + 2) % positions.length],
        slot: "bench",
        irEligible: false,
        minorsEligible: false,
        playedLastWeek: false,
      });
      nameIdx++;
    }

    // IR
    const irCount = ti === 7 ? 4 : ti === 10 ? 4 : 2; // Glaciers & Icebreakers over limit
    for (let i = 0; i < irCount; i++) {
      const idx = (ti * 13 + nameIdx) % firstNames.length;
      const isEligible = !(ti === 5 && i === 1) && !(ti === 10 && i >= 2); // Blizzard has 1 ineligible, Icebreakers has 2
      players.push({
        name: `${firstNames[idx]} ${lastNames[(idx + ti + 7) % lastNames.length]}`,
        position: positions[(i + 1) % positions.length],
        slot: "ir",
        irEligible: isEligible,
        minorsEligible: false,
        playedLastWeek: false,
      });
      nameIdx++;
    }

    // Minors
    const minorsCount = ti === 1 ? 7 : ti === 11 ? 8 : 5; // Polar Bears & Northern Lights over limit
    for (let i = 0; i < minorsCount; i++) {
      const idx = (ti * 17 + nameIdx) % firstNames.length;
      const isEligible = !(ti === 8 && i >= 4) && !(ti === 1 && i >= 5); // Tundra Kings & Polar Bears have ineligible
      players.push({
        name: `${firstNames[idx]} ${lastNames[(idx + ti + 11) % lastNames.length]}`,
        position: positions[(i + 3) % positions.length],
        slot: "minors",
        irEligible: false,
        minorsEligible: isEligible,
        playedLastWeek: false,
      });
      nameIdx++;
    }

    return { team, players };
  });
};

export const rosterMonitorData = generateRosterData();

// Generate weekly snapshots for historical review
export const generateWeeklyRosterFlags = () => {
  const weeks: Record<number, Record<string, { starting: number; bench: number; ir: number; minors: number; flags: string[] }>> = {};
  for (let w = 1; w <= TOTAL_WEEKS; w++) {
    weeks[w] = {};
    rosterMonitorData.forEach((t) => {
      const startCount = t.players.filter(p => p.slot === "starting").length;
      const benchCount = t.players.filter(p => p.slot === "bench").length;
      const irCount = t.players.filter(p => p.slot === "ir").length;
      const minorsCount = t.players.filter(p => p.slot === "minors").length;
      const flags: string[] = [];

      // Simulate some variance per week
      const seed = w * 3 + t.team.length;
      const wStartCount = startCount + ((seed % 3) - 1);
      const wBenchCount = benchCount + ((seed % 2));
      const wIrCount = irCount + ((seed * 2 % 3) - 1);
      const wMinorsCount = minorsCount + ((seed * 5 % 2));

      if (wStartCount > ROSTER_LIMITS.starting) flags.push("starting-over");
      if (wBenchCount > ROSTER_LIMITS.bench) flags.push("bench-over");
      if (wIrCount > ROSTER_LIMITS.ir) flags.push("ir-over");
      if (wMinorsCount > ROSTER_LIMITS.minors) flags.push("minors-over");

      // Simulate eligibility issues appearing some weeks
      if ((seed + w) % 5 === 0) flags.push("ir-ineligible");
      if ((seed + w) % 7 === 0) flags.push("minors-ineligible");
      if ((seed + w) % 6 === 0) flags.push("starting-inactive");

      weeks[w][t.team] = { starting: wStartCount, bench: wBenchCount, ir: wIrCount, minors: wMinorsCount, flags };
    });
  }
  return weeks;
};

export const weeklyRosterFlags = generateWeeklyRosterFlags();

export const CAP_LIMIT = 88000000;

// Simulated cap usage per team
export const teamCapUsage: Record<string, number> = {
  "Team Frostbite": 85000000,
  "Polar Bears": 87500000,
  "Ice Dragons": 92000000,
  "Frost Giants": 86000000,
  "Arctic Wolves": 84000000,
  "Blizzard": 87000000,
  "Snow Hawks": 91000000,
  "Glaciers": 88500000,
  "Tundra Kings": 83000000,
  "Avalanche": 86500000,
  "Icebreakers": 89000000,
  "Northern Lights": 82000000,
};

export interface AutoFixResult {
  canFix: boolean;
  reason?: string;
  fixCount: number;
}

export const evaluateAutoFix = (
  teamData: TeamRoster,
  benchCount: number,
  irIneligible: boolean,
  minorsIneligible: boolean,
  startingInactive: boolean,
  startOver: boolean,
  benchOver: boolean,
  irOver: boolean,
  minorsOver: boolean,
): AutoFixResult => {
  // No violations = nothing to fix
  if (!irIneligible && !minorsIneligible && !startingInactive && !startOver && !benchOver && !irOver && !minorsOver) {
    return { canFix: false, reason: "No violations", fixCount: 0 };
  }

  // Count players that would be moved to bench
  const irIneligiblePlayers = teamData.players.filter(p => p.slot === "ir" && !p.irEligible);
  const minorsIneligiblePlayers = teamData.players.filter(p => p.slot === "minors" && !p.minorsEligible);
  const moveToBenchCount = irIneligiblePlayers.length + minorsIneligiblePlayers.length;

  // If there are over-limit violations on starting/bench, can't auto-fix
  if (startOver || benchOver) {
    return { canFix: false, reason: "Manual fix required", fixCount: 0 };
  }

  // If over IR/minors limit (not just eligibility), manual fix needed
  if (irOver || minorsOver) {
    // Check if moving ineligible players would also resolve the over-limit
    const newIrCount = teamData.players.filter(p => p.slot === "ir").length - irIneligiblePlayers.length;
    const newMinorsCount = teamData.players.filter(p => p.slot === "minors").length - minorsIneligiblePlayers.length;
    const stillIrOver = newIrCount > ROSTER_LIMITS.ir;
    const stillMinorsOver = newMinorsCount > ROSTER_LIMITS.minors;
    if (stillIrOver || stillMinorsOver) {
      return { canFix: false, reason: "Manual fix required", fixCount: 0 };
    }
  }

  if (moveToBenchCount === 0 && startingInactive) {
    // Inactive starters are a warning only, no auto-move
    return { canFix: false, reason: "Manual fix required", fixCount: 0 };
  }

  if (moveToBenchCount === 0) {
    return { canFix: false, reason: "No violations", fixCount: 0 };
  }

  // Check bench won't exceed limit
  const newBenchCount = benchCount + moveToBenchCount;
  if (newBenchCount > ROSTER_LIMITS.bench) {
    return { canFix: false, reason: "Manual fix required", fixCount: 0 };
  }

  // Check cap won't be exceeded (moving to bench doesn't change cap, but we validate they're not already over)
  const capUsed = teamCapUsage[teamData.team] ?? 0;
  if (capUsed > CAP_LIMIT) {
    return { canFix: false, reason: "Manual fix required", fixCount: 0 };
  }

  return { canFix: true, fixCount: moveToBenchCount };
};

interface LiveRosterTeam {
  team_id: string;
  team: string;
  counts: { starting: number; bench: number; ir: number; minors: number };
  violations: { type: string; message: string }[];
  players: { id: string; name: string; position: string; slot: string; is_goalie: boolean; irEligible: boolean; fantasyPoints: number }[];
}

export const RosterMonitorTable = ({ onAuditLog, leagueId }: { onAuditLog?: (entry: Omit<AuditLogEntry, "id" | "timestamp">) => void; leagueId?: string }) => {
  const [reviewWeek, setReviewWeek] = useState<number>(0); // 0 = current/live
  const [fixedTeams, setFixedTeams] = useState<Set<string>>(new Set());
  const [liveTeams, setLiveTeams] = useState<LiveRosterTeam[] | null>(null);
  const [liveLimits, setLiveLimits] = useState<typeof ROSTER_LIMITS | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    if (!leagueId) { setLiveTeams(null); setLiveLimits(null); return; }
    setLoading(true);
    setLoadError(null);
    api.get(`/leagues/${leagueId}/roster-monitor`)
      .then((res) => {
        setLiveTeams((res.data?.teams || []) as LiveRosterTeam[]);
        const l = res.data?.limits || {};
        setLiveLimits({
          starting: (l.starting_skaters || 0) + (l.starting_goalies || 0),
          bench: l.bench || ROSTER_LIMITS.bench,
          ir: l.ir || ROSTER_LIMITS.ir,
          minors: l.minors || ROSTER_LIMITS.minors,
        });
      })
      .catch((err) => {
        setLoadError(err?.response?.data?.detail || "Failed to load live roster data");
        setLiveTeams(null); setLiveLimits(null);
      })
      .finally(() => setLoading(false));
  }, [leagueId]);

  const isLive = !!leagueId && liveTeams !== null;
  const limits = isLive ? (liveLimits as typeof ROSTER_LIMITS) : ROSTER_LIMITS;
  const weekOptions = Array.from({ length: TOTAL_WEEKS }, (_, i) => i + 1);

  const isCurrentView = reviewWeek === 0;

  const handleAutoFix = (teamName: string) => {
    setFixedTeams(prev => new Set(prev).add(teamName));
    const teamData = rosterMonitorData.find(t => t.team === teamName);
    const irIneligible = teamData?.players.filter(p => p.slot === "ir" && !p.irEligible).length ?? 0;
    const minorsIneligible = teamData?.players.filter(p => p.slot === "minors" && !p.minorsEligible).length ?? 0;
    const totalMoved = irIneligible + minorsIneligible;
    const details: string[] = [];
    if (irIneligible > 0) details.push(`${irIneligible} ineligible IR player(s)`);
    if (minorsIneligible > 0) details.push(`${minorsIneligible} ineligible Minors player(s)`);
    onAuditLog?.({
      action: "auto-fix",
      category: "Roster",
      description: `Auto-fix: Moved ${details.join(" and ")} to Bench`,
      team: teamName,
      performedBy: "System (Auto-Fix)",
    });
  };

  return (
    <div className="space-y-4" data-testid="roster-monitor-table">
      {/* Live status banner */}
      {leagueId && (
        <div className="flex items-center gap-2 text-xs" data-testid="roster-monitor-mode">
          {loading && <Badge variant="outline" className="text-xs animate-pulse">Loading live league data…</Badge>}
          {!loading && isLive && (
            <Badge className="bg-emerald-500/15 text-emerald-400 border-emerald-500/30 text-xs" data-testid="roster-monitor-live-badge">
              Live · {liveTeams?.length ?? 0} teams
            </Badge>
          )}
          {!loading && loadError && (
            <Badge variant="destructive" className="text-xs" data-testid="roster-monitor-error">{loadError}</Badge>
          )}
        </div>
      )}

      {!isLive && (
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2">
          <Label className="text-sm whitespace-nowrap">Review Week</Label>
          <Select value={reviewWeek.toString()} onValueChange={(v) => { setReviewWeek(parseInt(v)); setFixedTeams(new Set()); }}>
            <SelectTrigger className="w-32 bg-secondary border-border">
              <SelectValue />
            </SelectTrigger>
            <SelectContent className="bg-popover border-border z-50">
              <SelectItem value="0">Current</SelectItem>
              {weekOptions.map(w => (
                <SelectItem key={w} value={w.toString()}>Week {w}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <Badge variant="outline" className="text-xs ml-auto">
          {isCurrentView ? "Live Roster View" : `Week ${reviewWeek} Snapshot`}
        </Badge>
      </div>
      )}

      <div className="flex items-center gap-4 text-xs text-muted-foreground pb-2 border-b border-border">
        <span>Limits: Starting {limits.starting} | Bench {limits.bench} | IR {limits.ir} | Minors {limits.minors}</span>
      </div>

      <div className="flex items-center gap-4 text-xs text-muted-foreground">
        <span className="flex items-center gap-1.5">🔴 Over roster limit</span>
        <span className="flex items-center gap-1.5">🟡 Eligibility / inactivity concern</span>
        <span className="flex items-center gap-1.5">✅ Compliant</span>
      </div>

      <ScrollArea className="w-full" data-testid="tank-monitor-scroll-area">
        <Table className="min-w-[700px]">
          <TableHeader>
            <TableRow className="border-border">
              <TableHead className="text-muted-foreground">Team</TableHead>
              <TableHead className="text-center text-muted-foreground">Starting ({limits.starting})</TableHead>
              <TableHead className="text-center text-muted-foreground">Bench ({limits.bench})</TableHead>
              <TableHead className="text-center text-muted-foreground">IR ({limits.ir})</TableHead>
              <TableHead className="text-center text-muted-foreground">Minors ({limits.minors})</TableHead>
              <TableHead className="text-center text-muted-foreground">Status</TableHead>
              <TableHead className="text-center text-muted-foreground">Auto-Fix</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {((isLive ? (liveTeams || []).map((lt) => ({
              team: lt.team,
              players: (lt.players || []).map((p) => ({
                name: p.name, position: p.position, slot: p.slot as any,
                irEligible: !!p.irEligible, minorsEligible: true, playedLastWeek: true,
              })),
            } as TeamRoster)) : rosterMonitorData)).map((teamData) => {
              let startCount: number, benchCount: number, irCount: number, minorsCount: number;
              let irIneligible = false, minorsIneligible = false, startingInactive = false;

              if (isLive || isCurrentView) {
                startCount = teamData.players.filter(p => p.slot === "starting").length;
                benchCount = teamData.players.filter(p => p.slot === "bench").length;
                irCount = teamData.players.filter(p => p.slot === "ir").length;
                minorsCount = teamData.players.filter(p => p.slot === "minors").length;
                irIneligible = teamData.players.some(p => p.slot === "ir" && !p.irEligible);
                minorsIneligible = teamData.players.some(p => p.slot === "minors" && !p.minorsEligible);
                startingInactive = teamData.players.some(p => p.slot === "starting" && !p.playedLastWeek);
              } else {
                const snap = weeklyRosterFlags[reviewWeek]?.[teamData.team];
                startCount = snap?.starting ?? 0;
                benchCount = snap?.bench ?? 0;
                irCount = snap?.ir ?? 0;
                minorsCount = snap?.minors ?? 0;
                irIneligible = snap?.flags.includes("ir-ineligible") ?? false;
                minorsIneligible = snap?.flags.includes("minors-ineligible") ?? false;
                startingInactive = snap?.flags.includes("starting-inactive") ?? false;
              }

              const startOver = startCount > limits.starting;
              const benchOver = benchCount > limits.bench;
              const irOver = irCount > limits.ir;
              const minorsOver = minorsCount > limits.minors;
              const hasRedFlag = startOver || benchOver || irOver || minorsOver;
              const hasYellowFlag = irIneligible || minorsIneligible || startingInactive;
              const isFixed = fixedTeams.has(teamData.team);

              const autoFixResult = evaluateAutoFix(
                teamData, benchCount, irIneligible, minorsIneligible, startingInactive,
                startOver, benchOver, irOver, minorsOver,
              );

              const FlagIcon = ({ red, yellow, tooltip }: { red?: boolean; yellow?: boolean; tooltip: string }) => (
                <Tooltip>
                  <TooltipTrigger asChild>
                    <span className="inline-flex ml-1 cursor-help">
                      {red && <Flag className="h-3.5 w-3.5 text-destructive fill-destructive" />}
                      {yellow && <Flag className="h-3.5 w-3.5 text-yellow-500 fill-yellow-500" />}
                    </span>
                  </TooltipTrigger>
                  <TooltipContent><p className="text-xs">{tooltip}</p></TooltipContent>
                </Tooltip>
              );

              return (
                <TableRow key={teamData.team} className="border-border">
                  <TableCell className="font-medium">{teamData.team}</TableCell>
                  <TableCell className="text-center">
                    <span className={`tabular-nums ${startOver && !isFixed ? "text-destructive font-bold" : ""}`}>{isFixed ? limits.starting : startCount}</span>
                    {!isFixed && startOver && <FlagIcon red tooltip={`Over limit: ${startCount}/${limits.starting}`} />}
                    {!isFixed && startingInactive && <FlagIcon yellow tooltip="Player(s) in starting lineup did not play last week" />}
                  </TableCell>
                  <TableCell className="text-center">
                    <span className={`tabular-nums ${benchOver && !isFixed ? "text-destructive font-bold" : ""}`}>{isFixed ? benchCount + autoFixResult.fixCount : benchCount}</span>
                    {!isFixed && benchOver && <FlagIcon red tooltip={`Over limit: ${benchCount}/${limits.bench}`} />}
                  </TableCell>
                  <TableCell className="text-center">
                    <span className={`tabular-nums ${irOver && !isFixed ? "text-destructive font-bold" : ""}`}>
                      {isFixed ? irCount - teamData.players.filter(p => p.slot === "ir" && !p.irEligible).length : irCount}
                    </span>
                    {!isFixed && irOver && <FlagIcon red tooltip={`Over limit: ${irCount}/${limits.ir}`} />}
                    {!isFixed && irIneligible && <FlagIcon yellow tooltip="Player(s) no longer meet IR eligibility criteria" />}
                  </TableCell>
                  <TableCell className="text-center">
                    <span className={`tabular-nums ${minorsOver && !isFixed ? "text-destructive font-bold" : ""}`}>
                      {isFixed ? minorsCount - teamData.players.filter(p => p.slot === "minors" && !p.minorsEligible).length : minorsCount}
                    </span>
                    {!isFixed && minorsOver && <FlagIcon red tooltip={`Over limit: ${minorsCount}/${limits.minors}`} />}
                    {!isFixed && minorsIneligible && <FlagIcon yellow tooltip="Player(s) no longer meet minors eligibility criteria" />}
                  </TableCell>
                  <TableCell className="text-center">
                    {isFixed ? (
                      <Badge variant="secondary" className="text-[10px]">Fixed</Badge>
                    ) : hasRedFlag ? (
                      <Badge variant="destructive" className="text-[10px]">Violation</Badge>
                    ) : hasYellowFlag ? (
                      <Badge className="bg-yellow-500/20 text-yellow-500 border-yellow-500/30 text-[10px]">Review</Badge>
                    ) : (
                      <Badge variant="secondary" className="text-[10px]">Compliant</Badge>
                    )}
                  </TableCell>
                  <TableCell className="text-center">
                    {isFixed ? (
                      <span className="text-xs text-muted-foreground">✅ Applied</span>
                    ) : !hasRedFlag && !hasYellowFlag ? (
                      <span className="text-xs text-muted-foreground">—</span>
                    ) : autoFixResult.canFix ? (
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <Button
                            size="sm"
                            variant="ice"
                            className="h-7 text-[11px] gap-1"
                            onClick={() => handleAutoFix(teamData.team)}
                          >
                            <Wrench className="h-3 w-3" />
                            Fix ({autoFixResult.fixCount})
                          </Button>
                        </TooltipTrigger>
                        <TooltipContent>
                          <p className="text-xs">Move {autoFixResult.fixCount} ineligible player(s) to bench effective next week</p>
                        </TooltipContent>
                      </Tooltip>
                    ) : (
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <span className="inline-flex items-center gap-1 text-[11px] text-muted-foreground/60 cursor-not-allowed">
                            <Wrench className="h-3 w-3" />
                            {autoFixResult.reason}
                          </span>
                        </TooltipTrigger>
                        <TooltipContent>
                          <p className="text-xs">Cannot auto-fix: would exceed bench limit or salary cap</p>
                        </TooltipContent>
                      </Tooltip>
                    )}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </ScrollArea>
    </div>
  );
};
export interface AuditLogEntry {
  id: string;
  timestamp: Date;
  action: "auto-fix" | "roster-move" | "player-drop" | "player-add" | "setting-change" | "trade-override" | "scoring-update" | "draft-change";
  category: "Roster" | "League Settings" | "Scoring" | "Draft" | "Trade";
  description: string;
  team?: string;
  performedBy: string;
}

export const generateMockAuditLog = (): AuditLogEntry[] => {
  const now = new Date();
  const entries: AuditLogEntry[] = [
    { id: "al-1", timestamp: new Date(now.getTime() - 2 * 60 * 60 * 1000), action: "setting-change", category: "League Settings", description: "Updated trade deadline to Week 18", performedBy: "Commissioner" },
    { id: "al-2", timestamp: new Date(now.getTime() - 5 * 60 * 60 * 1000), action: "roster-move", category: "Roster", description: "Moved Connor McDavid from IR to Starting Lineup", team: "Arctic Wolves", performedBy: "Commissioner" },
    { id: "al-3", timestamp: new Date(now.getTime() - 8 * 60 * 60 * 1000), action: "trade-override", category: "Trade", description: "Approved trade: Auston Matthews (Polar Bears) ↔ Nathan MacKinnon (Ice Dragons)", performedBy: "Commissioner" },
    { id: "al-4", timestamp: new Date(now.getTime() - 1 * 24 * 60 * 60 * 1000), action: "auto-fix", category: "Roster", description: "Auto-fix: Moved 1 ineligible IR player to Bench", team: "Snow Hawks", performedBy: "System (Auto-Fix)" },
    { id: "al-5", timestamp: new Date(now.getTime() - 1 * 24 * 60 * 60 * 1000), action: "player-drop", category: "Roster", description: "Dropped Leon Draisaitl from roster", team: "Frost Giants", performedBy: "Commissioner" },
    { id: "al-6", timestamp: new Date(now.getTime() - 2 * 24 * 60 * 60 * 1000), action: "scoring-update", category: "Scoring", description: "Changed Goals scoring from 3.0 to 3.5 points", performedBy: "Commissioner" },
    { id: "al-7", timestamp: new Date(now.getTime() - 2 * 24 * 60 * 60 * 1000), action: "player-add", category: "Roster", description: "Added Cale Makar to roster from free agency", team: "Blizzard", performedBy: "Commissioner" },
    { id: "al-8", timestamp: new Date(now.getTime() - 3 * 24 * 60 * 60 * 1000), action: "draft-change", category: "Draft", description: "Swapped Round 2 pick order: Glaciers ↔ Tundra Kings", performedBy: "Commissioner" },
    { id: "al-9", timestamp: new Date(now.getTime() - 4 * 24 * 60 * 60 * 1000), action: "roster-move", category: "Roster", description: "Moved Sidney Crosby from Bench to Starting Lineup", team: "Northern Lights", performedBy: "Commissioner" },
    { id: "al-10", timestamp: new Date(now.getTime() - 5 * 24 * 60 * 60 * 1000), action: "setting-change", category: "League Settings", description: "Enabled IR-to-Bench auto-fix for eligibility violations", performedBy: "Commissioner" },
    { id: "al-11", timestamp: new Date(now.getTime() - 6 * 24 * 60 * 60 * 1000), action: "auto-fix", category: "Roster", description: "Auto-fix: Moved 2 ineligible Minors players to Bench", team: "Tundra Kings", performedBy: "System (Auto-Fix)" },
    { id: "al-12", timestamp: new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000), action: "trade-override", category: "Trade", description: "Vetoed trade: Jack Eichel (Avalanche) ↔ Mitch Marner (Team Frostbite)", performedBy: "Commissioner" },
    { id: "al-13", timestamp: new Date(now.getTime() - 8 * 24 * 60 * 60 * 1000), action: "scoring-update", category: "Scoring", description: "Enabled Hits scoring category at 0.2 points per hit", performedBy: "Commissioner" },
    { id: "al-14", timestamp: new Date(now.getTime() - 10 * 24 * 60 * 60 * 1000), action: "setting-change", category: "League Settings", description: "Changed roster limit: Bench increased from 3 to 4", performedBy: "Commissioner" },
    { id: "al-15", timestamp: new Date(now.getTime() - 12 * 24 * 60 * 60 * 1000), action: "player-drop", category: "Roster", description: "Dropped Igor Shesterkin from roster (season-ending injury)", team: "Icebreakers", performedBy: "Commissioner" },
  ];
  return entries.sort((a, b) => b.timestamp.getTime() - a.timestamp.getTime());
};
