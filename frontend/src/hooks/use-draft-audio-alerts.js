// @ts-nocheck
/**
 * Iter 229L — Extracted from DraftRoom.tsx.
 *
 * Plays soft "Next Up" chime when picksUntilMyTurn transitions to 1
 * and an urgent "On the Clock" arpeggio when it hits 0. Also flashes
 * the browser tab title while the user is on the clock and the page
 * is hidden, so a manager who tabbed away still gets cued in.
 */
import { useEffect, useRef } from 'react';
import { toast } from 'sonner';
import useDraftSounds, { useTabTitleAlert } from '@/hooks/use-draft-sounds';

export default function useDraftAudioAlerts(draftStarted, picksUntilMyTurn) {
  const draftSounds = useDraftSounds();
  const prevPicksUntilRef = useRef(null);

  useEffect(() => {
    const prev = prevPicksUntilRef.current;
    const curr = picksUntilMyTurn;
    if (
      draftStarted
      && prev !== null
      && curr !== null
      && prev !== curr
    ) {
      if (curr === 1 && prev > 1) {
        draftSounds.playNextUp();
        try {
          toast.info("You're next up", {
            description: "Your team is on the clock after this pick. Get your queue ready.",
          });
        } catch { /* toast lib missing — non-critical */ }
      } else if (curr === 0 && prev > 0) {
        draftSounds.playOnTheClock();
        try {
          toast.success("You're on the clock!", {
            description: 'Make your pick before the timer expires.',
          });
        } catch { /* toast lib missing — non-critical */ }
      }
    }
    prevPicksUntilRef.current = curr;
  }, [picksUntilMyTurn, draftStarted, draftSounds]);

  useTabTitleAlert(draftStarted && picksUntilMyTurn === 0);

  return draftSounds;
}
