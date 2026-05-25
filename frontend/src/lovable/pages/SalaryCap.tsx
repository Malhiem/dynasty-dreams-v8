// @ts-nocheck
import { AppLayout } from "@/components/layout/AppLayout";
import { useActiveLeague } from "@/hooks/use-active-league";
import LeagueContextBanner from "@/lovable/components/dashboard/LeagueContextBanner";
import api from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { DollarSign, TrendingUp, TrendingDown, AlertTriangle } from "lucide-react";
import {
  PieChart, Pie, Cell, ResponsiveContainer, Legend, Tooltip,
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
} from "recharts";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useState, useEffect, useMemo } from "react";

interface Contract {
  id: string;
  player: string;
  position: string;
  team: string;
  salary: number;
  yearsRemaining: number;
  totalYears: number;
  currentYear: number;
  endYear: number;
  endStatus: "UFA" | "RFA" | "ELC" | "Signed";
  status: "active" | "expiring" | "ir";
}

type ChartFilter = "all" | "players" | "position" | "by_year";

// Distinct, dark-mode-friendly hex palette — replaces the broken
// `hsl(var(--chart-2))` tokens that were resolving to empty/black on the
// off-black card background. Picked for visual contrast against `#000`-ish
// surface and clear separation when shown side-by-side in a legend.
const CHART_COLORS = [
  "#00D2FF", // cyan (matches --primary)
  "#FFB020", // gold (matches --accent)
  "#22C55E", // emerald
  "#A855F7", // violet
  "#F472B6", // pink
  "#3B82F6", // blue
  "#FB923C", // orange
  "#14B8A6", // teal
  "#EAB308", // yellow
  "#EF4444", // red
  "#8B5CF6", // purple-2
  "#06B6D4", // cyan-2
];

const CAP_SPACE_COLOR = "#34C759";   // bright emerald (was broken hsl(var(--success)))
const DEAD_CAP_COLOR = "#FFB020";    // gold/accent
const RETAINED_COLOR = "#FF3B30";    // red/destructive

