// @ts-nocheck
import { useEffect, useState } from 'react';
import api, { invalidateApiCache } from '@/lib/api';

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
  const [myTeamsByLeague, setMyTeamsByLeague] = useState({});
  const [leagueId, setLeagueId] = useState(() => {
    try { return localStorage.getItem(STORAGE_KEY) || null; } catch { return null; }
  });
  const [league, setLeague] = useState(null);
  const [myTeam, setMyTeam] = useState(null);
  const [leagueTeams, setLeagueTeams] = useState([]);
  const [teamsReloadKey, setTeamsReloadKey] = useState(0);

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
        // Fetch user's team in each league so the global Current League
        // switcher can show team logo+name per league entry without
        // round-tripping per click.
        try {
          const meRes = await api.get('/auth/me');
          const meId = meRes.data?.id;
          if (meId && Array.isArray(data) && data.length > 0) {
            const teamResults = await Promise.all(
              data.map(l =>
                api.get(`/teams?league_id=${l.id}`)
                  .then(r => [l.id, (r.data || []).find(t => t.owner_id === meId) || null])
                  .catch(() => [l.id, null]),
              ),
            );
            if (!cancelled) {
              const map = {};
              for (const [lid, t] of teamResults) map[lid] = t;
              setMyTeamsByLeague(map);
            }
          }
        } catch (e) { /* noop */ }
      } catch (e) {
        console.error('my_leagues failed', e);
      }
      setLoading(false);
    };
    init();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [teamsReloadKey]);  // Iter 194 — react to reloadMyLeagues() bumps

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
        // Keep myTeamsByLeague in sync for the active league.
        setMyTeamsByLeague(prev => ({ ...prev, [leagueId]: mine }));
      } catch (e) { console.error('active league load', e); }
    };
    load();
    return () => { cancelled = true; };
  }, [leagueId, teamsReloadKey]);

  const switchLeague = (id) => {
    try { localStorage.setItem(STORAGE_KEY, id); } catch (e) { /* noop */ }
    setLeagueId(id);
  };

  const reloadTeams = () => setTeamsReloadKey(k => k + 1);
  const reloadLeague = () => setTeamsReloadKey(k => k + 1);

  // Iter 194 — Force-refresh the league list (used by the global
  // league switcher when the dropdown is opened so new memberships
  // show up immediately instead of waiting for the GET cache TTL).
  const reloadMyLeagues = () => {
    invalidateApiCache(/leagues\?my_leagues=true/);
    setTeamsReloadKey(k => k + 1);
  };

  // Iter 229e — Listen for global "leagues-changed" events fired by
  // the ClaimTeamInvite flow + any future onboarding paths so the
  // sidebar dropdown reflects the new membership immediately, without
  // requiring the user to manually open the dropdown.
  useEffect(() => {
    const handler = () => reloadMyLeagues();
    window.addEventListener("dd:leagues-changed", handler);
    return () => window.removeEventListener("dd:leagues-changed", handler);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return { loading, myLeagues, myTeamsByLeague, leagueId, league, leagueTeams, myTeam, switchLeague, reloadTeams, reloadLeague, reloadMyLeagues };
}
