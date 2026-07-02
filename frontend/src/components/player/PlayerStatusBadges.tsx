// @ts-nocheck
// Iter 232N — Player status badges.
//
// Renders a compact icon strip for the status flags surfaced on
// eligible-players (and rostered-players, once the roster endpoint
// carries the same shape). Each icon is small, tooltip-annotated, and
// tuned to the app's dark palette so they don't compete with the
// player name for attention.
//
//   • Cross (medical)   — injured / IR
//   • Down arrow        — playing in minors (AHL / ECHL / league minors)
//   • Doc / signature   — unsigned (NHL rights not held OR contract lapsed)
//   • Sparkles          — undrafted in this fantasy league (fresh name)
//
// Multiple flags on the same player render side-by-side (e.g. an
// injured prospect playing in the AHL shows both the medical cross AND
// the down arrow). Zero-config: pass `flags` from the API response and
// the badge row is empty when none apply.
import { Cross, ArrowDownToLine, FileWarning, Sparkles } from "lucide-react";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

interface StatusFlags {
  injured?: boolean;
  in_minors?: boolean;
  unsigned?: boolean;
  undrafted?: boolean;
}

const BADGE_META: Record<keyof StatusFlags, { icon: any; tone: string; label: string }> = {
  injured: {
    icon: Cross,
    tone: "text-rose-400 border-rose-500/40 bg-rose-500/10",
    label: "Injured (IR/LTIR) — cannot contribute to scoring until activated",
  },
  in_minors: {
    icon: ArrowDownToLine,
    tone: "text-amber-300 border-amber-500/40 bg-amber-500/10",
    label: "Playing in the minors (AHL/ECHL) — not on the active NHL roster",
  },
  unsigned: {
    icon: FileWarning,
    tone: "text-purple-300 border-purple-500/40 bg-purple-500/10",
    label: "Unsigned — no active NHL contract",
  },
  undrafted: {
    icon: Sparkles,
    tone: "text-emerald-300 border-emerald-500/40 bg-emerald-500/10",
    label: "Undrafted in this fantasy league — never picked before",
  },
};

export function PlayerStatusBadges({
  flags,
  size = "sm",
  className = "",
}: {
  flags?: StatusFlags | null;
  size?: "sm" | "md";
  className?: string;
}) {
  if (!flags) return null;
  const active = (Object.keys(BADGE_META) as (keyof StatusFlags)[]).filter((k) => flags[k]);
  if (active.length === 0) return null;
  const iconSize = size === "md" ? "h-3.5 w-3.5" : "h-3 w-3";
  const boxSize = size === "md" ? "h-5 w-5" : "h-4 w-4";
  return (
    <span
      className={"inline-flex items-center gap-1 " + className}
      data-testid="player-status-badges"
    >
      {active.map((key) => {
        const meta = BADGE_META[key];
        const Icon = meta.icon;
        return (
          <Tooltip key={key}>
            <TooltipTrigger asChild>
              <span
                data-testid={`player-status-badge-${key}`}
                className={
                  "inline-flex items-center justify-center rounded-full border cursor-default " +
                  boxSize + " " + meta.tone
                }
              >
                <Icon className={iconSize} strokeWidth={2.4} />
              </span>
            </TooltipTrigger>
            <TooltipContent className="max-w-xs text-xs">{meta.label}</TooltipContent>
          </Tooltip>
        );
      })}
    </span>
  );
}
