// @ts-nocheck
import { HelpCircle } from "lucide-react";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

/**
 * Inline help icon — renders a small "?" that surfaces a tooltip
 * with a description. Use anywhere a setting needs a quick explainer.
 *
 * Usage:
 *   <Label>Roster spots <HelpTooltip text="Total number of players each team can carry." /></Label>
 */
export default function HelpTooltip({ text, testId }) {
  if (!text) return null;
  return (
    <TooltipProvider delayDuration={150}>
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            type="button"
            data-testid={testId}
            aria-label="Help"
            className="inline-flex items-center justify-center text-[#A1A1AA] hover:text-[#00D2FF] ml-1.5 align-middle cursor-help"
            onClick={(e) => e.preventDefault()}
          >
            <HelpCircle className="h-3.5 w-3.5" />
          </button>
        </TooltipTrigger>
        <TooltipContent className="max-w-xs bg-[#0A0A0A] border border-white/15 text-white text-xs">
          {text}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
