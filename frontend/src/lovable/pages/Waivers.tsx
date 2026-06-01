// @ts-nocheck
import { AppLayout } from "@/components/layout/AppLayout";
import { useActiveLeague } from "@/hooks/use-active-league";
import LeagueContextBanner from "@/lovable/components/dashboard/LeagueContextBanner";
import WaiverPriorityOrderCard from "@/lovable/components/dashboard/WaiverPriorityOrderCard";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Progress } from "@/components/ui/progress";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Clock, DollarSign, Plus, History, TrendingUp, ChevronDown, ChevronUp, AlertTriangle, ArrowRight } from "lucide-react";
import { useState, useEffect, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import api, { formatApiError } from "@/lib/api";
import TeamLink from "@/lovable/components/TeamLink";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";

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
  winningTeamId?: string;
}

const Waivers = () => {
  const navigate = useNavigate();
  const { league, leagueTeams, myTeam } = useActiveLeague();
  const leagueTeamsCount = leagueTeams?.length || 0;

  const [waiverOrderOpen, setWaiverOrderOpen] = useState(false);
  const [livePlayers, setLivePlayers] = useState<any[]>([]);
  const [liveClaims, setLiveClaims] = useState<any[]>([]);
  const [liveHistory, setLiveHistory] = useState<any[]>([]);
  const [liveBudget, setLiveBudget] = useState<any>(null);
  const [liveOrder, setLiveOrder] = useState<any[]>([]);
  // Iter 122 — pending_visibility audience controls whether non-owners can
  // see pending claim team names. "all_teams_anonymous" masks them to
  // "Team A", "Team B", … for everyone except the team owner + commissioner.
  const [txConfig, setTxConfig] = useState<any>(null);

  // Claim modal state ────────────────────────────────────────────────
  const [claimModalOpen, setClaimModalOpen] = useState(false);
  const [selectedPlayer, setSelectedPlayer] = useState<any>(null);
  const [bidAmount, setBidAmount] = useState<number>(1);
  const [precheck, setPrecheck] = useState<any>(null);
  const [prechecking, setPrechecking] = useState(false);
  const [claimSubmitting, setClaimSubmitting] = useState(false);

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
    // Iter 122 — fetch transactions-config for the anonymous visibility audience
    api.get(`/leagues/${league.id}/transactions-config`)
      .then(({ data }) => { if (!cancelled) setTxConfig(data); })
      .catch(() => { if (!cancelled) setTxConfig(null); });
    return () => { cancelled = true; };
  }, [league?.id, myTeam?.id]);

  // Re-fetch precheck whenever the modal opens, selected player changes,
  // or the bid amount changes (FAAB blocker depends on bid).
  useEffect(() => {
    if (!claimModalOpen || !selectedPlayer || !league?.id) return;
    let cancelled = false;
    setPrechecking(true);
    api.get(`/waivers/precheck`, {
      params: {
        league_id: league.id,
        player_id: selectedPlayer.id,
        bid_amount: bidAmount || 0,
      },
    })
      .then((res) => { if (!cancelled) setPrecheck(res.data); })
      .catch(() => { if (!cancelled) setPrecheck(null); })
      .finally(() => { if (!cancelled) setPrechecking(false); });
    return () => { cancelled = true; };
  }, [claimModalOpen, selectedPlayer?.id, bidAmount, league?.id]);

  const openClaimModal = (player: any) => {
    setSelectedPlayer(player);
    setBidAmount(1);
    setPrecheck(null);
    setClaimModalOpen(true);
  };

  const refreshLive = async () => {
    if (!league?.id) return;
    try {
      const [cRes, bRes] = await Promise.all([
        api.get(`/waivers/claims?my_claims=true&league_id=${league.id}`),
        myTeam?.id
          ? api.get(`/waivers/budget?league_id=${league.id}`)
          : Promise.resolve({ data: null }),
      ]);
      setLiveClaims(cRes.data || []);
      if (bRes.data) setLiveBudget(bRes.data);
    } catch { /* swallow */ }
  };

  const handleSubmitClaim = async () => {
    if (!selectedPlayer || !league?.id) return;
    setClaimSubmitting(true);
    try {
      await api.post("/waivers/claim", {
        league_id: league.id,
        player_id: selectedPlayer.id,
        bid_amount: bidAmount,
      });
      toast.success(`Claim placed on ${selectedPlayer.name} for $${bidAmount}`, {
        description: "You'll see the result after waivers process.",
      });
      setClaimModalOpen(false);
      await refreshLive();
    } catch (e) {
      toast.error(formatApiError(e));
    } finally {
      setClaimSubmitting(false);
    }
  };

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
    hasActiveClaim: !!p.has_active_claim,
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
    winningTeamId: h.winning_team_id || h.team_id || "",
  })), [liveHistory]);

  // Iter 122 — Anonymous waiver visibility variant.
  // When the league's waiver pending_visibility is set to "all_teams_anonymous",
  // mask team names to "Team A", "Team B", ... for non-commissioners viewing
  // OTHER owners' claims. Commissioner + the claim's own owner still see real
  // names. We derive a stable label per teamId so the masking is consistent
  // across renders + tabs (same team always shows as the same letter).
  const isCommish = !!(
    league?.commissioner_id && myTeam?.owner_id && league.commissioner_id === myTeam.owner_id
  );
  const waiverVisibility =
    txConfig?.waiver?.pending_visibility || txConfig?.claim_rules?.pending_visibility || "own";
  const isAnonymousMode =
    waiverVisibility === "all_teams_anonymous" && !isCommish;

  const teamLabelMap = useMemo(() => {
    if (!isAnonymousMode) return null;
    const sorted = [...(leagueTeams || [])].sort((a: any, b: any) =>
      String(a.id).localeCompare(String(b.id)),
    );
    const map: Record<string, string> = {};
    sorted.forEach((t: any, idx: number) => {
      const letter = String.fromCharCode(65 + (idx % 26));
      const suffix = idx >= 26 ? `${Math.floor(idx / 26) + 1}` : "";
      map[t.id] = `Team ${letter}${suffix}`;
    });
    return map;
  }, [isAnonymousMode, leagueTeams]);

  const maskTeamName = (teamId: string | undefined, fallbackName: string | undefined) => {
    if (!isAnonymousMode) return fallbackName || "—";
    if (myTeam?.id && teamId === myTeam.id) return fallbackName || "You";
    return teamLabelMap?.[teamId || ""] || "Anonymous";
  };

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

        <WaiverPriorityOrderCard
          leagueId={league?.id}
          teamsById={Object.fromEntries((leagueTeams || []).map((t) => [t.id, t]))}
        />

        {/* Iter 122 — Anonymous waiver visibility banner */}
        {isAnonymousMode && (
          <div
            className="rounded-md border border-purple-500/30 bg-purple-500/5 p-3 flex items-center gap-3"
            data-testid="waiver-anonymous-mode"
          >
            <AlertTriangle className="h-4 w-4 text-purple-300 flex-shrink-0" />
            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold text-purple-200">Anonymous waiver mode</p>
              <p className="text-xs text-muted-foreground mt-0.5">
                Team identities are masked on pending claims and history while
                waivers are in flight. Your own team always shows as "You" and
                names reveal after the league commissioner switches visibility.
              </p>
            </div>
          </div>
        )}

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
                          <Button
                            size="sm"
                            className="bg-primary hover:bg-primary/90"
                            onClick={() => openClaimModal(player)}
                            data-testid={`waiver-claim-${player.id}`}
                          >
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
                    <div
                      key={claim.id}
                      className="flex items-center justify-between p-4 rounded-lg bg-secondary/30"
                      data-testid={`waiver-history-row-${claim.id}`}
                    >
                      <div className="flex items-center gap-3">
                        <div className="h-10 w-10 rounded-lg bg-secondary flex items-center justify-center text-xs font-bold">
                          {claim.team}
                        </div>
                        <div>
                          <p className="font-medium">{claim.player}</p>
                          <p className="text-sm text-muted-foreground">
                            Won by{" "}
                            {isAnonymousMode ? (
                              <span
                                className="font-medium text-purple-300"
                                data-testid={`waiver-history-winner-anon-${claim.id}`}
                              >
                                {maskTeamName(claim.winningTeamId, claim.winner)}
                              </span>
                            ) : (
                              <TeamLink name={claim.winner} />
                            )}
                          </p>
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

        {/* Waiver Claim Modal with pre-check */}
        <Dialog open={claimModalOpen} onOpenChange={setClaimModalOpen}>
          <DialogContent className="bg-card border-border" data-testid="waiver-claim-modal">
            <DialogHeader>
              <DialogTitle>Place Waiver Claim</DialogTitle>
              <DialogDescription>
                Place a FAAB bid for {selectedPlayer?.name}
              </DialogDescription>
            </DialogHeader>
            <div className="py-4 space-y-4">
              <div className="flex items-center gap-3 p-3 bg-secondary/40 rounded-lg">
                <Badge variant="outline">{selectedPlayer?.position}</Badge>
                <div>
                  <p className="font-medium">{selectedPlayer?.name}</p>
                  <p className="text-xs text-muted-foreground">
                    {selectedPlayer?.team} · {selectedPlayer?.seasonPoints} pts
                  </p>
                </div>
              </div>

              <div>
                <label className="text-sm text-muted-foreground">FAAB Bid ($)</label>
                <Input
                  type="number"
                  min={0}
                  max={faabRemaining}
                  value={bidAmount}
                  onChange={(e) => setBidAmount(parseFloat(e.target.value) || 0)}
                  className="mt-2"
                  data-testid="waiver-bid-amount"
                />
                <p className="text-xs text-muted-foreground mt-1">
                  Remaining budget: ${faabRemaining}
                </p>
              </div>

              {/* Precheck panel ─ surfaces roster / cap / FAAB blockers */}
              {prechecking && (
                <p className="text-xs text-muted-foreground italic" data-testid="precheck-loading">
                  Checking your roster…
                </p>
              )}
              {precheck && (
                <div
                  className="rounded-lg border border-border p-3 space-y-2 bg-background/60"
                  data-testid="precheck-panel"
                >
                  <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
                    <span data-testid="precheck-roster">
                      Roster: <span className="text-foreground font-medium">
                        {precheck.roster.current}/{precheck.roster.max}
                      </span>
                      {precheck.roster.has_room ? (
                        <Badge variant="outline" className="ml-2 text-[10px] py-0 px-1.5 border-success/50 text-success">Room</Badge>
                      ) : (
                        <Badge variant="outline" className="ml-2 text-[10px] py-0 px-1.5 border-destructive/50 text-destructive">Full</Badge>
                      )}
                    </span>
                    {precheck.cap?.enabled && (
                      <span data-testid="precheck-cap">
                        Cap: <span className="text-foreground font-medium">
                          ${(precheck.cap.would_be / 1_000_000).toFixed(2)}M
                        </span> / ${(precheck.cap.cap / 1_000_000).toFixed(1)}M
                        {precheck.cap.fits ? (
                          <Badge variant="outline" className="ml-2 text-[10px] py-0 px-1.5 border-success/50 text-success">Fits</Badge>
                        ) : (
                          <Badge variant="outline" className="ml-2 text-[10px] py-0 px-1.5 border-destructive/50 text-destructive">Over</Badge>
                        )}
                      </span>
                    )}
                  </div>

                  {(precheck.issues || []).map((iss: any, idx: number) => {
                    const isError = iss.severity === "error";
                    return (
                      <div
                        key={`${iss.code}-${idx}`}
                        data-testid={`precheck-issue-${iss.code}`}
                        className={cn(
                          "flex items-start gap-2 p-2 rounded text-xs border",
                          isError
                            ? "bg-destructive/10 text-destructive border-destructive/30"
                            : "bg-yellow-500/10 text-yellow-600 dark:text-yellow-300 border-yellow-500/30",
                        )}
                      >
                        <AlertTriangle className="h-3.5 w-3.5 mt-0.5 shrink-0" />
                        <span>{iss.message}</span>
                      </div>
                    );
                  })}

                  {precheck.requires_drop && (
                    <Button
                      variant="outline"
                      size="sm"
                      className="w-full border-primary/40 text-primary hover:bg-primary/10 gap-1"
                      data-testid="precheck-proceed-to-drop"
                      onClick={() => {
                        setClaimModalOpen(false);
                        navigate("/roster");
                      }}
                    >
                      Proceed to Drop Player <ArrowRight className="h-3.5 w-3.5" />
                    </Button>
                  )}
                </div>
              )}
            </div>
            <DialogFooter>
              <Button
                variant="ghost"
                onClick={() => setClaimModalOpen(false)}
                data-testid="waiver-claim-cancel"
              >
                Cancel
              </Button>
              <Button
                className="bg-primary hover:bg-primary/90"
                onClick={handleSubmitClaim}
                disabled={
                  claimSubmitting ||
                  bidAmount > faabRemaining ||
                  (precheck && !precheck.can_claim)
                }
                data-testid="waiver-claim-confirm"
              >
                {claimSubmitting ? "Placing…" : "Place Claim"}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
    </AppLayout>
  );
};

export default Waivers;
