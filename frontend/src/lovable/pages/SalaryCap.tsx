// @ts-nocheck
import { AppLayout } from "@/components/layout/AppLayout";
import { useActiveLeague } from "@/hooks/use-active-league";
import LeagueContextBanner from "@/lovable/components/dashboard/LeagueContextBanner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { DollarSign, TrendingUp, TrendingDown, AlertTriangle } from "lucide-react";
import { PieChart, Pie, Cell, ResponsiveContainer, Legend, Tooltip } from "recharts";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useState } from "react";

interface Contract {
  id: number;
  player: string;
  position: string;
  team: string;
  salary: number;
  yearsRemaining: number;
  status: "active" | "expiring" | "ir";
}

interface RetainedSalary {
  id: number;
  player: string;
  tradedTo: string;
  retainedAmount: number;
  yearsRemaining: number;
}

const contracts: Contract[] = [
  { id: 1, player: "Connor McDavid", position: "C", team: "EDM", salary: 12500000, yearsRemaining: 3, status: "active" },
  { id: 2, player: "Nathan MacKinnon", position: "C", team: "COL", salary: 10600000, yearsRemaining: 4, status: "active" },
  { id: 3, player: "Cale Makar", position: "D", team: "COL", salary: 9000000, yearsRemaining: 5, status: "active" },
  { id: 4, player: "Nikita Kucherov", position: "RW", team: "TBL", salary: 8500000, yearsRemaining: 1, status: "expiring" },
  { id: 5, player: "Auston Matthews", position: "C", team: "TOR", salary: 11640000, yearsRemaining: 2, status: "active" },
  { id: 6, player: "Igor Shesterkin", position: "G", team: "NYR", salary: 5667000, yearsRemaining: 2, status: "ir" },
];

const retainedSalaries: RetainedSalary[] = [
  { id: 1, player: "Tyler Seguin", tradedTo: "DAL", retainedAmount: 1500000, yearsRemaining: 2 },
  { id: 2, player: "P.K. Subban", tradedTo: "NJD", retainedAmount: 1000000, yearsRemaining: 1 },
];

const capLimit = 82500000;
const currentSpending = contracts.reduce((sum, c) => sum + c.salary, 0);
const totalRetained = retainedSalaries.reduce((sum, r) => sum + r.retainedAmount, 0);
const deadCap = 2500000;
const capSpace = capLimit - currentSpending - deadCap - totalRetained;

type ChartFilter = "all" | "players" | "position";

const CHART_COLORS = [
  "hsl(var(--primary))",
  "hsl(var(--chart-2))",
  "hsl(var(--chart-3))",
  "hsl(var(--chart-4))",
  "hsl(var(--chart-5))",
  "hsl(210, 70%, 50%)",
  "hsl(280, 60%, 55%)",
  "hsl(30, 80%, 50%)",
];

const CAP_SPACE_COLOR = "hsl(var(--success))";
const DEAD_CAP_COLOR = "hsl(var(--accent))";
const RETAINED_COLOR = "hsl(var(--destructive))";

