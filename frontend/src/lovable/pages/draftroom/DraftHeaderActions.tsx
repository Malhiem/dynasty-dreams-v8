// @ts-nocheck
/**
 * Iter 174 — DraftHeaderActions
 *
 * Extracted from DraftRoom.tsx. Renders the page-header strip:
 *   • Draft Room title + sub-header (entry vs. open criteria copy).
 *   • Read-only Draft Criteria popover (set in League Admin → Drafts).
 *   • Trade Mode toggle (mirrors Draft Board's quick-add bar).
 *   • Trading Block (side-rail) overlay toggle + count badge.
 *
 * Pure presentational — the parent owns all state. Logic that used to
 * live inline (~90 LOC) is now a single tidy import.
 */
import { Button } from "@/components/ui/button";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { LayoutGrid, Info, Repeat, Megaphone } from "lucide-react";
import { cn } from "@/lib/utils";

export default function DraftHeaderActions({
  currentDraft,
  currentCriteria,
  tradeMode,
  setTradeMode,
  tradeBlockMode,
  setTradeBlockMode,
  tradeBlockItems,
}) {
  return (
    <div className="flex items-start gap-4 flex-wrap">
      <div>
        <h1 className="text-2xl font-bold text-foreground flex items-center gap-2">
          <LayoutGrid className="h-6 w-6 text-primary" />
          Draft Room
        </h1>
        <p className="text-sm text-muted-foreground" data-testid="draft-room-subheader">
          {currentDraft?.player_criteria === "entry"
            ? "2026 NHL Entry Draft — League Rookie Draft"
            : "League Draft — Open · all eligible NHL players"}
        </p>
      </div>

      {/* Iter 147 — Draft Criteria is READ-ONLY (set in League Admin → Drafts). */}
      <Popover>
        <PopoverTrigger asChild>
          <Button variant="outline" size="sm" className="gap-1.5" data-testid="draft-room-criteria-trigger">
            <Info className="h-3.5 w-3.5" />
            Draft Criteria: {currentCriteria?.label}
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-80 bg-popover border-border z-50" align="start">
          <div className="space-y-3">
            <h4 className="font-semibold text-sm text-foreground">Eligible Player Criteria</h4>
            <div
              className="rounded-md border border-border px-3 py-2 text-sm bg-secondary/40"
              data-testid="draft-room-criteria-display"
            >
              <span className="font-medium">{currentCriteria?.label}</span>
            </div>
            <div className="bg-secondary/50 rounded-md p-3">
              <p className="text-xs text-muted-foreground leading-relaxed">
                {currentCriteria?.description}
              </p>
            </div>
            <p
              className="text-[11px] italic text-muted-foreground"
              data-testid="draft-room-criteria-readonly-note"
            >
              Configured in League Administration → Drafts.
            </p>
          </div>
        </PopoverContent>
      </Popover>

      {/* Iter 147 — Propose Trade toggle (mirrors Draft Board) */}
      <Button
        size="sm"
        variant={tradeMode ? "default" : "outline"}
        onClick={() => setTradeMode((v) => !v)}
        data-testid="draft-room-trade-toggle"
        aria-pressed={tradeMode}
        className={tradeMode ? "bg-emerald-500 hover:bg-emerald-600 text-white gap-1.5" : "gap-1.5"}
      >
        <Repeat className="h-3.5 w-3.5" />
        {tradeMode ? "Trade Mode: On" : "Trade Mode: Off"}
      </Button>

      {/* Iter 149 — Trading Block overlay toggle (side-rail entry point) */}
      <Button
        size="sm"
        variant={tradeBlockMode ? "default" : "outline"}
        onClick={() => setTradeBlockMode((v) => !v)}
        data-testid="draft-room-trade-block-toggle"
        aria-pressed={tradeBlockMode}
        className={tradeBlockMode ? "bg-amber-500 hover:bg-amber-600 text-white gap-1.5" : "gap-1.5"}
      >
        <Megaphone className="h-3.5 w-3.5" />
        {tradeBlockMode ? "Trading Block: On" : "Trading Block: Off"}
        {tradeBlockItems.length > 0 && (
          <span
            className={cn(
              "ml-0.5 inline-flex items-center justify-center h-4 min-w-4 px-1 rounded-full text-[9px] font-bold",
              tradeBlockMode ? "bg-white/20 text-white" : "bg-amber-500/20 text-amber-300",
            )}
            data-testid="draft-room-trade-block-count"
          >
            {tradeBlockItems.length}
          </span>
        )}
      </Button>
    </div>
  );
}
