// @ts-nocheck
/**
 * Iter 201a — Platform Admin Dashboard
 *
 * Gate: `user.role === 'admin'`. Routes:
 *   - GET    /api/admin/platform/metrics
 *   - GET    /api/admin/platform/commish-actions
 *   - POST   /api/admin/platform/commish-actions/{id}/revert
 *
 * Phase 1 ships the dashboard SHELL + Platform Health metrics tiles
 * + Commissioner Action Log (cross-league) with one-click admin revert.
 * Subsequent iterations (201b/c/d) layer in trade fairness, collusion
 * detection, lineup audits, and tanking detection panels.
 */
import { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import api from "@/lib/api";
import { toast } from "sonner";
import {
  Users, ListChecks, TrendingUp, Activity, Shield, RotateCcw, Clock, Filter,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

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
      <div className="max-w-7xl mx-auto px-4 py-8 space-y-8">
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

        {/* Metrics tiles */}
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

        {/* 14-day timeseries */}
        {metrics?.timeseries_14d?.length > 0 && (
          <section className="space-y-3">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
              14-Day Growth
            </h2>
            <Timeseries data={metrics.timeseries_14d} />
          </section>
        )}

        {/* Commish action log */}
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
      </div>
    </div>
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
