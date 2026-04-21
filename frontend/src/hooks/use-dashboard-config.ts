// @ts-nocheck
import { useState, useCallback } from "react";

export interface DashboardWidget {
  id: string;
  label: string;
  description: string;
  visible: boolean;
  area: "stats" | "main" | "sidebar";
}

const DEFAULT_WIDGETS: DashboardWidget[] = [
  { id: "stat-rank", label: "League Rank", description: "Your current league position", visible: true, area: "stats" },
  { id: "stat-points", label: "Total Points", description: "Season point total", visible: true, area: "stats" },
  
  { id: "stat-roster", label: "Roster Size", description: "Current roster count", visible: true, area: "stats" },
  { id: "standings", label: "League Standings", description: "Full league standings overview", visible: true, area: "main" },
  { id: "trade-block", label: "Trading Block", description: "Players available for trade across the league", visible: false, area: "main" },
  { id: "league-schedule", label: "League Schedule", description: "Upcoming matchups and schedule", visible: false, area: "main" },
  { id: "notifications", label: "Player Alerts", description: "Injury, hot/cold streaks, trade rumors", visible: true, area: "sidebar" },
  { id: "player-roster", label: "Player Roster", description: "Your current team roster", visible: false, area: "sidebar" },
  { id: "weekly-top-scorers", label: "Top Scorers", description: "Weekly & daily top fantasy scorers", visible: true, area: "sidebar" },
  { id: "draft-picks", label: "Draft Capital", description: "Upcoming draft picks", visible: true, area: "sidebar" },
  { id: "recent-activity", label: "Recent Activity", description: "Latest league transactions", visible: true, area: "sidebar" },
  { id: "pending-trades", label: "Pending Trades", description: "Trades awaiting review or processing", visible: true, area: "sidebar" },
  { id: "chat-widget", label: "League Chat", description: "Quick access to league chat", visible: true, area: "sidebar" },
];

const STORAGE_KEY = "dynasty-ice-dashboard-config";

function loadConfig(): DashboardWidget[] {
  // IDs and labels that have been permanently removed
  const REMOVED_IDS = new Set(["stat-dynasty", "stat-value", "dynasty-value"]);
  const REMOVED_LABELS = ["dynasty value"];
  const isRemoved = (w: DashboardWidget) =>
    REMOVED_IDS.has(w.id) || REMOVED_LABELS.some((l) => w.label.toLowerCase().includes(l));

  // Only allow widgets that exist in defaults
  const validIds = new Set(DEFAULT_WIDGETS.map((w) => w.id));

  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) {
      const parsed: DashboardWidget[] = JSON.parse(stored);
      const ids = new Set(parsed.map((w) => w.id));
      const merged = [
        ...parsed.filter((w) => validIds.has(w.id) && !isRemoved(w)),
        ...DEFAULT_WIDGETS.filter((w) => !ids.has(w.id)),
      ];
      return merged;
    }
  } catch {
    // ignore
  }
  return DEFAULT_WIDGETS.map((w) => ({ ...w }));
}

export function useDashboardConfig() {
  const [widgets, setWidgets] = useState<DashboardWidget[]>(loadConfig);

  const save = useCallback((updated: DashboardWidget[]) => {
    setWidgets(updated);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(updated));
  }, []);

  const toggleVisibility = useCallback(
    (id: string) => {
      const updated = widgets.map((w) =>
        w.id === id ? { ...w, visible: !w.visible } : w
      );
      save(updated);
    },
    [widgets, save]
  );

  const reorder = useCallback(
    (area: DashboardWidget["area"], fromIndex: number, toIndex: number) => {
      const areaWidgets = widgets.filter((w) => w.area === area);
      const otherWidgets = widgets.filter((w) => w.area !== area);
      const [moved] = areaWidgets.splice(fromIndex, 1);
      areaWidgets.splice(toIndex, 0, moved);
      save([...otherWidgets, ...areaWidgets]);
    },
    [widgets, save]
  );

  const moveUp = useCallback(
    (area: DashboardWidget["area"], index: number) => {
      if (index > 0) reorder(area, index, index - 1);
    },
    [reorder]
  );

  const moveDown = useCallback(
    (area: DashboardWidget["area"], index: number) => {
      const areaWidgets = widgets.filter((w) => w.area === area);
      if (index < areaWidgets.length - 1) reorder(area, index, index + 1);
    },
    [reorder, widgets]
  );

  const resetToDefaults = useCallback(() => {
    save(DEFAULT_WIDGETS.map((w) => ({ ...w })));
  }, [save]);

  const getWidgetsByArea = useCallback(
    (area: DashboardWidget["area"]) =>
      widgets.filter((w) => w.area === area),
    [widgets]
  );

  const getVisibleWidgets = useCallback(
    (area: DashboardWidget["area"]) =>
      widgets.filter((w) => w.area === area && w.visible),
    [widgets]
  );

  const changeArea = useCallback(
    (id: string, newArea: DashboardWidget["area"]) => {
      const updated = widgets.map((w) =>
        w.id === id ? { ...w, area: newArea } : w
      );
      save(updated);
    },
    [widgets, save]
  );

  return {
    widgets,
    toggleVisibility,
    moveUp,
    moveDown,
    resetToDefaults,
    getWidgetsByArea,
    getVisibleWidgets,
    changeArea,
  };
}
