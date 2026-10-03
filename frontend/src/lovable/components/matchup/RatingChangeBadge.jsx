// @ts-nocheck
import { TrendingUp, TrendingDown } from "lucide-react";

/**
 * Compact "rating change" pill for completed matchups.
 *
 * Renders nothing when no delta is provided (i.e. the matchup hasn't been
 * simulated yet, so no ELO update has fired).
 *
 * Layout: `▲ +12 → 1547` (gain) or `▼ -12 → 1488` (loss) or `± 0 → 1500` (tie).
 */
export default function RatingChangeBadge({ delta, ratingAfter, testId }) {
  if (delta === null || delta === undefined || ratingAfter === null || ratingAfter === undefined) {
    return null;
  }
  const positive = delta > 0;
  const negative = delta < 0;
  const tone = positive
    ? "text-emerald-300 border-emerald-400/40 bg-emerald-500/10"
    : negative
      ? "text-rose-300 border-rose-400/40 bg-rose-500/10"
      : "text-zinc-300 border-zinc-400/30 bg-zinc-500/10";
  const Arrow = positive ? TrendingUp : negative ? TrendingDown : null;
  const sign = positive ? "+" : "";
  return (
    <span
      data-testid={testId}
      title={`ELO change ${sign}${delta.toFixed(1)} → final rating ${Math.round(ratingAfter)}`}
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full border text-[11px] font-semibold tabular-nums ${tone}`}
    >
      {Arrow && <Arrow className="h-3 w-3" />}
      {sign}{delta.toFixed(1)} → {Math.round(ratingAfter)}
    </span>
  );
}
