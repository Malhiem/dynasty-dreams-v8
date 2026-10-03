// @ts-nocheck
/**
 * PlatformAnalyticsPanel — Iter 211/212 DAU/MAU + retention + revenue + hockey insights.
 * Extracted from AdminDashboard.tsx during Iter 223 refactor.
 */
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { SyncStat } from "./_shared";

export function PlatformAnalyticsPanel() {
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
