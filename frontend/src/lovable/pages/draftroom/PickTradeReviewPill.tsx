// @ts-nocheck
/**
 * Iter 194c-frontend — PickTradeReviewPill
 *
 * Floating "Pick Trade Pending" widget mounted in the Draft Room's
 * top-right corner while a pick trade is in flight. Reads its state
 * from `draft_chat` WS messages broadcast by the backend
 * (kinds: pick_trade_proposed / vote / executed / vetoed /
 * auto_resolved). Falls back to GET /api/drafts/{lid}/pick-trade/{tid}
 * polling every 10s in case the WS drops.
 *
 * Exposes Approve / Veto buttons that POST to
 * /api/drafts/{league_id}/pick-trade/{trade_id}/vote and updates the
 * countdown in real time off `review_expires_at`.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import api from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { ArrowLeftRight, Check, X, Clock } from "lucide-react";

interface PickTrade {
  trade_id: string;
  status: string;
  review_expires_at: string;
  votes?: { approve?: number; veto?: number; choices?: Record<string, string> };
  post_review_action?: string;
  proposer_team_id?: string;
  receiver_team_id?: string;
}

export default function PickTradeReviewPill({
  leagueId, lastChatEvent, currentUserId,
}: {
  leagueId: string;
  /** the most recent draft_chat WS payload (parent forwards it) */
  lastChatEvent?: any;
  currentUserId?: string;
}) {
  const [trade, setTrade] = useState<PickTrade | null>(null);
  const [now, setNow] = useState<number>(Date.now());
  const [voting, setVoting] = useState(false);
  const dismissedIds = useRef<Set<string>>(new Set());

  // ── 1-second countdown tick ──
  useEffect(() => {
    if (!trade) return;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [trade?.trade_id]);

  // ── Hydrate from WS event ──
  useEffect(() => {
    if (!lastChatEvent || lastChatEvent.type !== "draft_chat") return;
    const { kind, trade_id, votes } = lastChatEvent;
    if (!kind || !trade_id) return;
    if (dismissedIds.current.has(trade_id) && kind !== "pick_trade_proposed") return;

    if (kind === "pick_trade_proposed") {
      // Newly proposed — fetch full state.
      api.get(`/drafts/${leagueId}/pick-trade/${trade_id}`)
        .then(({ data }) => {
          if (data?.status === "pending_draft_review") {
            setTrade(data);
          }
        })
        .catch(() => {});
    } else if (kind === "pick_trade_vote" && trade?.trade_id === trade_id) {
      setTrade((prev) => prev ? { ...prev, votes: { ...(prev.votes || {}), ...(votes || {}) } } : prev);
    } else if (["pick_trade_executed", "pick_trade_vetoed", "pick_trade_auto_resolved"].includes(kind)) {
      if (trade?.trade_id === trade_id) {
        dismissedIds.current.add(trade_id);
        toast.info(
          kind === "pick_trade_executed" ? "Pick trade executed"
          : kind === "pick_trade_vetoed" ? "Pick trade vetoed by the league"
          : "Pick trade auto-resolved",
        );
        setTrade(null);
      }
    }
  }, [lastChatEvent, leagueId, trade?.trade_id]);

  // ── Polling fallback ──
  useEffect(() => {
    if (!trade) return;
    const poll = setInterval(async () => {
      try {
        const { data } = await api.get(`/drafts/${leagueId}/pick-trade/${trade.trade_id}`);
        if (data?.status !== "pending_draft_review") {
          dismissedIds.current.add(trade.trade_id);
          setTrade(null);
        } else {
          setTrade((prev) => prev ? { ...prev, ...data } : prev);
        }
      } catch {}
    }, 10000);
    return () => clearInterval(poll);
  }, [trade?.trade_id, leagueId]);

  const remainingMs = useMemo(() => {
    if (!trade) return 0;
    return Math.max(0, new Date(trade.review_expires_at).getTime() - now);
  }, [trade, now]);

  const mm = Math.floor(remainingMs / 60000);
  const ss = Math.floor((remainingMs % 60000) / 1000);

  const myVote = trade?.votes?.choices?.[currentUserId || ""];
  const approves = trade?.votes?.approve ?? 0;
  const vetoes = trade?.votes?.veto ?? 0;

  const castVote = async (choice: "approve" | "veto") => {
    if (!trade || voting) return;
    setVoting(true);
    try {
      const { data } = await api.post(
        `/drafts/${leagueId}/pick-trade/${trade.trade_id}/vote`,
        { choice },
      );
      setTrade((prev) => prev ? { ...prev, votes: data.votes } : prev);
      if (data.decision) {
        dismissedIds.current.add(trade.trade_id);
        toast.success(
          data.decision === "approved" ? "Trade approved + executed"
          : data.decision === "vetoed" ? "Trade vetoed"
          : "Vote recorded",
        );
        if (data.decision !== null) setTrade(null);
      } else {
        toast.success(`Vote recorded: ${choice}`);
      }
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Failed to vote");
    } finally {
      setVoting(false);
    }
  };

  if (!trade) return null;

  // Urgency styling once <2 min remain
  const urgent = remainingMs < 120_000;

  return (
    <div
      className={`fixed top-20 right-4 z-50 w-80 rounded-xl border-2 backdrop-blur-md shadow-2xl ${
        urgent
          ? "border-rose-500/60 bg-rose-950/70 shadow-rose-500/20"
          : "border-amber-500/50 bg-amber-950/60 shadow-amber-500/15"
      } animate-in slide-in-from-right`}
      data-testid="pick-trade-review-pill"
    >
      <div className="p-3 space-y-2">
        <div className="flex items-center gap-2">
          <ArrowLeftRight className={`h-4 w-4 ${urgent ? "text-rose-300" : "text-amber-300"}`} />
          <div className="text-xs font-bold uppercase tracking-wider text-foreground">
            Pick Trade Pending
          </div>
          <div className="ml-auto flex items-center gap-1 text-xs font-mono">
            <Clock className="h-3 w-3" />
            <span data-testid="pick-trade-countdown">
              {mm}:{String(ss).padStart(2, "0")}
            </span>
          </div>
        </div>
        <div className="text-[11px] text-muted-foreground">
          League is reviewing this trade. {trade.post_review_action === "majority_vote" ? "Majority vote required." : trade.post_review_action === "auto_execute" ? "Will auto-execute on expiry." : trade.post_review_action === "require_admin" ? "Requires admin approval." : ""}
        </div>
        <div className="flex items-center justify-between text-[11px]" data-testid="pick-trade-tally">
          <span className="text-emerald-300 font-mono">✓ {approves}</span>
          <span className="text-rose-300 font-mono">✗ {vetoes}</span>
        </div>
        <div className="flex gap-2">
          <Button
            size="sm"
            className={`flex-1 h-8 text-xs ${
              myVote === "approve"
                ? "bg-emerald-500 hover:bg-emerald-400 text-emerald-950"
                : "bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-200 border border-emerald-500/40"
            }`}
            onClick={() => castVote("approve")}
            disabled={voting}
            data-testid="pick-trade-approve-btn"
          >
            <Check className="h-3 w-3 mr-1" />
            Approve
          </Button>
          <Button
            size="sm"
            className={`flex-1 h-8 text-xs ${
              myVote === "veto"
                ? "bg-rose-500 hover:bg-rose-400 text-rose-950"
                : "bg-rose-500/20 hover:bg-rose-500/30 text-rose-200 border border-rose-500/40"
            }`}
            onClick={() => castVote("veto")}
            disabled={voting}
            data-testid="pick-trade-veto-btn"
          >
            <X className="h-3 w-3 mr-1" />
            Veto
          </Button>
        </div>
      </div>
    </div>
  );
}
