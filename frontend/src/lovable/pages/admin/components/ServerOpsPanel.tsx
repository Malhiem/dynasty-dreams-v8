// @ts-nocheck
/* ServerOpsPanel — extracted from AdminDashboard.tsx during Iter 224 refactor. */
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { SyncStat } from "./_shared";

/* ─── Iter 209 — Server Ops / Error Logs Panel ───────────────────────── */
export function ServerOpsPanel() {
  const [uptime, setUptime] = useState<any>(null);
  const [logs, setLogs] = useState<any>(null);
  const [service, setService] = useState<"backend" | "frontend">("backend");
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [u, l] = await Promise.all([
        api.get("/admin/platform/uptime"),
        api.get(`/admin/platform/server-logs?service=${service}&lines=120`),
      ]);
      setUptime(u.data);
      setLogs(l.data);
    } catch { toast.error("Could not load server data"); }
    finally { setLoading(false); }
  }, [service]);

  useEffect(() => { load(); }, [load]);

  return (
    <section className="space-y-3" data-testid="server-ops-section">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">Server Ops</h2>
          <p className="text-xs text-muted-foreground">
            Uptime, throughput counters, and recent log lines.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Select value={service} onValueChange={(v: any) => setService(v)}>
            <SelectTrigger className="w-32" data-testid="ops-service-select"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="backend">Backend</SelectItem>
              <SelectItem value="frontend">Frontend</SelectItem>
            </SelectContent>
          </Select>
          <Button size="sm" variant="outline" onClick={load} data-testid="ops-refresh-btn">Refresh</Button>
        </div>
      </div>

      {loading && <div className="text-sm text-muted-foreground py-4 text-center">Loading…</div>}

      {!loading && uptime && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3" data-testid="ops-stats-grid">
          <SyncStat label="Logins (24h)" value={uptime.logins_24h} />
          <SyncStat label="Trades (24h)" value={uptime.trades_24h} />
          <SyncStat label="Waiver runs (24h)" value={uptime.waivers_24h} />
          <SyncStat label="Backend log mtime" value={
            <span className="text-xs">{uptime.backend_log_mtime}</span>
          } />
        </div>
      )}

      {!loading && logs && (
        <div className="rounded-lg border border-border bg-black/60 p-3 font-mono text-[11px]" data-testid="ops-log-tail">
          <div className="text-xs text-muted-foreground mb-2">
            {logs.log_file} · {logs.tail_size} lines · {" "}
            <span className={logs.error_count > 0 ? "text-rose-300" : "text-emerald-300"}>
              {logs.error_count} errors
            </span>
          </div>
          <div className="max-h-[400px] overflow-y-auto space-y-0.5">
            {logs.lines.map((row: any, i: number) => (
              <div
                key={i}
                className={row.is_error ? "text-rose-300" : "text-foreground/80"}
                data-testid={row.is_error ? `ops-log-error-${i}` : undefined}
              >
                {row.line || "\u00A0"}
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}


