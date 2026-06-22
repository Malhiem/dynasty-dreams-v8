// @ts-nocheck
/**
 * Iter 203 — Draft History page.
 *
 * Lists every completed draft for the active league. The backend marks
 * a draft `status="completed"` in `routes/drafts.py make_draft_pick`
 * the moment the final overall pick is recorded. This page fetches
 * `GET /api/drafts?league_id=...`, filters to `status=completed`, and
 * renders:
 *   - LEFT: a list of completed drafts (most recent first) — each card
 *           shows year/created_at, total picks, rounds × teams.
 *   - RIGHT: when a draft is selected, the full pick log as a Round ×
 *           Pick table with team + player name.
 *
 * Route: `/draft-history` (added in App.js).
 */
import { useEffect, useMemo, useState } from "react";
import { AppLayout } from "@/components/layout/AppLayout";
import { useActiveLeague } from "@/hooks/use-active-league";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Trophy, CalendarDays, Users as UsersIcon, Hash } from "lucide-react";
import api from "@/lib/api";
import { cn } from "@/lib/utils";

interface DraftSummary {
  _id: string;
  league_id: string;
  status: string;
  current_pick: number;
  total_rounds: number;
  snake_draft: boolean;
  team_abbrs: string[];
  picks: any[];
  created_at?: string;
  draft_type?: string;
  name?: string;
}

