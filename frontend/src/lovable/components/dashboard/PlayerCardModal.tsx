// @ts-nocheck
import { useState, useEffect } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  Newspaper,
  BarChart3,
  Calendar,
  ArrowRightLeft,
  Users,
  TrendingUp,
  TrendingDown,
  Minus,
  Repeat,
} from "lucide-react";
import {
  BarChart,
  Bar,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
  Legend,
} from "recharts";
import { getPlayerAccolades, awardWinnersData, type PlayerAccolade } from "@/lovable/data/playerAwardsData";

// ── Types (shared with PlayerRoster) ───────────────────

interface Contract {
  salary: number;
  yearsRemaining: number;
  type: "RFA" | "UFA" | "ELC" | "Signed";
}

interface PlayerGame {
  date: string;
  opponent: string;
  played: boolean;
  goals?: number;
  assists?: number;
  pts?: number;
}

interface PlayerCategoryBreakdown {
  G: number;
  A: number;
  PPP: number;
  SOG: number;
  HIT: number;
  BLK: number;
  PIM: number;
  "+/-": number;
  [key: string]: number;
}

interface Player {
  id: number;
  name: string;
  position: string;
  team: string;
  points: number;
  dynastyValue: number;
  trend: "up" | "down" | "stable";
  age: number;
  contract: Contract;
  rosterSection: string;
  statsByPeriod: Record<string, number>;
  categoryBreakdown: PlayerCategoryBreakdown;
  matchupGames: number;
  schedule: PlayerGame[];
}

// ── Mock data generators ───────────────────────────────

const categories = ["G", "A", "PPP", "SOG", "HIT", "BLK", "PIM", "+/-"];

const categoryLabels: Record<string, string> = {
  G: "Goals",
  A: "Assists",
  PPP: "Power Play Pts",
  SOG: "Shots on Goal",
  HIT: "Hits",
  BLK: "Blocked Shots",
  PIM: "Penalty Min",
  "+/-": "Plus/Minus",
};

const generatePlayerNews = (name: string) => [
  {
    date: "Feb 15, 2026",
    headline: `${name} scores twice in dominant win`,
    source: "NHL.com",
    summary: `${name} recorded two goals and an assist in a commanding 5-2 victory, extending their point streak to seven games.`,
  },
  {
    date: "Feb 12, 2026",
    headline: `${name} named to All-Star roster`,
    source: "ESPN",
    summary: `The league announced ${name} has been selected as an All-Star for the upcoming midseason showcase.`,
  },
  {
    date: "Feb 8, 2026",
    headline: `${name} returns from minor injury`,
    source: "TSN",
    summary: `After missing two games with a lower-body injury, ${name} is back in the lineup and expected to play tonight.`,
  },
];

const generateCareerStats = (player: Player) => {
  const seasons = [];
  const startYear = 2026 - (player.age - 18);
  for (let y = startYear; y <= 2025; y++) {
    const gp = 60 + Math.floor(Math.random() * 23);
    const g = Math.floor(player.categoryBreakdown.G * (0.5 + Math.random() * 0.7));
    const a = Math.floor(player.categoryBreakdown.A * (0.5 + Math.random() * 0.7));
    seasons.push({
      season: `${y}-${(y + 1).toString().slice(-2)}`,
      team: player.team,
      GP: gp,
      G: g,
      A: a,
      PTS: g + a,
      PPP: Math.floor(player.categoryBreakdown.PPP * (0.4 + Math.random() * 0.8)),
      SOG: Math.floor(player.categoryBreakdown.SOG * (0.6 + Math.random() * 0.5)),
      HIT: Math.floor(player.categoryBreakdown.HIT * (0.5 + Math.random() * 0.7)),
      BLK: Math.floor(player.categoryBreakdown.BLK * (0.5 + Math.random() * 0.7)),
      PIM: Math.floor(player.categoryBreakdown.PIM * (0.4 + Math.random() * 0.8)),
      "+/-": Math.floor((Math.random() - 0.3) * 40),
      FPTS: 0,
    });
    seasons[seasons.length - 1].FPTS =
      seasons[seasons.length - 1].G * 6 +
      seasons[seasons.length - 1].A * 4 +
      seasons[seasons.length - 1].PPP * 2 +
      Math.floor(seasons[seasons.length - 1].SOG * 0.5) +
      seasons[seasons.length - 1].HIT +
      seasons[seasons.length - 1].BLK;
  }
  return seasons;
};

