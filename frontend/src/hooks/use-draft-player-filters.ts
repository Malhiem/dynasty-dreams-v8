// @ts-nocheck
import { useCallback, useMemo } from "react";
import type { DraftEligiblePlayer } from "@/lovable/pages/draftroom/types";

/**
 * Iter 230v — Player filter / shortlist / queue derivation extracted
 * from DraftRoom.tsx.
 *
 * Owns the three memoised player collections (`filteredPlayers`,
 * `shortlistedPlayers`, `queuedPlayers`) plus the trio of mutation
 * helpers that toggle membership in the shortlist / queue arrays.
 *
 * The component still owns the underlying state arrays (`shortlist`,
 * `queue`) because they're also persisted via
 * `useDraftQueueShortlistPersistence` — passing the raw setters in
 * keeps this hook a pure derivation layer.
 */
export default function useDraftPlayerFilters({
  players,
  searchQuery,
  positionFilter,
  shortlist,
  setShortlist,
  queue,
  setQueue,
}: {
  players: DraftEligiblePlayer[];
  searchQuery: string;
  positionFilter: string;
  shortlist: string[];
  setShortlist: (updater: (prev: string[]) => string[]) => void;
  queue: string[];
  setQueue: (updater: (prev: string[]) => string[]) => void;
}) {
  const filteredPlayers = useMemo(() => {
    return players
      .filter((p) => !p.drafted)
      .filter((p) => {
        const matchesSearch = p.name.toLowerCase().includes(searchQuery.toLowerCase());
        const matchesPos = positionFilter === "all" || p.position === positionFilter;
        return matchesSearch && matchesPos;
      })
      .sort((a, b) => a.ranking - b.ranking);
  }, [players, searchQuery, positionFilter]);

  // Iter 170l — preserve the manager's drag-ordered shortlist (was
  // sorted by global ranking before, which made drag-to-reorder
  // visually no-op).
  const shortlistedPlayers = useMemo(() => {
    return shortlist
      .map((id) => players.find((p) => p.id === id))
      .filter((p): p is DraftEligiblePlayer => !!p && !p.drafted);
  }, [players, shortlist]);

  const queuedPlayers = useMemo(() => {
    return queue
      .map((id) => players.find((p) => p.id === id))
      .filter((p): p is DraftEligiblePlayer => !!p && !p.drafted);
  }, [queue, players]);

  const toggleShortlist = useCallback(
    (playerId: string) => {
      setShortlist((prev) =>
        prev.includes(playerId) ? prev.filter((id) => id !== playerId) : [...prev, playerId]
      );
    },
    [setShortlist]
  );

  const toggleQueue = useCallback(
    (playerId: string) => {
      setQueue((prev) =>
        prev.includes(playerId) ? prev.filter((id) => id !== playerId) : [...prev, playerId]
      );
    },
    [setQueue]
  );

  const removeFromQueue = useCallback(
    (playerId: string) => {
      setQueue((prev) => prev.filter((id) => id !== playerId));
    },
    [setQueue]
  );

  return {
    filteredPlayers,
    shortlistedPlayers,
    queuedPlayers,
    toggleShortlist,
    toggleQueue,
    removeFromQueue,
  };
}
