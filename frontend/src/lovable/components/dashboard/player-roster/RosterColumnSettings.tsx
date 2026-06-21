// @ts-nocheck
/**
 * Iter 187 — Roster Column Settings Popover.
 *
 * Extracted from `PlayerRoster.tsx` Team Roster header. Encapsulates
 * the `<Popover>` triggered by the Settings cog that lets owners
 * toggle which tracked / untracked stat categories + display options
 * (Fantasy Points, Position Eligibility) appear in the roster table.
 *
 * Risks documented:
 *   1. State is owned by `PlayerRoster.tsx` (`visibleColumns`,
 *      `showPositionEligibility`); we forward setters so the parent
 *      remains the single source of truth. Forgetting to pipe any
 *      setter would silently break the toggle for that column.
 *   2. `Show All / Tracked Only / Points Only` shortcut buttons
 *      replace the entire Set rather than toggling — must NOT switch
 *      to additive set merging or the "Points Only" preset breaks.
 *   3. The `categoryLabels` map must include every key in
 *      `trackedCategories` + `untrackedCategories` or the right-side
 *      description renders empty.
 */
import { Settings } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Checkbox } from "@/components/ui/checkbox";
import { Separator } from "@/components/ui/separator";
import {
  trackedCategories,
  untrackedCategories,
  allStatCategories,
  categoryLabels,
} from "./internals";

export const RosterColumnSettings = ({
  visibleColumns,
  setVisibleColumns,
  showPositionEligibility,
  setShowPositionEligibility,
}: {
  visibleColumns: Set<string>;
  setVisibleColumns: (next: Set<string> | ((prev: Set<string>) => Set<string>)) => void;
  showPositionEligibility: boolean;
  setShowPositionEligibility: (val: boolean) => void;
}) => {
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          className="h-7 w-7 text-muted-foreground hover:text-foreground"
          data-testid="roster-column-settings-trigger"
        >
          <Settings className="h-4 w-4" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-[280px] p-0" align="start" data-testid="roster-column-settings-popover">
        <div className="p-3 border-b border-border">
          <p className="text-sm font-semibold">Roster Display Settings</p>
          <p className="text-xs text-muted-foreground">Choose which columns to show</p>
        </div>

        {/* Tracked Categories */}
        <div className="p-3 space-y-2">
          <p className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
            Tracked Categories
          </p>
          <div className="grid grid-cols-2 gap-1.5">
            {trackedCategories.map((cat) => (
              <label
                key={cat}
                className="flex items-center gap-2 text-xs cursor-pointer hover:bg-secondary/50 rounded px-1.5 py-1"
              >
                <Checkbox
                  checked={visibleColumns.has(cat)}
                  onCheckedChange={(checked) => {
                    setVisibleColumns((prev) => {
                      const next = new Set(prev);
                      if (checked) next.add(cat); else next.delete(cat);
                      return next;
                    });
                  }}
                  className="h-3.5 w-3.5"
                />
                <span className="font-medium">{cat}</span>
                <span className="text-muted-foreground ml-auto text-[10px]">
                  {categoryLabels[cat]}
                </span>
              </label>
            ))}
          </div>
        </div>

        <Separator />

        {/* Untracked Categories */}
        <div className="p-3 space-y-2">
          <p className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
            Untracked Categories
          </p>
          <div className="grid grid-cols-2 gap-1.5">
            {untrackedCategories.map((cat) => (
              <label
                key={cat}
                className="flex items-center gap-2 text-xs cursor-pointer hover:bg-secondary/50 rounded px-1.5 py-1"
              >
                <Checkbox
                  checked={visibleColumns.has(cat)}
                  onCheckedChange={(checked) => {
                    setVisibleColumns((prev) => {
                      const next = new Set(prev);
                      if (checked) next.add(cat); else next.delete(cat);
                      return next;
                    });
                  }}
                  className="h-3.5 w-3.5"
                />
                <span className="font-medium">{cat}</span>
                <span className="text-muted-foreground ml-auto text-[10px]">
                  {categoryLabels[cat]}
                </span>
              </label>
            ))}
          </div>
        </div>

        <Separator />

        {/* Fantasy Points & Position Eligibility */}
        <div className="p-3 space-y-2">
          <p className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
            Display Options
          </p>
          <label className="flex items-center gap-2 text-xs cursor-pointer hover:bg-secondary/50 rounded px-1.5 py-1">
            <Checkbox
              checked={visibleColumns.has("FPTS")}
              onCheckedChange={(checked) => {
                setVisibleColumns((prev) => {
                  const next = new Set(prev);
                  if (checked) next.add("FPTS"); else next.delete("FPTS");
                  return next;
                });
              }}
              className="h-3.5 w-3.5"
            />
            <span className="font-medium">Fantasy Points</span>
          </label>
          <label className="flex items-center gap-2 text-xs cursor-pointer hover:bg-secondary/50 rounded px-1.5 py-1">
            <Checkbox
              checked={showPositionEligibility}
              onCheckedChange={(checked) => setShowPositionEligibility(!!checked)}
              className="h-3.5 w-3.5"
            />
            <span className="font-medium">Position Eligibility</span>
          </label>
        </div>

        <Separator />

        {/* Quick toggles */}
        <div className="p-3 flex gap-2">
          <Button
            variant="outline"
            size="sm"
            className="text-[10px] h-6 px-2"
            onClick={() => setVisibleColumns(new Set([...allStatCategories, "FPTS"]))}
            data-testid="roster-column-settings-show-all"
          >
            Show All
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="text-[10px] h-6 px-2"
            onClick={() => setVisibleColumns(new Set([...trackedCategories, "FPTS"]))}
            data-testid="roster-column-settings-tracked-only"
          >
            Tracked Only
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="text-[10px] h-6 px-2"
            onClick={() => setVisibleColumns(new Set(["FPTS"]))}
            data-testid="roster-column-settings-points-only"
          >
            Points Only
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  );
};
