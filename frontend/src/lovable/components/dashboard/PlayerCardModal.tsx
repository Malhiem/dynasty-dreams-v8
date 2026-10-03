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
  ExternalLink,
  Sprout,
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
import api from "@/lib/api";
import { useDailyScoring } from "@/hooks/use-daily-scoring";
import { PlayerDailyAccordion } from "@/components/daily-scoring";

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
  Trade: { color: "bg-primary/15 text-primary border-primary/30", icon: "↔" },
  Added: { color: "bg-success/15 text-success border-success/30", icon: "+" },
  Add: { color: "bg-success/15 text-success border-success/30", icon: "+" },
  Dropped: { color: "bg-destructive/15 text-destructive border-destructive/30", icon: "−" },
  Drop: { color: "bg-destructive/15 text-destructive border-destructive/30", icon: "−" },
  Release: { color: "bg-destructive/15 text-destructive border-destructive/30", icon: "−" },
  Kept: { color: "bg-accent/15 text-accent border-accent/30", icon: "★" },
  Drafted: { color: "bg-secondary text-secondary-foreground border-border", icon: "🎯" },
  Draft: { color: "bg-secondary text-secondary-foreground border-border", icon: "🎯" },
  Waiver: { color: "bg-accent/15 text-accent border-accent/30", icon: "⏳" },
  Lineup: { color: "bg-muted text-muted-foreground border-border", icon: "⇄" },
  Admin: { color: "bg-muted text-muted-foreground border-border", icon: "⚙" },
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
  scoringConfig?: any;
  leagueId?: string;
  teamId?: string;
}

const CAT_TO_CFG_KEY: Record<string, string> = {
  G: "goals", A: "assists", PPG: "power_play_goals", PPP: "power_play_points",
  SHG: "short_handed_goals", SHP: "short_handed_points", GWG: "game_winning_goals",
  SOG: "shots", HIT: "hits", BLK: "blocked_shots", PIM: "penalty_minutes", "+/-": "plus_minus",
  W: "wins", L: "losses", SV: "saves", GA: "goals_against", SO: "shutouts", OTL: "overtime_losses",
};

