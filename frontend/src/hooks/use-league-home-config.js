// @ts-nocheck
import { useCallback, useEffect, useRef, useState } from "react";
import api from "@/lib/api";

/**
 * Widget visibility + order for the League Home screen (`/leagues/:id`).
 *
 * Storage strategy (Iter 232N.29):
 *   1. localStorage keys `dynasty-league-home-{widgets|order}-${leagueId}`
 *      give a zero-flicker first paint before any network round-trip.
 *   2. On mount we hydrate from `GET /users/me/league-home-layout/{id}` —
 *      the server copy always wins over localStorage so desktop → mobile
 *      handoffs match. If the server has nothing yet, we keep the local
 *      preferences and start syncing them via debounced PATCH on the
 *      next reorder/toggle.
 *   3. Every `toggle` / `reorder` writes through to localStorage
 *      immediately AND schedules a 400 ms debounced PATCH so a rapid
 *      drag flurry sends one request instead of N.
 */
export const LEAGUE_HOME_WIDGETS = [
  { id: "matchups", label: "Matchups + Standings", description: "H2H week's head-to-head cards + standings rail." },
  { id: "points_leaderboard", label: "Points Leaderboard", description: "Roto leaderboard shown when the league uses points-based scoring." },
  { id: "top_trade_block", label: "Top Trade Block", description: "Most-watched trade-block players across the league." },
  { id: "pending_trades", label: "Pending Trades", description: "Trades awaiting your response or league approval." },
  { id: "transactions", label: "Recent Transactions", description: "Last 20 adds / drops / trades grouped by 5-minute windows." },
  // Iter 232N.30 — Player Status Feed + League Movers were previously
  // rendered outside SortableSections. Registering them here lets
  // managers reorder or hide them alongside the rest of the widgets.
  { id: "player_activity", label: "Recent Player Activity", description: "Status changes (IR / call-ups / trades) on your roster in the last 14 days." },
  { id: "league_movers", label: "League Movers", description: "Cross-league risers + fallers over the last 7 days." },
  { id: "quick_actions", label: "Quick Actions", description: "Shortcuts to your roster, the draft room, and the trade center." },
];

const DEFAULT_ORDER = LEAGUE_HOME_WIDGETS.map((w) => w.id);

const defaultVisible = () => {
  const out = {};
  LEAGUE_HOME_WIDGETS.forEach((w) => { out[w.id] = true; });
  return out;
};

// Reconcile a saved order against DEFAULT_ORDER — drop unknown ids,
// append newer widgets so users whose saved order predates a shipped
// widget still see it.
const reconcileOrder = (candidate) => {
  if (!Array.isArray(candidate) || candidate.length === 0) return DEFAULT_ORDER;
  const kept = candidate.filter((id) => DEFAULT_ORDER.includes(id));
  const missing = DEFAULT_ORDER.filter((id) => !kept.includes(id));
  return [...kept, ...missing];
};

