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
  ArrowLeftRight, AlertTriangle, UserX, Monitor, BarChart3, Heart, ScrollText,
  Headphones, ServerCog, DollarSign, Goal, Wrench, Flag, MessageSquare, Gavel,
  User,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
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

        <Tabs defaultValue="overview" orientation="vertical" className="flex gap-6" data-testid="admin-tabs-root">
          {/* Vertical sidebar nav */}
          <TabsList
            className="flex flex-col items-stretch h-auto bg-secondary/20 p-2 rounded-lg shrink-0 w-56 sticky top-4 self-start gap-1"
            data-testid="admin-sidebar-nav"
          >
            <SidebarTab value="overview" icon={BarChart3} label="Overview" testid="admin-tab-overview" />
            <SidebarTab value="users" icon={User} label="Users" testid="admin-tab-users" />
            <SidebarTab value="commish" icon={Gavel} label="Commish Actions" testid="admin-tab-commish" />
            <SidebarTab value="trades" icon={ArrowLeftRight} label="Trade Review" testid="admin-tab-trades" />
            <SidebarTab value="collusion" icon={AlertTriangle} label="Collusion" testid="admin-tab-collusion" />
            <SidebarTab value="tanking" icon={TrendingUp} label="Tanking" testid="admin-tab-tanking" />
            <SidebarTab value="lineup" icon={ListChecks} label="Lineup Audit" testid="admin-tab-lineup" />
            <SidebarTab value="reports" icon={Flag} label="User Reports" testid="admin-tab-reports" />
            <SidebarTab value="moderation" icon={MessageSquare} label="Moderation" testid="admin-tab-moderation" />
            <SidebarTab value="integrity" icon={UserX} label="Account Integrity" testid="admin-tab-integrity" />
            <SidebarTab value="appeals" icon={Shield} label="Appeals" testid="admin-tab-appeals" />
            <SidebarTab value="health" icon={Heart} label="League Health" testid="admin-tab-health" />
            <SidebarTab value="sync" icon={Activity} label="Sync Monitor" testid="admin-tab-sync" />
            <SidebarTab value="support" icon={Headphones} label="Support" testid="admin-tab-support" />
            <SidebarTab value="ops" icon={ServerCog} label="Server Ops" testid="admin-tab-ops" />
            <SidebarTab value="analytics" icon={BarChart3} label="Analytics" testid="admin-tab-analytics" />
          </TabsList>

          {/* Right content pane */}
          <div className="flex-1 min-w-0">

          {/* ─── Overview tab ─── */}
          <TabsContent value="overview" className="space-y-6 mt-0">
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
            {/* Iter 216 — Recent admin actions feed */}
            <RecentAdminActionsFeed />
          </TabsContent>

          {/* ─── Commish tab ─── */}
          <TabsContent value="commish" className="space-y-3 mt-0">
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
          <TabsContent value="trades" className="space-y-3 mt-0">
            <TradesPanel />
          </TabsContent>

          {/* ─── Collusion (201c) ─── */}
          <TabsContent value="collusion" className="space-y-3 mt-0">
            <CollusionPanel />
          </TabsContent>

          {/* ─── Tanking (201c) ─── */}
          <TabsContent value="tanking" className="space-y-3 mt-0">
            <TankingPanel />
          </TabsContent>

          {/* ─── Lineup Audit (201d) ─── */}
          <TabsContent value="lineup" className="space-y-3 mt-0">
            <LineupAuditPanel />
          </TabsContent>

          {/* ─── User Reports (Iter 205 — Content Moderation Phase 1) ─── */}
          <TabsContent value="reports" className="space-y-3 mt-0">
            <UserReportsPanel />
          </TabsContent>

          {/* ─── Moderation Queue + Keyword filters (Iter 206 — Phase 2/3) ─── */}
          <TabsContent value="moderation" className="space-y-3 mt-0">
            <ModerationQueuePanel />
            <KeywordFiltersPanel />
          </TabsContent>

          {/* ─── Account Integrity (Iter 206) ─── */}
          <TabsContent value="integrity" className="space-y-3 mt-0">
            <AccountIntegrityPanel />
          </TabsContent>

          {/* ─── Appeals (Iter 206) ─── */}
          <TabsContent value="appeals" className="space-y-3 mt-0">
            <AppealsPanel />
          </TabsContent>

          {/* ─── League Health (Iter 209) ─── */}
          <TabsContent value="health" className="space-y-3 mt-0">
            <LeagueHealthPanel />
          </TabsContent>

          {/* ─── Sync Monitor (Iter 209) ─── */}
          <TabsContent value="sync" className="space-y-3 mt-0">
            <SyncMonitorPanel />
          </TabsContent>

          {/* ─── Support Metrics (Iter 209) ─── */}
          <TabsContent value="support" className="space-y-3 mt-0">
            <SupportMetricsPanel />
          </TabsContent>

          {/* ─── Server Ops (Iter 209) ─── */}
          <TabsContent value="ops" className="space-y-3 mt-0">
            <ServerOpsPanel />
          </TabsContent>

          {/* ─── Platform Analytics (Iter 211) ─── */}
          <TabsContent value="analytics" className="space-y-3 mt-0">
            <PlatformAnalyticsPanel />
          </TabsContent>

          {/* ─── Users (Iter 214) ─── */}
          <TabsContent value="users" className="space-y-3 mt-0">
            <UsersPanel />
          </TabsContent>
          </div>
        </Tabs>
      </div>
    </div>
  );
}

