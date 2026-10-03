// @ts-nocheck
/**
 * Iter 229L — Extracted from DraftRoom.tsx.
 *
 * When the expanded player has a real Mongo ObjectId, refetch the
 * full record (NHL stats, contract, schedule) and merge over the
 * lean preview shape so the modal renders real numbers without
 * losing the fallback fields.
 */
import { useEffect } from 'react';
import api from '@/lib/api';

const OBJ_ID = /^[0-9a-fA-F]{24}$/;

export default function useExpandedPlayerFetch(expandedPlayer, setExpandedPlayer, leagueId) {
  useEffect(() => {
    if (!expandedPlayer?.id) return;
    if (!OBJ_ID.test(String(expandedPlayer.id))) return;
    let cancelled = false;
    (async () => {
      try {
        const params = leagueId ? { league_id: leagueId } : undefined;
        const { data } = await api.get(`/players/${expandedPlayer.id}`, { params });
        if (cancelled || !data) return;
        setExpandedPlayer((prev) => ({
          ...prev,
          ...data,
          id: prev.id,
          categoryBreakdown: {
            G:   data.goals ?? prev.categoryBreakdown?.G ?? 0,
            A:   data.assists ?? prev.categoryBreakdown?.A ?? 0,
            PTS: data.points ?? prev.categoryBreakdown?.PTS ?? 0,
            PPP: data.power_play_points ?? prev.categoryBreakdown?.PPP ?? 0,
            SOG: data.shots ?? prev.categoryBreakdown?.SOG ?? 0,
            HIT: data.hits ?? prev.categoryBreakdown?.HIT ?? 0,
            BLK: data.blocks ?? prev.categoryBreakdown?.BLK ?? 0,
            PIM: data.penalty_minutes ?? prev.categoryBreakdown?.PIM ?? 0,
          },
          statsByPeriod: {
            ...(prev.statsByPeriod || {}),
            season: data.fantasy_points ?? data.points ?? prev.statsByPeriod?.season ?? 0,
          },
          points: data.fantasy_points ?? data.points ?? prev.points ?? 0,
        }));
      } catch {
        /* silent — modal already has the fallback shape */
      }
    })();
    return () => { cancelled = true; };
  }, [expandedPlayer?.id, leagueId, setExpandedPlayer]);
}
