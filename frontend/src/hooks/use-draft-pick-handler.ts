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
import { useCallback, useEffect, useRef, type MutableRefObject } from "react";
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

  const pending = useRef(false);
  const activeDraft = useRef(currentDraft?._id);
  activeDraft.current = currentDraft?._id;
  useEffect(() => {
    activeDraft.current = currentDraft?._id;
    return () => { activeDraft.current = undefined; };
  }, [currentDraft?._id]);

  const handleDraftPlayer = useCallback(async (chosen?: DraftEligiblePlayer | null, destination?: string) => {
    if (pending.current) return false;
    if (chosen?.drafted) { toast.info("This player has already been drafted. Refresh to choose another player."); return false; }
    const totalPicks = totalTeams * draftConfig.totalRounds;
    if (draftConfig.currentPick > totalPicks) {
      toast.info("Draft is complete.");
      return false;
    }
    const teamAbbr = getTeamForPick(draftConfig.currentPick);
    const teamFull = boardTeams.find((t) => t.abbr === teamAbbr);
    const nextPlayer = chosen && !chosen.drafted
      ? chosen
      : players.find((p) => !p.drafted);
    if (!nextPlayer) {
      toast.warning("No eligible players left to draft.");
      return false;
    }
    const round = Math.ceil(draftConfig.currentPick / totalTeams);
    const pickInRound = ((draftConfig.currentPick - 1) % totalTeams) + 1;

    // Backend round-trip when a real draft is active.
    if (currentDraft?._id && isDraftActive && /^[0-9a-fA-F]{24}$/.test(String(nextPlayer.id))) {
      const draftId = currentDraft._id;
      const expectedPick = draftConfig.currentPick;
      pending.current = true;
      let saved = false;
      const hydrate = (data: any) => {
        if (activeDraft.current !== draftId) return;
        setCurrentDraft(data);
        setPicks(() => (data.picks || []).map((p: any) => ({
          round: p.round, pickInRound: p.pick_in_round, overall: p.overall,
          team: p.team, player: p.player,
          auto_picked: !!p.auto_picked, auto_pick_via: p.auto_pick_via,
        })));
        setDraftConfig(prev => ({...prev, currentPick: data.current_pick}));
        const draftedIds = new Set((data.picks || []).map((p: any) => String(p.player_id || p.player?.id || "")));
        setPlayers(prev => prev.map(p => draftedIds.has(String(p.id)) ? {...p, drafted: true} : p));
        setRosterReloadTick(t => t + 1);
      };
      const finish = () => {
        if (activeDraft.current !== draftId) return false;
        setLastPickedPlayerId(String(nextPlayer.id));
        setSelectedPlayerId(null);
        toast.success(`${teamFull?.name || teamAbbr} drafted ${nextPlayer.name}`);
        return true;
      };
      try {
        lastSelfPickRef.current = `${expectedPick}-${nextPlayer.id}`;
        const pickResponse = await api.post(`/drafts/${draftId}/pick`, { player_id: nextPlayer.id, destination, expected_pick: expectedPick });
        saved = true;
        if (activeDraft.current !== draftId) return false;
        if (pickResponse.data.salary_validation?.feasible === false) toast.warning(pickResponse.data.salary_validation.message);
        const {data} = await api.get(`/drafts/${draftId}`);
        hydrate(data);
        return finish();
      } catch (e: any) {
        if (activeDraft.current !== draftId) return false;
        try {
          const {data} = await api.get(`/drafts/${draftId}`);
          hydrate(data);
          const committed = (data.picks || []).some((p: any) =>
            p.overall === expectedPick && String(p.player_id || p.player?.id) === String(nextPlayer.id));
          if (committed) return finish();
        } catch {
          if (activeDraft.current !== draftId) return false;
          if (saved) {
            setPlayers(prev => prev.map(p => p.id === nextPlayer.id ? {...p, drafted: true} : p));
            setSelectedPlayerId(null);
            setRosterReloadTick(t => t + 1);
            toast.warning("Pick saved; reconnect to refresh draft totals.");
            return true;
          }
          toast.warning("Pick outcome unconfirmed", {description: "Reconnect and refresh the draft before trying again."});
          return false;
        }
        const detail = e?.response?.data?.detail;
        const description = typeof detail === "string" ? detail : detail?.message;
        toast.error("Pick not applied", {description: description || "The current draft has been refreshed. Check the player and try again."});
        return false;
      } finally {
        pending.current = false;
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
    return true;
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
