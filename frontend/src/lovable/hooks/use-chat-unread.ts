// @ts-nocheck
import { useState, useEffect, useCallback } from "react";

const STORAGE_KEY = "chat-unread-count";
const DEFAULT_COUNT = 8;

function getStoredCount(): number {
  const stored = localStorage.getItem(STORAGE_KEY);
  return stored !== null ? parseInt(stored, 10) : DEFAULT_COUNT;
}

export function useChatUnread() {
  const [count, setCount] = useState(getStoredCount);

  useEffect(() => {
    const handler = () => setCount(getStoredCount());
    window.addEventListener("chat-unread-updated", handler);
    window.addEventListener("storage", handler);
    return () => {
      window.removeEventListener("chat-unread-updated", handler);
      window.removeEventListener("storage", handler);
    };
  }, []);

  const markRead = useCallback(() => {
    localStorage.setItem(STORAGE_KEY, "0");
    setCount(0);
    window.dispatchEvent(new Event("chat-unread-updated"));
  }, []);

  return { count, markRead };
}
