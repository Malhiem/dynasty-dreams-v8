// @ts-nocheck
import { useEffect, useRef, useState } from "react";
import api from "@/lib/api";

/**
 * Iter 230v — Pre-draft countdown ticker extracted from DraftRoom.
 *
 * Iter 230an — Now ALSO triggers the backend `POST /drafts/{id}/start`
 * when the countdown hits 0:00 so the draft actually transitions from
 * `scheduled` → `active` server-side (instead of the frontend silently
 * flipping `draftStarted: true` while the backend stays scheduled, the
 * old behaviour that prevented picks from persisting and stopped any
 * `draft_your_turn` notification from firing).
 *
 * Idempotent — backend returns `already_active: true` on subsequent
 * calls. The endpoint also lets non-commissioners trigger once the
 * scheduled time has elapsed (so any team's manager booting the room
 * after the clock kicks in will get the draft moving).
 */
export default function useDraftCountdown({
  scheduledTime,
  draftStarted,
  setDraftConfig,
  draftId,
}: {
  scheduledTime: Date | null | undefined;
  draftStarted: boolean;
  setDraftConfig: (updater: (prev: any) => any) => void;
  draftId?: string | null;
}): number {
  const [countdown, setCountdown] = useState<number>(0);
  const autoStartedRef = useRef<boolean>(false);

  useEffect(() => {
    if (!scheduledTime) return;
    const interval = setInterval(() => {
      const diff = scheduledTime.getTime() - Date.now();
      setCountdown(Math.max(0, diff));
      if (diff <= 0 && !draftStarted) {
        setDraftConfig((prev) => ({ ...prev, draftStarted: true, earlyStart: false }));
        // Iter 230an — Boot the draft on the backend exactly once.
        if (draftId && !autoStartedRef.current) {
          autoStartedRef.current = true;
          api.post(`/drafts/${draftId}/start`).catch((err) => {
            // Re-arm if the backend was unreachable so the next tick
            // can retry. Don't re-arm on 4xx (would loop forever).
            const status = err?.response?.status;
            if (!status || status >= 500) autoStartedRef.current = false;
          });
        }
      }
    }, 1000);
    return () => clearInterval(interval);
  }, [scheduledTime, draftStarted, setDraftConfig, draftId]);

  return countdown;
}
