// @ts-nocheck
import { useState, useMemo } from "react";
import { AppLayout } from "@/components/layout/AppLayout";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
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
import { Search, UserPlus, Users, Calendar } from "lucide-react";

// ─── Types ───────────────────────────────────────────────────────────────────

interface PlayerCategoryBreakdown {
  G: number; A: number; PPP: number; SHP: number; SOG: number;
  HIT: number; BLK: number; FOW: number; FOL: number;
  W: number; L: number; SOL: number; SV: number; GA: number; SO: number;
  [key: string]: number;
}

interface Player {
  id: number;
  name: string;
  position: string;
  team: string;
  age: number;
  salary: number;
  categoryBreakdown: PlayerCategoryBreakdown;
  totalFpts: number;
  owned?: boolean;
  isMyRoster?: boolean;
  fantasyTeam?: string;
}

// ─── Constants ───────────────────────────────────────────────────────────────

const skaterStatCols = ["G", "A", "SOG", "PPP", "SHP", "HIT", "BLK", "FOW", "FOL"];
const goalieStatCols = ["W", "L", "SOL", "SV", "GA", "SO"];

const categoryLabels: Record<string, string> = {
  G: "Goals", A: "Assists", PPP: "Power Play Pts", SHP: "Shorthanded Pts",
  SOG: "Shots on Goal", HIT: "Hits", BLK: "Blocked Shots",
  FOW: "Faceoffs Won", FOL: "Faceoffs Lost",
  W: "Wins", L: "Losses", SOL: "Shootout Losses",
  SV: "Saves", GA: "Goals Against", SO: "Shutouts",
};

const leagueTeams = [
  { name: "Arctic Wolves", abbr: "ARC" },
  { name: "Blizzard Kings", abbr: "BLZ" },
  { name: "Frost Giants", abbr: "FRST" },
  { name: "Glacier Bears", abbr: "GLC" },
  { name: "Ice Hawks", abbr: "ICE" },
  { name: "Northern Lights", abbr: "NTH" },
  { name: "Polar Phantoms", abbr: "PLR" },
  { name: "Snow Serpents", abbr: "SNW" },
  { name: "Storm Riders", abbr: "STR" },
  { name: "Tundra Titans", abbr: "TND" },
  { name: "Winter Wrath", abbr: "WNT" },
  { name: "Zero Below", abbr: "ZRO" },
].sort((a, b) => a.name.localeCompare(b.name));

const MY_TEAM = "FRST";

const timeRanges = [
  { value: "season", label: "This Season" },
  { value: "1", label: "1 Day" },
  { value: "7", label: "7 Days" },
  { value: "14", label: "14 Days" },
  { value: "30", label: "30 Days" },
  { value: "60", label: "60 Days" },
  { value: "120", label: "120 Days" },
  { value: "prev-season-1", label: "2024-25 Season" },
  { value: "prev-season-2", label: "2023-24 Season" },
];

// Matchup periods (weekly matchups, 22 weeks)
const matchupPeriods = Array.from({ length: 22 }, (_, i) => ({
  value: `mp-${i + 1}`,
  label: `Matchup ${i + 1}`,
}));

// ─── Data ────────────────────────────────────────────────────────────────────