/* ─── SidebarTab — vertical nav button shared by every Tab (Iter 214) ─── */
function SidebarTab({ value, icon: Icon, label, testid }) {
  return (
    <TabsTrigger
      value={value}
      data-testid={testid}
      className="justify-start gap-2 px-3 py-2 text-sm h-9 w-full data-[state=active]:bg-primary/15 data-[state=active]:text-primary data-[state=active]:border-l-2 data-[state=active]:border-primary rounded-md text-left text-muted-foreground hover:text-foreground hover:bg-secondary/40 transition-colors"
    >
      <Icon className="h-4 w-4 shrink-0" />
      <span className="truncate">{label}</span>
    </TabsTrigger>
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


/* ──────────────────────────────────────────────────────────────────
 * Iter 214 — UsersPanel: admin directory + per-user drilldown
 * ────────────────────────────────────────────────────────────────── */
function UsersPanel() {
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [skip, setSkip] = useState(0);
  const limit = 25;
  const [selected, setSelected] = useState(null);
  const [selectedDetail, setSelectedDetail] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const q = new URLSearchParams();
      if (query.trim()) q.set("q", query.trim());
      if (statusFilter) q.set("status", statusFilter);
      q.set("limit", String(limit));
      q.set("skip", String(skip));
      const { data } = await api.get(`/admin/platform/users?${q.toString()}`);
      setRows(data.users || []);
      setTotal(data.total || 0);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to load users");
    } finally {
      setLoading(false);
    }
  }, [query, statusFilter, skip]);

  useEffect(() => { load(); }, [load]);

  const openDetail = async (userId) => {
    setSelected(userId);
    setSelectedDetail(null);
    setDetailLoading(true);
    try {
      const { data } = await api.get(`/admin/platform/users/${userId}`);
      setSelectedDetail(data);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to load user details");
    } finally {
      setDetailLoading(false);
    }
  };

  const closeDetail = () => { setSelected(null); setSelectedDetail(null); };

  return (
    <section className="space-y-4" data-testid="users-section">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
          Users <span className="text-foreground/70">· {total.toLocaleString()} total</span>
        </h2>
        <div className="flex items-center gap-2 flex-wrap">
          <Input
            placeholder="Search email or username"
            value={query}
            onChange={(e) => { setQuery(e.target.value); setSkip(0); }}
            className="h-8 w-[240px] text-xs"
            data-testid="users-search-input"
          />
          <Select
            value={statusFilter || "_all"}
            onValueChange={(v) => { setStatusFilter(v === "_all" ? "" : v); setSkip(0); }}
          >
            <SelectTrigger className="h-8 w-[160px] text-xs" data-testid="users-status-filter">
              <SelectValue placeholder="All statuses" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="_all">All statuses</SelectItem>
              <SelectItem value="active">Active</SelectItem>
              <SelectItem value="suspended">Suspended</SelectItem>
              <SelectItem value="banned">Banned</SelectItem>
              <SelectItem value="deactivated">Deactivated</SelectItem>
              <SelectItem value="pending_verification">Pending verification</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className="rounded-lg border border-border overflow-x-auto">
        <table className="w-full text-sm min-w-[860px]" data-testid="users-table">
          <thead className="bg-secondary/40">
            <tr className="text-left">
              <th className="px-3 py-2 text-xs font-semibold text-muted-foreground">User</th>
              <th className="px-3 py-2 text-xs font-semibold text-muted-foreground">Email</th>
              <th className="px-3 py-2 text-xs font-semibold text-muted-foreground">Role</th>
              <th className="px-3 py-2 text-xs font-semibold text-muted-foreground">Status</th>
              <th className="px-3 py-2 text-xs font-semibold text-muted-foreground">Created</th>
              <th className="px-3 py-2 text-xs font-semibold text-muted-foreground">Last login</th>
              <th className="px-3 py-2 text-xs font-semibold text-muted-foreground">2FA</th>
              <th className="px-3 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr><td colSpan={8} className="px-3 py-6 text-center text-xs text-muted-foreground">Loading…</td></tr>
            )}
            {!loading && rows.length === 0 && (
              <tr><td colSpan={8} className="px-3 py-6 text-center text-xs text-muted-foreground">No users match</td></tr>
            )}
            {!loading && rows.map((u) => (
              <tr key={u.id} className="border-t border-border/60 hover:bg-secondary/20" data-testid={`users-row-${u.id}`}>
                <td className="px-3 py-2 font-medium">{u.username || u.name || "—"}</td>
                <td className="px-3 py-2 text-muted-foreground max-w-[240px] truncate" title={u.email}>
                  {u.email}
                  {u.email_verified && <span className="ml-1 text-[10px] text-emerald-300">✓</span>}
                </td>
                <td className="px-3 py-2">
                  <span className={`text-[10px] px-1.5 py-0.5 rounded-full border ${
                    u.role === "admin" ? "border-rose-500/40 text-rose-300" : "border-border text-muted-foreground"
                  }`}>{u.role}</span>
                </td>
                <td className="px-3 py-2">
                  <StatusPill status={u.status} />
                </td>
                <td className="px-3 py-2 text-xs text-muted-foreground whitespace-nowrap">
                  {u.created_at ? new Date(u.created_at).toLocaleDateString() : "—"}
                </td>
                <td className="px-3 py-2 text-xs text-muted-foreground whitespace-nowrap">
                  {u.last_login_at ? new Date(u.last_login_at).toLocaleString() : "—"}
                </td>
                <td className="px-3 py-2 text-xs">
                  {u.two_factor_enabled ? <span className="text-emerald-300">ON</span> : <span className="text-muted-foreground">off</span>}
                </td>
                <td className="px-3 py-2 text-right">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => openDetail(u.id)}
                    data-testid={`users-view-${u.id}`}
                  >
                    View
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span>Showing {rows.length ? skip + 1 : 0}–{skip + rows.length} of {total.toLocaleString()}</span>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            disabled={skip === 0 || loading}
            onClick={() => setSkip(Math.max(0, skip - limit))}
            data-testid="users-prev-btn"
          >Prev</Button>
          <Button
            variant="outline"
            size="sm"
            disabled={skip + limit >= total || loading}
            onClick={() => setSkip(skip + limit)}
            data-testid="users-next-btn"
          >Next</Button>
        </div>
      </div>

      {/* ── User detail drawer ── */}
      {selected && (
        <UserDetailDrawer
          loading={detailLoading}
          detail={selectedDetail}
          onClose={closeDetail}
          onRefresh={() => openDetail(selected)}
          onRowsRefresh={load}
        />
      )}
    </section>
  );
}

function StatusPill({ status }) {
  const palette: Record<string, string> = {
    active: "border-emerald-500/40 text-emerald-300",
    suspended: "border-amber-500/40 text-amber-300",
    banned: "border-rose-500/40 text-rose-300",
    deactivated: "border-muted text-muted-foreground",
    pending_verification: "border-sky-500/40 text-sky-300",
  };
  const cls = palette[status] || "border-border text-muted-foreground";
  return (
    <span className={`text-[10px] px-1.5 py-0.5 rounded-full border ${cls}`} data-testid={`user-status-${status}`}>
      {status?.replace(/_/g, " ")}
    </span>
  );
}