export default function DraftHistory() {
  const { league, leagueId } = useActiveLeague();
  const [drafts, setDrafts] = useState<DraftSummary[]>([]);
  const [selectedDraftId, setSelectedDraftId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  // ── Fetch all drafts for the active league, filter to completed ──
  useEffect(() => {
    if (!leagueId) {
      setDrafts([]);
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    (async () => {
      try {
        const { data } = await api.get(`/drafts?league_id=${leagueId}`);
        const completed = (Array.isArray(data) ? data : [])
          .filter((d: any) => d.status === "completed")
          .sort((a: any, b: any) =>
            String(b.created_at || "").localeCompare(String(a.created_at || "")),
          );
        if (!cancelled) {
          setDrafts(completed);
          if (completed.length > 0) setSelectedDraftId(completed[0]._id);
        }
      } catch {
        if (!cancelled) setDrafts([]);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [leagueId]);

  const selected = useMemo(
    () => drafts.find((d) => d._id === selectedDraftId) || null,
    [drafts, selectedDraftId],
  );

  return (
    <AppLayout>
      <div className="space-y-6" data-testid="draft-history-page">
        {/* Page header */}
        <div className="flex items-center gap-3">
          <Trophy className="h-6 w-6 text-amber-400" />
          <div>
            <h1 className="text-2xl font-bold tracking-tight">Draft History</h1>
            <p className="text-sm text-muted-foreground">
              {league?.name
                ? `All completed drafts for ${league.name}`
                : "Select a league to view its draft history"}
            </p>
          </div>
        </div>

        {/* Empty / loading states */}
        {loading && (
          <Card>
            <CardContent className="p-8 text-center text-muted-foreground" data-testid="draft-history-loading">
              Loading drafts…
            </CardContent>
          </Card>
        )}
        {!loading && drafts.length === 0 && (
          <Card>
            <CardContent className="p-8 text-center text-muted-foreground" data-testid="draft-history-empty">
              No completed drafts yet for this league. Once a draft finishes (all
              picks made), it will appear here automatically.
            </CardContent>
          </Card>
        )}

        {/* Main grid */}
        {!loading && drafts.length > 0 && (
          <div className="grid grid-cols-1 lg:grid-cols-[320px_1fr] gap-6">
            {/* LEFT — completed drafts list */}
            <div className="space-y-2" data-testid="draft-history-list">
              {drafts.map((d, idx) => {
                const isSelected = d._id === selectedDraftId;
                const totalPicks = (d.picks || []).length;
                const teamsCount = (d.team_abbrs || []).length;
                const dateStr = d.created_at
                  ? new Date(d.created_at).toLocaleDateString(undefined, {
                      year: "numeric",
                      month: "short",
                      day: "numeric",
                    })
                  : "—";
                return (
                  <button
                    key={d._id}
                    type="button"
                    onClick={() => setSelectedDraftId(d._id)}
                    data-testid={`draft-history-card-${d._id}`}
                    className={cn(
                      "w-full text-left rounded-lg border p-3 transition-all",
                      isSelected
                        ? "border-amber-500/60 bg-amber-500/10 shadow-md"
                        : "border-border hover:border-amber-500/30 hover:bg-muted/40",
                    )}
                  >
                    <div className="flex items-center justify-between mb-2">
                      <div className="text-sm font-semibold flex items-center gap-2">
                        <Trophy className="h-3.5 w-3.5 text-amber-400" />
                        Draft #{drafts.length - idx}
                      </div>
                      <Badge
                        variant="outline"
                        className="border-emerald-500/40 text-emerald-300 text-[10px]"
                      >
                        Completed
                      </Badge>
                    </div>
                    <div className="space-y-1 text-xs text-muted-foreground">
                      <div className="flex items-center gap-1.5">
                        <CalendarDays className="h-3 w-3" /> {dateStr}
                      </div>
                      <div className="flex items-center gap-1.5">
                        <UsersIcon className="h-3 w-3" /> {teamsCount} teams ·{" "}
                        {d.total_rounds || "?"} rounds
                      </div>
                      <div className="flex items-center gap-1.5">
                        <Hash className="h-3 w-3" /> {totalPicks} picks
                        {d.snake_draft && " · snake"}
                      </div>
                      {d.draft_type && (
                        <div className="capitalize text-foreground/70">
                          {d.draft_type.replace(/_/g, " ")}
                        </div>
                      )}
                    </div>
                  </button>
                );
              })}
            </div>

            {/* RIGHT — selected draft detail */}
            <Card data-testid="draft-history-detail">
              {selected && (
                <>
                  <CardHeader>
                    <CardTitle className="flex items-center justify-between">
                      <span className="flex items-center gap-2">
                        <Trophy className="h-4 w-4 text-amber-400" />
                        Pick Log
                      </span>
                      <span className="text-xs text-muted-foreground font-normal">
                        {(selected.team_abbrs || []).length} teams ·{" "}
                        {selected.total_rounds} rounds ·{" "}
                        {(selected.picks || []).length} total picks
                      </span>
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <ScrollArea className="h-[calc(100vh-380px)] min-h-[400px]">
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead className="w-16">Overall</TableHead>
                            <TableHead className="w-20">Round</TableHead>
                            <TableHead className="w-20">Pick</TableHead>
                            <TableHead className="w-20">Team</TableHead>
                            <TableHead>Player</TableHead>
                            <TableHead className="w-14">Pos</TableHead>
                            <TableHead className="w-20">NHL</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {(selected.picks || []).map((p: any) => (
                            <TableRow
                              key={p.overall}
                              data-testid={`draft-history-pick-${p.overall}`}
                            >
                              <TableCell className="font-mono text-xs">
                                #{p.overall}
                              </TableCell>
                              <TableCell className="text-xs">{p.round}</TableCell>
                              <TableCell className="text-xs">
                                {p.pick_in_round}
                              </TableCell>
                              <TableCell>
                                <Badge variant="outline" className="text-[10px]">
                                  {p.team}
                                </Badge>
                              </TableCell>
                              <TableCell className="font-medium">
                                {p.player?.name || "—"}
                                {p.auto_picked && (
                                  <Badge
                                    variant="outline"
                                    className="ml-2 text-[10px] border-amber-500/40 text-amber-300"
                                  >
                                    auto
                                  </Badge>
                                )}
                              </TableCell>
                              <TableCell className="text-xs">
                                {p.player?.position || "—"}
                              </TableCell>
                              <TableCell className="text-xs text-muted-foreground">
                                {p.player?.nhlTeam || "—"}
                              </TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </ScrollArea>
                  </CardContent>
                </>
              )}
            </Card>
          </div>
        )}
      </div>
    </AppLayout>
  );
}
