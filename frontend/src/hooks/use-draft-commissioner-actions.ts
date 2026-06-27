/**
 * Iter 229g — Commissioner action handlers extracted from DraftRoom.tsx.
 *
 * Covers the four backend-touching commissioner controls:
 *   • undoPicks(count)            — POST /drafts/{id}/undo
 *   • swapPickPlayer(overall, id) — PATCH /drafts/{id}/picks/{overall}
 *   • startEarly()                — POST /drafts/{id}/start?early_start=true
 *   • startWithTimer()            — POST /drafts/{id}/start?early_start=false
 *
 * Each helper degrades gracefully when no backend draft exists yet
 * (Storybook / pre-draft demo mode), matching the original inline
 * behavior so DraftRoom rendering doesn't depend on these details.
 */
import api from "@/lib/api";
import { toast } from "sonner";
import type { DraftConfig, DraftPick } from "@/lovable/pages/draftroom/types";

interface CommissionerActionDeps {
  currentDraft: { _id?: string | null; status?: string } | null;
  // Iter 231 — leagueId enables materialising a preview draft on demand
  // when the user clicks Start Draft Early / With Timer.
  leagueId?: string | null;
  setCurrentDraft: (d: any) => void;
  refreshDraftState: () => Promise<void> | void;
  setPicks: (updater: (prev: DraftPick[]) => DraftPick[]) => void;
  setDraftConfig: (updater: (prev: DraftConfig) => DraftConfig) => void;
}

export function useDraftCommissionerActions(deps: CommissionerActionDeps) {
  const { currentDraft, leagueId, setCurrentDraft, refreshDraftState, setPicks, setDraftConfig } = deps;

  // Iter 231 — Materialise a preview draft into a real DB row on first
  // explicit commissioner action (Start / Schedule). Returns the
  // committed draft id or null if materialisation failed.
  const materialiseDraft = async (): Promise<string | null> => {
    if (currentDraft?._id) return currentDraft._id; // already real
    if (!leagueId) return null;
    try {
      const { data } = await api.post(`/drafts/auto-init/${leagueId}?commit=true`);
      const real = data?.draft;
      if (real?._id) {
        setCurrentDraft(real);
        return real._id;
      }
    } catch (e: any) {
      toast.error("Couldn't create draft", { description: e?.response?.data?.detail || e?.message });
    }
    return null;
  };

  const undoPicks = async (count: number = 1) => {
    if (!currentDraft?._id) {
      // Local-only fallback when no backend draft exists.
      setPicks((prev) => prev.slice(0, Math.max(0, prev.length - count)));
      setDraftConfig((prev) => ({ ...prev, currentPick: Math.max(1, prev.currentPick - count) }));
      return;
    }
    try {
      await api.post(`/drafts/${currentDraft._id}/undo`, { count });
      await refreshDraftState();
      toast.success(`Undid ${count} pick${count === 1 ? "" : "s"}`);
    } catch (e: any) {
      toast.error("Undo failed", { description: e?.response?.data?.detail || e?.message });
    }
  };

  const swapPickPlayer = async (overall: number, newPlayerId: string) => {
    if (!currentDraft?._id) {
      toast.info("Swap requires an active backend draft.");
      return;
    }
    try {
      await api.patch(`/drafts/${currentDraft._id}/picks/${overall}`, { new_player_id: newPlayerId });
      await refreshDraftState();
      toast.success(`Pick #${overall} swapped`);
    } catch (e: any) {
      toast.error("Swap failed", { description: e?.response?.data?.detail || e?.message });
    }
  };

  const _start = async (early: boolean) => {
    // Iter 231 — When the draft is still in preview mode (no _id),
    // materialise it first so /start has a real row to operate on.
    const draftId = await materialiseDraft();
    if (draftId && currentDraft?.status !== "active") {
      try {
        await api.post(`/drafts/${draftId}/start?early_start=${early ? "true" : "false"}`);
        const { data } = await api.get(`/drafts/${draftId}`);
        setCurrentDraft(data);
        setDraftConfig((prev) => ({
          ...prev,
          draftStarted: true,
          earlyStart: early,
          currentPick: data.current_pick,
        }));
        return;
      } catch (e: any) {
        toast.error("Couldn't start draft", { description: e?.response?.data?.detail || e?.message });
      }
    }
    setDraftConfig((prev) => ({ ...prev, draftStarted: true, earlyStart: early }));
  };

  return {
    handleUndoPicks: undoPicks,
    handleSwapPickPlayer: swapPickPlayer,
    handleEarlyStart: () => _start(true),
    handleStartWithTimer: () => _start(false),
  };
}

export default useDraftCommissionerActions;