function UserDetailDrawer({ loading, detail, onClose, onRefresh, onRowsRefresh }) {
  return (
    <div className="fixed inset-0 z-50 bg-black/60 flex items-stretch justify-end" onClick={onClose} data-testid="user-detail-drawer">
      <div
        className="w-full max-w-[760px] bg-background border-l border-border h-full overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="p-5 border-b border-border flex items-center justify-between sticky top-0 bg-background z-10">
          <h3 className="text-base font-semibold">User detail</h3>
          <Button variant="outline" size="sm" onClick={onClose} data-testid="user-detail-close">Close</Button>
        </div>
        {loading && <div className="p-6 text-sm text-muted-foreground">Loading user…</div>}
        {!loading && detail && (
          <div className="p-5 space-y-6 text-sm">
            {/* Identity & Account Core */}
            <section className="space-y-2" data-testid="user-detail-identity">
              <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Identity & Account Core</h4>
              <DetailGrid>
                <DetailRow k="User ID" v={<code className="text-xs">{detail.id}</code>} />
                <DetailRow k="Username" v={detail.username || "—"} />
                <DetailRow k="Display name" v={detail.name || "—"} />
                <DetailRow k="Email" v={<span>{detail.email} {detail.email_verified ? <span className="text-emerald-300 text-[10px] ml-1">verified</span> : <span className="text-amber-300 text-[10px] ml-1">unverified</span>}</span>} />
                <DetailRow k="Phone" v={detail.phone ? <span>{detail.phone} {detail.phone_verified ? <span className="text-emerald-300 text-[10px] ml-1">verified</span> : <span className="text-amber-300 text-[10px] ml-1">unverified</span>}</span> : "—"} />
                <DetailRow k="Auth method" v={detail.auth_method} />
                <DetailRow k="Password set" v={detail.password_hash_present ? "yes" : "no (SSO only)"} />
                <DetailRow k="Role" v={detail.role} />
                <DetailRow k="Status" v={<StatusPill status={detail.status} />} />
                <DetailRow k="Created" v={detail.created_at ? new Date(detail.created_at).toLocaleString() : "—"} />
                {detail.ban_reason_code && <DetailRow k="Ban reason" v={`${detail.ban_reason_code}${detail.ban_reason ? ` — ${detail.ban_reason}` : ""}`} />}
                {detail.ban_expires_at && <DetailRow k="Ban expires" v={new Date(detail.ban_expires_at).toLocaleString()} />}
              </DetailGrid>
              {detail.username_change_history?.length > 0 && (
                <div className="mt-2">
                  <p className="text-xs text-muted-foreground mb-1">Name / email change history</p>
                  <ul className="space-y-1 text-xs">
                    {detail.username_change_history.map((h, i) => (
                      <li key={i} className="flex items-center gap-2">
                        <span className="text-muted-foreground">{h.ts ? new Date(h.ts).toLocaleDateString() : "—"}</span>
                        <span className="text-foreground/80">{h.event_type}:</span>
                        <code className="text-rose-300">{h.from || "∅"}</code>
                        <span>→</span>
                        <code className="text-emerald-300">{h.to || "∅"}</code>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </section>

            {/* Authentication & Security */}
            <section className="space-y-2" data-testid="user-detail-security">
              <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Authentication & Security</h4>
              <DetailGrid>
                <DetailRow k="Last login" v={detail.last_login_at ? new Date(detail.last_login_at).toLocaleString() : "—"} />
                <DetailRow k="Failed login attempts" v={String(detail.failed_login_attempts || 0)} />
                {detail.lockout_until && <DetailRow k="Locked out until" v={new Date(detail.lockout_until).toLocaleString()} />}
                <DetailRow k="2FA" v={detail.two_factor_enabled ? <span className="text-emerald-300">enabled · {detail.two_factor_method || "totp"}</span> : <span className="text-muted-foreground">disabled</span>} />
                <DetailRow k="Linked SSO" v={detail.linked_sso_accounts?.length ? detail.linked_sso_accounts.join(", ") : "—"} />
                <DetailRow k="Recovery email" v={detail.recovery_email || "—"} />
                <DetailRow k="Security questions" v={detail.security_questions_set ? "set" : "not set"} />
              </DetailGrid>

              {detail.login_history?.length > 0 && (
                <div className="mt-3">
                  <p className="text-xs text-muted-foreground mb-1">Login history (last {detail.login_history.length})</p>
                  <div className="rounded border border-border max-h-[260px] overflow-y-auto" data-testid="user-detail-login-history">
                    <table className="w-full text-xs">
                      <thead className="bg-secondary/40 sticky top-0">
                        <tr>
                          <th className="text-left px-2 py-1">When</th>
                          <th className="text-left px-2 py-1">IP</th>
                          <th className="text-left px-2 py-1">Device hash</th>
                          <th className="text-left px-2 py-1">User agent</th>
                        </tr>
                      </thead>
                      <tbody>
                        {detail.login_history.map((h, i) => (
                          <tr key={i} className="border-t border-border/40">
                            <td className="px-2 py-1 whitespace-nowrap text-muted-foreground">{h.ts ? new Date(h.ts).toLocaleString() : "—"}</td>
                            <td className="px-2 py-1 font-mono">{h.ip || "—"}</td>
                            <td className="px-2 py-1 font-mono">{h.device_hash ? h.device_hash.slice(0, 12) + "…" : "—"}</td>
                            <td className="px-2 py-1 truncate max-w-[220px]" title={h.user_agent || ""}>{h.user_agent || "—"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {detail.password_reset_history?.length > 0 && (
                <div className="mt-3">
                  <p className="text-xs text-muted-foreground mb-1">Password reset history</p>
                  <ul className="space-y-1 text-xs">
                    {detail.password_reset_history.map((p, i) => (
                      <li key={i} className="flex items-center gap-2">
                        <span className="text-muted-foreground">{p.ts ? new Date(p.ts).toLocaleString() : "—"}</span>
                        <code>{p.ip || "—"}</code>
                        <span className={p.outcome === "success" ? "text-emerald-300" : "text-amber-300"}>{p.outcome || "—"}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {detail.active_sessions?.length > 0 && (
                <div className="mt-3">
                  <p className="text-xs text-muted-foreground mb-1">Active sessions</p>
                  <ul className="space-y-1 text-xs">
                    {detail.active_sessions.map((s) => (
                      <li key={s.session_id} className="flex items-center gap-2">
                        <code className="text-muted-foreground">{s.session_id.slice(-8)}</code>
                        <span>issued {s.issued_at ? new Date(s.issued_at).toLocaleString() : "—"}</span>
                        {s.ip && <code>{s.ip}</code>}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </section>

            {/* ── Iter 215 — Admin Actions ── */}
            <AdminActionsPanel
              userId={detail.id}
              userEmail={detail.email}
              userStatus={detail.status}
              permissionTier={detail.permission_tier}
              refresh={() => { onRefresh?.(); onRowsRefresh?.(); }}
            />

            {/* ── Iter 216 — Extended sections ── */}
            <UserExtensionsSection detail={detail} />

            {/* ── Iter 215 — Action history (audit trail for this user) ── */}
            <AdminActionHistorySection userId={detail.id} />
          </div>
        )}
      </div>
    </div>
  );
}

function DetailGrid({ children }) {
  return <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-1.5">{children}</div>;
}

function DetailRow({ k, v }) {
  return (
    <div className="flex items-baseline gap-2 text-sm">
      <span className="text-xs text-muted-foreground min-w-[100px]">{k}</span>
      <span className="flex-1 break-all">{v}</span>
    </div>
  );
}


/* ─── Iter 215c — Admin Actions panel (config-driven dialogs) ────── */
const REASON_CODES = [
  { value: "harassment", label: "Harassment" },
  { value: "fraud", label: "Fraud" },
  { value: "cheating", label: "Cheating" },
  { value: "collusion", label: "Collusion" },
  { value: "spam", label: "Spam" },
  { value: "other", label: "Other" },
];

const ACTION_CONFIGS = {
  suspend: {
    title: "Suspend account", tone: "warn", path: "/suspend",
    description: "Temporary suspension. Auto-expires after duration.",
    fields: [
      { name: "duration_days", label: "Duration (days)", type: "number", required: true, default: 7 },
      { name: "reason_code", label: "Reason code", type: "select", options: REASON_CODES, default: "other" },
      { name: "reason", label: "Reason (visible to user)", type: "textarea", required: true },
    ],
    success: "User suspended",
  },
  ban_permanent: {
    title: "Permanent ban", tone: "danger", path: "/ban-permanent",
    description: "Irreversible. Senior-admin only. We strongly recommend a second-admin sign-off.",
    requireConfirm: true,
    fields: [
      { name: "reason_code", label: "Reason code", type: "select", options: REASON_CODES, default: "other" },
      { name: "reason", label: "Reason (visible to user)", type: "textarea", required: true },
      { name: "second_signoff_admin_email", label: "Second admin sign-off email (recommended)", type: "text" },
    ],
    extraBody: { confirm: true },
    success: "User permanently banned",
  },
  reinstate: {
    title: "Reinstate account", tone: "success", path: "/reinstate",
    description: "Lift any active ban or suspension.",
    fields: [{ name: "note", label: "Reinstatement note (esp. for appeals)", type: "textarea", required: true }],
    success: "User reinstated",
  },
  force_logout: {
    title: "Force logout all sessions", tone: "warn", path: "/force-logout",
    description: "Revokes every active session for this user. JWT token_version is bumped.",
    fields: [], success: "All sessions revoked",
  },
  deactivate: {
    title: "Deactivate account", tone: "warn", path: "/deactivate",
    description: "Soft deactivation — account hidden, login blocked. Reversible.",
    fields: [{ name: "reason", label: "Reason", type: "textarea" }],
    success: "Account deactivated",
  },
  reactivate: {
    title: "Reactivate account", tone: "success", path: "/reactivate",
    description: "Restore a deactivated account.",
    fields: [], success: "Account reactivated",
  },
  delete: {
    title: "Hard delete (anonymise)", tone: "danger", path: "/delete",
    description: "IRREVERSIBLE. PII anonymised; rare action — usually legal/compliance only.",
    requireConfirm: true,
    fields: [{ name: "reason", label: "Reason", type: "textarea", required: true }],
    extraBody: { confirm: true },
    success: "User hard-deleted (anonymised)",
  },
  reset_password: {
    title: "Reset password", tone: "default", path: "/reset-password",
    description: "Trigger a password-reset email. Admin never sees the new password.",
    fields: [], success: "Reset email queued",
  },
  verify_email: {
    title: "Verify email", tone: "default", path: "/verify-email",
    description: "Mark the email as verified (manual override).",
    fields: [], success: "Email marked verified",
  },
  verify_phone: {
    title: "Verify phone", tone: "default", path: "/verify-phone",
    description: "Mark the phone number as verified.",
    fields: [], success: "Phone marked verified",
  },
  edit_username: {
    title: "Edit username", tone: "default", path: "/edit-username",
    description: "Override the normal change-frequency limits. Recorded in change history.",
    fields: [
      { name: "username", label: "New username", type: "text", required: true },
      { name: "reason", label: "Reason", type: "textarea" },
    ],
    success: "Username updated",
  },
  merge_accounts: {
    title: "Merge accounts", tone: "danger", path: "/merge-accounts",
    description: "STUBBED — audit-only. Source user data merged INTO this target account.",
    fields: [
      { name: "source_user_id", label: "Source user id", type: "text", required: true },
      { name: "reason", label: "Reason", type: "textarea" },
    ],
    success: "Merge queued",
  },
  unlink_sso: {
    title: "Unlink SSO provider", tone: "warn", path: "/unlink-sso",
    fields: [
      { name: "provider", label: "Provider", type: "select",
        options: [{ value: "google", label: "Google" }, { value: "apple", label: "Apple" },
                  { value: "facebook", label: "Facebook" }, { value: "github", label: "GitHub" }],
        required: true },
    ],
    success: "SSO unlinked",
  },
  permission_tier: {
    title: "Set permission tier", tone: "warn", path: "/permission-tier",
    description: "Grant or revoke admin tooling access. Requires senior_admin to perform.",
    fields: [
      { name: "tier", label: "New tier", type: "select", required: true,
        options: [
          { value: "user", label: "user (no admin access)" },
          { value: "moderator", label: "moderator (mute/warn/flag only)" },
          { value: "admin", label: "admin (most actions)" },
          { value: "senior_admin", label: "senior_admin (irreversible actions)" },
        ], default: "moderator" },
      { name: "reason", label: "Reason", type: "textarea", required: true },
    ],
    success: "Permission tier updated",
  },
  remove_from_league: {
    title: "Remove from league", tone: "warn", path: "/remove-from-league",
    fields: [
      { name: "league_id", label: "League id", type: "text", required: true },
      { name: "handover_mode", label: "Handover mode", type: "select", required: true,
        options: [{ value: "commissioner", label: "Commissioner takes over" },
                  { value: "ai", label: "AI auto-manages" },
                  { value: "pause", label: "Pause league" }] },
      { name: "reason", label: "Reason", type: "textarea" },
    ],
    success: "User removed from league",
  },
  transfer_commissioner: {
    title: "Transfer commissioner", tone: "warn", path: "/transfer-commissioner",
    fields: [
      { name: "league_id", label: "League id", type: "text", required: true },
      { name: "new_commissioner_user_id", label: "New commissioner user id", type: "text", required: true },
      { name: "reason", label: "Reason", type: "textarea" },
    ],
    success: "Commissioner transferred",
  },
  force_remove_draft: {
    title: "Force-remove from draft", tone: "warn", path: "/force-remove-from-draft",
    description: "Autopick takeover; the user is removed from active picking.",
    fields: [
      { name: "draft_id", label: "Draft id", type: "text", required: true },
      { name: "reason", label: "Reason", type: "textarea" },
    ],
    success: "Autopick takeover triggered",
  },
  reset_team: {
    title: "Reset team", tone: "danger", path: "/reset-team",
    description: "STUBBED — versioned snapshot rollback. Audit-only.",
    fields: [
      { name: "team_id", label: "Team id", type: "text", required: true },
      { name: "reason", label: "Reason", type: "textarea" },
    ],
    success: "Reset queued",
  },
  warning: {
    title: "Issue warning", tone: "warn", path: "/warning",
    description: "Tiered. 3rd warning auto-suspends 3 days. User is notified.",
    fields: [{ name: "reason", label: "Warning reason", type: "textarea", required: true }],
    success: "Warning issued",
  },
  mute: {
    title: "Mute (chat only)", tone: "warn", path: "/mute",
    description: "Restricts chat without suspending play.",
    fields: [
      { name: "duration_hours", label: "Duration (hours)", type: "number", required: true, default: 24 },
      { name: "reason", label: "Reason", type: "textarea", required: true },
    ],
    success: "User muted",
  },
  unmute: {
    title: "Unmute user", tone: "success", path: "/unmute",
    fields: [], success: "User unmuted",
  },
  flag_review: {
    title: "Flag for review", tone: "default", path: "/flag-for-review",
    description: "Adds to admin watchlist. No visible action to the user.",
    fields: [{ name: "reason", label: "Reason for watchlisting", type: "textarea", required: true }],
    success: "Added to watchlist",
  },
  unflag: {
    title: "Remove from watchlist", tone: "default", path: "/unflag",
    fields: [], success: "Removed from watchlist",
  },
  delete_content: {
    title: "Delete content", tone: "warn", path: "/delete-content",
    description: "STUBBED — delegate to existing moderation-queue flow.",
    fields: [
      { name: "content_type", label: "Content type", type: "select", required: true,
        options: [{ value: "chat_message", label: "Chat message" },
                  { value: "forum_post", label: "Forum post" },
                  { value: "team_name", label: "Team name" },
                  { value: "avatar", label: "Avatar" }] },
      { name: "content_id", label: "Content id", type: "text", required: true },
      { name: "reason", label: "Reason", type: "textarea" },
    ],
    success: "Content delete queued",
  },
  refund: {
    title: "Issue refund", tone: "warn", path: "/refund",
    description: "STUBBED — Stripe API call deferred.",
    fields: [
      { name: "amount_cents", label: "Amount (cents)", type: "number", required: true, default: 999 },
      { name: "currency", label: "Currency", type: "text", default: "usd" },
      { name: "reason", label: "Reason", type: "textarea", required: true },
      { name: "transaction_id", label: "Transaction id (optional)", type: "text" },
    ],
    success: "Refund recorded",
  },
  adjust_tier: {
    title: "Adjust subscription tier", tone: "default", path: "/adjust-tier",
    fields: [
      { name: "tier", label: "New tier", type: "select", required: true,
        options: [{ value: "free", label: "Free" }, { value: "pro", label: "Pro" },
                  { value: "commish", label: "Commish" }, { value: "premium", label: "Premium" }] },
      { name: "reason", label: "Reason", type: "textarea" },
      { name: "comp", label: "Goodwill comp?", type: "checkbox" },
    ],
    success: "Tier adjusted",
  },
  promo_credit: {
    title: "Add/remove promo credit", tone: "default", path: "/promo-credit",
    description: "Negative amount removes credit.",
    fields: [
      { name: "amount_cents", label: "Amount (cents, neg=remove)", type: "number", required: true, default: 500 },
      { name: "currency", label: "Currency", type: "text", default: "usd" },
      { name: "note", label: "Note", type: "textarea" },
    ],
    success: "Promo credit updated",
  },
  void_payout: {
    title: "Void pending payout", tone: "warn", path: "/void-payout",
    description: "STUBBED.",
    fields: [
      { name: "payout_id", label: "Payout id", type: "text", required: true },
      { name: "reason", label: "Reason", type: "textarea" },
    ],
    success: "Payout voided",
  },
  manual_payout: {
    title: "Manual payout", tone: "warn", path: "/manual-payout",
    description: "STUBBED — for edge cases where automated payout failed.",
    fields: [
      { name: "amount_cents", label: "Amount (cents)", type: "number", required: true },
      { name: "currency", label: "Currency", type: "text", default: "usd" },
      { name: "reason", label: "Reason", type: "textarea", required: true },
    ],
    success: "Manual payout queued",
  },
  impersonate: {
    title: "Impersonate (view-as)", tone: "warn", path: "/impersonate",
    description: "Issues a 15-min READ-ONLY JWT. The user is notified.",
    fields: [{ name: "reason", label: "Reason", type: "textarea", required: true }],
    success: "Read-only impersonation token issued",
  },
  resend_verification: {
    title: "Resend verification email", tone: "default", path: "/resend-verification",
    fields: [], success: "Verification email resent",
  },
  link_ticket: {
    title: "Link support ticket", tone: "default", path: "/link-support-ticket",
    fields: [
      { name: "ticket_id", label: "Ticket id", type: "text", required: true },
      { name: "ticket_url", label: "Ticket URL (optional)", type: "text" },
      { name: "note", label: "Note", type: "textarea" },
    ],
    success: "Ticket linked",
  },
  gdpr_delete: {
    title: "GDPR / CCPA delete", tone: "danger", path: "/gdpr-delete",
    description: "Right-to-be-forgotten deletion. PII anonymised; data-retention compliant.",
    requireConfirm: true,
    fields: [{ name: "reason", label: "Deletion reason", type: "textarea", required: true,
               default: "GDPR/CCPA data deletion request" }],
    extraBody: { confirm: true },
    success: "GDPR deletion executed",
  },
};

function AdminActionsPanel({ userId, userEmail, userStatus, permissionTier, refresh }) {
  const [active, setActive] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const open = (key) => setActive(key);
  const close = () => setActive(null);

  const submit = async (cfg, values) => {
    setBusy(true);
    try {
      const body = { ...(cfg.extraBody || {}), ...values };
      let res;
      if (cfg.path === "/export-data") {
        res = await api.get(`/admin/platform/users/${userId}${cfg.path}`);
        // Trigger download
        const blob = new Blob([JSON.stringify(res.data, null, 2)], { type: "application/json" });
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url; a.download = `user-data-${userId}.json`; a.click();
        window.URL.revokeObjectURL(url);
      } else {
        res = await api.post(`/admin/platform/users/${userId}${cfg.path}`, body);
      }
      const note = res.data?.mocked ? " (MOCKED)" : "";
      toast.success((cfg.success || "Action complete") + note);
      close();
      refresh?.();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Action failed");
    } finally {
      setBusy(false);
    }
  };

  const renderBtn = (k, label, tone?) => (
    <ActionBtn testid={`action-${k.replace(/_/g, "-")}`} tone={tone} onClick={() => open(k)} key={k}>
      {label}
    </ActionBtn>
  );

  return (
    <section className="space-y-3" data-testid="user-actions-panel">
      <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
        Admin Actions <span className="text-foreground/60 normal-case font-normal">· every action is logged</span>
        {permissionTier && (
          <span className="ml-2 text-[10px] px-1.5 py-0.5 rounded-full border border-border" data-testid="target-permission-tier">
            current tier: {permissionTier}
          </span>
        )}
      </h4>

      <ActionGroup label="Account Status" testid="actions-account-status">
        {renderBtn("suspend", "Suspend")}
        {renderBtn("ban_permanent", "Ban (permanent)", "danger")}
        {(userStatus === "banned" || userStatus === "suspended") && renderBtn("reinstate", "Reinstate", "success")}
        {renderBtn("force_logout", "Force logout")}
        {userStatus !== "deactivated" && renderBtn("deactivate", "Deactivate")}
        {userStatus === "deactivated" && renderBtn("reactivate", "Reactivate", "success")}
        {renderBtn("delete", "Delete", "danger")}
      </ActionGroup>

      <ActionGroup label="Identity & Access" testid="actions-identity">
        {renderBtn("reset_password", "Reset password")}
        {renderBtn("verify_email", "Verify email")}
        {renderBtn("verify_phone", "Verify phone")}
        {renderBtn("edit_username", "Edit username")}
        {renderBtn("merge_accounts", "Merge accounts")}
        {renderBtn("unlink_sso", "Unlink SSO")}
        {renderBtn("permission_tier", "Set permission tier", "warn")}
      </ActionGroup>

      <ActionGroup label="League / Team" testid="actions-league">
        {renderBtn("remove_from_league", "Remove from league")}
        {renderBtn("transfer_commissioner", "Transfer commissioner")}
        {renderBtn("force_remove_draft", "Force-remove from draft")}
        {renderBtn("reset_team", "Reset team")}
      </ActionGroup>

      <ActionGroup label="Moderation" testid="actions-moderation">
        {renderBtn("warning", "Issue warning")}
        {renderBtn("mute", "Mute")}
        {renderBtn("unmute", "Unmute")}
        {renderBtn("flag_review", "Flag for review")}
        {renderBtn("unflag", "Unflag")}
        {renderBtn("delete_content", "Delete content")}
      </ActionGroup>

      <ActionGroup label="Financial" testid="actions-financial">
        {renderBtn("refund", "Refund")}
        {renderBtn("adjust_tier", "Adjust tier")}
        {renderBtn("promo_credit", "Promo credit")}
        {renderBtn("void_payout", "Void payout")}
        {renderBtn("manual_payout", "Manual payout")}
      </ActionGroup>

      <ActionGroup label="Support" testid="actions-support">
        {renderBtn("impersonate", "Impersonate (view-as)")}
        {renderBtn("resend_verification", "Resend verification")}
        {renderBtn("link_ticket", "Link support ticket")}
        <ActionBtn testid="action-export-data" onClick={async () => {
          setBusy(true);
          try {
            const { data } = await api.get(`/admin/platform/users/${userId}/export-data`);
            const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url; a.download = `user-data-${userId}.json`; a.click();
            window.URL.revokeObjectURL(url);
            toast.success("Data export downloaded");
          } catch (e: any) {
            toast.error(e?.response?.data?.detail || "Export failed");
          } finally { setBusy(false); }
        }}>Export data (GDPR)</ActionBtn>
        {renderBtn("gdpr_delete", "GDPR delete", "danger")}
      </ActionGroup>

      {active && (
        <ActionDialog
          config={ACTION_CONFIGS[active]}
          userEmail={userEmail}
          busy={busy}
          onClose={close}
          onSubmit={(values) => submit(ACTION_CONFIGS[active], values)}
        />
      )}
    </section>
  );
}

function ActionDialog({ config, userEmail, busy, onClose, onSubmit }) {
  const [values, setValues] = useState<Record<string, any>>(() => {
    const init: any = {};
    (config.fields || []).forEach((f) => {
      init[f.name] = f.default ?? (f.type === "checkbox" ? false : "");
    });
    return init;
  });
  const [acknowledged, setAcknowledged] = useState(false);

  const update = (name, val) => setValues((prev) => ({ ...prev, [name]: val }));

  const isValid = () => {
    for (const f of config.fields || []) {
      if (f.required) {
        const v = values[f.name];
        if (v === undefined || v === null || v === "") return false;
      }
    }
    if (config.requireConfirm && !acknowledged) return false;
    return true;
  };

  const toneCls = config.tone === "danger" ? "border-rose-500/40"
    : config.tone === "warn" ? "border-amber-500/40"
    : config.tone === "success" ? "border-emerald-500/40"
    : "";

  const submitCls = config.tone === "danger" ? "bg-rose-500 hover:bg-rose-600 text-white"
    : config.tone === "warn" ? "bg-amber-500 hover:bg-amber-600 text-white"
    : "bg-primary hover:bg-primary/90 text-primary-foreground";

  return (
    <Dialog open={true} onOpenChange={(o) => { if (!o) onClose(); }}>
      <DialogContent
        className={`max-w-[520px] ${toneCls}`}
        data-testid={`action-dialog-${config.path?.replace(/^\//, "")}`}
      >
        <DialogHeader>
          <DialogTitle>{config.title}</DialogTitle>
          <DialogDescription>
            Target: <code className="text-foreground">{userEmail}</code>
            {config.description && <span className="block mt-2 text-xs">{config.description}</span>}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3 py-2">
          {(config.fields || []).map((f) => (
            <FieldRenderer
              key={f.name}
              field={f}
              value={values[f.name]}
              onChange={(v) => update(f.name, v)}
            />
          ))}
          {config.requireConfirm && (
            <label className="flex items-start gap-2 text-xs text-rose-300 mt-2 cursor-pointer" data-testid="dialog-confirm-checkbox">
              <input
                type="checkbox"
                checked={acknowledged}
                onChange={(e) => setAcknowledged(e.target.checked)}
                className="mt-0.5"
              />
              <span>I understand this action is irreversible and proceed at my own accountability.</span>
            </label>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={busy} data-testid="dialog-cancel-btn">
            Cancel
          </Button>
          <Button
            onClick={() => onSubmit(values)}
            disabled={!isValid() || busy}
            className={submitCls}
            data-testid="dialog-submit-btn"
          >
            {busy ? "Working…" : "Confirm"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function FieldRenderer({ field, value, onChange }) {
  if (field.type === "select") {
    return (
      <div className="space-y-1">
        <Label className="text-xs">{field.label}{field.required && <span className="text-rose-300 ml-0.5">*</span>}</Label>
        <Select value={value || ""} onValueChange={onChange}>
          <SelectTrigger className="h-9" data-testid={`field-${field.name}`}>
            <SelectValue placeholder={field.placeholder || `Select ${field.label.toLowerCase()}`} />
          </SelectTrigger>
          <SelectContent>
            {field.options.map((o) => (<SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>))}
          </SelectContent>
        </Select>
      </div>
    );
  }
  if (field.type === "textarea") {
    return (
      <div className="space-y-1">
        <Label className="text-xs">{field.label}{field.required && <span className="text-rose-300 ml-0.5">*</span>}</Label>
        <Textarea
          value={value || ""}
          onChange={(e) => onChange(e.target.value)}
          placeholder={field.placeholder}
          rows={3}
          data-testid={`field-${field.name}`}
        />
      </div>
    );
  }
  if (field.type === "number") {
    return (
      <div className="space-y-1">
        <Label className="text-xs">{field.label}{field.required && <span className="text-rose-300 ml-0.5">*</span>}</Label>
        <Input
          type="number"
          value={value ?? ""}
          onChange={(e) => onChange(e.target.value === "" ? "" : parseInt(e.target.value, 10))}
          data-testid={`field-${field.name}`}
        />
      </div>
    );
  }
  if (field.type === "checkbox") {
    return (
      <label className="flex items-center gap-2 text-sm cursor-pointer">
        <input type="checkbox" checked={!!value} onChange={(e) => onChange(e.target.checked)} data-testid={`field-${field.name}`} />
        <span>{field.label}</span>
      </label>
    );
  }
  return (
    <div className="space-y-1">
      <Label className="text-xs">{field.label}{field.required && <span className="text-rose-300 ml-0.5">*</span>}</Label>
      <Input
        type="text"
        value={value || ""}
        onChange={(e) => onChange(e.target.value)}
        placeholder={field.placeholder}
        data-testid={`field-${field.name}`}
      />
    </div>
  );
}

function ActionGroup({ label, testid, children }) {
  return (
    <div className="rounded-lg border border-border p-3 space-y-2" data-testid={testid}>
      <p className="text-[11px] font-semibold uppercase tracking-wider text-foreground/70">{label}</p>
      <div className="flex flex-wrap gap-2">{children}</div>
    </div>
  );
}

function ActionBtn({ children, onClick, tone = "default", testid }: any) {
  const toneCls = tone === "danger"
    ? "border-rose-500/40 text-rose-300 hover:bg-rose-500/10"
    : tone === "warn"
      ? "border-amber-500/40 text-amber-300 hover:bg-amber-500/10"
      : tone === "success"
        ? "border-emerald-500/40 text-emerald-300 hover:bg-emerald-500/10"
        : "border-border text-foreground hover:bg-secondary/40";
  return (
    <button
      type="button"
      onClick={onClick}
      className={`text-xs px-2.5 py-1.5 rounded border transition-colors ${toneCls}`}
      data-testid={testid}
    >
      {children}
    </button>
  );
}


/* ─── Iter 215 — Action history (audit trail) ──────────────────────── */
function AdminActionHistorySection({ userId }) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const { data } = await api.get(`/admin/platform/users/${userId}/admin-actions`);
        if (!cancelled) setRows(data.actions || []);
      } catch {
        // non-fatal
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [userId]);

  return (
    <section className="space-y-2" data-testid="user-action-history">
      <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
        Admin Action History · audit trail
      </h4>
      {loading && <p className="text-xs text-muted-foreground">Loading…</p>}
      {!loading && rows.length === 0 && (
        <p className="text-xs text-muted-foreground italic">No admin actions recorded for this user.</p>
      )}
      {!loading && rows.length > 0 && (
        <ul className="rounded border border-border divide-y divide-border/60 max-h-[300px] overflow-y-auto">
          {rows.map((r) => (
            <li key={r.id} className="px-3 py-2 text-xs" data-testid={`action-history-${r.action}`}>
              <div className="flex items-center justify-between gap-2">
                <span className="font-mono text-foreground/90">{r.action}</span>
                <span className="text-muted-foreground">{r.ts ? new Date(r.ts).toLocaleString() : "—"}</span>
              </div>
              <div className="text-muted-foreground mt-0.5">
                by {r.admin_email} <span className="text-[10px]">[{r.admin_tier}]</span>
                {r.mocked && <span className="ml-2 text-amber-300 text-[10px]">MOCKED</span>}
              </div>
              {r.reason && <div className="mt-1 text-foreground/80 italic">&ldquo;{r.reason}&rdquo;</div>}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}



/* ─── Iter 216 — Extended user-detail sections ────────────────────── */
function UserExtensionsSection({ detail }) {
  return (
    <>
      <ExtSection title="League & Team Relationships" testid="ext-league-team">
        <ExtSubTitle>Leagues joined · {detail.leagues_joined?.length || 0}</ExtSubTitle>
        {detail.leagues_joined?.length === 0 ? (
          <ExtEmpty>No league memberships</ExtEmpty>
        ) : (
          <ExtTable head={["League", "Role", "Status", "Joined"]}>
            {(detail.leagues_joined || []).slice(0, 15).map((l) => (
              <tr key={l.league_id} className="border-t border-border/40">
                <td className="px-2 py-1 max-w-[200px] truncate" title={l.league_name}>{l.league_name || "—"}</td>
                <td className="px-2 py-1">
                  <RoleBadge role={l.role} />
                </td>
                <td className="px-2 py-1 text-muted-foreground">{l.league_status || "—"}</td>
                <td className="px-2 py-1 text-muted-foreground whitespace-nowrap">
                  {l.joined_at ? new Date(l.joined_at).toLocaleDateString() : "—"}
                </td>
              </tr>
            ))}
          </ExtTable>
        )}
        <ExtSubTitle>Teams owned (current · {detail.teams_owned?.length || 0})</ExtSubTitle>
        {detail.teams_owned?.length === 0 ? (
          <ExtEmpty>No teams owned</ExtEmpty>
        ) : (
          <ul className="text-xs space-y-0.5">
            {(detail.teams_owned || []).slice(0, 10).map((t) => (
              <li key={t.team_id} className="flex gap-2">
                <span className="text-foreground/90 truncate max-w-[200px]">{t.team_name || "—"}</span>
                <span className="text-muted-foreground">·</span>
                <span className="text-muted-foreground truncate max-w-[200px]">{t.league_name || "—"}</span>
              </li>
            ))}
          </ul>
        )}
        {(detail.teams_owned_history?.length || 0) > 0 && (
          <>
            <ExtSubTitle>Teams owned (historical · {detail.teams_owned_history.length})</ExtSubTitle>
            <ul className="text-xs space-y-0.5 text-muted-foreground">
              {detail.teams_owned_history.slice(0, 10).map((t) => (
                <li key={t.team_id}>{t.team_name} · {t.league_name || "—"}</li>
              ))}
            </ul>
          </>
        )}
        {(detail.invitations_sent?.length || 0) + (detail.invitations_received?.length || 0) > 0 && (
          <DetailGrid>
            <DetailRow k="Invitations sent" v={`${detail.invitations_sent?.length || 0}`} />
            <DetailRow k="Invitations received" v={`${detail.invitations_received?.length || 0}`} />
          </DetailGrid>
        )}
      </ExtSection>

      <ExtSection title="Behavioral & Moderation" testid="ext-behavioral">
        <DetailGrid>
          <DetailRow k="Reports filed against user" v={`${detail.reports_against_count ?? 0}`} />
          <DetailRow k="Reports filed by user" v={`${detail.reports_filed_count ?? 0}`} />
          <DetailRow k="Trade flags" v={`${detail.trade_flags_count ?? 0}`} />
          <DetailRow k="Chat / content violations" v={`${detail.chat_violations_count ?? 0}`} />
          <DetailRow k="Trust score" v={detail.trust_score != null ? String(detail.trust_score) : "—"} />
          <DetailRow k="On watchlist" v={detail.watchlist
            ? <span className="text-amber-300">yes — {detail.watchlist_reason || "no reason"}</span>
            : "no"} />
        </DetailGrid>
        {(detail.multi_account_links?.length || 0) > 0 && (
          <>
            <ExtSubTitle>Multi-account linkage flags</ExtSubTitle>
            <ul className="text-xs space-y-0.5">
              {detail.multi_account_links.map((m, i) => (
                <li key={i} className="text-amber-300">
                  Device hash <code>{m.device_hash}</code> shared with {m.linked_user_ids.length} other account(s)
                </li>
              ))}
            </ul>
          </>
        )}
        {(detail.moderation_action_history?.length || 0) > 0 && (
          <>
            <ExtSubTitle>Moderation action history</ExtSubTitle>
            <ExtTable head={["Action", "Reason", "By", "When", "Appealed"]}>
              {detail.moderation_action_history.slice(0, 15).map((m) => (
                <tr key={m.id} className="border-t border-border/40">
                  <td className="px-2 py-1 font-mono">{m.action}</td>
                  <td className="px-2 py-1 italic text-foreground/80 max-w-[200px] truncate" title={m.reason}>{m.reason || "—"}</td>
                  <td className="px-2 py-1 text-muted-foreground truncate max-w-[160px]">{m.admin_email}</td>
                  <td className="px-2 py-1 text-muted-foreground whitespace-nowrap">{m.ts ? new Date(m.ts).toLocaleDateString() : "—"}</td>
                  <td className="px-2 py-1">{m.appealed ? <span className="text-amber-300">yes</span> : "no"}</td>
                </tr>
              ))}
            </ExtTable>
          </>
        )}
        {(detail.appeals?.length || 0) > 0 && (
          <>
            <ExtSubTitle>Appeals · {detail.appeals.length}</ExtSubTitle>
            <ul className="text-xs space-y-1">
              {detail.appeals.slice(0, 5).map((a) => (
                <li key={a.id}>
                  <span className={a.status === "approved" ? "text-emerald-300" : a.status === "denied" ? "text-rose-300" : "text-amber-300"}>
                    {a.status}
                  </span>
                  <span className="ml-2 text-muted-foreground">{a.created_at ? new Date(a.created_at).toLocaleDateString() : "—"}</span>
                </li>
              ))}
            </ul>
          </>
        )}
      </ExtSection>

      <ExtSection title="Financial / Billing" testid="ext-financial">
        <DetailGrid>
          <DetailRow k="Subscription tier" v={detail.subscription_tier} />
          <DetailRow k="Status" v={detail.subscription_status} />
          <DetailRow k="Promo credits" v={`${((detail.promo_credits_cents || 0) / 100).toFixed(2)} ${detail.payout_info?.currency || "USD"}`} />
          <DetailRow k="Chargebacks" v={detail.chargeback_flags?.length ? <span className="text-rose-300">{detail.chargeback_flags.length}</span> : "0"} />
          <DetailRow k="Payout method" v={detail.payout_info?.method || "—"} />
          <DetailRow k="Tax form" v={detail.payout_info?.tax_form_status || "—"} />
        </DetailGrid>
        {(detail.payment_methods?.length || 0) > 0 && (
          <>
            <ExtSubTitle>Payment methods on file (tokenized · PCI-safe)</ExtSubTitle>
            <ul className="text-xs space-y-0.5">
              {detail.payment_methods.map((pm) => (
                <li key={pm.id}>
                  <span className="font-mono">{pm.brand}</span> · ••••{pm.last4} · exp {pm.exp_month}/{pm.exp_year}
                </li>
              ))}
            </ul>
          </>
        )}
        {(detail.billing_history?.length || 0) > 0 && (
          <>
            <ExtSubTitle>Billing history (last {detail.billing_history.length})</ExtSubTitle>
            <ExtTable head={["When", "Amount", "Status", "Description"]}>
              {detail.billing_history.slice(0, 10).map((b) => (
                <tr key={b.id} className="border-t border-border/40">
                  <td className="px-2 py-1 text-muted-foreground whitespace-nowrap">{b.created_at ? new Date(b.created_at).toLocaleDateString() : "—"}</td>
                  <td className="px-2 py-1">{((b.amount_cents || 0) / 100).toFixed(2)} {(b.currency || "USD").toUpperCase()}</td>
                  <td className="px-2 py-1">{b.status}</td>
                  <td className="px-2 py-1 text-muted-foreground truncate max-w-[180px]">{b.description || "—"}</td>
                </tr>
              ))}
            </ExtTable>
          </>
        )}
        {(detail.league_fees?.length || 0) > 0 && (
          <>
            <ExtSubTitle>League fees · {detail.league_fees.length}</ExtSubTitle>
            <ul className="text-xs space-y-0.5">
              {detail.league_fees.slice(0, 8).map((f) => (
                <li key={f.id}>
                  {((f.amount_cents || 0) / 100).toFixed(2)} · <span className={f.status === "paid" ? "text-emerald-300" : "text-amber-300"}>{f.status}</span>
                </li>
              ))}
            </ul>
          </>
        )}
      </ExtSection>

      <ExtSection title="Support & Engagement" testid="ext-engagement">
        <DetailGrid>
          <DetailRow k="Lifetime sessions" v={`${detail.engagement?.lifetime_sessions ?? 0}`} />
          <DetailRow k="Last active" v={detail.engagement?.last_active_at
            ? new Date(detail.engagement.last_active_at).toLocaleString() : "—"} />
          <DetailRow k="Onboarding completed" v={detail.onboarding_completed
            ? <span className="text-emerald-300">yes</span>
            : <span className="text-amber-300">no</span>} />
        </DetailGrid>
        {(detail.feature_flags?.length || 0) > 0 && (
          <>
            <ExtSubTitle>Feature flags / beta access</ExtSubTitle>
            <div className="flex flex-wrap gap-1.5">
              {detail.feature_flags.map((ff) => (
                <span key={ff} className="text-[10px] px-1.5 py-0.5 rounded-full border border-border">{ff}</span>
              ))}
            </div>
          </>
        )}
        {(detail.support_tickets?.length || 0) > 0 && (
          <>
            <ExtSubTitle>Support tickets · {detail.support_tickets.length}</ExtSubTitle>
            <ul className="text-xs space-y-0.5">
              {detail.support_tickets.slice(0, 8).map((t) => (
                <li key={t.id}>
                  <code>{t.ticket_id}</code>
                  {t.ticket_url && <a href={t.ticket_url} className="text-primary ml-2 underline" target="_blank" rel="noreferrer">open</a>}
                  {t.note && <span className="text-muted-foreground ml-2 italic">— {t.note}</span>}
                </li>
              ))}
            </ul>
          </>
        )}
      </ExtSection>

      <ExtSection title="Compliance & Legal" testid="ext-compliance">
        <DetailGrid>
          <DetailRow k="Date of birth" v={detail.compliance?.date_of_birth
            ? new Date(detail.compliance.date_of_birth).toLocaleDateString() : "—"} />
          <DetailRow k="Age verified" v={detail.compliance?.age_verified
            ? <span className="text-emerald-300">yes</span>
            : <span className="text-amber-300">no</span>} />
          <DetailRow k="ToS version" v={detail.compliance?.tos_version_accepted
            ? `${detail.compliance.tos_version_accepted} · ${detail.compliance.tos_accepted_at ? new Date(detail.compliance.tos_accepted_at).toLocaleDateString() : "—"}`
            : <span className="text-amber-300">not accepted</span>} />
          <DetailRow k="Marketing emails" v={detail.compliance?.marketing_email_consent ? "yes" : "no"} />
          <DetailRow k="Region / jurisdiction" v={
            <>
              {detail.compliance?.region || "—"}
              {detail.compliance?.jurisdiction_block && (
                <span className="ml-2 text-[10px] text-rose-300 px-1.5 py-0.5 rounded-full border border-rose-500/40">
                  blocked: {detail.compliance.jurisdiction_block}
                </span>
              )}
            </>
          } />
          <DetailRow k="Data deletion requested" v={detail.compliance?.data_deletion_requested_at
            ? new Date(detail.compliance.data_deletion_requested_at).toLocaleString() : "—"} />
          {detail.compliance?.data_deletion_completed_at && (
            <DetailRow k="Data deletion completed" v={
              <span className="text-rose-300">{new Date(detail.compliance.data_deletion_completed_at).toLocaleString()}</span>
            } />
          )}
        </DetailGrid>
        {Object.keys(detail.compliance?.privacy_consents || {}).length > 0 && (
          <>
            <ExtSubTitle>Privacy consents (GDPR/CCPA)</ExtSubTitle>
            <ul className="text-xs space-y-0.5">
              {Object.entries(detail.compliance.privacy_consents).map(([k, v]: any) => (
                <li key={k}>
                  <code>{k}</code>: {v === true ? <span className="text-emerald-300">granted</span> : v === false ? <span className="text-rose-300">denied</span> : String(v)}
                </li>
              ))}
            </ul>
          </>
        )}
      </ExtSection>
    </>
  );
}

function ExtSection({ title, testid, children }) {
  return (
    <section className="space-y-2" data-testid={testid}>
      <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">{title}</h4>
      <div className="rounded-lg border border-border p-3 space-y-3">{children}</div>
    </section>
  );
}

function ExtSubTitle({ children }) {
  return <p className="text-[11px] font-semibold uppercase tracking-wider text-foreground/60 pt-2 first:pt-0">{children}</p>;
}

function ExtEmpty({ children }) {
  return <p className="text-xs text-muted-foreground italic">{children}</p>;
}

function ExtTable({ head, children }) {
  return (
    <div className="rounded border border-border max-h-[280px] overflow-y-auto">
      <table className="w-full text-xs">
        <thead className="bg-secondary/40 sticky top-0">
          <tr>
            {head.map((h) => (<th key={h} className="text-left px-2 py-1">{h}</th>))}
          </tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}

function RoleBadge({ role }) {
  const palette: Record<string, string> = {
    commissioner: "border-amber-500/40 text-amber-300",
    co_commissioner: "border-sky-500/40 text-sky-300",
    manager: "border-border text-muted-foreground",
  };
  return (
    <span className={`text-[10px] px-1.5 py-0.5 rounded-full border ${palette[role] || "border-border text-muted-foreground"}`}>
      {role?.replace(/_/g, " ")}
    </span>
  );
}


/* ─── Iter 216 — Recent admin actions feed (Overview tab) ──────────── */
function RecentAdminActionsFeed() {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const { data } = await api.get("/admin/platform/recent-admin-actions?limit=20");
        if (!cancelled) setRows(data.actions || []);
      } catch {
        // non-fatal
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  return (
    <Card className="bg-card border-border" data-testid="recent-admin-actions-feed">
      <CardHeader>
        <CardTitle className="text-base">Recent Admin Actions</CardTitle>
        <CardDescription>Latest {rows.length} actions across the platform — full audit visibility.</CardDescription>
      </CardHeader>
      <CardContent>
        {loading && <p className="text-xs text-muted-foreground">Loading…</p>}
        {!loading && rows.length === 0 && (
          <p className="text-xs text-muted-foreground italic">No admin actions recorded yet.</p>
        )}
        {!loading && rows.length > 0 && (
          <ul className="divide-y divide-border/60 max-h-[440px] overflow-y-auto">
            {rows.map((r: any) => (
              <li key={r.id} className="py-2 flex items-start gap-3 text-xs" data-testid={`recent-action-${r.action}`}>
                <span className="font-mono text-foreground/90 min-w-[160px]">{r.action}</span>
                <span className="flex-1">
                  <span className="text-muted-foreground">target:</span>{" "}
                  <span className="text-foreground/90 truncate">{r.target_email || r.target_user_id?.slice(-8)}</span>
                  {r.reason && <span className="text-muted-foreground italic"> — &ldquo;{r.reason}&rdquo;</span>}
                </span>
                <span className="text-muted-foreground whitespace-nowrap">by {r.admin_email}</span>
                <span className="text-muted-foreground whitespace-nowrap min-w-[110px] text-right">
                  {r.ts ? new Date(r.ts).toLocaleString() : "—"}
                </span>
                {r.mocked && <span className="text-amber-300 text-[10px]">MOCKED</span>}
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
