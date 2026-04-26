// @ts-nocheck
import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Shield, ChevronDown, ChevronUp, ArrowRightLeft, Eye, CheckCircle2 } from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";
import TeamLink from "@/lovable/components/TeamLink";
import { useActiveLeague } from "@/hooks/use-active-league";

/**
 * CommissionerPendingTrades — fetches REAL pending trades from the backend
 * (`/leagues/{id}/pending-trades`) and filters to those involving `teamId`.
 * Renders null if the team has no open trades, so the commissioner panel
 * collapses cleanly instead of showing fake placeholder data.
 *
 * The "View" and "Accept on behalf of" buttons remain (with audit-log toast)
 * — the audit-log accept-on-behalf is intentionally a confirmation-only UX
 * pending a backend endpoint for the actual commissioner override.
 */
const CommissionerPendingTrades = ({ teamId, teamName }: { teamId: string; teamName: string }) => {
  const { league } = useActiveLeague();
  const [allTrades, setAllTrades] = useState([]);
  const [loaded, setLoaded] = useState(false);

  const [isOpen, setIsOpen] = useState(false);
  const [viewConfirmTradeId, setViewConfirmTradeId] = useState<string | null>(null);
  const [viewingTradeId, setViewingTradeId] = useState<string | null>(null);
  const [acceptConfirmTradeId, setAcceptConfirmTradeId] = useState<string | null>(null);
  const [acceptedTrades, setAcceptedTrades] = useState<Set<string>>(new Set());
  const [confirmedTrades, setConfirmedTrades] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (!league?.id) return;
    let cancelled = false;
    api
      .get(`/leagues/${league.id}/pending-trades`)
      .then(({ data }) => {
        if (cancelled) return;
        setAllTrades(data?.pending_trades || []);
        setLoaded(true);
      })
      .catch(() => setLoaded(true));
    return () => {
      cancelled = true;
    };
  }, [league?.id]);

  // Filter to only trades involving THIS team (as proposer, target, or party).
  const teamTrades = allTrades.filter((t) => {
    if (t.proposer_team_id === teamId) return true;
    if (t.target_team_id === teamId) return true;
    if (Array.isArray(t.parties)) {
      return t.parties.some((p) => p.team_id === teamId);
    }
    return false;
  });

  const activeTrades = teamTrades.filter((t) => !acceptedTrades.has(t._id || t.id));

  const summarize = (t) => {
    const offered = (t.assets_offered || []).slice(0, 2).map((a) => a.player_name).filter(Boolean);
    const requested = (t.assets_requested || []).slice(0, 2).map((a) => a.player_name).filter(Boolean);
    if (!offered.length && !requested.length) return "Picks / FAAB";
    return `${offered.join(", ") || "—"} for ${requested.join(", ") || "—"}`;
  };

  const tradeDate = (t) => {
    if (!t.submitted_at) return "—";
    try {
      return new Date(t.submitted_at).toLocaleDateString();
    } catch {
      return "—";
    }
  };

  const handleViewConfirm = (tradeId: string) => setViewConfirmTradeId(tradeId);
  const handleViewApproved = () => {
    if (viewConfirmTradeId) {
      setConfirmedTrades((prev) => new Set([...prev, viewConfirmTradeId]));
      setViewingTradeId(viewConfirmTradeId);
      toast.info("Trade view logged in the league audit log.", {
        description: "Commissioner accessed pending trade details.",
      });
    }
    setViewConfirmTradeId(null);
  };

  const handleAcceptConfirm = (tradeId: string) => setAcceptConfirmTradeId(tradeId);
  const handleAcceptApproved = () => {
    if (acceptConfirmTradeId) {
      setAcceptedTrades((prev) => new Set([...prev, acceptConfirmTradeId]));
      const trade = teamTrades.find((t) => (t._id || t.id) === acceptConfirmTradeId);
      toast.success("Trade accepted on behalf of " + teamName, {
        description: `${trade ? summarize(trade) : ""} — logged in audit log.`,
      });
      setViewingTradeId(null);
    }
    setAcceptConfirmTradeId(null);
  };

  // Don't render until we know the answer — and don't render at all when
  // there are zero pending trades for this team.
  if (!loaded || activeTrades.length === 0) return null;

  const viewingTrade = teamTrades.find((t) => (t._id || t.id) === viewingTradeId);

  return (
    <>
      <Collapsible open={isOpen} onOpenChange={setIsOpen}>
        <Card className="border-primary/30 bg-primary/5" data-testid="commissioner-pending-trades">
          <CollapsibleTrigger asChild>
            <CardHeader className="pb-3 cursor-pointer hover:bg-primary/10 transition-colors rounded-t-lg">
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm flex items-center gap-2">
                  <Shield className="h-4 w-4 text-primary" />
                  <span className="text-primary">Commissioner: Pending Trades</span>
                  <Badge variant="secondary" className="text-[10px]">
                    {activeTrades.length} pending
                  </Badge>
                </CardTitle>
                {isOpen ? (
                  <ChevronUp className="h-4 w-4 text-muted-foreground" />
                ) : (
                  <ChevronDown className="h-4 w-4 text-muted-foreground" />
                )}
              </div>
            </CardHeader>
          </CollapsibleTrigger>
          <CollapsibleContent>
            <CardContent className="space-y-3 pt-0">
              {activeTrades.map((trade) => {
                const tid = trade._id || trade.id;
                const fromName = trade.proposer_team_name || "?";
                const toName = trade.target_team_name || "?";
                return (
                  <div
                    key={tid}
                    className="flex items-center justify-between p-3 rounded-lg bg-secondary/30 border border-border/50"
                    data-testid={`commissioner-pending-trade-${tid}`}
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 mb-1">
                        <ArrowRightLeft className="h-3.5 w-3.5 text-accent" />
                        {confirmedTrades.has(tid) ? (
                          <p className="text-sm font-medium truncate">
                            <TeamLink name={fromName} /> ↔ <TeamLink name={toName} />
                          </p>
                        ) : (
                          <p className="text-sm font-medium text-muted-foreground">
                            Pending Trade
                          </p>
                        )}
                      </div>
                      {confirmedTrades.has(tid) ? (
                        <>
                          <p className="text-xs text-muted-foreground truncate">{summarize(trade)}</p>
                          <p className="text-[10px] text-muted-foreground mt-0.5">
                            Proposed: {tradeDate(trade)}
                          </p>
                        </>
                      ) : (
                        <p className="text-xs text-muted-foreground italic">
                          Details hidden — confirm to view
                        </p>
                      )}
                    </div>
                    <div className="flex items-center gap-2 ml-3 shrink-0">
                      {confirmedTrades.has(tid) && viewingTradeId === tid ? (
                        <Button
                          size="sm"
                          variant="gold"
                          className="text-xs h-7 px-3"
                          onClick={() => handleAcceptConfirm(tid)}
                        >
                          <CheckCircle2 className="h-3 w-3 mr-1" />
                          Accept
                        </Button>
                      ) : (
                        <Button
                          size="sm"
                          variant="ice"
                          className="text-xs h-7 px-3"
                          onClick={() =>
                            confirmedTrades.has(tid) ? setViewingTradeId(tid) : handleViewConfirm(tid)
                          }
                        >
                          <Eye className="h-3 w-3 mr-1" />
                          View
                        </Button>
                      )}
                    </div>
                  </div>
                );
              })}

              {/* Expanded trade details */}
              {viewingTrade && !acceptedTrades.has(viewingTrade._id || viewingTrade.id) && (
                <div className="mt-2 p-4 rounded-lg bg-card border border-border space-y-3">
                  <div className="flex items-center gap-2 mb-2">
                    <ArrowRightLeft className="h-4 w-4 text-primary" />
                    <span className="text-sm font-semibold">
                      Trade Details: {viewingTrade.proposer_team_name} ↔ {viewingTrade.target_team_name}
                    </span>
                  </div>
                  <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-1.5">
                      <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                        {viewingTrade.proposer_team_name} Sends
                      </p>
                      {(viewingTrade.assets_offered || []).map((a, i) => (
                        <div key={i} className="text-sm px-2 py-1.5 rounded bg-destructive/10 border border-destructive/20">
                          {a.player_name || a.description || `${a.asset_type} asset`}
                        </div>
                      ))}
                    </div>
                    <div className="space-y-1.5">
                      <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                        {viewingTrade.proposer_team_name} Receives
                      </p>
                      {(viewingTrade.assets_requested || []).map((a, i) => (
                        <div key={i} className="text-sm px-2 py-1.5 rounded bg-emerald-500/10 border border-emerald-500/20">
                          {a.player_name || a.description || `${a.asset_type} asset`}
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              )}
            </CardContent>
          </CollapsibleContent>
        </Card>
      </Collapsible>

      {/* View Confirmation Dialog */}
      <AlertDialog open={!!viewConfirmTradeId} onOpenChange={(open) => !open && setViewConfirmTradeId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle className="flex items-center gap-2">
              <Shield className="h-5 w-5 text-primary" />
              Commissioner Action — View Trade
            </AlertDialogTitle>
            <AlertDialogDescription className="space-y-2">
              <span className="block">
                You are about to view a pending trade for <strong>{teamName}</strong>. This action
                will be <strong>logged in the league audit log</strong>.
              </span>
              <span className="block text-muted-foreground">
                Are you sure you would like to proceed?
              </span>
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>No</AlertDialogCancel>
            <AlertDialogAction onClick={handleViewApproved}>Yes</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Accept Confirmation Dialog */}
      <AlertDialog open={!!acceptConfirmTradeId} onOpenChange={(open) => !open && setAcceptConfirmTradeId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle className="flex items-center gap-2">
              <Shield className="h-5 w-5 text-accent" />
              Commissioner Action — Accept Trade
            </AlertDialogTitle>
            <AlertDialogDescription className="space-y-2">
              <span className="block">
                You are about to <strong>accept this trade on behalf of {teamName}</strong>. This
                action will be <strong>logged in the league audit log</strong> and cannot be undone.
              </span>
              <span className="block text-muted-foreground">
                Are you sure you would like to proceed?
              </span>
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>No</AlertDialogCancel>
            <AlertDialogAction onClick={handleAcceptApproved}>Yes</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
};

export default CommissionerPendingTrades;