const SalaryCap = () => {
  const { league, leagueTeams, myTeam } = useActiveLeague();
  const leagueTeamsCount = leagueTeams?.length || 0;
  const [chartFilter, setChartFilter] = useState<ChartFilter>("all");
  const [rosterDetail, setRosterDetail] = useState<any>(null);

  useEffect(() => {
    if (!myTeam?.id) return;
    let cancelled = false;
    api.get(`/roster/${myTeam.id}/detail`)
      .then(({ data }) => { if (!cancelled) setRosterDetail(data); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [myTeam?.id]);

  const contracts: Contract[] = useMemo(() => {
    if (!rosterDetail?.players) return [];
    return rosterDetail.players.map((p: any) => {
      const c = p.contract || {};
      const yearsRemaining = c.yearsRemaining || 1;
      const totalYears = c.total_years || yearsRemaining;
      const currentYear = c.current_year || Math.max(1, totalYears - yearsRemaining + 1);
      // Fallback when older backend response lacks the iter-110 fields.
      const fallbackEndYear = new Date().getFullYear() + Math.max(0, yearsRemaining - 1);
      const endYear = c.end_year || fallbackEndYear;
      const endStatus = c.end_status || (c.type === "ELC" ? "RFA" : (c.type || "UFA"));
      return {
        id: p.id,
        player: p.name,
        position: p.position,
        team: p.team,
        salary: c.salary || 0,
        yearsRemaining,
        totalYears,
        currentYear,
        endYear,
        endStatus,
        status: p.rosterSection === "ir"
          ? "ir"
          : ((c.type === "UFA" || yearsRemaining === 1) ? "expiring" : "active"),
      };
    });
  }, [rosterDetail]);

  const capLimit = Math.max(
    league?.salary_cap || 82_500_000,
    // Auto-scale to accommodate synthesized seed contracts (typical dynasty demo)
    Math.ceil(contracts.reduce((s, c) => s + c.salary, 0) / 5_000_000) * 5_000_000
  );
  const currentSpending = contracts.reduce((sum, c) => sum + c.salary, 0);
  const deadCap = 0; // not yet modelled in DB
  const totalRetained = 0;
  const retainedSalaries: any[] = [];
  const capSpace = capLimit - currentSpending - deadCap - totalRetained;
  const capUsagePercent = ((currentSpending + deadCap + totalRetained) / capLimit) * 100;

  // ── By-Year payload (iter 110) ─────────────────────────────────
  // For each of the next 5 NHL seasons, sum the salaries of players whose
  // contract still covers that year. Anything unsigned counts as `unsigned`
  // (rendered as the empty/cap-space portion) so users can see how much of
  // their cap is locked vs available year-over-year.
  const yearBreakdown = useMemo(() => {
    if (contracts.length === 0) return [];
    const minYear = Math.min(...contracts.map((c) => c.endYear - c.yearsRemaining + 1));
    const maxYear = Math.max(...contracts.map((c) => c.endYear));
    const start = Math.min(minYear, new Date().getFullYear());
    const end = Math.min(maxYear, start + 5); // cap at 6-year horizon
    const out: { year: number; locked: number; available: number; label: string }[] = [];
    for (let y = start; y <= end; y++) {
      const locked = contracts.reduce((sum, c) => {
        const contractStart = c.endYear - c.yearsRemaining + 1;
        return (y >= contractStart && y <= c.endYear) ? sum + c.salary : sum;
      }, 0);
      out.push({
        year: y,
        locked,
        available: Math.max(0, capLimit - locked),
        label: String(y),
      });
    }
    return out;
  }, [contracts, capLimit]);

  const getChartData = () => {
    switch (chartFilter) {
      case "players":
        const playerData = contracts.slice(0, 12).map((c, index) => ({
          name: c.player,
          value: c.salary,
          color: CHART_COLORS[index % CHART_COLORS.length],
        }));
        if (capSpace > 0) playerData.push({ name: "Cap Space", value: capSpace, color: CAP_SPACE_COLOR });
        return playerData;

      case "position":
        const positionGroups: Record<string, number> = {};
        contracts.forEach((c) => {
          positionGroups[c.position] = (positionGroups[c.position] || 0) + c.salary;
        });
        const posData = Object.entries(positionGroups).map(([pos, value], index) => ({
          name: pos,
          value,
          color: CHART_COLORS[index % CHART_COLORS.length],
        }));
        if (capSpace > 0) posData.push({ name: "Cap Space", value: capSpace, color: CAP_SPACE_COLOR });
        return posData;

      default:
        const allData: any[] = [
          { name: "Player Salaries", value: currentSpending, color: CHART_COLORS[0] },
        ];
        if (capSpace > 0) allData.push({ name: "Cap Space", value: capSpace, color: CAP_SPACE_COLOR });
        return allData;
    }
  };

  const chartData = getChartData();
  const formatCurrency = (value: number) => `$${(value / 1000000).toFixed(2)}M`;

  return (
    <AppLayout>
        <div className="container py-8 space-y-6">
          <LeagueContextBanner title="Salary Cap" kpiLabel="Teams on roster" kpiValue={leagueTeamsCount} primaryHref="/commissioner" primaryLabel="Manage in Commissioner" />
        <div>
          <h1 className="text-2xl font-bold">Salary Cap Management</h1>
          <p className="text-muted-foreground">Contracts, cap space, and roster management</p>
        </div>

        {/* Cap Overview Cards */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <Card className="bg-card border-border" data-testid="cap-overview-card-limit">
            <CardContent className="p-6">
              <div className="flex items-center gap-3 mb-3">
                <div className="h-10 w-10 rounded-lg bg-primary/20 flex items-center justify-center">
                  <DollarSign className="h-5 w-5 text-primary" />
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Salary Cap</p>
                  <p className="text-xl font-bold">${(capLimit / 1000000).toFixed(1)}M</p>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card className="bg-card border-border" data-testid="cap-overview-card-hit">
            <CardContent className="p-6">
              <div className="flex items-center gap-3 mb-3">
                <div className="h-10 w-10 rounded-lg bg-destructive/20 flex items-center justify-center">
                  <TrendingUp className="h-5 w-5 text-destructive" />
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Cap Hit</p>
                  <p className="text-xl font-bold">${(currentSpending / 1000000).toFixed(1)}M</p>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card className="bg-card border-border" data-testid="cap-overview-card-space">
            <CardContent className="p-6">
              <div className="flex items-center gap-3 mb-3">
                <div className="h-10 w-10 rounded-lg flex items-center justify-center" style={{ backgroundColor: "rgba(52, 199, 89, 0.18)" }}>
                  <TrendingDown className="h-5 w-5" style={{ color: CAP_SPACE_COLOR }} />
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Cap Space</p>
                  <p className="text-xl font-bold" style={{ color: CAP_SPACE_COLOR }}>${(capSpace / 1000000).toFixed(1)}M</p>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card className="bg-card border-border" data-testid="cap-overview-card-dead">
            <CardContent className="p-6">
              <div className="flex items-center gap-3 mb-3">
                <div className="h-10 w-10 rounded-lg bg-accent/20 flex items-center justify-center">
                  <AlertTriangle className="h-5 w-5 text-accent" />
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Dead Cap</p>
                  <p className="text-xl font-bold text-accent">${(deadCap / 1000000).toFixed(1)}M</p>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Salary Cap Chart — pie or by-year bar */}
        <Card className="bg-card border-border">
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>Cap Breakdown</CardTitle>
            <Select value={chartFilter} onValueChange={(value: ChartFilter) => setChartFilter(value)}>
              <SelectTrigger className="w-[180px]" data-testid="cap-chart-filter">
                <SelectValue placeholder="Filter by..." />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Overview</SelectItem>
                <SelectItem value="players">By Player</SelectItem>
                <SelectItem value="position">By Position</SelectItem>
                <SelectItem value="by_year">By Year</SelectItem>
              </SelectContent>
            </Select>
          </CardHeader>
          <CardContent>
            <div className="h-[350px]" data-testid="cap-chart-container">
              <ResponsiveContainer width="100%" height="100%">
                {chartFilter === "by_year" ? (
                  <BarChart data={yearBreakdown} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="hsl(222, 30%, 20%)" />
                    <XAxis dataKey="label" stroke="hsl(215, 20%, 65%)" tick={{ fill: "hsl(215, 20%, 75%)" }} />
                    <YAxis
                      stroke="hsl(215, 20%, 65%)"
                      tick={{ fill: "hsl(215, 20%, 75%)" }}
                      tickFormatter={(v) => `$${(v / 1_000_000).toFixed(0)}M`}
                    />
                    <Tooltip
                      formatter={(value: number, name: string) => [formatCurrency(value), name]}
                      contentStyle={{
                        backgroundColor: "hsl(var(--card))",
                        border: "1px solid hsl(var(--border))",
                        borderRadius: "8px",
                        color: "hsl(var(--foreground))",
                      }}
                      labelStyle={{ color: "hsl(var(--foreground))" }}
                    />
                    <Legend
                      verticalAlign="bottom"
                      height={36}
                      formatter={(value) => <span className="text-sm text-foreground">{value}</span>}
                    />
                    <Bar dataKey="locked" stackId="cap" name="Locked Salary" fill={CHART_COLORS[0]} radius={[0, 0, 0, 0]} />
                    <Bar dataKey="available" stackId="cap" name="Available (UFAs/RFAs unsigned)" fill={CAP_SPACE_COLOR} radius={[4, 4, 0, 0]} />
                  </BarChart>
                ) : (
                  <PieChart>
                    <Pie
                      data={chartData}
                      cx="50%"
                      cy="50%"
                      innerRadius={60}
                      outerRadius={120}
                      paddingAngle={2}
                      dataKey="value"
                      nameKey="name"
                      label={({ name, value }) => `${name}: ${formatCurrency(value)}`}
                      labelLine={false}
                    >
                      {chartData.map((entry, index) => (
                        <Cell key={`cell-${index}`} fill={entry.color} stroke="hsl(222, 30%, 12%)" strokeWidth={1} />
                      ))}
                    </Pie>
                    <Tooltip
                      formatter={(value: number) => formatCurrency(value)}
                      contentStyle={{
                        backgroundColor: "hsl(var(--card))",
                        border: "1px solid hsl(var(--border))",
                        borderRadius: "8px",
                        color: "hsl(var(--foreground))",
                      }}
                      labelStyle={{ color: "hsl(var(--foreground))" }}
                    />
                    <Legend
                      verticalAlign="bottom"
                      height={36}
                      formatter={(value) => <span className="text-sm text-foreground">{value}</span>}
                    />
                  </PieChart>
                )}
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>

        {/* Cap Usage Progress */}
        <Card className="bg-card border-border">
          <CardHeader>
            <CardTitle>Cap Usage</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Used: {capUsagePercent.toFixed(1)}%</span>
                <span className="text-muted-foreground">Available: {(100 - capUsagePercent).toFixed(1)}%</span>
              </div>
              <Progress
                value={capUsagePercent}
                className={`h-4 ${capUsagePercent > 95 ? "bg-destructive/20" : "bg-secondary"}`}
              />
              <div className="flex flex-wrap gap-4 text-sm">
                <div className="flex items-center gap-2">
                  <div className="h-3 w-3 rounded-full" style={{ backgroundColor: CHART_COLORS[0] }}></div>
                  <span className="text-muted-foreground">Active Contracts</span>
                </div>
                {totalRetained > 0 && (
                  <div className="flex items-center gap-2">
                    <div className="h-3 w-3 rounded-full" style={{ backgroundColor: RETAINED_COLOR }}></div>
                    <span className="text-muted-foreground">Retained Salary</span>
                  </div>
                )}
                <div className="flex items-center gap-2">
                  <div className="h-3 w-3 rounded-full" style={{ backgroundColor: DEAD_CAP_COLOR }}></div>
                  <span className="text-muted-foreground">Dead Cap</span>
                </div>
                <div className="flex items-center gap-2">
                  <div className="h-3 w-3 rounded-full" style={{ backgroundColor: CAP_SPACE_COLOR }}></div>
                  <span className="text-muted-foreground">Cap Space</span>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Retained Salary Table */}
        {retainedSalaries.length > 0 && (
          <Card className="bg-card border-border">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                Retained Salary
                <Badge variant="destructive" className="ml-2">
                  ${(totalRetained / 1000000).toFixed(2)}M
                </Badge>
              </CardTitle>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow className="border-border">
                    <TableHead>Player</TableHead>
                    <TableHead>Traded To</TableHead>
                    <TableHead className="text-right">Retained Amount</TableHead>
                    <TableHead className="text-center">Years Left</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {retainedSalaries.map((retained) => (
                    <TableRow key={retained.id} className="border-border">
                      <TableCell className="font-medium">{retained.player}</TableCell>
                      <TableCell>
                        <Badge variant="outline" className="bg-secondary/50">
                          {retained.tradedTo}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-right font-semibold text-destructive">
                        ${(retained.retainedAmount / 1000000).toFixed(2)}M
                      </TableCell>
                      <TableCell className="text-center">
                        {retained.yearsRemaining} {retained.yearsRemaining === 1 ? "year" : "years"}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        )}

        {/* Contracts Table */}
        <Card className="bg-card border-border">
          <CardHeader>
            <CardTitle>Active Contracts</CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow className="border-border">
                  <TableHead>Player</TableHead>
                  <TableHead className="text-center">POS</TableHead>
                  <TableHead className="text-right">Salary</TableHead>
                  <TableHead className="text-center">Year</TableHead>
                  <TableHead className="text-center">Contract Ends</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {contracts.map((contract) => (
                  <TableRow key={contract.id} className="border-border" data-testid={`contract-row-${contract.id}`}>
                    <TableCell>
                      <div className="flex items-center gap-3">
                        <div className="h-10 w-10 rounded-lg bg-secondary flex items-center justify-center text-xs font-bold">
                          {contract.team}
                        </div>
                        <div>
                          <p className="font-medium">{contract.player}</p>
                          <p className="text-xs text-muted-foreground">{contract.team}</p>
                        </div>
                      </div>
                    </TableCell>
                    <TableCell className="text-center">
                      <Badge variant="outline" className="bg-secondary/50">
                        {contract.position}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right font-semibold">
                      ${(contract.salary / 1000000).toFixed(2)}M
                    </TableCell>
                    <TableCell className="text-center" data-testid={`contract-year-${contract.id}`}>
                      <span className={contract.yearsRemaining <= 1 ? "text-accent font-medium" : "font-medium"}>
                        {contract.currentYear}/{contract.totalYears}
                      </span>
                    </TableCell>
                    <TableCell className="text-center" data-testid={`contract-ends-${contract.id}`}>
                      <Badge
                        variant="outline"
                        className={
                          contract.endStatus === "UFA"
                            ? "border-amber-500/40"
                            : contract.endStatus === "RFA"
                              ? "border-cyan-500/40"
                              : "border-border"
                        }
                        style={
                          contract.endStatus === "UFA"
                            ? { color: DEAD_CAP_COLOR, backgroundColor: "rgba(255, 176, 32, 0.12)" }
                            : contract.endStatus === "RFA"
                              ? { color: CHART_COLORS[0], backgroundColor: "rgba(0, 210, 255, 0.12)" }
                              : undefined
                        }
                      >
                        {contract.endStatus}/{contract.endYear}
                      </Badge>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      </div>
    </AppLayout>
  );
};

export default SalaryCap;
