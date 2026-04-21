// @ts-nocheck
import { useState, useMemo } from "react";
import { AppLayout } from "@/components/layout/AppLayout";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Dices, Trophy, AlertCircle, CheckCircle2, Shuffle, Scale, ArrowRight, AlertTriangle, Bell } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { cn } from "@/lib/utils";

// ─── NHL Draft Lottery Odds (2024 format, 16 non-playoff teams) ──────────────
// Official NHL odds for the #1 overall pick by standings position
const NHL_LOTTERY_ODDS: Record<number, number> = {
  1: 25.5,
  2: 13.5,
  3: 11.5,
  4: 9.5,
  5: 8.5,
  6: 7.5,
  7: 6.5,
  8: 6.0,
  9: 5.0,
  10: 3.5,
  11: 3.0,
  12: 2.5,
  13: 2.0,
  14: 1.5,
  15: 0.5,
  16: 0.5,
};

// ─── Mock League Teams (eliminated, worst to best) ───────────────────────────
const eliminatedTeams = [
  { name: "Zero Below", abbr: "ZRO", record: "18-42-6", pts: 42 },
  { name: "Snow Hawks", abbr: "SNW", record: "20-40-8", pts: 48 },
  { name: "Polar Phantoms", abbr: "POL", record: "22-38-6", pts: 50 },
  { name: "Tundra Titans", abbr: "TND", record: "24-36-8", pts: 56 },
  { name: "Ice Breakers", abbr: "ICE", record: "26-34-6", pts: 58 },
  { name: "Winter Storm", abbr: "WST", record: "28-32-8", pts: 64 },
];

// ─── Mock NHL Standings (worst to best, non-playoff teams) ───────────────────
const nhlTeams = [
  { name: "San Jose Sharks", abbr: "SJS", pts: 48 },
  { name: "Chicago Blackhawks", abbr: "CHI", pts: 52 },
  { name: "Anaheim Ducks", abbr: "ANA", pts: 56 },
  { name: "Columbus Blue Jackets", abbr: "CBJ", pts: 60 },
  { name: "Montreal Canadiens", abbr: "MTL", pts: 62 },
  { name: "Seattle Kraken", abbr: "SEA", pts: 64 },
  { name: "Philadelphia Flyers", abbr: "PHI", pts: 66 },
  { name: "Pittsburgh Penguins", abbr: "PIT", pts: 68 },
  { name: "Buffalo Sabres", abbr: "BUF", pts: 70 },
  { name: "Detroit Red Wings", abbr: "DET", pts: 72 },
  { name: "New York Islanders", abbr: "NYI", pts: 74 },
  { name: "Ottawa Senators", abbr: "OTT", pts: 76 },
  { name: "Calgary Flames", abbr: "CGY", pts: 78 },
  { name: "St. Louis Blues", abbr: "STL", pts: 80 },
  { name: "Nashville Predators", abbr: "NSH", pts: 82 },
  { name: "Utah Hockey Club", abbr: "UTA", pts: 84 },
];

interface LotteryResult {
  teamIndex: number;
  teamName: string;
  draftPosition: number;
}

