// @ts-nocheck
// Extracted from lovable/pages/DraftBoard.tsx (Iter 232N.34 refactor).
// Owns the Iter 138 draft-order-status banner and the Iter 138/139 read-only
// "Draft Order Results" tab (formerly wired to commissioner-side config; the
// config now lives in League Admin → Draft, this surface is display-only).
import { useState, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { CalendarDays, CheckCircle2, Clock } from "lucide-react";
import api from "@/lib/api";
import { cn } from "@/lib/utils";

export const METHOD_META: Record<string, { label: string; description: string }> = {
  nhl_lottery: {
    label: "NHL team draft lottery",
    description:
      "Pick order will mirror the official NHL Draft Lottery — date set by the system administrator.",
  },
  lottery_generator: {
    label: "Draft Lottery Generator",
    description: "League will run its own weighted lottery — commissioner schedules the date.",
  },
  manual_entry: {
    label: "Manual Entry",
    description:
      "Commissioner enters the draft order manually after the regular season — optional date.",
  },
};

export function formatScheduled(iso?: string | null): string {
  if (!iso) return "TBD";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export function DraftOrderStatus({ draftOrder, year }: any) {
  if (!draftOrder) return null;
  const method = draftOrder.method || "manual_entry";
  const meta = METHOD_META[method] || METHOD_META.manual_entry;
  const isSet = !!draftOrder.is_set;
  const scheduled = formatScheduled(draftOrder.scheduled_at);
  return (
    <div
      className={cn(
        "rounded-md border p-3 flex flex-wrap items-center gap-3 text-sm",
        isSet ? "border-emerald-500/40 bg-emerald-500/5" : "border-amber-500/30 bg-amber-500/5",
      )}
      data-testid="draft-order-status-banner"
    >
      {isSet ? (
        <CheckCircle2 className="h-5 w-5 text-emerald-400 shrink-0" />
      ) : (
        <Clock className="h-5 w-5 text-amber-400 shrink-0" />
      )}
      <div className="flex flex-col">
        <span className="font-semibold" data-testid="draft-order-status-headline">
          {year} pick order: {isSet ? "SET" : "Not yet set"}
        </span>
        <span className="text-xs text-muted-foreground" data-testid="draft-order-status-method">
          Format: {meta.label}
          {!isSet && (
            <>
              {" · "}
              <span data-testid="draft-order-status-scheduled">Scheduled: {scheduled}</span>
              {draftOrder.schedule_source === "system" && scheduled !== "TBD" && (
                <span className="ml-1 italic">(set by system admin)</span>
              )}
            </>
          )}
        </span>
      </div>
    </div>
  );
}

export function DraftOrderResultsTab({ leagueId, draftOrder, teams }: any) {
  const orderOK = !!draftOrder?.is_set;
  const method = draftOrder?.method || "manual_entry";
  const meta = METHOD_META[method] || METHOD_META.manual_entry;
  const scheduled = formatScheduled(draftOrder?.scheduled_at);
  const seedById: Record<string, number> = {};
  (draftOrder?.order || []).forEach((o: any) => {
    seedById[String(o.team_id)] = o.seed;
  });
  const orderedTeams = [...(teams || [])].sort((a: any, b: any) => {
    const aSeed = seedById[String(a.id)] ?? 9999;
    const bSeed = seedById[String(b.id)] ?? 9999;
    return aSeed - bSeed;
  });

  // Iter 143 — Expansion draft: show unprotected → protected players per team
  const [expansionBoard, setExpansionBoard] = useState<any[]>([]);
  const [showExpansion, setShowExpansion] = useState(false);
  useEffect(() => {
    if (!leagueId) return;
    api
      .get(`/leagues/${leagueId}/expansion-draft-board`)
      .then(({ data }) => {
        const rows = data?.teams || [];
        const anyPlayers = rows.some((r: any) => (r.unprotected?.length || 0) + (r.protected?.length || 0) > 0);
        setExpansionBoard(rows);
        setShowExpansion(anyPlayers);
      })
      .catch(() => setShowExpansion(false));
  }, [leagueId]);

  return (
    <div className="space-y-6">
      {/* Iter 139 — Read-only summary; configuration lives in League Admin */}
      <Card className="border-border gradient-card" data-testid="draft-order-summary-card">
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2">
            <CalendarDays className="h-4 w-4 text-cyan-300" />
            Draft Order Configuration
            <Badge
              variant="outline"
              className="ml-1 text-[10px] border-border text-muted-foreground"
              data-testid="draft-order-summary-method"
            >
              {meta.label}
            </Badge>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          <div className="text-xs text-muted-foreground">{meta.description}</div>
          <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
            <div data-testid="draft-order-summary-status">
              <span className="text-muted-foreground text-xs uppercase tracking-wider mr-2">Status</span>
              {orderOK ? (
                <Badge variant="outline" className="border-emerald-500/40 text-emerald-300">
                  SET
                </Badge>
              ) : (
                <Badge variant="outline" className="border-amber-500/40 text-amber-300">
                  Not yet set
                </Badge>
              )}
            </div>
            <div data-testid="draft-order-summary-scheduled">
              <span className="text-muted-foreground text-xs uppercase tracking-wider mr-2">Scheduled</span>
              <span className="font-mono">{scheduled}</span>
              {draftOrder?.schedule_source === "system" && scheduled !== "TBD" && (
                <span className="ml-1 text-xs italic text-muted-foreground">(set by system admin)</span>
              )}
            </div>
          </div>
          <div
            className="rounded-md bg-muted/30 border border-border p-2 text-xs text-muted-foreground"
            data-testid="draft-order-admin-hint"
          >
            Format + schedule are configured by the commissioner in{" "}
            <a href="/commissioner/settings" className="text-cyan-300 hover:underline" data-testid="draft-order-admin-link">
              League Administration → Draft
            </a>
            .
          </div>
        </CardContent>
      </Card>

      {/* Results card — ordered list */}
      <Card className="border-border gradient-card" data-testid="draft-order-results-card">
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2">
            Draft Order Results
            {orderOK ? (
              <Badge variant="outline" className="border-emerald-500/40 text-emerald-300 text-[10px]">
                Final
              </Badge>
            ) : (
              <Badge variant="outline" className="border-amber-500/40 text-amber-300 text-[10px]">
                Pre-lottery preview
              </Badge>
            )}
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow className="border-border hover:bg-transparent">
                <TableHead className="w-[80px] text-xs uppercase tracking-wider text-muted-foreground pl-4">
                  Pick
                </TableHead>
                <TableHead className="text-xs uppercase tracking-wider text-muted-foreground">Team</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {orderedTeams.map((t: any, idx: number) => (
                <TableRow key={t.id || t.abbr} className="border-border/50" data-testid={`draft-order-row-${idx + 1}`}>
                  <TableCell className="pl-4 font-mono text-sm">#{seedById[String(t.id)] || idx + 1}</TableCell>
                  <TableCell className="text-sm">
                    {t.name} <span className="text-muted-foreground">({t.abbr})</span>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
      {/* Iter 143 — Expansion draft: unprotected → protected listing */}
      {showExpansion && (
        <Card className="border-border gradient-card" data-testid="expansion-board-card">
          <CardHeader className="pb-3">
            <CardTitle className="text-base">Expansion Draft Board · Available Players</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-xs text-muted-foreground">
              Each team&apos;s unprotected players are listed first (available to be selected), followed by their protected list.
            </p>
            <div className="space-y-3" data-testid="expansion-board-teams">
              {expansionBoard.map((row: any) => (
                <div
                  key={row.team_id}
                  className="rounded-md border border-border p-3 space-y-2"
                  data-testid={`expansion-board-team-${row.team_abbr}`}
                >
                  <div className="flex items-center justify-between">
                    <div className="font-semibold text-sm">
                      {row.team_name} <span className="text-muted-foreground">({row.team_abbr})</span>
                    </div>
                    {row.submitted ? (
                      <Badge variant="outline" className="text-[10px] border-emerald-500/40 text-emerald-300">
                        List submitted
                      </Badge>
                    ) : (
                      <Badge variant="outline" className="text-[10px] border-amber-500/40 text-amber-300">
                        No list yet
                      </Badge>
                    )}
                  </div>
                  <div>
                    <div className="text-[10px] uppercase tracking-wider text-emerald-300 font-semibold mb-1">
                      Unprotected ({row.unprotected?.length || 0})
                    </div>
                    {(row.unprotected || []).length === 0 ? (
                      <div className="text-xs italic text-muted-foreground">— no unprotected players —</div>
                    ) : (
                      <ul className="grid sm:grid-cols-2 gap-1 text-xs" data-testid={`expansion-unprotected-${row.team_abbr}`}>
                        {row.unprotected.map((p: any) => (
                          <li key={p.id} className="flex items-center justify-between gap-2 px-2 py-1 rounded bg-emerald-500/5">
                            <span>
                              {p.name} <span className="text-muted-foreground">({p.position})</span>
                            </span>
                            {p.salary != null && (
                              <span className="font-mono text-muted-foreground">
                                ${(Number(p.salary) / 1_000_000).toFixed(2)}M
                              </span>
                            )}
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                  <div>
                    <div className="text-[10px] uppercase tracking-wider text-amber-300 font-semibold mb-1 mt-2">
                      Protected ({row.protected?.length || 0})
                    </div>
                    {(row.protected || []).length === 0 ? (
                      <div className="text-xs italic text-muted-foreground">— none —</div>
                    ) : (
                      <ul className="grid sm:grid-cols-2 gap-1 text-xs" data-testid={`expansion-protected-${row.team_abbr}`}>
                        {row.protected.map((p: any) => (
                          <li
                            key={p.id}
                            className="flex items-center justify-between gap-2 px-2 py-1 rounded bg-amber-500/5 text-muted-foreground"
                          >
                            <span>
                              {p.name} <span>({p.position})</span>
                            </span>
                            {p.salary != null && (
                              <span className="font-mono">${(Number(p.salary) / 1_000_000).toFixed(2)}M</span>
                            )}
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
