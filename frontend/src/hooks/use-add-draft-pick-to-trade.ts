// Iter 230j — Extracted from DraftRoom.tsx. Wraps the trade-builder
// open + addPick sequence for "Add this future pick to a trade
// proposal" actions launched from board cells.
import { useCallback } from "react";
import { toast } from "sonner";

type LiveTeam = { id?: string; name?: string; logo_abbr?: string };

type Args = {
  myTeam: { id?: string; name?: string } | null;
  leagueId: string | null | undefined;
  liveTeams: LiveTeam[];
  tradeBuilder: {
    openBuilder: (args: { leagueId: string; myTeam: any }) => void;
    addPick: (pick: any) => void;
  };
};

export default function useAddDraftPickToTrade({
  myTeam,
  leagueId,
  liveTeams,
  tradeBuilder,
}: Args) {
  return useCallback(
    (ownerAbbr: string, round: number, overall: number, player: any) => {
      if (!myTeam) {
        toast.error("Join a team in this league to propose trades");
        return;
      }
      if (!leagueId) {
        toast.error("League context missing");
        return;
      }
      tradeBuilder.openBuilder({ leagueId, myTeam });
      const ownerTeam = (liveTeams || []).find(
        (t) => (t.logo_abbr || (t.name || "").slice(0, 3).toUpperCase()) === ownerAbbr,
      );
      const year = new Date().getFullYear();
      tradeBuilder.addPick({
        id: `draft-room-pick-${overall}`,
        year,
        round,
        ownerTeamId: ownerTeam?.id,
        ownerTeamName: ownerTeam?.name || ownerAbbr,
        originalTeamId: ownerTeam?.id,
        originalTeamName: ownerAbbr,
        label: player?.name
          ? `${year} R${round} · #${overall} (${ownerAbbr} — ${player.name})`
          : `${year} R${round} · #${overall} (${ownerAbbr})`,
      });
    },
    [myTeam, leagueId, liveTeams, tradeBuilder],
  );
}
