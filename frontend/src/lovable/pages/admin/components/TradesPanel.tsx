// @ts-nocheck
/* TradesPanel — extracted from AdminDashboard.tsx during Iter 224 refactor. */
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import api from "@/lib/api";
import { AlertTriangle, ArrowLeftRight, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

/* ─── Iter 201b — Trade Review panel ───────────────────────────────── */
export function TradesPanel() {
  const [data, setData] = useState({ entries: [], alert_threshold: 50, total: 0 });
  const [loading, setLoading] = useState(true);
  const [sort, setSort] = useState("fairness_asc");
  const [onlyAlerts, setOnlyAlerts] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const q = new URLSearchParams({ sort_by: sort, limit: "50" });
      if (onlyAlerts) q.set("only_alerts", "true");
      const { data } = await api.get(`/admin/platform/trades-review?${q.toString()}`);
      setData(data);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to load trades");
    } finally { setLoading(false); }
  }, [sort, onlyAlerts]);
  useEffect(() => { load(); }, [load]);

  return (
    <section data-testid="trades-review-section" className="space-y-3">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-2">
          <ArrowLeftRight className="h-4 w-4" />
          Trade Review · fairness ALERT threshold {data.alert_threshold}%
        </h2>
        <div className="flex items-center gap-2">
          <label className="text-xs flex items-center gap-1.5 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={onlyAlerts}
              onChange={(e) => setOnlyAlerts(e.target.checked)}
              data-testid="trades-only-alerts-toggle"
            />
            Only alerts
          </label>
          <Select value={sort} onValueChange={setSort}>
            <SelectTrigger className="h-8 w-[160px] text-xs" data-testid="trades-sort-select">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="fairness_asc">Fairness (low → high)</SelectItem>
              <SelectItem value="fairness_desc">Fairness (high → low)</SelectItem>
              <SelectItem value="created_desc">Newest first</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>
      <div className="rounded-lg border border-border overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-secondary/50 text-xs uppercase tracking-wider text-muted-foreground">
            <tr>
              <th className="text-left px-3 py-2">When</th>
              <th className="text-left px-3 py-2">League</th>
              <th className="text-left px-3 py-2">Trade</th>
              <th className="text-left px-3 py-2">Fairness</th>
              <th className="text-left px-3 py-2">Favored</th>
              <th className="text-left px-3 py-2">Age Δ</th>
              <th className="text-left px-3 py-2">Assets</th>
              <th className="text-right px-3 py-2">Action</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={8} className="text-center text-muted-foreground py-6">Loading…</td></tr>
            ) : data.entries.length === 0 ? (
              <tr><td colSpan={8} className="text-center text-muted-foreground py-6">No trades.</td></tr>
            ) : data.entries.map((e) => (
              <tr key={e.id} className="border-t border-border hover:bg-secondary/20" data-testid={`trade-row-${e.id}`}>
                <td className="px-3 py-2 text-xs text-muted-foreground whitespace-nowrap">{(e.created_at || "").slice(0, 19).replace("T", " ")}</td>
                <td className="px-3 py-2 text-xs">{e.league_name || e.league_id?.slice(0, 8)}</td>
                <td className="px-3 py-2 text-xs">{e.proposer_team_name} ↔ {e.target_team_name}</td>
                <td className="px-3 py-2 text-xs">
                  <span
                    className={`inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 font-mono border ${
                      e.fairness.alert
                        ? "bg-rose-500/15 text-rose-300 border-rose-500/40"
                        : e.fairness.score >= 80
                          ? "bg-emerald-500/15 text-emerald-300 border-emerald-500/40"
                          : "bg-amber-500/15 text-amber-300 border-amber-500/40"
                    }`}
                    data-testid={`trade-fairness-${e.id}`}
                  >
                    {e.fairness.alert && <AlertTriangle className="h-3 w-3" />}
                    {e.fairness.score}%
                  </span>
                </td>
                <td className="px-3 py-2 text-xs capitalize text-muted-foreground">{e.fairness.favored_side}</td>
                <td className="px-3 py-2 text-xs tabular-nums">{e.fairness.age_differential ?? "—"}</td>
                <td className="px-3 py-2 text-xs text-muted-foreground">{e.asset_counts.offered}↔{e.asset_counts.requested}</td>
                <td className="px-3 py-2 text-right">
                  {e.status === "reverted" ? (
                    <span className="text-[10px] uppercase tracking-wider font-semibold text-rose-300" data-testid={`trade-reverted-pill-${e.id}`}>
                      Reverted
                    </span>
                  ) : (
                    <Button
                      size="sm" variant="ghost"
                      className="text-xs h-7"
                      onClick={async () => {
                        if (!confirm(`Revert trade ${e.proposer_team_name} ↔ ${e.target_team_name}?`)) return;
                        try {
                          await api.post(`/admin/platform/trades/${e.id}/revert`);
                          toast.success("Trade reverted");
                          load();
                        } catch (err) {
                          toast.error(err?.response?.data?.detail || "Failed to revert");
                        }
                      }}
                      data-testid={`trade-revert-btn-${e.id}`}
                    >
                      <RotateCcw className="h-3 w-3 mr-1" /> Revert
                    </Button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

