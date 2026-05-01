// @ts-nocheck
import { useCallback, useEffect, useState } from "react";

/**
 * Widget visibility hook keyed by league id — persists the user's choice of
 * which sections to hide/show on the League Home screen (`/leagues/:id`).
 *
 * Storage: `localStorage["dynasty-league-home-widgets-${leagueId}"]`.
 * Per-league so commissioners/owners get a clean default when they switch
 * into a different league instead of inheriting the last league's layout.
 */
export const LEAGUE_HOME_WIDGETS = [
  { id: "matchups", label: "Matchups + Standings", description: "H2H week's head-to-head cards + standings rail." },
  { id: "points_leaderboard", label: "Points Leaderboard", description: "Roto leaderboard shown when the league uses points-based scoring." },
  { id: "top_trade_block", label: "Top Trade Block", description: "Most-watched trade-block players across the league." },
  { id: "pending_trades", label: "Pending Trades", description: "Trades awaiting your response or league approval." },
  { id: "transactions", label: "Recent Transactions", description: "Last 20 adds / drops / trades grouped by 5-minute windows." },
  { id: "quick_actions", label: "Quick Actions", description: "Shortcuts to your roster, the draft room, and the trade center." },
];

const defaultVisible = () => {
  const out = {};
  LEAGUE_HOME_WIDGETS.forEach((w) => { out[w.id] = true; });
  return out;
};

export function useLeagueHomeConfig(leagueId) {
  const key = leagueId ? `dynasty-league-home-widgets-${leagueId}` : null;
  const [visibility, setVisibility] = useState(defaultVisible);

  useEffect(() => {
    if (!key) return;
    try {
      const raw = localStorage.getItem(key);
      if (raw) setVisibility({ ...defaultVisible(), ...JSON.parse(raw) });
      else setVisibility(defaultVisible());
    } catch {
      setVisibility(defaultVisible());
    }
  }, [key]);

  const toggle = useCallback((id) => {
    setVisibility((prev) => {
      const next = { ...prev, [id]: !prev[id] };
      if (key) { try { localStorage.setItem(key, JSON.stringify(next)); } catch { /* noop */ } }
      return next;
    });
  }, [key]);

  const reset = useCallback(() => {
    const d = defaultVisible();
    setVisibility(d);
    if (key) { try { localStorage.removeItem(key); } catch { /* noop */ } }
  }, [key]);

  return { visibility, toggle, reset };
}
