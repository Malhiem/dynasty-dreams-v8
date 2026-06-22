// @ts-nocheck
/**
 * Iter 204 — Pick timer hook (extracted from DraftRoom.tsx).
 *
 * Encapsulates the on-the-clock countdown for the live Draft Room:
 *   • Resets `pickTimeLeft` to `pickTimerSeconds` whenever the active
 *     pick changes (or the clock becomes active).
 *   • Decrements `pickTimeLeft` every second when the clock is active
 *     and not paused.
 *   • On expiry, fires the backend `/drafts/{id}/auto-pick` endpoint
 *     for the on-clock team (once per pick, guarded by a ref) when a
 *     real draft is active.
 *
 * Returns the timer state slots + the pause/resume setter so the
 * Draft Room JSX can render the countdown chip and pause toggle.
 */
import { useEffect, useRef, useState } from "react";
import api from "@/lib/api";

export default function usePickTimer({
  isClockActive,
  pickTimerSeconds,
  currentPick,
  currentDraftId,
  isDraftActive,
  refreshDraftState,
}: {
  isClockActive: boolean;
  pickTimerSeconds: number;
  currentPick: number;
  currentDraftId?: string | null;
  isDraftActive: boolean;
  refreshDraftState: () => Promise<void> | void;
}) {
  const [pickTimeLeft, setPickTimeLeft] = useState<number>(pickTimerSeconds);
  const [timerPaused, setTimerPaused] = useState(false);

  // Reset on clock activation or pick advance.
  useEffect(() => {
    if (!isClockActive) return;
    setPickTimeLeft(pickTimerSeconds);
    setTimerPaused(false);
  }, [isClockActive, currentPick, pickTimerSeconds]);

  // Countdown tick + backend auto-pick on expiry.
  const lastAutoFireRef = useRef<number | null>(null);
  useEffect(() => {
    lastAutoFireRef.current = null;
  }, [currentPick]);

  useEffect(() => {
    if (!isClockActive || timerPaused) return;
    const interval = setInterval(() => {
      setPickTimeLeft((prev) => {
        if (prev <= 1) {
          if (currentDraftId && isDraftActive && lastAutoFireRef.current !== currentPick) {
            lastAutoFireRef.current = currentPick;
            api
              .post(`/drafts/${currentDraftId}/auto-pick`)
              .then(() => refreshDraftState())
              .catch(() => {
                /* ignore — next tick will retry */
              });
          }
          return pickTimerSeconds;
        }
        return prev - 1;
      });
    }, 1000);
    return () => clearInterval(interval);
  }, [
    isClockActive,
    timerPaused,
    pickTimerSeconds,
    currentPick,
    currentDraftId,
    isDraftActive,
    refreshDraftState,
  ]);

  return { pickTimeLeft, setPickTimeLeft, timerPaused, setTimerPaused };
}
