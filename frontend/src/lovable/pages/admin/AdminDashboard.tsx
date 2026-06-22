// @ts-nocheck
/**
 * Iter 201a–d — Platform Admin Dashboard
 *
 * Tabs:
 *   • Overview          — metrics tiles + 14-day timeseries (201a)
 *   • Commish Actions   — cross-league audit feed + revert (201a)
 *   • Trade Review      — fairness-scored cross-league trades (201b)
 *   • Collusion         — repeat-pair one-sidedness flags (201c)
 *   • Tanking           — bench-top-salary heuristic (201c)
 *   • Lineup Audit      — IP/UA fingerprints + multi-account (201d)
 *
 * All routes are admin-role gated via /api/admin/platform/*.
 */
import { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import api from "@/lib/api";
import { toast } from "sonner";
import {
  Users, ListChecks, TrendingUp, Activity, Shield, RotateCcw, Clock, Filter,
  ArrowLeftRight, AlertTriangle, UserX, Monitor,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
// Iter 208 — Trust Score pill rendered next to reported users.
import TrustScoreBadge from "@/components/TrustScoreBadge";
// Iter 210 — Critical-alert banner pulling from Sync + Server Ops.
import CriticalAlertBanner from "@/components/CriticalAlertBanner";

const COMMISH_EVENT_TYPES = [
  "playoff_winner_marked",
  "playoff_prize_distributed",
  "ops_force_lineup_set",
  "ops_force_roster_move",
  "ops_force_trade_approve",
  "ops_force_trade_reject",
  "ops_force_pause_draft",
  "ops_force_resume_draft",
  "ops_violation_notified",
  "ops_violation_force_fixed",
  "lineup_override",
  "trade_override",
  "waiver_override",
  "team_owner_changed",
  "team_renamed",
  "draft_pick_traded",
  "schedule_regenerated",
  "playoff_format_changed",
  "setup_wizard_completed",
];

export default function AdminDashboard() {
  const { user, loading: authLoading } = useAuth();
  const navigate = useNavigate();
  const [metrics, setMetrics] = useState(null);
  const [actions, setActions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState({ event_type: "", league_id: "", user_id: "" });
  const [reverting, setReverting] = useState(null);

  // ── Auth gate
  useEffect(() => {
    if (!authLoading && user && user.role !== "admin") {
      toast.error("Platform admin access required");
      navigate("/dashboard", { replace: true });
    }
  }, [authLoading, user, navigate]);

  const loadAll = useCallback(async () => {
    setLoading(true);
    try {
      const q = new URLSearchParams();
      if (filters.event_type) q.set("event_type", filters.event_type);
      if (filters.league_id) q.set("league_id", filters.league_id);
      if (filters.user_id) q.set("user_id", filters.user_id);
      q.set("limit", "100");
      const [m, a] = await Promise.all([
        api.get("/admin/platform/metrics"),
        api.get(`/admin/platform/commish-actions?${q.toString()}`),
      ]);
      setMetrics(m.data);
      setActions(a.data?.entries || []);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to load admin dashboard");
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => {
    if (user?.role === "admin") loadAll();
  }, [user, loadAll]);

  const revert = async (id) => {
    setReverting(id);
    try {
      await api.post(`/admin/platform/commish-actions/${id}/revert`);
      toast.success("Action reverted");
      loadAll();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to revert");
    } finally {
      setReverting(null);
    }
  };

  if (authLoading || !user) return null;
  if (user.role !== "admin") return null;

  return (
    <div className="min-h-screen bg-background text-foreground" data-testid="admin-dashboard-page">
      <div className="max-w-7xl mx-auto px-4 py-8 space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div className="flex items-center gap-3">
            <Shield className="h-7 w-7 text-rose-400" />
            <div>
              <h1 className="text-2xl font-bold tracking-tight">Platform Admin</h1>
              <p className="text-sm text-muted-foreground">Moderation · trust &amp; safety · platform growth</p>
            </div>
          </div>
          <Button variant="outline" size="sm" onClick={loadAll} disabled={loading} data-testid="admin-refresh-btn">
            Refresh
          </Button>
        </div>

        {/* Iter 210 — Real-time critical alerts (Sync + Server Ops + Dead Leagues) */}
        <CriticalAlertBanner />

        <Tabs defaultValue="overview" className="space-y-6">
          <TabsList className="bg-secondary/30">
            <TabsTrigger value="overview" data-testid="admin-tab-overview">Overview</TabsTrigger>
            <TabsTrigger value="commish" data-testid="admin-tab-commish">Commish Actions</TabsTrigger>
            <TabsTrigger value="trades" data-testid="admin-tab-trades">Trade Review</TabsTrigger>
            <TabsTrigger value="collusion" data-testid="admin-tab-collusion">Collusion</TabsTrigger>
            <TabsTrigger value="tanking" data-testid="admin-tab-tanking">Tanking</TabsTrigger>
            <TabsTrigger value="lineup" data-testid="admin-tab-lineup">Lineup Audit</TabsTrigger>
            <TabsTrigger value="reports" data-testid="admin-tab-reports">User Reports</TabsTrigger>
            <TabsTrigger value="moderation" data-testid="admin-tab-moderation">Moderation</TabsTrigger>
            <TabsTrigger value="integrity" data-testid="admin-tab-integrity">Account Integrity</TabsTrigger>
            <TabsTrigger value="appeals" data-testid="admin-tab-appeals">Appeals</TabsTrigger>
            <TabsTrigger value="health" data-testid="admin-tab-health">League Health</TabsTrigger>
            <TabsTrigger value="sync" data-testid="admin-tab-sync">Sync Monitor</TabsTrigger>
            <TabsTrigger value="support" data-testid="admin-tab-support">Support</TabsTrigger>
            <TabsTrigger value="ops" data-testid="admin-tab-ops">Server Ops</TabsTrigger>
            <TabsTrigger value="analytics" data-testid="admin-tab-analytics">Analytics</TabsTrigger>
          </TabsList>

          {/* ─── Overview tab ─── */}
          <TabsContent value="overview" className="space-y-6">
            <section className="space-y-3">
              <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
                Platform Health
              </h2>
              <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
                <Tile icon={Users} label="Total Users" value={metrics?.counts?.users} delta={metrics?.this_week?.new_users} deltaLabel="this wk" testid="metric-users" />
                <Tile icon={ListChecks} label="Total Leagues" value={metrics?.counts?.leagues} delta={metrics?.this_week?.new_leagues} deltaLabel="this wk" testid="metric-leagues" />
                <Tile icon={TrendingUp} label="Trades" value={metrics?.counts?.trades} delta={metrics?.this_week?.trades} deltaLabel="this wk" testid="metric-trades" />
                <Tile icon={Activity} label="Active Drafts" value={metrics?.this_week?.active_drafts} testid="metric-active-drafts" />
                <Tile icon={Clock} label="Transactions (7d)" value={metrics?.this_week?.transactions} testid="metric-transactions-week" />
              </div>
            </section>
            {metrics?.timeseries_14d?.length > 0 && (
              <section className="space-y-3">
                <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
                  14-Day Growth
                </h2>
                <Timeseries data={metrics.timeseries_14d} />
              </section>
            )}
          </TabsContent>

          {/* ─── Commish tab ─── */}
          <TabsContent value="commish" className="space-y-3">
            <CommishActions
              actions={actions}
              loading={loading}
              filters={filters}
              setFilters={setFilters}
              revert={revert}
              reverting={reverting}
            />
          </TabsContent>

          {/* ─── Trade Review (201b) ─── */}
          <TabsContent value="trades" className="space-y-3">
            <TradesPanel />
          </TabsContent>

          {/* ─── Collusion (201c) ─── */}
          <TabsContent value="collusion" className="space-y-3">
            <CollusionPanel />
          </TabsContent>

          {/* ─── Tanking (201c) ─── */}
          <TabsContent value="tanking" className="space-y-3">
            <TankingPanel />
          </TabsContent>

          {/* ─── Lineup Audit (201d) ─── */}
          <TabsContent value="lineup" className="space-y-3">
            <LineupAuditPanel />
          </TabsContent>

          {/* ─── User Reports (Iter 205 — Content Moderation Phase 1) ─── */}
          <TabsContent value="reports" className="space-y-3">
            <UserReportsPanel />
          </TabsContent>

          {/* ─── Moderation Queue + Keyword filters (Iter 206 — Phase 2/3) ─── */}
          <TabsContent value="moderation" className="space-y-3">
            <ModerationQueuePanel />
            <KeywordFiltersPanel />
          </TabsContent>

          {/* ─── Account Integrity (Iter 206) ─── */}
          <TabsContent value="integrity" className="space-y-3">
            <AccountIntegrityPanel />
          </TabsContent>

          {/* ─── Appeals (Iter 206) ─── */}
          <TabsContent value="appeals" className="space-y-3">
            <AppealsPanel />
          </TabsContent>

          {/* ─── League Health (Iter 209) ─── */}
          <TabsContent value="health" className="space-y-3">
            <LeagueHealthPanel />
          </TabsContent>

          {/* ─── Sync Monitor (Iter 209) ─── */}
          <TabsContent value="sync" className="space-y-3">
            <SyncMonitorPanel />
          </TabsContent>

          {/* ─── Support Metrics (Iter 209) ─── */}
          <TabsContent value="support" className="space-y-3">
            <SupportMetricsPanel />
          </TabsContent>

          {/* ─── Server Ops (Iter 209) ─── */}
          <TabsContent value="ops" className="space-y-3">
            <ServerOpsPanel />
          </TabsContent>

          {/* ─── Platform Analytics (Iter 211) ─── */}
          <TabsContent value="analytics" className="space-y-3">
            <PlatformAnalyticsPanel />
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}

/* ─── CommishActions: extracted from inline so the dashboard can tab ─── */
function CommishActions({ actions, loading, filters, setFilters, revert, reverting }) {
  return (
    <section className="space-y-3" data-testid="commish-actions-section">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
          Commissioner Action Log <span className="text-foreground/70">· cross-league</span>
        </h2>
        <div className="flex items-center gap-2 flex-wrap">
          <Filter className="h-3.5 w-3.5 text-muted-foreground" />
          <Select
            value={filters.event_type || "_all"}
            onValueChange={(v) => setFilters((f) => ({ ...f, event_type: v === "_all" ? "" : v }))}
          >
            <SelectTrigger className="h-8 w-[230px] text-xs" data-testid="commish-filter-event-type">
              <SelectValue placeholder="All event types" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="_all">All event types</SelectItem>
              {COMMISH_EVENT_TYPES.map((t) => (
                <SelectItem key={t} value={t}>{t}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Input
            placeholder="League id"
            value={filters.league_id}
            onChange={(e) => setFilters((f) => ({ ...f, league_id: e.target.value }))}
            className="h-8 w-[180px] text-xs"
            data-testid="commish-filter-league-id"
          />
          <Input
            placeholder="User id"
            value={filters.user_id}
            onChange={(e) => setFilters((f) => ({ ...f, user_id: e.target.value }))}
            className="h-8 w-[180px] text-xs"
            data-testid="commish-filter-user-id"
          />
        </div>
      </div>

      <div className="rounded-lg border border-border overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-secondary/50 text-xs uppercase tracking-wider text-muted-foreground">
            <tr>
              <th className="text-left px-3 py-2">When</th>
              <th className="text-left px-3 py-2">Event</th>
              <th className="text-left px-3 py-2">League</th>
              <th className="text-left px-3 py-2">Actor</th>
              <th className="text-left px-3 py-2">Detail</th>
              <th className="text-right px-3 py-2">Action</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={6} className="text-center text-muted-foreground py-6">Loading…</td></tr>
            ) : actions.length === 0 ? (
              <tr><td colSpan={6} className="text-center text-muted-foreground py-6">No actions logged.</td></tr>
            ) : actions.map((a) => (
              <tr key={a.id} className="border-t border-border hover:bg-secondary/20" data-testid={`commish-action-row-${a.id}`}>
                <td className="px-3 py-2 text-xs text-muted-foreground whitespace-nowrap">{(a.created_at || "").slice(0, 19).replace("T", " ")}</td>
                <td className="px-3 py-2 text-xs">
                  <span className="inline-block rounded-md px-1.5 py-0.5 bg-cyan-500/15 text-cyan-300 border border-cyan-500/30 font-mono">
                    {a.event_type}
                  </span>
                </td>
                <td className="px-3 py-2 text-xs">{a.league_name || (a.league_id ? a.league_id.slice(0, 8) : "—")}</td>
                <td className="px-3 py-2 text-xs">{a.user?.email || a.user_id?.slice(0, 8) || "—"}</td>
                <td className="px-3 py-2 text-xs max-w-[280px] truncate" title={a.message}>{a.message || "—"}</td>
                <td className="px-3 py-2 text-right">
                  {a.reverted ? (
                    <span className="text-[10px] uppercase tracking-wider font-semibold text-rose-300" data-testid={`commish-reverted-pill-${a.id}`}>
                      Reverted
                    </span>
                  ) : (
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => revert(a.id)}
                      disabled={reverting === a.id}
                      className="text-xs h-7"
                      data-testid={`commish-revert-btn-${a.id}`}
                    >
                      <RotateCcw className="h-3 w-3 mr-1" />
                      Revert
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

/* ─── Iter 201b — Trade Review panel ───────────────────────────────── */
function TradesPanel() {
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

/* ─── Iter 201c — Collusion panel ──────────────────────────────────── */
function CollusionPanel() {
  const [data, setData] = useState({ pairs: [] });
  const [locks, setLocks] = useState([]);
  const [minTrades, setMinTrades] = useState(3);
  const [minNetFavor, setMinNetFavor] = useState(30);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [pairs, locksRes] = await Promise.all([
        api.get(`/admin/platform/collusion-flags?min_trades=${minTrades}&min_net_favor_pct=${minNetFavor}`),
        api.get(`/admin/platform/pairs/locks`),
      ]);
      setData(pairs.data);
      setLocks(locksRes.data?.locks || []);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to load collusion flags");
    } finally { setLoading(false); }
  }, [minTrades, minNetFavor]);
  useEffect(() => { load(); }, [load]);

  return (
    <section data-testid="collusion-section" className="space-y-3">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-2">
          <UserX className="h-4 w-4 text-rose-400" />
          Collusion Detection
        </h2>
        <div className="flex items-center gap-2 text-xs">
          <span className="text-muted-foreground">Min trades</span>
          <Input
            type="number" min={2} max={20} value={minTrades}
            onChange={(e) => setMinTrades(parseInt(e.target.value) || 3)}
            className="h-8 w-16 text-xs" data-testid="collusion-min-trades"
          />
          <span className="text-muted-foreground">Min net favor %</span>
          <Input
            type="number" min={10} max={100} value={minNetFavor}
            onChange={(e) => setMinNetFavor(parseInt(e.target.value) || 30)}
            className="h-8 w-16 text-xs" data-testid="collusion-min-favor"
          />
        </div>
      </div>
      <div className="rounded-lg border border-border overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-secondary/50 text-xs uppercase tracking-wider text-muted-foreground">
            <tr>
              <th className="text-left px-3 py-2">Pair</th>
              <th className="text-left px-3 py-2">Trades</th>
              <th className="text-left px-3 py-2">Net Favor</th>
              <th className="text-left px-3 py-2">Favored User</th>
              <th className="text-right px-3 py-2">Action</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={5} className="text-center text-muted-foreground py-6">Loading…</td></tr>
            ) : data.pairs.length === 0 ? (
              <tr><td colSpan={5} className="text-center text-muted-foreground py-6">No suspicious pairs flagged.</td></tr>
            ) : data.pairs.map((p, idx) => {
              const favEmail = (p.users || {})[p.favored_user_id]?.email || p.favored_user_id;
              return (
                <tr key={idx} className="border-t border-border" data-testid={`collusion-pair-${idx}`}>
                  <td className="px-3 py-2 text-xs">
                    {Object.values(p.users || {}).map((u) => u.email).join(" ↔ ")}
                  </td>
                  <td className="px-3 py-2 text-xs font-mono">{p.trade_count}</td>
                  <td className="px-3 py-2 text-xs">
                    <span className="font-mono text-rose-300">{p.net_favor > 0 ? "+" : ""}{p.net_favor}</span>
                  </td>
                  <td className="px-3 py-2 text-xs">{favEmail}</td>
                  <td className="px-3 py-2 text-right">
                    <Button
                      size="sm" variant="ghost" className="text-xs h-7"
                      onClick={async () => {
                        const reason = prompt("Lock reason (optional)?") || "";
                        try {
                          await api.post("/admin/platform/pairs/lock", {
                            user_ids: p.pair, reason,
                          });
                          toast.success("Pair locked");
                          load();
                        } catch (err) {
                          toast.error(err?.response?.data?.detail || "Failed to lock");
                        }
                      }}
                      data-testid={`collusion-lock-btn-${idx}`}
                    >
                      Lock pair
                    </Button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Active locks */}
      {locks.length > 0 && (
        <div className="rounded-lg border border-rose-500/40 bg-rose-500/5 p-3 space-y-2" data-testid="active-locks-block">
          <div className="text-xs font-bold uppercase tracking-wider text-rose-300">Active Trade Locks ({locks.length})</div>
          <ul className="space-y-1">
            {locks.map((l) => (
              <li key={l.lock_id} className="flex items-center justify-between text-xs border-t border-rose-500/20 pt-1.5" data-testid={`lock-row-${l.lock_id}`}>
                <span>
                  <span className="font-medium">{(l.emails || []).join(" ↔ ")}</span>
                  {l.reason && <span className="text-muted-foreground"> · &ldquo;{l.reason}&rdquo;</span>}
                  <span className="text-muted-foreground"> · locked {l.locked_at?.slice(0, 10)}</span>
                </span>
                <Button
                  size="sm" variant="ghost" className="text-xs h-7"
                  onClick={async () => {
                    try {
                      await api.delete(`/admin/platform/pairs/locks/${l.lock_id}`);
                      toast.success("Lock released");
                      load();
                    } catch (e) {
                      toast.error(e?.response?.data?.detail || "Failed to release");
                    }
                  }}
                  data-testid={`lock-release-btn-${l.lock_id}`}
                >
                  Release
                </Button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}

/* ─── Iter 201c — Tanking panel ────────────────────────────────────── */
function TankingPanel() {
  const [data, setData] = useState({ flagged: [] });
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    (async () => {
      try {
        const { data } = await api.get(`/admin/platform/tanking-flags`);
        setData(data);
      } catch (e) {
        toast.error(e?.response?.data?.detail || "Failed to load tanking flags");
      } finally { setLoading(false); }
    })();
  }, []);
  return (
    <section data-testid="tanking-section" className="space-y-3">
      <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-2">
        <AlertTriangle className="h-4 w-4 text-amber-400" />
        Tanking Detection · benched ≥2 top-salary players late-season
      </h2>
      {loading ? (
        <div className="text-sm text-muted-foreground">Loading…</div>
      ) : data.flagged.length === 0 ? (
        <div className="rounded-lg border border-border bg-secondary/10 p-4 text-sm text-muted-foreground">
          No tanking patterns detected in active late-season leagues.
        </div>
      ) : data.flagged.map((lg) => (
        <div key={lg.league_id} className="rounded-lg border border-border bg-secondary/30 p-3 space-y-2"
          data-testid={`tanking-league-${lg.league_id}`}>
          <div className="flex items-center justify-between">
            <div className="font-bold">{lg.league_name}</div>
            <span className="text-[10px] uppercase tracking-wider text-amber-300">
              {lg.weeks_left} weeks remaining
            </span>
          </div>
          <ul className="space-y-1">
            {lg.teams.map((t) => (
              <li key={t.team_id} className="text-xs flex items-center justify-between border-t border-border/40 pt-1">
                <span>{t.team_name} <span className="text-muted-foreground">({t.owner_name})</span></span>
                <span className="font-mono text-rose-300">{t.benched_top5_count} top-5 benched</span>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </section>
  );
}

/* ─── Iter 201d — Lineup Audit panel ───────────────────────────────── */
function LineupAuditPanel() {
  const [data, setData] = useState({ entries: [], multi_account_flags: [] });
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    (async () => {
      try {
        const { data } = await api.get(`/admin/platform/lineup-audit?limit=100`);
        setData(data);
      } catch (e) {
        toast.error(e?.response?.data?.detail || "Failed to load lineup audit");
      } finally { setLoading(false); }
    })();
  }, []);
  return (
    <section data-testid="lineup-audit-section" className="space-y-3">
      <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-2">
        <Monitor className="h-4 w-4" />
        Lineup Audit Trail · IP / UA fingerprinting
      </h2>

      {data.multi_account_flags.length > 0 && (
        <div className="rounded-lg border border-rose-500/40 bg-rose-500/10 p-3 space-y-2"
          data-testid="multi-account-flags-block">
          <div className="text-sm font-bold text-rose-300">
            Multi-account warning · same IP setting lineups for multiple accounts
          </div>
          <ul className="space-y-1">
            {data.multi_account_flags.map((f) => (
              <li key={f.ip} className="text-xs flex items-center justify-between border-t border-rose-500/30 pt-1">
                <span className="font-mono text-rose-200">{f.ip}</span>
                <span>{f.user_count} accounts: {f.users.join(", ")}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="rounded-lg border border-border overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-secondary/50 text-xs uppercase tracking-wider text-muted-foreground">
            <tr>
              <th className="text-left px-3 py-2">When</th>
              <th className="text-left px-3 py-2">League</th>
              <th className="text-left px-3 py-2">Actor</th>
              <th className="text-left px-3 py-2">IP</th>
              <th className="text-left px-3 py-2">UA</th>
              <th className="text-left px-3 py-2">Summary</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={6} className="text-center text-muted-foreground py-6">Loading…</td></tr>
            ) : data.entries.length === 0 ? (
              <tr><td colSpan={6} className="text-center text-muted-foreground py-6">No lineup events yet. Once owners save lineups, they’ll appear here.</td></tr>
            ) : data.entries.map((e) => (
              <tr key={e.id} className="border-t border-border" data-testid={`lineup-row-${e.id}`}>
                <td className="px-3 py-2 text-xs text-muted-foreground whitespace-nowrap">{(e.created_at || "").slice(0, 19).replace("T", " ")}</td>
                <td className="px-3 py-2 text-xs">{e.league_name || e.league_id?.slice(0, 8)}</td>
                <td className="px-3 py-2 text-xs">{e.user?.email || e.user_id?.slice(0, 8)}</td>
                <td className="px-3 py-2 text-xs font-mono">{e.ip || "—"}</td>
                <td className="px-3 py-2 text-xs text-muted-foreground max-w-[180px] truncate" title={e.user_agent}>{e.user_agent || "—"}</td>
                <td className="px-3 py-2 text-xs">{e.summary || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function Tile({ icon: Icon, label, value, delta, deltaLabel, testid }) {
  return (
    <div
      className="rounded-lg border border-border bg-secondary/30 p-3 space-y-1.5"
      data-testid={testid}
    >
      <div className="flex items-center justify-between">
        <span className="text-[10px] uppercase tracking-wider text-muted-foreground font-semibold">
          {label}
        </span>
        <Icon className="h-3.5 w-3.5 text-muted-foreground/70" />
      </div>
      <div className="text-2xl font-bold tabular-nums">
        {value === undefined || value === null ? "—" : value.toLocaleString()}
      </div>
      {(typeof delta === "number") && (
        <div className="text-[10px] text-muted-foreground">
          <span className={delta > 0 ? "text-emerald-300" : "text-muted-foreground"}>
            {delta > 0 ? "+" : ""}{delta}
          </span> {deltaLabel}
        </div>
      )}
    </div>
  );
}

function Timeseries({ data }) {
  const maxUsers = Math.max(1, ...data.map((d) => d.new_users));
  const maxLeagues = Math.max(1, ...data.map((d) => d.new_leagues));
  return (
    <div className="rounded-lg border border-border bg-secondary/30 p-3" data-testid="timeseries-14d">
      <div className="flex items-center gap-4 mb-3 text-xs">
        <span className="inline-flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-full bg-cyan-400" /> New users
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-full bg-emerald-400" /> New leagues
        </span>
      </div>
      <div className="grid grid-cols-15 gap-1" style={{ gridTemplateColumns: `repeat(${data.length}, minmax(0, 1fr))` }}>
        {data.map((d) => (
          <div key={d.date} className="flex flex-col items-center gap-1 group">
            <div className="w-full flex flex-col items-center gap-0.5 h-24 justify-end">
              <div
                className="w-full bg-cyan-400/70 rounded-t-sm transition-all"
                style={{ height: `${(d.new_users / maxUsers) * 50}%` }}
                title={`${d.new_users} new users`}
              />
              <div
                className="w-full bg-emerald-400/70 rounded-t-sm transition-all"
                style={{ height: `${(d.new_leagues / maxLeagues) * 50}%` }}
                title={`${d.new_leagues} new leagues`}
              />
            </div>
            <span className="text-[9px] text-muted-foreground/70">{d.date.slice(5)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}


/* ─── Iter 205 — User Reports / Flag Moderation Queue ────────────────────
 * Lists submitted user reports with filters and inline resolve actions.
 * Admin can mark each report as resolved or dismissed, optionally
 * applying a moderation action (warning / timeout / ban / none).
 */
function UserReportsPanel() {
  const [reports, setReports] = useState<any[]>([]);
  const [openCount, setOpenCount] = useState(0);
  const [loading, setLoading] = useState(false);
  const [statusFilter, setStatusFilter] = useState<"open" | "resolved" | "dismissed" | "all">("open");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get(`/admin/platform/reports?status=${statusFilter}`);
      setReports(data?.reports || []);
      setOpenCount(data?.open_count || 0);
    } catch (e: any) {
      toast.error("Could not load reports");
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => { load(); }, [load]);

  const resolve = async (report_id: string, action: "resolved" | "dismissed", applied: string) => {
    try {
      await api.post(`/admin/platform/reports/${report_id}/resolve`, {
        action,
        applied_action: applied,
        note: "",
      });
      toast.success(`Report ${action}`);
      await load();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Failed to resolve report");
    }
  };

  return (
    <section className="space-y-3" data-testid="reports-section">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold flex items-center gap-2">
            User Reports
            {openCount > 0 && (
              <span className="text-xs px-2 py-0.5 rounded-full bg-rose-500/20 text-rose-300" data-testid="reports-open-badge">
                {openCount} open
              </span>
            )}
          </h2>
          <p className="text-xs text-muted-foreground">
            Reports submitted by users about other users (chat misconduct,
            offensive names, suspicious trades, etc.).
          </p>
        </div>
        <Select value={statusFilter} onValueChange={(v: any) => setStatusFilter(v)}>
          <SelectTrigger className="w-40" data-testid="reports-status-filter">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="open">Open</SelectItem>
            <SelectItem value="resolved">Resolved</SelectItem>
            <SelectItem value="dismissed">Dismissed</SelectItem>
            <SelectItem value="all">All</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {loading && (
        <div className="text-sm text-muted-foreground py-6 text-center" data-testid="reports-loading">
          Loading reports…
        </div>
      )}

      {!loading && reports.length === 0 && (
        <div className="text-sm text-muted-foreground py-6 text-center border border-dashed border-border rounded-lg" data-testid="reports-empty">
          No {statusFilter === "all" ? "" : statusFilter} reports.
        </div>
      )}

      {!loading && reports.length > 0 && (
        <div className="space-y-3" data-testid="reports-list">
          {reports.map((r: any) => (
            <div key={r.report_id} className="rounded-lg border border-border bg-muted/20 p-4" data-testid={`report-${r.report_id}`}>
              <div className="flex items-start justify-between mb-2 gap-3">
                <div className="text-sm">
                  <div className="font-medium flex items-center gap-2 flex-wrap">
                    <span>{r.reporter_email || r.reporter_id} reported {r.target_user_email || r.target_user_id}</span>
                    {r.target_user_id && <TrustScoreBadge userId={r.target_user_id} />}
                  </div>
                  <div className="text-xs text-muted-foreground mt-0.5">
                    {new Date(r.created_at).toLocaleString()} · category:{" "}
                    <span className="capitalize">{r.category?.replace(/_/g, " ")}</span>
                    {r.league_id && <> · league {r.league_id}</>}
                  </div>
                </div>
                <span
                  className={`text-[10px] px-2 py-0.5 rounded-full border ${
                    r.status === "open"
                      ? "border-amber-500/40 text-amber-300"
                      : r.status === "resolved"
                        ? "border-emerald-500/40 text-emerald-300"
                        : "border-slate-500/40 text-slate-300"
                  }`}
                >
                  {r.status}
                </span>
              </div>
              {r.reason && (
                <div className="text-sm bg-secondary/30 rounded p-2 mb-2" data-testid={`report-reason-${r.report_id}`}>
                  {r.reason}
                </div>
              )}
              {r.context_url && (
                <div className="text-xs text-muted-foreground mb-2">
                  Context: <code className="bg-secondary/40 px-1.5 py-0.5 rounded">{r.context_url}</code>
                </div>
              )}
              {r.status === "open" && (
                <div className="flex items-center gap-2 mt-2">
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => resolve(r.report_id, "resolved", "warning")}
                    data-testid={`report-warn-${r.report_id}`}
                  >
                    Resolve · Warn
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    className="border-rose-500/50 text-rose-300 hover:bg-rose-500/10"
                    onClick={() => resolve(r.report_id, "resolved", "ban")}
                    data-testid={`report-ban-${r.report_id}`}
                  >
                    Resolve · Ban
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => resolve(r.report_id, "dismissed", "none")}
                    data-testid={`report-dismiss-${r.report_id}`}
                  >
                    Dismiss
                  </Button>
                </div>
              )}
              {r.status !== "open" && r.resolution_note && (
                <div className="text-xs text-muted-foreground mt-1">
                  <strong>Resolution:</strong> {r.resolution_action} — {r.resolution_note}
                </div>
              )}
              {/* Iter 209 — Mod notes thread per target user */}
              {r.target_user_id && (
                <ModNotesPanel
                  userId={r.target_user_id}
                  userEmail={r.target_user_email}
                />
              )}
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

/* ─── Iter 206 — Moderation Queue Panel ──────────────────────────────── */
function ModerationQueuePanel() {
  const [items, setItems] = useState<any[]>([]);
  const [pendingCount, setPendingCount] = useState(0);
  const [statusFilter, setStatusFilter] = useState<"pending" | "approved" | "deleted" | "all">("pending");
  const [sourceFilter, setSourceFilter] = useState<string>("all");
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ status: statusFilter });
      if (sourceFilter !== "all") params.set("source", sourceFilter);
      const { data } = await api.get(`/admin/platform/moderation-queue?${params.toString()}`);
      setItems(data?.items || []);
      setPendingCount(data?.pending_count || 0);
    } catch {
      toast.error("Could not load moderation queue");
    } finally {
      setLoading(false);
    }
  }, [statusFilter, sourceFilter]);

  useEffect(() => { load(); }, [load]);

  const resolve = async (id: string, action: "approved" | "deleted") => {
    try {
      await api.post(`/admin/platform/moderation/${id}/resolve`, { action, note: "" });
      toast.success(`Item ${action}`);
      await load();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Failed");
    }
  };

  return (
    <section className="space-y-3" data-testid="moderation-queue-section">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold flex items-center gap-2">
            Moderation Queue
            {pendingCount > 0 && (
              <span className="text-xs px-2 py-0.5 rounded-full bg-rose-500/20 text-rose-300" data-testid="moderation-pending-badge">
                {pendingCount} pending
              </span>
            )}
          </h2>
          <p className="text-xs text-muted-foreground">
            Auto-flagged chat messages, usernames, and team names.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Select value={sourceFilter} onValueChange={setSourceFilter}>
            <SelectTrigger className="w-36" data-testid="moderation-source-filter">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All sources</SelectItem>
              <SelectItem value="chat">Chat</SelectItem>
              <SelectItem value="trade_block">Trade block</SelectItem>
              <SelectItem value="username">Usernames</SelectItem>
              <SelectItem value="team_name">Team names</SelectItem>
              <SelectItem value="avatar">Avatars</SelectItem>
            </SelectContent>
          </Select>
          <Select value={statusFilter} onValueChange={(v: any) => setStatusFilter(v)}>
            <SelectTrigger className="w-36" data-testid="moderation-status-filter">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="pending">Pending</SelectItem>
              <SelectItem value="approved">Approved</SelectItem>
              <SelectItem value="deleted">Deleted</SelectItem>
              <SelectItem value="all">All</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      {loading && <div className="text-sm text-muted-foreground py-4 text-center">Loading…</div>}

      {!loading && items.length === 0 && (
        <div className="text-sm text-muted-foreground py-6 text-center border border-dashed border-border rounded-lg" data-testid="moderation-empty">
          No {statusFilter === "all" ? "" : statusFilter} items.
        </div>
      )}

      {!loading && items.length > 0 && (
        <div className="space-y-2" data-testid="moderation-list">
          {items.map((it: any) => (
            <div key={it.item_id} className="rounded-lg border border-border bg-muted/20 p-3" data-testid={`mod-item-${it.item_id}`}>
              <div className="flex items-center justify-between mb-1.5 gap-3">
                <div className="text-xs text-muted-foreground">
                  <span className="uppercase tracking-wider font-semibold text-foreground/80">{it.source}</span>
                  {" · "}
                  <span className="text-rose-300">{it.matched_word ? `matched "${it.matched_word}"` : "manual"}</span>
                  {" · "}
                  <span className="capitalize">severity: {it.severity}</span>
                </div>
                <span className={`text-[10px] px-2 py-0.5 rounded-full border ${
                  it.status === "pending"
                    ? "border-amber-500/40 text-amber-300"
                    : it.status === "approved"
                      ? "border-emerald-500/40 text-emerald-300"
                      : "border-rose-500/40 text-rose-300"
                }`}>
                  {it.status}
                </span>
              </div>
              <div className="text-sm bg-secondary/30 rounded p-2 mb-2 break-words" data-testid={`mod-content-${it.item_id}`}>
                {it.content}
              </div>
              <div className="text-[10px] text-muted-foreground mb-2">
                by {it.author_email || it.author_id || "anonymous"} · {new Date(it.created_at).toLocaleString()}
              </div>
              {it.status === "pending" && (
                <div className="flex items-center gap-2">
                  <Button size="sm" variant="outline" onClick={() => resolve(it.item_id, "approved")} data-testid={`mod-approve-${it.item_id}`}>
                    Approve
                  </Button>
                  <Button size="sm" variant="outline" className="border-rose-500/50 text-rose-300 hover:bg-rose-500/10" onClick={() => resolve(it.item_id, "deleted")} data-testid={`mod-delete-${it.item_id}`}>
                    Delete
                  </Button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </section>
  );
}


/* ─── Iter 206 — Keyword Filters Manager ─────────────────────────────── */
function KeywordFiltersPanel() {
  const [filters, setFilters] = useState<any[]>([]);
  const [word, setWord] = useState("");
  const [severity, setSeverity] = useState<"low" | "medium" | "high">("medium");

  const load = useCallback(async () => {
    try {
      const { data } = await api.get("/admin/platform/keyword-filters");
      setFilters(data?.filters || []);
    } catch { /* noop */ }
  }, []);

  useEffect(() => { load(); }, [load]);

  const add = async () => {
    if (!word.trim()) return;
    try {
      const { data } = await api.post("/admin/platform/keyword-filters", { word: word.trim(), severity });
      if (data?.deduped) toast.info("Already filtered");
      else toast.success("Keyword added");
      setWord("");
      await load();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Failed");
    }
  };

  const remove = async (id: string) => {
    try {
      await api.delete(`/admin/platform/keyword-filters/${id}`);
      toast.success("Keyword removed");
      await load();
    } catch { /* noop */ }
  };

  return (
    <section className="space-y-3 mt-6 pt-6 border-t border-border" data-testid="keyword-filters-section">
      <div>
        <h2 className="text-lg font-semibold">Keyword Filters</h2>
        <p className="text-xs text-muted-foreground">
          Words/phrases that auto-flag content into the moderation queue. Case-insensitive, word-boundary matched.
        </p>
      </div>
      <div className="flex items-center gap-2">
        <Input
          placeholder="Banned word or phrase…"
          value={word}
          onChange={(e) => setWord(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && add()}
          className="max-w-xs"
          data-testid="keyword-add-input"
        />
        <Select value={severity} onValueChange={(v: any) => setSeverity(v)}>
          <SelectTrigger className="w-28" data-testid="keyword-severity-select"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="low">Low</SelectItem>
            <SelectItem value="medium">Medium</SelectItem>
            <SelectItem value="high">High</SelectItem>
          </SelectContent>
        </Select>
        <Button onClick={add} data-testid="keyword-add-btn">Add</Button>
      </div>
      {filters.length === 0 ? (
        <div className="text-sm text-muted-foreground py-2">No keywords configured yet.</div>
      ) : (
        <div className="flex flex-wrap gap-2" data-testid="keyword-list">
          {filters.map((f: any) => (
            <div key={f.filter_id} className="px-2 py-1 rounded border border-border bg-secondary/30 text-xs flex items-center gap-2" data-testid={`keyword-${f.filter_id}`}>
              <span className="font-mono">{f.word}</span>
              <span className={`text-[9px] uppercase ${
                f.severity === "high" ? "text-rose-300" : f.severity === "low" ? "text-emerald-300" : "text-amber-300"
              }`}>{f.severity}</span>
              <button onClick={() => remove(f.filter_id)} className="text-rose-400 hover:text-rose-300 text-[10px]" data-testid={`keyword-remove-${f.filter_id}`}>✕</button>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}


/* ─── Iter 206 — Account Integrity Panel ─────────────────────────────── */
function AccountIntegrityPanel() {
  const [groups, setGroups] = useState<any[]>([]);
  const [deviceGroups, setDeviceGroups] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [banFor, setBanFor] = useState<{ userId: string; email: string } | null>(null);
  const [tab, setTab] = useState<"ip" | "device">("ip");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [ipRes, devRes] = await Promise.all([
        api.get("/admin/platform/account-integrity"),
        api.get("/admin/platform/device-integrity"),
      ]);
      setGroups(ipRes.data?.groups || []);
      setDeviceGroups(devRes.data?.groups || []);
    } catch {
      toast.error("Failed to load integrity report");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const activeGroups = tab === "ip" ? groups : deviceGroups;

  return (
    <section className="space-y-3" data-testid="integrity-section">
      <div>
        <h2 className="text-lg font-semibold">Account Integrity</h2>
        <p className="text-xs text-muted-foreground">
          Distinct users sharing the same IP or device fingerprint. Strong signal for multi-account abuse.
        </p>
      </div>
      <div className="flex gap-2 border-b border-border">
        <button
          type="button"
          onClick={() => setTab("ip")}
          className={`px-3 py-1.5 text-sm border-b-2 -mb-px ${
            tab === "ip"
              ? "border-primary text-foreground"
              : "border-transparent text-muted-foreground hover:text-foreground"
          }`}
          data-testid="integrity-tab-ip"
        >
          Shared IP
          <span className="ml-2 text-[10px] px-1.5 rounded bg-secondary/50">{groups.length}</span>
        </button>
        <button
          type="button"
          onClick={() => setTab("device")}
          className={`px-3 py-1.5 text-sm border-b-2 -mb-px ${
            tab === "device"
              ? "border-primary text-foreground"
              : "border-transparent text-muted-foreground hover:text-foreground"
          }`}
          data-testid="integrity-tab-device"
        >
          Shared Device
          <span className="ml-2 text-[10px] px-1.5 rounded bg-secondary/50">{deviceGroups.length}</span>
        </button>
      </div>
      {loading && <div className="text-sm text-muted-foreground py-4 text-center">Scanning login audit…</div>}
      {!loading && activeGroups.length === 0 && (
        <div className="text-sm text-muted-foreground py-6 text-center border border-dashed border-border rounded-lg" data-testid="integrity-empty">
          No shared-{tab === "ip" ? "IP" : "device"} groups detected.
        </div>
      )}
      {!loading && activeGroups.length > 0 && (
        <div className="space-y-3" data-testid="integrity-list">
          {activeGroups.map((g: any, idx: number) => (
            <div key={g.ip || g.device_hash || idx} className="rounded-lg border border-border bg-muted/20 p-3" data-testid={`integrity-group-${idx}`}>
              <div className="flex items-center justify-between mb-2">
                <div className="text-sm font-mono break-all">
                  {tab === "ip" ? g.ip : (
                    <span title={g.device_hash}>
                      {String(g.device_hash || "").slice(0, 16)}…
                    </span>
                  )}
                </div>
                <span className="text-[10px] px-2 py-0.5 rounded-full border border-amber-500/40 text-amber-300">
                  {g.distinct_users} accounts · {g.login_count} logins
                </span>
              </div>
              <div className="space-y-1">
                {g.users.map((u: any) => (
                  <div key={u.user_id} className="flex items-center justify-between text-sm">
                    <div className="flex items-center gap-2">
                      <span>{u.email || u.user_id}</span>
                      <span className={`text-[10px] px-1.5 rounded ${
                        u.status === "banned" ? "bg-rose-500/20 text-rose-300" :
                        u.status === "suspended" ? "bg-amber-500/20 text-amber-300" :
                        "bg-emerald-500/20 text-emerald-300"
                      }`}>
                        {u.status || "active"}
                      </span>
                    </div>
                    {u.status !== "banned" && (
                      <Button
                        size="sm"
                        variant="outline"
                        className="border-rose-500/50 text-rose-300 hover:bg-rose-500/10"
                        onClick={() => setBanFor({ userId: u.user_id, email: u.email })}
                        data-testid={`integrity-ban-${u.user_id}`}
                      >
                        Ban
                      </Button>
                    )}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
      {banFor && <BanUserDialog target={banFor} onClose={() => setBanFor(null)} onDone={load} />}
    </section>
  );
}


function BanUserDialog({ target, onClose, onDone }: { target: { userId: string; email: string }; onClose: () => void; onDone: () => void }) {
  const [reasonCode, setReasonCode] = useState("harassment");
  const [reason, setReason] = useState("");
  const [durationDays, setDurationDays] = useState<string>("");
  const [submitting, setSubmitting] = useState(false);

  const submit = async () => {
    setSubmitting(true);
    try {
      await api.post(`/admin/platform/users/${target.userId}/ban`, {
        reason_code: reasonCode,
        reason,
        duration_days: durationDays ? Number(durationDays) : null,
      });
      toast.success(`${target.email} ${durationDays ? "suspended" : "banned"}`);
      onClose();
      onDone();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Failed");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4" onClick={onClose}>
      <div className="bg-background border border-border rounded-lg p-5 max-w-md w-full space-y-3" onClick={(e) => e.stopPropagation()} data-testid="ban-dialog">
        <h3 className="text-lg font-semibold">Ban {target.email}</h3>
        <div className="space-y-2">
          <Select value={reasonCode} onValueChange={setReasonCode}>
            <SelectTrigger data-testid="ban-reason-code"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="harassment">Harassment</SelectItem>
              <SelectItem value="fraud">Payment fraud</SelectItem>
              <SelectItem value="cheating">Cheating</SelectItem>
              <SelectItem value="collusion">Collusion</SelectItem>
              <SelectItem value="other">Other</SelectItem>
            </SelectContent>
          </Select>
          <Input
            placeholder="Reason (visible to user)…"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            data-testid="ban-reason-input"
          />
          <Input
            type="number"
            placeholder="Duration days (blank = permanent)"
            value={durationDays}
            onChange={(e) => setDurationDays(e.target.value)}
            data-testid="ban-duration-input"
          />
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button onClick={submit} disabled={submitting || !reason.trim()} className="bg-rose-500/80 hover:bg-rose-500" data-testid="ban-submit-btn">
            {submitting ? "…" : "Apply"}
          </Button>
        </div>
      </div>
    </div>
  );
}


/* ─── Iter 206 — Appeals Panel ───────────────────────────────────────── */
function AppealsPanel() {
  const [appeals, setAppeals] = useState<any[]>([]);
  const [statusFilter, setStatusFilter] = useState<"open" | "approved" | "denied" | "all">("open");
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get(`/admin/platform/appeals?status=${statusFilter}`);
      setAppeals(data?.appeals || []);
    } catch { /* noop */ }
    finally { setLoading(false); }
  }, [statusFilter]);

  useEffect(() => { load(); }, [load]);

  const resolve = async (id: string, action: "approved" | "denied") => {
    try {
      await api.post(`/admin/platform/appeals/${id}/resolve`, { action, note: "" });
      toast.success(action === "approved" ? "Appeal approved · user reinstated" : "Appeal denied");
      await load();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Failed");
    }
  };

  return (
    <section className="space-y-3" data-testid="appeals-section">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">Ban Appeals</h2>
          <p className="text-xs text-muted-foreground">
            Banned/suspended users requesting reinstatement.
          </p>
        </div>
        <Select value={statusFilter} onValueChange={(v: any) => setStatusFilter(v)}>
          <SelectTrigger className="w-32" data-testid="appeals-status-filter"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="open">Open</SelectItem>
            <SelectItem value="approved">Approved</SelectItem>
            <SelectItem value="denied">Denied</SelectItem>
            <SelectItem value="all">All</SelectItem>
          </SelectContent>
        </Select>
      </div>
      {loading && <div className="text-sm text-muted-foreground py-4 text-center">Loading…</div>}
      {!loading && appeals.length === 0 && (
        <div className="text-sm text-muted-foreground py-6 text-center border border-dashed border-border rounded-lg" data-testid="appeals-empty">
          No {statusFilter === "all" ? "" : statusFilter} appeals.
        </div>
      )}
      {!loading && appeals.length > 0 && (
        <div className="space-y-3" data-testid="appeals-list">
          {appeals.map((a: any) => (
            <div key={a.appeal_id} className="rounded-lg border border-border bg-muted/20 p-3" data-testid={`appeal-${a.appeal_id}`}>
              <div className="flex items-center justify-between mb-1">
                <div className="text-sm font-medium">{a.user_email}</div>
                <span className={`text-[10px] px-2 py-0.5 rounded-full border ${
                  a.status === "open" ? "border-amber-500/40 text-amber-300" :
                  a.status === "approved" ? "border-emerald-500/40 text-emerald-300" :
                  "border-rose-500/40 text-rose-300"
                }`}>{a.status}</span>
              </div>
              <div className="text-[10px] text-muted-foreground mb-2">
                Original ban: <span className="capitalize">{a.ban_reason_code}</span> — {a.ban_reason}
              </div>
              <div className="text-sm bg-secondary/30 rounded p-2 mb-2 break-words">{a.message}</div>
              {a.status === "open" && (
                <div className="flex items-center gap-2">
                  <Button size="sm" variant="outline" className="border-emerald-500/50 text-emerald-300 hover:bg-emerald-500/10" onClick={() => resolve(a.appeal_id, "approved")} data-testid={`appeal-approve-${a.appeal_id}`}>
                    Approve · Reinstate
                  </Button>
                  <Button size="sm" variant="outline" className="border-rose-500/50 text-rose-300 hover:bg-rose-500/10" onClick={() => resolve(a.appeal_id, "denied")} data-testid={`appeal-deny-${a.appeal_id}`}>
                    Deny
                  </Button>
                </div>
              )}
              {a.status !== "open" && a.resolution_note && (
                <div className="text-xs text-muted-foreground mt-1">{a.resolution_note}</div>
              )}
            </div>
          ))}
        </div>
      )}
    </section>
  );
}



/* ─── Iter 209 — League Health Panel ─────────────────────────────────── */
function LeagueHealthPanel() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/admin/platform/league-health");
      setData(data);
    } catch {
      toast.error("Could not load league health");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  return (
    <section className="space-y-3" data-testid="league-health-section">
      <div>
        <h2 className="text-lg font-semibold">League Health</h2>
        <p className="text-xs text-muted-foreground">
          Auto-detected league issues — inactive commissioners, orphaned teams, dead-mid-season, capacity gaps.
        </p>
      </div>
      {loading && <div className="text-sm text-muted-foreground py-4 text-center">Scanning…</div>}
      {!loading && data && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3" data-testid="league-health-grid">
          <HealthCard
            title={`Inactive commissioners (${data.inactive_commissioners.length})`}
            description={`No login in ${data.days_inactive}+ days`}
            tone="amber"
            items={data.inactive_commissioners.map((x: any) => ({
              key: x.league_id,
              primary: x.league_name,
              secondary: `Commish ${x.commissioner_email} · last login ${x.last_login || "never"}`,
            }))}
            testId="health-inactive-commish"
          />
          <HealthCard
            title={`Orphaned teams (${data.orphaned_teams.length})`}
            description="Teams missing owner_id"
            tone="rose"
            items={data.orphaned_teams.map((x: any) => ({
              key: x.league_id,
              primary: x.league_name,
              secondary: `${x.orphaned_team_count}/${x.total_teams} teams unowned`,
            }))}
            testId="health-orphaned"
          />
          <HealthCard
            title={`Dead-mid-season (${data.dead_leagues.length})`}
            description="Status=active but no recent matchups"
            tone="rose"
            items={data.dead_leagues.map((x: any) => ({
              key: x.league_id,
              primary: x.league_name,
              secondary: `Last matchup: ${x.last_matchup_at}`,
            }))}
            testId="health-dead"
          />
          <HealthCard
            title={`Capacity gaps (${data.capacity_issues.length})`}
            description="Fewer teams than expected"
            tone="sky"
            items={data.capacity_issues.map((x: any) => ({
              key: x.league_id,
              primary: x.league_name,
              secondary: `${x.current_teams} of ${x.expected_teams} teams`,
            }))}
            testId="health-capacity"
          />
        </div>
      )}
    </section>
  );
}

function HealthCard({ title, description, tone, items, testId }: any) {
  const toneClass: Record<string, string> = {
    amber: "border-amber-500/40",
    rose: "border-rose-500/40",
    sky: "border-sky-500/40",
    emerald: "border-emerald-500/40",
  };
  return (
    <div className={`rounded-lg border bg-muted/20 p-3 ${toneClass[tone] || ""}`} data-testid={testId}>
      <div className="text-sm font-semibold">{title}</div>
      <div className="text-xs text-muted-foreground mb-2">{description}</div>
      {items.length === 0 ? (
        <div className="text-xs text-muted-foreground italic py-1">All clear.</div>
      ) : (
        <div className="space-y-1 max-h-48 overflow-y-auto">
          {items.map((it: any) => (
            <div key={it.key} className="text-xs border-l-2 border-border pl-2 py-0.5">
              <div>{it.primary}</div>
              <div className="text-[10px] text-muted-foreground">{it.secondary}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}


/* ─── Iter 209 — Sync Monitor Panel ──────────────────────────────────── */
function SyncMonitorPanel() {
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

function SyncStat({ label, value }: { label: string; value: any }) {
  return (
    <div className="rounded-lg border border-border bg-muted/20 p-3">
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className="text-lg font-semibold">{value ?? "—"}</div>
    </div>
  );
}


/* ─── Iter 209 — Support Metrics Panel ───────────────────────────────── */
function SupportMetricsPanel() {
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


/* ─── Iter 209 — Server Ops / Error Logs Panel ───────────────────────── */
function ServerOpsPanel() {
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


/* ─── Iter 209 — Mod Notes side-panel (lives inside the Reports tab) ──── */
export function ModNotesPanel({ userId, userEmail }: { userId: string; userEmail?: string }) {
  const [notes, setNotes] = useState<any[]>([]);
  const [body, setBody] = useState("");
  const [category, setCategory] = useState<"general" | "warning" | "positive" | "other">("general");

  const load = useCallback(async () => {
    if (!userId) return;
    try {
      const { data } = await api.get(`/admin/platform/users/${userId}/mod-notes`);
      setNotes(data?.notes || []);
    } catch { /* noop */ }
  }, [userId]);

  useEffect(() => { load(); }, [load]);

  const add = async () => {
    if (!body.trim()) return;
    try {
      await api.post(`/admin/platform/users/${userId}/mod-notes`, { body: body.trim(), category });
      setBody("");
      toast.success("Note added");
      await load();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Failed");
    }
  };

  const remove = async (id: string) => {
    try {
      await api.delete(`/admin/platform/users/${userId}/mod-notes/${id}`);
      await load();
    } catch { /* noop */ }
  };

  return (
    <div className="mt-3 border-t border-border pt-3" data-testid={`mod-notes-${userId}`}>
      <div className="text-xs font-semibold mb-2 flex items-center gap-2">
        Mod notes
        <span className="text-[10px] px-1.5 rounded bg-secondary/50 text-muted-foreground">
          {notes.length}
        </span>
        <span className="text-[10px] text-muted-foreground font-normal">
          for {userEmail || userId}
        </span>
      </div>
      <div className="space-y-1 mb-2 max-h-40 overflow-y-auto">
        {notes.length === 0 && (
          <div className="text-[11px] text-muted-foreground italic">No notes yet.</div>
        )}
        {notes.map((n: any) => (
          <div key={n.note_id} className="text-xs flex items-start gap-2 border-l-2 border-border pl-2 py-0.5">
            <span className={`text-[9px] uppercase shrink-0 mt-0.5 ${
              n.category === "warning" ? "text-amber-300" :
              n.category === "positive" ? "text-emerald-300" :
              "text-muted-foreground"
            }`}>{n.category}</span>
            <div className="flex-1 min-w-0">
              <div className="break-words">{n.body}</div>
              <div className="text-[10px] text-muted-foreground">
                {n.author_email} · {new Date(n.created_at).toLocaleString()}
              </div>
            </div>
            <button
              onClick={() => remove(n.note_id)}
              className="text-rose-400 hover:text-rose-300 text-[10px] shrink-0"
              data-testid={`mod-note-remove-${n.note_id}`}
            >✕</button>
          </div>
        ))}
      </div>
      <div className="flex items-center gap-2">
        <Input
          value={body}
          onChange={(e) => setBody(e.target.value)}
          placeholder="Add a moderator note…"
          onKeyDown={(e) => e.key === "Enter" && add()}
          maxLength={2000}
          className="text-xs h-8"
          data-testid={`mod-note-input-${userId}`}
        />
        <Select value={category} onValueChange={(v: any) => setCategory(v)}>
          <SelectTrigger className="w-24 h-8 text-xs"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="general">General</SelectItem>
            <SelectItem value="warning">Warning</SelectItem>
            <SelectItem value="positive">Positive</SelectItem>
            <SelectItem value="other">Other</SelectItem>
          </SelectContent>
        </Select>
        <Button size="sm" onClick={add} disabled={!body.trim()} data-testid={`mod-note-add-${userId}`}>
          Add
        </Button>
      </div>
    </div>
  );
}



/* ─── Iter 211 — Platform Analytics Panel ────────────────────────────── */
function PlatformAnalyticsPanel() {
  const [engagement, setEngagement] = useState<any>(null);
  const [survival, setSurvival] = useState<any>(null);
  const [usage, setUsage] = useState<any>(null);
  const [revenue, setRevenue] = useState<any>(null);
  const [irAbuse, setIrAbuse] = useState<any>(null);
  const [goalies, setGoalies] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [e, s, u, r, ir, g] = await Promise.all([
        api.get("/admin/platform/analytics/engagement?days=30"),
        api.get("/admin/platform/analytics/league-survival"),
        api.get("/admin/platform/analytics/feature-usage"),
        api.get("/admin/platform/analytics/revenue?months=12"),
        api.get("/admin/platform/hockey/ir-abuse"),
        api.get("/admin/platform/hockey/goalie-streaming?days=7"),
      ]);
      setEngagement(e.data);
      setSurvival(s.data);
      setUsage(u.data);
      setRevenue(r.data);
      setIrAbuse(ir.data);
      setGoalies(g.data);
    } catch { toast.error("Could not load analytics"); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  return (
    <section className="space-y-4" data-testid="platform-analytics-section">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">Platform Analytics</h2>
          <p className="text-xs text-muted-foreground">
            DAU/MAU · Cohort retention · League survival · Top features
          </p>
        </div>
        <Button size="sm" variant="outline" onClick={load} data-testid="analytics-refresh-btn">Refresh</Button>
      </div>
      {loading && <div className="text-sm text-muted-foreground py-4 text-center">Loading…</div>}

      {!loading && engagement && (
        <div className="space-y-3" data-testid="analytics-engagement">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <SyncStat label="MAU (30d)" value={engagement.mau} />
            <SyncStat label="Latest DAU" value={engagement.latest_dau} />
            <SyncStat label="DAU/MAU" value={
              <span className={engagement.dau_mau_ratio > 0.2 ? "text-emerald-300" : "text-amber-300"}>
                {(engagement.dau_mau_ratio * 100).toFixed(1)}%
              </span>
            } />
            <SyncStat label="Days tracked" value={engagement.dau_series?.length || 0} />
          </div>
          {engagement.dau_series?.length > 0 && (
            <div className="rounded-lg border border-border bg-muted/20 p-3" data-testid="dau-series">
              <div className="text-sm font-semibold mb-2">DAU last {engagement.days} days</div>
              <div className="flex items-end gap-0.5 h-24">
                {engagement.dau_series.map((d: any) => {
                  const max = Math.max(1, ...engagement.dau_series.map((x: any) => x.dau));
                  const h = (d.dau / max) * 100;
                  return (
                    <div
                      key={d.day}
                      className="flex-1 bg-sky-500/60 hover:bg-sky-400 rounded-t transition-colors"
                      style={{ height: `${h}%` }}
                      title={`${d.day}: ${d.dau} DAU`}
                    />
                  );
                })}
              </div>
            </div>
          )}
          {engagement.cohort_retention?.length > 0 && (
            <div className="rounded-lg border border-border bg-muted/20 p-3" data-testid="cohort-retention">
              <div className="text-sm font-semibold mb-2">Monthly cohort retention (active last 30d)</div>
              <div className="space-y-1.5">
                {engagement.cohort_retention.map((c: any) => (
                  <div key={c.cohort}>
                    <div className="flex items-center justify-between text-xs mb-0.5">
                      <span>{c.cohort}</span>
                      <span className="text-muted-foreground">
                        {c.retained}/{c.total} · {c.retention_pct}%
                      </span>
                    </div>
                    <div className="h-1.5 bg-secondary/30 rounded">
                      <div className="h-full bg-emerald-500/60 rounded" style={{ width: `${c.retention_pct}%` }} />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {!loading && survival?.by_year?.length > 0 && (
        <div className="rounded-lg border border-border bg-muted/20 p-3" data-testid="league-survival">
          <div className="text-sm font-semibold mb-2">League survival by creation year</div>
          <div className="space-y-1.5">
            {survival.by_year.map((y: any) => (
              <div key={y.year}>
                <div className="flex items-center justify-between text-xs mb-0.5">
                  <span>{y.year}</span>
                  <span className="text-muted-foreground">
                    {y.still_active}/{y.total} still active · {y.survival_pct}%
                  </span>
                </div>
                <div className="h-1.5 bg-secondary/30 rounded">
                  <div className="h-full bg-amber-500/60 rounded" style={{ width: `${y.survival_pct}%` }} />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {!loading && usage?.top_endpoints?.length > 0 && (
        <div className="rounded-lg border border-border bg-muted/20 p-3" data-testid="feature-usage">
          <div className="text-sm font-semibold mb-2">
            Top endpoints (last {usage.log_tail_size} log lines)
          </div>
          <div className="space-y-1">
            {usage.top_endpoints.slice(0, 15).map((e: any) => {
              const max = Math.max(1, ...usage.top_endpoints.map((x: any) => x.hits));
              const pct = (e.hits / max) * 100;
              return (
                <div key={e.endpoint} className="flex items-center gap-2 text-xs">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between mb-0.5">
                      <span className="font-mono truncate">{e.endpoint}</span>
                      <span className="text-muted-foreground shrink-0 ml-2">{e.hits}</span>
                    </div>
                    <div className="h-1 bg-secondary/30 rounded">
                      <div className="h-full bg-sky-500/60 rounded" style={{ width: `${pct}%` }} />
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Iter 212 — Revenue Dashboard */}
      {!loading && revenue && (
        <div className="rounded-lg border border-emerald-500/40 bg-muted/20 p-3" data-testid="revenue-dashboard">
          <div className="text-sm font-semibold mb-2">Revenue (Stripe-backed)</div>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-3">
            <SyncStat label="Total revenue" value={
              <span className="text-emerald-300">
                ${(revenue.total_revenue_cents / 100).toFixed(2)}
              </span>
            } />
            <SyncStat label="Paid txns" value={revenue.total_paid_txns} />
            <SyncStat label="MRR (last month)" value={
              <span className="text-emerald-300">
                ${(revenue.mrr_cents / 100).toFixed(2)}
              </span>
            } />
          </div>
          {revenue.by_month?.length > 0 && (
            <div className="space-y-1">
              {revenue.by_month.map((m: any) => {
                const max = Math.max(1, ...revenue.by_month.map((x: any) => x.revenue_cents));
                const pct = (m.revenue_cents / max) * 100;
                return (
                  <div key={m.month} className="text-xs">
                    <div className="flex items-center justify-between mb-0.5">
                      <span>{m.month}</span>
                      <span className="text-muted-foreground">
                        ${(m.revenue_cents / 100).toFixed(2)} · {m.txn_count} txns
                      </span>
                    </div>
                    <div className="h-1.5 bg-secondary/30 rounded">
                      <div className="h-full bg-emerald-500/60 rounded" style={{ width: `${pct}%` }} />
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* Iter 212 — Hockey Insights */}
      {!loading && (irAbuse || goalies) && (
        <div className="rounded-lg border border-sky-500/40 bg-muted/20 p-3 space-y-3" data-testid="hockey-insights">
          <div className="text-sm font-semibold">Hockey Insights</div>

          {irAbuse && (
            <div data-testid="ir-abuse">
              <div className="flex items-center justify-between mb-1.5">
                <div className="text-xs font-semibold uppercase tracking-wider">
                  IR Abuse — healthy players stashed
                </div>
                <span className={`text-[10px] px-2 py-0.5 rounded-full border ${
                  irAbuse.flagged_count > 0 ? "border-rose-500/40 text-rose-300" : "border-emerald-500/40 text-emerald-300"
                }`}>
                  {irAbuse.flagged_count} flagged
                </span>
              </div>
              {irAbuse.flagged_count === 0 ? (
                <div className="text-xs text-muted-foreground italic">All clear.</div>
              ) : (
                <div className="space-y-0.5 max-h-40 overflow-y-auto">
                  {irAbuse.flagged.slice(0, 15).map((f: any, i: number) => (
                    <div key={`${f.team_id}-${f.player_id}-${i}`} className="text-xs flex items-center justify-between border-l-2 border-rose-500/40 pl-2 py-0.5">
                      <div>
                        <span className="font-medium">{f.player_name}</span>
                        <span className="text-muted-foreground"> · {f.nhl_team}</span>
                      </div>
                      <span className="text-[10px] text-rose-300 capitalize">{f.current_status}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {goalies && (
            <div data-testid="goalie-streaming">
              <div className="flex items-center justify-between mb-1.5">
                <div className="text-xs font-semibold uppercase tracking-wider">
                  Goalie streaming (last {goalies.days}d)
                </div>
                <span className={`text-[10px] px-2 py-0.5 rounded-full border ${
                  goalies.flagged_teams?.length > 0 ? "border-amber-500/40 text-amber-300" : "border-emerald-500/40 text-emerald-300"
                }`}>
                  {goalies.flagged_teams?.length || 0} flagged
                </span>
              </div>
              {!goalies.flagged_teams?.length ? (
                <div className="text-xs text-muted-foreground italic">No streaming patterns detected.</div>
              ) : (
                <div className="space-y-0.5 max-h-40 overflow-y-auto">
                  {goalies.flagged_teams.slice(0, 15).map((t: any) => (
                    <div key={t.team_id} className="text-xs border-l-2 border-amber-500/40 pl-2 py-0.5">
                      <span>Team {t.team_id}</span>
                      <span className="text-amber-300"> · {t.distinct_goalies_started} distinct goalies started</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </section>
  );
}

