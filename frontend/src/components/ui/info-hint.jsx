// @ts-nocheck
import { Info } from "lucide-react";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

/**
 * Iter 127 — Superscript "i" info hint for league admin settings.
 *
 * Renders a tiny circled "i" icon that, when hovered (or focused on
 * keyboard / touched on mobile), surfaces a short explainer for the
 * setting it sits next to. Different from <HelpTooltip /> which uses
 * a "?" icon — this is a tighter, in-line info marker meant to ride
 * along setting labels without crowding the layout.
 *
 * Usage:
 *   <Label>
 *     FAAB Budget per Team
 *     <InfoHint text="Per-team blind-bid budget reset every season at draft." />
 *   </Label>
 */
export default function InfoHint({ text, testId, className = "" }) {
  if (!text) return null;
  return (
    <TooltipProvider delayDuration={120} skipDelayDuration={50}>
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            type="button"
            data-testid={testId || "info-hint"}
            aria-label="Setting details"
            onClick={(e) => e.preventDefault()}
            className={`inline-flex align-text-top items-center justify-center ml-1 text-cyan-300/70 hover:text-cyan-200 focus:text-cyan-200 cursor-help leading-none focus:outline-none focus:ring-1 focus:ring-cyan-400/50 rounded-full transition ${className}`}
          >
            {/* Superscript-sized info glyph. The Info icon has the
                circled-i shape requested in the spec. */}
            <Info className="h-3 w-3" strokeWidth={2.2} />
          </button>
        </TooltipTrigger>
        <TooltipContent
          side="top"
          align="start"
          className="max-w-sm bg-popover border border-border text-foreground text-xs leading-relaxed shadow-xl"
          data-testid={testId ? `${testId}-content` : "info-hint-content"}
        >
          {text}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