const PlayerCardModal = ({ open, onOpenChange, player, defaultTab = "overview", scoringConfig, leagueId, teamId }: PlayerCardModalProps) => {
  const [sideTab, setSideTab] = useState(defaultTab);
  useEffect(() => { if (open) setSideTab(defaultTab); }, [open, defaultTab]);
  const [chartCategory, setChartCategory] = useState("G");
  const [chartType, setChartType] = useState<"season" | "career">("career");

  // ── Daily scoring for this player ──
  const { data: dailyScoringData } = useDailyScoring(
    open ? leagueId : undefined,
    open ? teamId : undefined
  );
  const playerDailyData = dailyScoringData?.players?.find(
    (p) => p.name === player.name || p.id === (player as any).id
  );
  const dayLabelMap: Record<string, string> = {};
  if (dailyScoringData) {
    dailyScoringData.days.forEach((d, i) => {
      dayLabelMap[d] = dailyScoringData.day_labels[i];
    });
  }

  // ── Real news + recent games (league-aware) ──
  // Falls back to the legacy mock generators if either endpoint errors out so
  // the modal never renders blank.
  const [liveNews, setLiveNews] = useState<any[] | null>(null);
  const [liveGames, setLiveGames] = useState<any[] | null>(null);
  useEffect(() => {
    if (!open || !(player as any).id) return;
    const pid = String((player as any).id);
    let cancelled = false;
    api.get(`/players/${pid}/news`, { params: { limit: 20 } })
      .then(({ data }) => { if (!cancelled) setLiveNews(data?.news || []); })
      .catch(() => { if (!cancelled) setLiveNews([]); });
    api.get(`/players/${pid}/recent-games`, { params: { limit: 10 } })
      .then(({ data }) => { if (!cancelled) setLiveGames(data?.games || []); })
      .catch(() => { if (!cancelled) setLiveGames([]); });
    return () => { cancelled = true; };
  }, [open, (player as any).id]);

  const news = (liveNews && liveNews.length > 0)
    ? liveNews.map((n) => ({
        date: n.published_at ? new Date(n.published_at).toLocaleDateString() : "",
        time: n.published_at ? new Date(n.published_at).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" }) : "",
        title: n.headline || n.title || "Update",
        snippet: n.summary || n.body || "",
        source: n.source || "Beat",
        tag: (n.signal || n.tag || "update").toString(),
      }))
    : generatePlayerNews(player.name);
  const careerStats = generateCareerStats(player);
  const last10Games = (liveGames && liveGames.length > 0)
    ? liveGames.slice(0, 10).map((g) => ({
        date: g.date || "",
        opponent: g.opponent || "—",
        played: true,
        goals: g.goals ?? 0,
        assists: g.assists ?? 0,
        ppp: g.ppp ?? 0,
        shp: g.shp ?? 0,
        sog: g.shots ?? g.sog ?? 0,
        hits: g.hits ?? 0,
        blocks: g.blocks ?? 0,
        pim: g.pim ?? 0,
        plus_minus: g.plus_minus ?? 0,
        fpts: g.fantasy_points ?? g.fpts ?? 0,
        pts: g.points ?? ((g.goals ?? 0) + (g.assists ?? 0)),
      }))
    : player.schedule.filter((g) => g.played).slice(-10);
  const next5Games = player.schedule.filter((g) => !g.played).slice(0, 5);

  const sideMenuItems = [
    { id: "overview", label: "Overview", icon: Newspaper },
    { id: "news", label: "News", icon: Newspaper },
    { id: "daily-scoring", label: "Daily Scoring", icon: Calendar },
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
                <div className="flex items-center gap-2">
                  <DialogTitle className="text-xl font-bold">{player.name}</DialogTitle>
                  {/* Iter 153 — expand-to-full-page link (opens in a new tab) */}
                  {(player as any).id && (
                    <a
                      href={`/players/${(player as any).id}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 text-[11px] text-primary hover:text-primary/80 hover:underline"
                      data-testid="player-card-expand-link"
                      title="Open full player page in a new tab"
                    >
                      <ExternalLink className="h-3 w-3" />
                      Open full page
                    </a>
                  )}
                </div>
                <div className="flex items-center gap-2 mt-1 flex-wrap">
                  <Badge variant="outline" className="text-xs">
                    {player.position}
                  </Badge>
                  {/* Iter 173 — Show league + team they actually play for.
                      For NHL players that's "NHL · {team}"; for prospects
                      we surface the feeder league + their club (e.g.
                      "OHL · London Knights"). */}
                  <span className="text-sm text-muted-foreground" data-testid="player-card-affiliation">
                    {(() => {
                      const league = (player as any).league
                        || (player as any).amateurLeague
                        || (player as any).amateur_league
                        || "NHL";
                      const teamName = (player as any).teamName
                        || (player as any).team_name
                        || player.team;
                      return teamName && teamName !== league
                        ? `${league} · ${teamName}`
                        : (league || player.team);
                    })()}
                  </span>
                  {/* Iter 173 — Minor-league-eligible badge. Surfaces only
                      when the active league has minors_enabled and the
                      player is a prospect (or explicitly minor_eligible). */}
                  {((player as any).minor_eligible || (player as any).player_type === "prospect") && (
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <Badge
                          variant="outline"
                          className="text-[10px] border-emerald-400/40 text-emerald-300 bg-emerald-500/10 gap-1"
                          data-testid="player-card-minor-eligible"
                        >
                          <Sprout className="h-3 w-3" />
                          Minor-eligible
                        </Badge>
                      </TooltipTrigger>
                      <TooltipContent>
                        Can be slotted into your roster's minors / farm system
                      </TooltipContent>
                    </Tooltip>
                  )}
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
                  scoringConfig={scoringConfig}
                  onSeeMoreNews={() => setSideTab("news")}
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
                <FantasyTransactionsTab playerId={(player as any).id} leagueId={leagueId} />
              )}
              {sideTab === "ownership" && <OwnershipTab playerId={(player as any).id} leagueId={leagueId} />}
              {sideTab === "news" && <NewsTab news={news} />}
              {sideTab === "daily-scoring" && (
                <DailyScoringTab
                  playerName={player.name}
                  isGoalie={player.position === "G"}
                  dailyData={playerDailyData}
                  dayLabelMap={dayLabelMap}
                />
              )}
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
  scoringConfig,
  onSeeMoreNews,
}: {
  player: Player;
  news: any[];
  last10Games: any[];
  next5Games: PlayerGame[];
  scoringConfig?: any;
  onSeeMoreNews?: () => void;
}) => {
  // Derive the displayed stat categories from the league scoring config when
  // available so the Last 10 Games + Season Stats columns reflect what the
  // league actually scores (e.g. SHP / GWG / FOW). Falls back to the default
  // 8-category set used by Season Stats.
  const isGoalieOv = (player as any).position === "G" || (player as any).player_type === "goalie";
  const cfgKeyToCat: Record<string, string> = {
    goals: "G", assists: "A", power_play_points: "PPP", short_handed_points: "SHP",
    power_play_goals: "PPG", short_handed_goals: "SHG", game_winning_goals: "GWG",
    shots: "SOG", hits: "HIT", blocked_shots: "BLK", penalty_minutes: "PIM",
    plus_minus: "+/-", faceoff_wins: "FOW",
    wins: "W", losses: "L", saves: "SV", goals_against: "GA", shutouts: "SO",
    overtime_losses: "OTL",
  };
  const liveCategories: string[] = (() => {
    const cfg = (isGoalieOv ? scoringConfig?.goalie_scoring : scoringConfig?.skater_scoring) || null;
    if (!cfg) return categories;
    const out: string[] = [];
    Object.entries(cfg).forEach(([k, v]) => {
      const cat = cfgKeyToCat[k];
      if (cat && typeof v === "number" && v !== 0 && !out.includes(cat)) out.push(cat);
    });
    return out.length > 0 ? out : categories;
  })();
  return (
  <div className="space-y-6">
    {/* Season Stat Line — moved to top per UX request */}
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

    {/* Latest News — single most-recent item, click "More news" → News tab */}
    <div data-testid="player-card-latest-news">
      <div className="flex items-center justify-between mb-3">
        <h4 className="text-sm font-semibold flex items-center gap-2">
          <Newspaper className="h-4 w-4 text-primary" />
          Latest News
        </h4>
        {news.length > 1 && (
          <button
            type="button"
            data-testid="player-card-more-news-btn"
            onClick={onSeeMoreNews}
            className="text-xs text-primary hover:underline"
          >
            More news →
          </button>
        )}
      </div>
      {news.length === 0 ? (
        <div className="p-3 rounded-lg bg-secondary/20 border border-border/50 text-xs text-muted-foreground italic">
          No recent news for this player.
        </div>
      ) : (
        <div className="p-3 rounded-lg bg-secondary/20 border border-border/50" data-testid="player-card-latest-news-item">
          <div className="flex items-center justify-between mb-1">
            <span className="text-sm font-medium">{(news[0] as any).title || (news[0] as any).headline}</span>
            <span className="text-xs text-muted-foreground">
              {(news[0] as any).date}{(news[0] as any).time ? ` · ${(news[0] as any).time}` : ""}
            </span>
          </div>
          <p className="text-xs text-muted-foreground">
            {(news[0] as any).snippet || (news[0] as any).summary}
          </p>
          <span className="text-[10px] text-primary mt-1 inline-block">
            {(news[0] as any).source}
          </span>
        </div>
      )}
    </div>

    {/* Fantasy Points Breakdown */}
    {(() => {
      const isGoalie = (player as any).position === "G" || (player as any).player_type === "goalie";
      const cfg = (isGoalie ? scoringConfig?.goalie_scoring : scoringConfig?.skater_scoring) || {};
      const rows = categories
        .map((cat) => {
          const count = Number(player.categoryBreakdown[cat] ?? 0);
          const w = cfg[CAT_TO_CFG_KEY[cat]];
          if (typeof w !== "number" || count === 0) return null;
          const pts = +(count * w).toFixed(1);
          return { cat, count, w, pts };
        })
        .filter(Boolean) as { cat: string; count: number; w: number; pts: number }[];
      const totalPositive = rows.filter(r => r.pts > 0).reduce((s, r) => s + r.pts, 0);
      const totalNegative = rows.filter(r => r.pts < 0).reduce((s, r) => s + r.pts, 0);
      if (!scoringConfig || rows.length === 0) return null;
      return (
        <div data-testid="player-card-fp-breakdown">
          <h4 className="text-sm font-semibold mb-3 flex items-center gap-2">
            <BarChart3 className="h-4 w-4 text-emerald-400" />
            Fantasy Points Breakdown
            <span className="text-[10px] text-muted-foreground font-normal ml-1">(per league scoring)</span>
          </h4>
          <div className="rounded-lg border border-border/50 overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-secondary/30">
                <tr>
                  <th className="text-left p-2 text-[10px] uppercase tracking-wider text-muted-foreground font-medium">Category</th>
                  <th className="text-right p-2 text-[10px] uppercase tracking-wider text-muted-foreground font-medium">Count</th>
                  <th className="text-right p-2 text-[10px] uppercase tracking-wider text-muted-foreground font-medium">×</th>
                  <th className="text-right p-2 text-[10px] uppercase tracking-wider text-muted-foreground font-medium">Per</th>
                  <th className="text-right p-2 text-[10px] uppercase tracking-wider text-muted-foreground font-medium">Points</th>
                </tr>
              </thead>
              <tbody>
                {rows.map(r => (
                  <tr key={r.cat} className="border-t border-border/30" data-testid={`fp-breakdown-row-${r.cat}`}>
                    <td className="p-2">
                      <span className="text-sm font-medium">{r.cat}</span>
                      <span className="text-[10px] text-muted-foreground ml-2">{categoryLabels[r.cat] || r.cat}</span>
                    </td>
                    <td className="p-2 text-right tabular-nums">{r.count}</td>
                    <td className="p-2 text-right text-muted-foreground">×</td>
                    <td className="p-2 text-right tabular-nums text-muted-foreground">{r.w}</td>
                    <td className={`p-2 text-right tabular-nums font-semibold ${r.pts >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                      {r.pts > 0 ? `+${r.pts}` : r.pts}
                    </td>
                  </tr>
                ))}
                <tr className="border-t-2 border-border bg-secondary/20" data-testid="fp-breakdown-total">
                  <td className="p-2 font-semibold" colSpan={4}>Total Fantasy Points</td>
                  <td className="p-2 text-right tabular-nums font-bold text-primary text-base">
                    {(totalPositive + totalNegative).toFixed(1)}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      );
    })()}

    {/* Last 10 Games — full category table matching league scoring categories
         dynamically (POS · Date · OPP · FPTS · {league cats}). Falls back to
         the default 8-category set when no scoringConfig is provided. */}
    <div data-testid="player-card-last10">
      <h4 className="text-sm font-semibold mb-3">Last 10 Games</h4>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border bg-secondary/30">
              <th className="text-left p-2 text-xs text-muted-foreground">Date</th>
              <th className="text-center p-2 text-xs text-muted-foreground">OPP</th>
              <th className="text-right p-2 text-xs text-muted-foreground">FPTS</th>
              {liveCategories.map((cat) => (
                <th key={cat} className="text-center p-2 text-xs text-muted-foreground">{cat}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {last10Games.length === 0 && (
              <tr>
                <td colSpan={3 + liveCategories.length} className="p-4 text-center text-xs text-muted-foreground italic">
                  No games played yet this season.
                </td>
              </tr>
            )}
            {last10Games.map((g, i) => {
              const valFor = (cat: string) => {
                const map: Record<string, any> = {
                  G: g.goals, A: g.assists,
                  PPP: g.ppp, SHP: g.shp, PPG: g.ppg, SHG: g.shg, GWG: g.gwg,
                  SOG: g.sog, HIT: g.hits, BLK: g.blocks,
                  PIM: g.pim, "+/-": g.plus_minus, FOW: g.fow,
                  W: g.wins, L: g.losses, SV: g.saves, GA: g.goals_against,
                  SO: g.shutouts, OTL: g.otl,
                };
                const v = map[cat];
                return v == null ? "—" : v;
              };
              return (
                <tr
                  key={i}
                  className="border-b border-border/30 hover:bg-secondary/10"
                  data-testid={`last10-row-${i}`}
                >
                  <td className="p-2 text-xs text-muted-foreground whitespace-nowrap">{g.date}</td>
                  <td className="p-2 text-center text-xs font-medium">{g.opponent}</td>
                  <td className="p-2 text-right font-semibold text-primary tabular-nums" data-testid={`last10-fpts-${i}`}>
                    {typeof g.fpts === "number" ? g.fpts.toFixed(1) : "—"}
                  </td>
                  {liveCategories.map((cat) => (
                    <td key={cat} className="p-2 text-center tabular-nums" data-testid={`last10-${cat}-${i}`}>
                      {valFor(cat)}
                    </td>
                  ))}
                </tr>
              );
            })}
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
};

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



const FantasyTransactionsTab = ({ playerId, leagueId }: { playerId?: string; leagueId?: string }) => {
  const [history, setHistory] = useState<any[]>([]);
  const [lineupHistory, setLineupHistory] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!playerId) { setLoading(false); return; }
    let cancelled = false;
    const fetchData = async () => {
      setLoading(true);
      try {
        const [ownerRes, lineupRes] = await Promise.all([
          api.get(`/players/${playerId}/ownership-history`, { params: { league_id: leagueId || "" } }).catch(() => ({ data: { history: [] } })),
          api.get(`/players/${playerId}/lineup-history`, { params: { league_id: leagueId || "", team_id: "" } }).catch(() => ({ data: { history: [] } })),
        ]);
        if (!cancelled) {
          setHistory(ownerRes.data?.history || []);
          setLineupHistory(lineupRes.data?.history || []);
        }
      } catch { /* fallback handled */ }
      if (!cancelled) setLoading(false);
    };
    fetchData();
    return () => { cancelled = true; };
  }, [playerId, leagueId]);

  // Merge ownership + lineup events into a unified timeline
  const events: { date: string; type: string; detail: string; team: string }[] = [];
  for (const h of history) {
    events.push({
      date: h.acquired_at ? new Date(h.acquired_at).toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric" }) : "—",
      type: (h.source || "add").charAt(0).toUpperCase() + (h.source || "add").slice(1),
      detail: `Acquired by ${h.team_name || "team"} via ${h.source || "unknown"}`,
      team: h.team_name || "—",
    });
    if (h.released_at) {
      events.push({
        date: new Date(h.released_at).toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric" }),
        type: (h.release_source || "release").charAt(0).toUpperCase() + (h.release_source || "release").slice(1),
        detail: `Released from ${h.team_name || "team"} via ${h.release_source || "release"}`,
        team: h.team_name || "—",
      });
    }
  }
  for (const l of lineupHistory) {
    events.push({
      date: l.started_at ? new Date(l.started_at).toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric" }) : "—",
      type: "Lineup",
      detail: `Moved to ${(l.position || "bench").toUpperCase()}`,
      team: "",
    });
  }
  // Sort newest first
  events.sort((a, b) => {
    const da = new Date(a.date).getTime() || 0;
    const db2 = new Date(b.date).getTime() || 0;
    return db2 - da;
  });

  if (loading) {
    return <div className="text-center text-muted-foreground py-12 text-sm">Loading transaction history...</div>;
  }

  return (
    <div className="space-y-3" data-testid="fantasy-transactions-tab">
      <h4 className="text-sm font-semibold flex items-center gap-2">
        <Calendar className="h-4 w-4 text-primary" />
        Fantasy Transaction History
      </h4>
      {events.length === 0 ? (
        <div className="p-3 rounded-lg bg-secondary/20 border border-border/50 text-xs text-muted-foreground italic">
          No transaction history recorded yet.
        </div>
      ) : (
        events.map((t, i) => {
          const config = movementTypeConfig[t.type] || movementTypeConfig.Added;
          return (
            <div key={i} className="flex items-center gap-3 p-3 rounded-lg bg-secondary/20 border border-border/50" data-testid={`fantasy-tx-${i}`}>
              <div className={`h-8 w-8 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0 border ${config.color} bg-background`}>
                {config.icon}
              </div>
              <div className="flex-1">
                <p className="text-sm font-medium">{t.detail}</p>
                <p className="text-xs text-muted-foreground">{t.date}</p>
              </div>
              <Badge variant="outline" className={`text-xs border ${config.color}`}>
                {t.type}
              </Badge>
            </div>
          );
        })
      )}
    </div>
  );
};

