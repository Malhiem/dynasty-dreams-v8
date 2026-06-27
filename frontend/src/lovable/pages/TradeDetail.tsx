// @ts-nocheck
/**
 * Iter 231i — Trade detail page deep-linked from notifications.
 *
 * Route: /transactions/trade/:tradeId
 *
 * Renders a single trade proposal with:
 *   • Accept / Reject buttons (visible to recipient team owner / co-owner)
 *   • Cancel button (visible to the proposer while still in `proposed` or `pending`)
 *   • Pending Response / Pending Review banner reflecting the current state
 *   • A read-only summary of assets exchanged
 *
 * Backend contract (iter 231h):
 *   GET  /api/trades/{id}                  – fetch trade
 *   POST /api/trades/{id}/respond          – { action: "accept" | "reject", reason? }
 *   POST /api/trades/{id}/cancel           – proposer cancels
 */
import { useEffect, useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { AppLayout } from "@/components/layout/AppLayout";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { ArrowLeft, Check, X, AlertCircle, Loader2, Clock, ArrowRightLeft } from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";

const STATUS_META: Record<string, { label: string; tone: string }> = {
  proposed: { label: "Awaiting Response", tone: "bg-amber-500/20 text-amber-300" },
  pending: { label: "In Review Window", tone: "bg-cyan-500/20 text-cyan-300" },
  accepted: { label: "Accepted", tone: "bg-green-500/20 text-green-300" },
  rejected: { label: "Rejected", tone: "bg-red-500/20 text-red-300" },
  vetoed: { label: "Vetoed", tone: "bg-red-500/20 text-red-300" },
  executed: { label: "Executed", tone: "bg-green-500/20 text-green-300" },
  cancelled: { label: "Cancelled", tone: "bg-zinc-500/20 text-zinc-300" },
  expired: { label: "Expired", tone: "bg-zinc-500/20 text-zinc-300" },
};

function AssetList({ title, assets, testId }: { title: string; assets: any[]; testId: string }) {
  return (
    <div className="space-y-2" data-testid={testId}>
      <p className="text-xs uppercase tracking-wider text-[#A1A1AA] font-semibold">{title}</p>
      {(assets || []).length === 0 ? (
        <p className="text-sm italic text-[#52525B]">Nothing on this side</p>
      ) : (
        <ul className="space-y-1.5">
          {(assets || []).map((a: any, i: number) => (
            <li
              key={i}
              className="flex items-center justify-between gap-2 rounded-md bg-white/5 px-3 py-2 text-sm"
              data-testid={`${testId}-item-${i}`}
            >
              <span className="text-white truncate">
                {a.player_name ||
                  (a.asset_type === "pick"
                    ? `${a.pick_year || ""} ${a.pick_round ? `R${a.pick_round}` : ""} pick`.trim()
                    : a.asset_type || "Asset")}
              </span>
              {a.salary != null && (
                <span className="text-xs text-[#A1A1AA] shrink-0">${(Number(a.salary) / 1_000_000).toFixed(1)}M</span>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function TradeDetail() {
  const { tradeId } = useParams<{ tradeId: string }>();
  const navigate = useNavigate();
  const { user } = useAuth();
  const [trade, setTrade] = useState<any | null>(null);
  const [loading, setLoading] = useState(true);
  const [acting, setActing] = useState<"" | "accept" | "reject" | "cancel">("");
  const [rejectReason, setRejectReason] = useState("");
  const [showRejectInput, setShowRejectInput] = useState(false);

  useEffect(() => {
    if (!tradeId) return;
    let alive = true;
    (async () => {
      setLoading(true);
      try {
        const { data } = await api.get(`/trades/${tradeId}`);
        if (alive) setTrade(data);
      } catch (e: any) {
        toast.error(e?.response?.data?.detail || "Couldn't load trade", { description: e?.message });
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => {
      alive = false;
    };
  }, [tradeId]);

  if (loading) {
    return (
      <AppLayout>
        <div className="container mx-auto px-4 py-8 max-w-3xl">
          <div className="flex items-center justify-center text-[#A1A1AA]" data-testid="trade-detail-loading">
            <Loader2 className="h-5 w-5 animate-spin mr-2" /> Loading trade…
          </div>
        </div>
      </AppLayout>
    );
  }

  if (!trade) {
    return (
      <AppLayout>
        <div className="container mx-auto px-4 py-8 max-w-3xl">
          <Card className="bg-card border-border" data-testid="trade-detail-missing">
            <CardContent className="py-12 text-center">
              <AlertCircle className="h-10 w-10 text-amber-400 mx-auto mb-3" />
              <p className="text-white font-medium mb-1">Trade not found</p>
              <p className="text-sm text-[#A1A1AA] mb-4">It may have been cancelled or rejected.</p>
              <Button asChild variant="outline" size="sm">
                <Link to="/transactions">Back to Transactions</Link>
              </Button>
            </CardContent>
          </Card>
        </div>
      </AppLayout>
    );
  }

  const isRecipient = trade.target_owner_id === user?.id;
  const isProposer = trade.proposer_id === user?.id;
  const status = trade.status as string;
  const meta = STATUS_META[status] || { label: status, tone: "bg-zinc-500/20 text-zinc-300" };
  const canRespond = isRecipient && status === "proposed";
  const canCancel = isProposer && (status === "proposed" || status === "pending");

  const refetch = async () => {
    try {
      const { data } = await api.get(`/trades/${tradeId}`);
      setTrade(data);
    } catch {
      /* ignore — caller already toasted */
    }
  };

  const handleAccept = async () => {
    setActing("accept");
    try {
      await api.post(`/trades/${tradeId}/respond`, { action: "accept" });
      toast.success("Trade accepted — now in league review.");
      await refetch();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Couldn't accept trade");
    } finally {
      setActing("");
    }
  };

  const handleReject = async () => {
    if (!showRejectInput) {
      setShowRejectInput(true);
      return;
    }
    setActing("reject");
    try {
      await api.post(`/trades/${tradeId}/respond`, { action: "reject", reason: rejectReason.trim() || undefined });
      toast.success("Trade rejected.");
      await refetch();
      setShowRejectInput(false);
      setRejectReason("");
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Couldn't reject trade");
    } finally {
      setActing("");
    }
  };

  const handleCancel = async () => {
    if (!window.confirm("Cancel this trade proposal?")) return;
    setActing("cancel");
    try {
      await api.post(`/trades/${tradeId}/cancel`);
      toast.success("Trade cancelled.");
      await refetch();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Couldn't cancel trade");
    } finally {
      setActing("");
    }
  };

  // Banner — surfaces the state in the user's terms.
  const banner =
    canRespond
      ? { tone: "border-amber-500/40 bg-amber-500/10 text-amber-200", text: "Pending Response — review the offer below and Accept or Reject." }
      : isProposer && status === "proposed"
      ? { tone: "border-cyan-500/40 bg-cyan-500/10 text-cyan-200", text: `Pending Response from ${trade.target_team_name}.` }
      : status === "pending"
      ? { tone: "border-cyan-500/40 bg-cyan-500/10 text-cyan-200", text: `Pending Review — accepted by ${trade.target_team_name}, now in the league review window.` }
      : null;

  return (
    <AppLayout>
      <div className="container mx-auto px-4 py-6 max-w-3xl space-y-4">
        <Button
          variant="ghost"
          size="sm"
          asChild
          data-testid="trade-detail-back"
          className="text-[#A1A1AA] hover:text-white"
        >
          <Link to="/transactions" className="gap-1.5">
            <ArrowLeft className="h-3.5 w-3.5" /> Back to Transactions
          </Link>
        </Button>

        {banner && (
          <div
            data-testid="trade-detail-banner"
            className={`rounded-lg border px-4 py-2.5 text-sm ${banner.tone}`}
          >
            {banner.text}
          </div>
        )}

        <Card className="bg-card border-border" data-testid="trade-detail-card">
          <CardHeader>
            <div className="flex items-start justify-between gap-3 flex-wrap">
              <div>
                <CardTitle className="flex items-center gap-2 text-base">
                  <ArrowRightLeft className="h-4 w-4 text-[#00D2FF]" />
                  Trade Proposal
                </CardTitle>
                <CardDescription className="mt-1">
                  {trade.proposer_team_name} <span className="text-[#52525B]">↔</span> {trade.target_team_name}
                </CardDescription>
              </div>
              <Badge className={`${meta.tone} border-0`} data-testid="trade-detail-status-badge">{meta.label}</Badge>
            </div>
          </CardHeader>
          <CardContent className="space-y-5">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
              <AssetList
                title={`${trade.proposer_team_name} sends`}
                assets={trade.assets_offered}
                testId="trade-detail-offered"
              />
              <AssetList
                title={`${trade.target_team_name} sends`}
                assets={trade.assets_requested}
                testId="trade-detail-requested"
              />
            </div>

            {trade.message && (
              <div className="rounded-md bg-white/5 p-3 text-sm text-white" data-testid="trade-detail-message">
                <p className="text-xs uppercase tracking-wider text-[#A1A1AA] font-semibold mb-1">Message</p>
                {trade.message}
              </div>
            )}

            {trade.processes_at && status === "pending" && (
              <div className="flex items-center gap-2 text-xs text-[#A1A1AA]">
                <Clock className="h-3.5 w-3.5" />
                Auto-processes at {new Date(trade.processes_at).toLocaleString()}
              </div>
            )}

            {showRejectInput && canRespond && (
              <div className="space-y-2 pt-2" data-testid="trade-detail-reject-reason-wrap">
                <p className="text-xs text-[#A1A1AA]">Optional — share why you&apos;re rejecting:</p>
                <Textarea
                  value={rejectReason}
                  onChange={(e) => setRejectReason(e.target.value)}
                  placeholder="e.g. Pick values don't line up"
                  rows={2}
                  data-testid="trade-detail-reject-reason"
                />
              </div>
            )}
          </CardContent>
        </Card>

        {/* Action row — Iter 231k: mobile-friendly. On small screens the
            buttons stack full-width with a comfortable 44px+ touch target
            and the Accept button is sticky-bottom-stacked so it's always
            within thumb reach. */}
        {(canRespond || canCancel) && (
          <div
            className="flex flex-col-reverse sm:flex-row gap-2 sm:justify-end sticky bottom-0 sm:static bg-[#0A0A0A]/95 sm:bg-transparent backdrop-blur-sm sm:backdrop-blur-none -mx-4 sm:mx-0 px-4 sm:px-0 py-3 sm:py-0 border-t border-white/10 sm:border-0"
            data-testid="trade-detail-actions"
          >
            {canRespond && (
              <>
                <Button
                  variant="destructive"
                  onClick={handleReject}
                  disabled={acting !== ""}
                  data-testid="trade-detail-reject-btn"
                  className="w-full sm:w-auto min-h-[44px]"
                >
                  {acting === "reject" ? <Loader2 className="h-4 w-4 animate-spin mr-1.5" /> : <X className="h-4 w-4 mr-1.5" />}
                  {showRejectInput ? "Confirm Reject" : "Reject"}
                </Button>
                <Button
                  onClick={handleAccept}
                  disabled={acting !== ""}
                  data-testid="trade-detail-accept-btn"
                  className="bg-green-500/20 hover:bg-green-500/30 text-green-300 w-full sm:w-auto min-h-[44px]"
                >
                  {acting === "accept" ? <Loader2 className="h-4 w-4 animate-spin mr-1.5" /> : <Check className="h-4 w-4 mr-1.5" />}
                  Accept
                </Button>
              </>
            )}
            {canCancel && (
              <Button
                variant="outline"
                onClick={handleCancel}
                disabled={acting !== ""}
                data-testid="trade-detail-cancel-btn"
                className="w-full sm:w-auto min-h-[44px]"
              >
                {acting === "cancel" ? <Loader2 className="h-4 w-4 animate-spin mr-1.5" /> : <X className="h-4 w-4 mr-1.5" />}
                Cancel Proposal
              </Button>
            )}
          </div>
        )}
      </div>
    </AppLayout>
  );
}
