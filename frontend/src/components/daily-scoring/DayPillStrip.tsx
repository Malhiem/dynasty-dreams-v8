// @ts-nocheck
/**
 * DayPillStrip — Horizontal row of day pills for selecting a date
 * within a matchup period. Clicking a day filters player rows to
 * show that day's stats. A "Total" pill shows the full period.
 */
import { cn } from "@/lib/utils";

interface DayPillStripProps {
  days: string[];
  dayLabels: string[];
  dailyTotals: Record<string, number>;
  selectedDay: string | null; // null = "Total" selected
  onSelectDay: (day: string | null) => void;
  oppDailyTotals?: Record<string, number>;
  className?: string;
}

export function DayPillStrip({
  days,
  dayLabels,
  dailyTotals,
  selectedDay,
  onSelectDay,
  oppDailyTotals,
  className,
}: DayPillStripProps) {
  const periodTotal = Object.values(dailyTotals).reduce((s, v) => s + v, 0);

  return (
    <div
      className={cn("flex gap-1.5 overflow-x-auto pb-1 scrollbar-thin", className)}
      data-testid="day-pill-strip"
    >
      {/* Total pill */}
      <button
        onClick={() => onSelectDay(null)}
        data-testid="day-pill-total"
        className={cn(
          "shrink-0 rounded-lg px-3 py-2 text-center transition-all border min-w-[68px]",
          selectedDay === null
            ? "border-primary bg-primary/15 ring-1 ring-primary/40"
            : "border-border bg-secondary/30 hover:bg-secondary/50"
        )}
      >
        <p className="text-[10px] font-semibold text-muted-foreground tracking-wider uppercase">
          Total
        </p>
        <p className={cn(
          "text-sm font-bold tabular-nums",
          selectedDay === null ? "text-primary" : "text-foreground"
        )}>
          {periodTotal.toFixed(1)}
        </p>
        {oppDailyTotals && (
          <p className="text-[10px] text-muted-foreground tabular-nums">
            vs {Object.values(oppDailyTotals).reduce((s, v) => s + v, 0).toFixed(1)}
          </p>
        )}
      </button>

      {days.map((day, idx) => {
        const myPts = dailyTotals[day] || 0;
        const oppPts = oppDailyTotals?.[day] || 0;
        const isSelected = selectedDay === day;
        const isWinning = myPts >= oppPts;

        return (
          <button
            key={day}
            onClick={() => onSelectDay(day)}
            data-testid={`day-pill-${day}`}
            className={cn(
              "shrink-0 rounded-lg px-3 py-2 text-center transition-all border min-w-[62px]",
              isSelected
                ? "border-primary bg-primary/15 ring-1 ring-primary/40"
                : "border-border bg-secondary/30 hover:bg-secondary/50"
            )}
          >
            <p className="text-[10px] font-medium text-muted-foreground">
              {dayLabels[idx]?.split(" ")[0] || ""}
            </p>
            <p
              className={cn(
                "text-sm font-bold tabular-nums",
                myPts === 0
                  ? "text-muted-foreground"
                  : oppDailyTotals
                    ? isWinning ? "text-emerald-400" : "text-rose-400"
                    : "text-foreground"
              )}
            >
              {myPts.toFixed(1)}
            </p>
            {oppDailyTotals && (
              <p className="text-[10px] text-muted-foreground tabular-nums">
                {oppPts.toFixed(1)}
              </p>
            )}
          </button>
        );
      })}
    </div>
  );
}
