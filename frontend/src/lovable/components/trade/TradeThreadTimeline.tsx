// @ts-nocheck
// Iter 232M.2 — TradeThreadTimeline
//
// Renders the negotiation history for a trade whose `counter_thread_root`
// pulls in every counter that came before or after it. Ordered by
// `counter_depth` so it reads: Proposal #1 → Counter #2 → Counter #3 →
// (final action). The currently-viewed trade is highlighted so managers
// know where they are in the thread.
//
// Only mounts when the thread has more than one entry — for a plain
// accept/reject trade there's nothing to show.
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api from "@/lib/api";
import {
  ArrowRightLeft, Reply, CheckCircle2, XCircle, Clock, MinusCircle, GitBranch,
  Bell, BellOff,
} from "lucide-react";
import { toast } from "sonner";

// Icon + colour for each terminal state we might land on in a thread.
const STEP_ICON: Record<string, any> = {
  proposed: Clock,
  pending: Clock,
  accepted: CheckCircle2,
  executed: CheckCircle2,
  rejected: XCircle,
  vetoed: XCircle,
  cancelled: MinusCircle,
  withdrawn: MinusCircle,
  countered: Reply,
};
const STEP_TONE: Record<string, string> = {
  proposed: "border-amber-500/40 text-amber-300 bg-amber-500/5",
  pending: "border-cyan-500/40 text-cyan-300 bg-cyan-500/5",
  accepted: "border-emerald-500/40 text-emerald-300 bg-emerald-500/5",
  executed: "border-emerald-500/40 text-emerald-300 bg-emerald-500/5",
  rejected: "border-rose-500/40 text-rose-300 bg-rose-500/5",
  vetoed: "border-rose-500/40 text-rose-300 bg-rose-500/5",
  cancelled: "border-zinc-500/40 text-zinc-300 bg-zinc-500/5",
  withdrawn: "border-zinc-500/40 text-zinc-300 bg-zinc-500/5",
  countered: "border-sky-500/40 text-sky-300 bg-sky-500/5",
};

const STEP_LABEL: Record<string, string> = {
  proposed: "Awaiting Response",
  pending: "In Review",
  accepted: "Accepted",
  executed: "Executed",
  rejected: "Rejected",
  vetoed: "Vetoed",
  cancelled: "Cancelled",
  withdrawn: "Withdrawn",
  countered: "Countered",
};

function fmtTs(iso?: string | null) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString(undefined, {
      month: "short", day: "numeric", hour: "numeric", minute: "2-digit",
    });
  } catch {
    return iso.slice(0, 16).replace("T", " ");
  }
}

