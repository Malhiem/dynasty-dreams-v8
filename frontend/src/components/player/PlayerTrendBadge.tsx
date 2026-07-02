/**
 * Iter 232N.7 — Player trend badge.
 *
 * Compact chip that surfaces the cross-league mover signal computed
 * nightly by `services/player_trends_aggregator.py`. Renders inline
 * next to player names on Waivers, Players, Roster, Trade Block, and
 * the Player Status Feed cards.
 *
 * Design brief:
 *   • Tiny — never more than a single icon + 2-char count so it
 *     doesn't compete with `<PlayerStatusBadges />` (medical/etc).
 *   • Three visual variants keyed off the derived `trend`:
 *       hot     — flame, amber accent (added a lot across leagues)
 *       dropped — arrow-down-from-line, rose accent (widely cut)
 *       traded  — repeat-2, cyan accent (moving between rosters)
 *   • Tooltip surfaces the raw counts so a curious manager can see
 *     "3 leagues added, 12 total" without leaving the row.
 *   • Zero-config: pass `trends` from the API response and the chip
 *     renders only when there's a live signal (`trend !== null`).
 */
import { Flame, ArrowDownFromLine, Repeat2 } from "lucide-react";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

interface TrendPayload {
  trend?: "hot" | "dropped" | "traded" | null;
  adds_7d?: number;
  drops_7d?: number;
  trades_7d?: number;
  distinct_leagues_7d?: number;
}

interface Props {
  trends?: TrendPayload | null;
}

const META = {
  hot: {
    icon: Flame,
    tone: "text-amber-300 border-amber-500/40 bg-amber-500/10",
    label: (t: TrendPayload) => `Hot — added ${t.adds_7d} time${t.adds_7d === 1 ? "" : "s"} in the last 7 days across ${t.distinct_leagues_7d} league${t.distinct_leagues_7d === 1 ? "" : "s"}.`,
    count: (t: TrendPayload) => t.adds_7d || 0,
  },
  dropped: {
    icon: ArrowDownFromLine,
    tone: "text-rose-300 border-rose-500/40 bg-rose-500/10",
    label: (t: TrendPayload) => `Dropped — cut ${t.drops_7d} time${t.drops_7d === 1 ? "" : "s"} in the last 7 days across ${t.distinct_leagues_7d} league${t.distinct_leagues_7d === 1 ? "" : "s"}.`,
    count: (t: TrendPayload) => t.drops_7d || 0,
  },
  traded: {
    icon: Repeat2,
    tone: "text-cyan-300 border-cyan-500/40 bg-cyan-500/10",
    label: (t: TrendPayload) => `Traded — moved ${t.trades_7d} time${t.trades_7d === 1 ? "" : "s"} in the last 7 days across ${t.distinct_leagues_7d} league${t.distinct_leagues_7d === 1 ? "" : "s"}.`,
    count: (t: TrendPayload) => t.trades_7d || 0,
  },
} as const;

export function PlayerTrendBadge({ trends }: Props) {
  if (!trends || !trends.trend) return null;
  const meta = META[trends.trend];
  if (!meta) return null;
  const Icon = meta.icon;
  const count = meta.count(trends);
  return (
    <span
      className="inline-flex"
      data-testid="player-trend-badge"
      data-trend={trends.trend}
    >
      <Tooltip>
        <TooltipTrigger asChild>
          <span
            className={`inline-flex items-center gap-0.5 text-[10px] font-semibold border rounded px-1 py-0.5 leading-none ${meta.tone}`}
            data-testid={`player-trend-badge-${trends.trend}`}
          >
            <Icon className="h-2.5 w-2.5" />
            {count}
          </span>
        </TooltipTrigger>
        <TooltipContent side="top" className="text-xs max-w-xs">
          {meta.label(trends)}
        </TooltipContent>
      </Tooltip>
    </span>
  );
}

export default PlayerTrendBadge;
