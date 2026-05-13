// @ts-nocheck
/**
 * VetoThresholdPreview — small live preview that translates a raw veto %
 * into "X teams required to veto" by hitting
 * `GET /api/leagues/{id}/veto-threshold-preview?pct=N`.
 *
 * Renders inline alongside the % input so the commissioner sees, in real
 * time, what their setting actually means for their league size.
 *
 *   50% of 12 teams = 6 teams required to veto a trade.
 */
import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Users, ShieldX, Loader2 } from "lucide-react";
import api from "@/lib/api";

export default function VetoThresholdPreview({ leagueId, pct, className = "", testId }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!leagueId) return;
    const n = Number(pct);
    if (Number.isNaN(n)) return;
    let cancelled = false;
    setLoading(true);
    api
      .get(`/leagues/${leagueId}/veto-threshold-preview`, { params: { pct: n } })
      .then(({ data }) => { if (!cancelled) setData(data); })
      .catch(() => {})
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [leagueId, pct]);

  if (!leagueId) return null;
  if (loading && !data) {
    return (
      <span className={`text-xs text-muted-foreground flex items-center gap-1 ${className}`}>
        <Loader2 className="h-3 w-3 animate-spin" /> Calculating…
      </span>
    );
  }
  if (!data) return null;
  if (!data.enabled) {
    return (
      <Badge
        variant="outline"
        className={`gap-1 bg-rose-500/15 text-rose-300 border-rose-500/40 ${className}`}
        data-testid={testId || "veto-threshold-disabled"}
      >
        <ShieldX className="h-3 w-3" />
        Vetoes disabled
      </Badge>
    );
  }
  return (
    <Badge
      variant="outline"
      className={`gap-1 bg-amber-500/15 text-amber-300 border-amber-500/40 ${className}`}
      data-testid={testId || "veto-threshold-preview"}
    >
      <Users className="h-3 w-3" />
      {data.pct}% of {data.total_teams} ={" "}
      <span className="font-semibold">
        {data.teams_required} team{data.teams_required === 1 ? "" : "s"}
      </span>
      &nbsp;required to veto
    </Badge>
  );
}
