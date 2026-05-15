// @ts-nocheck
import { useCallback, useEffect, useState } from "react";

/**
 * Per-league Trade Block UI preferences.
 *
 * Persists:
 *  - `viewMode` ("list" | "tile") — toggles the page/widget render style
 *  - `hiddenIds` (string[]) — items the user has dismissed (only honored in
 *    tile view; list view ignores them so the user can re-find dismissed
 *    rows via sort)
 *  - `sort`  ({ key, dir }) — list-view sort key + direction
 *
 * Storage keys are scoped per-league so each league remembers its own
 * setup. localStorage is the right home for this: it's purely UI state
 * (no backend cost), survives reloads, and stays local to the device the
 * user configured.
 */
const k = (leagueId, suffix) => `dynasty-trade-block-${suffix}-${leagueId || "_"}`;

export function useTradeBlockUiPrefs(leagueId) {
  const [viewMode, setViewModeState] = useState("tile");
  const [hiddenIds, setHiddenIds] = useState([]);
  const [sort, setSortState] = useState({ key: "weeklyPoints", dir: "desc" });

  // Hydrate from localStorage whenever the league changes.
  useEffect(() => {
    if (!leagueId) return;
    try {
      const v = localStorage.getItem(k(leagueId, "view"));
      if (v === "list" || v === "tile") setViewModeState(v);
      else setViewModeState("tile");

      const h = localStorage.getItem(k(leagueId, "hidden"));
      setHiddenIds(h ? (JSON.parse(h) || []) : []);

      const s = localStorage.getItem(k(leagueId, "sort"));
      if (s) setSortState(JSON.parse(s));
      else setSortState({ key: "weeklyPoints", dir: "desc" });
    } catch {
      // Corrupted storage — fall back to defaults.
      setViewModeState("tile");
      setHiddenIds([]);
      setSortState({ key: "weeklyPoints", dir: "desc" });
    }
  }, [leagueId]);

  const setViewMode = useCallback((next) => {
    setViewModeState(next);
    if (leagueId) {
      try { localStorage.setItem(k(leagueId, "view"), next); } catch { /* noop */ }
    }
  }, [leagueId]);

  const hide = useCallback((id) => {
    setHiddenIds((prev) => {
      const sid = String(id);
      if (prev.includes(sid)) return prev;
      const next = [...prev, sid];
      if (leagueId) {
        try { localStorage.setItem(k(leagueId, "hidden"), JSON.stringify(next)); } catch { /* noop */ }
      }
      return next;
    });
  }, [leagueId]);

  const unhide = useCallback((id) => {
    setHiddenIds((prev) => {
      const sid = String(id);
      const next = prev.filter((x) => x !== sid);
      if (leagueId) {
        try { localStorage.setItem(k(leagueId, "hidden"), JSON.stringify(next)); } catch { /* noop */ }
      }
      return next;
    });
  }, [leagueId]);

  const clearHidden = useCallback(() => {
    setHiddenIds([]);
    if (leagueId) {
      try { localStorage.removeItem(k(leagueId, "hidden")); } catch { /* noop */ }
    }
  }, [leagueId]);

  const setSort = useCallback((next) => {
    setSortState(next);
    if (leagueId) {
      try { localStorage.setItem(k(leagueId, "sort"), JSON.stringify(next)); } catch { /* noop */ }
    }
  }, [leagueId]);

  // Toggle direction if the same key, otherwise switch key with default desc.
  const toggleSort = useCallback((key) => {
    setSortState((prev) => {
      const next = prev.key === key
        ? { key, dir: prev.dir === "asc" ? "desc" : "asc" }
        : { key, dir: "desc" };
      if (leagueId) {
        try { localStorage.setItem(k(leagueId, "sort"), JSON.stringify(next)); } catch { /* noop */ }
      }
      return next;
    });
  }, [leagueId]);

  return {
    viewMode,
    setViewMode,
    hiddenIds,
    isHidden: (id) => hiddenIds.includes(String(id)),
    hide,
    unhide,
    clearHidden,
    sort,
    setSort,
    toggleSort,
  };
}
