// @ts-nocheck
import { useCallback, useMemo } from "react";
import type { DraftPick } from "@/lovable/pages/draftroom/types";

/**
 * Iter 230v — Pick-grid derivation extracted from DraftRoom.tsx.
 *
 * Owns the three intertwined pure-derivations that the Draft Board
 * and Draft Live tile need:
 *
 *   • `getDraftOrder(round)`    — snake-aware team order for the round
 *   • `getTeamForPick(overall)` — which team owns the overall pick #
 *   • `allPicks`                — full grid of `DraftPick[][]` rows
 *
 * Plus the convenience scalars `currentRound` / `currentPickInRound`
 * read by the on-the-clock UI.
 *
 * Keeping these as a single hook avoids passing 4 different setters
 * to the Draft Board component and keeps the snake-draft branching
 * in one place.
 */
export default function useDraftPickGrid({
  boardTeamAbbrs,
  totalTeams,
  snakeDraft,
  totalRounds,
  currentPick,
  picks,
}: {
  boardTeamAbbrs: string[];
  totalTeams: number;
  snakeDraft: boolean;
  totalRounds: number;
  currentPick: number;
  picks: DraftPick[];
}) {
  const getDraftOrder = useCallback(
    (round: number): string[] => {
      if (snakeDraft && round % 2 === 0) return [...boardTeamAbbrs].reverse();
      return boardTeamAbbrs;
    },
    [snakeDraft, boardTeamAbbrs]
  );

  const getTeamForPick = useCallback(
    (overall: number): string => {
      const round = Math.ceil(overall / totalTeams);
      const pickInRound = (overall - 1) % totalTeams;
      const order = getDraftOrder(round);
      return order[pickInRound];
    },
    [getDraftOrder, totalTeams]
  );

  const allPicks = useMemo(() => {
    const grid: DraftPick[][] = [];
    for (let r = 1; r <= totalRounds; r++) {
      const order = getDraftOrder(r);
      const roundPicks: DraftPick[] = order.map((team, idx) => {
        const overall = (r - 1) * totalTeams + idx + 1;
        const existing = picks.find((p) => p.overall === overall);
        return existing || { round: r, pickInRound: idx + 1, overall, team };
      });
      grid.push(roundPicks);
    }
    return grid;
  }, [picks, totalRounds, getDraftOrder, totalTeams]);

  const currentRound = Math.ceil(currentPick / totalTeams);
  const currentPickInRound = ((currentPick - 1) % totalTeams) + 1;

  return {
    getDraftOrder,
    getTeamForPick,
    allPicks,
    currentRound,
    currentPickInRound,
  };
}
