// @ts-nocheck
// Iter 232L (refactor) — Global stat-view toggle for the Transactions
// page. Flips every trade card between FPts (season + per-game) and the
// league's counting categories. Selection is persisted to localStorage
// under `transactions.viewMode` (default `fpts`).

export function StatViewToggle({ viewMode, onChange }) {
  const btn = (mode, label) => (
    <button
      type="button"
      onClick={() => onChange(mode)}
      aria-pressed={viewMode === mode}
      data-testid={`transactions-view-${mode}`}
      className={
        "px-3 py-1.5 rounded transition-colors font-medium " +
        (viewMode === mode
          ? "bg-primary text-primary-foreground shadow-sm"
          : "text-muted-foreground hover:text-foreground")
      }
    >
      {label}
    </button>
  );
  return (
    <div
      className="inline-flex items-center rounded-md border border-border/60 bg-secondary/30 p-0.5 text-xs"
      role="group"
      aria-label="Stat view mode"
      data-testid="transactions-view-toggle"
    >
      {btn("fpts", "FPts")}
      {btn("categories", "Categories")}
    </div>
  );
}
