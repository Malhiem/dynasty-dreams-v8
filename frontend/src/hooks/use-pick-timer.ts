// @ts-nocheck
/**
 * Iter 204 — Pick timer hook (extracted from DraftRoom.tsx).
 * Iter 230ar — Server-authoritative remaining-time computation.
 *
 * Previously this reset `pickTimeLeft = pickTimerSeconds` on every
 * mount / pick advance, so navigating into the Draft Room restarted
 * the per-pick countdown from the full duration. Now: when the caller
 * provides `currentPickStartedAt` (an ISO timestamp written by the
 * backend on draft start / each pick / undo), the remaining time is
 * computed as `pickTimerSeconds - (now - currentPickStartedAt)` and
 * stays consistent across page refreshes / reconnects.
 *
 * Falls back to the legacy "reset to full" behaviour when no server
 * timestamp is available so an offline / pre-iter-230ar draft still
 * works (just without persistence across reloads).
 */
import { useEffect, useRef, useState, useCallback } from "react";
import api from "@/lib/api";

function _computeRemaining(pickTimerSeconds: number, startedAtIso?: string | null): number {
  if (!startedAtIso) return pickTimerSeconds;
  const startMs = new Date(startedAtIso).getTime();
  if (Number.isNaN(startMs)) return pickTimerSeconds;
  const elapsed = Math.floor((Date.now() - startMs) / 1000);
  return Math.max(0, pickTimerSeconds - elapsed);
}

export default function usePickTimer({
  isClockActive,
  pickTimerSeconds,
  currentPick,
  currentDraftId,
  isDraftActive,
  refreshDraftState,
  currentPickStartedAt = null,
  deferOnExpiry = false,
  onTimerExpired,
}: {
  isClockActive: boolean;
  pickTimerSeconds: number;
  currentPick: number;
  currentDraftId?: string | null;
  isDraftActive: boolean;
  refreshDraftState: () => Promise<void> | void;
  currentPickStartedAt?: string | null;
  deferOnExpiry?: boolean;
  onTimerExpired?: (pickNo: number) => void;
}) {
  // Iter 230ar — Initialise from the server-authoritative remaining
  // time so the very first render is correct (no flash of full
  // duration).
  const [pickTimeLeft, setPickTimeLeft] = useState<number>(
    _computeRemaining(pickTimerSeconds, currentPickStartedAt),
  );
  const [timerPaused, setTimerPaused] = useState(false);

  // Iter 230ar — Re-sync from the server timestamp whenever it
  // changes (draft starts, pick advances, undo, etc.). Keeps every
  // open tab in lock-step.
  useEffect(() => {
    if (!isClockActive) return;
    setPickTimeLeft(_computeRemaining(pickTimerSeconds, currentPickStartedAt));
    setTimerPaused(false);
  }, [isClockActive, currentPick, pickTimerSeconds, currentPickStartedAt]);

  // Countdown tick + backend auto-pick on expiry.
  const lastAutoFireRef = useRef<number | null>(null);
  useEffect(() => {
    lastAutoFireRef.current = null;
  }, [currentPick]);

  const fireAutoPick = useCallback(() => {
    if (!currentDraftId || !isDraftActive) return;
    if (lastAutoFireRef.current === currentPick) return;
    lastAutoFireRef.current = currentPick;
    if (deferOnExpiry) {
      try { onTimerExpired?.(currentPick); } catch { /* noop */ }
      return;
    }
    // `expected_pick` tells the server which pick this countdown belonged to, so a
    // late or duplicate request (several browsers fire at once) can't auto-pick the
    // NEXT team's turn. The server also rejects it (409) while the clock is running.
    api.post(`/drafts/${currentDraftId}/auto-pick`, { expected_pick: currentPick }).then(() => refreshDraftState()).catch(() => {
      // ignore — if another browser, the timer worker or a commissioner already picked,
      // the next draft-state refresh shows it, and the server-side timer worker is the backstop
    });
  }, [currentDraftId, isDraftActive, currentPick, deferOnExpiry, onTimerExpired, refreshDraftState]);

  useEffect(() => {
    if (!isClockActive || timerPaused) return;
    const interval = setInterval(() => {
      // Iter 230ar — When we have a server timestamp, recompute from
      // it on each tick so drift between local Date.now() and the
      // server is bounded. Otherwise fall back to the simple -1
      // decrement.
      setPickTimeLeft((prev) => {
        const next = currentPickStartedAt
          ? _computeRemaining(pickTimerSeconds, currentPickStartedAt)
          : prev - 1;
        if (next <= 0) {
          fireAutoPick();
          return 0;
        }
        return next;
      });
    }, 1000);
    return () => clearInterval(interval);
  }, [
    isClockActive,
    timerPaused,
    pickTimerSeconds,
    currentPick,
    currentPickStartedAt,
    fireAutoPick,
  ]);

  return { pickTimeLeft, setPickTimeLeft, timerPaused, setTimerPaused };
}
