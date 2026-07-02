// @ts-nocheck
/**
 * Iter 232N.9 — Polls the caller's pending waiver claims across their
 * active league every 60s and exposes the count for the sidebar badge
 * on the unified Free Agent nav link.
 *
 * Kept intentionally light — this is a badge signal, not a source of
 * truth. `refresh()` allows immediate re-fetch after user actions (e.g.
 * after cancelling a claim inside the panel).
 */
import { useCallback, useEffect, useRef, useState } from "react";
import api from "@/lib/api";
import { useActiveLeague } from "@/hooks/use-active-league";

const POLL_MS = 60_000;
const REFRESH_EVENT = "pending-waivers-updated";

export function usePendingWaivers() {
  const { leagueId } = useActiveLeague();
  const [count, setCount] = useState(0);
  const mountedRef = useRef(true);

  const refresh = useCallback(async () => {
    if (!leagueId) {
      if (mountedRef.current) setCount(0);
      return;
    }
    try {
      const { data } = await api.get(
        `/waivers/claims?my_claims=true&status=pending&league_id=${leagueId}`,
      );
      if (!mountedRef.current) return;
      const claims = Array.isArray(data) ? data : (data?.claims || []);
      setCount(claims.filter((c) => (c.status || "pending") === "pending").length);
    } catch {
      // Silently swallow — badge is best-effort
    }
  }, [leagueId]);

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

  return { count, refresh };
}

export function notifyPendingWaiversChanged() {
  try {
    window.dispatchEvent(new Event(REFRESH_EVENT));
  } catch { /* noop */ }
}
