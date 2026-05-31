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
  const [priorityData, setPriorityData] = useState(null);

  useEffect(() => {
    if (!leagueId) return;
    let cancel = false;
    api
      .get(`/leagues/${leagueId}/transactions-config`)
      .then(({ data }) => { if (!cancel) setCfg(data); })
      .catch(() => { if (!cancel) setCfg(null); });
    // Iter 122 — fetch the team's current rank in the waiver priority queue
    api
      .get(`/leagues/${leagueId}/waiver-priority`)
      .then(({ data }) => { if (!cancel) setPriorityData(data); })
      .catch(() => { if (!cancel) setPriorityData(null); });
    return () => { cancel = true; };
  }, [leagueId]);

  if (!cfg) return null;
  const w = cfg.waiver || {};
  if (!w.enabled) return null;

  const meta = PRIORITY_META[w.priority_order] || PRIORITY_META.reverse_standings_serpentine;
  const Icon = meta.icon;
  const manualOrder = w.priority_order === "manual" ? (w.manual_priority_order || []) : null;
  const myRank = priorityData?.my_rank;
  const totalTeams = priorityData?.total_teams;

  // Iter 122 — Render the league's effective queue, with the user's team
  // visually highlighted so they know where they sit this week.
  const queue = priorityData?.order || [];

  // Friendly rank suffix ("1st", "2nd", "3rd", "12th")
  const rankLabel = (n) => {
    if (n == null) return "—";
    if (n >= 11 && n <= 13) return `${n}th`;
    const r = n % 10;
    return `${n}${r === 1 ? "st" : r === 2 ? "nd" : r === 3 ? "rd" : "th"}`;
  };

  return (
    <div
      className="rounded-md border border-amber-500/30 bg-amber-500/5 p-3 space-y-3"
      data-testid="waiver-priority-order-card"
    >
      <div className="flex items-start gap-3">
        <Icon className="h-4 w-4 text-amber-400 mt-0.5 flex-shrink-0" />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-xs uppercase tracking-wide text-amber-300/70">Priority Order this week</span>
            <span className="text-sm font-semibold text-amber-200" data-testid="waiver-priority-order-label">
              {meta.label}
            </span>
            {myRank != null && (
              <span
                className="text-xs px-2 py-0.5 rounded-md bg-emerald-500/15 border border-emerald-500/40 text-emerald-300 font-bold"
                data-testid="waiver-my-rank"
              >
                You're {rankLabel(myRank)} in line
                {totalTeams ? ` (of ${totalTeams})` : ""}
              </span>
            )}
          </div>
          <p className="text-xs text-muted-foreground mt-1 leading-relaxed">{meta.blurb}</p>
        </div>
      </div>

      {/* Iter 122 — Full queue with the user's team highlighted */}
      {queue.length > 0 && (
        <div className="rounded-md border border-amber-500/20 bg-background/30 p-2" data-testid="waiver-priority-queue">
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-1">
            {queue.map((row) => {
              const isMe = priorityData?.my_team_id === row.team_id;
              return (
                <div
                  key={row.team_id}
                  className={`text-xs px-2 py-1 rounded flex items-center gap-2 ${isMe ? "bg-emerald-500/15 text-emerald-200 font-semibold border border-emerald-500/40" : "text-foreground/80"}`}
                  data-testid={isMe ? "waiver-queue-me" : "waiver-queue-row"}
                >
                  <span className="text-muted-foreground w-6 text-right">{row.rank}.</span>
                  <span className="truncate">{row.team_name}</span>
                  {isMe && <span className="ml-auto text-[10px] uppercase tracking-wide">you</span>}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Manual list (when set, but no priorityData yet) */}
      {!queue.length && manualOrder && manualOrder.length > 0 && (
        <ol className="text-xs text-foreground/80 mt-2 ml-4 list-decimal space-y-0.5" data-testid="waiver-priority-manual-list">
          {manualOrder.map((tid) => (
            <li key={tid}>{teamsById?.[tid]?.name || tid}</li>
          ))}
        </ol>
      )}
    </div>
  );
}
