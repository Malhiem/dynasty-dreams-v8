// @ts-nocheck
import { AppLayout } from "@/components/layout/AppLayout";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Progress } from "@/components/ui/progress";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Clock, DollarSign, Plus, History, TrendingUp, ChevronDown, ChevronUp } from "lucide-react";
import { useState } from "react";
import TeamLink from "@/lovable/components/TeamLink";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";

interface WaiverPlayer {
  id: number;
  name: string;
  position: string;
  team: string;
  previousOwner?: string;
  clearTime: string;
  weekPoints: number;
  seasonPoints: number;
  percentOwned: number;
  trending: "up" | "down" | "stable";
}

interface WaiverClaim {
  id: number;
  player: string;
  team: string;
  bidAmount: number;
  dropPlayer?: string;
  status: "pending" | "won" | "lost";
  processTime: string;
}

interface ClaimHistory {
  id: number;
  player: string;
  team: string;
  winner: string;
  winningBid: number;
  processedAt: string;
}

const waiverPlayers: WaiverPlayer[] = [
  { id: 1, name: "Jack Hughes", position: "C", team: "NJD", previousOwner: "Ice Crushers", clearTime: "2h 30m", weekPoints: 18.5, seasonPoints: 245, percentOwned: 78, trending: "up" },
  { id: 2, name: "Trevor Zegras", position: "C", team: "ANA", clearTime: "2h 30m", weekPoints: 12.2, seasonPoints: 189, percentOwned: 45, trending: "stable" },
  { id: 3, name: "Moritz Seider", position: "D", team: "DET", previousOwner: "Puck Masters", clearTime: "1d 2h", weekPoints: 8.4, seasonPoints: 156, percentOwned: 62, trending: "up" },
  { id: 4, name: "Jake Oettinger", position: "G", team: "DAL", clearTime: "1d 2h", weekPoints: 14.0, seasonPoints: 142, percentOwned: 55, trending: "down" },
];

const myClaims: WaiverClaim[] = [
  { id: 1, player: "Jack Hughes", team: "NJD", bidAmount: 25, dropPlayer: "Tage Thompson", status: "pending", processTime: "2h 30m" },
  { id: 2, player: "Moritz Seider", team: "DET", bidAmount: 15, status: "pending", processTime: "1d 2h" },
];

const claimHistory: ClaimHistory[] = [
  { id: 1, player: "Marco Rossi", team: "MIN", winner: "Glacier Kings", winningBid: 12, processedAt: "Yesterday" },
  { id: 2, player: "Kevin Fiala", team: "LAK", winner: "Team Frostbite", winningBid: 18, processedAt: "2 days ago" },
  { id: 3, player: "Luke Hughes", team: "NJD", winner: "Frozen Thunder", winningBid: 42, processedAt: "3 days ago" },
];

const faabBudget = 100;
const faabSpent = 35;
const faabRemaining = faabBudget - faabSpent;
const waiverPriority = 3;

const waiverOrder = [
  { rank: 1, team: "Frozen Thunder", record: "4-6" },
  { rank: 2, team: "Ice Crushers", record: "5-5" },
  { rank: 3, team: "Glacier Kings", record: "5-5" },
  { rank: 4, team: "Puck Masters", record: "6-4" },
  { rank: 5, team: "Team Frostbite", record: "6-4" },
  { rank: 6, team: "Blizzard Brigade", record: "7-3" },
  { rank: 7, team: "Arctic Wolves", record: "7-3" },
  { rank: 8, team: "Snow Storm", record: "8-2" },
];