// ── News Tab ───────────────────────────────────────────
//
// Lists the player's news for the **current year only** (per UX request —
// older items are hidden so commissioners don't have to scroll past stale
// blurbs). News items missing a `date` are kept (we can't filter what we
// can't parse).

const NewsTab = ({ news }: { news: any[] }) => {
  const currentYear = new Date().getFullYear();
  const filtered = (news || []).filter((n: any) => {
    if (!n?.date) return true;
    const parsed = new Date(n.date);
    if (isNaN(parsed.getTime())) {
      // Fallback: try to extract a 4-digit year from a free-form string
      const m = String(n.date).match(/\b(20\d{2})\b/);
      return m ? Number(m[1]) === currentYear : true;
    }
    return parsed.getFullYear() === currentYear;
  });
  return (
    <div className="space-y-3" data-testid="player-card-news-tab">
      <div className="flex items-center justify-between">
        <h4 className="text-sm font-semibold flex items-center gap-2">
          <Newspaper className="h-4 w-4 text-primary" />
          News &mdash; {currentYear}
        </h4>
        <span className="text-[10px] text-muted-foreground">
          {filtered.length} item{filtered.length === 1 ? "" : "s"}
        </span>
      </div>
      {filtered.length === 0 ? (
        <div className="p-3 rounded-lg bg-secondary/20 border border-border/50 text-xs text-muted-foreground italic">
          No news items for {currentYear}.
        </div>
      ) : (
        filtered.map((n: any, i: number) => (
          <div
            key={i}
            className="p-3 rounded-lg bg-secondary/20 border border-border/50"
            data-testid={`news-tab-item-${i}`}
          >
            <div className="flex items-center justify-between gap-2 mb-1">
              <span className="text-sm font-medium">{n.title || n.headline}</span>
              <span className="text-xs text-muted-foreground whitespace-nowrap">
                {n.date}
                {n.time ? ` · ${n.time}` : ""}
              </span>
            </div>
            <p className="text-xs text-muted-foreground">{n.snippet || n.summary}</p>
            {n.source && (
              <span className="text-[10px] text-primary mt-1 inline-block">{n.source}</span>
            )}
          </div>
        ))
      )}
    </div>
  );
};

