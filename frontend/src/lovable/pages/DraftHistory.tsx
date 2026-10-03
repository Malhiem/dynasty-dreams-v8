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
import { useEffect, useMemo, useState, Fragment } from "react";
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
import { Trophy, CalendarDays, Users as UsersIcon, Hash, ArrowRightLeft, ShieldAlert, ChevronDown, ChevronRight, Medal } from "lucide-react";
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

// Iter 205 — small stat cell used inside the expanded pick row.
function Stat({ label, value, highlight }: { label: string; value: any; highlight?: boolean }) {
  const display =
    value === null || value === undefined || (typeof value === "number" && Number.isNaN(value))
      ? "—"
      : value;
  return (
    <div className="flex flex-col">
      <span className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</span>
      <span className={cn("font-mono", highlight && "text-amber-300 font-semibold")}>
        {display}
      </span>
    </div>
  );
}

export default function DraftHistory() {
  const { league, leagueId } = useActiveLeague();
  const [drafts, setDrafts] = useState<DraftSummary[]>([]);
  const [selectedDraftId, setSelectedDraftId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  // Iter 204 — related trades for the selected completed draft.
  const [relatedTrades, setRelatedTrades] = useState<any[]>([]);
  const [tradesLoading, setTradesLoading] = useState(false);
  // Iter 205 — per-player career stats + medal rankings + expansion state.
  const [playerStats, setPlayerStats] = useState<Record<string, any>>({});
  const [statsMeta, setStatsMeta] = useState<{ is_h2h: boolean; scoring_format: string } | null>(null);
  const [expandedPick, setExpandedPick] = useState<number | null>(null);

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

  // Iter 204 — When a draft is selected, fetch related trades.
  useEffect(() => {
    if (!selectedDraftId) {
      setRelatedTrades([]);
      return;
    }
    let cancelled = false;
    setTradesLoading(true);
    (async () => {
      try {
        const { data } = await api.get(`/drafts/${selectedDraftId}/related-trades`);
        if (!cancelled) setRelatedTrades(data?.related_trades || []);
      } catch {
        if (!cancelled) setRelatedTrades([]);
      } finally {
        if (!cancelled) setTradesLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [selectedDraftId]);

  // Iter 205 — Fetch player stats + medals for the selected draft.
  useEffect(() => {
    setExpandedPick(null);
    if (!selectedDraftId) {
      setPlayerStats({});
      setStatsMeta(null);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const { data } = await api.get(`/drafts/${selectedDraftId}/player-stats`);
        if (cancelled) return;
        const byOverall: Record<string, any> = {};
        (data?.picks || []).forEach((row: any) => {
          byOverall[row.overall] = row;
        });
        setPlayerStats(byOverall);
        setStatsMeta({
          is_h2h: !!data?.is_h2h,
          scoring_format: data?.scoring_format || "head_to_head",
        });
      } catch {
        if (!cancelled) {
          setPlayerStats({});
          setStatsMeta(null);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [selectedDraftId]);

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
                            <TableHead className="w-10"></TableHead>
                            <TableHead className="w-14">Overall</TableHead>
                            <TableHead className="w-16">Round</TableHead>
                            <TableHead className="w-16">Pick</TableHead>
                            <TableHead className="w-16">Team</TableHead>
                            <TableHead>Player</TableHead>
                            <TableHead className="w-44 text-xs text-muted-foreground">Key stats</TableHead>
                            <TableHead className="w-12">Pos</TableHead>
                            <TableHead className="w-16">NHL</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {(selected.picks || []).map((p: any) => {
                            const stat = playerStats[p.overall];
                            const isOpen = expandedPick === p.overall;
                            const cs = stat?.career_stats || {};
                            const isGoalie = !!stat?.is_goalie;
                            const medal = stat?.medal as "gold" | "silver" | "bronze" | null;
                            const medalColor =
                              medal === "gold" ? "text-amber-400" :
                              medal === "silver" ? "text-slate-300" :
                              medal === "bronze" ? "text-orange-400" : null;
                            return (
                              <Fragment key={p.overall}>
                                <TableRow
                                  data-testid={`draft-history-pick-${p.overall}`}
                                  className="cursor-pointer hover:bg-muted/40 transition-colors"
                                  onClick={() => setExpandedPick(isOpen ? null : p.overall)}
                                >
                                  <TableCell className="text-muted-foreground">
                                    {isOpen ? (
                                      <ChevronDown className="h-3.5 w-3.5" />
                                    ) : (
                                      <ChevronRight className="h-3.5 w-3.5" />
                                    )}
                                  </TableCell>
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
                                    <div className="flex items-center gap-2">
                                      {medal && medalColor && (
                                        <Medal
                                          className={`h-4 w-4 ${medalColor}`}
                                          data-testid={`medal-${medal}-${p.overall}`}
                                        />
                                      )}
                                      <span>{p.player?.name || "—"}</span>
                                      {p.auto_picked && (
                                        <Badge
                                          variant="outline"
                                          className="ml-1 text-[10px] border-amber-500/40 text-amber-300"
                                        >
                                          auto
                                        </Badge>
                                      )}
                                    </div>
                                  </TableCell>
                                  {/* Iter 205 — compact inline key stats */}
                                  <TableCell className="text-[10px] text-muted-foreground font-mono">
                                    {!stat && "—"}
                                    {stat && isGoalie && (
                                      <span data-testid={`inline-stats-${p.overall}`}>
                                        GP {cs.games_played || 0} · W {cs.wins || 0}
                                        {" · "}SV%{" "}
                                        {cs.save_pct
                                          ? (Number(cs.save_pct) <= 1
                                              ? (Number(cs.save_pct) * 100).toFixed(1)
                                              : Number(cs.save_pct).toFixed(1))
                                          : "—"}
                                      </span>
                                    )}
                                    {stat && !isGoalie && (
                                      <span data-testid={`inline-stats-${p.overall}`}>
                                        GP {cs.games_played || 0} · {cs.goals || 0}G {cs.assists || 0}A {cs.points || 0}P
                                      </span>
                                    )}
                                  </TableCell>
                                  <TableCell className="text-xs">
                                    {p.player?.position || "—"}
                                  </TableCell>
                                  <TableCell className="text-xs text-muted-foreground">
                                    {p.player?.nhlTeam || "—"}
                                  </TableCell>
                                </TableRow>
                                {isOpen && (
                                  <TableRow
                                    className="bg-muted/20 hover:bg-muted/20"
                                    data-testid={`pick-stats-expand-${p.overall}`}
                                  >
                                    <TableCell colSpan={9} className="py-3 px-6">
                                      {!stat && (
                                        <div className="text-sm text-muted-foreground">
                                          Stats not available for this player.
                                        </div>
                                      )}
                                      {stat && (
                                        <div className="space-y-2">
                                          <div className="text-xs uppercase tracking-wider text-muted-foreground flex items-center gap-2">
                                            Stats to date
                                            {medal && (
                                              <Badge
                                                variant="outline"
                                                className={`text-[10px] ${medalColor || ""} border-current/40`}
                                              >
                                                Top {medal === "gold" ? "1" : medal === "silver" ? "2" : "3"} ·{" "}
                                                {stat.position_group} group
                                              </Badge>
                                            )}
                                          </div>
                                          <div className="grid grid-cols-4 md:grid-cols-8 gap-x-6 gap-y-2 text-sm">
                                            {isGoalie ? (
                                              <>
                                                <Stat label="GP" value={cs.games_played} />
                                                <Stat label="W" value={cs.wins} />
                                                <Stat label="L" value={cs.losses} />
                                                <Stat label="SO" value={cs.shutouts} />
                                                <Stat label="SV%" value={
                                                  Number(cs.save_pct) <= 1
                                                    ? (Number(cs.save_pct) * 100).toFixed(1)
                                                    : Number(cs.save_pct).toFixed(1)
                                                } />
                                                <Stat label="GAA" value={Number(cs.goals_against_avg).toFixed(2)} />
                                                <Stat label="FP" value={stat.fantasy_points} />
                                                {statsMeta?.is_h2h && (
                                                  <Stat label="FP/G" value={stat.fantasy_points_per_game} highlight />
                                                )}
                                              </>
                                            ) : (
                                              <>
                                                <Stat label="GP" value={cs.games_played} />
                                                <Stat label="G" value={cs.goals} />
                                                <Stat label="A" value={cs.assists} />
                                                <Stat label="PTS" value={cs.points} />
                                                <Stat label="+/-" value={cs.plus_minus} />
                                                <Stat label="SOG" value={cs.shots} />
                                                <Stat label="FP" value={stat.fantasy_points} />
                                                {statsMeta?.is_h2h && (
                                                  <Stat label="FP/G" value={stat.fantasy_points_per_game} highlight />
                                                )}
                                              </>
                                            )}
                                          </div>
                                        </div>
                                      )}
                                    </TableCell>
                                  </TableRow>
                                )}
                              </Fragment>
                            );
                          })}
                        </TableBody>
                      </Table>
                    </ScrollArea>
                  </CardContent>
                </>
              )}
            </Card>
            {/* Iter 204 — Related trades for this draft */}
            {selected && (
              <Card data-testid="draft-history-related-trades" className="lg:col-start-2">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <ArrowRightLeft className="h-4 w-4 text-sky-400" />
                    Related Trades
                    <Badge variant="outline" className="ml-2 text-[10px]">
                      {relatedTrades.length}
                    </Badge>
                  </CardTitle>
                  <p className="text-xs text-muted-foreground">
                    Trades that affected players drafted, or any picks
                    proposed during this draft cycle.
                  </p>
                </CardHeader>
                <CardContent>
                  {tradesLoading && (
                    <div className="text-sm text-muted-foreground py-4" data-testid="related-trades-loading">
                      Loading trades…
                    </div>
                  )}
                  {!tradesLoading && relatedTrades.length === 0 && (
                    <div className="text-sm text-muted-foreground py-4" data-testid="related-trades-empty">
                      No trades affected this draft.
                    </div>
                  )}
                  {!tradesLoading && relatedTrades.length > 0 && (
                    <div className="space-y-3" data-testid="related-trades-list">
                      {relatedTrades.map((t: any) => {
                        const isPickTrade = t.relevance === "pick";
                        const statusColor = t.status === "executed"
                          ? "border-emerald-500/40 text-emerald-300"
                          : t.status === "vetoed"
                            ? "border-rose-500/40 text-rose-300"
                            : "border-amber-500/40 text-amber-300";
                        return (
                          <div
                            key={t.trade_id}
                            className="rounded-lg border border-border bg-muted/20 p-3"
                            data-testid={`related-trade-${t.trade_id}`}
                          >
                            <div className="flex items-center justify-between mb-2">
                              <div className="flex items-center gap-2 text-sm font-medium">
                                {isPickTrade ? (
                                  <ShieldAlert className="h-3.5 w-3.5 text-amber-400" />
                                ) : (
                                  <ArrowRightLeft className="h-3.5 w-3.5 text-sky-400" />
                                )}
                                <span>{t.proposer_team_name || "Team A"}</span>
                                <ArrowRightLeft className="h-3 w-3 text-muted-foreground" />
                                <span>{t.receiver_team_name || "Team B"}</span>
                              </div>
                              <div className="flex items-center gap-1.5">
                                <Badge variant="outline" className={cn("text-[10px]", statusColor)}>
                                  {t.status}
                                </Badge>
                                <Badge variant="outline" className="text-[10px]">
                                  {isPickTrade ? "Pick trade" : "Player trade"}
                                </Badge>
                              </div>
                            </div>
                            {t.affected_players?.length > 0 && (
                              <div className="text-xs space-y-0.5 mt-1.5">
                                <div className="text-muted-foreground">Affected drafted players:</div>
                                {t.affected_players.map((p: any) => (
                                  <div
                                    key={p.player_id}
                                    className="ml-2"
                                    data-testid={`affected-player-${p.player_id}`}
                                  >
                                    • <span className="font-medium">{p.name}</span>
                                    <span className="text-muted-foreground">
                                      {" "}— picked #{p.drafted_overall} by {p.drafted_by_team}
                                    </span>
                                  </div>
                                ))}
                              </div>
                            )}
                            {t.affected_picks?.length > 0 && (
                              <div className="text-xs space-y-0.5 mt-1.5">
                                <div className="text-muted-foreground">Affected picks:</div>
                                {t.affected_picks.map((p: any, i: number) => (
                                  <div key={i} className="ml-2">
                                    • Round {p.round || "?"} · {p.year || "?"}
                                  </div>
                                ))}
                              </div>
                            )}
                            {t.executed_at && (
                              <div className="text-[10px] text-muted-foreground mt-2">
                                Executed {new Date(t.executed_at).toLocaleString()}
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  )}
                </CardContent>
              </Card>
            )}
          </div>
        )}
      </div>
    </AppLayout>
  );
}
