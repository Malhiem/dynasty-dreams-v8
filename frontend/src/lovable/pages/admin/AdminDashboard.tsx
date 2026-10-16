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
import "./admin-dashboard.css";
import { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import api from "@/lib/api";
import { toast } from "sonner";
import {
  Users, ListChecks, TrendingUp, Activity, Shield, RotateCcw, Clock, Filter,
  ArrowLeftRight, AlertTriangle, UserX, Monitor, BarChart3, Heart, ScrollText,
  Headphones, ServerCog, DollarSign, Goal, Wrench, Flag, MessageSquare, Gavel,
  User, Archive, Home, ShieldCheck, Sparkles, FlaskConical, Database,
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
// Iter 222 / 223 / 224 — Admin sub-components extracted out of this file.
import { AdminActionsPanel } from "./components/AdminActionsPanel";
import { UserExtensionsSection } from "./components/UserExtensionsSection";
import { UXAnalyticsPanel } from "./components/UXAnalyticsPanel";
import { SyncMonitorPanel } from "./components/SyncMonitorPanel";
import { PlatformAnalyticsPanel } from "./components/PlatformAnalyticsPanel";
import { UsersPanel } from "./components/UsersPanel";
import { UserDetailDrawer } from "./components/UserDetailDrawer";
import { CommishActions } from "./components/CommishActions";
import PlatformCommissionerActivityPanel from "./components/PlatformCommissionerActivityPanel";
import { TradesPanel } from "./components/TradesPanel";
import { CollusionPanel } from "./components/CollusionPanel";
import { TankingPanel } from "./components/TankingPanel";
import { LineupAuditPanel } from "./components/LineupAuditPanel";
import { UserReportsPanel } from "./components/UserReportsPanel";
import { ModerationQueuePanel } from "./components/ModerationQueuePanel";
import { KeywordFiltersPanel } from "./components/KeywordFiltersPanel";
import { AccountIntegrityPanel } from "./components/AccountIntegrityPanel";
import { AppealsPanel } from "./components/AppealsPanel";
import { LeagueHealthPanel } from "./components/LeagueHealthPanel";
import { SupportMetricsPanel } from "./components/SupportMetricsPanel";
import { ServerOpsPanel } from "./components/ServerOpsPanel";
import { RecentAdminActionsFeed } from "./components/RecentAdminActionsFeed";
// Iter 228e — Archived drafts + Player verification panels
import ArchivedDraftsPanel from "./components/ArchivedDraftsPanel";
import PlayerVerifyPanel from "./components/PlayerVerifyPanel";
// Iter 230m — Security threat-model + audit conventions reference.
import SecurityDocPanel from "./components/SecurityDocPanel";
// Iter 230n — Security audit history widget (compliance cadence view).
import SecurityAuditHistory from "./components/SecurityAuditHistory";
// Iter 231ag — Database hygiene one-click pollution sweep.
import DbHygienePanel from "./components/DbHygienePanel";
import RecentCrashesPanel from "./components/RecentCrashesPanel";
// Iter 232N.56 — Metric Explorer for the generic daily-rollup framework
import MetricExplorerPanel from "./components/MetricExplorerPanel";
// Iter 232N.57 — "What needs attention today?" anomaly feed
import AttentionFeedPanel from "./components/AttentionFeedPanel";
// Iter 232N.59 — Admin Test Sandbox (throwaway leagues + user impersonation)
import TestSandboxPanel from "./components/TestSandboxPanel";
// Iter 232N.64 — Admin Player DB (full CRUD + audit + refresh)
import PlayerDbPanel from "./components/PlayerDbPanel";
export { ModNotesPanel } from "./components/ModNotesPanel";
import { DetailGrid, DetailRow, StatusPill, SyncStat } from "./components/_shared";

export default function AdminDashboard() {
  const { user, loading: authLoading } = useAuth();
  const navigate = useNavigate();
  const [wideNavigation, setWideNavigation] = useState(() => window.matchMedia("(min-width: 1024px)").matches);
  useEffect(() => {
    const media = window.matchMedia("(min-width: 1024px)");
    const update = () => setWideNavigation(media.matches);
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);
  const [metrics, setMetrics] = useState(null);
  const [actions, setActions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState({ event_type: "", league_id: "", user_id: "" });
  const [reverting, setReverting] = useState(null);

  // ── Auth gate
  useEffect(() => {
    if (!authLoading && user && user.role !== "admin") {
      // Iter 232N.59 — Don't spam the "Platform admin access required"
      // toast when the admin is impersonating a test user. The redirect
      // to /dashboard is still correct behaviour; just skip the toast.
      if (!user._impersonation_mode) {
        toast.error("Platform admin access required");
      }
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
    <div className="admin-dashboard min-h-screen bg-background text-foreground" data-testid="admin-dashboard-page">
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
          {/* Iter 228g — Return to user dashboard view (admins can otherwise
                get stuck on the platform-admin page with no obvious way back). */}
          <Button
            variant="default" size="sm"
            onClick={() => navigate("/dashboard")}
            data-testid="admin-back-to-user-dashboard"
            className="gap-1.5"
          >
            <Home className="h-4 w-4" />
            User Dashboard
          </Button>
        </div>

        {/* Iter 210 — Real-time critical alerts (Sync + Server Ops + Dead Leagues) */}
        <CriticalAlertBanner />

        <Tabs defaultValue="overview" orientation={wideNavigation ? "vertical" : "horizontal"} className="flex flex-col lg:flex-row gap-6 min-w-0" data-testid="admin-tabs-root">
          {/* Vertical sidebar nav */}
          <TabsList
            className="flex flex-row lg:flex-col justify-start items-center lg:items-stretch h-auto bg-secondary/20 p-2 rounded-lg shrink-0 w-full lg:w-56 lg:sticky lg:top-4 self-start gap-1 overflow-x-auto"
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
            <SidebarTab value="security" icon={ShieldCheck} label="Security" testid="admin-tab-security" />
            <SidebarTab value="analytics" icon={BarChart3} label="Analytics" testid="admin-tab-analytics" />
            <SidebarTab value="ux-analytics" icon={Activity} label="UX Analytics" testid="admin-tab-ux-analytics" />
            <SidebarTab value="archived-drafts" icon={Archive} label="Archived Drafts" testid="admin-tab-archived-drafts" />
            <SidebarTab value="players" icon={Users} label="Player Verify" testid="admin-tab-player-verify" />
            <SidebarTab value="db-hygiene" icon={ShieldCheck} label="DB Hygiene" testid="admin-tab-db-hygiene" />
            <SidebarTab value="crashes" icon={AlertTriangle} label="Recent Crashes" testid="admin-tab-crashes" />
            <SidebarTab value="metric-explorer" icon={Sparkles} label="Metric Explorer" testid="admin-tab-metric-explorer" />
            <SidebarTab value="test-sandbox" icon={FlaskConical} label="Test Sandbox" testid="admin-tab-test-sandbox" />
            <SidebarTab value="player-db" icon={Database} label="Player DB" testid="admin-tab-player-db" />
          </TabsList>

          {/* Right content pane */}
          <div className="admin-content flex-1 min-w-0 w-full">

          {/* ─── Overview tab ─── */}
          <TabsContent value="overview" className="space-y-6 mt-0">
            {/* Iter 232N.57 — Compact 'what needs attention today?'
                anomaly summary at the very top of Overview so admins
                catch outages / spikes before anything else. */}
            <AttentionFeedPanel compact />
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
            {/* Iter 232N.53 — Platform-wide commissioner activity feed
                surfaces cross-league override patterns above the
                existing per-action list so problem leagues + hot
                commissioners are the first thing an admin sees. */}
            <PlatformCommissionerActivityPanel />
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

          {/* ─── Security (Iter 230m) — repo SECURITY.md rendered live ─── */}
          <TabsContent value="security" className="space-y-3 mt-0">
            <SecurityAuditHistory />
            <SecurityDocPanel />
          </TabsContent>

          {/* ─── Platform Analytics (Iter 211) ─── */}
          <TabsContent value="analytics" className="space-y-3 mt-0">
            <PlatformAnalyticsPanel />
          </TabsContent>

          {/* ─── Users (Iter 214) ─── */}
          <TabsContent value="users" className="space-y-3 mt-0">
            <UsersPanel />
          </TabsContent>

          {/* ─── UX Analytics (Iter 220) ─── */}
          <TabsContent value="ux-analytics" className="space-y-3 mt-0">
            <UXAnalyticsPanel />
          </TabsContent>

          {/* ─── Iter 228e — Archived Drafts ─── */}
          <TabsContent value="archived-drafts" className="space-y-3 mt-0">
            <ArchivedDraftsPanel />
          </TabsContent>

          {/* ─── Iter 228e — Player Verification ─── */}
          <TabsContent value="players" className="space-y-3 mt-0">
            <PlayerVerifyPanel />
          </TabsContent>

          {/* ─── Iter 231ag — DB Hygiene one-click pollution sweep ─── */}
          <TabsContent value="db-hygiene" className="space-y-3 mt-0">
            <DbHygienePanel />
          </TabsContent>

          {/* ─── Iter 231ar — Recent Crashes triage ─── */}
          <TabsContent value="crashes" className="space-y-3 mt-0">
            <RecentCrashesPanel />
          </TabsContent>

          {/* ─── Iter 232N.56 — Metric Explorer ─── */}
          <TabsContent value="metric-explorer" className="space-y-3 mt-0">
            {/* Iter 232N.57 — Full 'what needs attention today?' feed
                sits above the explorer so anomalies drive drill-down. */}
            <AttentionFeedPanel />
            <MetricExplorerPanel />
          </TabsContent>

          {/* ─── Iter 232N.59 — Admin Test Sandbox ─── */}
          <TabsContent value="test-sandbox" className="space-y-3 mt-0">
            <TestSandboxPanel />
          </TabsContent>

          {/* ─── Iter 232N.64 — Admin Player DB ─── */}
          <TabsContent value="player-db" className="space-y-3 mt-0">
            <PlayerDbPanel />
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
      className="justify-start gap-2 px-3 py-2 text-sm h-9 w-auto lg:w-full shrink-0 data-[state=active]:bg-primary/15 data-[state=active]:text-primary data-[state=active]:border-l-2 data-[state=active]:border-primary rounded-md text-left text-muted-foreground hover:text-foreground hover:bg-secondary/40 transition-colors"
    >
      <Icon className="h-4 w-4 shrink-0" />
      <span className="truncate">{label}</span>
    </TabsTrigger>
  );
}

/* ─── CommishActions: extracted from inline so the dashboard can tab ─── */
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
