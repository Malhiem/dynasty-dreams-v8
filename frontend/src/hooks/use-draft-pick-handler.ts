/**
 * Iter 229h — `useDraftPickHandler`
 *
 * Extracted from DraftRoom.tsx. Wraps the ~80-line `handleDraftPlayer`
 * action that:
 *   • Picks the supplied player (when invoked from "Draft" button) OR
 *     auto-picks the top-ranked undrafted player (Simulate Pick).
 *   • Backend round-trips when an active draft exists: stamps the
 *     `lastSelfPickRef` for self-echo dedupe, POSTs to
 *     `/drafts/{id}/pick`, hydrates from the canonical GET response.
 *   • Falls back to a pure-local mock progression for Storybook /
 *     pre-draft demo mode (no backend draft yet).
 *
 * Returns:
 *   • `handleDraftPlayer(chosen?)` — the bound action.
 *   • `handleSimulatePick()`       — convenience alias the Simulate
 *     button binds to.
 */
import { useCallback, type MutableRefObject } from "react";
import api from "@/lib/api";
import { toast } from "sonner";
import type {
  DraftEligiblePlayer,
  DraftPick,
  DraftConfig,
  ChatMessage,
} from "@/lovable/pages/draftroom/types";

interface BoardTeam { id?: string; name: string; abbr: string }

interface DraftPickHandlerDeps {
  currentDraft: { _id?: string } | null;
  isDraftActive: boolean;
  draftConfig: DraftConfig;
  totalTeams: number;
  players: DraftEligiblePlayer[];
  boardTeams: BoardTeam[];
  getTeamForPick: (pickOverall: number) => string;
  lastSelfPickRef: MutableRefObject<string | null>;
  setCurrentDraft: (d: any) => void;
  setPicks: (updater: (prev: DraftPick[]) => DraftPick[]) => void;
  setDraftConfig: (updater: (prev: DraftConfig) => DraftConfig) => void;
  setPlayers: (updater: (prev: DraftEligiblePlayer[]) => DraftEligiblePlayer[]) => void;
  setChatMessages: (updater: (prev: ChatMessage[]) => ChatMessage[]) => void;
  setLastPickedPlayerId: (id: string | null) => void;
  setSelectedPlayerId: (id: string | null) => void;
  setRosterReloadTick: (updater: (t: number) => number) => void;
}

export function useDraftPickHandler(deps: DraftPickHandlerDeps) {
  const {
    currentDraft, isDraftActive, draftConfig, totalTeams, players, boardTeams,
    getTeamForPick, lastSelfPickRef,
    setCurrentDraft, setPicks, setDraftConfig, setPlayers, setChatMessages,
    setLastPickedPlayerId, setSelectedPlayerId, setRosterReloadTick,
  } = deps;

  const handleDraftPlayer = useCallback(async (chosen?: DraftEligiblePlayer | null) => {
    const totalPicks = totalTeams * draftConfig.totalRounds;
    if (draftConfig.currentPick > totalPicks) {
      toast.info("Draft is complete.");
      return;
    }
    const teamAbbr = getTeamForPick(draftConfig.currentPick);
    const teamFull = boardTeams.find((t) => t.abbr === teamAbbr);
    const nextPlayer = chosen && !chosen.drafted
      ? chosen
      : players.find((p) => !p.drafted);
    if (!nextPlayer) {
      toast.warning("No eligible players left to draft.");
      return;
    }
    const round = Math.ceil(draftConfig.currentPick / totalTeams);
    const pickInRound = ((draftConfig.currentPick - 1) % totalTeams) + 1;

    // Backend round-trip when a real draft is active.
    if (currentDraft?._id && isDraftActive && /^[0-9a-fA-F]{24}$/.test(String(nextPlayer.id))) {
      try {
        // Stamp the self-action so our own Socket.IO echo doesn't
        // double-toast (Iter 170i).
        lastSelfPickRef.current = `${draftConfig.currentPick}-${nextPlayer.id}`;
        await api.post(`/drafts/${currentDraft._id}/pick`, { player_id: nextPlayer.id });
        const { data } = await api.get(`/drafts/${currentDraft._id}`);
        setCurrentDraft(data);
        setPicks(() => (data.picks || []).map((p: any) => ({
          round: p.round, pickInRound: p.pick_in_round, overall: p.overall,
          team: p.team, player: p.player,
          auto_picked: !!p.auto_picked, auto_pick_via: p.auto_pick_via,
        })));
        setDraftConfig((prev) => ({ ...prev, currentPick: data.current_pick }));
        setPlayers((prev) =>
          prev.map((p) => p.id === nextPlayer.id ? { ...p, drafted: true } : p),
        );
        setLastPickedPlayerId(String(nextPlayer.id));
        setSelectedPlayerId(null);
        setRosterReloadTick((t) => t + 1);
        toast.success(`${teamFull?.name || teamAbbr} drafted ${nextPlayer.name}`);
        return;
      } catch (e: any) {
        toast.error("Pick failed", { description: e?.response?.data?.detail || e?.message });
        return;
      }
    }

    // Local-only mock progression (no backend draft yet).
    setPlayers((prev) =>
      prev.map((p) =>
        p.id === nextPlayer.id
          ? { ...p, drafted: true, draftedBy: teamAbbr, draftedRound: round, draftedPick: pickInRound }
          : p,
      ),
    );
    setPicks((prev) => [
      ...prev,
      {
        round,
        pickInRound,
        overall: draftConfig.currentPick,
        team: teamAbbr,
        player: { ...nextPlayer, drafted: true, draftedBy: teamAbbr, draftedRound: round, draftedPick: pickInRound },
      } as DraftPick,
    ]);
    setChatMessages((prev) => [
      ...prev,
      {
        id: `pick-${Date.now()}`,
        type: "pick",
        sender: "System",
        text: `${teamFull?.name || teamAbbr} selects ${nextPlayer.name} (${nextPlayer.position}) at #${draftConfig.currentPick}`,
        timestamp: new Date(),
      },
    ]);
    setLastPickedPlayerId(String(nextPlayer.id));
    setSelectedPlayerId(null);
    setDraftConfig((prev) => ({ ...prev, currentPick: prev.currentPick + 1 }));
  }, [
    currentDraft, isDraftActive, draftConfig, totalTeams, players, boardTeams,
    getTeamForPick, lastSelfPickRef,
    setCurrentDraft, setPicks, setDraftConfig, setPlayers, setChatMessages,
    setLastPickedPlayerId, setSelectedPlayerId, setRosterReloadTick,
  ]);

  const handleSimulatePick = useCallback(() => { handleDraftPlayer(); }, [handleDraftPlayer]);

  return { handleDraftPlayer, handleSimulatePick };
}

export default useDraftPickHandler;
