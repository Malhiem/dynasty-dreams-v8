// @ts-nocheck
/**
 * Iter 229L — Extracted from DraftRoom.tsx.
 *
 * Fetches real draft picks (with trade_history) for the active
 * league + current draft year so the Draft Board's provenance
 * overlays + filter-by-owner highlights can populate. Returns a
 * map keyed by `${round}|${original_team_id}` (and abbr-secondary
 * keys) so the board can look up a pick by its column slot.
 */
import { useEffect, useState } from 'react';
import api from '@/lib/api';

export default function useLivePicksByOrigKey(leagueId, liveTeams) {
  const [livePicksByOrigKey, setLivePicksByOrigKey] = useState({});

  useEffect(() => {
    if (!leagueId) { setLivePicksByOrigKey({}); return; }
    const year = new Date().getFullYear();
    const computeAbbrs = (name, teamId) => {
      if (!name && !teamId) return [];
      const out = [];
      if (teamId && Array.isArray(liveTeams)) {
        const lt = liveTeams.find((t) => (t.id || t._id) === teamId);
        if (lt?.logo_abbr) out.push(String(lt.logo_abbr).toUpperCase());
      }
      if (name) {
        out.push(name.replace(/\s/g, '').slice(0, 3).toUpperCase());
        out.push(name.split(' ').map((w) => w[0] || '').join('').toUpperCase());
        out.push(name.replace(/-/g, ' ').split(' ').map((w) => w[0] || '').join('').toUpperCase().slice(0, 4));
      }
      return Array.from(new Set(out.filter(Boolean)));
    };

    api.get(`/drafts/${leagueId}/picks?year=${year}`)
      .then((res) => {
        const picks = (res.data?.picks || []);
        const map = {};
        for (const p of picks) {
          const currentAbbrs = computeAbbrs(
            p.current_team_name || p.original_team_name || '',
            p.current_team_id || p.original_team_id,
          );
          const entry = { ...p, _currentOwnerAbbrs: currentAbbrs };
          map[`${p.round}|${p.original_team_id}`] = entry;
          for (const ab of computeAbbrs(p.original_team_name || '', p.original_team_id)) {
            map[`${p.round}|abbr:${ab}`] = entry;
          }
        }
        setLivePicksByOrigKey(map);
      })
      .catch(() => setLivePicksByOrigKey({}));
  }, [leagueId, liveTeams]);

  return livePicksByOrigKey;
}
