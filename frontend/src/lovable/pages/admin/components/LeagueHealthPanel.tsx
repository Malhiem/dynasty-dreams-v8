// @ts-nocheck
/* LeagueHealthPanel — extracted from AdminDashboard.tsx during Iter 224 refactor. */
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import api from "@/lib/api";

/* ─── Iter 209 — League Health Panel ─────────────────────────────────── */
export function LeagueHealthPanel() {
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

export function HealthCard({ title, description, tone, items, testId }: any) {
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




