// @ts-nocheck
/**
 * Iter 232N.9 — Waiver Management Panel
 *
 * Extracted from `Waivers.tsx` so the unified Free Agent screen
 * (`/players`) can host claim management inline. Owns:
 *   • FAAB budget tile (FAAB leagues only)
 *   • Waiver priority collapsible tile
 *   • Pending Claims + next-run tile
 *   • WaiverPriorityOrderCard
 *   • Inner tabs: My Claims / Claim History
 *
 * Player discovery + the Place-Claim modal continue to live on the
 * Players table (`PlayersPage.jsx`) — the `+` button there routes to
 * `/waivers?add=<pid>` which still opens the claim flow. This panel
 * is intentionally read/manage only.
 */
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import api, { formatApiError } from "@/lib/api";
import { useActiveLeague } from "@/hooks/use-active-league";
import { useLeagueSocket } from "@/hooks/use-socket";
import WaiverPriorityOrderCard from "@/lovable/components/dashboard/WaiverPriorityOrderCard";
import TeamLink from "@/lovable/components/TeamLink";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Collapsible, CollapsibleContent, CollapsibleTrigger,
} from "@/components/ui/collapsible";
import {
  Clock, DollarSign, History, ChevronDown, ChevronUp, AlertTriangle,
} from "lucide-react";

