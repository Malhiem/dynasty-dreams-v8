/**
 * Rotisserie Standings — full category-rank matrix.
 *
 * Displays each team's accumulated stat, rank, and awarded points for
 * every configured scoring category.  Overall standings sort by total
 * category points, highest first.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { toast } from "sonner";
import { RefreshCw, Trophy, Calculator, ArrowDown, ArrowUp } from "lucide-react";
import api from "@/lib/api";
import { AppLayout } from "@/components/layout/AppLayout";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

/* ── helpers ─────────────────────────────────────────────────────── */

/** Extract the short abbreviation from a label like "Goals (G)" → "G" */
function abbr(label) {
  const m = label?.match(/\(([^)]+)\)/);
  return m ? m[1] : label;
}

/** Full category name without the parenthetical, e.g. "Goals" */
function fullName(label) {
  return (label || "").replace(/\s*\([^)]*\)\s*$/, "").trim();
}

/** Format a stat value — percentages get 3 decimals, others 1 or 0 */
function fmtStat(value, key) {
  const v = Number(value ?? 0);
  if (key === "save_percentage") return v.toFixed(3);
  if (key === "goals_against_avg") return v.toFixed(2);
  return Number.isInteger(v) ? String(v) : v.toFixed(1);
}

/* ── component ───────────────────────────────────────────────────── */

