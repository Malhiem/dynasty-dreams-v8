// Iter 230i — Extracted from DraftRoom.tsx. Owns the draft auto-init
// effect that fires on mount/league-change and hydrates picks +
// draftConfig + chat from the backend. Also exposes the
// `refreshDraftState` callback used by Socket.IO event handlers to
// re-pull the canonical state after a remote pick/undo/swap.
import { useCallback, useEffect } from "react";
import api from "@/lib/api";

type PickHydrated = {
  id?: string;
  round: number;
  pickInRound: number;
  overall: number;
  team: string;
  player?: any;
  auto_picked: boolean;
  auto_pick_via?: string | null;
};

type Args = {
  leagueId: string | null | undefined;
  selectedDraftId: string | null | undefined;
  currentDraftId: string | null | undefined;
  setCurrentDraft: (d: any) => void;
  setPicks: (updater: any) => void;
  setDraftConfig: (updater: any) => void;
  setLastPickedPlayerId: (id: string | null) => void;
  setMissedPickAction: (s: string) => void;
  setDeferAvailable: (a: string[]) => void;
  setChatMessages: (m: any[]) => void;
  setRosterReloadTick: (updater: any) => void;
};

function _hydratePicks(picksRaw: any[]): PickHydrated[] {
  return (picksRaw || []).map((p: any) => ({
    // Iter 228i — Stable unique key per pick.
    id: p.id || p._id || `pick-${p.round}-${p.pick_in_round || p.overall}`,
    round: p.round,
    pickInRound: p.pick_in_round,
    overall: p.overall,
    team: p.team,
    player: p.player,
    auto_picked: !!p.auto_picked,
    auto_pick_via: p.auto_pick_via,
  }));
}

export default function useDraftAutoInit({
  leagueId,
  selectedDraftId,
  currentDraftId,
  setCurrentDraft,
  setPicks,
  setDraftConfig,
  setLastPickedPlayerId,
  setMissedPickAction,
  setDeferAvailable,
  setChatMessages,
  setRosterReloadTick,
}: Args) {
  // Auto-init / fetch the draft on mount + when league or
  // selected-draft id changes.
  useEffect(() => {
    if (!leagueId) {
      setCurrentDraft(null);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        // Iter 228n — When the user picked a specific draft from the
        // upcoming-drafts dropdown, load that one directly instead of
        // auto-init (which always returns the most-recent draft).
        let data: any;
        if (selectedDraftId) {
          const r = await api.get(`/drafts/${selectedDraftId}`);
          data = { draft: r.data, created: false };
        } else {
          const r = await api.post(`/drafts/auto-init/${leagueId}`);
          data = r.data;
        }
        if (cancelled) return;
        const d = data?.draft;
        if (!d) return;
        setCurrentDraft(d);
        if (Array.isArray(d.picks) && d.picks.length > 0) {
          setPicks(_hydratePicks(d.picks));
          const lastPlayerId = d.picks[d.picks.length - 1]?.player_id;
          if (lastPlayerId) setLastPickedPlayerId(String(lastPlayerId));
        }
        // Iter 228j — Always hydrate totalRounds / pickTimerSeconds.
        setDraftConfig((prev: any) => ({
          ...prev,
          currentPick: typeof d.current_pick === "number" ? d.current_pick : prev.currentPick,
          draftStarted: d.status === "active",
          totalRounds: d.total_rounds || prev.totalRounds,
          pickTimerSeconds: d.time_per_pick || prev.pickTimerSeconds,
          // Iter 228n — Anchor the "Draft starts in" countdown.
          scheduledTime: d.scheduled_time ? new Date(d.scheduled_time) : prev.scheduledTime,
        }));
        // Iter 228f — Hydrate missed_pick_action + defer_user_options.
        if (d.missed_pick_action) setMissedPickAction(d.missed_pick_action);
        if (Array.isArray(d.defer_user_options) && d.defer_user_options.length) {
          setDeferAvailable(d.defer_user_options);
        }
        // Iter 170m — Hydrate historic chat (picks + system messages).
        if (Array.isArray(d.chat_messages) && d.chat_messages.length > 0) {
          setChatMessages(
            d.chat_messages.map((m: any) => ({
              ...m,
              timestamp: new Date(m.timestamp || Date.now()),
            })),
          );
        }
      } catch (e) {
        // Non-commissioners get 403 → fall back to mock/local-only flow.
        if (!cancelled) setCurrentDraft(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [leagueId, selectedDraftId]);

  // Iter 170h — Refetch the canonical draft state + bump roster
  // reload tick. Called from Socket.IO `draft_pick` / `draft_undo` /
  // `draft_pick_swapped` handlers so every connected manager sees the
  // board update in real time without polling.
  const refreshDraftState = useCallback(async () => {
    if (!currentDraftId) return;
    try {
      const { data } = await api.get(`/drafts/${currentDraftId}`);
      setCurrentDraft(data);
      setPicks(
        (data.picks || []).map((p: any) => ({
          round: p.round,
          pickInRound: p.pick_in_round,
          overall: p.overall,
          team: p.team,
          player: p.player,
          auto_picked: !!p.auto_picked,
          auto_pick_via: p.auto_pick_via,
        })),
      );
      setDraftConfig((prev: any) => ({ ...prev, currentPick: data.current_pick }));
      setRosterReloadTick((t: number) => t + 1);
      // Iter 170m — Keep chat in sync with backend on every refresh.
      if (Array.isArray(data.chat_messages)) {
        setChatMessages(
          data.chat_messages.map((m: any) => ({
            ...m,
            timestamp: new Date(m.timestamp || Date.now()),
          })),
        );
      }
    } catch {
      /* ignore — will retry on next event */
    }
  }, [currentDraftId]);

  return { refreshDraftState };
}