export default function DraftLottery() {
  const [nhlFinalized, setNhlFinalized] = useState(true);
  const [lotteryResults, setLotteryResults] = useState<LotteryResult[] | null>(null);
  const [isAnimating, setIsAnimating] = useState(false);

  const numTeams = eliminatedTeams.length;

  // Map NHL teams to league teams round-robin style
  // 1st place lottery team gets NHL positions 1, 1+N, 1+2N, ...
  // 2nd place lottery team gets NHL positions 2, 2+N, 2+2N, ...
  const teamMappings = useMemo(() => {
    return eliminatedTeams.map((team, teamIdx) => {
      const assignedNhlIndices: number[] = [];
      for (let i = teamIdx; i < nhlTeams.length; i += numTeams) {
        assignedNhlIndices.push(i);
      }
      const assignedNhlTeams = assignedNhlIndices.map((i) => ({
        ...nhlTeams[i],
        nhlStandingsPos: i + 1,
        odds: NHL_LOTTERY_ODDS[i + 1] || 0,
      }));
      const totalOdds = assignedNhlTeams.reduce((sum, t) => sum + t.odds, 0);
      return {
        ...team,
        nhlRepresentations: assignedNhlTeams,
        totalOdds: Math.round(totalOdds * 10) / 10,
      };
    });
  }, [numTeams]);

  // Run the lottery simulation
  const runLottery = () => {
    setIsAnimating(true);
    setLotteryResults(null);

    // Simulate weighted lottery based on accumulated odds
    setTimeout(() => {
      const pool = teamMappings.map((t, i) => ({ index: i, name: t.name, odds: t.totalOdds }));
      const results: LotteryResult[] = [];
      const remaining = [...pool];

      // Draw positions 1 through numTeams
      for (let pos = 1; pos <= numTeams; pos++) {
        const totalWeight = remaining.reduce((s, t) => s + t.odds, 0);
        let roll = Math.random() * totalWeight;
        let winner = remaining[0];
        for (const team of remaining) {
          roll -= team.odds;
          if (roll <= 0) {
            winner = team;
            break;
          }
        }
        results.push({
          teamIndex: winner.index,
          teamName: winner.name,
          draftPosition: pos,
        });
        const idx = remaining.findIndex((t) => t.index === winner.index);
        remaining.splice(idx, 1);
      }

      setLotteryResults(results);
      setIsAnimating(false);
    }, 2000);
  };

  return (
    <AppLayout>
      <div className="space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="h-10 w-10 rounded-xl bg-primary/20 flex items-center justify-center">
              <Dices className="h-5 w-5 text-primary" />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-foreground">Draft Lottery</h1>
              <p className="text-sm text-muted-foreground">
                NHL-weighted lottery to determine draft order for eliminated teams
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <Badge
              variant="outline"
              className={cn(
                "px-3 py-1",
                nhlFinalized
                  ? "border-success/50 text-success"
                  : "border-accent/50 text-accent"
              )}
            >
              {nhlFinalized ? (
                <><CheckCircle2 className="h-3.5 w-3.5 mr-1.5" /> NHL Standings Finalized</>
              ) : (
                <><AlertCircle className="h-3.5 w-3.5 mr-1.5" /> NHL Standings Pending</>
              )}
            </Badge>
            <Button
              onClick={runLottery}
              disabled={isAnimating}
              className="gap-2"
            >
              <Shuffle className="h-4 w-4" />
              {isAnimating ? "Drawing..." : "Run Lottery"}
            </Button>
          </div>
        </div>

        <Tabs defaultValue="lottery" className="w-full">
          <TabsList>
            <TabsTrigger value="lottery">Lottery Pool</TabsTrigger>
            <TabsTrigger value="tiebreakers">Tiebreakers</TabsTrigger>
          </TabsList>

          <TabsContent value="lottery" className="space-y-6 mt-4">
            {/* Lottery Teams & NHL Representation */}
            <Card className="border-border">
              <CardHeader className="pb-3">
                <CardTitle className="text-lg flex items-center gap-2">
                  <Trophy className="h-5 w-5 text-accent" />
                  Lottery Teams &amp; NHL Representation
                </CardTitle>
                <p className="text-sm text-muted-foreground">
                  Each eliminated team is assigned NHL counterparts in round-robin order (worst gets worst). 
                  Odds are accumulated from each NHL team's official lottery probability.
                </p>
              </CardHeader>
              <CardContent>
                <Table>
                  <TableHeader>
                    <TableRow className="border-border hover:bg-transparent">
                      <TableHead className="text-muted-foreground w-12">#</TableHead>
                      <TableHead className="text-muted-foreground">League Team</TableHead>
                      <TableHead className="text-muted-foreground">Record</TableHead>
                      <TableHead className="text-muted-foreground">Pts</TableHead>
                      <TableHead className="text-muted-foreground">NHL Representations</TableHead>
                      <TableHead className="text-muted-foreground text-right">Combined Odds</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {teamMappings.map((team, idx) => (
                      <TableRow key={team.abbr} className="border-border">
                        <TableCell className="font-mono text-muted-foreground">{idx + 1}</TableCell>
                        <TableCell>
                          <div className="flex items-center gap-2">
                            <span className="font-semibold text-foreground">{team.name}</span>
                            <Badge variant="outline" className="text-xs border-border text-muted-foreground">
                              {team.abbr}
                            </Badge>
                          </div>
                        </TableCell>
                        <TableCell className="text-muted-foreground font-mono text-sm">{team.record}</TableCell>
                        <TableCell className="font-semibold text-foreground">{team.pts}</TableCell>
                        <TableCell>
                          <div className="flex flex-wrap gap-1.5">
                            {team.nhlRepresentations.map((nhl) => (
                              <Badge
                                key={nhl.abbr}
                                variant="secondary"
                                className="text-xs font-mono gap-1"
                              >
                                <span className="text-foreground">{nhl.abbr}</span>
                                <span className="text-muted-foreground">#{nhl.nhlStandingsPos}</span>
                                <span className="text-primary">({nhl.odds}%)</span>
                              </Badge>
                            ))}
                          </div>
                        </TableCell>
                        <TableCell className="text-right">
                          <span className="text-lg font-bold text-primary">{team.totalOdds}%</span>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>

            {/* Odds Breakdown Visual */}
            <Card className="border-border">
              <CardHeader className="pb-3">
                <CardTitle className="text-lg">Odds Distribution</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  {teamMappings.map((team) => {
                    const maxOdds = teamMappings[0].totalOdds;
                    const barWidth = (team.totalOdds / maxOdds) * 100;
                    return (
                      <div key={team.abbr} className="flex items-center gap-3">
                        <span className="w-36 text-sm font-medium text-foreground truncate">{team.name}</span>
                        <div className="flex-1 h-8 rounded-lg bg-secondary/50 overflow-hidden relative">
                          <div
                            className="h-full rounded-lg bg-gradient-to-r from-primary/80 to-primary/40 transition-all duration-700"
                            style={{ width: `${barWidth}%` }}
                          />
                          <span className="absolute inset-0 flex items-center px-3 text-sm font-semibold text-foreground">
                            {team.totalOdds}%
                          </span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </CardContent>
            </Card>

            {/* Lottery Animation / Results */}
            {isAnimating && (
              <Card className="border-primary/30 glow-ice">
                <CardContent className="py-12 flex flex-col items-center justify-center gap-4">
                  <Dices className="h-16 w-16 text-primary animate-spin" />
                  <p className="text-xl font-bold text-foreground animate-pulse">Drawing lottery balls...</p>
                  <p className="text-sm text-muted-foreground">Determining draft order</p>
                </CardContent>
              </Card>
            )}

            {lotteryResults && !isAnimating && (
              <Card className="border-primary/30 glow-ice">
                <CardHeader className="pb-3">
                  <CardTitle className="text-lg flex items-center gap-2">
                    <Trophy className="h-5 w-5 text-accent" />
                    Lottery Results
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                    {lotteryResults
                      .sort((a, b) => a.draftPosition - b.draftPosition)
                      .map((result) => {
                        const team = teamMappings[result.teamIndex];
                        const movedUp = result.draftPosition < result.teamIndex + 1;
                        const movedDown = result.draftPosition > result.teamIndex + 1;
                        return (
                          <div
                            key={result.teamName}
                            className={cn(
                              "relative rounded-xl border p-5 flex flex-col items-center gap-2 transition-all",
                              result.draftPosition === 1
                                ? "border-accent/50 bg-accent/5"
                                : "border-border bg-card"
                            )}
                          >
                            {result.draftPosition === 1 && (
                              <div className="absolute -top-3 left-1/2 -translate-x-1/2">
                                <Badge className="bg-accent text-accent-foreground font-bold">
                                  🏆 1ST OVERALL
                                </Badge>
                              </div>
                            )}
                            <span className="text-4xl font-display text-foreground">
                              #{result.draftPosition}
                            </span>
                            <span className="text-lg font-bold text-foreground">{result.teamName}</span>
                            <span className="text-sm text-muted-foreground">
                              Odds: {team.totalOdds}%
                            </span>
                            {movedUp && (
                              <Badge variant="outline" className="text-xs border-success/50 text-success">
                                ▲ Moved up {result.teamIndex + 1 - result.draftPosition}
                              </Badge>
                            )}
                            {movedDown && (
                              <Badge variant="outline" className="text-xs border-destructive/50 text-destructive">
                                ▼ Dropped {result.draftPosition - (result.teamIndex + 1)}
                              </Badge>
                            )}
                            {!movedUp && !movedDown && (
                              <Badge variant="outline" className="text-xs border-border text-muted-foreground">
                                — Held position
                              </Badge>
                            )}
                          </div>
                        );
                      })}
                  </div>
                </CardContent>
              </Card>
            )}

            {/* NHL Lottery Reference */}
            <Card className="border-border">
              <CardHeader className="pb-3">
                <CardTitle className="text-lg">NHL Draft Lottery Odds Reference</CardTitle>
                <p className="text-sm text-muted-foreground">
                  Official NHL lottery probabilities used for weighting
                </p>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-2">
                  {Object.entries(NHL_LOTTERY_ODDS).map(([pos, odds]) => (
                    <div
                      key={pos}
                      className="rounded-lg border border-border bg-secondary/30 p-2.5 text-center"
                    >
                      <div className="text-xs text-muted-foreground">#{pos}</div>
                      <div className="text-sm font-bold text-foreground">{odds}%</div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="tiebreakers" className="space-y-6 mt-4">
            {/* Active Tiebreaker Rules */}
            <Card className="border-border">
              <CardHeader className="pb-3">
                <CardTitle className="text-lg flex items-center gap-2">
                  <Scale className="h-5 w-5 text-accent" />
                  Tiebreaker Rules
                </CardTitle>
                <p className="text-sm text-muted-foreground">
                  When teams finish with identical records, these rules determine draft lottery positioning
                </p>
              </CardHeader>
              <CardContent>
                <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
                  {[
                    { step: "1st", label: "Lowest Points For", description: "Team with fewer total points scored gets higher lottery position" },
                    { step: "2nd", label: "Head-to-Head Record", description: "Season series record between the tied teams" },
                    { step: "3rd", label: "Manual (Administrator)", description: "League Administrator determines order outside the system" },
                  ].map((rule, i) => (
                    <div key={rule.step} className="flex items-center gap-3 flex-1">
                      <div className="flex-1 rounded-xl border border-border bg-card p-4">
                        <div className="flex items-center gap-2 mb-1">
                          <Badge variant="secondary" className="text-xs">{rule.step}</Badge>
                          <span className="font-semibold text-foreground text-sm">{rule.label}</span>
                        </div>
                        <p className="text-xs text-muted-foreground">{rule.description}</p>
                      </div>
                      {i < 2 && <ArrowRight className="h-4 w-4 text-muted-foreground hidden sm:block shrink-0" />}
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>

            {/* Tiebreaker Scenarios Visualization */}
            <Card className="border-border">
              <CardHeader className="pb-3">
                <CardTitle className="text-lg">Tiebreaker Scenarios</CardTitle>
                <p className="text-sm text-muted-foreground">
                  Current teams with identical records and how tiebreakers resolve their lottery order
                </p>
              </CardHeader>
              <CardContent className="space-y-4">
                {/* Tie group 1 */}
                <div className="rounded-xl border border-border bg-secondary/20 p-4 space-y-3">
                  <div className="flex items-center gap-2">
                    <Badge variant="outline" className="border-accent/50 text-accent">Tie Group</Badge>
                    <span className="text-sm font-semibold text-foreground">18-42-6 (42 pts)</span>
                    <span className="text-xs text-muted-foreground">— 1 team</span>
                  </div>
                  <div className="text-sm text-muted-foreground">No tiebreaker needed — only Zero Below holds this record.</div>
                </div>

                {/* Tie group 2: simulated tie */}
                <div className="rounded-xl border border-primary/30 bg-primary/5 p-4 space-y-3">
                  <div className="flex items-center gap-2">
                    <Badge variant="outline" className="border-accent/50 text-accent">Tie Group</Badge>
                    <span className="text-sm font-semibold text-foreground">26-34-6 / 28-32-8 (58–64 pts)</span>
                    <span className="text-xs text-muted-foreground">— Simulated scenario</span>
                  </div>
                  <Table>
                    <TableHeader>
                      <TableRow className="border-border hover:bg-transparent">
                        <TableHead className="text-muted-foreground">Team</TableHead>
                        <TableHead className="text-muted-foreground">Record</TableHead>
                        <TableHead className="text-muted-foreground">Pts</TableHead>
                        <TableHead className="text-muted-foreground">Points For</TableHead>
                        <TableHead className="text-muted-foreground">H2H</TableHead>
                        <TableHead className="text-muted-foreground">Tiebreaker Used</TableHead>
                        <TableHead className="text-muted-foreground text-right">Resolved Position</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      <TableRow className="border-border">
                        <TableCell className="font-semibold text-foreground">Ice Breakers</TableCell>
                        <TableCell className="font-mono text-sm text-muted-foreground">26-34-6</TableCell>
                        <TableCell className="text-foreground">58</TableCell>
                        <TableCell className="text-foreground">412</TableCell>
                        <TableCell className="text-muted-foreground">3-5</TableCell>
                        <TableCell>
                          <Badge variant="secondary" className="text-xs">1st — Lowest PF</Badge>
                        </TableCell>
                        <TableCell className="text-right">
                          <span className="text-lg font-bold text-primary">#5</span>
                        </TableCell>
                      </TableRow>
                      <TableRow className="border-border">
                        <TableCell className="font-semibold text-foreground">Winter Storm</TableCell>
                        <TableCell className="font-mono text-sm text-muted-foreground">28-32-8</TableCell>
                        <TableCell className="text-foreground">64</TableCell>
                        <TableCell className="text-foreground">438</TableCell>
                        <TableCell className="text-muted-foreground">5-3</TableCell>
                        <TableCell>
                          <Badge variant="secondary" className="text-xs">1st — Lowest PF</Badge>
                        </TableCell>
                        <TableCell className="text-right">
                          <span className="text-lg font-bold text-primary">#6</span>
                        </TableCell>
                      </TableRow>
                    </TableBody>
                  </Table>
                  <p className="text-xs text-muted-foreground">
                    Ice Breakers win the tiebreak via 1st tiebreaker (Lowest Points For: 412 vs 438)
                  </p>
                </div>

                {/* Tie group 3: 3rd tiebreaker needed — admin action required */}
                <div className="rounded-xl border border-destructive/40 bg-destructive/5 p-4 space-y-3">
                  <div className="flex items-center gap-2">
                    <Badge variant="outline" className="border-destructive/50 text-destructive">Tie Group — Action Required</Badge>
                    <span className="text-sm font-semibold text-foreground">24-38-4 (52 pts)</span>
                    <span className="text-xs text-muted-foreground">— 2 teams</span>
                  </div>
                  <Alert variant="destructive" className="border-destructive/30 bg-destructive/10">
                    <AlertTriangle className="h-4 w-4" />
                    <AlertTitle className="text-sm font-semibold">League Administrator Decision Required</AlertTitle>
                    <AlertDescription className="text-xs">
                      These teams could not be resolved by the 1st or 2nd tiebreakers. The 3rd tiebreaker is manual — the League Administrator must determine the final draft order positioning for these teams.
                    </AlertDescription>
                  </Alert>
                  <Table>
                    <TableHeader>
                      <TableRow className="border-border hover:bg-transparent">
                        <TableHead className="text-muted-foreground">Team</TableHead>
                        <TableHead className="text-muted-foreground">Record</TableHead>
                        <TableHead className="text-muted-foreground">Pts</TableHead>
                        <TableHead className="text-muted-foreground">Points For</TableHead>
                        <TableHead className="text-muted-foreground">H2H</TableHead>
                        <TableHead className="text-muted-foreground">Tiebreaker Used</TableHead>
                        <TableHead className="text-muted-foreground text-right">Resolved Position</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      <TableRow className="border-border">
                        <TableCell className="font-semibold text-foreground">Polar Vortex</TableCell>
                        <TableCell className="font-mono text-sm text-muted-foreground">24-38-4</TableCell>
                        <TableCell className="text-foreground">52</TableCell>
                        <TableCell className="text-foreground">395</TableCell>
                        <TableCell className="text-muted-foreground">4-4</TableCell>
                        <TableCell>
                          <Badge variant="destructive" className="text-xs">3rd — Manual</Badge>
                        </TableCell>
                        <TableCell className="text-right">
                          <span className="text-sm font-semibold text-destructive">Pending</span>
                        </TableCell>
                      </TableRow>
                      <TableRow className="border-border">
                        <TableCell className="font-semibold text-foreground">Frozen Fury</TableCell>
                        <TableCell className="font-mono text-sm text-muted-foreground">24-38-4</TableCell>
                        <TableCell className="text-foreground">52</TableCell>
                        <TableCell className="text-foreground">395</TableCell>
                        <TableCell className="text-muted-foreground">4-4</TableCell>
                        <TableCell>
                          <Badge variant="destructive" className="text-xs">3rd — Manual</Badge>
                        </TableCell>
                        <TableCell className="text-right">
                          <span className="text-sm font-semibold text-destructive">Pending</span>
                        </TableCell>
                      </TableRow>
                    </TableBody>
                  </Table>
                  <div className="flex items-center gap-2 pt-1">
                    <Bell className="h-4 w-4 text-destructive" />
                    <p className="text-xs text-destructive font-medium">
                      A notification has been sent to the League Administrator to resolve this tiebreaker.
                    </p>
                  </div>
                </div>

                {/* Legend */}
                <div className="flex flex-wrap gap-4 pt-2">
                  <div className="flex items-center gap-2 text-xs text-muted-foreground">
                    <div className="h-3 w-3 rounded-sm bg-primary/20 border border-primary/30" />
                    <span>Active tiebreak scenario</span>
                  </div>
                  <div className="flex items-center gap-2 text-xs text-muted-foreground">
                    <div className="h-3 w-3 rounded-sm bg-secondary/50 border border-border" />
                    <span>No tiebreak needed</span>
                  </div>
                  <div className="flex items-center gap-2 text-xs text-muted-foreground">
                    <div className="h-3 w-3 rounded-sm bg-destructive/20 border border-destructive/30" />
                    <span>Administrator action required</span>
                  </div>
                </div>
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </div>
    </AppLayout>
  );
}