const freeAgentPlayers: Player[] = [
  { id: 101, name: "Jake Guentzel", position: "LW", team: "TBL", age: 29, salary: 0, totalFpts: 82, owned: false, categoryBreakdown: { G: 28, A: 34, PPP: 18, SHP: 1, SOG: 210, HIT: 32, BLK: 14, FOW: 12, FOL: 8, W: 0, L: 0, SOL: 0, SV: 0, GA: 0, SO: 0 } },
  { id: 102, name: "Sam Reinhart", position: "C", team: "FLA", age: 28, salary: 0, totalFpts: 94, owned: false, categoryBreakdown: { G: 32, A: 38, PPP: 22, SHP: 2, SOG: 230, HIT: 24, BLK: 10, FOW: 520, FOL: 410, W: 0, L: 0, SOL: 0, SV: 0, GA: 0, SO: 0 } },
  { id: 103, name: "Elias Lindholm", position: "C", team: "BOS", age: 29, salary: 0, totalFpts: 58, owned: false, categoryBreakdown: { G: 16, A: 22, PPP: 10, SHP: 3, SOG: 160, HIT: 44, BLK: 28, FOW: 680, FOL: 540, W: 0, L: 0, SOL: 0, SV: 0, GA: 0, SO: 0 } },
  { id: 104, name: "Jonathan Marchessault", position: "RW", team: "NSH", age: 33, salary: 0, totalFpts: 62, owned: false, categoryBreakdown: { G: 22, A: 24, PPP: 12, SHP: 0, SOG: 190, HIT: 28, BLK: 8, FOW: 18, FOL: 14, W: 0, L: 0, SOL: 0, SV: 0, GA: 0, SO: 0 } },
  { id: 105, name: "Matt Duchene", position: "C", team: "DAL", age: 33, salary: 0, totalFpts: 68, owned: false, categoryBreakdown: { G: 20, A: 30, PPP: 14, SHP: 1, SOG: 175, HIT: 18, BLK: 6, FOW: 440, FOL: 380, W: 0, L: 0, SOL: 0, SV: 0, GA: 0, SO: 0 } },
  { id: 106, name: "Tyler Bertuzzi", position: "LW", team: "CHI", age: 29, salary: 0, totalFpts: 54, owned: false, categoryBreakdown: { G: 18, A: 20, PPP: 8, SHP: 0, SOG: 150, HIT: 82, BLK: 18, FOW: 6, FOL: 4, W: 0, L: 0, SOL: 0, SV: 0, GA: 0, SO: 0 } },
  { id: 107, name: "Anthony Mantha", position: "RW", team: "FA", age: 29, salary: 0, totalFpts: 42, owned: false, categoryBreakdown: { G: 14, A: 16, PPP: 6, SHP: 0, SOG: 130, HIT: 36, BLK: 10, FOW: 4, FOL: 2, W: 0, L: 0, SOL: 0, SV: 0, GA: 0, SO: 0 } },
  { id: 108, name: "Sean Monahan", position: "C", team: "CBJ", age: 29, salary: 0, totalFpts: 56, owned: false, categoryBreakdown: { G: 18, A: 22, PPP: 10, SHP: 1, SOG: 155, HIT: 22, BLK: 8, FOW: 580, FOL: 460, W: 0, L: 0, SOL: 0, SV: 0, GA: 0, SO: 0 } },
  { id: 109, name: "Viktor Arvidsson", position: "RW", team: "FA", age: 31, salary: 0, totalFpts: 38, owned: false, categoryBreakdown: { G: 12, A: 14, PPP: 4, SHP: 0, SOG: 110, HIT: 20, BLK: 6, FOW: 2, FOL: 2, W: 0, L: 0, SOL: 0, SV: 0, GA: 0, SO: 0 } },
  { id: 110, name: "Tomas Hertl", position: "C", team: "VGK", age: 30, salary: 0, totalFpts: 72, owned: false, categoryBreakdown: { G: 24, A: 28, PPP: 14, SHP: 2, SOG: 185, HIT: 38, BLK: 12, FOW: 620, FOL: 490, W: 0, L: 0, SOL: 0, SV: 0, GA: 0, SO: 0 } },
  { id: 111, name: "Jake DeBrusk", position: "LW", team: "VAN", age: 27, salary: 0, totalFpts: 64, owned: false, categoryBreakdown: { G: 22, A: 22, PPP: 12, SHP: 1, SOG: 200, HIT: 48, BLK: 14, FOW: 8, FOL: 6, W: 0, L: 0, SOL: 0, SV: 0, GA: 0, SO: 0 } },
  { id: 112, name: "Brett Pesce", position: "D", team: "NJD", age: 29, salary: 0, totalFpts: 48, owned: false, categoryBreakdown: { G: 6, A: 22, PPP: 8, SHP: 0, SOG: 120, HIT: 92, BLK: 138, FOW: 0, FOL: 0, W: 0, L: 0, SOL: 0, SV: 0, GA: 0, SO: 0 } },
  { id: 113, name: "Erik Gustafsson", position: "D", team: "DET", age: 32, salary: 0, totalFpts: 34, owned: false, categoryBreakdown: { G: 4, A: 18, PPP: 10, SHP: 0, SOG: 95, HIT: 18, BLK: 76, FOW: 0, FOL: 0, W: 0, L: 0, SOL: 0, SV: 0, GA: 0, SO: 0 } },
  { id: 114, name: "Tyson Barrie", position: "D", team: "CGY", age: 33, salary: 0, totalFpts: 42, owned: false, categoryBreakdown: { G: 8, A: 20, PPP: 12, SHP: 0, SOG: 110, HIT: 14, BLK: 64, FOW: 0, FOL: 0, W: 0, L: 0, SOL: 0, SV: 0, GA: 0, SO: 0 } },
  { id: 115, name: "Laurent Brossoit", position: "G", team: "FA", age: 31, salary: 0, totalFpts: 45, owned: false, categoryBreakdown: { G: 0, A: 0, PPP: 0, SHP: 0, SOG: 0, HIT: 0, BLK: 0, FOW: 0, FOL: 0, W: 18, L: 10, SOL: 3, SV: 842, GA: 68, SO: 2 } },
  { id: 116, name: "Casey DeSmith", position: "G", team: "DAL", age: 32, salary: 0, totalFpts: 38, owned: false, categoryBreakdown: { G: 0, A: 0, PPP: 0, SHP: 0, SOG: 0, HIT: 0, BLK: 0, FOW: 0, FOL: 0, W: 14, L: 12, SOL: 4, SV: 780, GA: 82, SO: 1 } },
];

