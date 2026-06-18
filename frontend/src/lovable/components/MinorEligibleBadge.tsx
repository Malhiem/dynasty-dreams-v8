/**
 * Iter 181 — Minor (Prospect) Eligibility Badge
 *
 * Tiny, consistent visual indicator for players who satisfy the
 * league's prospect / minor-eligible criteria. Surfaces in every
 * place a player can appear: roster tables, waivers / players
 * directory, transactions feed, trade block, draft room, and
 * depth chart.
 *
 * The eligibility data itself is computed server-side and arrives
 * as `player.minor_eligible: boolean` (set by
 * `roster_rules.compute_minor_eligibility` based on age, career
 * games played, and league `prospect_eligibility_*` thresholds).
 *
 * Usage:
 *   <MinorEligibleBadge eligible={player.minor_eligible} />
 *   <MinorEligibleBadge eligible={player.minor_eligible} size="md" />
 *
 * Rendering rules:
 *   - When `eligible` is falsy the component renders nothing (so
 *     callers can drop the prop unconditionally without an extra
 *     `if` guard wrapping the JSX).
 *   - A native `title` attribute carries the explainer string —
 *     hovers reveal "Minor-eligible prospect" without the page
 *     needing a tooltip portal.
 */
import { Sprout } from "lucide-react";

type Size = "sm" | "md";

const SIZE_MAP: Record<Size, { wrapper: string; icon: string }> = {
  sm: { wrapper: "h-4 w-4 text-[10px]", icon: "h-3 w-3" },
  md: { wrapper: "h-5 w-5 text-[11px]", icon: "h-3.5 w-3.5" },
};

export const MinorEligibleBadge = ({
  eligible,
  size = "sm",
  className = "",
}: {
  eligible?: boolean | null;
  size?: Size;
  className?: string;
}) => {
  if (!eligible) return null;
  const cls = SIZE_MAP[size];
  return (
    <span
      title="Minor-eligible prospect"
      aria-label="Minor-eligible prospect"
      data-testid="minor-eligible-badge"
      className={
        "inline-flex shrink-0 items-center justify-center rounded-full " +
        "border border-emerald-500/40 bg-emerald-500/15 text-emerald-300 " +
        cls.wrapper +
        " " +
        className
      }
    >
      <Sprout className={cls.icon} />
    </span>
  );
};

export default MinorEligibleBadge;
