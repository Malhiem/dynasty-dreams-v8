// @ts-nocheck
import { useState } from "react";
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
import TeamLink from "@/lovable/components/TeamLink";

interface PendingTradeItem {
  id: string;
  from: string;
  to: string;
  summary: string;
  details: {
    sending: string[];
    receiving: string[];
  };
  proposedDate: string;
}

const MOCK_TEAM_PENDING_TRADES: Record<string, PendingTradeItem[]> = {
  "ice-dragons": [
    {
      id: "CT-001",
      from: "Ice Dragons",
      to: "Team Frostbite",
      summary: "N. MacKinnon for L. Draisaitl",
      details: {
        sending: ["Nathan MacKinnon (C) — $12.6M"],
        receiving: ["Leon Draisaitl (C) — $11.2M", "2026 3rd Round Pick"],
      },
      proposedDate: "Mar 8, 2026",
    },
  ],
  blazers: [
    {
      id: "CT-002",
      from: "Blazers",
      to: "Thunder",
      summary: "A. Fox for C. Makar + 2027 2nd",
      details: {
        sending: ["Adam Fox (D) — $9.5M"],
        receiving: ["Cale Makar (D) — $9.0M", "2027 2nd Round Pick"],
      },
      proposedDate: "Mar 7, 2026",
    },
    {
      id: "CT-003",
      from: "Phoenix",
      to: "Blazers",
      summary: "J. Robertson for B. Tkachuk",
      details: {
        sending: ["Jason Robertson (LW) — $7.75M"],
        receiving: ["Brady Tkachuk (LW) — $8.2M"],
      },
      proposedDate: "Mar 6, 2026",
    },
  ],
  thunder: [],
  wolverines: [
    {
      id: "CT-004",
      from: "Wolverines",
      to: "Knights",
      summary: "T. Seguin for M. Zibanejad",
      details: {
        sending: ["Tyler Seguin (C) — $9.85M"],
        receiving: ["Mika Zibanejad (C) — $8.5M"],
      },
      proposedDate: "Mar 5, 2026",
    },
  ],
};

interface CommissionerPendingTradesProps {
  teamId: string;
  teamName: string;
}

const CommissionerPendingTrades = ({ teamId, teamName }: CommissionerPendingTradesProps) => {
  const [isOpen, setIsOpen] = useState(false);
  const [viewConfirmTradeId, setViewConfirmTradeId] = useState<string | null>(null);
  const [viewingTradeId, setViewingTradeId] = useState<string | null>(null);
  const [acceptConfirmTradeId, setAcceptConfirmTradeId] = useState<string | null>(null);
  const [acceptedTrades, setAcceptedTrades] = useState<Set<string>>(new Set());

  const [confirmedTrades, setConfirmedTrades] = useState<Set<string>>(new Set());

  const trades = MOCK_TEAM_PENDING_TRADES[teamId] || [];

  const activeTrades = trades.filter((t) => !acceptedTrades.has(t.id));

  const handleViewConfirm = (tradeId: string) => {
    setViewConfirmTradeId(tradeId);
  };

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

  const handleAcceptConfirm = (tradeId: string) => {
    setAcceptConfirmTradeId(tradeId);
  };

  const handleAcceptApproved = () => {
    if (acceptConfirmTradeId) {
      setAcceptedTrades((prev) => new Set([...prev, acceptConfirmTradeId]));
      const trade = trades.find((t) => t.id === acceptConfirmTradeId);
      toast.success("Trade accepted on behalf of " + teamName, {
        description: `${trade?.summary} — logged in audit log.`,
      });
      setViewingTradeId(null);
    }
    setAcceptConfirmTradeId(null);
  };

  if (trades.length === 0) return null;

  const viewingTrade = trades.find((t) => t.id === viewingTradeId);

  return (
    <>
      <Collapsible open={isOpen} onOpenChange={setIsOpen}>
        <Card className="border-primary/30 bg-primary/5">
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
              {activeTrades.length === 0 ? (
                <p className="text-xs text-muted-foreground text-center py-2">
                  No pending trades remaining.
                </p>
              ) : (
                activeTrades.map((trade) => (
                  <div
                    key={trade.id}
                    className="flex items-center justify-between p-3 rounded-lg bg-secondary/30 border border-border/50"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 mb-1">
                        <ArrowRightLeft className="h-3.5 w-3.5 text-accent" />
                        {confirmedTrades.has(trade.id) ? (
                          <p className="text-sm font-medium truncate">
                            <TeamLink name={trade.from} /> ↔ <TeamLink name={trade.to} />
                          </p>
                        ) : (
                          <p className="text-sm font-medium text-muted-foreground">
                            Pending Trade #{trade.id}
                          </p>
                        )}
                      </div>
                      {confirmedTrades.has(trade.id) ? (
                        <>
                          <p className="text-xs text-muted-foreground truncate">{trade.summary}</p>
                          <p className="text-[10px] text-muted-foreground mt-0.5">
                            Proposed: {trade.proposedDate}
                          </p>
                        </>
                      ) : (
                        <p className="text-xs text-muted-foreground italic">
                          Details hidden — confirm to view
                        </p>
                      )}
                    </div>
                    <div className="flex items-center gap-2 ml-3 shrink-0">
                      {confirmedTrades.has(trade.id) && viewingTradeId === trade.id ? (
                        <Button
                          size="sm"
                          variant="gold"
                          className="text-xs h-7 px-3"
                          onClick={() => handleAcceptConfirm(trade.id)}
                        >
                          <CheckCircle2 className="h-3 w-3 mr-1" />
                          Accept
                        </Button>
                      ) : (
                        <Button
                          size="sm"
                          variant="ice"
                          className="text-xs h-7 px-3"
                          onClick={() => confirmedTrades.has(trade.id) ? setViewingTradeId(trade.id) : handleViewConfirm(trade.id)}
                        >
                          <Eye className="h-3 w-3 mr-1" />
                          View
                        </Button>
                      )}
                    </div>
                  </div>
                ))
              )}

              {/* Expanded trade details */}
              {viewingTrade && !acceptedTrades.has(viewingTrade.id) && (
                <div className="mt-2 p-4 rounded-lg bg-card border border-border space-y-3">
                  <div className="flex items-center gap-2 mb-2">
                    <ArrowRightLeft className="h-4 w-4 text-primary" />
                    <span className="text-sm font-semibold">
                      Trade Details: {viewingTrade.from} ↔ {viewingTrade.to}
                    </span>
                  </div>
                  <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-1.5">
                      <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                        {viewingTrade.from} Sends
                      </p>
                      {viewingTrade.details.sending.map((item, i) => (
                        <div key={i} className="text-sm px-2 py-1.5 rounded bg-destructive/10 border border-destructive/20">
                          {item}
                        </div>
                      ))}
                    </div>
                    <div className="space-y-1.5">
                      <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                        {viewingTrade.from} Receives
                      </p>
                      {viewingTrade.details.receiving.map((item, i) => (
                        <div key={i} className="text-sm px-2 py-1.5 rounded bg-emerald-500/10 border border-emerald-500/20">
                          {item}
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
              <span className="block">
                Trade: <strong>{trades.find((t) => t.id === acceptConfirmTradeId)?.summary}</strong>
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
