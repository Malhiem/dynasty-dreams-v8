// @ts-nocheck
/**
 * Iter 187 — Commissioner Ops Console.
 *
 * One-glance dashboard giving commissioners:
 *   - Trade Deadline status pill (passed / live countdown).
 *   - 4 counter cards (pending waivers, pending trades, vetoed trades,
 *     teams with violations).
 *   - Recent vetoes table.
 *   - Pending waivers table with quick "Force Process" button (uses
 *     existing POST /waivers/process endpoint so audit log stays
 *     unified).
 *
 * Risks documented:
 *   1. The endpoint requires commissioner access — guard the page
 *      route accordingly. We render a banner if the API returns 403.
 *   2. Force-process is a one-way action; we surface a confirm dialog
 *      before firing the destructive call.
 *   3. Counters refresh on mount + after force-process — no polling
 *      yet to keep the page light. Future: SSE / WebSocket fan-out.
 */
import { useEffect, useState, useRef, useMemo } from "react";
import { Link } from "react-router-dom";
import api from "@/lib/api";
import { useActiveLeague } from "@/hooks/use-active-league";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from "@/components/ui/sheet";
import { toast } from "sonner";
import { Clock, AlertTriangle, ShieldOff, Gavel, Zap, ListChecks, RefreshCw, ScrollText, Download } from "lucide-react";

function fmtRemainingMs(ms) {
  if (ms == null) return null;
  if (ms <= 0) return "passed";
  const totalMin = Math.floor(ms / 60_000);
  const days = Math.floor(totalMin / (60 * 24));
  const hours = Math.floor((totalMin % (60 * 24)) / 60);
  const mins = totalMin % 60;
  if (days > 0) return `${days}d ${hours}h`;
  if (hours > 0) return `${hours}h ${mins}m`;
  return `${mins}m`;
}

