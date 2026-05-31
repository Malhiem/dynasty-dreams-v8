// @ts-nocheck
/**
 * Iter 118 — Site admin Operations Console.
 *
 * Consumes `GET /api/admin/health-deep` (site-admin gated) and renders:
 *   • Service summary (uptime, total requests, error rate)
 *   • Database health pill (alive + ping ms)
 *   • Worker liveness pills (live_scoring / ownership_snapshot / tbd_deadline)
 *   • Per-route table sortable by count / avg / p95 / error rate, with
 *     traffic-light status icons next to slow / error-prone rows.
 *
 * Auto-refreshes every 15 s (configurable). Pause toggle stops the timer
 * for when the admin is investigating a specific row and doesn't want the
 * table re-sorting under them.
 */
import { useEffect, useMemo, useState, useRef } from "react";
import {
  Activity, Database, Server, Pause, Play, RefreshCw, AlertTriangle,
  CheckCircle2, XCircle, ChevronUp, ChevronDown,
} from "lucide-react";
import api from "@/lib/api";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

const REFRESH_MS = 15000;

// Latency / error thresholds for the traffic-light column. Tuned for our
// median request profile (most reads should be < 200 ms). Tweak here once
// the alerts feature lands.
const WARN_P95 = 500;
const BAD_P95 = 1500;
const WARN_ERR_PCT = 1.0;
const BAD_ERR_PCT = 5.0;

