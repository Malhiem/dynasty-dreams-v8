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

        <Tabs defaultValue="overview" className="space-y-6">
          <TabsList className="bg-secondary/30">
            <TabsTrigger value="overview" data-testid="admin-tab-overview">Overview</TabsTrigger>
            <TabsTrigger value="commish" data-testid="admin-tab-commish">Commish Actions</TabsTrigger>
            <TabsTrigger value="trades" data-testid="admin-tab-trades">Trade Review</TabsTrigger>
            <TabsTrigger value="collusion" data-testid="admin-tab-collusion">Collusion</TabsTrigger>
            <TabsTrigger value="tanking" data-testid="admin-tab-tanking">Tanking</TabsTrigger>
            <TabsTrigger value="lineup" data-testid="admin-tab-lineup">Lineup Audit</TabsTrigger>
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
