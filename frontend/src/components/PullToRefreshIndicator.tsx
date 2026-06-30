/**
 * Iter 231at — `<PullToRefreshIndicator />`
 *
 * The visual chrome for `usePullToRefresh`. Render as a sibling of
 * page content (NOT inside a scroll container) so the fixed-position
 * cue lives above the layout. Two states:
 *
 *   • Dragging (engaged && !refreshing) — chevron rotates as the user
 *     pulls past the threshold to communicate "release to refresh".
 *   • Refreshing — chevron swaps for a spinner so the user gets a
 *     deterministic "we heard you" before the page repaints.
 *
 * Mobile-only by virtue of the hook ignoring non-touch devices.
 */
import { ArrowDown, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

interface Props {
  distance: number;
  refreshing: boolean;
  engaged: boolean;
  threshold?: number;
}

export default function PullToRefreshIndicator({
  distance,
  refreshing,
  engaged,
  threshold = 70,
}: Props) {
  // Hide entirely when idle so SSR + Tailwind purge can dead-code
  // the wrapper class.
  if (!engaged && !refreshing) return null;

  const pastThreshold = distance >= threshold;
  // Linear rotation up to threshold, hold at 180° beyond.
  const rotation = Math.min(180, (distance / threshold) * 180);
  // Fade in over the first 20px so subtle taps don't flash the cue.
  const opacity = Math.min(1, distance / 28);

  return (
    <div
      className="fixed left-0 right-0 top-0 z-[1100] flex justify-center pointer-events-none"
      style={{
        transform: `translate3d(0, ${Math.max(0, distance - 50)}px, 0)`,
        opacity,
        transition: refreshing ? "transform 200ms ease-out" : "none",
      }}
      data-testid="pull-to-refresh-indicator"
      role="status"
      aria-live="polite"
      aria-label={refreshing ? "Refreshing" : pastThreshold ? "Release to refresh" : "Pull down to refresh"}
    >
      <div
        className={cn(
          "mt-[max(env(safe-area-inset-top),0.5rem)]",
          "flex h-10 w-10 items-center justify-center rounded-full",
          "border border-[#00D2FF]/30 bg-[#0F0F14]/95 backdrop-blur-md shadow-lg shadow-[#00D2FF]/10",
        )}
      >
        {refreshing ? (
          <Loader2
            className="h-5 w-5 text-[#00D2FF] animate-spin"
            data-testid="pull-to-refresh-spinner"
          />
        ) : (
          <ArrowDown
            className={cn(
              "h-5 w-5 text-[#00D2FF] transition-transform",
              pastThreshold ? "text-emerald-400" : "",
            )}
            style={{ transform: `rotate(${rotation}deg)` }}
            data-testid="pull-to-refresh-chevron"
          />
        )}
      </div>
    </div>
  );
}