const mockTransactions = (name: string) => [
  { date: "Oct 1, 2025", type: "Signed", detail: `${name} signed to starting roster` },
  { date: "Sep 15, 2025", type: "Drafted", detail: `${name} drafted in Round 1, Pick 3` },
  { date: "Mar 10, 2025", type: "Traded", detail: `${name} acquired from Ice Dragons` },
];

const mockFantasyTransactions = (name: string) => [
  { date: "Jan 20, 2026", type: "Lineup", detail: `${name} moved to starting roster from bench` },
  { date: "Dec 5, 2025", type: "IR", detail: `${name} placed on IR (lower body)` },
  { date: "Nov 12, 2025", type: "Add", detail: `${name} claimed off waivers` },
];

const mockLeagueMovements = (name: string) => [
  { date: "Jan 25, 2026", type: "Traded" as const, detail: `${name} traded from Frozen Fury to Team Frostbite for a 2nd round pick`, team: "Team Frostbite" },
  { date: "Dec 10, 2025", type: "Kept" as const, detail: `${name} kept as a keeper selection (Round 3 cost)`, team: "Frozen Fury" },
  { date: "Oct 3, 2025", type: "Added" as const, detail: `${name} added from free agency`, team: "Frozen Fury" },
  { date: "Sep 28, 2025", type: "Dropped" as const, detail: `${name} dropped to waivers`, team: "Northern Lights" },
  { date: "Sep 15, 2025", type: "Drafted" as const, detail: `${name} drafted in Round 1, Pick 3`, team: "Northern Lights" },
  { date: "Mar 10, 2025", type: "Traded" as const, detail: `${name} traded from Ice Dragons to Northern Lights in a 3-team deal`, team: "Northern Lights" },
  { date: "Oct 5, 2024", type: "Added" as const, detail: `${name} claimed off waivers`, team: "Ice Dragons" },
  { date: "Sep 20, 2024", type: "Dropped" as const, detail: `${name} dropped to free agency`, team: "Snow Storm" },
  { date: "Sep 1, 2024", type: "Drafted" as const, detail: `${name} drafted in Round 4, Pick 8`, team: "Snow Storm" },
];

const movementTypeConfig: Record<string, { color: string; icon: string }> = {
  Traded: { color: "bg-primary/15 text-primary border-primary/30", icon: "↔" },
  Added: { color: "bg-success/15 text-success border-success/30", icon: "+" },
  Dropped: { color: "bg-destructive/15 text-destructive border-destructive/30", icon: "−" },
  Kept: { color: "bg-accent/15 text-accent border-accent/30", icon: "★" },
  Drafted: { color: "bg-secondary text-secondary-foreground border-border", icon: "🎯" },
};

const mockOwnership = () => [
  { league: "Dynasty Kings", owner: "Team Frostbite", status: "Rostered" },
  { league: "Hockey Legends", owner: "Northern Lights", status: "Rostered" },
  { league: "Puck Masters", owner: "Free Agent", status: "Available" },
  { league: "Ice Breakers", owner: "Snow Storm", status: "Rostered" },
];

// ── Helpers ────────────────────────────────────────────

const formatSalary = (salary: number) => `$${(salary / 1000000).toFixed(1)}M`;

const getContractTypeColor = (type: Contract["type"]) => {
  switch (type) {
    case "ELC": return "bg-success/20 text-success";
    case "RFA": return "bg-accent/20 text-accent";
    case "UFA": return "bg-destructive/20 text-destructive";
    case "Signed": return "bg-primary/20 text-primary";
    default: return "bg-secondary text-secondary-foreground";
  }
};