export default function OpsConsole() {
  const { league } = useActiveLeague();
  const leagueId = league?.id || league?._id;

  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState(null);
  const [processing, setProcessing] = useState(false);

  // Iter 189 — Violations drilldown sheet state
  const [violationsOpen, setViolationsOpen] = useState(false);
  const [violationsData, setViolationsData] = useState(null);
  const [violationsLoading, setViolationsLoading] = useState(false);

  // Iter 189 — Audit log state. Loads lazily on mount; refresh
  // tied to the global Refresh button to keep payload light.
  const [auditEntries, setAuditEntries] = useState([]);
  const [auditLoading, setAuditLoading] = useState(false);

  // Iter 190 — Event-type filter chips above the audit log. Empty
  // Set means "show all". We always include every distinct type
  // observed so the chip strip rebuilds itself as new events appear.
  const [auditFilter, setAuditFilter] = useState(new Set());
  const [exportingCsv, setExportingCsv] = useState(false);

  const load = async () => {
    if (!leagueId) return;
    setLoading(true);
    setErrorMsg(null);
    try {
      const r = await api.get(`/leagues/${leagueId}/ops-summary`);
      setSummary(r.data);
    } catch (e) {
      const msg = e?.response?.data?.detail || e?.message || "Failed to load ops summary";
      setErrorMsg(typeof msg === "string" ? msg : JSON.stringify(msg));
    } finally {
      setLoading(false);
    }
    // Iter 189 — also refresh audit log entries.
    loadAuditLog();
  };

  const loadAuditLog = async () => {
    if (!leagueId) return;
    setAuditLoading(true);
    try {
      const r = await api.get(`/leagues/${leagueId}/ops-audit-log`, { params: { limit: 20 } });
      setAuditEntries(r.data?.entries || []);
    } catch {
      // non-fatal — leave existing entries on screen
    } finally {
      setAuditLoading(false);
    }
  };

  const loadViolations = async () => {
    if (!leagueId) return;
    setViolationsOpen(true);
    setViolationsLoading(true);
    try {
      const r = await api.get(`/leagues/${leagueId}/ops-violations`);
      setViolationsData(r.data);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to load violations");
    } finally {
      setViolationsLoading(false);
    }
  };

  // Iter 191 — Drilldown quick actions
  const [actionPending, setActionPending] = useState(false);
  const notifyOwners = async () => {
    if (!leagueId) return;
    setActionPending(true);
    try {
      const r = await api.post(`/leagues/${leagueId}/ops-violations/notify`);
      toast.success(`Notified ${r.data?.notified ?? 0} owner(s)`);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to send notifications");
    } finally {
      setActionPending(false);
    }
  };
  const forceFix = async () => {
    if (!leagueId) return;
    if (!window.confirm("Auto-fix all auto-fixable violations (e.g. move healthy players off IR)? Cap-over violations will be left for the owner.")) return;
    setActionPending(true);
    try {
      const r = await api.post(`/leagues/${leagueId}/ops-violations/force-fix`);
      const fixed = r.data?.fixed_count ?? 0;
      const skipped = r.data?.skipped_count ?? 0;
      toast.success(
        `Fixed ${fixed} violation(s)${skipped ? ` · ${skipped} skipped (owner action required)` : ""}`
      );
      // Re-load drilldown + parent counters
      await loadViolations();
      await load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Force-fix failed");
    } finally {
      setActionPending(false);
    }
  };

  // Iter 190 — Distinct event_types in the current audit window —
  // drives the chip strip. Sorted alpha so the strip doesn't shuffle
  // on every refresh.
  const distinctEventTypes = useMemo(() => {
    const s = new Set();
    (auditEntries || []).forEach((e) => e?.event_type && s.add(e.event_type));
    return [...s].sort();
  }, [auditEntries]);

  // Iter 190 — Apply chip filter client-side. The server endpoint
  // also accepts `event_types=`, but filtering here keeps the strip
  // responsive without an extra round-trip on every chip click.
  const filteredAuditEntries = useMemo(() => {
    if (auditFilter.size === 0) return auditEntries;
    return (auditEntries || []).filter((e) => auditFilter.has(e?.event_type));
  }, [auditEntries, auditFilter]);

  const toggleAuditFilter = (t) => {
    setAuditFilter((prev) => {
      const next = new Set(prev);
      if (next.has(t)) next.delete(t); else next.add(t);
      return next;
    });
  };

  // Iter 190 — CSV export. Triggers a download via a temporary
  // anchor; auth header is forwarded by the axios `api` client.
  // We hit the endpoint with `responseType:"blob"` and assemble the
  // Object URL on the fly.
  const exportCsv = async () => {
    if (!leagueId) return;
    setExportingCsv(true);
    try {
      const r = await api.get(`/leagues/${leagueId}/ops-audit-log`, {
        params: { format: "csv", limit: 1000 },
        responseType: "blob",
      });
      const blob = new Blob([r.data], { type: "text/csv" });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `audit-log-${leagueId}-${new Date().toISOString().slice(0, 10)}.csv`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
      toast.success("Audit log exported");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "CSV export failed");
    } finally {
      setExportingCsv(false);
    }
  };

  useEffect(() => { load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [leagueId]);

  // ── Iter 190 — 30s polling tied to document.visibilityState ──
  // We avoid hammering the API when the tab is hidden by skipping
  // the tick whenever the document isn't `visible`. When the tab
  // becomes visible again we fire one immediate refresh so the user
  // doesn't have to wait for the next 30s tick.
  useEffect(() => {
    if (!leagueId) return undefined;
    const tick = () => {
      if (typeof document !== "undefined" && document.visibilityState !== "visible") return;
      // Quiet refresh — don't toggle the global "loading" spinner
      // every 30s; the Refresh button is still the canonical loud
      // refresh for explicit user intent.
      api.get(`/leagues/${leagueId}/ops-summary`).then((r) => setSummary(r.data)).catch(() => {});
      loadAuditLog();
    };
    const id = setInterval(tick, 30_000);
    const onVisible = () => {
      if (document.visibilityState === "visible") tick();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      clearInterval(id);
      document.removeEventListener("visibilitychange", onVisible);
    };
    /* eslint-disable-next-line react-hooks/exhaustive-deps */
  }, [leagueId]);

  const onForceProcess = async () => {
    if (!leagueId) return;
    if (!window.confirm("Force-process all pending waiver claims now? This will settle every pending claim in priority order and adjust FAAB budgets accordingly.")) return;
    setProcessing(true);
    try {
      const r = await api.post(`/waivers/process`, null, { params: { league_id: leagueId } });
      toast.success(`Processed ${r.data?.processed_count ?? 0} waiver claims`);
      await load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to process waivers");
    } finally {
      setProcessing(false);
    }
  };

  if (!leagueId) {
    return (
      <div className="p-6" data-testid="ops-console-no-league">
        <p className="text-sm text-muted-foreground">Select a league to access the Ops Console.</p>
      </div>
    );
  }

  if (errorMsg) {
    return (
      <div className="p-6" data-testid="ops-console-error">
        <Card>
          <CardContent className="pt-6 text-center">
            <AlertTriangle className="h-8 w-8 mx-auto mb-2 text-destructive" />
            <p className="text-sm font-semibold">{errorMsg}</p>
            <p className="text-xs text-muted-foreground mt-1">
              Ops Console is commissioner-only.
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  const counters = summary?.counters || {};
  const deadline = summary?.trade_deadline || {};
  const recentVetoes = summary?.recent_vetoes || [];
  const recentWaivers = summary?.recent_waivers || [];

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto" data-testid="ops-console">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Ops Console</h1>
          <p className="text-sm text-muted-foreground">League operations at a glance</p>
        </div>
        <div className="flex items-center gap-2">
          {/* Trade Deadline pill */}
          {deadline.iso ? (
            <Badge
              variant="outline"
              className={`text-xs ${
                deadline.passed
                  ? "border-destructive text-destructive bg-destructive/10"
                  : "border-amber-500/40 text-amber-300 bg-amber-500/10"
              }`}
              data-testid="ops-trade-deadline-pill"
            >
              <Clock className="h-3.5 w-3.5 mr-1" />
              {deadline.passed
                ? "Trade Deadline passed"
                : `Trade Deadline in ${fmtRemainingMs(deadline.ms_remaining)}`}
            </Badge>
          ) : (
            <Badge variant="outline" className="text-xs text-muted-foreground" data-testid="ops-trade-deadline-pill">
              <Clock className="h-3.5 w-3.5 mr-1" />
              No deadline configured
            </Badge>
          )}
          <Button variant="outline" size="sm" onClick={load} disabled={loading} data-testid="ops-refresh-btn">
            <RefreshCw className={`h-3.5 w-3.5 mr-1 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </Button>
        </div>
      </div>

      {/* ── 4 counter cards ────────────────────────────── */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <CounterCard
          label="Pending Waivers"
          value={counters.pending_waivers ?? 0}
          icon={<Zap className="h-4 w-4 text-blue-300" />}
          testid="ops-counter-pending-waivers"
          accent="border-l-blue-500"
        />
        <CounterCard
          label="Pending Trades"
          value={counters.pending_trades ?? 0}
          icon={<ListChecks className="h-4 w-4 text-emerald-300" />}
          testid="ops-counter-pending-trades"
          accent="border-l-emerald-500"
        />
        <CounterCard
          label="Vetoed Trades"
          value={counters.vetoed_trades ?? 0}
          icon={<Gavel className="h-4 w-4 text-rose-300" />}
          testid="ops-counter-vetoed-trades"
          accent="border-l-rose-500"
        />
        <CounterCard
          label="Teams w/ Violations"
          value={counters.teams_with_violations ?? 0}
          icon={<ShieldOff className="h-4 w-4 text-amber-300" />}
          testid="ops-counter-teams-with-violations"
          accent="border-l-amber-500"
          onClick={loadViolations}
          clickable
        />
      </div>

      {/* ── Pending waivers table ───────────────────────── */}
      <Card data-testid="ops-pending-waivers-card">
        <CardHeader className="flex flex-row items-center justify-between pb-2">
          <CardTitle className="text-base">Next 5 pending waivers</CardTitle>
          <Button
            variant="destructive"
            size="sm"
            onClick={onForceProcess}
            disabled={processing || (counters.pending_waivers ?? 0) === 0}
            data-testid="ops-force-process-btn"
          >
            {processing ? "Processing…" : "Force Process All"}
          </Button>
        </CardHeader>
        <CardContent className="pt-2">
          {recentWaivers.length === 0 ? (
            <p className="text-xs text-muted-foreground py-4 text-center">No pending claims.</p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-xs text-muted-foreground border-b border-border">
                  <th className="text-left py-1.5">Team</th>
                  <th className="text-left py-1.5">Player</th>
                  <th className="text-right py-1.5">Bid</th>
                  <th className="text-right py-1.5">Processes At</th>
                </tr>
              </thead>
              <tbody>
                {recentWaivers.map((w) => (
                  <tr key={w.claim_id} className="border-b border-border/50">
                    <td className="py-1.5">{w.team_name}</td>
                    <td className="py-1.5 font-medium">{w.player_name}</td>
                    <td className="py-1.5 text-right">${w.bid_amount}</td>
                    <td className="py-1.5 text-right text-xs text-muted-foreground">
                      {w.processes_at ? new Date(w.processes_at).toLocaleString() : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>

      {/* ── Recent vetoes ──────────────────────────────── */}
      <Card data-testid="ops-recent-vetoes-card">
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Recent vetoes</CardTitle>
        </CardHeader>
        <CardContent className="pt-2">
          {recentVetoes.length === 0 ? (
            <p className="text-xs text-muted-foreground py-4 text-center">No vetoed trades yet.</p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-xs text-muted-foreground border-b border-border">
                  <th className="text-left py-1.5">Trade</th>
                  <th className="text-left py-1.5">Teams</th>
                  <th className="text-right py-1.5">Vetoes</th>
                  <th className="text-right py-1.5">When</th>
                </tr>
              </thead>
              <tbody>
                {recentVetoes.map((t) => (
                  <tr key={t.trade_id} className="border-b border-border/50">
                    <td className="py-1.5 font-mono text-xs">{t.trade_id?.slice(-8)}</td>
                    <td className="py-1.5">{t.proposer_team_name} ↔ {t.receiver_team_name}</td>
                    <td className="py-1.5 text-right">{t.veto_count}</td>
                    <td className="py-1.5 text-right text-xs text-muted-foreground">
                      {t.vetoed_at ? new Date(t.vetoed_at).toLocaleString() : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>

      {/* ── Iter 189/190 — Audit log card ─────────────────── */}
      <Card data-testid="ops-audit-log-card">
        <CardHeader className="flex flex-row items-center justify-between pb-2 flex-wrap gap-2">
          <div className="flex items-center gap-2">
            <ScrollText className="h-4 w-4 text-muted-foreground" />
            <CardTitle className="text-base">Audit log</CardTitle>
            <span className="text-xs text-muted-foreground">last 20</span>
            {auditLoading && <span className="text-xs text-muted-foreground">Loading…</span>}
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={exportCsv}
            disabled={exportingCsv || auditEntries.length === 0}
            data-testid="ops-audit-export-csv"
          >
            <Download className={`h-3.5 w-3.5 mr-1 ${exportingCsv ? "animate-pulse" : ""}`} />
            {exportingCsv ? "Exporting…" : "Export CSV"}
          </Button>
        </CardHeader>
        <CardContent className="pt-2 space-y-3">
          {/* Iter 190 — Event-type filter chip strip */}
          {distinctEventTypes.length > 0 && (
            <div
              className="flex flex-wrap gap-1.5 pb-2 border-b border-border/40"
              data-testid="ops-audit-filter-chips"
            >
              <button
                type="button"
                onClick={() => setAuditFilter(new Set())}
                className={`text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-full border transition-colors ${
                  auditFilter.size === 0
                    ? "bg-primary/20 text-primary border-primary/40"
                    : "bg-secondary text-muted-foreground border-border hover:border-primary/40"
                }`}
                data-testid="ops-audit-filter-chip-all"
              >
                All
              </button>
              {distinctEventTypes.map((t) => {
                const active = auditFilter.has(t);
                return (
                  <button
                    key={t}
                    type="button"
                    onClick={() => toggleAuditFilter(t)}
                    className={`text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-full border transition-colors ${
                      active
                        ? "bg-primary/20 text-primary border-primary/40"
                        : "bg-secondary text-muted-foreground border-border hover:border-primary/40"
                    }`}
                    data-testid={`ops-audit-filter-chip-${t}`}
                  >
                    {t}
                  </button>
                );
              })}
            </div>
          )}

          {filteredAuditEntries.length === 0 ? (
            <p className="text-xs text-muted-foreground py-4 text-center" data-testid="ops-audit-log-empty">
              {auditEntries.length === 0
                ? "No activity recorded yet."
                : "No entries match the selected filters."}
            </p>
          ) : (
            <ul className="divide-y divide-border/50">
              {filteredAuditEntries.map((entry) => (
                <li
                  key={entry.id}
                  className="py-2 flex items-start gap-3 text-sm"
                  data-testid={`ops-audit-entry-${entry.event_type}`}
                >
                  <Badge variant="outline" className="text-[10px] uppercase tracking-wider shrink-0">
                    {entry.event_type}
                  </Badge>
                  <div className="flex-1">
                    <p className="leading-snug">{entry.message}</p>
                    <p className="text-[11px] text-muted-foreground flex flex-wrap items-center gap-x-2">
                      <span>{entry.created_at ? new Date(entry.created_at).toLocaleString() : "—"}</span>
                      {/* Iter 190 — User attribution */}
                      {entry.user_name && (
                        <span className="text-foreground/70">· by {entry.user_name}</span>
                      )}
                      {!entry.user_name && entry.user_email && (
                        <span className="text-foreground/60">· by {entry.user_email}</span>
                      )}
                      {!entry.user_name && !entry.user_email && entry.user_id && (
                        <span className="text-muted-foreground/60">· system</span>
                      )}
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <div className="pt-2">
        <Link to="/commissioner/settings" className="text-xs text-primary hover:underline">
          Go to Commissioner Settings →
        </Link>
      </div>

      {/* ── Iter 189 — Violations drilldown sheet ───── */}
      <Sheet open={violationsOpen} onOpenChange={setViolationsOpen}>
        <SheetContent
          side="right"
          className="w-full sm:max-w-[480px] overflow-y-auto"
          data-testid="ops-violations-sheet"
        >
          <SheetHeader>
            <SheetTitle className="flex items-center gap-2">
              <ShieldOff className="h-4 w-4 text-amber-300" />
              Roster Violations
            </SheetTitle>
            <SheetDescription>
              Per-team rule breaches that need commissioner attention.
            </SheetDescription>
          </SheetHeader>
          {/* Iter 191 — Drilldown quick actions */}
          {!violationsLoading && (violationsData?.teams || []).length > 0 && (
            <div className="mt-3 flex flex-wrap gap-2" data-testid="ops-violations-actions">
              <Button
                size="sm"
                variant="outline"
                onClick={notifyOwners}
                disabled={actionPending}
                data-testid="ops-violations-notify-btn"
              >
                📧 Notify owners
              </Button>
              <Button
                size="sm"
                variant="destructive"
                onClick={forceFix}
                disabled={actionPending}
                data-testid="ops-violations-force-fix-btn"
              >
                🔧 Force-fix
              </Button>
            </div>
          )}
          <div className="mt-4 space-y-3">
            {violationsLoading && (
              <p className="text-xs text-muted-foreground" data-testid="ops-violations-loading">
                Loading…
              </p>
            )}
            {!violationsLoading && (violationsData?.teams || []).length === 0 && (
              <p className="text-xs text-muted-foreground py-6 text-center" data-testid="ops-violations-empty">
                No teams currently in violation. 🎉
              </p>
            )}
            {!violationsLoading
              && (violationsData?.teams || []).map((team) => (
                <div
                  key={team.team_id}
                  className="rounded-md border border-amber-500/40 bg-amber-500/10 p-3 space-y-2"
                  data-testid={`ops-violations-team-${team.team_id}`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-sm font-semibold">{team.team_name}</span>
                    {team.cap_total != null && (
                      <span className="text-[11px] text-muted-foreground">
                        Cap: ${(team.salary_used / 1_000_000).toFixed(2)}M / $
                        {(team.cap_total / 1_000_000).toFixed(1)}M
                      </span>
                    )}
                  </div>
                  <ul className="space-y-1">
                    {team.violations.map((v, idx) => (
                      <li
                        key={`${v.code}-${idx}`}
                        className="text-xs flex items-start gap-2"
                      >
                        <Badge
                          variant="outline"
                          className={`text-[9px] shrink-0 ${
                            v.severity === "error"
                              ? "border-destructive/50 text-destructive"
                              : "border-amber-500/40 text-amber-300"
                          }`}
                        >
                          {v.code}
                        </Badge>
                        <span className="leading-snug">{v.message}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
          </div>
        </SheetContent>
      </Sheet>
    </div>
  );
}

function CounterCard({ label, value, icon, testid, accent, onClick, clickable }) {
  return (
    <Card
      className={`border-l-4 ${accent} ${clickable ? "cursor-pointer hover:bg-secondary/30 transition-colors" : ""}`}
      data-testid={testid}
      onClick={clickable ? onClick : undefined}
      role={clickable ? "button" : undefined}
      tabIndex={clickable ? 0 : undefined}
      onKeyDown={
        clickable
          ? (e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onClick?.();
              }
            }
          : undefined
      }
    >
      <CardContent className="pt-6 pb-4">
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          {icon}
          {label}
          {clickable && <span className="ml-auto text-[10px] text-primary">View →</span>}
        </div>
        <div className="text-3xl font-bold mt-1">{value}</div>
      </CardContent>
    </Card>
  );
}
