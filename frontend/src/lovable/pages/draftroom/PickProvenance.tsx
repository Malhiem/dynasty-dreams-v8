/**
 * Iter 165 — PickProvenance display.
 *
 * Formats a pick's trade_history array into a human-readable chain:
 *   "Acquired via trade with Team A, 1/25/25 via Team B, 4/20"
 *
 * Same-calendar-year rule: only the FIRST trade in a calendar year
 * shows the full M/D/YY date; subsequent trades in that same calendar
 * year show only M/D. New calendar year → full date again.
 *
 * Each date is wrapped in a <Link> to /transactions?trade_id={id} so
 * the commissioner can pivot from the provenance label straight to the
 * full trade detail.
 */
import { Link } from "react-router-dom";
import { cn } from "@/lib/utils";

export interface TradeHistoryEntry {
  trade_id: string;
  from_team_id: string;
  from_team_name: string;
  to_team_id: string;
  to_team_name: string;
  traded_at: string;  // ISO or BSON datetime
}

interface PickProvenanceProps {
  tradeHistory?: TradeHistoryEntry[] | null;
  className?: string;
  /** Compact = single-line, no "Acquired via" prefix. */
  compact?: boolean;
}

function _shortDate(d: Date, yearAlreadyShown: boolean): string {
  const m = d.getMonth() + 1;
  const day = d.getDate();
  const yr = String(d.getFullYear()).slice(-2);
  return yearAlreadyShown ? `${m}/${day}` : `${m}/${day}/${yr}`;
}

export function formatProvenance(
  entries: TradeHistoryEntry[],
): { fromTeam: string; date: string; tradeId: string; yearShown: boolean }[] {
  // Chain order: earliest → latest, so reverse-iter to know if we've
  // already printed a date in the current calendar year.
  const yearsSeen = new Set<number>();
  return entries.map((e) => {
    const d = new Date(e.traded_at);
    const yr = d.getFullYear();
    const yearAlreadyShown = yearsSeen.has(yr);
    yearsSeen.add(yr);
    return {
      fromTeam: e.from_team_name,
      date: _shortDate(d, yearAlreadyShown),
      tradeId: e.trade_id,
      yearShown: !yearAlreadyShown,
    };
  });
}

export default function PickProvenance({
  tradeHistory,
  className,
  compact = false,
}: PickProvenanceProps) {
  if (!tradeHistory || tradeHistory.length === 0) return null;
  const segments = formatProvenance(tradeHistory);

  return (
    <span
      className={cn("text-xs text-muted-foreground inline-flex flex-wrap items-center gap-x-1", className)}
      data-testid="pick-provenance"
    >
      {!compact && <span>Acquired via trade with</span>}
      {segments.map((seg, idx) => (
        <span key={`${seg.tradeId}-${idx}`} className="inline-flex items-center gap-x-1">
          {idx > 0 && <span className="text-muted-foreground/60">via</span>}
          <span className="font-medium text-foreground" data-testid={`pick-provenance-team-${idx}`}>
            {seg.fromTeam},
          </span>
          <Link
            to={`/transactions?trade_id=${seg.tradeId}`}
            className="text-primary hover:underline"
            data-testid={`pick-provenance-date-${idx}`}
          >
            {seg.date}
          </Link>
        </span>
      ))}
    </span>
  );
}
