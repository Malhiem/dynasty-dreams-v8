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
  CheckCircle2, XCircle, ChevronUp, ChevronDown, Settings,
} from "lucide-react";
import api from "@/lib/api";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";

const REFRESH_MS = 15000;

// Latency / error thresholds for the traffic-light column. Tuned for our
// median request profile (most reads should be < 200 ms). Defaults; the
// admin can override per-deployment via the Ops Console's "Thresholds"
// dialog — overrides persist in localStorage (key: dd-ops-thresholds).
const DEFAULT_WARN_P95 = 500;
const DEFAULT_BAD_P95 = 1500;
const DEFAULT_WARN_ERR_PCT = 1.0;
const DEFAULT_BAD_BAD_PCT = 5.0;
const THRESHOLDS_LS_KEY = "dd-ops-thresholds";

function defaultThresholds() {
  return {
    warn_p95: DEFAULT_WARN_P95,
    bad_p95: DEFAULT_BAD_P95,
    warn_err_pct: DEFAULT_WARN_ERR_PCT,
    bad_err_pct: DEFAULT_BAD_BAD_PCT,
  };
}

/**
 * Count the routes currently breaching the configured thresholds. Used by
 * the alert banner shown atop the console — admins know at a glance how
 * many endpoints need attention without scanning the table.
 */
function countBreaches(routes, thresholds) {
  let bad = 0;
  let warn = 0;
  (routes || []).forEach((r) => {
    if (r.p95_latency_ms > thresholds.bad_p95 || r.error_rate_pct > thresholds.bad_err_pct) bad++;
    else if (r.p95_latency_ms > thresholds.warn_p95 || r.error_rate_pct > thresholds.warn_err_pct) warn++;
  });
  return { bad, warn };
}

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

function StatusDot({ p95, errPct, thresholds }) {
  let level = "ok";
  if (p95 > thresholds.bad_p95 || errPct > thresholds.bad_err_pct) level = "bad";
  else if (p95 > thresholds.warn_p95 || errPct > thresholds.warn_err_pct) level = "warn";

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
  // Iter 122 — admin-configurable thresholds, persisted in localStorage so
  // each operator can tune for their deployment without round-tripping
  // through the API.
  const [thresholds, setThresholds] = useState(() => {
    try {
      const raw = typeof window !== "undefined" && window.localStorage.getItem(THRESHOLDS_LS_KEY);
      if (raw) return { ...defaultThresholds(), ...JSON.parse(raw) };
    } catch (e) { /* ignore */ }
    return defaultThresholds();
  });
  const [showSettings, setShowSettings] = useState(false);
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

  useEffect(() => {
    try { window.localStorage.setItem(THRESHOLDS_LS_KEY, JSON.stringify(thresholds)); } catch (e) { /* ignore */ }
  }, [thresholds]);

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
            <Button size="sm" variant="outline" onClick={() => setShowSettings(true)} className="gap-1" data-testid="ops-open-thresholds">
              <Settings className="h-3 w-3" /> Thresholds
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
            tone={data.service.error_rate_pct >= thresholds.bad_err_pct ? "bad" : data.service.error_rate_pct >= thresholds.warn_err_pct ? "warn" : "ok"}
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

        {/* Iter 122 — Threshold-driven alert banner. Shows the user
            exactly how many endpoints are breaching their configured
            limits before they scan the table. */}
        {(() => {
          const { bad, warn } = countBreaches(sortedRoutes, thresholds);
          if (bad === 0 && warn === 0) return null;
          return (
            <div
              className={`rounded-md border p-3 text-sm flex items-center gap-3 ${
                bad > 0
                  ? "border-rose-500/40 bg-rose-500/10 text-rose-300"
                  : "border-amber-500/40 bg-amber-500/10 text-amber-300"
              }`}
              data-testid="ops-threshold-banner"
            >
              {bad > 0 ? <XCircle className="h-4 w-4" /> : <AlertTriangle className="h-4 w-4" />}
              <span className="font-semibold">
                {bad > 0
                  ? `${bad} route${bad === 1 ? "" : "s"} above critical threshold`
                  : `${warn} route${warn === 1 ? "" : "s"} above warning threshold`}
                {bad > 0 && warn > 0 ? ` (+ ${warn} on watch)` : ""}
              </span>
              <span className="text-xs opacity-80">
                Critical: p95 &gt; {thresholds.bad_p95}ms or errors &gt; {thresholds.bad_err_pct}%.
              </span>
            </div>
          );
        })()}

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
                  <TableCell><StatusDot p95={r.p95_latency_ms} errPct={r.error_rate_pct} thresholds={thresholds} /></TableCell>
                  <TableCell className="font-mono text-xs">{r.method}</TableCell>
                  <TableCell className="font-mono text-xs truncate max-w-[420px]">{r.route}</TableCell>
                  <TableCell className="text-right text-xs">{r.count}</TableCell>
                  <TableCell className={`text-right text-xs ${r.error_count > 0 ? "text-rose-400 font-semibold" : ""}`}>{r.error_count}</TableCell>
                  <TableCell className="text-right text-xs">{r.status_4xx_count}</TableCell>
                  <TableCell className="text-right text-xs">{r.error_rate_pct.toFixed(2)}</TableCell>
                  <TableCell className="text-right text-xs">{r.avg_latency_ms.toFixed(0)}</TableCell>
                  <TableCell className="text-right text-xs">{r.p50_latency_ms.toFixed(0)}</TableCell>
                  <TableCell className={`text-right text-xs ${r.p95_latency_ms > thresholds.bad_p95 ? "text-rose-400 font-semibold" : r.p95_latency_ms > thresholds.warn_p95 ? "text-amber-400" : ""}`}>{r.p95_latency_ms.toFixed(0)}</TableCell>
                  <TableCell className="text-right text-xs">{r.max_latency_ms.toFixed(0)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>

        <p className="text-[10px] text-muted-foreground">
          Latencies in ms. Status icon: green ≤ {thresholds.warn_p95} ms p95 & ≤ {thresholds.warn_err_pct}% errors · amber up to {thresholds.bad_p95} ms / {thresholds.bad_err_pct}% · red beyond.
        </p>
      </CardContent>

      {/* Iter 122 — Threshold settings dialog */}
      <ThresholdsDialog open={showSettings} onOpenChange={setShowSettings} thresholds={thresholds} onSave={setThresholds} />
    </Card>
  );
}

