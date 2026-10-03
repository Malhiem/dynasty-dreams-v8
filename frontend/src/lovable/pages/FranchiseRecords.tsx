// @ts-nocheck
import { AppLayout } from "@/components/layout/AppLayout";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Trophy, TrendingUp, TrendingDown, Target, Medal, Users, Calendar, Star } from "lucide-react";

// Mock data for franchise records
const franchiseOverview = {
  teamName: "Team Frostbite",
  established: "2016-17",
  owner: "You",
  totalSeasons: 8,
  totalWins: 89,
  totalLosses: 47,
  winPercentage: ".654",
  championships: 3,
  playoffAppearances: 7,
  lifetimePoints: 52100,
  leagueRank: 1,
};

const seasonBySeasonRecords = [
  { season: "2023-24", wins: 14, losses: 3, points: 8240, finish: "1st 🏆", playoff: "Champion" },
  { season: "2022-23", wins: 12, losses: 5, points: 7890, finish: "1st 🏆", playoff: "Champion" },
  { season: "2021-22", wins: 11, losses: 6, points: 6720, finish: "2nd", playoff: "Finals" },
  { season: "2020-21", wins: 10, losses: 7, points: 6480, finish: "3rd", playoff: "Semis" },
  { season: "2019-20", wins: 13, losses: 4, points: 7650, finish: "1st 🏆", playoff: "Champion" },
  { season: "2018-19", wins: 9, losses: 8, points: 5890, finish: "4th", playoff: "Quarters" },
  { season: "2017-18", wins: 11, losses: 6, points: 5120, finish: "2nd", playoff: "Finals" },
  { season: "2016-17", wins: 9, losses: 8, points: 4110, finish: "5th", playoff: "Quarters" },
];

const franchiseRecordStats = {
  highestSeasonPoints: { value: 8240, season: "2023-24" },
  lowestSeasonPoints: { value: 4110, season: "2016-17" },
  bestRecord: { value: "14-3", season: "2023-24" },
  worstRecord: { value: "9-8", season: "2016-17" },
  longestWinStreak: { value: 7, season: "2022-23" },
  longestLossStreak: { value: 3, season: "2018-19" },
  highestWeekScore: { value: 856, week: "Week 14, 2023-24" },
  lowestWeekScore: { value: 312, week: "Week 3, 2016-17" },
};

const franchisePlayerRecords = {
  mostFantasyPoints: [
    { player: "Connor McDavid", position: "C", seasons: "2020-24", total: 1890, perGame: 8.4 },
    { player: "Nathan MacKinnon", position: "C", seasons: "2018-22", total: 1560, perGame: 7.2 },
    { player: "Leon Draisaitl", position: "C", seasons: "2019-23", total: 1480, perGame: 7.0 },
    { player: "Nikita Kucherov", position: "RW", seasons: "2017-21", total: 1320, perGame: 6.5 },
    { player: "Cale Makar", position: "D", seasons: "2021-24", total: 1180, perGame: 6.8 },
  ],
  mostGoals: [
    { player: "Connor McDavid", value: 142, seasons: "2020-24" },
    { player: "Auston Matthews", value: 128, seasons: "2019-22" },
    { player: "Leon Draisaitl", value: 118, seasons: "2019-23" },
    { player: "David Pastrnak", value: 98, seasons: "2018-21" },
    { player: "Alex Ovechkin", value: 92, seasons: "2016-19" },
  ],
  mostAssists: [
    { player: "Connor McDavid", value: 198, seasons: "2020-24" },
    { player: "Nathan MacKinnon", value: 172, seasons: "2018-22" },
    { player: "Leon Draisaitl", value: 156, seasons: "2019-23" },
    { player: "Mitch Marner", value: 142, seasons: "2020-23" },
    { player: "Nikita Kucherov", value: 138, seasons: "2017-21" },
  ],
  mostPoints: [
    { player: "Connor McDavid", value: 340, seasons: "2020-24" },
    { player: "Leon Draisaitl", value: 274, seasons: "2019-23" },
    { player: "Nathan MacKinnon", value: 262, seasons: "2018-22" },
    { player: "Nikita Kucherov", value: 228, seasons: "2017-21" },
    { player: "Auston Matthews", value: 218, seasons: "2019-22" },
  ],
  bestSingleSeason: [
    { player: "Connor McDavid", season: "2023-24", points: 612, goals: 48, assists: 89 },
    { player: "Nathan MacKinnon", season: "2021-22", points: 534, goals: 42, assists: 76 },
    { player: "Leon Draisaitl", season: "2022-23", points: 498, goals: 38, assists: 72 },
    { player: "Nikita Kucherov", season: "2020-21", points: 476, goals: 34, assists: 68 },
    { player: "Cale Makar", season: "2023-24", points: 456, goals: 22, assists: 62 },
  ],
};

