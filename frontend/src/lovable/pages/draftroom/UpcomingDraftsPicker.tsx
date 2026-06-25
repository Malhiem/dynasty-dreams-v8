// @ts-nocheck
/**
 * Iter 229j — Upcoming Drafts picker dropdown. Extracted from
 * DraftRoom.tsx. Renders only when the league has 2+ scheduled drafts
 * within the next 30 days; defaults to the soonest.
 */
import type { UpcomingDraft } from "@/hooks/use-upcoming-drafts";

interface Props {
  upcomingDrafts: UpcomingDraft[];
  selectedDraftId: string | null;
  setSelectedDraftId: (id: string) => void;
}

export default function UpcomingDraftsPicker({ upcomingDrafts, selectedDraftId, setSelectedDraftId }: Props) {
  if (upcomingDrafts.length <= 1) return null;
  return (
    <div
      className="flex flex-col sm:flex-row sm:items-center gap-2 rounded-md border border-border/60 bg-muted/20 px-3 py-2"
      data-testid="draft-room-upcoming-picker"
    >
      <span className="text-xs uppercase tracking-wider text-muted-foreground">
        Upcoming drafts ({upcomingDrafts.length})
      </span>
      <select
        className="bg-background border border-border rounded px-2 py-1 text-sm flex-1"
        value={selectedDraftId || ""}
        onChange={(e) => setSelectedDraftId(e.target.value)}
        data-testid="draft-room-upcoming-select"
      >
        {upcomingDrafts.map((d) => {
          const id = d._id || d.id;
          const when = d.scheduled_time
            ? new Date(d.scheduled_time).toLocaleString(undefined, {
                month: "short", day: "numeric",
                hour: "numeric", minute: "2-digit",
              })
            : "TBD";
          return (
            <option key={id} value={id}>
              {d.name || "Untitled Draft"} · {when}
            </option>
          );
        })}
      </select>
    </div>
  );
}