const Waivers = () => {
  const [waiverOrderOpen, setWaiverOrderOpen] = useState(false);

  return (
    <AppLayout>
      <div className="container py-8 space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold">Waiver Wire</h1>
            <p className="text-muted-foreground">FAAB bidding and waiver claims</p>
          </div>
        </div>

        {/* FAAB Overview */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <Card className="bg-card border-border">
            <CardContent className="p-6">
              <div className="flex items-center gap-3 mb-3">
                <div className="h-10 w-10 rounded-lg bg-primary/20 flex items-center justify-center">
                  <DollarSign className="h-5 w-5 text-primary" />
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">FAAB Remaining</p>
                  <p className="text-xl font-bold text-primary">${faabRemaining}</p>
                </div>
              </div>
              <Progress value={(faabRemaining / faabBudget) * 100} className="h-2" />
              <p className="text-xs text-muted-foreground mt-2">${faabSpent} spent of ${faabBudget} budget</p>
            </CardContent>
          </Card>

          <Card className="bg-card border-border">
            <Collapsible open={waiverOrderOpen} onOpenChange={setWaiverOrderOpen}>
              <CardContent className="p-6">
                <div className="flex items-center gap-3 mb-3">
                  <div className="h-10 w-10 rounded-lg bg-accent/20 flex items-center justify-center">
                    <Clock className="h-5 w-5 text-accent" />
                  </div>
                  <div className="flex-1">
                    <p className="text-sm text-muted-foreground">Waiver Priority</p>
                    <p className="text-xl font-bold">#{waiverPriority}</p>
                  </div>
                  <CollapsibleTrigger asChild>
                    <Button variant="ghost" size="sm" className="h-8 w-8 p-0">
                      {waiverOrderOpen ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                    </Button>
                  </CollapsibleTrigger>
                </div>
                <p className="text-xs text-muted-foreground">Resets after successful claim</p>
                <CollapsibleContent>
                  <div className="mt-4 pt-4 border-t border-border space-y-2">
                    <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">League Waiver Order</p>
                    {waiverOrder.map((entry) => (
                      <div
                        key={entry.rank}
                        className={`flex items-center justify-between px-3 py-1.5 rounded-md text-sm ${
                          entry.rank === waiverPriority ? "bg-primary/10 font-semibold" : ""
                        }`}
                      >
                        <span className="flex items-center gap-2">
                          <span className="text-muted-foreground w-5 text-right">{entry.rank}.</span>
                          <span><TeamLink name={entry.team} /></span>
                          {entry.rank === waiverPriority && (
                            <Badge variant="outline" className="text-[10px] px-1.5 py-0">You</Badge>
                          )}
                        </span>
                        <span className="text-xs text-muted-foreground">{entry.record}</span>
                      </div>
                    ))}
                  </div>
                </CollapsibleContent>
              </CardContent>
            </Collapsible>
          </Card>

          <Card className="bg-card border-border">
            <CardContent className="p-6">
              <div className="flex items-center gap-3 mb-3">
                <div className="h-10 w-10 rounded-lg bg-success/20 flex items-center justify-center">
                  <History className="h-5 w-5 text-success" />
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Pending Claims</p>
                  <p className="text-xl font-bold">{myClaims.filter(c => c.status === "pending").length}</p>
                </div>
              </div>
              <p className="text-xs text-muted-foreground">Next process: Tonight 3:00 AM</p>
            </CardContent>
          </Card>
        </div>

        <Tabs defaultValue="available" className="space-y-4">
          <TabsList className="bg-secondary">
            <TabsTrigger value="available">Available Players</TabsTrigger>
            <TabsTrigger value="my-claims">My Claims ({myClaims.length})</TabsTrigger>
            <TabsTrigger value="history">Claim History</TabsTrigger>
          </TabsList>

          <TabsContent value="available">
            <Card className="bg-card border-border">
              <CardContent className="p-0">
                <Table>
                  <TableHeader>
                    <TableRow className="border-border">
                      <TableHead>Player</TableHead>
                      <TableHead className="text-center">POS</TableHead>
                      <TableHead className="text-center">Clears In</TableHead>
                      <TableHead className="text-right">Week Pts</TableHead>
                      <TableHead className="text-right">Season Pts</TableHead>
                      <TableHead className="text-center">% Owned</TableHead>
                      <TableHead className="text-right">Action</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {waiverPlayers.map((player) => (
                      <TableRow key={player.id} className="border-border">
                        <TableCell>
                          <div className="flex items-center gap-3">
                            <div className="h-10 w-10 rounded-lg bg-secondary flex items-center justify-center text-xs font-bold">
                              {player.team}
                            </div>
                            <div>
                              <div className="flex items-center gap-2">
                                <p className="font-medium">{player.name}</p>
                                {player.trending === "up" && <TrendingUp className="h-3 w-3 text-success" />}
                              </div>
                              {player.previousOwner && (
                                <p className="text-xs text-muted-foreground">Dropped by <TeamLink name={player.previousOwner} /></p>
                              )}
                            </div>
                          </div>
                        </TableCell>
                        <TableCell className="text-center">
                          <Badge variant="outline" className="bg-secondary/50">{player.position}</Badge>
                        </TableCell>
                        <TableCell className="text-center">
                          <Badge className="bg-accent/20 text-accent border-accent/30">
                            <Clock className="h-3 w-3 mr-1" />
                            {player.clearTime}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-right font-semibold">{player.weekPoints}</TableCell>
                        <TableCell className="text-right">{player.seasonPoints}</TableCell>
                        <TableCell className="text-center">{player.percentOwned}%</TableCell>
                        <TableCell className="text-right">
                          <Button size="sm" className="bg-primary hover:bg-primary/90">
                            <Plus className="h-4 w-4 mr-1" />
                            Claim
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="my-claims">
            <Card className="bg-card border-border">
              <CardHeader>
                <CardTitle>Pending Claims</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  {myClaims.map((claim) => (
                    <div key={claim.id} className="flex items-center justify-between p-4 rounded-lg bg-secondary/30">
                      <div className="flex items-center gap-3">
                        <div className="h-10 w-10 rounded-lg bg-secondary flex items-center justify-center text-xs font-bold">
                          {claim.team}
                        </div>
                        <div>
                          <p className="font-medium">{claim.player}</p>
                          {claim.dropPlayer && (
                            <p className="text-sm text-muted-foreground">Dropping: {claim.dropPlayer}</p>
                          )}
                        </div>
                      </div>
                      <div className="flex items-center gap-4">
                        <div className="text-right">
                          <p className="font-semibold text-primary">${claim.bidAmount}</p>
                          <p className="text-xs text-muted-foreground">FAAB Bid</p>
                        </div>
                        <Badge className="bg-accent/20 text-accent border-accent/30">
                          <Clock className="h-3 w-3 mr-1" />
                          {claim.processTime}
                        </Badge>
                        <Button variant="outline" size="sm" className="text-destructive border-destructive/30">
                          Cancel
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="history">
            <Card className="bg-card border-border">
              <CardHeader>
                <CardTitle>Recent Claim History</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  {claimHistory.map((claim) => (
                    <div key={claim.id} className="flex items-center justify-between p-4 rounded-lg bg-secondary/30">
                      <div className="flex items-center gap-3">
                        <div className="h-10 w-10 rounded-lg bg-secondary flex items-center justify-center text-xs font-bold">
                          {claim.team}
                        </div>
                        <div>
                          <p className="font-medium">{claim.player}</p>
                          <p className="text-sm text-muted-foreground">Won by <TeamLink name={claim.winner} /></p>
                        </div>
                      </div>
                      <div className="flex items-center gap-4">
                        <div className="text-right">
                          <p className="font-semibold text-primary">${claim.winningBid}</p>
                          <p className="text-xs text-muted-foreground">Winning Bid</p>
                        </div>
                        <span className="text-sm text-muted-foreground">{claim.processedAt}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </div>
    </AppLayout>
  );
};

export default Waivers;
