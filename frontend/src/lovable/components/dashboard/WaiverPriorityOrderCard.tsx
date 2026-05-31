// @ts-nocheck
/**
 * Iter 121 — Render the league's selected waiver Priority Order so owners
 * know what to expect when claims process. Reads the live envelope from
 * `/api/leagues/{id}/transactions-config` (iter 117).
 *
 * Renders nothing when:
 *   • leagueId is missing,
 *   • waiver section is disabled (free agency rules govern adds),
 *   • the config call fails (silently — non-critical surface).
 */
import { useEffect, useState } from "react";
import { Crown, Shuffle, ListOrdered, Hand } from "lucide-react";
import api from "@/lib/api";

const PRIORITY_META = {
  reverse_standings_serpentine: {
    label: "Reverse Order of Standings — Serpentine",
    icon: ListOrdered,
    blurb:
      "Lowest-ranked team picks first each round, then the order snakes back the other way. Repeats until every team is out of pending claims.",
  },
  reverse_standings: {
    label: "Reverse Order of Standings",
    icon: ListOrdered,
    blurb: "Same order every round — lowest-ranked team always picks first.",
  },
  manual: {
    label: "Manual Priority Order",
    icon: Hand,
    blurb:
      "League Admin sets the order; the same priority list applies every cycle.",
  },
  random: {
    label: "Random",
    icon: Shuffle,
    blurb: "Order is reshuffled at random every processing cycle.",
  },
};

export default function WaiverPriorityOrderCard({ leagueId, teamsById }) {
  const [cfg, setCfg] = useState(null);

  useEffect(() => {
    if (!leagueId) return;
    let cancel = false;
    api
      .get(`/leagues/${leagueId}/transactions-config`)
      .then(({ data }) => { if (!cancel) setCfg(data); })
      .catch(() => { if (!cancel) setCfg(null); });
    return () => { cancel = true; };
  }, [leagueId]);

  if (!cfg) return null;
  const w = cfg.waiver || {};
  if (!w.enabled) return null;

  const meta = PRIORITY_META[w.priority_order] || PRIORITY_META.reverse_standings_serpentine;
  const Icon = meta.icon;
  const manualOrder = w.priority_order === "manual" ? (w.manual_priority_order || []) : null;

  return (
    <div
      className="rounded-md border border-amber-500/30 bg-amber-500/5 p-3 flex items-start gap-3"
      data-testid="waiver-priority-order-card"
    >
      <Icon className="h-4 w-4 text-amber-400 mt-0.5 flex-shrink-0" />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-xs uppercase tracking-wide text-amber-300/70">Priority Order this week</span>
          <span className="text-sm font-semibold text-amber-200" data-testid="waiver-priority-order-label">
            {meta.label}
          </span>
        </div>
        <p className="text-xs text-muted-foreground mt-1 leading-relaxed">{meta.blurb}</p>
        {manualOrder && manualOrder.length > 0 && (
          <ol className="text-xs text-foreground/80 mt-2 ml-4 list-decimal space-y-0.5" data-testid="waiver-priority-manual-list">
            {manualOrder.map((tid) => (
              <li key={tid}>{teamsById?.[tid]?.name || tid}</li>
            ))}
          </ol>
        )}
      </div>
    </div>
  );
}
