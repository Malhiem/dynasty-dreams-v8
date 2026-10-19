import { useRef, useState, type Dispatch, type SetStateAction } from "react";
import api from "@/lib/api";
import { toast } from "sonner";

type Intent = { channel: string; content: string; id: string };
type Options = { selectedId: string | null; draft: string; setDraft: Dispatch<SetStateAction<string>>; onSent: () => Promise<void> };
const messageId = () => Array.from(crypto.getRandomValues(new Uint8Array(16)), value => value.toString(16).padStart(2, "0")).join("");

export default function useChatSubmission({ selectedId, draft, setDraft, onSent }: Options) {
  const [sending, setSending] = useState(false);
  const busy = useRef(false);
  const intent = useRef<Intent | null>(null);
  const channel = useRef(selectedId);
  channel.current = selectedId;
  const send = async () => {
    const content = draft.trim();
    if (busy.current || !content || !selectedId) return;
    busy.current = true;
    setSending(true);
    // Retain the same intent after response loss; a completed send starts a new one.
    if (intent.current?.channel !== selectedId || intent.current?.content !== content) {
      intent.current = { channel: selectedId, content, id: messageId() };
    }
    const pending = intent.current;
    try {
      await api.post(`/chat/channels/${selectedId}/messages`, {
        content, client_message_id: pending.id,
      });
      intent.current = null;
      if (channel.current === selectedId) {
        setDraft(value => value.trim() === content ? "" : value);
        await onSent();
      }
    } catch (error: any) {
      toast.error(error?.response?.data?.detail || "Could not send message. Your draft is ready to retry.");
    } finally {
      busy.current = false;
      setSending(false);
    }
  };
  return { send, sending };
}