const SalaryCap = () => {
  const { league, leagueTeams } = useActiveLeague();
  const leagueTeamsCount = leagueTeams?.length || 0;
  const totalFpts = Math.round((leagueTeams || []).reduce((a, t) => a + ((t.points_for || 0) + (t.live_points || 0)), 0));
  const pendingTradesCount = 0; // wired in follow-up
  const pendingClaimsCount = 0;

  const [chartFilter, setChartFilter] = useState<ChartFilter>("all");
  const capUsagePercent = ((currentSpending + deadCap + totalRetained) / capLimit) * 100;

  const getChartData = () => {
    switch (chartFilter) {
      case "players":
        const playerData = contracts.map((c, index) => ({
          name: c.player,
          value: c.salary,
          color: CHART_COLORS[index % CHART_COLORS.length],
        }));
        if (totalRetained > 0) {
          playerData.push({ name: "Retained Salary", value: totalRetained, color: RETAINED_COLOR });
        }
        if (deadCap > 0) {
          playerData.push({ name: "Dead Cap", value: deadCap, color: DEAD_CAP_COLOR });
        }
        playerData.push({ name: "Cap Space", value: capSpace, color: CAP_SPACE_COLOR });
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
        if (totalRetained > 0) {
          posData.push({ name: "Retained Salary", value: totalRetained, color: RETAINED_COLOR });
        }
        if (deadCap > 0) {
          posData.push({ name: "Dead Cap", value: deadCap, color: DEAD_CAP_COLOR });
        }
        posData.push({ name: "Cap Space", value: capSpace, color: CAP_SPACE_COLOR });
        return posData;

      default:
        const allData = [
          { name: "Player Salaries", value: currentSpending, color: "hsl(var(--primary))" },
        ];
        if (totalRetained > 0) {
          allData.push({ name: "Retained Salary", value: totalRetained, color: RETAINED_COLOR });
        }
        if (deadCap > 0) {
          allData.push({ name: "Dead Cap", value: deadCap, color: DEAD_CAP_COLOR });
        }
        allData.push({ name: "Cap Space", value: capSpace, color: CAP_SPACE_COLOR });
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
          <Card className="bg-card border-border">
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

          <Card className="bg-card border-border">
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

          <Card className="bg-card border-border">
            <CardContent className="p-6">
              <div className="flex items-center gap-3 mb-3">
                <div className="h-10 w-10 rounded-lg bg-success/20 flex items-center justify-center">
                  <TrendingDown className="h-5 w-5 text-success" />
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Cap Space</p>
                  <p className="text-xl font-bold text-success">${(capSpace / 1000000).toFixed(1)}M</p>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card className="bg-card border-border">
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

        {/* Salary Cap Pie Chart */}
        <Card className="bg-card border-border">
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>Cap Breakdown</CardTitle>
            <Select value={chartFilter} onValueChange={(value: ChartFilter) => setChartFilter(value)}>
              <SelectTrigger className="w-[180px]">
                <SelectValue placeholder="Filter by..." />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Overview</SelectItem>
                <SelectItem value="players">By Player</SelectItem>
                <SelectItem value="position">By Position</SelectItem>
              </SelectContent>
            </Select>
          </CardHeader>
          <CardContent>
            <div className="h-[350px]">
              <ResponsiveContainer width="100%" height="100%">
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
                      <Cell key={`cell-${index}`} fill={entry.color} />
                    ))}
                  </Pie>
                  <Tooltip
                    formatter={(value: number) => formatCurrency(value)}
                    contentStyle={{
                      backgroundColor: "hsl(var(--card))",
                      border: "1px solid hsl(var(--border))",
                      borderRadius: "8px",
                    }}
                  />
                  <Legend
                    verticalAlign="bottom"
                    height={36}
                    formatter={(value) => <span className="text-sm text-foreground">{value}</span>}
                  />
                </PieChart>
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
                  <div className="h-3 w-3 rounded-full bg-primary"></div>
                  <span className="text-muted-foreground">Active Contracts</span>
                </div>
                {totalRetained > 0 && (
                  <div className="flex items-center gap-2">
                    <div className="h-3 w-3 rounded-full bg-destructive"></div>
                    <span className="text-muted-foreground">Retained Salary</span>
                  </div>
                )}
                <div className="flex items-center gap-2">
                  <div className="h-3 w-3 rounded-full bg-accent"></div>
                  <span className="text-muted-foreground">Dead Cap</span>
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
                  <TableHead className="text-center">Years Left</TableHead>
                  <TableHead className="text-center">Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {contracts.map((contract) => (
                  <TableRow key={contract.id} className="border-border">
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
                    <TableCell className="text-center">
                      <span className={contract.yearsRemaining <= 1 ? "text-accent font-medium" : ""}>
                        {contract.yearsRemaining} {contract.yearsRemaining === 1 ? "year" : "years"}
                      </span>
                    </TableCell>
                    <TableCell className="text-center">
                      <Badge 
                        variant={
                          contract.status === "active" ? "outline" :
                          contract.status === "expiring" ? "default" : "destructive"
                        }
                        className={
                          contract.status === "active" ? "bg-success/20 text-success border-success/30" :
                          contract.status === "expiring" ? "bg-accent/20 text-accent border-accent/30" :
                          ""
                        }
                      >
                        {contract.status === "ir" ? "IR" : contract.status.charAt(0).toUpperCase() + contract.status.slice(1)}
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