const myRosterPlayers: Player[] = [
  { id: 201, name: "Connor McDavid", position: "C", team: "EDM", age: 27, salary: 12500000, totalFpts: 142, owned: true, isMyRoster: true, fantasyTeam: MY_TEAM, categoryBreakdown: { G: 44, A: 68, PPP: 36, SHP: 4, SOG: 320, HIT: 16, BLK: 8, FOW: 780, FOL: 520, W: 0, L: 0, SOL: 0, SV: 0, GA: 0, SO: 0 } },
  { id: 202, name: "Cale Makar", position: "D", team: "COL", age: 25, salary: 9000000, totalFpts: 108, owned: true, isMyRoster: true, fantasyTeam: MY_TEAM, categoryBreakdown: { G: 22, A: 52, PPP: 28, SHP: 2, SOG: 260, HIT: 34, BLK: 96, FOW: 0, FOL: 0, W: 0, L: 0, SOL: 0, SV: 0, GA: 0, SO: 0 } },
  { id: 203, name: "Andrei Vasilevskiy", position: "G", team: "TBL", age: 29, salary: 9500000, totalFpts: 88, owned: true, isMyRoster: true, fantasyTeam: MY_TEAM, categoryBreakdown: { G: 0, A: 0, PPP: 0, SHP: 0, SOG: 0, HIT: 0, BLK: 0, FOW: 0, FOL: 0, W: 34, L: 14, SOL: 4, SV: 1620, GA: 112, SO: 5 } },
  { id: 204, name: "Brady Tkachuk", position: "LW", team: "OTT", age: 25, salary: 8214000, totalFpts: 96, owned: true, isMyRoster: true, fantasyTeam: MY_TEAM, categoryBreakdown: { G: 30, A: 36, PPP: 16, SHP: 2, SOG: 280, HIT: 184, BLK: 32, FOW: 14, FOL: 10, W: 0, L: 0, SOL: 0, SV: 0, GA: 0, SO: 0 } },
  { id: 205, name: "Mika Zibanejad", position: "C", team: "NYR", age: 31, salary: 8500000, totalFpts: 78, owned: true, isMyRoster: true, fantasyTeam: MY_TEAM, categoryBreakdown: { G: 26, A: 32, PPP: 20, SHP: 1, SOG: 240, HIT: 28, BLK: 12, FOW: 620, FOL: 480, W: 0, L: 0, SOL: 0, SV: 0, GA: 0, SO: 0 } },
];

