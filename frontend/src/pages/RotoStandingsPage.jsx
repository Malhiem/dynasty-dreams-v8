/**
 * Iter 232N.86 — Rotisserie standings + live matchup view.
 * URL: /leagues/{id}/roto  (or use as a tab).
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { toast } from "sonner";
import { RefreshCw, Trophy, Calculator } from "lucide-react";
import api from "@/lib/api";
import { AppLayout } from "@/components/layout/AppLayout";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

export default function RotoStandingsPage() {
  const { id, leagueId: routeLid } = useParams();
  const leagueId = id || routeLid;
  const [standings, setStandings] = useState(null);
  const [matchup, setMatchup] = useState(null);
  const [period, setPeriod] = useState("");
  const [loading, setLoading] = useState(true);
  const [recomputing, setRecomputing] = useState(false);

  const load = useCallback(async () => {
    if (!leagueId) return;
    setLoading(true);
    try {
      const [sRes, mRes] = await Promise.all([
        api.get(`/leagues/${leagueId}/roto/standings`),
        api.get(`/leagues/${leagueId}/roto/matchup`, {
          params: period ? { period: Number(period) } : {},
        }),
      ]);
      setStandings(sRes.data);
      setMatchup(mRes.data);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to load Roto data");
    } finally {
      setLoading(false);
    }
  }, [leagueId, period]);

  useEffect(() => { load(); }, [load]);

  const recompute = async () => {
    setRecomputing(true);
    try {
      const p = period ? Number(period) : null;
      const { data } = await api.post(`/leagues/${leagueId}/roto/recompute`, {
        period: p, close: false,
      });
      toast.success(`Recomputed · ${data.num_teams} teams · leader: ${data.leader?.team_name || "—"}`);
      await load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Recompute failed");
    } finally {
      setRecomputing(false);
    }
  };

  const teamsSorted = useMemo(() => {
    if (!standings?.totals) return [];
    return Object.entries(standings.totals)
      .map(([tid, t]) => ({ ...t, team_id: tid }))
      .sort((a, b) => (b.total_points || 0) - (a.total_points || 0));
  }, [standings]);

  return (
    <AppLayout>
      <div className="p-4 md:p-6 space-y-4" data-testid="roto-standings-page">
        <div className="flex items-center gap-2 flex-wrap">
          <Trophy className="h-5 w-5 text-emerald-300" />
          <h1 className="text-lg font-bold">Rotisserie Standings</h1>
          <div className="ml-auto flex items-center gap-2">
            <input
              type="number"
              min={0} max={52}
              placeholder="Period"
              value={period}
              onChange={(e) => setPeriod(e.target.value)}
              className="h-8 w-20 text-xs rounded border border-border bg-background px-2"
              data-testid="roto-period-input"
            />
            <Button
              size="sm"
              variant="outline"
              onClick={recompute}
              disabled={recomputing}
              data-testid="roto-recompute-btn"
            >
              {recomputing
                ? <RefreshCw className="h-3.5 w-3.5 mr-1 animate-spin" />
                : <Calculator className="h-3.5 w-3.5 mr-1" />}
              Recompute
            </Button>
          </div>
        </div>

        {loading && (
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <RefreshCw className="h-3 w-3 animate-spin" /> Loading…
          </div>
        )}

        {!loading && teamsSorted.length === 0 && (
          <div className="rounded border border-dashed border-muted-foreground/30 p-6 text-center text-sm text-muted-foreground">
            No roto data yet — hit Recompute once players have season stats.
          </div>
        )}

        {!loading && teamsSorted.length > 0 && (
          <>
            <div
              className="rounded border border-border overflow-x-auto"
              data-testid="roto-standings-table"
            >
              <table className="w-full text-xs">
                <thead className="bg-secondary/40">
                  <tr>
                    <th className="text-left px-2 py-2">Rank</th>
                    <th className="text-left px-2 py-2">Team</th>
                    <th className="text-right px-2 py-2">Total Points</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/50">
                  {teamsSorted.map((t, idx) => (
                    <tr key={t.team_id} data-testid={`roto-standings-row-${t.team_id}`}>
                      <td className="px-2 py-1.5">
                        {idx === 0
                          ? <Badge variant="outline" className="text-amber-300 border-amber-400/60">1</Badge>
                          : idx + 1}
                      </td>
                      <td className="px-2 py-1.5 font-medium">{t.team_name}</td>
                      <td className="px-2 py-1.5 text-right tabular-nums font-semibold">
                        {(t.total_points ?? 0).toFixed(1)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {matchup?.categories?.length > 0 && (
              <div
                className="rounded border border-border overflow-x-auto"
                data-testid="roto-matchup-table"
              >
                <div className="px-3 py-2 border-b border-border text-[11px] uppercase tracking-wide text-muted-foreground">
                  {period ? `Live · Period ${period}` : "Live · Full season"} — category leaders
                </div>
                <table className="w-full text-xs">
                  <thead className="bg-secondary/30">
                    <tr>
                      <th className="text-left px-2 py-2">Category</th>
                      {teamsSorted.map((t) => (
                        <th key={t.team_id} className="text-right px-2 py-2 text-[10px]">
                          {t.team_name}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border/50">
                    {matchup.categories.map((cat) => (
                      <tr key={cat.key} data-testid={`roto-matchup-cat-${cat.key}`}>
                        <td className="px-2 py-1.5 font-medium">
                          {cat.label}
                          {cat.higher_is_better === false && (
                            <span className="ml-1 text-[9px] uppercase text-amber-300/70">↓</span>
                          )}
                        </td>
                        {teamsSorted.map((t) => {
                          const stat = cat.team_stats?.[t.team_id] ?? 0;
                          const pts = cat.points?.[t.team_id] ?? 0;
                          return (
                            <td key={t.team_id} className="px-2 py-1.5 text-right tabular-nums">
                              {Number(stat).toFixed(1)}
                              <span className="text-[9px] text-muted-foreground ml-1">
                                ({Number(pts).toFixed(1)})
                              </span>
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
      </div>
    </AppLayout>
  );
}
