// @ts-nocheck
/**
 * Iter 187 — Lineup Lock Status Banner.
 *
 * Extracted from `PlayerRoster.tsx` JSX block (iter 103). Renders the
 * amber "Lineup locked" banner above the Team Roster when the league's
 * lineup_lock backend returns `locked: true`. Returns null when not
 * locked so the parent doesn't need to guard the render.
 *
 * Risks documented:
 *   1. `data-testid="lineup-lock-banner"` MUST be preserved — iter 103
 *      tests assert on it.
 *   2. The amber styling (bg/border) must stay visually consistent;
 *      do not change the colour tokens without updating the iter 103
 *      visual tests.
 *   3. The `next_unlock_iso` formatting uses `toLocaleString` with
 *      explicit options so locale-dependent rendering stays stable.
 */
import { AlertTriangle } from "lucide-react";

export type LockStatus = {
  locked: boolean;
  reason?: string;
  next_unlock_iso?: string | null;
} | null;

export const LineupLockBanner = ({ lockStatus }: { lockStatus: LockStatus }) => {
  if (!lockStatus?.locked) return null;
  return (
    <div
      className="px-4 py-2.5 border-b border-amber-500/40 bg-amber-500/10 flex items-start gap-2"
      data-testid="lineup-lock-banner"
    >
      <AlertTriangle className="h-4 w-4 text-amber-400 mt-0.5 shrink-0" />
      <div className="flex-1">
        <div className="text-xs font-semibold text-amber-300">
          Lineup locked — saves will be rejected
        </div>
        <div className="text-[11px] text-amber-200/80 leading-snug">
          {lockStatus.reason}
          {lockStatus.next_unlock_iso && (
            <span className="ml-1 opacity-80">
              Unlocks at {new Date(lockStatus.next_unlock_iso).toLocaleString(undefined, {
                weekday: "short",
                hour: "numeric",
                minute: "2-digit",
              })}.
            </span>
          )}
        </div>
      </div>
    </div>
  );
};