const otherOwnedPlayers: Player[] = [
  { id: 301, name: "Nathan MacKinnon", position: "C", team: "COL", age: 28, salary: 12600000, totalFpts: 136, owned: true, fantasyTeam: "ARC", categoryBreakdown: { G: 40, A: 62, PPP: 32, SHP: 3, SOG: 300, HIT: 22, BLK: 6, FOW: 700, FOL: 480, W: 0, L: 0, SOL: 0, SV: 0, GA: 0, SO: 0 } },
  { id: 302, name: "Auston Matthews", position: "C", team: "TOR", age: 26, salary: 13250000, totalFpts: 128, owned: true, fantasyTeam: "BLZ", categoryBreakdown: { G: 52, A: 38, PPP: 26, SHP: 2, SOG: 340, HIT: 18, BLK: 10, FOW: 640, FOL: 500, W: 0, L: 0, SOL: 0, SV: 0, GA: 0, SO: 0 } },
  { id: 303, name: "Nikita Kucherov", position: "RW", team: "TBL", age: 31, salary: 9500000, totalFpts: 132, owned: true, fantasyTeam: "GLC", categoryBreakdown: { G: 38, A: 62, PPP: 34, SHP: 1, SOG: 280, HIT: 14, BLK: 8, FOW: 6, FOL: 4, W: 0, L: 0, SOL: 0, SV: 0, GA: 0, SO: 0 } },
  { id: 304, name: "Igor Shesterkin", position: "G", team: "NYR", age: 28, salary: 5666667, totalFpts: 92, owned: true, fantasyTeam: "ICE", categoryBreakdown: { G: 0, A: 0, PPP: 0, SHP: 0, SOG: 0, HIT: 0, BLK: 0, FOW: 0, FOL: 0, W: 36, L: 12, SOL: 3, SV: 1720, GA: 98, SO: 6 } },
  { id: 305, name: "Leon Draisaitl", position: "C", team: "EDM", age: 28, salary: 8500000, totalFpts: 126, owned: true, fantasyTeam: "NTH", categoryBreakdown: { G: 42, A: 54, PPP: 30, SHP: 2, SOG: 290, HIT: 30, BLK: 8, FOW: 660, FOL: 520, W: 0, L: 0, SOL: 0, SV: 0, GA: 0, SO: 0 } },
  { id: 306, name: "David Pastrnak", position: "RW", team: "BOS", age: 28, salary: 11250000, totalFpts: 118, owned: true, fantasyTeam: "PLR", categoryBreakdown: { G: 40, A: 44, PPP: 28, SHP: 1, SOG: 310, HIT: 20, BLK: 6, FOW: 4, FOL: 2, W: 0, L: 0, SOL: 0, SV: 0, GA: 0, SO: 0 } },
  { id: 307, name: "Kirill Kaprizov", position: "LW", team: "MIN", age: 27, salary: 9000000, totalFpts: 122, owned: true, fantasyTeam: "SNW", categoryBreakdown: { G: 38, A: 48, PPP: 26, SHP: 3, SOG: 270, HIT: 26, BLK: 10, FOW: 8, FOL: 6, W: 0, L: 0, SOL: 0, SV: 0, GA: 0, SO: 0 } },
  { id: 308, name: "Quinn Hughes", position: "D", team: "VAN", age: 25, salary: 7850000, totalFpts: 104, owned: true, fantasyTeam: "STR", categoryBreakdown: { G: 16, A: 58, PPP: 32, SHP: 1, SOG: 220, HIT: 22, BLK: 82, FOW: 0, FOL: 0, W: 0, L: 0, SOL: 0, SV: 0, GA: 0, SO: 0 } },
  { id: 309, name: "Aleksander Barkov", position: "C", team: "FLA", age: 28, salary: 10000000, totalFpts: 98, owned: true, fantasyTeam: "TND", categoryBreakdown: { G: 28, A: 40, PPP: 18, SHP: 6, SOG: 200, HIT: 42, BLK: 24, FOW: 720, FOL: 480, W: 0, L: 0, SOL: 0, SV: 0, GA: 0, SO: 0 } },
  { id: 310, name: "Mikko Rantanen", position: "RW", team: "COL", age: 27, salary: 9250000, totalFpts: 112, owned: true, fantasyTeam: "WNT", categoryBreakdown: { G: 34, A: 46, PPP: 24, SHP: 2, SOG: 260, HIT: 32, BLK: 12, FOW: 10, FOL: 8, W: 0, L: 0, SOL: 0, SV: 0, GA: 0, SO: 0 } },
  { id: 311, name: "Jason Robertson", position: "LW", team: "DAL", age: 25, salary: 7750000, totalFpts: 102, owned: true, fantasyTeam: "ZRO", categoryBreakdown: { G: 32, A: 40, PPP: 22, SHP: 1, SOG: 240, HIT: 18, BLK: 8, FOW: 6, FOL: 4, W: 0, L: 0, SOL: 0, SV: 0, GA: 0, SO: 0 } },
];

