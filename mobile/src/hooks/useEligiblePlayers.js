import { useCallback, useEffect, useRef, useState } from 'react';
import api from '../lib/api';
import { loadFailure } from '../lib/errors';
import { fetchEligible, mergePlayers } from '../lib/eligible';

// Paged, searchable eligible-player list for a draft.
//   loadMore()  next page
//   refresh()   re-fetch the pages already loaded (after a pick), keeping depth
export function useEligiblePlayers(draftId, search) {
  const [state, setState] = useState({ players: [], total: 0, pages: 1, page: 0 });
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState(null);
  const seq = useRef(0);
  const stateRef = useRef(state);
  stateRef.current = state;

  const run = useCallback(async (mode) => {
    if (!draftId) return;
    const id = ++seq.current; // a newer request supersedes this one
    const cur = stateRef.current;
    const from = mode === 'more' ? cur.page + 1 : 1;
    const to = mode === 'refresh' ? Math.max(1, cur.page) : from;
    if (mode === 'more') setLoadingMore(true); else if (mode === 'reset') setLoading(true);
    setError(null);
    try {
      const r = await fetchEligible(api, draftId, { search, fromPage: from, toPage: to });
      if (id !== seq.current) return;
      setState((prev) => ({
        players: mode === 'more' ? mergePlayers(prev.players, r.players) : r.players,
        total: r.total, pages: r.pages, page: r.page,
      }));
    } catch (e) {
      if (id === seq.current) setError(loadFailure(e, 'the player list'));
    }
    if (id === seq.current) { setLoading(false); setLoadingMore(false); }
  }, [draftId, search]);

  // New draft or new search: start from page 1 (debounced while typing).
  useEffect(() => {
    const t = setTimeout(() => run('reset'), search ? 300 : 0);
    return () => clearTimeout(t);
  }, [run, search]);

  const loadMore = useCallback(() => {
    const cur = stateRef.current;
    if (cur.page < cur.pages) run('more');
  }, [run]);
  const refresh = useCallback(() => run('refresh'), [run]);
  const reload = useCallback(() => run('reset'), [run]);

  return {
    players: state.players, total: state.total,
    hasMore: state.page < state.pages,
    loading, loadingMore, error, loadMore, refresh, reload,
  };
}
