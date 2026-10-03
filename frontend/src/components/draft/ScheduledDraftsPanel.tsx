// @ts-nocheck
// Extracted from lovable/pages/DraftBoard.tsx (Iter 232N.34 refactor).
// Iter 232N.39 — Tiles are now clickable and the parent controls which
// draft is "selected" so the pick-ownership grid + summary badges below
// can scope to that specific scheduled draft. Also exposes the drafts
// list back to the parent via `onDraftsLoaded` so the parent can decide
// which draft to auto-select on first load (prefers ACTIVE, then the
// nearest upcoming SCHEDULED).
import { useState, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Clock, CheckCircle2 } from "lucide-react";
import api from "@/lib/api";
import { cn } from "@/lib/utils";

interface ScheduledDraft {
  id?: string;
  _id?: string;
  name?: string;
  status: string;
  scheduled_time?: string | null;
  total_rounds?: number;
  team_abbrs?: string[];
  team_map?: Record<string, { name?: string }>;
  current_pick?: number;
  picks?: unknown[];
  year?: number;
}

const STATUS_BADGES: Record<string, string> = {
  scheduled: "border-amber-500/40 text-amber-300 bg-amber-500/10",
  active: "border-emerald-500/40 text-emerald-300 bg-emerald-500/10",
  completed: "border-cyan-500/40 text-cyan-300 bg-cyan-500/10",
};

export default function ScheduledDraftsPanel({
  leagueId,
  year,
  selectedDraftId,
  onSelectDraft,
  onDraftsLoaded,
}: {
  leagueId?: string;
  year?: string | number;
  selectedDraftId?: string | null;
  onSelectDraft?: (draftId: string) => void;
  onDraftsLoaded?: (drafts: ScheduledDraft[]) => void;
}) {
  const [drafts, setDrafts] = useState<ScheduledDraft[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!leagueId) return;
    let cancelled = false;
    setLoading(true);
    api
      .get(`/drafts?league_id=${leagueId}`)
      .then(({ data }) => {
        if (cancelled) return;
        let relevant: ScheduledDraft[] = (Array.isArray(data) ? data : [])
          .filter((d: ScheduledDraft) => d && ["scheduled", "active", "completed"].includes(d.status));
        // Iter 232N.39 — Year filter uses hockey-season boundaries
        // (Jul 1 YYYY → Jun 30 YYYY+1) so the "2026/27 Draft Year"
        // dropdown includes drafts scheduled anywhere from summer 2026
        // through spring 2027 (Inaugural in June won't quite fit — we
        // treat June as the tail of the PREVIOUS season). Falls back
        // to the raw `year` field if the backend sets it.
        if (year != null && year !== "") {
          const wantY = Number(year);
          const seasonStart = new Date(Date.UTC(wantY, 6, 1)).getTime();  // Jul 1
          const seasonEnd = new Date(Date.UTC(wantY + 1, 5, 30, 23, 59, 59)).getTime();  // Jun 30 next year
          relevant = relevant.filter((d) => {
            if (d.year != null) return Number(d.year) === wantY;
            if (d.scheduled_time) {
              try {
                const t = new Date(d.scheduled_time).getTime();
                if (t >= seasonStart && t <= seasonEnd) return true;
                // Also include drafts scheduled in the June before season
                // start — that's the classic Entry Draft window that
                // formally belongs to the upcoming season.
                const juneStart = new Date(Date.UTC(wantY, 5, 1)).getTime();
                if (t >= juneStart && t < seasonStart) return true;
                return false;
              } catch { return true; }
            }
            return true;
          });
        }
        relevant.sort((a, b) => {
          const rank: Record<string, number> = { active: 0, scheduled: 1, completed: 2 };
          const ra = rank[a.status] ?? 9;
          const rb = rank[b.status] ?? 9;
          if (ra !== rb) return ra - rb;
          return (a.scheduled_time || "").localeCompare(b.scheduled_time || "");
        });
        setDrafts(relevant);
        onDraftsLoaded?.(relevant);
      })
      .catch(() => {
        setDrafts([]);
        onDraftsLoaded?.([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [leagueId, year]);

  if (loading) {
    return (
      <Card className="border-border gradient-card" data-testid="scheduled-drafts-loading">
        <CardContent className="p-4 text-sm text-muted-foreground italic">
          Loading scheduled drafts…
        </CardContent>
      </Card>
    );
  }
  if (!drafts.length) {
    return (
      <Card className="border-border gradient-card" data-testid="scheduled-drafts-empty">
        <CardContent className="p-4 text-sm text-muted-foreground italic">
          No drafts scheduled for this season yet — commissioners can create one from League Admin → Draft.
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3" data-testid="scheduled-drafts-panel">
      {drafts.map((d) => {
        const picksCount = (d.picks || []).length;
        const totalPicks = (d.total_rounds || 0) * ((d.team_abbrs || []).length || 0);
        const onClockAbbr =
          d.status === "active"
            ? d.team_abbrs?.[((d.current_pick || 1) - 1) % (d.team_abbrs?.length || 1)] || null
            : null;
        const onClockName = onClockAbbr && d.team_map?.[onClockAbbr]?.name;
        const when = d.scheduled_time
          ? new Date(d.scheduled_time).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })
          : "TBD";
        const draftId = d.id || d._id || "";
        const isSelected = selectedDraftId === draftId;
        return (
          <button
            key={draftId}
            type="button"
            onClick={() => onSelectDraft?.(draftId)}
            className="text-left"
            data-testid={`scheduled-draft-card-${draftId}`}
            data-selected={isSelected ? "true" : "false"}
          >
            <Card
              className={cn(
                "border transition-all cursor-pointer",
                isSelected
                  ? "border-cyan-400/60 shadow-[0_0_0_2px_rgba(103,232,249,0.25)] gradient-card"
                  : "border-border gradient-card hover:border-cyan-500/40",
              )}
            >
              <CardHeader className="pb-2">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <CardTitle className="text-base truncate flex items-center gap-1.5">
                      {isSelected && <CheckCircle2 className="h-3.5 w-3.5 text-cyan-300 shrink-0" />}
                      {d.name || "Untitled Draft"}
                    </CardTitle>
                    <p className="text-[11px] text-muted-foreground mt-0.5">
                      {when} · {d.total_rounds || "?"} round{d.total_rounds === 1 ? "" : "s"} · {(d.team_abbrs || []).length} teams
                    </p>
                  </div>
                  <Badge
                    variant="outline"
                    className={cn("text-[10px] h-5 whitespace-nowrap", STATUS_BADGES[d.status] || "")}
                  >
                    {String(d.status).toUpperCase()}
                  </Badge>
                </div>
              </CardHeader>
              <CardContent className="pt-1 pb-3 space-y-1.5">
                <div className="flex items-center gap-2 text-xs">
                  <span className="text-muted-foreground uppercase tracking-wider text-[10px]">Picks made</span>
                  <span className="font-mono text-foreground font-semibold">
                    {picksCount}
                    {totalPicks ? ` / ${totalPicks}` : ""}
                  </span>
                </div>
                {onClockName && (
                  <div className="flex items-center gap-2 text-xs text-emerald-300">
                    <Clock className="h-3 w-3" />
                    <span>
                      On the clock: <span className="font-semibold">{onClockName}</span>
                    </span>
                  </div>
                )}
                <p className="text-[10px] text-cyan-300/80 italic pt-0.5">
                  {isSelected ? "Showing ownership below" : "Click to view pick ownership"}
                </p>
              </CardContent>
            </Card>
          </button>
        );
      })}
    </div>
  );
}