// ── Player Accolades Badges ────────────────────────────

const PlayerAccoladesBadges = ({ playerName }: { playerName: string }) => {
  const accolades = getPlayerAccolades(playerName, awardWinnersData);
  if (accolades.length === 0) return null;
  return (
    <div className="flex items-center gap-1.5 mt-1.5 flex-wrap">
      {accolades.map((a) => (
        <TooltipProvider key={a.type}>
          <Tooltip>
            <TooltipTrigger asChild>
              <span className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded-md bg-primary/10 border border-primary/20 text-xs cursor-default">
                <span>{a.emoji}</span>
                {a.count > 1 && <span className="font-semibold text-primary">x{a.count}</span>}
              </span>
            </TooltipTrigger>
            <TooltipContent>
              <p>{a.type}{a.count > 1 ? ` (${a.count}x)` : ""}</p>
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>
      ))}
    </div>
  );
};

// ── Main Component ─────────────────────────────────────

interface PlayerCardModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  player: Player;
  defaultTab?: string;
}

const PlayerCardModal = ({ open, onOpenChange, player, defaultTab = "overview" }: PlayerCardModalProps) => {
  const [sideTab, setSideTab] = useState(defaultTab);
  useEffect(() => { if (open) setSideTab(defaultTab); }, [open, defaultTab]);
  const [chartCategory, setChartCategory] = useState("G");
  const [chartType, setChartType] = useState<"season" | "career">("career");

  const news = generatePlayerNews(player.name);
  const careerStats = generateCareerStats(player);
  const last10Games = player.schedule.filter((g) => g.played).slice(-10);
  const next5Games = player.schedule.filter((g) => !g.played).slice(0, 5);

  const sideMenuItems = [
    { id: "overview", label: "Overview", icon: Newspaper },
    { id: "season-stats", label: "Season Stats", icon: BarChart3 },
    { id: "career-stats", label: "Career Stats", icon: TrendingUp },
    { id: "transactions", label: "Transactions", icon: ArrowRightLeft },
    { id: "league-movements", label: "League Movements", icon: Repeat },
    { id: "fantasy-transactions", label: "Fantasy Transactions", icon: Calendar },
    { id: "ownership", label: "Ownership", icon: Users },
  ];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-5xl max-h-[85vh] p-0 gap-0 overflow-hidden">
        {/* Header */}
        <div className="p-6 pb-4 border-b border-border bg-secondary/20">
          <DialogHeader>
            <div className="flex items-center gap-4">
              <div className="h-14 w-14 rounded-xl bg-gradient-to-br from-primary/30 to-secondary flex items-center justify-center text-lg font-bold text-primary">
                {player.team}
              </div>
              <div className="flex-1">
                <DialogTitle className="text-xl font-bold">{player.name}</DialogTitle>
                <div className="flex items-center gap-2 mt-1 flex-wrap">
                  <Badge variant="outline" className="text-xs">
                    {player.position}
                  </Badge>
                  <span className="text-sm text-muted-foreground">{player.team}</span>
                  <span className="text-sm text-muted-foreground">• Age {player.age}</span>
                  <Badge className={`text-xs ${getContractTypeColor(player.contract.type)}`}>
                    {player.contract.type}
                  </Badge>
                  <span className="text-sm font-semibold text-accent">
                    {formatSalary(player.contract.salary)}
                  </span>
                  <span className="text-xs text-muted-foreground">
                    ({player.contract.yearsRemaining}yr)
                  </span>
                </div>
                <PlayerAccoladesBadges playerName={player.name} />
              </div>
              <div className="text-right">
                <p className="text-2xl font-bold text-primary">{player.points}</p>
                <p className="text-xs text-muted-foreground">Fantasy Points</p>
              </div>
            </div>
          </DialogHeader>
        </div>

        {/* Body: Side Nav + Content */}
        <div className="flex h-[calc(85vh-120px)]">
          {/* Side Nav */}
          <div className="w-48 border-r border-border bg-secondary/10 py-2 flex-shrink-0">
            {sideMenuItems.map((item) => {
              const Icon = item.icon;
              return (
                <button
                  key={item.id}
                  onClick={() => setSideTab(item.id)}
                  className={`w-full flex items-center gap-2 px-4 py-2.5 text-sm transition-colors text-left ${
                    sideTab === item.id
                      ? "bg-primary/10 text-primary border-r-2 border-primary font-medium"
                      : "text-muted-foreground hover:text-foreground hover:bg-secondary/30"
                  }`}
                >
                  <Icon className="h-4 w-4 flex-shrink-0" />
                  <span className="truncate">{item.label}</span>
                </button>
              );
            })}
          </div>

          {/* Content Area */}
          <ScrollArea className="flex-1">
            <div className="p-6">
              {sideTab === "overview" && (
                <OverviewTab
                  player={player}
                  news={news}
                  last10Games={last10Games}
                  next5Games={next5Games}
                />
              )}
              {sideTab === "season-stats" && (
                <SeasonStatsTab player={player} />
              )}
              {sideTab === "career-stats" && (
                <CareerStatsTab
                  player={player}
                  careerStats={careerStats}
                  chartCategory={chartCategory}
                  setChartCategory={setChartCategory}
                  chartType={chartType}
                  setChartType={setChartType}
                />
              )}
              {sideTab === "transactions" && (
                <TransactionsTab name={player.name} />
              )}
              {sideTab === "league-movements" && (
                <LeagueMovementsTab name={player.name} />
              )}
              {sideTab === "fantasy-transactions" && (
                <FantasyTransactionsTab name={player.name} />
              )}
              {sideTab === "ownership" && <OwnershipTab />}
            </div>
          </ScrollArea>
        </div>
      </DialogContent>
    </Dialog>
  );
};

