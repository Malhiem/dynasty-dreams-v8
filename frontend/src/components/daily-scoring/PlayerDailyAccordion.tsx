// @ts-nocheck
/**
 * PlayerDailyAccordion — Expandable day-by-day breakdown for a
 * single player inside a player card. Shows a mini table with
 * date | stat line | FPTS for each day they played.
 */
import { useState } from "react";
import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";
import type { DailyPlayerStats } from "@/hooks/use-daily-scoring";

interface PlayerDailyAccordionProps {
  playerName: string;
  isGoalie: boolean;
  daily: Record<string, DailyPlayerStats>;
  dayLabels: Record<string, string>; // "2026-01-13" -> "Mon 1/13"
  totalFpts: number;
  className?: string;
}

export function PlayerDailyAccordion({
  playerName,
  isGoalie,
  daily,
  dayLabels,
  totalFpts,
  className,
}: PlayerDailyAccordionProps) {
  const [expanded, setExpanded] = useState(false);

  const sortedDays = Object.keys(daily).sort();
  const activeDays = sortedDays.filter((d) => daily[d]?.games > 0);

  if (activeDays.length === 0) return null;

  return (
    <div className={cn("mt-1", className)} data-testid={`player-daily-accordion`}>
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-1 text-[11px] text-primary/70 hover:text-primary transition-colors"
        data-testid="player-daily-accordion-toggle"
      >
        <ChevronDown
          className={cn(
            "h-3 w-3 transition-transform",
            expanded && "rotate-180"
          )}
        />
        <span>
          {activeDays.length} game day{activeDays.length !== 1 ? "s" : ""} · {totalFpts.toFixed(1)} FPTS
        </span>
      </button>

      {expanded && (
        <div className="mt-1.5 rounded-md border border-border/50 overflow-hidden" data-testid="player-daily-accordion-content">
          <table className="w-full text-xs">
            <thead>
              <tr className="bg-secondary/40 text-muted-foreground">
                <th className="px-2 py-1 text-left font-medium">Date</th>
                <th className="px-2 py-1 text-left font-medium">Stats</th>
                <th className="px-2 py-1 text-right font-medium">FPTS</th>
              </tr>
            </thead>
            <tbody>
              {activeDays.map((day) => {
                const s = daily[day];
                const label = dayLabels[day] || day;
                const statLine = isGoalie
                  ? `${s.wins}W · ${s.saves} SVS · ${s.goals_against} GA`
                  : `${s.goals}G ${s.assists}A · ${s.shots} SOG`;

                return (
                  <tr
                    key={day}
                    className="border-t border-border/30"
                    data-testid={`player-daily-row-${day}`}
                  >
                    <td className="px-2 py-1 text-muted-foreground whitespace-nowrap">
                      {label}
                    </td>
                    <td className="px-2 py-1 font-mono tabular-nums text-muted-foreground">
                      {statLine}
                    </td>
                    <td className="px-2 py-1 text-right font-semibold tabular-nums text-primary">
                      {s.fpts.toFixed(1)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
