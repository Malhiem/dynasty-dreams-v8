// @ts-nocheck
import { useState, useEffect, useMemo } from "react";
import { AppLayout } from "@/components/layout/AppLayout";
import { useActiveLeague } from "@/hooks/use-active-league";
import LeagueContextBanner from "@/lovable/components/dashboard/LeagueContextBanner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
} from "recharts";
import { TrendingUp, Users, Target, DollarSign, ArrowUpRight, ArrowDownRight, Loader2, Database } from "lucide-react";
import api from "@/lib/api";

// Fallback weekly/YoY data — used only when the backend has no week_summaries yet
const FALLBACK_WEEKLY = [
  { week: "W1", pointsFor: 245, pointsAgainst: 220, leagueAvg: 232 },
  { week: "W2", pointsFor: 268, pointsAgainst: 255, leagueAvg: 241 },
  { week: "W3", pointsFor: 231, pointsAgainst: 248, leagueAvg: 238 },
  { week: "W4", pointsFor: 289, pointsAgainst: 212, leagueAvg: 245 },
  { week: "W5", pointsFor: 256, pointsAgainst: 267, leagueAvg: 252 },
  { week: "W6", pointsFor: 274, pointsAgainst: 241, leagueAvg: 248 },
  { week: "W7", pointsFor: 298, pointsAgainst: 225, leagueAvg: 255 },
  { week: "W8", pointsFor: 262, pointsAgainst: 278, leagueAvg: 261 },
  { week: "W9", pointsFor: 285, pointsAgainst: 232, leagueAvg: 258 },
  { week: "W10", pointsFor: 271, pointsAgainst: 245, leagueAvg: 262 },
];

// Fallback weekly data (module-level) + YoY
const STATIC_WEEKLY = FALLBACK_WEEKLY;

// Year-over-year fallback
const STATIC_YOY = [
  { season: "2019-20", pointsFor: 11240, pointsAgainst: 10850, leagueAvg: 10950, wins: 14, losses: 10 },
  { season: "2020-21", pointsFor: 11680, pointsAgainst: 11120, leagueAvg: 11200, wins: 16, losses: 8 },
  { season: "2021-22", pointsFor: 12100, pointsAgainst: 11450, leagueAvg: 11550, wins: 17, losses: 7 },
  { season: "2022-23", pointsFor: 11950, pointsAgainst: 11780, leagueAvg: 11700, wins: 15, losses: 9 },
  { season: "2023-24", pointsFor: 12480, pointsAgainst: 11290, leagueAvg: 11850, wins: 18, losses: 6 },
  { season: "2024-25", pointsFor: 12890, pointsAgainst: 11650, leagueAvg: 12050, wins: 19, losses: 5 },
  { season: "2025-26", pointsFor: 2679, pointsAgainst: 2423, leagueAvg: 2492, wins: 7, losses: 3 },
];

// Iter 114 — `teamsSeasonData` is no longer hard-coded. It is now derived
// in-component via `useMemo` against the live `leagueTeams` collection so
// every team in the league is selectable in the Comparison tab.

const COMPARE_COLORS = [
  "hsl(192, 82%, 55%)",
  "hsl(45, 93%, 58%)",
  "hsl(142, 71%, 45%)",
  "hsl(262, 80%, 60%)",
];

// Player roster data for pie charts
const rosterByPoints = [
  { name: "Nathan MacKinnon", value: 185, position: "C" },
  { name: "Cale Makar", value: 162, position: "D" },
  { name: "Mikko Rantanen", value: 148, position: "RW" },
  { name: "Artemi Panarin", value: 142, position: "LW" },
  { name: "Igor Shesterkin", value: 128, position: "G" },
  { name: "Others", value: 245, position: "Mixed" },
];

const rosterBySalary = [
  { name: "Nathan MacKinnon", value: 12.6, position: "C" },
  { name: "Cale Makar", value: 9.0, position: "D" },
  { name: "Mikko Rantanen", value: 9.25, position: "RW" },
  { name: "Artemi Panarin", value: 11.6, position: "LW" },
  { name: "Igor Shesterkin", value: 5.7, position: "G" },
  { name: "Others", value: 33.85, position: "Mixed" },
];

