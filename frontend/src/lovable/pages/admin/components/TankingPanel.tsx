// @ts-nocheck
/* TankingPanel — extracted from AdminDashboard.tsx during Iter 224 refactor. */
import { useEffect, useState } from "react";
import { toast } from "sonner";
import api from "@/lib/api";
import { AlertTriangle } from "lucide-react";

/* ─── Iter 201c — Tanking panel ────────────────────────────────────── */
export function TankingPanel() {
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

