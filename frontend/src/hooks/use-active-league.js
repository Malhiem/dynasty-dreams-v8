// @ts-nocheck
import { useEffect, useState } from 'react';
import api, { invalidateApiCache } from '@/lib/api';
import { useSocket } from '@/hooks/use-socket';

const STORAGE_KEY = 'dd_active_league_id';
const ORDER_KEY = 'dd_league_order_v1';

// Iter 230al + 230am — Apply the user's saved league order so every
// consumer of `myLeagues` renders in the same sequence. Server-side
// preference (returned by `/notifications/preferences`) takes
// precedence; localStorage is used as a same-session fast path AND a
// fallback when the server hasn't been hit yet on initial mount.
function _readSavedOrder(serverOrder) {
  if (Array.isArray(serverOrder) && serverOrder.length) return serverOrder;
  try {
    const raw = localStorage.getItem(ORDER_KEY);
    const order = raw ? JSON.parse(raw) : [];
    return Array.isArray(order) ? order : [];
  } catch {
    return [];
  }
}

function _applyOrder(leagues, order) {
  if (!Array.isArray(order) || !order.length) return leagues;
  const byId = {};
  (leagues || []).forEach((l) => { byId[l.id] = l; });
  return [
    ...order.map((id) => byId[id]).filter(Boolean),
    ...(leagues || []).filter((l) => !order.includes(l.id)),
  ];
}

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
  // Iter 229f — Capture the current user's id so the global socket
  // listener (below) can subscribe to their personal notification
  // room (`user_{userId}`) and surface membership-changed events
  // anywhere in the app.
  const [meId, setMeId] = useState(null);

  useEffect(() => {
    let cancelled = false;
    const init = async () => {
      setLoading(true);
      try {
        // Iter 230am — Fetch both the league list AND the server-side
        // order preference in parallel. Server order wins; localStorage
        // is the fallback for cold starts before the prefs call lands.
        const [leaguesRes, prefsRes] = await Promise.all([
          api.get('/leagues?my_leagues=true&exclude_archived=true&exclude_test=true'),
          api.get('/notifications/preferences').catch(() => ({ data: null })),
        ]);
        if (cancelled) return;
        const data = leaguesRes.data;
        const serverOrder = prefsRes.data?.league_order;
        const effectiveOrder = _readSavedOrder(serverOrder);
        // Keep localStorage in lock-step with the server so the next
        // cold start renders the right order before the prefs RTT.
        if (Array.isArray(serverOrder) && serverOrder.length) {
          try { localStorage.setItem(ORDER_KEY, JSON.stringify(serverOrder)); } catch { /* noop */ }
        }
        const ordered = _applyOrder(data || [], effectiveOrder);
        setMyLeagues(ordered);
        let id = leagueId;
        if (!id || !(ordered || []).some(l => l.id === id)) {
          id = ordered?.[0]?.id || null;
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
          const meIdResolved = meRes.data?.id;
          if (!cancelled && meIdResolved) setMeId(meIdResolved);
          if (meIdResolved && Array.isArray(data) && data.length > 0) {
            const teamResults = await Promise.all(
              data.map(l =>
                api.get(`/teams?league_id=${l.id}`)
                  .then(r => [l.id, (r.data || []).find(t => t.owner_id === meIdResolved) || null])
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

  // Iter 229f — Subscribe to the user's personal Socket.IO room
  // (`user_{userId}`) so that membership changes broadcast by the
  // backend (e.g. when a commissioner adds the user as a co-owner)
  // are reflected in the sidebar dropdown instantly, no refresh
  // required. The backend emits `team_membership_changed` to both
  // `league_{id}` AND `user_{user_id}` (see `routes/team_invites.py
  // :accept_team_invite`). This hook covers the user-scoped channel.
  useSocket(
    meId ? `user_${meId}` : null,
    {
      team_membership_changed: () => {
        try { invalidateApiCache(/leagues\?my_leagues=true/); } catch { /* noop */ }
        reloadMyLeagues();
      },
      // Iter 232N.3 — Player status-flag change toasts. Fires whenever
      // a player rostered by any of the user's teams flips a status
      // flag (injured / minors / unsigned). Shown as a low-priority
      // toast so it doesn't compete with trade/lineup activity.
      player_status_change: (payload) => {
        try {
          const title = payload?.title || `${payload?.player_name || 'Player'} status changed`;
          const message = payload?.message || '';
          import('sonner').then(({ toast }) => {
            toast(title, {
              description: message,
              duration: 6000,
              action: payload?.player_id ? {
                label: 'View',
                onClick: () => { window.location.href = `/players/${payload.player_id}`; },
              } : undefined,
            });
          }).catch(() => { /* toast lib unavailable in this route — noop */ });
        } catch { /* best-effort */ }
      },
      // Iter 232N.24 — Gamified XP toast fires whenever the backend
      // credits the user with career XP (trade accepted, matchup won,
      // etc.). Copy mirrors the Fantasy Level badge — "+25 XP · Line
      // Captain in 3" — so the badge feels alive without needing a
      // full page refresh.
      xp_awarded: (payload) => {
        try {
          const delta = Number(payload?.delta || 0);
          if (delta <= 0) return;
          const title = `+${delta} XP`;
          const remaining = Number(payload?.xp_to_next_level || 0);
          const levelTitle = payload?.title || 'Fantasy Level';
          const source = payload?.source;
          const sourceLabel = source === 'trade_accepted'
            ? 'Trade accepted'
            : source === 'matchup_won'
              ? 'Matchup win'
              : source === 'waiver_claim_won'
                ? 'Waiver claim won'
                : source === 'draft_completed'
                  ? 'Draft completed'
                  : 'Career progress';
          const desc = remaining > 0
            ? `${sourceLabel} · ${levelTitle} in ${remaining}`
            : `${sourceLabel} · ${levelTitle}`;
          import('sonner').then(({ toast }) => {
            toast.success(title, {
              description: desc,
              duration: 5000,
            });
          }).catch(() => { /* toast lib unavailable — noop */ });
        } catch { /* best-effort */ }
      },
    },
    meId,
  );

  // Iter 230al + 230am — Reorder leagues in-place. Persists the order
  // to BOTH localStorage (instant cold-start replay) AND the server
  // (`/notifications/preferences/league-order`) so the user's chosen
  // order follows them across devices.
  const reorderLeagues = (from, to) => {
    setMyLeagues((prev) => {
      if (from === to) return prev;
      if (from < 0 || from >= prev.length) return prev;
      if (to < 0 || to >= prev.length) return prev;
      const next = [...prev];
      const [moved] = next.splice(from, 1);
      next.splice(to, 0, moved);
      const orderedIds = next.map((l) => l.id);
      try { localStorage.setItem(ORDER_KEY, JSON.stringify(orderedIds)); } catch (e) { /* noop */ }
      api.put('/notifications/preferences/league-order', {
        ordered_ids: orderedIds,
      }).catch(() => { /* best-effort; localStorage still has it */ });
      return next;
    });
  };

  // Iter 230al — Hide a league from the user's day-to-day surfaces
  // (switcher, Dashboard "My Leagues" list, Week-at-a-Glance). Hidden
  // leagues are reversible from the Settings modal. We optimistically
  // strip the league from `myLeagues` so the UI updates instantly.
  const hideLeague = async (id) => {
    setMyLeagues((prev) => prev.filter((l) => l.id !== id));
    try {
      await api.put('/notifications/preferences/league-hide', {
        league_id: id,
        hidden: true,
      });
    } catch (e) {
      // On failure, reload to restore state.
      reloadMyLeagues();
      throw e;
    }
  };

  return { loading, myLeagues, myTeamsByLeague, leagueId, league, leagueTeams, myTeam, switchLeague, reloadTeams, reloadLeague, reloadMyLeagues, reorderLeagues, hideLeague };
}
