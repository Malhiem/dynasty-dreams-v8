import { useEffect, useState, useCallback, useRef } from 'react';
import api from '../lib/api';

const POLL_MS = 30000;

/** Polls /api/chat/unread for the badge dot on the Chat tab. */
export function useChatUnread(leagueId) {
  const [count, setCount] = useState(0);
  const mountedRef = useRef(true);

  const refresh = useCallback(async () => {
    try {
      const url = leagueId ? `/chat/unread?league_id=${leagueId}` : '/chat/unread';
      const { data } = await api.get(url);
      if (mountedRef.current) setCount(Number(data?.unread || 0));
    } catch {
      // best-effort
    }
  }, [leagueId]);

  useEffect(() => {
    mountedRef.current = true;
    refresh();
    const id = setInterval(refresh, POLL_MS);
    return () => { mountedRef.current = false; clearInterval(id); };
  }, [refresh]);

  return { count, refresh };
}
