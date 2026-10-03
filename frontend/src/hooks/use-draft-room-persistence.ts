// @ts-nocheck
/**
 * Iter 205 — Draft Room state persistence hook (extracted from DraftRoom.tsx).
 *
 * Mirrors `picks`, `currentPick`, `draftStarted`, and `lastPickedPlayerId`
 * into localStorage keyed by active league id, so a manager who reloads
 * the page mid-draft doesn't lose progress. (The real `/drafts/{id}/pick`
 * backend wiring is the canonical source of truth; this localStorage
 * mirror is a P3 fallback for the local mock/demo path that pre-dates
 * the backend draft.)
 *
 * Two effects:
 *   • On mount + league change → hydrate state from localStorage once.
 *   • On any tracked field change → persist to localStorage.
 */
import { useEffect, useRef } from "react";

export default function useDraftRoomPersistence({
  leagueId,
  picks,
  currentPick,
  draftStarted,
  lastPickedPlayerId,
  setPicks,
  setPlayers,
  setDraftConfig,
  setLastPickedPlayerId,
}: {
  leagueId?: string;
  picks: any[];
  currentPick: number;
  draftStarted: boolean;
  lastPickedPlayerId: string | null;
  setPicks: (p: any[]) => void;
  setPlayers: (updater: any) => void;
  setDraftConfig: (updater: any) => void;
  setLastPickedPlayerId: (id: string) => void;
}) {
  const draftStorageKey = leagueId ? `draftroom-state-v1:${leagueId}` : null;
  const hasHydratedRef = useRef(false);

  // ── Hydrate from localStorage once per league ──
  useEffect(() => {
    if (!draftStorageKey || hasHydratedRef.current) return;
    try {
      const raw = localStorage.getItem(draftStorageKey);
      if (!raw) {
        hasHydratedRef.current = true;
        return;
      }
      const data = JSON.parse(raw);
      if (Array.isArray(data.picks) && data.picks.length > 0) {
        setPicks(data.picks);
        const draftedIds = new Set(
          data.picks
            .map((p: any) => p.player?.id)
            .filter((id: any) => id !== undefined && id !== null)
            .map(String),
        );
        if (draftedIds.size > 0) {
          setPlayers((prev: any[]) =>
            prev.map((p: any) =>
              draftedIds.has(String(p.id)) ? { ...p, drafted: true } : p,
            ),
          );
        }
      }
      if (typeof data.currentPick === "number") {
        setDraftConfig((prev: any) => ({
          ...prev,
          currentPick: data.currentPick,
          draftStarted: !!data.draftStarted,
        }));
      }
      if (data.lastPickedPlayerId) {
        setLastPickedPlayerId(String(data.lastPickedPlayerId));
      }
    } catch {
      /* ignore parse errors */
    }
    hasHydratedRef.current = true;
  }, [draftStorageKey]);

  // ── Persist on every tracked change ──
  useEffect(() => {
    if (!draftStorageKey || !hasHydratedRef.current) return;
    try {
      localStorage.setItem(
        draftStorageKey,
        JSON.stringify({
          picks,
          currentPick,
          draftStarted,
          lastPickedPlayerId,
        }),
      );
    } catch {
      /* storage quota — non-fatal */
    }
  }, [draftStorageKey, picks, currentPick, draftStarted, lastPickedPlayerId]);
}
