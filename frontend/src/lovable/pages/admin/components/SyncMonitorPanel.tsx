// @ts-nocheck
/**
 * SyncMonitorPanel — Iter 209 NHL stats-feed health monitor.
 * Extracted from AdminDashboard.tsx during Iter 223 refactor.
 */
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { SyncStat } from "./_shared";

export function SyncMonitorPanel() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/admin/platform/sync-status");
      setData(data);
    } catch { toast.error("Could not load sync status"); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  return (
    <section className="space-y-3" data-testid="sync-monitor-section">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">Sync / Data Status</h2>
          <p className="text-xs text-muted-foreground">
            NHL stats feed health — critical for live scoring during games.
          </p>
        </div>
        <Button size="sm" variant="outline" onClick={load} data-testid="sync-refresh-btn">
          Refresh
        </Button>
      </div>
      {loading && <div className="text-sm text-muted-foreground py-4 text-center">Loading…</div>}
      {!loading && data && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3" data-testid="sync-stats-grid">
          <SyncStat label="Status" value={
            <span className={data.healthy ? "text-emerald-300" : "text-rose-300"}>
              {data.healthy ? "Healthy" : "Degraded"}
            </span>
          } />
          <SyncStat label="Players Total" value={data.players_total} />
          <SyncStat label="With NHL ID" value={data.players_with_nhl_id} />
          <SyncStat label="Stale (24h)" value={
            <span className={data.players_stale_24h > 100 ? "text-amber-300" : "text-foreground"}>
              {data.players_stale_24h}
            </span>
          } />
          <SyncStat label="Cache Size" value={data.career_cache_size} />
          <SyncStat label="Last Sync" value={
            <span className="text-xs">{data.last_sync_at || "Never"}</span>
          } />
        </div>
      )}
      {!loading && data?.recent_errors?.length > 0 && (
        <div className="rounded-lg border border-rose-500/40 bg-muted/20 p-3" data-testid="sync-errors">
          <div className="text-sm font-semibold mb-2 text-rose-300">Recent sync errors</div>
          <div className="space-y-1">
            {data.recent_errors.map((e: any, i: number) => (
              <div key={i} className="text-xs">
                <span className="text-muted-foreground">{e.ts}</span> · <span className="font-mono">{e.source}</span>: {e.message}
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}
