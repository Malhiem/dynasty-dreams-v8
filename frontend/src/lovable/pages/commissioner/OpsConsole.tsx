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
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api from "@/lib/api";
import { useActiveLeague } from "@/hooks/use-active-league";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";
import { Clock, AlertTriangle, ShieldOff, Gavel, Zap, ListChecks, RefreshCw } from "lucide-react";

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
  };

  useEffect(() => { load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [leagueId]);

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

      <div className="pt-2">
        <Link to="/commissioner/settings" className="text-xs text-primary hover:underline">
          Go to Commissioner Settings →
        </Link>
      </div>
    </div>
  );
}

function CounterCard({ label, value, icon, testid, accent }) {
  return (
    <Card className={`border-l-4 ${accent}`} data-testid={testid}>
      <CardContent className="pt-6 pb-4">
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          {icon}
          {label}
        </div>
        <div className="text-3xl font-bold mt-1">{value}</div>
      </CardContent>
    </Card>
  );
}