export function TradeThreadTimeline({ tradeId }: { tradeId: string }) {
  const [thread, setThread] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  // Iter 232M.4 — per-thread mute state for the current user.
  const [muted, setMuted] = useState(false);
  const [mutePending, setMutePending] = useState(false);

  useEffect(() => {
    if (!tradeId) return;
    let cancelled = false;
    setLoading(true);
    Promise.all([
      api.get(`/trades/${tradeId}/thread`).catch(() => ({ data: { thread: [] } })),
      api.get(`/trades/${tradeId}/thread/mute-state`).catch(() => ({ data: { muted: false } })),
    ]).then(([threadRes, muteRes]) => {
      if (cancelled) return;
      setThread(threadRes.data?.thread || []);
      setMuted(Boolean(muteRes.data?.muted));
    }).finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [tradeId]);

  const toggleMute = async () => {
    if (mutePending) return;
    const next = !muted;
    setMutePending(true);
    setMuted(next);  // optimistic
    try {
      await api.post(`/trades/${tradeId}/thread/mute`, { muted: next });
      toast.success(
        next
          ? "Notifications muted for this negotiation"
          : "Notifications on for this negotiation",
      );
    } catch (e) {
      setMuted(!next);  // rollback
      toast.error("Couldn't update mute", {
        description: e?.response?.data?.detail || e?.message,
      });
    } finally {
      setMutePending(false);
    }
  };

  if (loading || thread.length <= 1) return null;

  return (
    <div
      className="rounded-lg border border-sky-500/30 bg-sky-500/[0.03] p-4 space-y-3"
      data-testid="trade-thread-timeline"
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-sky-300 font-semibold">
          <GitBranch className="h-3.5 w-3.5" />
          Negotiation History · {thread.length} step{thread.length === 1 ? "" : "s"}
        </div>
        <button
          type="button"
          onClick={toggleMute}
          disabled={mutePending}
          aria-pressed={muted}
          data-testid="trade-thread-mute-toggle"
          title={muted ? "You're muting this negotiation — click to un-mute" : "Mute this negotiation for you"}
          className={
            "inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-[11px] font-medium transition-colors " +
            (muted
              ? "bg-secondary/50 text-muted-foreground hover:bg-secondary/70"
              : "text-sky-300 hover:bg-sky-500/10")
          }
        >
          {muted ? <BellOff className="h-3.5 w-3.5" /> : <Bell className="h-3.5 w-3.5" />}
          {muted ? "Muted" : "Mute"}
        </button>
      </div>
      <ol className="space-y-2">
        {thread.map((step, idx) => {
          const isCurrent = step.id === tradeId;
          const status = step.status || "proposed";
          const Icon = STEP_ICON[status] || Clock;
          const tone = STEP_TONE[status] || STEP_TONE.proposed;
          const label = STEP_LABEL[status] || status;
          const isCounter = step.counter_depth > 0;
          const stepKind = isCounter ? `Counter #${idx + 1}` : "Proposal";
          return (
            <li key={step.id} className="flex items-start gap-3">
              {/* Vertical connector rail */}
              <div className="flex flex-col items-center pt-1">
                <div className={`flex h-7 w-7 items-center justify-center rounded-full border ${tone}`}>
                  {isCounter && idx > 0
                    ? <Reply className="h-3.5 w-3.5" />
                    : <ArrowRightLeft className="h-3.5 w-3.5" />}
                </div>
                {idx < thread.length - 1 && (
                  <div className="w-px flex-1 min-h-[24px] bg-border/60 mt-1" />
                )}
              </div>

              {/* Step content */}
              <div
                className={
                  "flex-1 rounded-md border px-3 py-2 transition-colors " +
                  (isCurrent
                    ? "border-sky-500/60 bg-sky-500/10 ring-1 ring-sky-500/40"
                    : "border-border/60 bg-secondary/20")
                }
                data-testid={`trade-thread-step-${idx}`}
              >
                <div className="flex items-center justify-between gap-2 flex-wrap">
                  <div className="flex items-center gap-2">
                    <span className="text-xs uppercase tracking-wider text-muted-foreground font-semibold">
                      {stepKind}
                    </span>
                    <span className="text-sm">
                      <span className="text-foreground font-medium">{step.proposer_team_name || "?"}</span>
                      <span className="text-muted-foreground mx-1.5">→</span>
                      <span className="text-foreground font-medium">{step.target_team_name || "?"}</span>
                    </span>
                    {isCurrent && (
                      <span
                        className="text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded bg-sky-500/25 text-sky-100 border border-sky-500/40"
                        data-testid={`trade-thread-current-marker-${idx}`}
                      >
                        Viewing
                      </span>
                    )}
                  </div>
                  <div className={`inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded border ${tone}`}>
                    <Icon className="h-3 w-3" />
                    {label}
                  </div>
                </div>
                <div className="flex items-center justify-between gap-2 flex-wrap mt-1">
                  <div className="text-[11px] text-muted-foreground">
                    Sent {fmtTs(step.submitted_at)}
                    {step.responded_at && (
                      <> · Responded {fmtTs(step.responded_at)}</>
                    )}
                    {step.processed_at && !step.responded_at && (
                      <> · Executed {fmtTs(step.processed_at)}</>
                    )}
                  </div>
                  {!isCurrent && (
                    <Link
                      to={`/transactions/trade/${step.id}`}
                      className="text-[11px] text-sky-300 hover:text-sky-100 underline underline-offset-2"
                      data-testid={`trade-thread-step-link-${idx}`}
                    >
                      Open →
                    </Link>
                  )}
                </div>
                {step.message && (
                  <p className="text-[11px] text-muted-foreground italic mt-1.5 line-clamp-2">
                    &ldquo;{step.message}&rdquo;
                  </p>
                )}
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
