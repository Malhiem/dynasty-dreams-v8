// @ts-nocheck
/* SupportMetricsPanel — extracted from AdminDashboard.tsx during Iter 224 refactor. */
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import api from "@/lib/api";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { SyncStat } from "./_shared";

/* ─── Iter 209 — Support Metrics Panel ───────────────────────────────── */
export function SupportMetricsPanel() {
  const [data, setData] = useState<any>(null);
  const [days, setDays] = useState(30);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get(`/admin/platform/support-metrics?days=${days}`);
      setData(data);
    } catch { toast.error("Could not load support metrics"); }
    finally { setLoading(false); }
  }, [days]);

  useEffect(() => { load(); }, [load]);

  return (
    <section className="space-y-3" data-testid="support-metrics-section">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">Support Tickets</h2>
          <p className="text-xs text-muted-foreground">
            Volume, response time, top categories over the last {days} days.
          </p>
        </div>
        <Select value={String(days)} onValueChange={(v: any) => setDays(Number(v))}>
          <SelectTrigger className="w-32" data-testid="support-days-select"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="7">Last 7 days</SelectItem>
            <SelectItem value="30">Last 30 days</SelectItem>
            <SelectItem value="90">Last 90 days</SelectItem>
            <SelectItem value="365">Last year</SelectItem>
          </SelectContent>
        </Select>
      </div>
      {loading && <div className="text-sm text-muted-foreground py-4 text-center">Loading…</div>}
      {!loading && data && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
            <SyncStat label="Total" value={data.total_reports} />
            <SyncStat label="Open" value={
              <span className="text-amber-300">{data.open}</span>
            } />
            <SyncStat label="Resolved" value={
              <span className="text-emerald-300">{data.resolved}</span>
            } />
            <SyncStat label="Dismissed" value={data.dismissed} />
            <SyncStat label="Avg response (hrs)" value={data.avg_response_hours ?? "—"} />
          </div>
          {data.by_category?.length > 0 && (
            <div className="rounded-lg border border-border bg-muted/20 p-3" data-testid="support-categories">
              <div className="text-sm font-semibold mb-2">By Category</div>
              <div className="space-y-1.5">
                {data.by_category.map((c: any) => {
                  const pct = data.total_reports > 0 ? (c.count / data.total_reports) * 100 : 0;
                  return (
                    <div key={c.category}>
                      <div className="flex items-center justify-between text-xs mb-0.5">
                        <span className="capitalize">{c.category.replace(/_/g, " ")}</span>
                        <span className="text-muted-foreground">{c.count} · {pct.toFixed(0)}%</span>
                      </div>
                      <div className="h-1.5 bg-secondary/30 rounded">
                        <div className="h-full bg-sky-500/60 rounded" style={{ width: `${pct}%` }} />
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </>
      )}
    </section>
  );
}


