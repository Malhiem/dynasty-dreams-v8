// @ts-nocheck
import { AppLayout } from "@/components/layout/AppLayout";
import { useActiveLeague } from "@/hooks/use-active-league";
import LeagueContextBanner from "@/lovable/components/dashboard/LeagueContextBanner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Progress } from "@/components/ui/progress";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Clock, DollarSign, Plus, History, TrendingUp, ChevronDown, ChevronUp } from "lucide-react";
import { useState, useEffect, useMemo } from "react";
import api from "@/lib/api";
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

const Waivers = () => {
  const { league, leagueTeams, myTeam } = useActiveLeague();
  const leagueTeamsCount = leagueTeams?.length || 0;

  const [waiverOrderOpen, setWaiverOrderOpen] = useState(false);
  const [livePlayers, setLivePlayers] = useState<any[]>([]);
  const [liveClaims, setLiveClaims] = useState<any[]>([]);
  const [liveHistory, setLiveHistory] = useState<any[]>([]);
  const [liveBudget, setLiveBudget] = useState<any>(null);
  const [liveOrder, setLiveOrder] = useState<any[]>([]);

  useEffect(() => {
    if (!league?.id) return;
    let cancelled = false;
    Promise.all([
      api.get(`/waivers/available?league_id=${league.id}&limit=20`).catch(() => ({ data: { players: [] } })),
      api.get(`/waivers/claims?league_id=${league.id}`).catch(() => ({ data: { claims: [] } })),
      api.get(`/waivers/history?league_id=${league.id}`).catch(() => ({ data: { history: [] } })),
      myTeam?.id
        ? api.get(`/waivers/budget?team_id=${myTeam.id}&league_id=${league.id}`).catch(() => ({ data: null }))
        : Promise.resolve({ data: null }),
      api.get(`/waivers/order?league_id=${league.id}`).catch(() => ({ data: { order: [] } })),
    ]).then(([pRes, cRes, hRes, bRes, oRes]) => {
      if (cancelled) return;
      setLivePlayers(pRes.data?.players || []);
      setLiveClaims(cRes.data?.claims || cRes.data || []);
      setLiveHistory(hRes.data?.history || hRes.data || []);
      setLiveBudget(bRes.data);
      setLiveOrder(oRes.data?.order || oRes.data || []);
    });
    return () => { cancelled = true; };
  }, [league?.id, myTeam?.id]);

  const faabBudget = liveBudget?.total_budget ?? 100;
  const faabSpent = liveBudget?.spent ?? 0;
  const faabRemaining = liveBudget?.remaining ?? (faabBudget - faabSpent);

  const waiverOrder = useMemo(() => {
    if (liveOrder?.length) {
      return liveOrder.map((o: any, i: number) => ({
        rank: o.rank || i + 1,
        team: o.team_name || o.name || "Team",
        record: `${o.wins || 0}-${o.losses || 0}`,
        teamId: o.team_id,
      }));
    }
    return (leagueTeams || []).map((t: any, i: number) => ({
      rank: i + 1,
      team: t.name,
      record: `${t.wins || 0}-${t.losses || 0}`,
      teamId: t.id,
    })).slice(0, 12);
  }, [liveOrder, leagueTeams]);

  const waiverPriority = Math.max(1, waiverOrder.findIndex((w: any) => w.teamId === myTeam?.id) + 1);

  const waiverPlayers: WaiverPlayer[] = useMemo(() => (livePlayers || []).slice(0, 20).map((p: any, i: number) => ({
    id: p.id || i,
    name: p.name,
    position: p.position,
    team: p.team,
    previousOwner: undefined,
    clearTime: "24h",
    weekPoints: 0,
    seasonPoints: p.points || 0,
    percentOwned: Math.min(99, Math.round(((p.games_played || 0) / 50) * 100)),
    trending: (p.points > 30 ? "up" : "stable") as any,
  })), [livePlayers]);

  const myClaims: WaiverClaim[] = useMemo(() => (liveClaims || []).map((c: any, i: number) => ({
    id: c._id || i,
    player: c.player_name || "Unknown",
    team: c.nhl_team || "",
    bidAmount: c.bid_amount || 0,
    dropPlayer: c.drop_player_name,
    status: (c.status || "pending") as any,
    processTime: c.process_time || "—",
  })), [liveClaims]);

  const claimHistory: ClaimHistory[] = useMemo(() => (liveHistory || []).map((h: any, i: number) => ({
    id: h._id || i,
    player: h.player_name || "Unknown",
    team: h.nhl_team || "",
    winner: h.winning_team_name || "—",
    winningBid: h.winning_bid || 0,
    processedAt: (h.processed_at || "").slice(0, 10),
  })), [liveHistory]);

  return (
    <AppLayout>
        <div className="container py-8 space-y-6">
          <LeagueContextBanner title="Waiver Wire" kpiLabel="Pending claims" kpiValue={myClaims.filter(c => c.status === "pending").length} primaryHref="/players" primaryLabel="Free agents" />
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