const FranchiseRecords = () => {
  return (
    <AppLayout>
      <div className="container py-8">
        <div className="mb-8 animate-fade-in">
          <h1 className="text-3xl font-bold mb-2 flex items-center gap-3">
            <Medal className="h-8 w-8 text-primary" />
            Franchise Records
          </h1>
          <p className="text-muted-foreground">
            Your complete franchise history and player records
          </p>
        </div>

        {/* Franchise Overview */}
        <Card className="bg-card/50 backdrop-blur border-border/50 mb-8">
          <CardHeader>
            <CardTitle className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Star className="h-5 w-5 text-yellow-500" />
                {franchiseOverview.teamName}
              </div>
              <div className="flex gap-2">
                {franchiseOverview.championships > 0 && (
                  <Badge className="bg-yellow-500/20 text-yellow-500">
                    {"🏆".repeat(franchiseOverview.championships)} {franchiseOverview.championships}x Champion
                  </Badge>
                )}
                <Badge variant="outline">Est. {franchiseOverview.established}</Badge>
              </div>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-4">
              <div className="text-center p-3 rounded-lg bg-secondary/50">
                <div className="text-2xl font-bold text-primary">{franchiseOverview.totalSeasons}</div>
                <div className="text-xs text-muted-foreground">Seasons</div>
              </div>
              <div className="text-center p-3 rounded-lg bg-secondary/50">
                <div className="text-2xl font-bold text-green-500">{franchiseOverview.totalWins}</div>
                <div className="text-xs text-muted-foreground">Wins</div>
              </div>
              <div className="text-center p-3 rounded-lg bg-secondary/50">
                <div className="text-2xl font-bold text-red-500">{franchiseOverview.totalLosses}</div>
                <div className="text-xs text-muted-foreground">Losses</div>
              </div>
              <div className="text-center p-3 rounded-lg bg-secondary/50">
                <div className="text-2xl font-bold">{franchiseOverview.winPercentage}</div>
                <div className="text-xs text-muted-foreground">Win %</div>
              </div>
              <div className="text-center p-3 rounded-lg bg-secondary/50">
                <div className="text-2xl font-bold text-yellow-500">{franchiseOverview.championships}</div>
                <div className="text-xs text-muted-foreground">Championships</div>
              </div>
              <div className="text-center p-3 rounded-lg bg-secondary/50">
                <div className="text-2xl font-bold">{franchiseOverview.playoffAppearances}</div>
                <div className="text-xs text-muted-foreground">Playoffs</div>
              </div>
              <div className="text-center p-3 rounded-lg bg-secondary/50">
                <div className="text-2xl font-bold text-primary">{franchiseOverview.lifetimePoints.toLocaleString()}</div>
                <div className="text-xs text-muted-foreground">Lifetime Pts</div>
              </div>
            </div>
          </CardContent>
        </Card>

        <Tabs defaultValue="seasons" className="space-y-6">
          <TabsList className="grid w-full grid-cols-3 lg:w-auto lg:inline-grid">
            <TabsTrigger value="seasons" className="flex items-center gap-2">
              <Calendar className="h-4 w-4" />
              Season History
            </TabsTrigger>
            <TabsTrigger value="records" className="flex items-center gap-2">
              <Target className="h-4 w-4" />
              Franchise Records
            </TabsTrigger>
            <TabsTrigger value="players" className="flex items-center gap-2">
              <Users className="h-4 w-4" />
              Player Records
            </TabsTrigger>
          </TabsList>

          {/* Season History Tab */}
          <TabsContent value="seasons" className="space-y-6">
            <Card className="bg-card/50 backdrop-blur border-border/50">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Calendar className="h-5 w-5 text-primary" />
                  Season-by-Season Breakdown
                </CardTitle>
                <CardDescription>
                  Your franchise performance across all seasons
                </CardDescription>
              </CardHeader>
              <CardContent>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Season</TableHead>
                      <TableHead className="text-center">W</TableHead>
                      <TableHead className="text-center">L</TableHead>
                      <TableHead className="text-right">Points</TableHead>
                      <TableHead className="text-center">Finish</TableHead>
                      <TableHead>Playoffs</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {seasonBySeasonRecords.map((season) => (
                      <TableRow key={season.season} className={season.playoff === "Champion" ? "bg-yellow-500/5" : ""}>
                        <TableCell className="font-medium">{season.season}</TableCell>
                        <TableCell className="text-center text-green-500">{season.wins}</TableCell>
                        <TableCell className="text-center text-red-500">{season.losses}</TableCell>
                        <TableCell className="text-right font-semibold">{season.points.toLocaleString()}</TableCell>
                        <TableCell className="text-center">{season.finish}</TableCell>
                        <TableCell>
                          <Badge variant={season.playoff === "Champion" ? "default" : "outline"}
                            className={season.playoff === "Champion" ? "bg-yellow-500/20 text-yellow-500" : ""}>
                            {season.playoff}
                          </Badge>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          </TabsContent>

          {/* Franchise Records Tab */}
          <TabsContent value="records" className="space-y-6">
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
              <Card className="bg-card/50 backdrop-blur border-border/50">
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium flex items-center gap-2">
                    <TrendingUp className="h-4 w-4 text-green-500" />
                    Highest Season Points
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="text-2xl font-bold text-green-500">{franchiseRecordStats.highestSeasonPoints.value.toLocaleString()}</div>
                  <Badge variant="outline" className="mt-2">{franchiseRecordStats.highestSeasonPoints.season}</Badge>
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
                  <div className="text-2xl font-bold text-red-500">{franchiseRecordStats.lowestSeasonPoints.value.toLocaleString()}</div>
                  <Badge variant="outline" className="mt-2">{franchiseRecordStats.lowestSeasonPoints.season}</Badge>
                </CardContent>
              </Card>

              <Card className="bg-card/50 backdrop-blur border-border/50">
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium flex items-center gap-2">
                    <Trophy className="h-4 w-4 text-green-500" />
                    Best Season Record
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="text-2xl font-bold text-green-500">{franchiseRecordStats.bestRecord.value}</div>
                  <Badge variant="outline" className="mt-2">{franchiseRecordStats.bestRecord.season}</Badge>
                </CardContent>
              </Card>

              <Card className="bg-card/50 backdrop-blur border-border/50">
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium flex items-center gap-2">
                    <Target className="h-4 w-4 text-red-500" />
                    Worst Season Record
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="text-2xl font-bold text-red-500">{franchiseRecordStats.worstRecord.value}</div>
                  <Badge variant="outline" className="mt-2">{franchiseRecordStats.worstRecord.season}</Badge>
                </CardContent>
              </Card>

              <Card className="bg-card/50 backdrop-blur border-border/50">
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium flex items-center gap-2">
                    <TrendingUp className="h-4 w-4 text-primary" />
                    Longest Win Streak
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="text-2xl font-bold text-primary">{franchiseRecordStats.longestWinStreak.value} games</div>
                  <Badge variant="outline" className="mt-2">{franchiseRecordStats.longestWinStreak.season}</Badge>
                </CardContent>
              </Card>

              <Card className="bg-card/50 backdrop-blur border-border/50">
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium flex items-center gap-2">
                    <TrendingDown className="h-4 w-4 text-muted-foreground" />
                    Longest Loss Streak
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="text-2xl font-bold text-muted-foreground">{franchiseRecordStats.longestLossStreak.value} games</div>
                  <Badge variant="outline" className="mt-2">{franchiseRecordStats.longestLossStreak.season}</Badge>
                </CardContent>
              </Card>

              <Card className="bg-card/50 backdrop-blur border-border/50">
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium flex items-center gap-2">
                    <TrendingUp className="h-4 w-4 text-green-500" />
                    Highest Week Score
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="text-2xl font-bold text-green-500">{franchiseRecordStats.highestWeekScore.value}</div>
                  <p className="text-xs text-muted-foreground mt-1">{franchiseRecordStats.highestWeekScore.week}</p>
                </CardContent>
              </Card>

              <Card className="bg-card/50 backdrop-blur border-border/50">
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium flex items-center gap-2">
                    <TrendingDown className="h-4 w-4 text-red-500" />
                    Lowest Week Score
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="text-2xl font-bold text-red-500">{franchiseRecordStats.lowestWeekScore.value}</div>
                  <p className="text-xs text-muted-foreground mt-1">{franchiseRecordStats.lowestWeekScore.week}</p>
                </CardContent>
              </Card>
            </div>
          </TabsContent>

          {/* Player Records Tab */}
          <TabsContent value="players" className="space-y-6">
            <div className="grid gap-6 lg:grid-cols-2">
              <Card className="bg-card/50 backdrop-blur border-border/50">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <Star className="h-5 w-5 text-yellow-500" />
                    Most Fantasy Points (Franchise Career)
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className="w-12">#</TableHead>
                        <TableHead>Player</TableHead>
                        <TableHead className="text-center">Pos</TableHead>
                        <TableHead className="text-right">Total</TableHead>
                        <TableHead className="text-right">PPG</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {franchisePlayerRecords.mostFantasyPoints.map((player, idx) => (
                        <TableRow key={player.player}>
                          <TableCell className="font-medium">{idx + 1}</TableCell>
                          <TableCell>{player.player}</TableCell>
                          <TableCell className="text-center"><Badge variant="outline">{player.position}</Badge></TableCell>
                          <TableCell className="text-right font-semibold">{player.total.toLocaleString()}</TableCell>
                          <TableCell className="text-right text-muted-foreground">{player.perGame}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </CardContent>
              </Card>

              <Card className="bg-card/50 backdrop-blur border-border/50">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <Target className="h-5 w-5 text-primary" />
                    Best Single Season
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className="w-12">#</TableHead>
                        <TableHead>Player</TableHead>
                        <TableHead className="text-center">Season</TableHead>
                        <TableHead className="text-right">FPts</TableHead>
                        <TableHead className="text-right">G-A</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {franchisePlayerRecords.bestSingleSeason.map((player, idx) => (
                        <TableRow key={`${player.player}-${player.season}`}>
                          <TableCell className="font-medium">{idx + 1}</TableCell>
                          <TableCell>{player.player}</TableCell>
                          <TableCell className="text-center"><Badge variant="outline">{player.season}</Badge></TableCell>
                          <TableCell className="text-right font-semibold">{player.points}</TableCell>
                          <TableCell className="text-right text-muted-foreground">{player.goals}-{player.assists}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </CardContent>
              </Card>

              <Card className="bg-card/50 backdrop-blur border-border/50">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <TrendingUp className="h-5 w-5 text-green-500" />
                    Most Goals with Franchise
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className="w-12">#</TableHead>
                        <TableHead>Player</TableHead>
                        <TableHead className="text-right">Goals</TableHead>
                        <TableHead>Tenure</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {franchisePlayerRecords.mostGoals.map((player, idx) => (
                        <TableRow key={player.player}>
                          <TableCell className="font-medium">{idx + 1}</TableCell>
                          <TableCell>{player.player}</TableCell>
                          <TableCell className="text-right font-semibold text-green-500">{player.value}</TableCell>
                          <TableCell className="text-muted-foreground">{player.seasons}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </CardContent>
              </Card>

              <Card className="bg-card/50 backdrop-blur border-border/50">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <Users className="h-5 w-5 text-primary" />
                    Most Assists with Franchise
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className="w-12">#</TableHead>
                        <TableHead>Player</TableHead>
                        <TableHead className="text-right">Assists</TableHead>
                        <TableHead>Tenure</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {franchisePlayerRecords.mostAssists.map((player, idx) => (
                        <TableRow key={player.player}>
                          <TableCell className="font-medium">{idx + 1}</TableCell>
                          <TableCell>{player.player}</TableCell>
                          <TableCell className="text-right font-semibold text-primary">{player.value}</TableCell>
                          <TableCell className="text-muted-foreground">{player.seasons}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </CardContent>
              </Card>

              <Card className="bg-card/50 backdrop-blur border-border/50 lg:col-span-2">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <Medal className="h-5 w-5 text-yellow-500" />
                    Most Points (G+A) with Franchise
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className="w-12">#</TableHead>
                        <TableHead>Player</TableHead>
                        <TableHead className="text-right">Points</TableHead>
                        <TableHead>Tenure</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {franchisePlayerRecords.mostPoints.map((player, idx) => (
                        <TableRow key={player.player}>
                          <TableCell className="font-medium">{idx + 1}</TableCell>
                          <TableCell>{player.player}</TableCell>
                          <TableCell className="text-right font-semibold text-yellow-500">{player.value}</TableCell>
                          <TableCell className="text-muted-foreground">{player.seasons}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </CardContent>
              </Card>
            </div>
          </TabsContent>
        </Tabs>
      </div>
    </AppLayout>
  );
};

export default FranchiseRecords;
