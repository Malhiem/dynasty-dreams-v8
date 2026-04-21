// @ts-nocheck
import { useState } from "react";
import { AppLayout } from "@/components/layout/AppLayout";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Trophy, Crown, Award, TrendingUp, TrendingDown, Target, Users, BarChart3, Calendar, Star, Shield, Medal, Stars } from "lucide-react";
import { allStarTeams } from "@/lovable/data/playerAwardsData";

// Mock data for league history
const lifetimeTeamRecords = [
  { rank: 1, team: "Team Frostbite", seasons: 8, wins: 89, losses: 47, ties: 0, winPct: ".654", totalPoints: 52100, championships: 3, presidentsTrophies: 2, divisionWins: 4 },
  { rank: 2, team: "Arctic Thunder", seasons: 8, wins: 82, losses: 54, ties: 0, winPct: ".603", totalPoints: 48900, championships: 2, presidentsTrophies: 1, divisionWins: 3 },
  { rank: 3, team: "Ice Wolves", seasons: 8, wins: 78, losses: 58, ties: 0, winPct: ".574", totalPoints: 46200, championships: 1, presidentsTrophies: 2, divisionWins: 2 },
  { rank: 4, team: "Polar Dynasty", seasons: 8, wins: 75, losses: 61, ties: 0, winPct: ".551", totalPoints: 44800, championships: 1, presidentsTrophies: 1, divisionWins: 2 },
  { rank: 5, team: "Glacier Kings", seasons: 8, wins: 71, losses: 65, ties: 0, winPct: ".522", totalPoints: 43100, championships: 1, presidentsTrophies: 1, divisionWins: 1 },
  { rank: 6, team: "Frozen Elite", seasons: 7, wins: 62, losses: 57, ties: 0, winPct: ".521", totalPoints: 38200, championships: 0, presidentsTrophies: 0, divisionWins: 1 },
  { rank: 7, team: "Blizzard Force", seasons: 8, wins: 68, losses: 68, ties: 0, winPct: ".500", totalPoints: 41500, championships: 0, presidentsTrophies: 1, divisionWins: 2 },
  { rank: 8, team: "Tundra Titans", seasons: 6, wins: 48, losses: 51, ties: 0, winPct: ".485", totalPoints: 29800, championships: 0, presidentsTrophies: 0, divisionWins: 1 },
  { rank: 9, team: "Snow Storm", seasons: 8, wins: 59, losses: 77, ties: 0, winPct: ".434", totalPoints: 36100, championships: 0, presidentsTrophies: 0, divisionWins: 0 },
  { rank: 10, team: "Winter Hawks", seasons: 5, wins: 35, losses: 50, ties: 0, winPct: ".412", totalPoints: 21500, championships: 0, presidentsTrophies: 0, divisionWins: 0 },
  { rank: 11, team: "Avalanche", seasons: 4, wins: 24, losses: 44, ties: 0, winPct: ".353", totalPoints: 15200, championships: 0, presidentsTrophies: 0, divisionWins: 0 },
  { rank: 12, team: "Cold Front", seasons: 3, wins: 15, losses: 36, ties: 0, winPct: ".294", totalPoints: 9800, championships: 0, presidentsTrophies: 0, divisionWins: 0 },
];

const leagueRecords = {
  highestSeasonPoints: { team: "Team Frostbite", value: 8240, season: "2023-24" },
  lowestSeasonPoints: { team: "Cold Front", value: 2890, season: "2022-23" },
  bestWinLossRecord: { team: "Team Frostbite", value: "14-3", season: "2023-24" },
  worstWinLossRecord: { team: "Avalanche", value: "3-14", season: "2020-21" },
  mostChampionships: { team: "Team Frostbite", value: 3, seasons: ["2019-20", "2022-23", "2023-24"] },
  longestWinStreak: { team: "Arctic Thunder", value: 9, season: "2021-22" },
  highestSingleWeek: { team: "Ice Wolves", value: 892, week: "Week 12, 2022-23" },
};

interface StatRecord {
  category: string;
  abbr: string;
  record: number;
  player: string;
  team: string;
  context: string;
}

