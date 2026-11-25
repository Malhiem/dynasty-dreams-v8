import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import * as SecureStore from 'expo-secure-store';
import api from '../lib/api';
import { loadFailure } from '../lib/errors';
import { ACTIVE_LEAGUE_KEY, pickActiveLeague } from '../lib/leagues';
import { useAuth } from './AuthContext';

const LeagueContext = createContext(null);

// Holds the user's leagues and which one the league screens are showing, so
// Roster, Waivers, Chat, Standings, etc. no longer all assume "the first league".
export function LeagueProvider({ children }) {
  const { user } = useAuth();
  const [leagues, setLeagues] = useState([]);
  const [activeId, setActiveId] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const reload = useCallback(async () => {
    if (!user) return;
    setLoading(true);
    setError(null);
    try {
      const { data } = await api.get('/leagues?my_leagues=true');
      let saved = null;
      try { saved = await SecureStore.getItemAsync(ACTIVE_LEAGUE_KEY); } catch { /* optional */ }
      setLeagues(data || []);
      setActiveId((prev) => pickActiveLeague(data, prev || saved)?.id || null);
    } catch (e) {
      setError(loadFailure(e, 'your leagues'));
    }
    setLoading(false);
  }, [user]);

  useEffect(() => {
    if (user) reload();
    else { setLeagues([]); setActiveId(null); setError(null); }
  }, [user, reload]);

  const select = useCallback((id) => {
    setActiveId(id);
    SecureStore.setItemAsync(ACTIVE_LEAGUE_KEY, String(id)).catch(() => {});
  }, []);

  const league = useMemo(() => pickActiveLeague(leagues, activeId), [leagues, activeId]);
  const value = useMemo(
    () => ({ leagues, league, leagueId: league?.id || null, select, reload, loading, error }),
    [leagues, league, select, reload, loading, error],
  );
  return <LeagueContext.Provider value={value}>{children}</LeagueContext.Provider>;
}

export function useLeague() {
  const ctx = useContext(LeagueContext);
  if (!ctx) throw new Error('useLeague must be used within LeagueProvider');
  return ctx;
}