export default function RotoStandingsPage() {
  const { id, leagueId: routeLid } = useParams();
  const leagueId = id || routeLid;

  const [standings, setStandings] = useState(null);
  const [loading, setLoading] = useState(true);
  const [recomputing, setRecomputing] = useState(false);

  /* Fetch season standings (includes categories + ranks + stats) */
  const load = useCallback(async () => {
    if (!leagueId) return;
    setLoading(true);
    try {
      const { data } = await api.get(`/leagues/${leagueId}/roto/standings`);
      setStandings(data);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to load Roto standings");
    } finally {
      setLoading(false);
    }
  }, [leagueId]);

  useEffect(() => { load(); }, [load]);

  /* Commissioner recompute */
  const recompute = async () => {
    setRecomputing(true);
    try {
      const { data } = await api.post(`/leagues/${leagueId}/roto/recompute`, {
        period: null, close: false,
      });
      toast.success(
        `Recomputed · ${data.num_teams} teams · leader: ${data.leader?.team_name || "—"}`,
      );
      await load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Recompute failed");
    } finally {
      setRecomputing(false);
    }
  };

  /* Sort teams by total points DESC */
  const teamsSorted = useMemo(() => {
    if (!standings?.totals) return [];
    return Object.entries(standings.totals)
      .map(([tid, t]) => ({ ...t, team_id: tid }))
      .sort((a, b) => (b.total_points || 0) - (a.total_points || 0));
  }, [standings]);

  const categories = standings?.categories || [];

  return (
    <AppLayout>
      <div className="p-4 md:p-6 space-y-4" data-testid="roto-standings-page">
        {/* ── Header ──────────────────────────────────────────── */}
        <div className="flex items-center gap-2 flex-wrap">
          <Trophy className="h-5 w-5 text-amber-400" />
          <h1 className="text-lg font-bold">Rotisserie Standings</h1>
          <div className="ml-auto flex items-center gap-2">
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

        {/* ── Loading ─────────────────────────────────────────── */}
        {loading && (
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <RefreshCw className="h-3 w-3 animate-spin" /> Loading…
          </div>
        )}

        {/* ── Empty state ─────────────────────────────────────── */}
        {!loading && teamsSorted.length === 0 && (
          <div className="rounded border border-dashed border-muted-foreground/30 p-6 text-center text-sm text-muted-foreground">
            No roto data yet — hit Recompute once players have season stats.
          </div>
        )}

        {/* ── Standings matrix ────────────────────────────────── */}
        {!loading && teamsSorted.length > 0 && categories.length > 0 && (
          <div
            className="rounded border border-border overflow-x-auto"
            data-testid="roto-standings-table"
          >
            <table className="w-full text-xs border-collapse">
              {/* ── Two-row header: group + sub-columns ───────── */}
              <thead className="bg-secondary/40">
                <tr>
                  <th
                    rowSpan={2}
                    className="text-left px-2 py-2 border-b border-border sticky left-0 bg-secondary/40 z-10 min-w-[2rem]"
                  >
                    #
                  </th>
                  <th
                    rowSpan={2}
                    className="text-left px-2 py-2 border-b border-border sticky left-8 bg-secondary/40 z-10 min-w-[8rem]"
                  >
                    Team
                  </th>
                  {categories.map((cat) => (
                    <th
                      key={cat.key}
                      colSpan={3}
                      className="text-center px-1 py-1.5 border-b border-l border-border"
                      data-testid={`roto-cat-header-${cat.key}`}
                    >
                      <span className="flex items-center justify-center gap-1">
                        {abbr(cat.label)}
                        {cat.higher_is_better === false
                          ? <ArrowDown className="h-2.5 w-2.5 text-amber-400/80" />
                          : <ArrowUp className="h-2.5 w-2.5 text-emerald-400/80" />}
                      </span>
                    </th>
                  ))}
                  <th
                    rowSpan={2}
                    className="text-right px-2 py-2 border-b border-l border-border min-w-[3.5rem]"
                  >
                    Total
                  </th>
                </tr>
                <tr>
                  {categories.map((cat) => (
                    <SubHeaders key={cat.key} catKey={cat.key} label={cat.label} />
                  ))}
                </tr>
              </thead>

              {/* ── Body ───────────────────────────────────────── */}
              <tbody className="divide-y divide-border/40">
                {teamsSorted.map((team, idx) => {
                  const overallRank = idx + 1;
                  return (
                    <tr
                      key={team.team_id}
                      data-testid={`roto-standings-row-${team.team_id}`}
                      className={overallRank === 1 ? "bg-amber-500/5" : ""}
                    >
                      <td className="px-2 py-1.5 sticky left-0 bg-card z-[5] border-r border-border/30">
                        {overallRank === 1 ? (
                          <Badge variant="outline" className="text-amber-400 border-amber-400/60 text-[10px]">
                            1
                          </Badge>
                        ) : (
                          overallRank
                        )}
                      </td>
                      <td className="px-2 py-1.5 font-medium whitespace-nowrap sticky left-8 bg-card z-[5] border-r border-border/30">
                        {team.team_name}
                      </td>
                      {categories.map((cat) => (
                        <CategoryCells
                          key={cat.key}
                          cat={cat}
                          teamId={team.team_id}
                        />
                      ))}
                      <td
                        className="px-2 py-1.5 text-right tabular-nums font-semibold border-l border-border/30"
                        data-testid={`roto-total-${team.team_id}`}
                      >
                        {(team.total_points ?? 0).toFixed(1)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {/* ── Metadata footer ─────────────────────────────────── */}
        {!loading && standings && (
          <div className="text-[10px] text-muted-foreground flex gap-3 flex-wrap">
            <span>{standings.num_teams} teams</span>
            <span>Tiebreak: {standings.tiebreak || "split"}</span>
            {standings.aggregated && (
              <span>{standings.periods_closed} closed period(s)</span>
            )}
          </div>
        )}
      </div>
    </AppLayout>
  );
}

/* ── Sub-header cells for a single category (Stat · Rank · Pts) ── */
function SubHeaders({ catKey, label }) {
  const name = fullName(label);
  return (
    <>
      <th
        className="text-right px-1 py-1 text-[10px] text-muted-foreground font-normal border-l border-border"
        aria-label={`${name} Stat`}
      >
        Stat
      </th>
      <th
        className="text-right px-1 py-1 text-[10px] text-muted-foreground font-normal"
        aria-label={`${name} Rank`}
        data-testid={`roto-col-${catKey}-rank`}
      >
        Rank
      </th>
      <th
        className="text-right px-1 py-1 text-[10px] text-muted-foreground font-normal"
        aria-label={`${name} Points`}
      >
        Pts
      </th>
    </>
  );
}

/* ── Three data cells for one team × one category ─────────────── */
function CategoryCells({ cat, teamId }) {
  const stat = cat.team_stats?.[teamId] ?? 0;
  const rank = cat.ranks?.[teamId] ?? "—";
  const pts = cat.points?.[teamId] ?? 0;

  return (
    <>
      <td
        className="px-1 py-1.5 text-right tabular-nums border-l border-border/30"
        data-testid={`roto-stat-${cat.key}-${teamId}`}
      >
        {fmtStat(stat, cat.key)}
      </td>
      <td
        className="px-1 py-1.5 text-right tabular-nums text-muted-foreground"
        data-testid={`roto-rank-${cat.key}-${teamId}`}
        aria-label={`${fullName(cat.label)} Rank`}
      >
        {rank}
      </td>
      <td
        className="px-1 py-1.5 text-right tabular-nums font-medium"
        data-testid={`roto-pts-${cat.key}-${teamId}`}
      >
        {Number(pts).toFixed(1)}
      </td>
    </>
  );
}
