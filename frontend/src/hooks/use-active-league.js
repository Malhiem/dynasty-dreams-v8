// @ts-nocheck
import { useEffect, useState } from 'react';
import api from '@/lib/api';

const STORAGE_KEY = 'dd_active_league_id';

/**
 * Resolves "the league I'm currently viewing" for multi-league users.
 * - Pulls the user's teams via `/api/leagues?my_leagues=true`
 * - Uses the league_id stored in localStorage if present, else picks the first
 * - Surfaces teams-in-league, the user's own team, and a setter for switching
 */
export function useActiveLeague() {
  const [loading, setLoading] = useState(true);
  const [myLeagues, setMyLeagues] = useState([]);
  const [leagueId, setLeagueId] = useState(() => {
    try { return localStorage.getItem(STORAGE_KEY) || null; } catch { return null; }
  });
  const [league, setLeague] = useState(null);
  const [myTeam, setMyTeam] = useState(null);
  const [leagueTeams, setLeagueTeams] = useState([]);

  useEffect(() => {
    let cancelled = false;
    const init = async () => {
      setLoading(true);
      try {
        const { data } = await api.get('/leagues?my_leagues=true');
        if (cancelled) return;
        setMyLeagues(data || []);
        let id = leagueId;
        if (!id || !(data || []).some(l => l.id === id)) {
          id = data?.[0]?.id || null;
          if (id) {
            try { localStorage.setItem(STORAGE_KEY, id); } catch (e) { /* noop */ }
            setLeagueId(id);
          }
        }
      } catch (e) {
        console.error('my_leagues failed', e);
      }
      setLoading(false);
    };
    init();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!leagueId) { setLeague(null); setLeagueTeams([]); setMyTeam(null); return; }
    let cancelled = false;
    const load = async () => {
      try {
        const [lRes, tRes, meRes] = await Promise.all([
          api.get(`/leagues/${leagueId}`),
          api.get(`/teams?league_id=${leagueId}`),
          api.get('/auth/me'),
        ]);
        if (cancelled) return;
        setLeague(lRes.data);
        setLeagueTeams(tRes.data || []);
        const mine = (tRes.data || []).find(t => t.owner_id === meRes.data?.id) || null;
        setMyTeam(mine);
      } catch (e) { console.error('active league load', e); }
    };
    load();
    return () => { cancelled = true; };
  }, [leagueId]);

  const switchLeague = (id) => {
    try { localStorage.setItem(STORAGE_KEY, id); } catch (e) { /* noop */ }
    setLeagueId(id);
  };

  return { loading, myLeagues, leagueId, league, leagueTeams, myTeam, switchLeague };
}