export default function WaiverManagementPanel() {
  const { league, leagueTeams, myTeam } = useActiveLeague();

  const [waiverOrderOpen, setWaiverOrderOpen] = useState(false);
  const [liveClaims, setLiveClaims] = useState<any[]>([]);
  const [liveHistory, setLiveHistory] = useState<any[]>([]);
  const [liveBudget, setLiveBudget] = useState<any>(null);
  const [liveOrder, setLiveOrder] = useState<any[]>([]);
  const [nextRun, setNextRun] = useState<any>(null);
  const [txConfig, setTxConfig] = useState<any>(null);
  const [cancellingClaimId, setCancellingClaimId] = useState<string | null>(null);

  // Real-time waivers-processed toast (mirrors Waivers.tsx behaviour).
  useLeagueSocket(league?.id, {
    onWaiversProcessed: (data: any) => {
      const results = data?.results || [];
      if (!results.length) return;
      const myTeamId = (myTeam as any)?.id || (myTeam as any)?._id;
      const myWins = results.filter((r: any) => r.winner_team_id === myTeamId);
      const myLosses = results.filter((r: any) =>
        (r.losers || []).some((tn: string) => tn === (myTeam as any)?.name),
      );
      if (myWins.length) {
        const list = myWins.map((w: any) => `${w.player} ($${w.bid || 0})`).join(", ");
        toast.success(`Waivers landed: ${list}`, {
          duration: 8000,
          description: "Refresh your roster to see your new players.",
        });
      }
      if (myLosses.length) {
        const list = myLosses.map((w: any) => `${w.player} → ${w.winner}`).join(", ");
        toast.info(`Lost on waivers: ${list}`, { duration: 8000 });
      }
      refreshLive();
    },
  });

  useEffect(() => {
    if (!league?.id) return;
    let cancelled = false;
    Promise.all([
      api.get(`/waivers/claims?league_id=${league.id}&my_claims=true`).catch(() => ({ data: [] })),
      api.get(`/waivers/history?league_id=${league.id}`).catch(() => ({ data: { history: [] } })),
      myTeam?.id
        ? api.get(`/waivers/budget?team_id=${myTeam.id}&league_id=${league.id}`).catch(() => ({ data: null }))
        : Promise.resolve({ data: null }),
      api.get(`/waivers/order?league_id=${league.id}`).catch(() => ({ data: { order: [] } })),
      api.get(`/waivers/next-run?league_id=${league.id}`).catch(() => ({ data: null })),
      api.get(`/leagues/${league.id}/transactions-config`).catch(() => ({ data: null })),
    ]).then(([cRes, hRes, bRes, oRes, nRes, txRes]) => {
      if (cancelled) return;
      setLiveClaims(cRes.data?.claims || cRes.data || []);
      setLiveHistory(hRes.data?.history || hRes.data || []);
      setLiveBudget(bRes.data);
      setLiveOrder(oRes.data?.order || oRes.data || []);
      setNextRun(nRes.data);
      setTxConfig(txRes.data);
    });
    return () => { cancelled = true; };
  }, [league?.id, myTeam?.id]);

  const refreshLive = async () => {
    if (!league?.id) return;
    try {
      const [cRes, bRes, nRes] = await Promise.all([
        api.get(`/waivers/claims?my_claims=true&league_id=${league.id}`),
        myTeam?.id
          ? api.get(`/waivers/budget?league_id=${league.id}`)
          : Promise.resolve({ data: null }),
        api.get(`/waivers/next-run?league_id=${league.id}`),
      ]);
      setLiveClaims(cRes.data?.claims || cRes.data || []);
      if (bRes.data) setLiveBudget(bRes.data);
      if (nRes.data) setNextRun(nRes.data);
    } catch { /* swallow */ }
  };

  const handleCancelClaim = async (claimId: string) => {
    if (!claimId || cancellingClaimId) return;
    setCancellingClaimId(claimId);
    try {
      await api.delete(`/waivers/claims/${claimId}`);
      toast.success("Claim cancelled");
      setLiveClaims((prev) => prev.filter((c: any) => (c._id || c.id) !== claimId));
      await refreshLive();
    } catch (e) {
      toast.error(formatApiError(e));
    } finally {
      setCancellingClaimId(null);
    }
  };

  const isFaabSystem = (txConfig?.waiver?.system_type || "auto_priority") === "faab";
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

  const waiverPriority = Math.max(
    1,
    waiverOrder.findIndex((w: any) => w.teamId === myTeam?.id) + 1,
  );

  const myClaims = useMemo(() => (liveClaims || []).map((c: any, i: number) => ({
    id: c._id || i,
    player: c.player_name || "Unknown",
    team: c.nhl_team || "",
    bidAmount: c.bid_amount || 0,
    dropPlayer: c.drop_player_name,
    status: (c.status || "pending") as any,
    processTime: c.process_time || "—",
  })), [liveClaims]);

  const claimHistory = useMemo(() => (liveHistory || []).map((h: any, i: number) => ({
    id: h._id || i,
    player: h.player_name || "Unknown",
    team: h.nhl_team || "",
    winner: h.winning_team_name || "—",
    winningBid: h.winning_bid || 0,
    processedAt: (h.processed_at || "").slice(0, 10),
    winningTeamId: h.winning_team_id || h.team_id || "",
  })), [liveHistory]);

  const pendingCount = myClaims.filter((c) => c.status === "pending").length;

  return (
    <div className="space-y-6" data-testid="waiver-management-panel">
      {/* Top row: FAAB / Priority / Pending stats */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {isFaabSystem && (
          <Card className="bg-card border-border" data-testid="waiver-faab-tile">
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
              <p className="text-xs text-muted-foreground mt-2">
                ${faabSpent} spent of ${faabBudget} budget
              </p>
            </CardContent>
          </Card>
        )}

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
                  <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">
                    League Waiver Order
                  </p>
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
                <p className="text-xl font-bold" data-testid="waivers-pending-count">
                  {pendingCount}
                </p>
              </div>
            </div>
            <p className="text-xs text-muted-foreground" data-testid="waivers-next-run">
              {(() => {
                if (!nextRun?.enabled) return "Waivers disabled";
                if (!nextRun?.next_run_at) return "No upcoming run scheduled";
                try {
                  const d = new Date(nextRun.next_run_at);
                  return `Next process: ${d.toLocaleString(undefined, {
                    weekday: "short", month: "short", day: "numeric",
                    hour: "numeric", minute: "2-digit",
                  })}`;
                } catch {
                  return `Next process: ${nextRun.next_run_at}`;
                }
              })()}
            </p>
          </CardContent>
        </Card>
      </div>

      <WaiverPriorityOrderCard
        leagueId={league?.id}
        teamsById={Object.fromEntries((leagueTeams || []).map((t: any) => [t.id, t]))}
      />

      <Tabs defaultValue="my-claims" className="space-y-4">
        <TabsList className="bg-secondary">
          <TabsTrigger value="my-claims" data-testid="waiver-tab-my-claims">
            My Claims ({myClaims.length})
          </TabsTrigger>
          <TabsTrigger value="history" data-testid="waiver-tab-history">
            Claim History
          </TabsTrigger>
        </TabsList>

        <TabsContent value="my-claims">
          <Card className="bg-card border-border">
            <CardHeader>
              <CardTitle>Pending Claims</CardTitle>
            </CardHeader>
            <CardContent>
              {myClaims.length === 0 ? (
                <div
                  className="text-center py-8 text-sm text-muted-foreground"
                  data-testid="waiver-my-claims-empty"
                >
                  You haven&apos;t placed any waiver claims yet. Use the{" "}
                  <span className="font-mono text-emerald-300">+</span> button on
                  the Free Agents tab to submit one.
                </div>
              ) : (
                <div className="space-y-4">
                  {myClaims.map((claim) => (
                    <div
                      key={claim.id}
                      className="flex items-center justify-between p-4 rounded-lg bg-secondary/30"
                      data-testid={`waiver-my-claim-${claim.id}`}
                    >
                      <div className="flex items-center gap-3">
                        <div className="h-10 w-10 rounded-lg bg-secondary flex items-center justify-center text-xs font-bold">
                          {claim.team}
                        </div>
                        <div>
                          <p className="font-medium">{claim.player}</p>
                          {claim.dropPlayer && (
                            <p className="text-sm text-muted-foreground">
                              Dropping: {claim.dropPlayer}
                            </p>
                          )}
                        </div>
                      </div>
                      <div className="flex items-center gap-4">
                        {isFaabSystem ? (
                          <div className="text-right">
                            <p className="font-semibold text-primary">${claim.bidAmount}</p>
                            <p className="text-xs text-muted-foreground">FAAB Bid</p>
                          </div>
                        ) : null}
                        <Badge
                          className={
                            claim.status === "pending"
                              ? "bg-accent/20 text-accent border-accent/30"
                              : claim.status === "won"
                              ? "bg-success/20 text-success border-success/30"
                              : claim.status === "denied" || claim.status === "lost" || claim.status === "cancelled"
                              ? "bg-destructive/15 text-destructive border-destructive/30"
                              : "bg-secondary/20 text-muted-foreground border-border"
                          }
                          data-testid={`waiver-claim-status-${claim.id}`}
                        >
                          {claim.status === "pending" ? (
                            <Clock className="h-3 w-3 mr-1" />
                          ) : null}
                          {claim.status === "pending"
                            ? claim.processTime
                            : claim.status.charAt(0).toUpperCase() + claim.status.slice(1)}
                        </Badge>
                        {claim.status === "pending" && (
                          <Button
                            variant="outline"
                            size="sm"
                            className="text-destructive border-destructive/30 hover:bg-destructive/10"
                            disabled={cancellingClaimId === String(claim.id)}
                            onClick={() => handleCancelClaim(String(claim.id))}
                            data-testid={`waiver-claim-cancel-${claim.id}`}
                          >
                            {cancellingClaimId === String(claim.id) ? "Cancelling…" : "Cancel"}
                          </Button>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="history">
          <Card className="bg-card border-border">
            <CardHeader>
              <CardTitle>Recent Claim History</CardTitle>
            </CardHeader>
            <CardContent>
              {claimHistory.length === 0 ? (
                <div
                  className="text-center py-8 text-sm text-muted-foreground"
                  data-testid="waiver-history-empty"
                >
                  No waiver claims have been processed in this league yet.
                </div>
              ) : (
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
                            Won by <TeamLink name={claim.winner} />
                          </p>
                        </div>
                      </div>
                      <div className="flex items-center gap-4">
                        <div className="text-right">
                          <p className="font-semibold text-primary">${claim.winningBid}</p>
                          <p className="text-xs text-muted-foreground">Winning Bid</p>
                        </div>
                        <span className="text-sm text-muted-foreground">
                          {claim.processedAt}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