// ── Ownership Tab ──────────────────────────────────────

const OwnershipTab = ({ playerId, leagueId }: { playerId?: string; leagueId?: string }) => {
  const [history, setHistory] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!playerId) { setLoading(false); return; }
    let cancelled = false;
    api.get(`/players/${playerId}/ownership-history`, { params: { league_id: leagueId || "" } })
      .then(({ data }) => { if (!cancelled) setHistory(data?.history || []); })
      .catch(() => {})
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [playerId, leagueId]);

  if (loading) return <div className="text-center text-muted-foreground py-12 text-sm">Loading...</div>;

  // Build ownership periods: current vs past
  const current = history.find(h => !h.released_at);
  const past = history.filter(h => h.released_at);

  return (
    <div className="space-y-4" data-testid="ownership-tab">
      <h4 className="text-sm font-semibold flex items-center gap-2">
        <Users className="h-4 w-4 text-primary" />
        Ownership Timeline
      </h4>
      {current ? (
        <div className="flex items-center justify-between p-3 rounded-lg bg-primary/5 border border-primary/20">
          <div>
            <p className="text-sm font-medium">{current.team_name || "Unknown Team"}</p>
            <p className="text-xs text-muted-foreground">
              Since {current.acquired_at ? new Date(current.acquired_at).toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric" }) : "—"}
              {current.source ? ` (via ${current.source})` : ""}
            </p>
          </div>
          <Badge variant="outline" className="text-xs border-primary text-primary">Current</Badge>
        </div>
      ) : (
        <div className="p-3 rounded-lg bg-secondary/20 border border-border/50 text-xs text-muted-foreground italic">
          Not currently rostered in this league.
        </div>
      )}
      {past.length > 0 && (
        <>
          <p className="text-xs text-muted-foreground font-medium pt-1">Previous Owners</p>
          {past.map((h, i) => (
            <div key={i} className="flex items-center justify-between p-3 rounded-lg bg-secondary/20 border border-border/50">
              <div>
                <p className="text-sm font-medium">{h.team_name || "Unknown Team"}</p>
                <p className="text-xs text-muted-foreground">
                  {h.acquired_at ? new Date(h.acquired_at).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }) : "—"}
                  {" → "}
                  {h.released_at ? new Date(h.released_at).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }) : "—"}
                </p>
              </div>
              <Badge variant="outline" className="text-xs">
                {h.source || "—"} → {h.release_source || "—"}
              </Badge>
            </div>
          ))}
        </>
      )}
      {history.length === 0 && (
        <div className="p-3 rounded-lg bg-secondary/20 border border-border/50 text-xs text-muted-foreground italic">
          No ownership history recorded yet.
        </div>
      )}
    </div>
  );
};