const weeklyMatchupRecords: StatRecord[] = [
  { category: "Goals", abbr: "G", record: 7, player: "Auston Matthews", team: "Puck Dynasty", context: "Week 4, 2023-24" },
  { category: "Assists", abbr: "A", record: 9, player: "Connor McDavid", team: "Team Frostbite", context: "Week 11, 2022-23" },
  { category: "Powerplay Points", abbr: "PPP", record: 6, player: "Nikita Kucherov", team: "Ice Wolves", context: "Week 8, 2023-24" },
  { category: "Shorthanded Points", abbr: "SHP", record: 3, player: "Brad Marchand", team: "Arctic Thunder", context: "Week 14, 2021-22" },
  { category: "Game Winning Goals", abbr: "GWG", record: 3, player: "Leon Draisaitl", team: "Glacier Kings", context: "Week 6, 2023-24" },
  { category: "Shots on Goal", abbr: "SOG", record: 32, player: "Alex Ovechkin", team: "Blizzard Force", context: "Week 2, 2020-21" },
  { category: "Hits", abbr: "HIT", record: 28, player: "Ryan Reaves", team: "Tundra Titans", context: "Week 9, 2022-23" },
  { category: "Blocked Shots", abbr: "BLK", record: 22, player: "Cale Makar", team: "Team Frostbite", context: "Week 15, 2023-24" },
  { category: "Plus/Minus", abbr: "+/-", record: 10, player: "Nathan MacKinnon", team: "Polar Dynasty", context: "Week 7, 2022-23" },
  { category: "Goalie Wins", abbr: "W", record: 4, player: "Connor Hellebuyck", team: "Arctic Thunder", context: "Week 3, 2023-24" },
  { category: "Saves", abbr: "SV", record: 148, player: "Igor Shesterkin", team: "Frozen Elite", context: "Week 12, 2022-23" },
  { category: "Shutouts", abbr: "SO", record: 3, player: "Andrei Vasilevskiy", team: "Ice Wolves", context: "Week 5, 2021-22" },
  { category: "Goals Against (fewest)", abbr: "GA", record: 2, player: "Jake Oettinger", team: "Glacier Kings", context: "Week 10, 2023-24" },
];

const seasonRecords: StatRecord[] = [
  { category: "Goals", abbr: "G", record: 58, player: "Auston Matthews", team: "Puck Dynasty", context: "2023-24" },
  { category: "Assists", abbr: "A", record: 82, player: "Connor McDavid", team: "Team Frostbite", context: "2022-23" },
  { category: "Powerplay Points", abbr: "PPP", record: 48, player: "Nikita Kucherov", team: "Ice Wolves", context: "2023-24" },
  { category: "Shorthanded Points", abbr: "SHP", record: 12, player: "Brad Marchand", team: "Arctic Thunder", context: "2021-22" },
  { category: "Game Winning Goals", abbr: "GWG", record: 14, player: "Leon Draisaitl", team: "Glacier Kings", context: "2023-24" },
  { category: "Shots on Goal", abbr: "SOG", record: 348, player: "Alex Ovechkin", team: "Blizzard Force", context: "2020-21" },
  { category: "Hits", abbr: "HIT", record: 312, player: "Tom Wilson", team: "Tundra Titans", context: "2022-23" },
  { category: "Blocked Shots", abbr: "BLK", record: 198, player: "Cale Makar", team: "Team Frostbite", context: "2023-24" },
  { category: "Plus/Minus", abbr: "+/-", record: 42, player: "Nathan MacKinnon", team: "Polar Dynasty", context: "2022-23" },
  { category: "Goalie Wins", abbr: "W", record: 38, player: "Connor Hellebuyck", team: "Arctic Thunder", context: "2023-24" },
  { category: "Saves", abbr: "SV", record: 1842, player: "Igor Shesterkin", team: "Frozen Elite", context: "2022-23" },
  { category: "Shutouts", abbr: "SO", record: 9, player: "Andrei Vasilevskiy", team: "Ice Wolves", context: "2021-22" },
  { category: "Goals Against (fewest)", abbr: "GA", record: 98, player: "Jake Oettinger", team: "Glacier Kings", context: "2023-24" },
];

const hallOfFameSkaters = [
  { rank: 1, player: "Connor McDavid", position: "C", totalPoints: 2840, seasons: 5, avgPPG: 8.2, bestSeason: 612 },
  { rank: 2, player: "Nathan MacKinnon", position: "C", totalPoints: 2680, seasons: 6, avgPPG: 7.8, bestSeason: 589 },
  { rank: 3, player: "Leon Draisaitl", position: "C", totalPoints: 2590, seasons: 5, avgPPG: 7.5, bestSeason: 578 },
  { rank: 4, player: "Nikita Kucherov", position: "RW", totalPoints: 2410, seasons: 6, avgPPG: 7.0, bestSeason: 542 },
  { rank: 5, player: "Auston Matthews", position: "C", totalPoints: 2380, seasons: 5, avgPPG: 6.9, bestSeason: 534 },
  { rank: 6, player: "Cale Makar", position: "D", totalPoints: 2290, seasons: 4, avgPPG: 6.6, bestSeason: 521 },
  { rank: 7, player: "David Pastrnak", position: "RW", totalPoints: 2180, seasons: 5, avgPPG: 6.3, bestSeason: 498 },
  { rank: 8, player: "Artemi Panarin", position: "LW", totalPoints: 2090, seasons: 6, avgPPG: 6.1, bestSeason: 476 },
  { rank: 9, player: "Mitch Marner", position: "RW", totalPoints: 1980, seasons: 5, avgPPG: 5.7, bestSeason: 445 },
  { rank: 10, player: "Kirill Kaprizov", position: "LW", totalPoints: 1890, seasons: 4, avgPPG: 5.5, bestSeason: 512 },
];