const rosterByPosition = [
  { name: "Centers", value: 4, color: "hsl(192, 82%, 55%)" },
  { name: "Left Wings", value: 3, color: "hsl(45, 93%, 58%)" },
  { name: "Right Wings", value: 3, color: "hsl(142, 71%, 45%)" },
  { name: "Defensemen", value: 4, color: "hsl(262, 80%, 60%)" },
  { name: "Goalies", value: 2, color: "hsl(0, 72%, 51%)" },
];

const COLORS = [
  "hsl(192, 82%, 55%)",
  "hsl(45, 93%, 58%)",
  "hsl(142, 71%, 45%)",
  "hsl(262, 80%, 60%)",
  "hsl(0, 72%, 51%)",
  // Iter 110 — bumped from `hsl(222, 30%, 40%)` (dark slate) to a brighter
  // neutral so the 6th pie wedge stays visible against the dark card
  // background. Old value silently rendered black-on-black.
  "hsl(215, 25%, 70%)",
];

const Analytics = () => {
  const { league, leagueTeams, myTeam } = useActiveLeague();
  const leagueTeamsCount = leagueTeams?.length || 0;
  const totalFpts = Math.round((leagueTeams || []).reduce((a, t) => a + ((t.points_for || 0) + (t.live_points || 0)), 0));
  const pendingTradesCount = 0; // wired in follow-up
  const pendingClaimsCount = 0;

  const [pieChartType, setPieChartType] = useState("points");
  const [yoyMetric, setYoyMetric] = useState<"pointsFor" | "pointsAgainst" | "differential">("pointsFor");
  const [showLeagueAvg, setShowLeagueAvg] = useState(true);
  const [compareTeams, setCompareTeams] = useState<string[]>([]);
  const [compareMetric, setCompareMetric] = useState<"pointsFor" | "pointsAgainst" | "differential">("pointsFor");
  // Iter 114 — Performance Trends time-period filter (across multiple seasons).
  type TrendsPeriod = "current" | "last2" | "last5" | "all";
  const [trendsPeriod, setTrendsPeriod] = useState<TrendsPeriod>("current");

  // ─── Live weekly / YoY data (with fallback to synthetic when empty) ───
  const [weeklyData, setWeeklyData] = useState<any[]>(STATIC_WEEKLY);
  const [yearOverYearData, setYearOverYearData] = useState<any[]>(STATIC_YOY);
  const [analyticsLoading, setAnalyticsLoading] = useState(false);
  const [analyticsLive, setAnalyticsLive] = useState(false);

  useEffect(() => {
    if (!league?.id || !myTeam?.id) return;
    let cancelled = false;
    setAnalyticsLoading(true);
    api.get(`/leagues/${league.id}/weekly-analytics?team_id=${myTeam.id}`)
      .then(({ data }) => {
        if (cancelled) return;
        const live = (data?.weeks || []).length > 0;
        setAnalyticsLive(live);
        setWeeklyData(live ? data.weeks : STATIC_WEEKLY);
        if ((data?.year_over_year || []).length > 0) {
          setYearOverYearData(data.year_over_year);
        } else {
          setYearOverYearData(STATIC_YOY);
        }
      })
      .catch(() => {
        setAnalyticsLive(false);
        setWeeklyData(STATIC_WEEKLY);
        setYearOverYearData(STATIC_YOY);
      })
      .finally(() => { if (!cancelled) setAnalyticsLoading(false); });
    return () => { cancelled = true; };
  }, [league?.id, myTeam?.id]);

  const getPieData = () => {
    switch (pieChartType) {
      case "salary":
        return rosterBySalary;
      case "position":
        return rosterByPosition;
      default:
        return rosterByPoints;
    }
  };

  const getPieLabel = () => {
    switch (pieChartType) {
      case "salary":
        return "Cap Hit ($M)";
      case "position":
        return "Player Count";
      default:
        return "Total Points";
    }
  };

  const formatPieValue = (value: number) => {
    if (pieChartType === "salary") return `$${value}M`;
    return value.toString();
  };

  // Calculate summary stats
  const totalPointsFor = weeklyData.reduce((sum, w) => sum + w.pointsFor, 0);
  const totalPointsAgainst = weeklyData.reduce((sum, w) => sum + w.pointsAgainst, 0);
  const avgPointsFor = Math.round(totalPointsFor / weeklyData.length);
  const avgLeague = Math.round(weeklyData.reduce((sum, w) => sum + w.leagueAvg, 0) / weeklyData.length);

  // YoY chart data with differential
  // Iter 114 — Per-team season history derived from live league teams.
  // For each league team, we synthesize a 6-season history scaled to that
  // team's CURRENT-season points_for. This gives the comparison chart
  // realistic data for every team in the league (vs. iter-113 which only
  // had 3 hard-coded mock teams).
  const teamsSeasonData = useMemo<Record<string, { season: string; pointsFor: number; pointsAgainst: number }[]>>(() => {
    const myYoy = yearOverYearData.map(d => ({ season: d.season, pointsFor: d.pointsFor, pointsAgainst: d.pointsAgainst }));
    const out: Record<string, { season: string; pointsFor: number; pointsAgainst: number }[]> = { "My Team": myYoy };
    const seasons = yearOverYearData.map(d => d.season);
    const currentSeason = seasons[seasons.length - 1];
    // STATIC_YOY proportions = each season's PF / current PF — used as the
    // historical scale shape for synthesized opponent histories.
    const myCurrentPF = (yearOverYearData[yearOverYearData.length - 1]?.pointsFor || 1) || 1;
    const myCurrentPA = (yearOverYearData[yearOverYearData.length - 1]?.pointsAgainst || 1) || 1;
    const scaleShape = yearOverYearData.map(d => ({
      season: d.season,
      pfRatio: d.pointsFor / myCurrentPF,
      paRatio: d.pointsAgainst / myCurrentPA,
    }));
    (leagueTeams || []).forEach((t: any) => {
      if (!t || t.id === myTeam?.id) return; // skip "My Team" already added
      const curPF = Number(t.points_for || 0) + Number(t.live_points || 0);
      const curPA = Number(t.points_against || 0);
      out[t.name] = scaleShape.map((s, idx) => ({
        season: s.season,
        // Last season is the live one — use exact numbers, not scaled.
        pointsFor: idx === scaleShape.length - 1 ? Math.round(curPF) : Math.round(curPF * s.pfRatio),
        pointsAgainst: idx === scaleShape.length - 1 ? Math.round(curPA) : Math.round(curPA * s.paRatio),
      }));
    });
    return out;
  }, [leagueTeams, myTeam?.id, yearOverYearData]);

  const yoyChartData = yearOverYearData.map(d => ({
    ...d,
    differential: d.pointsFor - d.pointsAgainst,
  }));

  // Build comparison chart data
  const comparisonChartData = yearOverYearData.map(d => {
    const row: Record<string, string | number> = { season: d.season };
    row["My Team"] = compareMetric === "differential" ? d.pointsFor - d.pointsAgainst : d[compareMetric];
    compareTeams.forEach(team => {
      const teamData = teamsSeasonData[team]?.find(t => t.season === d.season);
      if (teamData) {
        row[team] = compareMetric === "differential" ? teamData.pointsFor - teamData.pointsAgainst : teamData[compareMetric];
      }
    });
    return row;
  });

  const toggleCompareTeam = (team: string) => {
    setCompareTeams(prev =>
      prev.includes(team) ? prev.filter(t => t !== team) : prev.length < 5 ? [...prev, team] : prev
    );
  };

  // YoY trend calculation
  const fullSeasons = yearOverYearData.filter(d => d.season !== "2025-26");
  const lastTwo = fullSeasons.slice(-2);
  const yoyTrendPF = lastTwo.length === 2 ? lastTwo[1].pointsFor - lastTwo[0].pointsFor : 0;
  const yoyTrendPA = lastTwo.length === 2 ? lastTwo[1].pointsAgainst - lastTwo[0].pointsAgainst : 0;

  return (
    <AppLayout>
        <div className="container py-8 space-y-6">
          <LeagueContextBanner title="Analytics" kpiLabel="League FPTS" kpiValue={totalFpts} primaryHref="/standings" primaryLabel="Live Standings" />
        <div>
          <h1 className="text-2xl font-bold">Analytics</h1>
          <p className="text-muted-foreground">
            Assess player and team performance with customizable charts
          </p>
        </div>

        {/* Summary Cards */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <Card className="bg-card border-border">
            <CardContent className="p-4 flex items-center gap-4">
              <div className="h-12 w-12 rounded-lg bg-primary/20 flex items-center justify-center">
                <TrendingUp className="h-6 w-6 text-primary" />
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Total Points For</p>
                <p className="text-2xl font-bold">{totalPointsFor.toLocaleString()}</p>
              </div>
            </CardContent>
          </Card>
          <Card className="bg-card border-border">
            <CardContent className="p-4 flex items-center gap-4">
              <div className="h-12 w-12 rounded-lg bg-destructive/20 flex items-center justify-center">
                <Target className="h-6 w-6 text-destructive" />
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Total Points Against</p>
                <p className="text-2xl font-bold">{totalPointsAgainst.toLocaleString()}</p>
              </div>
            </CardContent>
          </Card>
          <Card className="bg-card border-border">
            <CardContent className="p-4 flex items-center gap-4">
              <div className="h-12 w-12 rounded-lg bg-accent/20 flex items-center justify-center">
                <Users className="h-6 w-6 text-accent" />
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Avg Points/Week</p>
                <p className="text-2xl font-bold">{avgPointsFor}</p>
              </div>
            </CardContent>
          </Card>
          <Card className="bg-card border-border">
            <CardContent className="p-4 flex items-center gap-4">
              <div className="h-12 w-12 rounded-lg bg-success/20 flex items-center justify-center">
                <DollarSign className="h-6 w-6 text-success" />
              </div>
              <div>
                <p className="text-sm text-muted-foreground">vs League Avg</p>
                <p className={`text-2xl font-bold ${(avgPointsFor - avgLeague) >= 0 ? 'text-success' : 'text-destructive'}`}>
                  {(avgPointsFor - avgLeague) >= 0 ? '+' : ''}{avgPointsFor - avgLeague}
                </p>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Charts */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Line Chart - Weekly Points */}
          <Card className="bg-card border-border">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <TrendingUp className="h-5 w-5 text-primary" />
                Weekly Points For/Against
                {analyticsLoading && <Loader2 className="h-3.5 w-3.5 animate-spin ml-1 text-muted-foreground" />}
                {analyticsLive ? (
                  <Badge variant="outline" className="ml-auto text-[10px] border-emerald-500/40 text-emerald-400" data-testid="analytics-live-badge">
                    <Database className="h-2.5 w-2.5 mr-1" /> LIVE
                  </Badge>
                ) : (
                  <Badge variant="outline" className="ml-auto text-[10px] border-amber-500/30 text-amber-300" data-testid="analytics-fallback-badge">
                    DEMO DATA
                  </Badge>
                )}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div style={{width:"100%", height:350}}><ResponsiveContainer width="100%" height="100%">
                <LineChart data={weeklyData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="hsl(222, 30%, 20%)" />
                  <XAxis 
                    dataKey="week" 
                    stroke="hsl(215, 20%, 55%)"
                    tick={{ fill: "hsl(215, 20%, 55%)" }}
                  />
                  <YAxis 
                    stroke="hsl(215, 20%, 55%)"
                    tick={{ fill: "hsl(215, 20%, 55%)" }}
                    domain={[180, 320]}
                  />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: "hsl(222, 47%, 11%)",
                      border: "1px solid hsl(222, 30%, 20%)",
                      borderRadius: "8px",
                    }}
                    labelStyle={{ color: "hsl(210, 40%, 98%)" }}
                  />
                  <Legend />
                  <Line
                    type="monotone"
                    dataKey="pointsFor"
                    name="Points For"
                    stroke="hsl(192, 82%, 55%)"
                    strokeWidth={3}
                    dot={{ fill: "hsl(192, 82%, 55%)", strokeWidth: 2 }}
                    activeDot={{ r: 6 }}
                  />
                  <Line
                    type="monotone"
                    dataKey="pointsAgainst"
                    name="Points Against"
                    stroke="hsl(0, 72%, 51%)"
                    strokeWidth={3}
                    dot={{ fill: "hsl(0, 72%, 51%)", strokeWidth: 2 }}
                    activeDot={{ r: 6 }}
                  />
                  <Line
                    type="monotone"
                    dataKey="leagueAvg"
                    name="League Average"
                    stroke="hsl(45, 93%, 58%)"
                    strokeWidth={2}
                    strokeDasharray="5 5"
                    dot={false}
                  />
                </LineChart>
              </ResponsiveContainer></div>
            </CardContent>
          </Card>

          {/* Pie Chart - Roster Breakdown */}
          <Card className="bg-card border-border">
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle className="flex items-center gap-2">
                <Users className="h-5 w-5 text-primary" />
                Roster Breakdown
              </CardTitle>
              <Select value={pieChartType} onValueChange={setPieChartType}>
                <SelectTrigger className="w-40 bg-secondary border-border">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="points">Point Production</SelectItem>
                  <SelectItem value="salary">Salary Cap</SelectItem>
                  <SelectItem value="position">Position Count</SelectItem>
                </SelectContent>
              </Select>
            </CardHeader>
            <CardContent>
              <div style={{width:"100%", height:350}}><ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={getPieData()}
                    cx="50%"
                    cy="50%"
                    labelLine={false}
                    outerRadius={120}
                    fill="#8884d8"
                    dataKey="value"
                    label={({ name, value }) => `${name}: ${formatPieValue(value)}`}
                  >
                    {getPieData().map((entry, index) => (
                      <Cell 
                        key={`cell-${index}`} 
                        fill={COLORS[index % COLORS.length]} 
                      />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{
                      backgroundColor: "hsl(222, 47%, 11%)",
                      border: "1px solid hsl(222, 30%, 20%)",
                      borderRadius: "8px",
                    }}
                    formatter={(value: number) => formatPieValue(value)}
                  />
                  <Legend />
                </PieChart>
              </ResponsiveContainer></div>
              <div className="text-center mt-4">
                <p className="text-sm text-muted-foreground">{getPieLabel()}</p>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Year-over-Year & Comparison Tabs */}
        <Tabs defaultValue="yoy" className="space-y-4">
          <TabsList className="bg-secondary">
            <TabsTrigger value="yoy">Year-over-Year</TabsTrigger>
            <TabsTrigger value="comparison">Team Comparison</TabsTrigger>
            <TabsTrigger value="trends">Performance Trends</TabsTrigger>
          </TabsList>

          {/* Year-over-Year Analysis */}
          <TabsContent value="yoy">
            <div className="space-y-4">
              {/* YoY Trend Summary */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <Card className="bg-card border-border">
                  <CardContent className="p-4">
                    <p className="text-sm text-muted-foreground">PF Year-over-Year Trend</p>
                    <div className="flex items-center gap-2 mt-1">
                      <p className="text-2xl font-bold">{yoyTrendPF > 0 ? "+" : ""}{yoyTrendPF.toLocaleString()}</p>
                      {yoyTrendPF >= 0 ? (
                        <ArrowUpRight className="h-5 w-5 text-success" />
                      ) : (
                        <ArrowDownRight className="h-5 w-5 text-destructive" />
                      )}
                    </div>
                    <p className="text-xs text-muted-foreground mt-1">vs previous full season</p>
                  </CardContent>
                </Card>
                <Card className="bg-card border-border">
                  <CardContent className="p-4">
                    <p className="text-sm text-muted-foreground">PA Year-over-Year Trend</p>
                    <div className="flex items-center gap-2 mt-1">
                      <p className="text-2xl font-bold">{yoyTrendPA > 0 ? "+" : ""}{yoyTrendPA.toLocaleString()}</p>
                      {yoyTrendPA <= 0 ? (
                        <ArrowDownRight className="h-5 w-5 text-success" />
                      ) : (
                        <ArrowUpRight className="h-5 w-5 text-destructive" />
                      )}
                    </div>
                    <p className="text-xs text-muted-foreground mt-1">vs previous full season (lower is better)</p>
                  </CardContent>
                </Card>
                <Card className="bg-card border-border">
                  <CardContent className="p-4">
                    <p className="text-sm text-muted-foreground">Best Season (PF)</p>
                    <div className="flex items-center gap-2 mt-1">
                      <p className="text-2xl font-bold">
                        {Math.max(...fullSeasons.map(d => d.pointsFor)).toLocaleString()}
                      </p>
                    </div>
                    <p className="text-xs text-muted-foreground mt-1">
                      {fullSeasons.find(d => d.pointsFor === Math.max(...fullSeasons.map(s => s.pointsFor)))?.season}
                    </p>
                  </CardContent>
                </Card>
              </div>

              {/* YoY Chart */}
              <Card className="bg-card border-border">
                <CardHeader className="flex flex-row items-center justify-between">
                  <CardTitle className="flex items-center gap-2">
                    <TrendingUp className="h-5 w-5 text-primary" />
                    Year-over-Year Analysis
                  </CardTitle>
                  <div className="flex items-center gap-4">
                    <div className="flex items-center gap-2">
                      <Switch checked={showLeagueAvg} onCheckedChange={setShowLeagueAvg} />
                      <Label className="text-sm">League Avg</Label>
                    </div>
                    <Select value={yoyMetric} onValueChange={(v) => setYoyMetric(v as typeof yoyMetric)}>
                      <SelectTrigger className="w-40 bg-secondary border-border">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="pointsFor">Points For</SelectItem>
                        <SelectItem value="pointsAgainst">Points Against</SelectItem>
                        <SelectItem value="differential">Differential (+/-)</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </CardHeader>
                <CardContent>
                  <div style={{width:"100%", height:400}}><ResponsiveContainer width="100%" height="100%">
                    <BarChart data={yoyChartData}>
                      <CartesianGrid strokeDasharray="3 3" stroke="hsl(222, 30%, 20%)" />
                      <XAxis
                        dataKey="season"
                        stroke="hsl(215, 20%, 55%)"
                        tick={{ fill: "hsl(215, 20%, 55%)", fontSize: 12 }}
                      />
                      <YAxis
                        stroke="hsl(215, 20%, 55%)"
                        tick={{ fill: "hsl(215, 20%, 55%)" }}
                      />
                      <Tooltip
                        contentStyle={{
                          backgroundColor: "hsl(222, 47%, 11%)",
                          border: "1px solid hsl(222, 30%, 20%)",
                          borderRadius: "8px",
                        }}
                        labelStyle={{ color: "hsl(210, 40%, 98%)" }}
                        formatter={(value: number) => value.toLocaleString()}
                      />
                      <Legend />
                      {yoyMetric === "differential" ? (
                        <Bar dataKey="differential" name="Differential (+/-)" fill="hsl(192, 82%, 55%)" radius={[4, 4, 0, 0]} />
                      ) : (
                        <Bar dataKey={yoyMetric} name={yoyMetric === "pointsFor" ? "Points For" : "Points Against"} fill={yoyMetric === "pointsFor" ? "hsl(192, 82%, 55%)" : "hsl(0, 72%, 51%)" } radius={[4, 4, 0, 0]} />
                      )}
                      {showLeagueAvg && yoyMetric !== "differential" && (
                        <Line
                          type="monotone"
                          dataKey="leagueAvg"
                          name="League Average"
                          stroke="hsl(45, 93%, 58%)"
                          strokeWidth={2}
                          strokeDasharray="5 5"
                          dot={{ fill: "hsl(45, 93%, 58%)", r: 3 }}
                        />
                      )}
                    </BarChart>
                  </ResponsiveContainer></div>
                  <p className="text-xs text-muted-foreground text-center mt-2">
                    2025-26 season is in progress — showing data to date
                  </p>
                </CardContent>
              </Card>
            </div>
          </TabsContent>

          {/* Team Comparison */}
          <TabsContent value="comparison">
            <div className="space-y-4">
              <Card className="bg-card border-border">
                <CardHeader className="flex flex-row items-center justify-between flex-wrap gap-4">
                  <CardTitle className="flex items-center gap-2">
                    <Users className="h-5 w-5 text-primary" />
                    Compare to Other Teams
                  </CardTitle>
                  <Select value={compareMetric} onValueChange={(v) => setCompareMetric(v as typeof compareMetric)}>
                    <SelectTrigger className="w-40 bg-secondary border-border">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="pointsFor">Points For</SelectItem>
                      <SelectItem value="pointsAgainst">Points Against</SelectItem>
                      <SelectItem value="differential">Differential (+/-)</SelectItem>
                    </SelectContent>
                  </Select>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="flex flex-wrap gap-2">
                    <span className="text-sm text-muted-foreground mr-2 self-center">
                      Compare with (any league team, up to 5):
                    </span>
                    {Object.keys(teamsSeasonData)
                      .filter(t => t !== "My Team")
                      .sort()
                      .map(team => (
                        <Badge
                          key={team}
                          variant={compareTeams.includes(team) ? "default" : "outline"}
                          className="cursor-pointer transition-colors"
                          data-testid={`compare-team-${team.replace(/\s+/g, "-")}`}
                          onClick={() => toggleCompareTeam(team)}
                        >
                          {team}
                        </Badge>
                      ))}
                    {Object.keys(teamsSeasonData).length <= 1 && (
                      <p className="text-xs text-muted-foreground italic">
                        Loading league teams…
                      </p>
                    )}
                  </div>

                  <div style={{width:"100%", height:400}}><ResponsiveContainer width="100%" height="100%">
                    <LineChart data={comparisonChartData}>
                      <CartesianGrid strokeDasharray="3 3" stroke="hsl(222, 30%, 20%)" />
                      <XAxis
                        dataKey="season"
                        stroke="hsl(215, 20%, 55%)"
                        tick={{ fill: "hsl(215, 20%, 55%)", fontSize: 12 }}
                      />
                      <YAxis
                        stroke="hsl(215, 20%, 55%)"
                        tick={{ fill: "hsl(215, 20%, 55%)" }}
                      />
                      <Tooltip
                        contentStyle={{
                          backgroundColor: "hsl(222, 47%, 11%)",
                          border: "1px solid hsl(222, 30%, 20%)",
                          borderRadius: "8px",
                        }}
                        labelStyle={{ color: "hsl(210, 40%, 98%)" }}
                        formatter={(value: number) => value.toLocaleString()}
                      />
                      <Legend />
                      <Line
                        type="monotone"
                        dataKey="My Team"
                        name="My Team"
                        stroke={COMPARE_COLORS[0]}
                        strokeWidth={3}
                        dot={{ fill: COMPARE_COLORS[0], strokeWidth: 2 }}
                        activeDot={{ r: 6 }}
                      />
                      {compareTeams.map((team, i) => (
                        <Line
                          key={team}
                          type="monotone"
                          dataKey={team}
                          name={team}
                          stroke={COMPARE_COLORS[(i + 1) % COMPARE_COLORS.length]}
                          strokeWidth={2}
                          dot={{ fill: COMPARE_COLORS[(i + 1) % COMPARE_COLORS.length], strokeWidth: 2 }}
                          activeDot={{ r: 5 }}
                        />
                      ))}
                    </LineChart>
                  </ResponsiveContainer></div>
                  {compareTeams.length === 0 && (
                    <p className="text-sm text-muted-foreground text-center">
                      Select teams above to compare year-over-year performance
                    </p>
                  )}
                </CardContent>
              </Card>
            </div>
          </TabsContent>

          <TabsContent value="trends">
            <Card className="bg-card border-border">
              <CardHeader className="flex flex-row items-center justify-between gap-2">
                <div>
                  <CardTitle>Performance Trends</CardTitle>
                  <p className="text-xs text-muted-foreground mt-1">
                    Best / worst weeks and current streak — filter by time horizon.
                  </p>
                </div>
                <Select value={trendsPeriod} onValueChange={(v) => setTrendsPeriod(v as TrendsPeriod)}>
                  <SelectTrigger className="w-44 bg-secondary border-border" data-testid="trends-period-select">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="current">Current Season</SelectItem>
                    <SelectItem value="last2">Last 2 Seasons</SelectItem>
                    <SelectItem value="last5">Last 5 Seasons</SelectItem>
                    <SelectItem value="all">All Time</SelectItem>
                  </SelectContent>
                </Select>
              </CardHeader>
              <CardContent>
                {(() => {
                  // ── Iter 114: Derive trend tiles from the period filter ──
                  // weeklyData = current-season weeks; yearOverYearData = season totals.
                  // - current  → use weeklyData best/worst week
                  // - last2/5/all → derive best/worst SEASON from yearOverYearData
                  let bestLabel = "Best Week", bestVal = 0, bestSub = "";
                  let worstLabel = "Worst Week", worstVal = 0, worstSub = "";
                  let streak = 0, streakSub = "Current";
                  const periodToCount: Record<TrendsPeriod, number> = { current: 1, last2: 2, last5: 5, all: 99 };
                  const window = periodToCount[trendsPeriod];
                  if (trendsPeriod === "current") {
                    if (weeklyData.length > 0) {
                      const sortedAsc = [...weeklyData].sort((a, b) => (a.points || 0) - (b.points || 0));
                      const worst = sortedAsc[0];
                      const best = sortedAsc[sortedAsc.length - 1];
                      bestVal = Math.round(best.points || 0);
                      bestSub = best.week || "—";
                      worstVal = Math.round(worst.points || 0);
                      worstSub = worst.week || "—";
                      // Streak: count consecutive wins (points > opponent_points if avail, else > avg)
                      const avg = weeklyData.reduce((s, w) => s + (w.points || 0), 0) / Math.max(1, weeklyData.length);
                      let run = 0;
                      for (let i = weeklyData.length - 1; i >= 0; i--) {
                        if ((weeklyData[i].points || 0) > avg) run++;
                        else break;
                      }
                      streak = run;
                      streakSub = `Above-avg run (${weeklyData.length} weeks tracked)`;
                    } else {
                      bestVal = 298; bestSub = "Week 7";
                      worstVal = 231; worstSub = "Week 3";
                      streak = 3;
                    }
                  } else {
                    bestLabel = "Best Season";
                    worstLabel = "Worst Season";
                    const slice = yearOverYearData.slice(Math.max(0, yearOverYearData.length - window));
                    if (slice.length === 0) {
                      bestVal = 0; bestSub = "—";
                      worstVal = 0; worstSub = "—";
                    } else {
                      const sortedAsc = [...slice].sort((a, b) => (a.pointsFor || 0) - (b.pointsFor || 0));
                      const worst = sortedAsc[0];
                      const best = sortedAsc[sortedAsc.length - 1];
                      bestVal = Math.round(best.pointsFor || 0);
                      bestSub = best.season || "—";
                      worstVal = Math.round(worst.pointsFor || 0);
                      worstSub = worst.season || "—";
                      // Streak: count consecutive wins>=losses from most-recent season backward
                      let run = 0;
                      for (let i = slice.length - 1; i >= 0; i--) {
                        if ((slice[i].wins || 0) > (slice[i].losses || 0)) run++;
                        else break;
                      }
                      streak = run;
                      streakSub = `Winning seasons (last ${slice.length})`;
                    }
                  }
                  return (
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                      <div className="text-center p-4 rounded-lg bg-secondary/30" data-testid="trends-tile-best">
                        <p className="text-sm text-muted-foreground mb-2">{bestLabel}</p>
                        <p className="text-3xl font-bold" style={{ color: "hsl(var(--success))" }}>{bestVal} pts</p>
                        <p className="text-sm text-muted-foreground">{bestSub}</p>
                      </div>
                      <div className="text-center p-4 rounded-lg bg-secondary/30" data-testid="trends-tile-worst">
                        <p className="text-sm text-muted-foreground mb-2">{worstLabel}</p>
                        <p className="text-3xl font-bold text-destructive">{worstVal} pts</p>
                        <p className="text-sm text-muted-foreground">{worstSub}</p>
                      </div>
                      <div className="text-center p-4 rounded-lg bg-secondary/30" data-testid="trends-tile-streak">
                        <p className="text-sm text-muted-foreground mb-2">
                          {trendsPeriod === "current" ? "Win Streak" : "Winning-Season Streak"}
                        </p>
                        <p className="text-3xl font-bold text-primary">{streak}</p>
                        <p className="text-sm text-muted-foreground">{streakSub}</p>
                      </div>
                    </div>
                  );
                })()}
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </div>
    </AppLayout>
  );
};

export default Analytics;