export function useLeagueHomeConfig(leagueId) {
  const visKey = leagueId ? `dynasty-league-home-widgets-${leagueId}` : null;
  const orderKey = leagueId ? `dynasty-league-home-order-${leagueId}` : null;

  const [visibility, setVisibility] = useState(defaultVisible);
  const [order, setOrder] = useState(DEFAULT_ORDER);
  // Iter 232N.29 — Customize mode. When ON, LeagueDetailPage renders
  // dashed cyan outlines + prominent grip handles so users discover
  // the widgets are drag-to-reorder. Off by default.
  const [customizing, setCustomizing] = useState(false);
  // Iter 232N.31 — First-run marker. Once true, smart-arrange is
  // permanently disabled so we never clobber user-chosen orders on
  // subsequent visits. Hydrated from the server on mount.
  const [firstRunCompleted, setFirstRunCompleted] = useState(true);
  const saveTimer = useRef(null);

  // ── Local storage hydration ────────────────────────────────────
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
      setOrder(rawOrder ? reconcileOrder(JSON.parse(rawOrder)) : DEFAULT_ORDER);
    } catch {
      setOrder(DEFAULT_ORDER);
    }
  }, [visKey, orderKey]);

  // ── Server hydration (Iter 232N.29 — cross-device sync) ────────
  useEffect(() => {
    if (!leagueId) return;
    let cancelled = false;
    (async () => {
      try {
        const { data } = await api.get(`/users/me/league-home-layout/${leagueId}`);
        if (cancelled) return;
        const remoteOrder = Array.isArray(data?.widget_order) ? data.widget_order : [];
        if (remoteOrder.length) {
          const reconciled = reconcileOrder(remoteOrder);
          setOrder(reconciled);
          if (orderKey) {
            try { localStorage.setItem(orderKey, JSON.stringify(reconciled)); } catch { /* noop */ }
          }
        }
        const remoteVis = data?.visibility && typeof data.visibility === "object" ? data.visibility : null;
        if (remoteVis && Object.keys(remoteVis).length) {
          const next = { ...defaultVisible(), ...remoteVis };
          setVisibility(next);
          if (visKey) {
            try { localStorage.setItem(visKey, JSON.stringify(next)); } catch { /* noop */ }
          }
        }
        // Iter 232N.31 — Only allow smart-arrange when the server
        // has NEVER seen a first-run marker AND there's no saved
        // layout yet. Any saved order or explicit flag flips this off.
        const serverFirstRun = !!data?.first_run_completed;
        setFirstRunCompleted(serverFirstRun || remoteOrder.length > 0);
      } catch { /* offline / unauth — localStorage stays authoritative */ }
    })();
    return () => { cancelled = true; };
  }, [leagueId, visKey, orderKey]);

  // Debounced server write for any subsequent local change.
  const scheduleSync = useCallback((nextOrder, nextVis, extras = {}) => {
    if (!leagueId) return;
    if (saveTimer.current) clearTimeout(saveTimer.current);
    saveTimer.current = setTimeout(() => {
      const body = {};
      if (nextOrder) body.widget_order = nextOrder;
      if (nextVis) body.visibility = nextVis;
      if (typeof extras.first_run_completed === "boolean") {
        body.first_run_completed = extras.first_run_completed;
      }
      api.patch(`/users/me/league-home-layout/${leagueId}`, body)
        .catch(() => { /* offline / auth blip — localStorage is authoritative */ });
    }, 400);
  }, [leagueId]);

  const toggle = useCallback((id) => {
    setVisibility((prev) => {
      const next = { ...prev, [id]: !prev[id] };
      if (visKey) { try { localStorage.setItem(visKey, JSON.stringify(next)); } catch { /* noop */ } }
      // Iter 232N.31 — Any manual change → mark first-run done so we
      // never override the user's intent on later visits.
      scheduleSync(null, next, { first_run_completed: true });
      setFirstRunCompleted(true);
      return next;
    });
  }, [visKey, scheduleSync]);

  const reorder = useCallback((nextOrder) => {
    setOrder(nextOrder);
    if (orderKey) { try { localStorage.setItem(orderKey, JSON.stringify(nextOrder)); } catch { /* noop */ } }
    scheduleSync(nextOrder, null, { first_run_completed: true });
    setFirstRunCompleted(true);
  }, [orderKey, scheduleSync]);

  const reset = useCallback(() => {
    const d = defaultVisible();
    setVisibility(d);
    setOrder(DEFAULT_ORDER);
    if (visKey) { try { localStorage.removeItem(visKey); } catch { /* noop */ } }
    if (orderKey) { try { localStorage.removeItem(orderKey); } catch { /* noop */ } }
    // Iter 232N.31 — Explicit reset re-arms smart-arrange for the next
    // page load. That way a manager who resets on a slow week gets a
    // freshly-relevant layout on their next visit.
    setFirstRunCompleted(false);
    scheduleSync(DEFAULT_ORDER, d, { first_run_completed: false });
  }, [visKey, orderKey, scheduleSync]);

  // Iter 232N.31 — Smart-arrange helper. Callers hand us a map of
  // { widgetId: signalScore } and we push widgets with the highest
  // signal to the top. No-op if firstRunCompleted is already true —
  // never clobbers a user's saved layout.
  const applySmartOrder = useCallback((signals) => {
    if (firstRunCompleted) return;
    if (!signals || typeof signals !== "object") return;
    // Only rank widgets we actually know about; unknown ids drop.
    const scored = DEFAULT_ORDER.map((id, idx) => ({
      id,
      // High-signal first; ties broken by the DEFAULT_ORDER index so
      // the sort stays deterministic across renders.
      score: Number.isFinite(signals[id]) ? Number(signals[id]) : 0,
      tie: idx,
    }));
    scored.sort((a, b) => (b.score - a.score) || (a.tie - b.tie));
    const nextOrder = scored.map((s) => s.id);
    setOrder(nextOrder);
    if (orderKey) { try { localStorage.setItem(orderKey, JSON.stringify(nextOrder)); } catch { /* noop */ } }
    // Persist immediately + latch the first-run marker so we don't
    // re-arrange on every subsequent page load.
    setFirstRunCompleted(true);
    scheduleSync(nextOrder, null, { first_run_completed: true });
  }, [firstRunCompleted, orderKey, scheduleSync]);

  return {
    visibility, order, toggle, reorder, reset,
    customizing, setCustomizing,
    firstRunCompleted, applySmartOrder,
  };
}
