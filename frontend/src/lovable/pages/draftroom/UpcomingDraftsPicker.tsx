// @ts-nocheck
/**
 * Iter 229j — Upcoming Drafts picker dropdown. Extracted from
 * DraftRoom.tsx. Renders only when the league has 2+ drafts (active
 * or scheduled) within the next 30 days; defaults to the live draft
 * if any, otherwise the soonest scheduled one.
 *
 * Iter 230w — Active drafts are highlighted with a pulsing LIVE pill
 * so a commissioner running multiple drafts can see at a glance which
 * one is in-progress vs. queued for later. The picker now also shows
 * up whenever any draft is present (even just one) so users always
 * have a way to see "which draft am I in?".
 */
import type { UpcomingDraft } from "@/hooks/use-upcoming-drafts";
import { Radio, Calendar } from "lucide-react";

interface Props {
  upcomingDrafts: UpcomingDraft[];
  selectedDraftId: string | null;
  setSelectedDraftId: (id: string) => void;
}

function _fmtWhen(scheduledTime?: string | null): string {
  if (!scheduledTime) return "TBD";
  return new Date(scheduledTime).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

export default function UpcomingDraftsPicker({ upcomingDrafts, selectedDraftId, setSelectedDraftId }: Props) {
  // Iter 230w — Hide ONLY when the league has zero drafts. With a
  // single draft, still show the row so the user can see the active
  // draft name + LIVE status indicator (the dropdown is disabled).
  if (upcomingDrafts.length === 0) return null;

  const selectedDraft = upcomingDrafts.find((d) => (d._id || d.id) === selectedDraftId);
  const isSelectedActive = selectedDraft?.status === "active";
  const activeCount = upcomingDrafts.filter((d) => d.status === "active").length;

  return (
    <div
      className="flex flex-col sm:flex-row sm:items-center gap-2 rounded-md border border-border/60 bg-muted/20 px-3 py-2"
      data-testid="draft-room-upcoming-picker"
    >
      <div className="flex items-center gap-2 min-w-0">
        {isSelectedActive ? (
          <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/15 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-emerald-400 ring-1 ring-emerald-500/30">
            <span className="relative flex h-1.5 w-1.5">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
              <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-emerald-400"></span>
            </span>
            Live
          </span>
        ) : (
          <Calendar size={14} className="text-muted-foreground" />
        )}
        <span className="text-xs uppercase tracking-wider text-muted-foreground whitespace-nowrap">
          {upcomingDrafts.length === 1 ? "Draft" : `Drafts (${upcomingDrafts.length})`}
          {activeCount > 0 && upcomingDrafts.length > 1 ? (
            <span className="ml-1 text-emerald-400 normal-case">· {activeCount} live</span>
          ) : null}
        </span>
      </div>
      <select
        className="bg-background border border-border rounded px-2 py-1 text-sm flex-1 min-w-0"
        value={selectedDraftId || ""}
        onChange={(e) => setSelectedDraftId(e.target.value)}
        disabled={upcomingDrafts.length <= 1}
        data-testid="draft-room-upcoming-select"
      >
        {upcomingDrafts.map((d) => {
          const id = d._id || d.id;
          const liveTag = d.status === "active" ? "● LIVE — " : "";
          return (
            <option key={id} value={id}>
              {liveTag}{d.name || "Untitled Draft"} · {_fmtWhen(d.scheduled_time)}
            </option>
          );
        })}
      </select>
    </div>
  );
}
