// Iter 230i — Extracted from DraftRoom.tsx. Computes "how many picks
// until your turn" so the Draft Live tile + audio alerts can render
// a real number for the local user.
//
// Two-mode resolution:
//   • Real-league mode — `boardTeams` carries the team `id`s, so we
//     match `myTeam.id` directly.
//   • Mock-data fallback — Storybook / standalone demo passes an
//     abbreviation-only board, so we walk a small set of abbr
//     candidates (logo_abbr, derived initials, name slice) and pick
//     whichever one appears on the board.
import { useMemo } from "react";

type BoardTeam = { id?: string | null; abbr: string; name?: string };

type Args = {
  myTeam: { id?: string; abbr?: string; logo_abbr?: string; name?: string } | null;
  boardTeams: BoardTeam[];
  boardTeamAbbrs: string[];
  currentPick: number;
  totalRounds: number;
  totalTeams: number;
  getTeamForPick: (overall: number) => string;
};

export default function useDraftPicksUntilMyTurn({
  myTeam,
  boardTeams,
  boardTeamAbbrs,
  currentPick,
  totalRounds,
  totalTeams,
  getTeamForPick,
}: Args): number | null {
  return useMemo(() => {
    if (!myTeam) return null;
    const myBoardEntry = boardTeams.find((t) => t.id && t.id === (myTeam as any).id);
    const myAbbrCandidates = new Set<string>();
    if (myBoardEntry) {
      myAbbrCandidates.add(myBoardEntry.abbr);
    } else {
      // Mock-data fallback path
      [
        (myTeam as any).abbr,
        (myTeam as any).logo_abbr,
        myTeam.name?.replace(/\s/g, "").slice(0, 3).toUpperCase(),
        myTeam.name
          ?.split(" ")
          .map((w: string) => w[0] || "")
          .join("")
          .toUpperCase(),
      ]
        .filter(Boolean)
        .forEach((a: string) => {
          if (boardTeamAbbrs.includes(a)) myAbbrCandidates.add(a);
        });
      if (myAbbrCandidates.size === 0) {
        const firstLetter = myTeam.name?.charAt(0).toUpperCase();
        const fallback = boardTeamAbbrs.find((a) => a.startsWith(firstLetter || ""));
        if (fallback) myAbbrCandidates.add(fallback);
        else if (boardTeamAbbrs.length > 0)
          myAbbrCandidates.add(boardTeamAbbrs[boardTeamAbbrs.length - 1]);
      }
    }
    const totalPicks = totalTeams * totalRounds;
    for (let n = currentPick; n <= totalPicks; n++) {
      if (myAbbrCandidates.has(getTeamForPick(n))) {
        return n - currentPick;
      }
    }
    return null;
  }, [myTeam, boardTeams, boardTeamAbbrs, currentPick, totalRounds, totalTeams, getTeamForPick]);
}
