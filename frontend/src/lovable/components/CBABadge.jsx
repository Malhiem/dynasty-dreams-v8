// @ts-nocheck
/**
 * CBABadge — small flag that compares a league's salary-retention configuration
 * against the real NHL Collective Bargaining Agreement limits.
 *
 * NHL CBA reference (2025-26):
 *   • Each team may carry a maximum of **3** retention slots simultaneously.
 *   • A team may retain at most **50%** of a player's cap hit / salary.
 *   • A single contract may be retained at most twice in its chain (not
 *     enforced here — informational only).
 *
 * Pass the current slots/maxPct and the badge returns one of three states:
 *   • "Within CBA"     — slots ≤ 3 AND maxPct ≤ 50
 *   • "Exceeds CBA"    — slots > 3 OR maxPct > 50
 *   • "Below CBA"      — slots < 3 OR maxPct < 50  (stricter than the NHL)
 */
import { Badge } from "@/components/ui/badge";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { ShieldCheck, ShieldAlert, ShieldX, Info } from "lucide-react";

const NHL_CBA_MAX_SLOTS = 3;
const NHL_CBA_MAX_PCT = 50;

export default function CBABadge({ slots = 3, maxPct = 50, className = "", testId }) {
  const slotsN = Number(slots);
  const pctN = Number(maxPct);
  const exceedsSlots = slotsN > NHL_CBA_MAX_SLOTS;
  const exceedsPct = pctN > NHL_CBA_MAX_PCT;
  const isStrict = slotsN < NHL_CBA_MAX_SLOTS || pctN < NHL_CBA_MAX_PCT;

  let kind = "within";
  if (exceedsSlots || exceedsPct) kind = "exceeds";
  else if (isStrict) kind = "strict";

  const config = {
    within: {
      label: "Matches NHL CBA",
      Icon: ShieldCheck,
      cls: "bg-emerald-500/20 text-emerald-300 border-emerald-500/40",
      tip: `Exactly mirrors the NHL Collective Bargaining Agreement: ${NHL_CBA_MAX_SLOTS} slots @ ${NHL_CBA_MAX_PCT}% max retention.`,
    },
    exceeds: {
      label: "Exceeds NHL CBA",
      Icon: ShieldAlert,
      cls: "bg-amber-500/20 text-amber-300 border-amber-500/40",
      tip: [
        exceedsSlots ? `${slotsN} retention slots is more than the NHL allows (${NHL_CBA_MAX_SLOTS}).` : null,
        exceedsPct ? `${pctN}% max retention exceeds the NHL cap (${NHL_CBA_MAX_PCT}%).` : null,
        "Dynasty / deep-keeper leagues sometimes go beyond — Dynasty Dreams will honor your setting.",
      ].filter(Boolean).join(" "),
    },
    strict: {
      label: "Stricter than NHL CBA",
      Icon: ShieldX,
      cls: "bg-cyan-500/20 text-cyan-300 border-cyan-500/40",
      tip: `Your league is tighter than the NHL: ${slotsN} slots / ${pctN}% max vs the CBA's ${NHL_CBA_MAX_SLOTS} / ${NHL_CBA_MAX_PCT}%. Great for keeper realism.`,
    },
  }[kind];

  const { label, Icon, cls, tip } = config;

  return (
    <TooltipProvider delayDuration={150}>
      <Tooltip>
        <TooltipTrigger asChild>
          <Badge
            variant="outline"
            className={`gap-1 cursor-help ${cls} ${className}`}
            data-testid={testId || `cba-badge-${kind}`}
          >
            <Icon className="h-3 w-3" />
            {label}
            <Info className="h-3 w-3 opacity-60" />
          </Badge>
        </TooltipTrigger>
        <TooltipContent className="max-w-xs">
          <p className="text-xs leading-snug">{tip}</p>
          <p className="text-[10px] text-muted-foreground mt-1">NHL CBA: {NHL_CBA_MAX_SLOTS} slots @ {NHL_CBA_MAX_PCT}% max.</p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}

export { NHL_CBA_MAX_SLOTS, NHL_CBA_MAX_PCT };
