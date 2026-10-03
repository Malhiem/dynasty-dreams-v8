// @ts-nocheck
/**
 * Iter 174 — useDraftLiveState (trade-block slice)
 *
 * Lifts the trade-block state + side-effects out of DraftRoom.tsx so the
 * page renders less, and the hook becomes testable in isolation.
 *
 * Owned state:
 *   • tradeBlockItems  — server-truth list of /trade-block listings
 *   • tradeBlockMode   — UI overlay toggle (controlled by the caller)
 *
 * Derived (memoized):
 *   • tradeBlockPlayerIds   — Set<player_id> for fast tile lookup
 *   • tradeBlockPickIds     — Set<pick_id>   for fast tile lookup
 *   • tradeBlockOverallKeys — Set<"team_id|R<round>"> for placeholder picks
 *
 * Side effects:
 *   • Polls /trade-block every 20s while the overlay is on (Iter 149).
 *   • Single-load on mount so megaphone icons paint immediately, before
 *     the manager toggles the overlay.
 *
 * Callbacks (returned for the caller to wire to UI events):
 *   • toggleMyTeamTradeBlock(player) — add/remove the user's own player
 *   • markAvailableForDraft(kind, payload) — mark a player OR a pick as
 *     available specifically for the current draft (draft_only: true).
 *
 * Future iterations may grow this into a fuller "live draft state" hook
 * (auction bids, presence, etc.); for now the trade-block slice is the
 * highest-LOC chunk worth lifting.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

type Player = { id: string | number; name?: string };

type Options = {
  leagueId?: string | null;
  myTeamId?: string | null;
  overlayActive: boolean;
};

export default function useDraftLiveState({
  leagueId,
  myTeamId,
  overlayActive,
}: Options) {
  const [tradeBlockItems, setTradeBlockItems] = useState<any[]>([]);

  // Iter 149 — fetch league trade-block listings so the overlay can paint
  // megaphone icons on player + pick tiles. Re-fetches every 20s while
  // the overlay is active so other managers' listings show up quickly.
  useEffect(() => {
    if (!leagueId) return;
    let cancelled = false;
    const load = async () => {
      try {
        const api = (await import("@/lib/api")).default;
        const { data } = await api.get(`/trade-block?league_id=${leagueId}`);
        if (!cancelled) setTradeBlockItems(Array.isArray(data) ? data : []);
      } catch { /* noop */ }
    };
    load();
    if (!overlayActive) return;
    const id = setInterval(load, 20_000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [leagueId, overlayActive]);

  const tradeBlockPlayerIds = useMemo(
    () => new Set(
      (tradeBlockItems || [])
        .filter((x) => x.item_type === "player" && x.player_id)
        .map((x) => String(x.player_id)),
    ),
    [tradeBlockItems],
  );

  const tradeBlockPickIds = useMemo(
    () => new Set(
      (tradeBlockItems || [])
        .filter((x) => x.item_type === "pick" && x.pick_id)
        .map((x) => String(x.pick_id)),
    ),
    [tradeBlockItems],
  );

  // Composite key for picks not yet assigned a `pick_id` (mock data
  // sometimes only carries overall#) so we can still light up overlays
  // on placeholder pick tiles.
  const tradeBlockOverallKeys = useMemo(
    () => new Set(
      (tradeBlockItems || [])
        .filter((x) => x.item_type === "pick")
        .map((x) => `${x.team_id || ""}|R${x.pick_round || ""}`),
    ),
    [tradeBlockItems],
  );

  const markAvailableForDraft = useCallback(
    async (kind: "player" | "pick", payload: any) => {
      if (!leagueId || !myTeamId) {
        toast.error("Join a team in this league to mark items available");
        return;
      }
      try {
        const api = (await import("@/lib/api")).default;
        const body: any = {
          item_type: kind,
          league_id: leagueId,
          team_id: myTeamId,
          draft_only: true,
        };
        if (kind === "player") body.player_id = payload.id;
        else {
          body.pick_year = payload.year;
          body.pick_round = String(payload.round);
        }
        const { data } = await api.post("/trade-block", body);
        toast.success(`Marked ${payload.name || `R${payload.round}`} available for draft`);
        setTradeBlockItems((prev) => [...prev, data]);
      } catch (e: any) {
        toast.error(e?.response?.data?.detail || "Could not mark available");
      }
    },
    [leagueId, myTeamId],
  );

  // Iter 151 — Toggle a player on/off the logged-in user's team trade
  // block. Called from TruncatedRosterPanel when the manager clicks the
  // megaphone beside one of their own players.
  const toggleMyTeamTradeBlock = useCallback(
    async (player: Player) => {
      if (!leagueId || !myTeamId || !player?.id) return;
      const existing = (tradeBlockItems || []).find(
        (x) =>
          x.item_type === "player"
          && x.team_id === myTeamId
          && String(x.player_id) === String(player.id),
      );
      const api = (await import("@/lib/api")).default;
      try {
        if (existing) {
          await api.delete(`/trade-block/${existing._id || existing.id}`);
          setTradeBlockItems((prev) =>
            prev.filter((x) => (x._id || x.id) !== (existing._id || existing.id)),
          );
          toast.success(`Removed ${player.name} from your trade block`);
        } else {
          const { data } = await api.post("/trade-block", {
            item_type: "player",
            league_id: leagueId,
            team_id: myTeamId,
            player_id: String(player.id),
          });
          setTradeBlockItems((prev) => [...prev, data]);
          toast.success(`Added ${player.name} to your trade block`);
        }
      } catch (e: any) {
        toast.error(e?.response?.data?.detail || "Trade block update failed");
      }
    },
    [leagueId, myTeamId, tradeBlockItems],
  );

  return {
    tradeBlockItems,
    setTradeBlockItems,
    tradeBlockPlayerIds,
    tradeBlockPickIds,
    tradeBlockOverallKeys,
    markAvailableForDraft,
    toggleMyTeamTradeBlock,
  };
}
