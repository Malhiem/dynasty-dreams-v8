// @ts-nocheck
/**
 * Iter 117 — Claims counter chip.
 *
 * Reads `/api/teams/{teamId}/claim-counts` which is gated by the league's
 * `claim_rules.pending_visibility` setting. If the calling user isn't
 * entitled to see this team's counts, the API returns `visible:false` and
 * we render nothing.
 *
 * Visible chip shape:  "Claims · Season 5/20 · Week 1/5"
 * If a bucket is unlimited (cap=null) we show just the count: "Season 5".
 */
import { useEffect, useState } from "react";
import { Activity } from "lucide-react";
import api from "@/lib/api";

const fmtBucket = (used, cap, label) => {
  if (cap === null || cap === undefined) return `${label} ${used}`;
  return `${label} ${used}/${cap}`;
};

export default function TeamClaimCounter({ teamId, refreshKey }) {
  const [data, setData] = useState(null);

  useEffect(() => {
    if (!teamId) return;
    let cancelled = false;
    api.get(`/teams/${teamId}/claim-counts`)
      .then((r) => { if (!cancelled) setData(r.data); })
      .catch(() => { if (!cancelled) setData(null); });
    return () => { cancelled = true; };
  }, [teamId, refreshKey]);

  if (!data || !data.visible) return null;

  // Iter 122 — Anonymous mode: only the total counts surface, not the
  // free-agency / waiver breakdown (which could reveal strategy). Owners
  // and commissioners are unaffected — they always see the full breakdown.
  if (data.anonymous) {
    return (
      <div
        className="inline-flex items-center gap-2 rounded-md border border-border bg-secondary/40 px-3 py-1.5 text-xs"
        data-testid="team-claim-counter-anonymous"
      >
        <Activity className="h-3.5 w-3.5 text-cyan-400" />
        <span className="font-medium">Claims</span>
        <span className="text-muted-foreground">·</span>
        <span data-testid="team-claim-counter-season-anon">Season {data.season.total}</span>
        <span className="text-muted-foreground">·</span>
        <span data-testid="team-claim-counter-week-anon">Week {data.week.total}</span>
        <span className="text-[10px] text-muted-foreground italic ml-1">(league total view)</span>
      </div>
    );
  }

  const sLimits = data.limits?.season || {};
  const wLimits = data.limits?.week || {};

  return (
    <div
      className="inline-flex items-center gap-2 rounded-md border border-border bg-secondary/40 px-3 py-1.5 text-xs"
      data-testid="team-claim-counter"
    >
      <Activity className="h-3.5 w-3.5 text-cyan-400" />
      <span className="font-medium">Claims</span>
      <span className="text-muted-foreground">·</span>
      <span data-testid="team-claim-counter-season">
        {fmtBucket(data.season.total, sLimits.total, "Season")}
      </span>
      <span className="text-muted-foreground">·</span>
      <span data-testid="team-claim-counter-week">
        {fmtBucket(data.week.total, wLimits.total, "Week")}
      </span>
    </div>
  );
}
