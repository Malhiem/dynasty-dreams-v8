// @ts-nocheck
// Extracted from lovable/pages/DraftBoard.tsx (Iter 232N.34 refactor).
// Fetches all drafts scheduled/active/completed for a league and renders one
// card per draft with its own pick count, status, and on-clock team. Replaces
// the old year-only Draft Board view that aggregated Summer + Winter drafts
// into a single misleading "0 picks" grid.
import { useState, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Clock } from "lucide-react";
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
}

const STATUS_BADGES: Record<string, string> = {
  scheduled: "border-amber-500/40 text-amber-300 bg-amber-500/10",
  active: "border-emerald-500/40 text-emerald-300 bg-emerald-500/10",
  completed: "border-cyan-500/40 text-cyan-300 bg-cyan-500/10",
};

export default function ScheduledDraftsPanel({ leagueId }: { leagueId?: string }) {
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
        const relevant: ScheduledDraft[] = (Array.isArray(data) ? data : [])
          .filter((d: ScheduledDraft) => d && ["scheduled", "active", "completed"].includes(d.status))
          .sort((a: ScheduledDraft, b: ScheduledDraft) => {
            // Active first, then scheduled, then completed. Within each group,
            // sort by scheduled_time ascending so upcoming drafts show above
            // completed ones.
            const rank: Record<string, number> = { active: 0, scheduled: 1, completed: 2 };
            const ra = rank[a.status] ?? 9;
            const rb = rank[b.status] ?? 9;
            if (ra !== rb) return ra - rb;
            return (a.scheduled_time || "").localeCompare(b.scheduled_time || "");
          });
        setDrafts(relevant);
      })
      .catch(() => setDrafts([]))
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [leagueId]);

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
          No drafts scheduled yet — commissioners can create one from League Admin → Draft.
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="grid gap-3 md:grid-cols-2" data-testid="scheduled-drafts-panel">
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
        const draftId = d.id || d._id;
        return (
          <Card
            key={draftId}
            className="border-border gradient-card"
            data-testid={`scheduled-draft-card-${draftId}`}
          >
            <CardHeader className="pb-2">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <CardTitle className="text-base truncate">{d.name || "Untitled Draft"}</CardTitle>
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
                <span className="text-muted-foreground uppercase tracking-wider text-[10px]">Picks</span>
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
              {d.status === "active" ? (
                <a
                  href={`/draft-room/${draftId}`}
                  className="inline-block text-[11px] text-primary hover:underline mt-1"
                  data-testid={`scheduled-draft-open-${draftId}`}
                >
                  Open draft room →
                </a>
              ) : d.status === "completed" ? (
                <a
                  href={`/draft-room/${draftId}`}
                  className="inline-block text-[11px] text-muted-foreground hover:underline mt-1"
                >
                  View results →
                </a>
              ) : (
                <p className="text-[11px] text-amber-300/80 italic">Scheduled — waiting to start</p>
              )}
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}
