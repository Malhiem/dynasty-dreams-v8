/**
 * Iter 232b — `<LastUpdatedBadge />`
 *
 * Tiny "Last updated · 14s ago" label that lives next to a page
 * title and flashes green briefly whenever the underlying timestamp
 * changes (i.e. when the page has just successfully refreshed).
 *
 * Designed to pair with the pull-to-refresh hook (iter 231at / 232a)
 * so users get immediate confirmation that the gesture did its job
 * AND a continuous signal of how stale the data they're looking at
 * actually is — especially valuable during live game-day scoring
 * windows.
 *
 * Caller contract:
 *   <LastUpdatedBadge timestamp={lastUpdatedAt} />
 *
 *   • `timestamp` — number (ms epoch) when the page's data was last
 *     successfully fetched. Pass `null` / `0` while loading the
 *     initial payload; the badge renders nothing in that state so
 *     the layout doesn't jump.
 *   • Component re-ticks once per second internally so the relative
 *     time stays current without the parent re-rendering.
 *   • When `timestamp` changes (a fresh fetch resolved), the badge
 *     pulses green for ~1500ms and falls back to the muted style.
 */
import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";

interface Props {
  /**
   * Milliseconds-since-epoch when the page's data was last
   * successfully fetched. `null` / `0` hides the badge entirely.
   */
  timestamp: number | null | undefined;
  /** Optional className escape hatch. */
  className?: string;
  /** Optional test-id suffix so multiple badges on the same page can be disambiguated. */
  testIdSuffix?: string;
  /** How long to flash green after a refresh, in ms. */
  flashMs?: number;
}

function formatRelative(now: number, ts: number): string {
  const deltaSec = Math.max(0, Math.floor((now - ts) / 1000));
  if (deltaSec < 5) return "just now";
  if (deltaSec < 60) return `${deltaSec}s ago`;
  if (deltaSec < 3600) {
    const m = Math.floor(deltaSec / 60);
    return `${m}m ago`;
  }
  if (deltaSec < 86400) {
    const h = Math.floor(deltaSec / 3600);
    return `${h}h ago`;
  }
  const d = Math.floor(deltaSec / 86400);
  return `${d}d ago`;
}

export default function LastUpdatedBadge({
  timestamp,
  className,
  testIdSuffix = "",
  flashMs = 1500,
}: Props) {
  // 1Hz tick so the relative-time string keeps updating without the
  // parent component having to re-render.
  const [now, setNow] = useState<number>(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);

  // Flash green when `timestamp` changes. We compare against a ref
  // rather than putting timestamp in a useEffect dep so the very
  // first render (no previous value) does NOT trigger the flash.
  const prevTsRef = useRef<number | null | undefined>(undefined);
  const [flashing, setFlashing] = useState(false);
  useEffect(() => {
    if (prevTsRef.current !== undefined && prevTsRef.current !== timestamp && timestamp) {
      setFlashing(true);
      const id = setTimeout(() => setFlashing(false), flashMs);
      return () => clearTimeout(id);
    }
    prevTsRef.current = timestamp;
    return undefined;
  }, [timestamp, flashMs]);

  // Sync the ref the first time we get a real timestamp so a
  // subsequent identical value doesn't cause a flash.
  useEffect(() => {
    if (prevTsRef.current === undefined && timestamp) {
      prevTsRef.current = timestamp;
    }
  }, [timestamp]);

  if (!timestamp) return null;

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full",
        "px-2 py-0.5 text-[11px] font-medium leading-none",
        "border transition-colors duration-300",
        flashing
          ? "border-[#34C759]/60 bg-[#34C759]/15 text-[#34C759]"
          : "border-white/10 bg-white/[0.04] text-[#A1A1AA]",
        className,
      )}
      data-testid={`last-updated-badge${testIdSuffix ? `-${testIdSuffix}` : ""}`}
      data-flashing={flashing ? "true" : "false"}
      title={`Data last refreshed at ${new Date(timestamp).toLocaleTimeString()}`}
      aria-live="polite"
    >
      <span
        className={cn(
          "inline-block h-1.5 w-1.5 rounded-full",
          flashing ? "bg-[#34C759]" : "bg-[#A1A1AA]/60",
        )}
        aria-hidden="true"
      />
      <span>
        Last updated · <span data-testid={`last-updated-relative${testIdSuffix ? `-${testIdSuffix}` : ""}`}>{formatRelative(now, timestamp)}</span>
      </span>
    </span>
  );
}