// ── Overview Tab ───────────────────────────────────────

const OverviewTab = ({
  player,
  news,
  last10Games,
  next5Games,
}: {
  player: Player;
  news: ReturnType<typeof generatePlayerNews>;
  last10Games: PlayerGame[];
  next5Games: PlayerGame[];
}) => (
  <div className="space-y-6">
    {/* Latest News */}
    <div>
      <h4 className="text-sm font-semibold mb-3 flex items-center gap-2">
        <Newspaper className="h-4 w-4 text-primary" />
        Latest News
      </h4>
      <div className="space-y-3">
        {news.map((item, i) => (
          <div
            key={i}
            className="p-3 rounded-lg bg-secondary/20 border border-border/50"
          >
            <div className="flex items-center justify-between mb-1">
              <span className="text-sm font-medium">{item.headline}</span>
              <span className="text-xs text-muted-foreground">{item.date}</span>
            </div>
            <p className="text-xs text-muted-foreground">{item.summary}</p>
            <span className="text-[10px] text-primary mt-1 inline-block">
              {item.source}
            </span>
          </div>
        ))}
      </div>
    </div>

    {/* Season Stat Line */}
    <div>
      <h4 className="text-sm font-semibold mb-3 flex items-center gap-2">
        <BarChart3 className="h-4 w-4 text-primary" />
        Season Stats
      </h4>
      <div className="grid grid-cols-4 sm:grid-cols-8 gap-2">
        {categories.map((cat) => (
          <div
            key={cat}
            className="text-center p-2 rounded-lg bg-secondary/20 border border-border/50"
          >
            <p className="text-[10px] text-muted-foreground uppercase">{cat}</p>
            <p className="text-lg font-bold text-foreground">
              {player.categoryBreakdown[cat]}
            </p>
          </div>
        ))}
      </div>
    </div>

    {/* Last 10 Games */}
    <div>
      <h4 className="text-sm font-semibold mb-3">Last 10 Games</h4>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border bg-secondary/30">
              <th className="text-left p-2 text-xs text-muted-foreground">Date</th>
              <th className="text-center p-2 text-xs text-muted-foreground">OPP</th>
              <th className="text-center p-2 text-xs text-muted-foreground">G</th>
              <th className="text-center p-2 text-xs text-muted-foreground">A</th>
              <th className="text-center p-2 text-xs text-muted-foreground">PTS</th>
            </tr>
          </thead>
          <tbody>
            {last10Games.map((g, i) => (
              <tr
                key={i}
                className="border-b border-border/30 hover:bg-secondary/10"
              >
                <td className="p-2 text-xs text-muted-foreground">{g.date}</td>
                <td className="p-2 text-center text-xs font-medium">{g.opponent}</td>
                <td className="p-2 text-center">{g.goals}</td>
                <td className="p-2 text-center">{g.assists}</td>
                <td className="p-2 text-center font-semibold text-primary">
                  {g.pts}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>

    {/* Next 5 Games */}
    <div>
      <h4 className="text-sm font-semibold mb-3 flex items-center gap-2">
        <Calendar className="h-4 w-4 text-primary" />
        Next 5 Games
      </h4>
      <div className="flex gap-2">
        {next5Games.map((g, i) => (
          <div
            key={i}
            className="flex-1 text-center p-3 rounded-lg bg-secondary/20 border border-border/50"
          >
            <p className="text-[10px] text-muted-foreground">{g.date}</p>
            <p className="text-sm font-bold mt-1">{g.opponent}</p>
          </div>
        ))}
      </div>
    </div>
  </div>
);

// ── Season Stats Tab ───────────────────────────────────

const SeasonStatsTab = ({ player }: { player: Player }) => {
  const periods = ["1d", "7d", "14d", "30d", "60d", "100d", "season"] as const;
  return (
    <div className="space-y-6">
      <h4 className="text-sm font-semibold">Points by Time Period</h4>
      <div className="grid grid-cols-4 sm:grid-cols-7 gap-2">
        {periods.map((p) => (
          <div
            key={p}
            className="text-center p-3 rounded-lg bg-secondary/20 border border-border/50"
          >
            <p className="text-[10px] text-muted-foreground uppercase">{p}</p>
            <p className="text-lg font-bold text-primary">
              {player.statsByPeriod[p] ?? 0}
            </p>
          </div>
        ))}
      </div>

      <h4 className="text-sm font-semibold">Category Breakdown</h4>
      <div className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            data={categories.map((cat) => ({
              category: cat,
              value: player.categoryBreakdown[cat],
            }))}
          >
            <CartesianGrid strokeDasharray="3 3" stroke="hsl(222 30% 20%)" />
            <XAxis dataKey="category" stroke="hsl(215 20% 55%)" fontSize={12} />
            <YAxis stroke="hsl(215 20% 55%)" fontSize={12} />
            <RechartsTooltip
              contentStyle={{
                backgroundColor: "hsl(222 47% 11%)",
                border: "1px solid hsl(222 30% 20%)",
                borderRadius: "8px",
                color: "hsl(210 40% 98%)",
              }}
            />
            <Bar dataKey="value" fill="hsl(192 82% 55%)" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};

// ── Career Stats Tab ───────────────────────────────────

const CareerStatsTab = ({
  player,
  careerStats,
  chartCategory,
  setChartCategory,
  chartType,
  setChartType,
}: {
  player: Player;
  careerStats: ReturnType<typeof generateCareerStats>;
  chartCategory: string;
  setChartCategory: (c: string) => void;
  chartType: "season" | "career";
  setChartType: (t: "season" | "career") => void;
}) => (
  <div className="space-y-6">
    {/* Career Table */}
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border bg-secondary/30">
            <th className="text-left p-2 text-xs text-muted-foreground">Season</th>
            <th className="text-center p-2 text-xs text-muted-foreground">Team</th>
            <th className="text-center p-2 text-xs text-muted-foreground">GP</th>
            {categories.map((cat) => (
              <th
                key={cat}
                className="text-center p-2 text-xs text-muted-foreground"
              >
                {cat}
              </th>
            ))}
            <th className="text-center p-2 text-xs text-muted-foreground">PTS</th>
            <th className="text-center p-2 text-xs text-muted-foreground font-bold text-primary">
              FPTS
            </th>
          </tr>
        </thead>
        <tbody>
          {careerStats.map((s, i) => (
            <tr
              key={i}
              className="border-b border-border/30 hover:bg-secondary/10"
            >
              <td className="p-2 text-xs font-medium">{s.season}</td>
              <td className="p-2 text-center text-xs">{s.team}</td>
              <td className="p-2 text-center">{s.GP}</td>
              {categories.map((cat) => (
                <td key={cat} className="p-2 text-center">
                  {s[cat as keyof typeof s]}
                </td>
              ))}
              <td className="p-2 text-center font-medium">{s.PTS}</td>
              <td className="p-2 text-center font-bold text-primary">{s.FPTS}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>

    {/* Interactive Chart */}
    <Card className="border-border">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm">Career Trend</CardTitle>
          <div className="flex gap-2">
            <Select value={chartCategory} onValueChange={setChartCategory}>
              <SelectTrigger className="w-[120px] h-8 text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {categories.map((cat) => (
                  <SelectItem key={cat} value={cat}>
                    {categoryLabels[cat]}
                  </SelectItem>
                ))}
                <SelectItem value="PTS">Points</SelectItem>
                <SelectItem value="FPTS">Fantasy Pts</SelectItem>
              </SelectContent>
            </Select>
            <Select
              value={chartType}
              onValueChange={(v) => setChartType(v as "season" | "career")}
            >
              <SelectTrigger className="w-[110px] h-8 text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="career">By Season</SelectItem>
                <SelectItem value="season">This Season</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            {chartType === "career" ? (
              <LineChart data={careerStats}>
                <CartesianGrid
                  strokeDasharray="3 3"
                  stroke="hsl(222 30% 20%)"
                />
                <XAxis
                  dataKey="season"
                  stroke="hsl(215 20% 55%)"
                  fontSize={11}
                  angle={-30}
                  textAnchor="end"
                  height={50}
                />
                <YAxis stroke="hsl(215 20% 55%)" fontSize={12} />
                <RechartsTooltip
                  contentStyle={{
                    backgroundColor: "hsl(222 47% 11%)",
                    border: "1px solid hsl(222 30% 20%)",
                    borderRadius: "8px",
                    color: "hsl(210 40% 98%)",
                  }}
                />
                <Line
                  type="monotone"
                  dataKey={chartCategory}
                  stroke="hsl(192 82% 55%)"
                  strokeWidth={2}
                  dot={{ fill: "hsl(192 82% 55%)", r: 4 }}
                  activeDot={{ r: 6 }}
                />
              </LineChart>
            ) : (
              <BarChart
                data={player.schedule
                  .filter((g) => g.played)
                  .slice(-20)
                  .map((g) => ({
                    date: g.date.slice(5),
                    [chartCategory]:
                      chartCategory === "G"
                        ? g.goals
                        : chartCategory === "A"
                        ? g.assists
                        : g.pts,
                  }))}
              >
                <CartesianGrid
                  strokeDasharray="3 3"
                  stroke="hsl(222 30% 20%)"
                />
                <XAxis
                  dataKey="date"
                  stroke="hsl(215 20% 55%)"
                  fontSize={10}
                  angle={-45}
                  textAnchor="end"
                  height={50}
                />
                <YAxis stroke="hsl(215 20% 55%)" fontSize={12} />
                <RechartsTooltip
                  contentStyle={{
                    backgroundColor: "hsl(222 47% 11%)",
                    border: "1px solid hsl(222 30% 20%)",
                    borderRadius: "8px",
                    color: "hsl(210 40% 98%)",
                  }}
                />
                <Bar
                  dataKey={chartCategory}
                  fill="hsl(45 93% 58%)"
                  radius={[4, 4, 0, 0]}
                />
              </BarChart>
            )}
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  </div>
);

// ── Transactions Tab ───────────────────────────────────

const TransactionsTab = ({ name }: { name: string }) => {
  const transactions = mockTransactions(name);
  return (
    <div className="space-y-3">
      <h4 className="text-sm font-semibold">Transaction History</h4>
      {transactions.map((t, i) => (
        <div
          key={i}
          className="flex items-center gap-3 p-3 rounded-lg bg-secondary/20 border border-border/50"
        >
          <ArrowRightLeft className="h-4 w-4 text-primary flex-shrink-0" />
          <div className="flex-1">
            <p className="text-sm font-medium">{t.detail}</p>
            <p className="text-xs text-muted-foreground">{t.date}</p>
          </div>
          <Badge variant="outline" className="text-xs">
            {t.type}
          </Badge>
        </div>
      ))}
    </div>
  );
};

// ── League Movements Tab ───────────────────────────────

const LeagueMovementsTab = ({ name }: { name: string }) => {
  const movements = mockLeagueMovements(name);
  return (
    <div className="space-y-4">
      <h4 className="text-sm font-semibold flex items-center gap-2">
        <Repeat className="h-4 w-4 text-primary" />
        League Movement History
      </h4>
      <p className="text-xs text-muted-foreground">
        A timeline of how this player has moved through the league — trades, adds, drops, keeper selections, and draft picks.
      </p>
      <div className="relative">
        {/* Timeline line */}
        <div className="absolute left-[19px] top-4 bottom-4 w-px bg-border" />
        <div className="space-y-0">
          {movements.map((m, i) => {
            const config = movementTypeConfig[m.type] || movementTypeConfig.Added;
            return (
              <div key={i} className="flex items-start gap-3 py-3 relative">
                {/* Timeline dot */}
                <div className={`h-10 w-10 rounded-full flex items-center justify-center text-sm font-bold flex-shrink-0 border ${config.color} z-10 bg-background`}>
                  {config.icon}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <Badge variant="outline" className={`text-xs border ${config.color}`}>
                      {m.type}
                    </Badge>
                    <span className="text-xs text-muted-foreground">{m.date}</span>
                  </div>
                  <p className="text-sm mt-1">{m.detail}</p>
                  <p className="text-xs text-muted-foreground mt-0.5">→ {m.team}</p>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};



const FantasyTransactionsTab = ({ name }: { name: string }) => {
  const transactions = mockFantasyTransactions(name);
  return (
    <div className="space-y-3">
      <h4 className="text-sm font-semibold">Fantasy Transaction History</h4>
      {transactions.map((t, i) => (
        <div
          key={i}
          className="flex items-center gap-3 p-3 rounded-lg bg-secondary/20 border border-border/50"
        >
          <Calendar className="h-4 w-4 text-accent flex-shrink-0" />
          <div className="flex-1">
            <p className="text-sm font-medium">{t.detail}</p>
            <p className="text-xs text-muted-foreground">{t.date}</p>
          </div>
          <Badge variant="outline" className="text-xs">
            {t.type}
          </Badge>
        </div>
      ))}
    </div>
  );
};

// ── Ownership Tab ──────────────────────────────────────

const OwnershipTab = () => {
  const ownership = mockOwnership();
  return (
    <div className="space-y-3">
      <h4 className="text-sm font-semibold">Ownership Across Leagues</h4>
      {ownership.map((o, i) => (
        <div
          key={i}
          className="flex items-center justify-between p-3 rounded-lg bg-secondary/20 border border-border/50"
        >
          <div>
            <p className="text-sm font-medium">{o.league}</p>
            <p className="text-xs text-muted-foreground">{o.owner}</p>
          </div>
          <Badge
            variant="outline"
            className={`text-xs ${
              o.status === "Available"
                ? "border-success text-success"
                : "border-primary text-primary"
            }`}
          >
            {o.status}
          </Badge>
        </div>
      ))}
    </div>
  );
};

export default PlayerCardModal;
