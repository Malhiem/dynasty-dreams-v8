// @ts-nocheck
/**
 * DailyGrid — Full grid view: rows = players, columns = days.
 * Each cell shows FPTS, color-coded (green = above avg, red = below).
 * Option C design for comprehensive day-by-day view.
 */
import { cn } from "@/lib/utils";
import { ScrollArea, ScrollBar } from "@/components/ui/scroll-area";
import type { DailyScoringPlayer } from "@/hooks/use-daily-scoring";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

interface DailyGridProps {
  days: string[];
  dayLabels: string[];
  players: DailyScoringPlayer[];
  dailyTotals: Record<string, number>;
  className?: string;
}

export function DailyGrid({
  days,
  dayLabels,
  players,
  dailyTotals,
  className,
}: DailyGridProps) {
  // Calculate the average per-cell fpts to use for color coding
  const allValues: number[] = [];
  players.forEach((p) => {
    days.forEach((d) => {
      const v = p.daily[d]?.fpts || 0;
      if (v > 0) allValues.push(v);
    });
  });
  const avg = allValues.length > 0 ? allValues.reduce((a, b) => a + b, 0) / allValues.length : 0;

  const cellColor = (val: number) => {
    if (val === 0) return "text-muted-foreground/40";
    if (val >= avg * 1.5) return "bg-emerald-500/20 text-emerald-400 font-semibold";
    if (val >= avg) return "bg-emerald-500/10 text-emerald-300";
    if (val >= avg * 0.5) return "text-foreground";
    return "bg-rose-500/10 text-rose-300";
  };

  if (!players.length) {
    return (
      <div className="surface p-6 text-center text-muted-foreground text-sm" data-testid="daily-grid-empty">
        No player data available for this matchup period.
      </div>
    );
  }

  return (
    <div className={cn("surface overflow-hidden", className)} data-testid="daily-grid">
      <ScrollArea className="w-full">
        <table className="w-full text-left text-sm border-collapse">
          <thead>
            <tr className="bg-secondary/50 text-muted-foreground text-xs uppercase tracking-wider">
              <th className="px-3 py-2.5 sticky left-0 bg-secondary/50 z-10 min-w-[160px]">
                Player
              </th>
              <th className="px-3 py-2.5 text-center min-w-[56px]">Pos</th>
              {days.map((d, i) => (
                <th key={d} className="px-2 py-2.5 text-center min-w-[70px]">
                  <div className="text-[10px]">{dayLabels[i]?.split(" ")[0]}</div>
                  <div className="text-[9px] text-muted-foreground/60">{dayLabels[i]?.split(" ")[1]}</div>
                </th>
              ))}
              <th className="px-3 py-2.5 text-center min-w-[70px] font-bold">Total</th>
            </tr>
          </thead>
          <tbody>
            {players.map((p, idx) => (
              <TooltipProvider key={p.id} delayDuration={200}>
                <tr
                  className={cn(
                    "border-t border-border/50 transition-colors hover:bg-secondary/30",
                    idx === 0 && "bg-primary/5"
                  )}
                  data-testid={`daily-grid-row-${p.id}`}
                >
                  <td className="px-3 py-2 sticky left-0 bg-card z-10">
                    <div className="font-medium truncate max-w-[140px]">{p.name}</div>
                    <div className="text-[10px] text-muted-foreground">{p.team}</div>
                  </td>
                  <td className="px-3 py-2 text-center text-muted-foreground text-xs">
                    {p.position}
                  </td>
                  {days.map((d) => {
                    const dayStats = p.daily[d];
                    const fpts = dayStats?.fpts || 0;
                    return (
                      <td key={d} className="px-1 py-2 text-center">
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <span
                              className={cn(
                                "inline-block rounded px-1.5 py-0.5 tabular-nums text-xs min-w-[40px]",
                                cellColor(fpts)
                              )}
                              data-testid={`daily-grid-cell-${p.id}-${d}`}
                            >
                              {fpts > 0 ? fpts.toFixed(1) : "—"}
                            </span>
                          </TooltipTrigger>
                          {dayStats && dayStats.games > 0 && (
                            <TooltipContent side="top" className="text-xs">
                              {p.is_goalie ? (
                                <span>{dayStats.wins}W · {dayStats.saves} SVS · {dayStats.goals_against} GA</span>
                              ) : (
                                <span>{dayStats.goals}G {dayStats.assists}A · {dayStats.shots} SOG</span>
                              )}
                              <span className="text-muted-foreground"> · {dayStats.games} GP</span>
                            </TooltipContent>
                          )}
                        </Tooltip>
                      </td>
                    );
                  })}
                  <td className="px-3 py-2 text-center">
                    <span className="font-bold tabular-nums text-primary text-sm">
                      {p.total_fpts > 0 ? p.total_fpts.toFixed(1) : "—"}
                    </span>
                  </td>
                </tr>
              </TooltipProvider>
            ))}
            {/* Totals row */}
            <tr className="border-t-2 border-border bg-secondary/40 font-semibold">
              <td className="px-3 py-2.5 sticky left-0 bg-secondary/40 z-10 text-sm">
                Team Total
              </td>
              <td />
              {days.map((d) => (
                <td key={d} className="px-1 py-2.5 text-center tabular-nums text-sm">
                  {(dailyTotals[d] || 0) > 0 ? (dailyTotals[d] || 0).toFixed(1) : "—"}
                </td>
              ))}
              <td className="px-3 py-2.5 text-center text-primary font-bold tabular-nums text-sm">
                {players.reduce((s, p) => s + p.total_fpts, 0).toFixed(1)}
              </td>
            </tr>
          </tbody>
        </table>
        <ScrollBar orientation="horizontal" />
      </ScrollArea>
    </div>
  );
}
