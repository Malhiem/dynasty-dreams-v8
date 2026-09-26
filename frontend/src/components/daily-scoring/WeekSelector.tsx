// @ts-nocheck
/**
 * WeekSelector — Dropdown to select a matchup week/period for
 * reviewing past or current daily scoring breakdowns.
 */
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

interface WeekSelectorProps {
  currentWeek: number;
  totalWeeks: number;
  selectedWeek: number;
  onWeekChange: (week: number) => void;
  className?: string;
}

export function WeekSelector({
  currentWeek,
  totalWeeks,
  selectedWeek,
  onWeekChange,
  className,
}: WeekSelectorProps) {
  const weeks = Array.from({ length: Math.max(totalWeeks, currentWeek) }, (_, i) => i + 1);

  return (
    <div className={className} data-testid="week-selector">
      <Select
        value={String(selectedWeek)}
        onValueChange={(v) => onWeekChange(Number(v))}
      >
        <SelectTrigger
          className="w-[160px] h-8 text-xs bg-secondary/40 border-border"
          data-testid="week-selector-trigger"
        >
          <SelectValue placeholder="Select Week" />
        </SelectTrigger>
        <SelectContent>
          {weeks.map((w) => (
            <SelectItem key={w} value={String(w)} data-testid={`week-option-${w}`}>
              Week {w}
              {w === currentWeek && (
                <span className="text-primary ml-1 text-[10px]">• Current</span>
              )}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}
