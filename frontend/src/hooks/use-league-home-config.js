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

const DEFAULT_ORDER = LEAGUE_HOME_WIDGETS.map((w) => w.id);

const defaultVisible = () => {
  const out = {};
  LEAGUE_HOME_WIDGETS.forEach((w) => { out[w.id] = true; });
  return out;
};

export function useLeagueHomeConfig(leagueId) {
  const visKey = leagueId ? `dynasty-league-home-widgets-${leagueId}` : null;
  const orderKey = leagueId ? `dynasty-league-home-order-${leagueId}` : null;

  const [visibility, setVisibility] = useState(defaultVisible);
  const [order, setOrder] = useState(DEFAULT_ORDER);

  useEffect(() => {
    if (!visKey) return;
    try {
      const raw = localStorage.getItem(visKey);
      if (raw) setVisibility({ ...defaultVisible(), ...JSON.parse(raw) });
      else setVisibility(defaultVisible());
    } catch {
      setVisibility(defaultVisible());
    }
    try {
      const rawOrder = orderKey ? localStorage.getItem(orderKey) : null;
      if (rawOrder) {
        const parsed = JSON.parse(rawOrder);
        if (Array.isArray(parsed) && parsed.length) {
          // Guard against missing ids after a release added/removed widgets
          const kept = parsed.filter((id) => DEFAULT_ORDER.includes(id));
          const missing = DEFAULT_ORDER.filter((id) => !kept.includes(id));
          setOrder([...kept, ...missing]);
        } else {
          setOrder(DEFAULT_ORDER);
        }
      } else {
        setOrder(DEFAULT_ORDER);
      }
    } catch {
      setOrder(DEFAULT_ORDER);
    }
  }, [visKey, orderKey]);

  const toggle = useCallback((id) => {
    setVisibility((prev) => {
      const next = { ...prev, [id]: !prev[id] };
      if (visKey) { try { localStorage.setItem(visKey, JSON.stringify(next)); } catch { /* noop */ } }
      return next;
    });
  }, [visKey]);

  const reorder = useCallback((nextOrder) => {
    setOrder(nextOrder);
    if (orderKey) { try { localStorage.setItem(orderKey, JSON.stringify(nextOrder)); } catch { /* noop */ } }
  }, [orderKey]);

  const reset = useCallback(() => {
    const d = defaultVisible();
    setVisibility(d);
    setOrder(DEFAULT_ORDER);
    if (visKey) { try { localStorage.removeItem(visKey); } catch { /* noop */ } }
    if (orderKey) { try { localStorage.removeItem(orderKey); } catch { /* noop */ } }
  }, [visKey, orderKey]);

  return { visibility, order, toggle, reorder, reset };
}