function ThresholdsDialog({ open, onOpenChange, thresholds, onSave }) {
  const [draft, setDraft] = useState(thresholds);
  useEffect(() => { if (open) setDraft(thresholds); }, [open, thresholds]);
  const upd = (k) => (v) => setDraft((d) => ({ ...d, [k]: v }));
  const reset = () => setDraft(defaultThresholds());
  const submit = () => { onSave(draft); onOpenChange(false); };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="bg-popover border-border z-50" data-testid="ops-thresholds-dialog">
        <DialogHeader>
          <DialogTitle>Operations Alert Thresholds</DialogTitle>
          <DialogDescription>
            Tune the warning + critical levels for p95 latency and 5xx error
            rate. Stored locally per admin — doesn't change anyone else's view.
          </DialogDescription>
        </DialogHeader>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 py-2">
          <div className="space-y-2">
            <Label className="text-xs">Warn p95 (ms)</Label>
            <Input
              type="number" min={0} max={10000}
              value={draft.warn_p95}
              onChange={(e) => upd("warn_p95")(Number(e.target.value) || 0)}
              data-testid="ops-threshold-warn-p95"
            />
          </div>
          <div className="space-y-2">
            <Label className="text-xs">Critical p95 (ms)</Label>
            <Input
              type="number" min={0} max={30000}
              value={draft.bad_p95}
              onChange={(e) => upd("bad_p95")(Number(e.target.value) || 0)}
              data-testid="ops-threshold-bad-p95"
            />
          </div>
          <div className="space-y-2">
            <Label className="text-xs">Warn error rate (%)</Label>
            <Input
              type="number" min={0} max={100} step={0.1}
              value={draft.warn_err_pct}
              onChange={(e) => upd("warn_err_pct")(Number(e.target.value) || 0)}
              data-testid="ops-threshold-warn-err"
            />
          </div>
          <div className="space-y-2">
            <Label className="text-xs">Critical error rate (%)</Label>
            <Input
              type="number" min={0} max={100} step={0.1}
              value={draft.bad_err_pct}
              onChange={(e) => upd("bad_err_pct")(Number(e.target.value) || 0)}
              data-testid="ops-threshold-bad-err"
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={reset} data-testid="ops-threshold-reset">Reset to defaults</Button>
          <Button onClick={submit} data-testid="ops-threshold-save">Save</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
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