interface AwardEntry {
  season: string;
  player: string;
  position: string;
  team: string;
  fantasyPoints: number;
}

interface AwardCategory {
  name: string;
  description: string;
  icon: React.ReactNode;
  winners: AwardEntry[];
}

const playerAwards: AwardCategory[] = [
  {
    name: "Art Ross Trophy",
    description: "Season MVP — most fantasy points in the regular season",
    icon: <Trophy className="h-5 w-5 text-yellow-500" />,
    winners: [
      { season: "2025-26", player: "Connor McDavid", position: "C", team: "Team Frostbite", fantasyPoints: 648 },
      { season: "2024-25", player: "Nathan MacKinnon", position: "C", team: "Polar Dynasty", fantasyPoints: 612 },
      { season: "2023-24", player: "Connor McDavid", position: "C", team: "Team Frostbite", fantasyPoints: 634 },
      { season: "2022-23", player: "Connor McDavid", position: "C", team: "Team Frostbite", fantasyPoints: 621 },
      { season: "2021-22", player: "Leon Draisaitl", position: "C", team: "Glacier Kings", fantasyPoints: 578 },
      { season: "2020-21", player: "Auston Matthews", position: "C", team: "Arctic Thunder", fantasyPoints: 556 },
      { season: "2019-20", player: "Leon Draisaitl", position: "C", team: "Glacier Kings", fantasyPoints: 542 },
      { season: "2018-19", player: "Nikita Kucherov", position: "RW", team: "Ice Wolves", fantasyPoints: 538 },
    ],
  },
  {
    name: "Conn Smythe Trophy",
    description: "Playoff MVP — most fantasy points by a player on the championship or runner-up team",
    icon: <Star className="h-5 w-5 text-primary" />,
    winners: [
      { season: "2025-26", player: "Nathan MacKinnon", position: "C", team: "Polar Dynasty", fantasyPoints: 189 },
      { season: "2024-25", player: "Connor McDavid", position: "C", team: "Team Frostbite", fantasyPoints: 201 },
      { season: "2023-24", player: "Nikita Kucherov", position: "RW", team: "Ice Wolves", fantasyPoints: 178 },
      { season: "2022-23", player: "Leon Draisaitl", position: "C", team: "Glacier Kings", fantasyPoints: 184 },
      { season: "2021-22", player: "Cale Makar", position: "D", team: "Team Frostbite", fantasyPoints: 162 },
      { season: "2020-21", player: "Andrei Vasilevskiy", position: "G", team: "Ice Wolves", fantasyPoints: 148 },
      { season: "2019-20", player: "Nathan MacKinnon", position: "C", team: "Polar Dynasty", fantasyPoints: 172 },
      { season: "2018-19", player: "Ryan O'Reilly", position: "C", team: "Arctic Thunder", fantasyPoints: 145 },
    ],
  },
  {
    name: "Hart Trophy",
    description: "Best forward — most fantasy points by a forward (C/LW/RW) for the season",
    icon: <Award className="h-5 w-5 text-accent" />,
    winners: [
      { season: "2025-26", player: "Connor McDavid", position: "C", team: "Team Frostbite", fantasyPoints: 648 },
      { season: "2024-25", player: "Nathan MacKinnon", position: "C", team: "Polar Dynasty", fantasyPoints: 612 },
      { season: "2023-24", player: "Nikita Kucherov", position: "RW", team: "Ice Wolves", fantasyPoints: 598 },
      { season: "2022-23", player: "Connor McDavid", position: "C", team: "Team Frostbite", fantasyPoints: 621 },
      { season: "2021-22", player: "Auston Matthews", position: "C", team: "Arctic Thunder", fantasyPoints: 534 },
      { season: "2020-21", player: "Auston Matthews", position: "C", team: "Arctic Thunder", fantasyPoints: 556 },
      { season: "2019-20", player: "Leon Draisaitl", position: "C", team: "Glacier Kings", fantasyPoints: 542 },
      { season: "2018-19", player: "Nikita Kucherov", position: "RW", team: "Ice Wolves", fantasyPoints: 538 },
    ],
  },
  {
    name: "Norris Trophy",
    description: "Best defenseman — most fantasy points by a defenseman for the season",
    icon: <Shield className="h-5 w-5 text-green-500" />,
    winners: [
      { season: "2025-26", player: "Cale Makar", position: "D", team: "Team Frostbite", fantasyPoints: 478 },
      { season: "2024-25", player: "Cale Makar", position: "D", team: "Team Frostbite", fantasyPoints: 521 },
      { season: "2023-24", player: "Quinn Hughes", position: "D", team: "Blizzard Force", fantasyPoints: 462 },
      { season: "2022-23", player: "Erik Karlsson", position: "D", team: "Snow Storm", fantasyPoints: 489 },
      { season: "2021-22", player: "Cale Makar", position: "D", team: "Team Frostbite", fantasyPoints: 498 },
      { season: "2020-21", player: "Adam Fox", position: "D", team: "Frozen Elite", fantasyPoints: 445 },
      { season: "2019-20", player: "Roman Josi", position: "D", team: "Tundra Titans", fantasyPoints: 432 },
      { season: "2018-19", player: "Brent Burns", position: "D", team: "Polar Dynasty", fantasyPoints: 418 },
    ],
  },
  {
    name: "Vezina Trophy",
    description: "Best goalie — most fantasy points by a goaltender for the season",
    icon: <Medal className="h-5 w-5 text-destructive" />,
    winners: [
      { season: "2025-26", player: "Connor Hellebuyck", position: "G", team: "Arctic Thunder", fantasyPoints: 312 },
      { season: "2024-25", player: "Igor Shesterkin", position: "G", team: "Frozen Elite", fantasyPoints: 345 },
      { season: "2023-24", player: "Connor Hellebuyck", position: "G", team: "Arctic Thunder", fantasyPoints: 298 },
      { season: "2022-23", player: "Linus Ullmark", position: "G", team: "Snow Storm", fantasyPoints: 289 },
      { season: "2021-22", player: "Igor Shesterkin", position: "G", team: "Frozen Elite", fantasyPoints: 324 },
      { season: "2020-21", player: "Andrei Vasilevskiy", position: "G", team: "Ice Wolves", fantasyPoints: 298 },
      { season: "2019-20", player: "Connor Hellebuyck", position: "G", team: "Arctic Thunder", fantasyPoints: 278 },
      { season: "2018-19", player: "Andrei Vasilevskiy", position: "G", team: "Ice Wolves", fantasyPoints: 265 },
    ],
  },
];