const positions = [
  { value: "all", label: "All Positions" },
  { value: "C", label: "Center" },
  { value: "LW", label: "Left Wing" },
  { value: "RW", label: "Right Wing" },
  { value: "D", label: "Defense" },
  { value: "G", label: "Goalie" },
];

const getPositionColor = (position: string) => {
  switch (position) {
    case "C": return "bg-primary/20 text-primary";
    case "LW":
    case "RW": return "bg-success/20 text-success";
    case "D": return "bg-accent/20 text-accent";
    case "G": return "bg-purple-500/20 text-purple-400";
    default: return "bg-secondary text-secondary-foreground";
  }
};

const isGoalie = (pos: string) => pos === "G";

// Deterministic pseudo-random
const seededRandom = (seed: number) => {
  const x = Math.sin(seed) * 10000;
  return x - Math.floor(x);
};

// ─── Component ───────────────────────────────────────────────────────────────

const PlayerPool = () => {
  const [searchQuery, setSearchQuery] = useState("");
  const [positionFilter, setPositionFilter] = useState("all");
  const [timeRange, setTimeRange] = useState("season");
  const [matchupPeriod, setMatchupPeriod] = useState("none");
  const [includeMyRoster, setIncludeMyRoster] = useState(false);
  const [includeAllPlayers, setIncludeAllPlayers] = useState(false);
  const [fantasyTeamFilter, setFantasyTeamFilter] = useState("all");

  // The active filter: matchup period overrides time range when selected
  const activeRange = matchupPeriod !== "none" ? matchupPeriod : timeRange;

  const scaledCache = useMemo(() => {
    const cache = new Map<string, { breakdown: PlayerCategoryBreakdown; fpts: number }>();
    const allPlayers = [...freeAgentPlayers, ...myRosterPlayers, ...otherOwnedPlayers];

    let ratio = 1;
    let seedOffset = 0;

    if (activeRange === "season") {
      ratio = 1;
    } else if (activeRange === "prev-season-1") {
      ratio = 0.92; // slightly different previous season
      seedOffset = 5000;
    } else if (activeRange === "prev-season-2") {
      ratio = 0.85;
      seedOffset = 10000;
    } else if (activeRange.startsWith("mp-")) {
      // Matchup period = ~7 days of a season
      ratio = 7 / 180;
      seedOffset = parseInt(activeRange.replace("mp-", "")) * 1000;
    } else {
      const days = parseInt(activeRange);
      ratio = days / 180;
    }

    for (const player of allPlayers) {
      if (activeRange === "season") {
        cache.set(`${player.id}`, { breakdown: player.categoryBreakdown, fpts: player.totalFpts });
      } else {
        const scaled: Record<string, number> = {};
        let i = 0;
        for (const key of Object.keys(player.categoryBreakdown)) {
          const base = player.categoryBreakdown[key];
          const variance = 0.75 + seededRandom(player.id * 100 + i + seedOffset + (parseInt(activeRange) || 0)) * 0.5;
          scaled[key] = Math.round(base * ratio * variance);
          i++;
        }
        const fptsVariance = 0.8 + seededRandom(player.id * 1000 + seedOffset + (parseInt(activeRange) || 0)) * 0.4;
        cache.set(`${player.id}`, {
          breakdown: scaled as PlayerCategoryBreakdown,
          fpts: Math.round(player.totalFpts * ratio * fptsVariance),
        });
      }
    }
    return cache;
  }, [activeRange]);

  const filteredPlayers = useMemo(() => {
    let pool: Player[] = [...freeAgentPlayers];

    if (includeMyRoster) {
      pool = [...pool, ...myRosterPlayers];
    }

    if (includeAllPlayers) {
      pool = [...pool, ...otherOwnedPlayers];
      if (!includeMyRoster) {
        pool = [...pool, ...myRosterPlayers];
      }
    }

    return pool
      .filter((player) => {
        const matchesSearch = player.name.toLowerCase().includes(searchQuery.toLowerCase());
        const matchesPosition = positionFilter === "all" || player.position === positionFilter;
        const matchesFantasyTeam =
          fantasyTeamFilter === "all" ||
          fantasyTeamFilter === "fa"
            ? (fantasyTeamFilter === "all" || !player.owned)
            : player.fantasyTeam === fantasyTeamFilter;
        return matchesSearch && matchesPosition && matchesFantasyTeam;
      })
      .sort((a, b) => {
        const aData = scaledCache.get(`${a.id}`);
        const bData = scaledCache.get(`${b.id}`);
        return (bData?.fpts ?? b.totalFpts) - (aData?.fpts ?? a.totalFpts);
      });
  }, [searchQuery, positionFilter, includeMyRoster, includeAllPlayers, fantasyTeamFilter, scaledCache]);

  const showingOnlyGoalies = positionFilter === "G";
  const showingOnlySkaters = positionFilter !== "all" && positionFilter !== "G";

  const statColumns = showingOnlyGoalies
    ? goalieStatCols
    : showingOnlySkaters
      ? skaterStatCols
      : [...skaterStatCols, ...goalieStatCols];

  const showFantasyTeamCol = includeAllPlayers || includeMyRoster;

  return (
    <AppLayout>
      <div className="container py-8 space-y-6">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Users className="h-6 w-6 text-primary" />
            <span className="text-gradient-ice">Player Pool</span>
          </h1>
          <p className="text-muted-foreground">
            Browse available free agents and analyze player performance trends
          </p>
        </div>

        {/* Filters Row 1: Search + Position + Time Range */}
        <div className="flex flex-col sm:flex-row gap-4">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Search by player name..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-10 bg-secondary/50"
            />
          </div>
          <Select value={positionFilter} onValueChange={setPositionFilter}>
            <SelectTrigger className="w-full sm:w-[160px] bg-secondary/50">
              <SelectValue placeholder="Position" />
            </SelectTrigger>
            <SelectContent>
              {positions.map((pos) => (
                <SelectItem key={pos.value} value={pos.value}>
                  {pos.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select
            value={timeRange}
            onValueChange={(val) => {
              setTimeRange(val);
              setMatchupPeriod("none");
            }}
          >
            <SelectTrigger className="w-full sm:w-[160px] bg-secondary/50">
              <SelectValue placeholder="Time Range" />
            </SelectTrigger>
            <SelectContent>
              {timeRanges.map((tr) => (
                <SelectItem key={tr.value} value={tr.value}>
                  {tr.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select
            value={matchupPeriod}
            onValueChange={(val) => {
              setMatchupPeriod(val);
              if (val !== "none") setTimeRange("season");
            }}
          >
            <SelectTrigger className="w-full sm:w-[170px] bg-secondary/50">
              <Calendar className="h-4 w-4 mr-2 text-muted-foreground shrink-0" />
              <SelectValue placeholder="Matchup Period" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="none">No Matchup Filter</SelectItem>
              {matchupPeriods.map((mp) => (
                <SelectItem key={mp.value} value={mp.value}>
                  {mp.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {/* Filters Row 2: Toggles + Fantasy Team Filter */}
        <div className="flex flex-wrap items-center gap-6">
          <div className="flex items-center gap-2">
            <Switch
              id="include-roster"
              checked={includeMyRoster}
              onCheckedChange={(checked) => {
                setIncludeMyRoster(checked);
                if (checked && includeAllPlayers) setIncludeAllPlayers(false);
                if (!checked && !includeAllPlayers) setFantasyTeamFilter("all");
              }}
            />
            <Label htmlFor="include-roster" className="text-sm cursor-pointer">
              Include My Roster
            </Label>
          </div>
          <div className="flex items-center gap-2">
            <Switch
              id="include-all"
              checked={includeAllPlayers}
              onCheckedChange={(checked) => {
                setIncludeAllPlayers(checked);
                if (checked) setIncludeMyRoster(false);
                if (!checked) setFantasyTeamFilter("all");
              }}
            />
            <Label htmlFor="include-all" className="text-sm cursor-pointer">
              All Players (incl. owned)
            </Label>
          </div>

          {(includeAllPlayers || includeMyRoster) && (
            <Select value={fantasyTeamFilter} onValueChange={setFantasyTeamFilter}>
              <SelectTrigger className="w-[180px] bg-secondary/50">
                <SelectValue placeholder="Fantasy Team" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Teams</SelectItem>
                <SelectItem value="fa">Free Agents Only</SelectItem>
                {leagueTeams.map((t) => (
                  <SelectItem key={t.abbr} value={t.abbr}>
                    {t.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}

          <Badge variant="secondary" className="text-sm ml-auto">
            {filteredPlayers.length} players
          </Badge>
        </div>

        {/* Active filter indicator */}
        {(activeRange !== "season") && (
          <div className="flex items-center gap-2">
            <Badge variant="outline" className="text-xs border-primary/30 text-primary">
              {matchupPeriod !== "none"
                ? matchupPeriods.find(mp => mp.value === matchupPeriod)?.label
                : timeRanges.find(tr => tr.value === timeRange)?.label
              }
            </Badge>
            <span className="text-xs text-muted-foreground">
              Stats are filtered to this period
            </span>
          </div>
        )}

        {/* Player Table */}
        <div className="stat-card p-0 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full table-fixed">
              <thead>
                <tr className="border-b border-border bg-secondary/30">
                  <th className="text-left text-xs font-medium text-muted-foreground p-3 w-[180px]">Player</th>
                  <th className="text-center text-xs font-medium text-muted-foreground p-2 w-[48px]">POS</th>
                  {showFantasyTeamCol && (
                    <th className="text-center text-xs font-medium text-muted-foreground p-2 w-[64px]">Owner</th>
                  )}
                  <th className="text-center text-xs font-medium text-muted-foreground p-2 w-[40px]">Age</th>
                  {statColumns.map(cat => (
                    <th key={cat} className="text-center text-xs font-medium text-muted-foreground p-2 w-[48px]">
                      <TooltipProvider>
                        <Tooltip>
                          <TooltipTrigger><span>{cat}</span></TooltipTrigger>
                          <TooltipContent><p>{categoryLabels[cat]}</p></TooltipContent>
                        </Tooltip>
                      </TooltipProvider>
                    </th>
                  ))}
                  <th className="text-right text-xs font-medium text-muted-foreground p-2 w-[52px]">FPTS</th>
                  <th className="text-center text-xs font-medium text-muted-foreground p-2 w-[50px]">Action</th>
                </tr>
              </thead>
              <tbody>
                {filteredPlayers.map((player, index) => {
                  const data = scaledCache.get(`${player.id}`);
                  const breakdown = data?.breakdown ?? player.categoryBreakdown;
                  const fpts = data?.fpts ?? player.totalFpts;
                  const ownerTeam = player.fantasyTeam
                    ? leagueTeams.find(t => t.abbr === player.fantasyTeam)
                    : null;

                  return (
                    <tr
                      key={player.id}
                      className={`border-b border-border/50 hover:bg-secondary/20 transition-colors animate-fade-in ${
                        player.isMyRoster ? "bg-primary/5 border-l-2 border-l-primary" : ""
                      }`}
                      style={{ animationDelay: `${index * 30}ms` }}
                    >
                      <td className="p-3">
                        <div className="flex items-center gap-2">
                          <div className="h-8 w-8 rounded-md bg-gradient-to-br from-secondary to-muted flex items-center justify-center text-[10px] font-bold shrink-0">
                            {player.team}
                          </div>
                          <div className="flex flex-col min-w-0">
                            <span className="font-medium text-sm text-foreground truncate">{player.name}</span>
                          </div>
                        </div>
                      </td>
                      <td className="p-2 text-center">
                        <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded-full ${getPositionColor(player.position)}`}>
                          {player.position}
                        </span>
                      </td>
                      {showFantasyTeamCol && (
                        <td className="p-2 text-center">
                          {ownerTeam ? (
                            <TooltipProvider>
                              <Tooltip>
                                <TooltipTrigger>
                                  <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded ${
                                    player.isMyRoster
                                      ? "bg-primary/20 text-primary"
                                      : "bg-secondary text-muted-foreground"
                                  }`}>
                                    {ownerTeam.abbr}
                                  </span>
                                </TooltipTrigger>
                                <TooltipContent><p>{ownerTeam.name}</p></TooltipContent>
                              </Tooltip>
                            </TooltipProvider>
                          ) : (
                            <span
                              className="text-[10px] text-muted-foreground/60"
                              data-testid="player-pool-fantasy-team-na"
                              title="Not drafted by any fantasy team yet"
                            >
                              N/A
                            </span>
                          )}
                        </td>
                      )}
                      <td className="p-2 text-center text-xs text-muted-foreground">{player.age}</td>
                      {statColumns.map(cat => (
                        <td key={cat} className="p-2 text-center text-sm">
                          {breakdown[cat] ?? 0}
                        </td>
                      ))}
                      <td className="p-2 text-right font-bold text-primary">{fpts}</td>
                      <td className="p-2 text-center">
                        {!player.owned ? (
                          <TooltipProvider>
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <Button
                                  variant="ghost"
                                  size="icon"
                                  className="h-7 w-7 text-muted-foreground hover:text-success hover:bg-success/10"
                                >
                                  <UserPlus className="h-3.5 w-3.5" />
                                </Button>
                              </TooltipTrigger>
                              <TooltipContent>
                                <p>Add to Roster</p>
                              </TooltipContent>
                            </Tooltip>
                          </TooltipProvider>
                        ) : (
                          <span className="text-xs text-muted-foreground">—</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </AppLayout>
  );
};

export default PlayerPool;
