// @ts-nocheck
/**
 * Iter 203 — Draft Room WebSocket hook (extracted from DraftRoom.tsx).
 *
 * Centralizes the Socket.IO subscription for a live draft room. Returns
 * the latest `draft_chat` payload (used by `PickTradeReviewPill`) and
 * dispatches into caller-provided handlers for refresh + chat updates.
 *
 * Callers must pass:
 *   - `roomId`           : "draft_<draft_id>" or null when no draft is active
 *   - `userId`           : current user id (forwarded to useSocket)
 *   - `refreshDraftState`: () => void — refetch canonical draft state
 *   - `setChatMessages`  : React setter for the local chat log
 *   - `boardTeams`       : [{name, abbr}, ...] — used to humanize toast text
 *   - `lastSelfPickRef`  : ref containing `${overall}-${player_id}` for the
 *                         current user's own pending pick, so we don't
 *                         double-toast it.
 */
import { useState } from "react";
import { useSocket } from "@/hooks/use-socket";
import { toast } from "sonner";

export default function useDraftRoomSocket({
  roomId,
  userId,
  refreshDraftState,
  setChatMessages,
  boardTeams,
  lastSelfPickRef,
}: {
  roomId: string | null;
  userId?: string;
  refreshDraftState: () => void | Promise<void>;
  setChatMessages: (updater: any) => void;
  boardTeams: Array<{ name: string; abbr: string }>;
  lastSelfPickRef: React.MutableRefObject<string | null>;
}) {
  // Iter 194c — latest `draft_chat` payload forwarded to the
  // PickTradeReviewPill so it can react to pick_trade_* kinds.
  const [lastChatEvent, setLastChatEvent] = useState<any>(null);

  useSocket(
    roomId,
    {
      draft_pick: (p: any) => {
        refreshDraftState();
        // Skip the toast if this is the echo of OUR pick (we already
        // toasted locally in handleDraftPlayer).
        const sig = `${p?.overall}-${p?.player_id}`;
        if (sig && sig !== lastSelfPickRef.current) {
          const team =
            boardTeams.find((t) => t.abbr === p?.team)?.name || p?.team || "A team";
          toast.info(`${team} drafted ${p?.player?.name || "a player"}`, {
            description: `Pick #${p?.overall} · ${p?.player?.position || ""} ${p?.player?.nhlTeam || ""}`.trim(),
          });
        }
      },
      draft_undo: (p: any) => {
        refreshDraftState();
        const count = p?.count || 1;
        const onClk = p?.on_the_clock
          ? boardTeams.find((t) => t.abbr === p.on_the_clock)?.name || p.on_the_clock
          : null;
        toast.warning(`Commissioner undid ${count} pick${count === 1 ? "" : "s"}`, {
          description: onClk ? `Now on the clock: ${onClk}` : undefined,
        });
      },
      draft_pick_swapped: (p: any) => {
        refreshDraftState();
        toast.warning(`Commissioner swapped pick #${p?.overall}`, {
          description: p?.pick?.player?.name ? `Now: ${p.pick.player.name}` : undefined,
        });
      },
      draft_chat: (msg: any) => {
        // Forward every payload to the pill so it can react to
        // pick_trade_* kinds. Fresh object ref ensures the effect dep
        // fires.
        setLastChatEvent({ ...msg, _rxAt: Date.now() });
        if (!msg?.id) return;
        setChatMessages((prev: any) =>
          prev.find((m: any) => m.id === msg.id)
            ? prev
            : [
                ...prev,
                { ...msg, timestamp: new Date(msg.timestamp || Date.now()) },
              ],
        );
      },
      // Iter 203 — when the draft completes, surface a celebratory
      // toast + auto-refresh so the UI flips to its completed state.
      draft_completed: () => {
        refreshDraftState();
        toast.success("Draft complete!", {
          description: "All picks have been made. View full results in Draft History.",
          duration: 8000,
        });
      },
    },
    userId,
  );

  return { lastChatEvent, setLastChatEvent };
}