const hallOfFameGoalies = [
  { rank: 1, player: "Connor Hellebuyck", totalPoints: 1420, seasons: 6, avgPPG: 4.1, bestSeason: 312, wins: 198 },
  { rank: 2, player: "Igor Shesterkin", totalPoints: 1280, seasons: 4, avgPPG: 3.7, bestSeason: 345, wins: 142 },
  { rank: 3, player: "Andrei Vasilevskiy", totalPoints: 1190, seasons: 5, avgPPG: 3.4, bestSeason: 298, wins: 168 },
  { rank: 4, player: "Jake Oettinger", totalPoints: 980, seasons: 3, avgPPG: 2.8, bestSeason: 289, wins: 98 },
  { rank: 5, player: "Ilya Sorokin", totalPoints: 920, seasons: 4, avgPPG: 2.7, bestSeason: 276, wins: 112 },
];

const positionOrder = ["C", "LW", "RW", "D", "G"];
const positionLabels: Record<string, string> = { C: "Center", LW: "Left Wing", RW: "Right Wing", D: "Defense", G: "Goalie" };

const AllStarTeamsSection = () => {
  const [selectedSeason, setSelectedSeason] = useState(allStarTeams[0].season);
  const seasonData = allStarTeams.find(s => s.season === selectedSeason) || allStarTeams[0];

  const sortByPosition = (players: typeof seasonData.firstTeam) =>
    [...players].sort((a, b) => positionOrder.indexOf(a.position) - positionOrder.indexOf(b.position));

  const renderTeam = (label: string, players: typeof seasonData.firstTeam, accent: boolean) => (
    <Card className="bg-card/50 backdrop-blur border-border/50">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-lg">
          {accent ? <Star className="h-5 w-5 text-yellow-500" /> : <Star className="h-5 w-5 text-muted-foreground" />}
          {label}
        </CardTitle>
        <CardDescription>Best lineup: 1C · 1LW · 1RW · 2D · 1G</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="grid gap-3">
          {sortByPosition(players).map((p) => (
            <div key={p.player} className="flex items-center justify-between p-3 rounded-lg bg-secondary/20 border border-border/50">
              <div className="flex items-center gap-3">
                <Badge variant="outline" className="w-10 justify-center text-xs font-bold">{p.position}</Badge>
                <div>
                  <p className="font-semibold text-sm">{p.player}</p>
                  <p className="text-xs text-muted-foreground">{p.team}</p>
                </div>
              </div>
              <div className="text-right">
                <p className="font-bold text-primary">{p.fantasyPoints.toLocaleString()}</p>
                <p className="text-[10px] text-muted-foreground">FPTS</p>
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold">Season All-Star Teams</h3>
          <p className="text-sm text-muted-foreground">Best performing lineup at each position</p>
        </div>
        <Select value={selectedSeason} onValueChange={setSelectedSeason}>
          <SelectTrigger className="w-40">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {allStarTeams.map(s => (
              <SelectItem key={s.season} value={s.season}>{s.season}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className="grid md:grid-cols-2 gap-6">
        {renderTeam("1st Team All-Stars", seasonData.firstTeam, true)}
        {renderTeam("2nd Team All-Stars", seasonData.secondTeam, false)}
      </div>
    </div>
  );
};

const LeagueHistory = () => {
  return (
    <AppLayout>
      <div className="container py-8">
        <div className="mb-8 animate-fade-in">
          <h1 className="text-3xl font-bold mb-2 flex items-center gap-3">
            <Trophy className="h-8 w-8 text-primary" />
            League History
          </h1>
          <p className="text-muted-foreground">
            Celebrating 8 seasons of dynasty hockey excellence
          </p>
        </div>

        <Tabs defaultValue="lifetime" className="space-y-6">
          <TabsList className="grid w-full grid-cols-6 lg:w-auto lg:inline-grid">
            <TabsTrigger value="lifetime" className="flex items-center gap-2">
              <Users className="h-4 w-4" />
              Lifetime Records
            </TabsTrigger>
            <TabsTrigger value="records" className="flex items-center gap-2">
              <Target className="h-4 w-4" />
              League Records
            </TabsTrigger>
            <TabsTrigger value="statrecords" className="flex items-center gap-2">
              <BarChart3 className="h-4 w-4" />
              Stat Records
            </TabsTrigger>
            <TabsTrigger value="awards" className="flex items-center gap-2">
              <Award className="h-4 w-4" />
              Player Awards
            </TabsTrigger>
            <TabsTrigger value="allstars" className="flex items-center gap-2">
              <Stars className="h-4 w-4" />
              All-Star Teams
            </TabsTrigger>
            <TabsTrigger value="halloffame" className="flex items-center gap-2">
              <Crown className="h-4 w-4" />
              Hall of Fame
            </TabsTrigger>
          </TabsList>

          {/* Lifetime Records Tab */}
          <TabsContent value="lifetime" className="space-y-6">
            <Card className="bg-card/50 backdrop-blur border-border/50">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Users className="h-5 w-5 text-primary" />
                  All-Time Team Standings
                </CardTitle>
                <CardDescription>
                  Lifetime performance records for all franchise owners
                </CardDescription>
              </CardHeader>
              <CardContent>
              <div className="flex flex-wrap gap-4 mb-4 text-sm text-muted-foreground">
                <span className="flex items-center gap-1">🏆 Championship</span>
                <span className="flex items-center gap-1">🏅 President's Trophy</span>
                <span className="flex items-center gap-1">🥇 Division Win</span>
              </div>
              <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="w-12">Rank</TableHead>
                      <TableHead>Team</TableHead>
                      <TableHead className="text-center">Seasons</TableHead>
                      <TableHead className="text-center">W</TableHead>
                      <TableHead className="text-center">L</TableHead>
                      <TableHead className="text-center">Win %</TableHead>
                      <TableHead className="text-right">Total Pts</TableHead>
                      <TableHead className="text-center">🏆</TableHead>
                      <TableHead className="text-center" title="President's Trophy">🏅</TableHead>
                      <TableHead className="text-center" title="Division Wins">🥇</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {lifetimeTeamRecords.map((team) => (
                      <TableRow key={team.rank} className={team.rank <= 3 ? "bg-primary/5" : ""}>
                        <TableCell>
                          {team.rank <= 3 ? (
                            <Badge variant={team.rank === 1 ? "default" : "secondary"} className={
                              team.rank === 1 ? "bg-yellow-500/20 text-yellow-500" :
                              team.rank === 2 ? "bg-gray-400/20 text-gray-400" :
                              "bg-amber-600/20 text-amber-600"
                            }>
                              #{team.rank}
                            </Badge>
                          ) : (
                            <span className="text-muted-foreground">#{team.rank}</span>
                          )}
                        </TableCell>
                        <TableCell className="font-medium">{team.team}</TableCell>
                        <TableCell className="text-center">{team.seasons}</TableCell>
                        <TableCell className="text-center text-green-500">{team.wins}</TableCell>
                        <TableCell className="text-center text-red-500">{team.losses}</TableCell>
                        <TableCell className="text-center">{team.winPct}</TableCell>
                        <TableCell className="text-right font-semibold">{team.totalPoints.toLocaleString()}</TableCell>
                        <TableCell className="text-center">
                          {team.championships > 0 ? (
                            <span className="text-yellow-500">{"🏆".repeat(team.championships)}</span>
                          ) : (
                            <span className="text-muted-foreground">-</span>
                          )}
                        </TableCell>
                        <TableCell className="text-center">
                          {team.presidentsTrophies > 0 ? (
                            <span>{"🏅".repeat(team.presidentsTrophies)}</span>
                          ) : (
                            <span className="text-muted-foreground">-</span>
                          )}
                        </TableCell>
                        <TableCell className="text-center">
                          {team.divisionWins > 0 ? (
                            <span>{"🥇".repeat(team.divisionWins)}</span>
                          ) : (
                            <span className="text-muted-foreground">-</span>
                          )}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          </TabsContent>

          {/* League Records Tab */}
          <TabsContent value="records" className="space-y-6">
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
              <Card className="bg-card/50 backdrop-blur border-border/50">
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium flex items-center gap-2">
                    <TrendingUp className="h-4 w-4 text-green-500" />
                    Highest Season Points
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="text-2xl font-bold text-green-500">{leagueRecords.highestSeasonPoints.value.toLocaleString()}</div>
                  <p className="text-sm text-muted-foreground">{leagueRecords.highestSeasonPoints.team}</p>
                  <Badge variant="outline" className="mt-2">{leagueRecords.highestSeasonPoints.season}</Badge>
                </CardContent>
              </Card>

              <Card className="bg-card/50 backdrop-blur border-border/50">
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium flex items-center gap-2">
                    <TrendingDown className="h-4 w-4 text-red-500" />
                    Lowest Season Points
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="text-2xl font-bold text-red-500">{leagueRecords.lowestSeasonPoints.value.toLocaleString()}</div>
                  <p className="text-sm text-muted-foreground">{leagueRecords.lowestSeasonPoints.team}</p>
                  <Badge variant="outline" className="mt-2">{leagueRecords.lowestSeasonPoints.season}</Badge>
                </CardContent>
              </Card>

              <Card className="bg-card/50 backdrop-blur border-border/50">
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium flex items-center gap-2">
                    <Trophy className="h-4 w-4 text-yellow-500" />
                    Most Championships
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="text-2xl font-bold text-yellow-500">{leagueRecords.mostChampionships.value}</div>
                  <p className="text-sm text-muted-foreground">{leagueRecords.mostChampionships.team}</p>
                  <div className="flex flex-wrap gap-1 mt-2">
                    {leagueRecords.mostChampionships.seasons.map((s) => (
                      <Badge key={s} variant="outline" className="text-xs">{s}</Badge>
                    ))}
                  </div>
                </CardContent>
              </Card>

              <Card className="bg-card/50 backdrop-blur border-border/50">
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium flex items-center gap-2">
                    <Award className="h-4 w-4 text-green-500" />
                    Best Season Record
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="text-2xl font-bold text-green-500">{leagueRecords.bestWinLossRecord.value}</div>
                  <p className="text-sm text-muted-foreground">{leagueRecords.bestWinLossRecord.team}</p>
                  <Badge variant="outline" className="mt-2">{leagueRecords.bestWinLossRecord.season}</Badge>
                </CardContent>
              </Card>

              <Card className="bg-card/50 backdrop-blur border-border/50">
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium flex items-center gap-2">
                    <TrendingDown className="h-4 w-4 text-red-500" />
                    Worst Season Record
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="text-2xl font-bold text-red-500">{leagueRecords.worstWinLossRecord.value}</div>
                  <p className="text-sm text-muted-foreground">{leagueRecords.worstWinLossRecord.team}</p>
                  <Badge variant="outline" className="mt-2">{leagueRecords.worstWinLossRecord.season}</Badge>
                </CardContent>
              </Card>

              <Card className="bg-card/50 backdrop-blur border-border/50">
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium flex items-center gap-2">
                    <Target className="h-4 w-4 text-primary" />
                    Longest Win Streak
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="text-2xl font-bold text-primary">{leagueRecords.longestWinStreak.value} games</div>
                  <p className="text-sm text-muted-foreground">{leagueRecords.longestWinStreak.team}</p>
                  <Badge variant="outline" className="mt-2">{leagueRecords.longestWinStreak.season}</Badge>
                </CardContent>
              </Card>

              <Card className="bg-card/50 backdrop-blur border-border/50 md:col-span-2 lg:col-span-3">
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium flex items-center gap-2">
                    <TrendingUp className="h-4 w-4 text-primary" />
                    Highest Single Week Score
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="text-2xl font-bold text-primary">{leagueRecords.highestSingleWeek.value} pts</div>
                  <p className="text-sm text-muted-foreground">{leagueRecords.highestSingleWeek.team}</p>
                  <Badge variant="outline" className="mt-2">{leagueRecords.highestSingleWeek.week}</Badge>
                </CardContent>
              </Card>
            </div>
          </TabsContent>

          {/* Stat Records Tab */}
          <TabsContent value="statrecords" className="space-y-6">
            <div className="grid gap-6 lg:grid-cols-2">
              {/* Weekly Matchup Records */}
              <Card className="bg-card/50 backdrop-blur border-border/50">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <Calendar className="h-5 w-5 text-primary" />
                    Weekly Matchup Records
                  </CardTitle>
                  <CardDescription>
                    Single-week record performances by scoring category
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Category</TableHead>
                        <TableHead className="text-right">Record</TableHead>
                        <TableHead>Player</TableHead>
                        <TableHead className="hidden md:table-cell">Team</TableHead>
                        <TableHead className="hidden sm:table-cell text-right">When</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {weeklyMatchupRecords.map((rec) => (
                        <TableRow key={rec.abbr}>
                          <TableCell>
                            <div className="flex items-center gap-2">
                              <Badge variant="outline" className="font-mono text-xs">{rec.abbr}</Badge>
                              <span className="text-xs text-muted-foreground hidden lg:inline">{rec.category}</span>
                            </div>
                          </TableCell>
                          <TableCell className="text-right font-bold text-primary">{rec.record.toLocaleString()}</TableCell>
                          <TableCell className="font-medium">{rec.player}</TableCell>
                          <TableCell className="hidden md:table-cell text-muted-foreground text-sm">{rec.team}</TableCell>
                          <TableCell className="hidden sm:table-cell text-right">
                            <Badge variant="outline" className="text-xs">{rec.context}</Badge>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </CardContent>
              </Card>

              {/* Season Records */}
              <Card className="bg-card/50 backdrop-blur border-border/50">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <BarChart3 className="h-5 w-5 text-accent" />
                    Season Records
                  </CardTitle>
                  <CardDescription>
                    Full-season record totals by scoring category
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Category</TableHead>
                        <TableHead className="text-right">Record</TableHead>
                        <TableHead>Player</TableHead>
                        <TableHead className="hidden md:table-cell">Team</TableHead>
                        <TableHead className="hidden sm:table-cell text-right">Season</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {seasonRecords.map((rec) => (
                        <TableRow key={rec.abbr}>
                          <TableCell>
                            <div className="flex items-center gap-2">
                              <Badge variant="outline" className="font-mono text-xs">{rec.abbr}</Badge>
                              <span className="text-xs text-muted-foreground hidden lg:inline">{rec.category}</span>
                            </div>
                          </TableCell>
                          <TableCell className="text-right font-bold text-accent">{rec.record.toLocaleString()}</TableCell>
                          <TableCell className="font-medium">{rec.player}</TableCell>
                          <TableCell className="hidden md:table-cell text-muted-foreground text-sm">{rec.team}</TableCell>
                          <TableCell className="hidden sm:table-cell text-right">
                            <Badge variant="outline" className="text-xs">{rec.context}</Badge>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </CardContent>
              </Card>
            </div>
          </TabsContent>

          {/* Hall of Fame Tab */}
          <TabsContent value="halloffame" className="space-y-6">
            <div className="grid gap-6 lg:grid-cols-2">
              <Card className="bg-card/50 backdrop-blur border-border/50">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <Crown className="h-5 w-5 text-yellow-500" />
                    Skaters - All-Time Point Production
                  </CardTitle>
                  <CardDescription>
                    Top 10 skaters by lifetime fantasy points
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className="w-12">#</TableHead>
                        <TableHead>Player</TableHead>
                        <TableHead className="text-center">Pos</TableHead>
                        <TableHead className="text-right">Total Pts</TableHead>
                        <TableHead className="text-right">Best Szn</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {hallOfFameSkaters.map((player) => (
                        <TableRow key={player.rank} className={player.rank <= 3 ? "bg-primary/5" : ""}>
                          <TableCell>
                            {player.rank <= 3 ? (
                              <span className={
                                player.rank === 1 ? "text-yellow-500 font-bold" :
                                player.rank === 2 ? "text-gray-400 font-bold" :
                                "text-amber-600 font-bold"
                              }>
                                {player.rank === 1 ? "🥇" : player.rank === 2 ? "🥈" : "🥉"}
                              </span>
                            ) : (
                              <span className="text-muted-foreground">{player.rank}</span>
                            )}
                          </TableCell>
                          <TableCell className="font-medium">{player.player}</TableCell>
                          <TableCell className="text-center">
                            <Badge variant="outline">{player.position}</Badge>
                          </TableCell>
                          <TableCell className="text-right font-semibold">{player.totalPoints.toLocaleString()}</TableCell>
                          <TableCell className="text-right text-muted-foreground">{player.bestSeason}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </CardContent>
              </Card>

              <Card className="bg-card/50 backdrop-blur border-border/50">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <Crown className="h-5 w-5 text-yellow-500" />
                    Goalies - All-Time Point Production
                  </CardTitle>
                  <CardDescription>
                    Top 5 goalies by lifetime fantasy points
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className="w-12">#</TableHead>
                        <TableHead>Player</TableHead>
                        <TableHead className="text-right">Total Pts</TableHead>
                        <TableHead className="text-right">Wins</TableHead>
                        <TableHead className="text-right">Best Szn</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {hallOfFameGoalies.map((player) => (
                        <TableRow key={player.rank} className={player.rank <= 3 ? "bg-primary/5" : ""}>
                          <TableCell>
                            {player.rank <= 3 ? (
                              <span className={
                                player.rank === 1 ? "text-yellow-500 font-bold" :
                                player.rank === 2 ? "text-gray-400 font-bold" :
                                "text-amber-600 font-bold"
                              }>
                                {player.rank === 1 ? "🥇" : player.rank === 2 ? "🥈" : "🥉"}
                              </span>
                            ) : (
                              <span className="text-muted-foreground">{player.rank}</span>
                            )}
                          </TableCell>
                          <TableCell className="font-medium">{player.player}</TableCell>
                          <TableCell className="text-right font-semibold">{player.totalPoints.toLocaleString()}</TableCell>
                          <TableCell className="text-right text-green-500">{player.wins}</TableCell>
                          <TableCell className="text-right text-muted-foreground">{player.bestSeason}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </CardContent>
              </Card>
            </div>
          </TabsContent>

          {/* All-Star Teams Tab */}
          <TabsContent value="allstars" className="space-y-6">
            <AllStarTeamsSection />
          </TabsContent>

          {/* Player Awards Tab */}
          <TabsContent value="awards" className="space-y-6">
            <div className="grid gap-6">
              {playerAwards.map((award) => {
                const mostWins = award.winners.reduce<Record<string, number>>((acc, w) => {
                  acc[w.player] = (acc[w.player] || 0) + 1;
                  return acc;
                }, {});
                const topWinner = Object.entries(mostWins).sort((a, b) => b[1] - a[1])[0];

                return (
                  <Card key={award.name} className="bg-card/50 backdrop-blur border-border/50">
                    <CardHeader>
                      <div className="flex items-start justify-between">
                        <div>
                          <CardTitle className="flex items-center gap-2">
                            {award.icon}
                            {award.name}
                          </CardTitle>
                          <CardDescription>{award.description}</CardDescription>
                        </div>
                        {topWinner && topWinner[1] > 1 && (
                          <Badge variant="outline" className="shrink-0 border-primary/30 text-primary">
                            {topWinner[0]} — {topWinner[1]}x winner
                          </Badge>
                        )}
                      </div>
                    </CardHeader>
                    <CardContent>
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead>Season</TableHead>
                            <TableHead>Player</TableHead>
                            <TableHead className="text-center">Pos</TableHead>
                            <TableHead>Fantasy Team</TableHead>
                            <TableHead className="text-right">Fantasy Points</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {award.winners.map((w, i) => (
                            <TableRow key={w.season} className={i === 0 ? "bg-primary/5" : ""}>
                              <TableCell>
                                <Badge variant={i === 0 ? "default" : "outline"} className={i === 0 ? "bg-primary/20 text-primary" : ""}>
                                  {w.season}
                                </Badge>
                              </TableCell>
                              <TableCell className="font-medium">{w.player}</TableCell>
                              <TableCell className="text-center">
                                <Badge variant="outline">{w.position}</Badge>
                              </TableCell>
                              <TableCell className="text-muted-foreground">{w.team}</TableCell>
                              <TableCell className="text-right font-semibold">{w.fantasyPoints.toLocaleString()}</TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </CardContent>
                  </Card>
                );
              })}
            </div>
          </TabsContent>
        </Tabs>
      </div>
    </AppLayout>
  );
};

export default LeagueHistory;
