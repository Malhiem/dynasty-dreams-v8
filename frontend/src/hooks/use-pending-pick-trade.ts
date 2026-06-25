/**
 * Iter 229d — `usePendingPickTrade`
 * Extracted from DraftRoom.tsx. On league change, hydrates any pick
 * trade already sitting in `pending_draft_review` so a refreshed Draft
 * Room still shows the floating review pill (simulating a fresh
 * `pick_trade_proposed` WS event for the pill component).
 */
import { useEffect } from "react";
import api from "@/lib/api";

type SetLastChatEvent = (e: {
  type: string;
  kind: string;
  trade_id: string;
  _rxAt: number;
  _hydrated: boolean;
}) => void;

export function usePendingPickTrade(
  leagueId: string | null | undefined,
  setLastChatEvent: SetLastChatEvent,
) {
  useEffect(() => {
    if (!leagueId) return;
    let cancelled = false;
    (async () => {
      try {
        const { data } = await api.get(`/drafts/${leagueId}/pick-trades/pending`);
        const pending = (data?.pending || [])[0];
        if (!cancelled && pending?.trade_id) {
          setLastChatEvent({
            type: "draft_chat",
            kind: "pick_trade_proposed",
            trade_id: pending.trade_id,
            _rxAt: Date.now(),
            _hydrated: true,
          });
        }
      } catch {
        /* non-blocking */
      }
    })();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [leagueId]);
}

export default usePendingPickTrade;
