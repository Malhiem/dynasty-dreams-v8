// @ts-nocheck
/**
 * Iter 229L — Extracted from DraftRoom.tsx.
 *
 * Hydrates + debounce-persists the user's draft queue + shortlist
 * via `/teams/{id}/draft-queue` and `/teams/{id}/shortlist`.
 * Hydration runs once per team-id change; persistence runs after
 * a 400ms debounce on every queue/shortlist mutation.
 */
import { useEffect, useRef } from 'react';
import api from '@/lib/api';

export default function useDraftQueueShortlistPersistence({
  myTeamId,
  queue,
  setQueue,
  shortlist,
  setShortlist,
}) {
  const hasHydratedQueueRef = useRef(false);
  const hasHydratedShortlistRef = useRef(false);

  useEffect(() => {
    if (!myTeamId) return;
    hasHydratedQueueRef.current = false;
    hasHydratedShortlistRef.current = false;
    api.get(`/teams/${myTeamId}/draft-queue`)
      .then(({ data }) => {
        setQueue((data?.draft_queue || []).map(String));
        hasHydratedQueueRef.current = true;
      })
      .catch(() => { hasHydratedQueueRef.current = true; });
    api.get(`/teams/${myTeamId}/shortlist`)
      .then(({ data }) => {
        setShortlist((data?.shortlist || []).map(String));
        hasHydratedShortlistRef.current = true;
      })
      .catch(() => { hasHydratedShortlistRef.current = true; });
  }, [myTeamId, setQueue, setShortlist]);

  useEffect(() => {
    if (!myTeamId || !hasHydratedQueueRef.current) return;
    const t = setTimeout(() => {
      api.put(`/teams/${myTeamId}/draft-queue`, { player_ids: queue })
        .catch(() => { /* non-fatal */ });
    }, 400);
    return () => clearTimeout(t);
  }, [queue, myTeamId]);

  useEffect(() => {
    if (!myTeamId || !hasHydratedShortlistRef.current) return;
    const t = setTimeout(() => {
      api.put(`/teams/${myTeamId}/shortlist`, { player_ids: shortlist })
        .catch(() => { /* non-fatal */ });
    }, 400);
    return () => clearTimeout(t);
  }, [shortlist, myTeamId]);
}
