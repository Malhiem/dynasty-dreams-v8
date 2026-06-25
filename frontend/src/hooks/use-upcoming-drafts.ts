/**
 * Iter 229d — `useUpcomingDrafts`
 * Extracted from DraftRoom.tsx. Loads the next 30 days of scheduled
 * drafts for a league so the Draft Room's draft-switcher can offer the
 * commissioner an explicit pick instead of always auto-loading the
 * most-recent one. Defaults the selection to the soonest scheduled
 * draft on first hydration.
 */
import { useEffect, useState } from "react";
import api from "@/lib/api";

export interface UpcomingDraft {
  _id?: string;
  id?: string;
  name?: string;
  scheduled_time?: string | null;
  status?: string;
  total_rounds?: number;
}

export function useUpcomingDrafts(leagueId: string | null | undefined) {
  const [upcomingDrafts, setUpcomingDrafts] = useState<UpcomingDraft[]>([]);
  const [selectedDraftId, setSelectedDraftId] = useState<string | null>(null);

  useEffect(() => {
    if (!leagueId) {
      setUpcomingDrafts([]);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const { data } = await api.get(`/leagues/${leagueId}/upcoming-drafts?days=30`);
        if (cancelled) return;
        const list: UpcomingDraft[] = Array.isArray(data?.drafts) ? data.drafts : [];
        setUpcomingDrafts(list);
        if (list.length > 0 && !selectedDraftId) {
          setSelectedDraftId(list[0]._id || list[0].id || null);
        }
      } catch {
        // Non-fatal — fall back to auto-init in the parent.
      }
    })();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [leagueId]);

  return { upcomingDrafts, selectedDraftId, setSelectedDraftId };
}

export default useUpcomingDrafts;
