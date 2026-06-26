// @ts-nocheck
import { useEffect, useState } from "react";

/**
 * Iter 230v — Pre-draft countdown ticker extracted from DraftRoom.
 *
 * Updates every second while `scheduledTime` is in the future. Once
 * the scheduled moment arrives AND the draft hasn't already been
 * started early, flips `draftStarted: true` on the draftConfig so
 * downstream timer / pick-clock logic begins.
 */
export default function useDraftCountdown({
  scheduledTime,
  draftStarted,
  setDraftConfig,
}: {
  scheduledTime: Date | null | undefined;
  draftStarted: boolean;
  setDraftConfig: (updater: (prev: any) => any) => void;
}): number {
  const [countdown, setCountdown] = useState<number>(0);

  useEffect(() => {
    if (!scheduledTime) return;
    const interval = setInterval(() => {
      const diff = scheduledTime.getTime() - Date.now();
      setCountdown(Math.max(0, diff));
      if (diff <= 0 && !draftStarted) {
        setDraftConfig((prev) => ({ ...prev, draftStarted: true, earlyStart: false }));
      }
    }, 1000);
    return () => clearInterval(interval);
  }, [scheduledTime, draftStarted, setDraftConfig]);

  return countdown;
}
