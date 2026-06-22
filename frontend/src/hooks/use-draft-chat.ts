// @ts-nocheck
/**
 * Iter 205 — Draft Chat hook (extracted from DraftRoom.tsx).
 *
 * Owns the local `chatInput` field and `handleSendChat` callback. The
 * `chatMessages` array remains in DraftRoom because the WS hook
 * (`useDraftRoomSocket`) writes into it and DraftLiveColumn reads from
 * it — moving it here would require lifting a callback chain back up
 * (and we lose modularity gains). The composer-level pieces — input
 * text + send handler — live here cleanly.
 */
import { useState } from "react";
import api from "@/lib/api";

export default function useDraftChat({
  currentDraftId,
  myTeamName,
  appendLocalMessage,
}: {
  currentDraftId?: string | null;
  myTeamName?: string;
  appendLocalMessage: (msg: any) => void;
}) {
  const [chatInput, setChatInput] = useState("");

  const handleSendChat = () => {
    if (!chatInput.trim()) return;
    const text = chatInput.trim();
    setChatInput("");
    // Persist outbound chat via backend so reload + every other
    // connected manager see the message. Falls back to a local
    // optimistic append when no backend draft exists.
    if (currentDraftId) {
      api.post(`/drafts/${currentDraftId}/chat`, { text }).catch(() => {
        appendLocalMessage({
          id: `chat-${Date.now()}`,
          type: "chat",
          sender: myTeamName || "You",
          text,
          timestamp: new Date(),
        });
      });
      return;
    }
    appendLocalMessage({
      id: `chat-${Date.now()}`,
      type: "chat",
      sender: myTeamName || "You",
      text,
      timestamp: new Date(),
    });
  };

  return { chatInput, setChatInput, handleSendChat };
}
