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
import { useEffect, useState } from "react";
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
  // Iter 232b — Live presence (user_ids currently in the draft room).
  // Powered by the existing socket-side `presence_state` /
  // `user_joined` / `user_left` events that the server already emits
  // on every connect/join/leave. We surface this so the DraftRoom UI
  // can mark online managers in the participants list + draft board.
  const [onlineUserIds, setOnlineUserIds] = useState<Set<string>>(new Set());

  // Reset the presence set when the room id changes (e.g. switching
  // leagues / drafts) so we don't carry stale "online" markers from
  // the previous room.
  useEffect(() => {
    setOnlineUserIds(new Set());
  }, [roomId]);

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
      // Iter 228k — Auto-seed safety net broadcast. Fires when the
      // backend transparently materialised the draft_picks rows on
      // first Draft Room load. We toast + refresh so every connected
      // manager's Trade Center / Draft Board updates instantly.
      draft_picks_seeded: (p: any) => {
        refreshDraftState();
        const n = Number(p?.picks_inserted || 0);
        if (n > 0) {
          toast.info("Draft picks generated", {
            description: `Seeded ${n} pick${n === 1 ? "" : "s"} for trade & board views.`,
          });
        }
      },
      // Iter 230ar — Refresh when the draft transitions from
      // `scheduled` → `active` (whether via the commissioner button,
      // the frontend countdown auto-boot, or the backend auto-start
      // worker). Without this hook, a user who has the Draft Room
      // open at the scheduled time would still see the pre-draft
      // countdown until they manually refreshed.
      draft_started: (p: any) => {
        refreshDraftState();
        toast.success("Draft started!", {
          description: p?.auto_started
            ? "Auto-started — clock is running."
            : "The clock is now running.",
        });
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
      // Iter 232b — Live presence wiring (same payload shape the
      // server emits for the legacy DraftRoomPage). `presence_state`
      // is the room snapshot sent when the client first joins;
      // `user_joined` / `user_left` are deltas.
      presence_state: (data: any) => {
        if (!data) return;
        setOnlineUserIds(new Set((data.user_ids || []).map(String)));
      },
      user_joined: (data: any) => {
        if (!data?.user_id) return;
        setOnlineUserIds((prev) => {
          const next = new Set(prev);
          next.add(String(data.user_id));
          return next;
        });
      },
      user_left: (data: any) => {
        if (!data?.user_id) return;
        setOnlineUserIds((prev) => {
          const next = new Set(prev);
          next.delete(String(data.user_id));
          return next;
        });
      },
    },
    userId,
  );

  return { lastChatEvent, setLastChatEvent, onlineUserIds };
}
