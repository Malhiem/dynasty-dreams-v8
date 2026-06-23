/**
 * Iter 218 — Personal "Your Activity" widget on the User Dashboard.
 *
 * Pulls the user's own engagement signal so they see something
 * compelling without exposing platform-wide admin analytics:
 *   • Sessions this week (estimated from pageview cadence)
 *   • Pages viewed in last 7 days
 *   • Top 3 pages by visit count
 *   • Streak (consecutive days with ≥1 pageview)
 *
 * Data source: `analytics_pageviews` filtered to current user.
 * If the user is brand-new (no pageviews yet) we render an encouraging
 * empty-state instead of a blank card.
 */
import { useEffect, useState } from "react";
import api from "@/lib/api";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { ChartLine, FireSimple, Eye, ClockCounterClockwise } from "@phosphor-icons/react";

export default function YourActivityWidget() {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const { data } = await api.get("/analytics-ux/my-activity?days=7");
        if (!cancelled) setStats(data);
      } catch {
        if (!cancelled) setStats({ total_pageviews: 0, top_paths: [], streak_days: 0, sessions_this_week: 0 });
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  return (
    <Card className="bg-card border-border" data-testid="your-activity-widget">
      <CardHeader className="pb-3">
        <CardTitle className="text-base flex items-center gap-2">
          <ChartLine size={18} weight="fill" className="text-primary" />
          Your Activity
        </CardTitle>
        <CardDescription>How you&apos;ve been engaging with the app this week.</CardDescription>
      </CardHeader>
      <CardContent>
        {loading && <p className="text-sm text-muted-foreground">Loading…</p>}
        {!loading && stats && (
          <div className="space-y-4">
            <div className="grid grid-cols-3 gap-3">
              <Stat
                icon={<Eye size={16} weight="fill" />}
                label="Pages viewed"
                value={stats.total_pageviews}
                testid="activity-pageviews"
              />
              <Stat
                icon={<ClockCounterClockwise size={16} weight="fill" />}
                label="Sessions"
                value={stats.sessions_this_week}
                testid="activity-sessions"
              />
              <Stat
                icon={<FireSimple size={16} weight="fill" className="text-amber-400" />}
                label="Day streak"
                value={stats.streak_days}
                testid="activity-streak"
              />
            </div>
            {(stats.top_paths || []).length > 0 ? (
              <div data-testid="activity-top-paths">
                <p className="text-xs uppercase tracking-wider text-muted-foreground mb-1.5">
                  Where you spent your time
                </p>
                <ul className="space-y-1 text-sm">
                  {stats.top_paths.slice(0, 3).map((p) => (
                    <li key={p.path} className="flex items-center justify-between">
                      <span className="truncate text-foreground/90 mr-3">{p.path}</span>
                      <span className="text-muted-foreground text-xs">{p.views} visit{p.views === 1 ? "" : "s"}</span>
                    </li>
                  ))}
                </ul>
              </div>
            ) : (
              <p className="text-xs text-muted-foreground italic">
                Browse a few pages — your top destinations will show up here.
              </p>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function Stat({ icon, label, value, testid }) {
  return (
    <div className="rounded-lg border border-border bg-background/40 px-3 py-2.5" data-testid={testid}>
      <div className="flex items-center gap-1.5 text-muted-foreground text-[10px] uppercase tracking-wider">
        {icon}
        <span>{label}</span>
      </div>
      <p className="text-2xl font-bold text-foreground mt-1 tabular-nums">{value ?? 0}</p>
    </div>
  );
}