// ── Daily Scoring Tab ──────────────────────────────────

const DailyScoringTab = ({
  playerName,
  isGoalie,
  dailyData,
  dayLabelMap,
}: {
  playerName: string;
  isGoalie: boolean;
  dailyData: any;
  dayLabelMap: Record<string, string>;
}) => {
  if (!dailyData || Object.keys(dailyData.daily || {}).length === 0) {
    return (
      <div className="text-center text-muted-foreground py-12 text-sm" data-testid="daily-scoring-tab-empty">
        <Calendar className="h-8 w-8 mx-auto mb-3 text-muted-foreground/40" />
        <p className="font-medium">No daily scoring data</p>
        <p className="text-xs mt-1">This player hasn't recorded any stats in the current matchup period yet.</p>
      </div>
    );
  }

  return (
    <div data-testid="daily-scoring-tab">
      <h3 className="text-lg font-semibold mb-4">Daily Scoring Breakdown</h3>
      <PlayerDailyAccordion
        playerName={playerName}
        isGoalie={isGoalie}
        daily={dailyData.daily}
        dayLabels={dayLabelMap}
        totalFpts={dailyData.total_fpts}
        className="mb-4"
      />
      {/* Summary stats */}
      <div className="grid grid-cols-3 gap-3 mt-4">
        <Card className="bg-secondary/20 border-border/50">
          <CardContent className="p-3 text-center">
            <p className="text-2xl font-bold text-primary tabular-nums">
              {dailyData.total_fpts.toFixed(1)}
            </p>
            <p className="text-[10px] text-muted-foreground uppercase tracking-wider">Total FPTS</p>
          </CardContent>
        </Card>
        <Card className="bg-secondary/20 border-border/50">
          <CardContent className="p-3 text-center">
            <p className="text-2xl font-bold tabular-nums">
              {dailyData.total_games}
            </p>
            <p className="text-[10px] text-muted-foreground uppercase tracking-wider">Games</p>
          </CardContent>
        </Card>
        <Card className="bg-secondary/20 border-border/50">
          <CardContent className="p-3 text-center">
            <p className="text-2xl font-bold tabular-nums">
              {dailyData.total_games > 0
                ? (dailyData.total_fpts / dailyData.total_games).toFixed(1)
                : "—"}
            </p>
            <p className="text-[10px] text-muted-foreground uppercase tracking-wider">FPTS / Game</p>
          </CardContent>
        </Card>
      </div>
      {/* Stat line summary */}
      <div className="mt-4 p-3 rounded-lg bg-secondary/20 border border-border/50">
        <p className="text-xs text-muted-foreground uppercase tracking-wider mb-2">Period Stat Line</p>
        {isGoalie ? (
          <p className="text-sm font-mono tabular-nums">
            {dailyData.total_wins}W · {dailyData.total_saves} SVS · {dailyData.total_goals_against} GA
          </p>
        ) : (
          <p className="text-sm font-mono tabular-nums">
            {dailyData.total_goals}G {dailyData.total_assists}A · {dailyData.total_shots} SOG
          </p>
        )}
      </div>
    </div>
  );
};

export default PlayerCardModal;