function fmtUptime(seconds) {
  if (!seconds && seconds !== 0) return "—";
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (d > 0) return `${d}d ${h}h`;
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${Math.floor(seconds % 60)}s`;
  return `${Math.floor(seconds)}s`;
}

function StatusDot({ p95, errPct }) {
  let level = "ok";
  if (p95 > BAD_P95 || errPct > BAD_ERR_PCT) level = "bad";
  else if (p95 > WARN_P95 || errPct > WARN_ERR_PCT) level = "warn";

  const Cls = level === "bad" ? "text-rose-400" : level === "warn" ? "text-amber-400" : "text-emerald-400";
  const Icon = level === "bad" ? XCircle : level === "warn" ? AlertTriangle : CheckCircle2;
  return <Icon className={`h-4 w-4 ${Cls}`} aria-label={level} />;
}

function Pill({ ok, label, sub, icon: Icon }) {
  const cls = ok
    ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-300"
    : "border-rose-500/40 bg-rose-500/10 text-rose-300";
  return (
    <div className={`flex items-center gap-2 rounded-md border px-3 py-2 ${cls}`} data-testid={`ops-pill-${label.toLowerCase().replace(/\s+/g, "-")}`}>
      <Icon className="h-4 w-4" />
      <div className="leading-tight">
        <div className="text-xs font-semibold">{label}</div>
        {sub && <div className="text-[10px] opacity-80">{sub}</div>}
      </div>
    </div>
  );
}

export default function OperationsConsole() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [paused, setPaused] = useState(false);
  const [sortKey, setSortKey] = useState("p95_latency_ms");
  const [sortDir, setSortDir] = useState("desc");
  const timerRef = useRef(null);

  const fetchOnce = async () => {
    try {
      const { data } = await api.get("/admin/health-deep?top=50");
      setData(data);
      setError(null);
    } catch (e) {
      setError(e?.response?.data?.detail || e.message || "failed");
      setData(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchOnce();
    if (paused) return;
    timerRef.current = setInterval(fetchOnce, REFRESH_MS);
    return () => timerRef.current && clearInterval(timerRef.current);
  }, [paused]);

  const sortedRoutes = useMemo(() => {
    if (!data?.routes) return [];
    const arr = [...data.routes];
    arr.sort((a, b) => {
      const av = a[sortKey];
      const bv = b[sortKey];
      if (av === bv) return 0;
      const cmp = av < bv ? -1 : 1;
      return sortDir === "asc" ? cmp : -cmp;
    });
    return arr;
  }, [data, sortKey, sortDir]);

  const toggleSort = (k) => {
    if (sortKey === k) setSortDir(sortDir === "asc" ? "desc" : "asc");
    else { setSortKey(k); setSortDir("desc"); }
  };

  const SortHeader = ({ k, children, right }) => (
    <TableHead
      onClick={() => toggleSort(k)}
      className={`cursor-pointer select-none ${right ? "text-right" : ""}`}
      data-testid={`ops-sort-${k}`}
    >
      <span className="inline-flex items-center gap-1">
        {children}
        {sortKey === k && (sortDir === "asc" ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />)}
      </span>
    </TableHead>
  );

  if (error) {
    return (
      <Card className="bg-card border-rose-500/40" data-testid="ops-console-error">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-rose-400">
            <XCircle className="h-4 w-4" /> Operations Console
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            Couldn't reach health-deep ({error}). Are you logged in as the site admin
            (<code className="text-xs">ADMIN_EMAIL</code>)?
          </p>
        </CardContent>
      </Card>
    );
  }

  if (loading || !data) {
    return (
      <Card className="bg-card border-border">
        <CardContent className="py-6 text-sm text-muted-foreground italic">Loading operations data…</CardContent>
      </Card>
    );
  }

  return (
    <Card className="bg-card border-border" data-testid="ops-console-card">
      <CardHeader>
        <div className="flex items-start justify-between gap-3 flex-wrap">
          <div>
            <CardTitle className="flex items-center gap-2">
              <Activity className="h-4 w-4 text-cyan-400" />
              Operations Console
              {data.ok ? (
                <Badge className="bg-emerald-500/10 text-emerald-300 border-emerald-500/40 border" data-testid="ops-overall-ok">All systems normal</Badge>
              ) : (
                <Badge className="bg-rose-500/10 text-rose-300 border-rose-500/40 border" data-testid="ops-overall-bad">Degraded</Badge>
              )}
            </CardTitle>
            <CardDescription>
              Live per-route latency, error rates, and worker liveness.
              Auto-refreshes every {REFRESH_MS / 1000}s.
            </CardDescription>
          </div>
          <div className="flex items-center gap-2">
            <Button size="sm" variant="outline" onClick={fetchOnce} className="gap-1" data-testid="ops-refresh-now">
              <RefreshCw className="h-3 w-3" /> Refresh
            </Button>
            <Button size="sm" variant={paused ? "default" : "outline"} onClick={() => setPaused((p) => !p)} className="gap-1" data-testid="ops-toggle-pause">
              {paused ? <><Play className="h-3 w-3" /> Resume</> : <><Pause className="h-3 w-3" /> Pause</>}
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-5">
        {/* Service summary tiles */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <SummaryTile label="Uptime" value={fmtUptime(data.service.uptime_seconds)} testId="ops-uptime" />
          <SummaryTile label="Total requests" value={data.service.total_requests.toLocaleString()} testId="ops-total-requests" />
          <SummaryTile label="Errors (5xx)" value={data.service.total_errors.toLocaleString()} testId="ops-total-errors" />
          <SummaryTile
            label="Error rate"
            value={`${data.service.error_rate_pct.toFixed(2)}%`}
            tone={data.service.error_rate_pct >= BAD_ERR_PCT ? "bad" : data.service.error_rate_pct >= WARN_ERR_PCT ? "warn" : "ok"}
            testId="ops-error-rate"
          />
        </div>

        {/* DB + worker pills */}
        <div className="flex flex-wrap gap-3">
          <Pill
            ok={data.database.alive}
            label="MongoDB"
            sub={data.database.alive ? `ping ${data.database.ping_ms?.toFixed(1) ?? "—"} ms` : data.database.error}
            icon={Database}
          />
          <Pill ok={data.workers.live_scoring} label="Live scoring" sub={data.workers.live_scoring ? "running" : "stopped"} icon={Server} />
          <Pill ok={data.workers.ownership_snapshot} label="Ownership snapshot" sub={data.workers.ownership_snapshot ? "running" : "stopped"} icon={Server} />
          <Pill ok={data.workers.tbd_deadline} label="TBD deadline" sub={data.workers.tbd_deadline ? "running" : "stopped"} icon={Server} />
        </div>

        {/* Per-route table */}
        <div className="rounded-md border border-border overflow-x-auto">
          <Table data-testid="ops-route-table">
            <TableHeader>
              <TableRow>
                <TableHead className="w-8"></TableHead>
                <SortHeader k="method">Method</SortHeader>
                <SortHeader k="route">Route</SortHeader>
                <SortHeader k="count" right>Count</SortHeader>
                <SortHeader k="error_count" right>5xx</SortHeader>
                <SortHeader k="status_4xx_count" right>4xx</SortHeader>
                <SortHeader k="error_rate_pct" right>Err %</SortHeader>
                <SortHeader k="avg_latency_ms" right>Avg</SortHeader>
                <SortHeader k="p50_latency_ms" right>p50</SortHeader>
                <SortHeader k="p95_latency_ms" right>p95</SortHeader>
                <SortHeader k="max_latency_ms" right>Max</SortHeader>
              </TableRow>
            </TableHeader>
            <TableBody>
              {sortedRoutes.length === 0 && (
                <TableRow><TableCell colSpan={11} className="text-center text-muted-foreground italic py-4">No traffic recorded yet.</TableCell></TableRow>
              )}
              {sortedRoutes.map((r) => (
                <TableRow key={`${r.method} ${r.route}`} data-testid={`ops-route-row`}>
                  <TableCell><StatusDot p95={r.p95_latency_ms} errPct={r.error_rate_pct} /></TableCell>
                  <TableCell className="font-mono text-xs">{r.method}</TableCell>
                  <TableCell className="font-mono text-xs truncate max-w-[420px]">{r.route}</TableCell>
                  <TableCell className="text-right text-xs">{r.count}</TableCell>
                  <TableCell className={`text-right text-xs ${r.error_count > 0 ? "text-rose-400 font-semibold" : ""}`}>{r.error_count}</TableCell>
                  <TableCell className="text-right text-xs">{r.status_4xx_count}</TableCell>
                  <TableCell className="text-right text-xs">{r.error_rate_pct.toFixed(2)}</TableCell>
                  <TableCell className="text-right text-xs">{r.avg_latency_ms.toFixed(0)}</TableCell>
                  <TableCell className="text-right text-xs">{r.p50_latency_ms.toFixed(0)}</TableCell>
                  <TableCell className={`text-right text-xs ${r.p95_latency_ms > BAD_P95 ? "text-rose-400 font-semibold" : r.p95_latency_ms > WARN_P95 ? "text-amber-400" : ""}`}>{r.p95_latency_ms.toFixed(0)}</TableCell>
                  <TableCell className="text-right text-xs">{r.max_latency_ms.toFixed(0)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>

        <p className="text-[10px] text-muted-foreground">
          Latencies in ms. Status icon: green ≤ {WARN_P95} ms p95 & ≤ {WARN_ERR_PCT}% errors · amber up to {BAD_P95} ms / {BAD_ERR_PCT}% · red beyond.
        </p>
      </CardContent>
    </Card>
  );
}

function SummaryTile({ label, value, tone = "ok", testId }) {
  const cls = tone === "bad" ? "border-rose-500/40" : tone === "warn" ? "border-amber-500/40" : "border-border";
  return (
    <div className={`rounded-md border bg-secondary/30 px-3 py-2 ${cls}`} data-testid={testId}>
      <div className="text-[10px] text-muted-foreground uppercase tracking-wide">{label}</div>
      <div className="text-lg font-bold text-foreground">{value}</div>
    </div>
  );
}
