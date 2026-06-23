// @ts-nocheck
/**
 * UXAnalyticsPanel — Iter 220 admin tab consuming the 4 analytics-ux endpoints.
 * Extracted from AdminDashboard.tsx during Iter 222 refactor.
 */
import { useEffect, useState } from "react";
import { toast } from "sonner";
import api from "@/lib/api";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";

export function UXAnalyticsPanel() {
  const [pageviews, setPageviews] = useState<any>(null);
  const [adoption, setAdoption] = useState<any>(null);
  const [funnel, setFunnel] = useState<any>(null);
  const [cadence, setCadence] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const [pv, fa, of, ec] = await Promise.all([
          api.get("/analytics-ux/pageviews-summary?days=7"),
          api.get("/analytics-ux/feature-adoption?days=30"),
          api.get("/analytics-ux/onboarding-funnel?days=60"),
          api.get("/analytics-ux/engagement-cadence?days=30"),
        ]);
        setPageviews(pv.data); setAdoption(fa.data); setFunnel(of.data); setCadence(ec.data);
      } catch (e: any) {
        toast.error(e?.response?.data?.detail || "Failed to load UX analytics");
      } finally { setLoading(false); }
    })();
  }, []);

  if (loading) return <p className="text-sm text-muted-foreground">Loading UX analytics…</p>;

  return (
    <section className="space-y-4" data-testid="ux-analytics-panel">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card data-testid="ux-pageviews-card">
          <CardHeader>
            <CardTitle className="text-base">Pageviews · last 7 days</CardTitle>
            <CardDescription>
              {pageviews?.total_views?.toLocaleString() || 0} total views · top + bottom paths
            </CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-[11px] uppercase tracking-wider text-muted-foreground mb-1">Top paths</p>
            <ul className="space-y-1 text-xs mb-3">
              {(pageviews?.top_paths || []).slice(0, 10).map((r: any) => (
                <li key={r.path} className="flex items-center justify-between gap-3">
                  <code className="truncate flex-1">{r.path}</code>
                  <span className="text-muted-foreground tabular-nums">{r.views}</span>
                  <span className="text-muted-foreground text-[10px]">({r.unique_users} u)</span>
                </li>
              ))}
            </ul>
            {(pageviews?.least_paths?.length || 0) > 0 && (
              <>
                <p className="text-[11px] uppercase tracking-wider text-muted-foreground mb-1">Least visited</p>
                <ul className="space-y-1 text-xs">
                  {pageviews.least_paths.slice(0, 5).map((r: any) => (
                    <li key={r.path} className="flex items-center justify-between gap-3">
                      <code className="truncate flex-1 text-amber-300/80">{r.path}</code>
                      <span className="text-muted-foreground tabular-nums">{r.views}</span>
                    </li>
                  ))}
                </ul>
              </>
            )}
          </CardContent>
        </Card>

        <Card data-testid="ux-cadence-card">
          <CardHeader>
            <CardTitle className="text-base">Engagement cadence · 30 d</CardTitle>
            <CardDescription>Median session pattern across active users</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-3 gap-3">
              <UxMetric label="Active users" value={cadence?.active_user_count} />
              <UxMetric label="Sessions / user / wk" value={cadence?.median_sessions_per_user_per_week} />
              <UxMetric label="Median session" value={cadence?.median_session_length_seconds
                ? `${Math.round(cadence.median_session_length_seconds)}s` : "—"} />
            </div>
            {(pageviews?.dau_series?.length || 0) > 0 && (
              <div className="mt-4">
                <p className="text-[11px] uppercase tracking-wider text-muted-foreground mb-1">DAU · last 7 days</p>
                <ul className="grid grid-cols-7 gap-1.5">
                  {pageviews.dau_series.slice(-7).map((d: any) => (
                    <li key={d.day} className="text-center">
                      <div className="h-12 bg-primary/20 border border-primary/40 rounded flex items-end justify-center pb-0.5"
                           style={{ opacity: Math.max(0.3, Math.min(1, d.dau / 20)) }}>
                        <span className="text-[10px] font-mono">{d.dau}</span>
                      </div>
                      <span className="text-[9px] text-muted-foreground">{d.day.slice(5)}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      <Card data-testid="ux-funnel-card">
        <CardHeader>
          <CardTitle className="text-base">Onboarding funnel · last {funnel?.window_days || 60} days</CardTitle>
          <CardDescription>{funnel?.total_new_users || 0} new users · drop-off by stage</CardDescription>
        </CardHeader>
        <CardContent>
          <ul className="space-y-2" data-testid="ux-funnel-stages">
            {(funnel?.stages || []).map((s: any, i: number) => {
              const prevPct = i === 0 ? 100 : (funnel.stages[i - 1]?.pct_of_total || 100);
              const drop = Math.max(0, prevPct - s.pct_of_total);
              return (
                <li key={s.stage} className="space-y-1">
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-foreground/90 capitalize">{s.stage.replace(/_/g, " ")}</span>
                    <span className="tabular-nums">
                      <strong>{s.users}</strong> ({s.pct_of_total}%)
                      {drop > 0 && i > 0 && <span className="ml-2 text-rose-300/80">−{drop.toFixed(1)}%</span>}
                    </span>
                  </div>
                  <div className="h-2 bg-secondary/40 rounded-full overflow-hidden">
                    <div className="h-full bg-gradient-to-r from-primary to-primary/60"
                         style={{ width: `${s.pct_of_total}%` }} />
                  </div>
                </li>
              );
            })}
          </ul>
        </CardContent>
      </Card>

      <Card data-testid="ux-adoption-card">
        <CardHeader>
          <CardTitle className="text-base">Feature adoption · last {adoption?.window_days || 30} days</CardTitle>
          <CardDescription>{adoption?.total_users || 0} non-admin users · discovered → used → returned</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="rounded border border-border overflow-hidden">
            <table className="w-full text-xs">
              <thead className="bg-secondary/40">
                <tr className="text-left">
                  <th className="px-2 py-1.5">Feature</th>
                  <th className="px-2 py-1.5 text-right">Discovered</th>
                  <th className="px-2 py-1.5 text-right">Used</th>
                  <th className="px-2 py-1.5 text-right">Returned (≥2x)</th>
                  <th className="px-2 py-1.5 text-right">Adoption</th>
                </tr>
              </thead>
              <tbody>
                {(adoption?.features || []).map((f: any) => (
                  <tr key={f.feature} className="border-t border-border/40">
                    <td className="px-2 py-1.5 font-mono">{f.feature}</td>
                    <td className="px-2 py-1.5 text-right tabular-nums">{f.discovered} <span className="text-muted-foreground">({f.discovered_pct}%)</span></td>
                    <td className="px-2 py-1.5 text-right tabular-nums">{f.used} <span className="text-muted-foreground">({f.used_pct}%)</span></td>
                    <td className="px-2 py-1.5 text-right tabular-nums">{f.returned}</td>
                    <td className="px-2 py-1.5 text-right">
                      <span className={`tabular-nums ${
                        f.used_pct > 30 ? "text-emerald-300" :
                        f.used_pct > 10 ? "text-amber-300" : "text-rose-300"
                      }`}>{f.used_pct}%</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </section>
  );
}

function UxMetric({ label, value }: any) {
  return (
    <div className="rounded-lg border border-border bg-background/40 px-3 py-2.5">
      <p className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</p>
      <p className="text-xl font-bold mt-1 tabular-nums">{value ?? 0}</p>
    </div>
  );
}
