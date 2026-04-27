// @ts-nocheck
/**
 * Polls /api/chat/unread every 30s and exposes the aggregate unread count
 * for the sidebar badge. `markRead()` triggers an immediate refresh after
 * the user views any channel (which already updates the read cursor on
 * the server inside list_messages).
 */
import { useState, useEffect, useCallback, useRef } from "react";
import api from "@/lib/api";

const POLL_MS = 30_000;
const REFRESH_EVENT = "chat-unread-updated";

export function useChatUnread() {
  const [count, setCount] = useState(0);
  const [byChannel, setByChannel] = useState({});
  const mountedRef = useRef(true);

  const refresh = useCallback(async () => {
    try {
      const { data } = await api.get("/chat/unread");
      if (!mountedRef.current) return;
      setCount(Number(data?.unread || 0));
      setByChannel(data?.by_channel || {});
    } catch (e) {
      // Silently swallow — unread badge is best-effort
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    refresh();
    const id = setInterval(refresh, POLL_MS);
    const handler = () => refresh();
    window.addEventListener(REFRESH_EVENT, handler);
    return () => {
      mountedRef.current = false;
      clearInterval(id);
      window.removeEventListener(REFRESH_EVENT, handler);
    };
  }, [refresh]);

  const markRead = useCallback(() => {
    // The server already moves the read cursor when /messages is fetched;
    // we just trigger a refresh shortly after so the badge updates without
    // waiting for the next 30s tick.
    setTimeout(refresh, 250);
    window.dispatchEvent(new Event(REFRESH_EVENT));
  }, [refresh]);

  return { count, byChannel, markRead, refresh };
}
