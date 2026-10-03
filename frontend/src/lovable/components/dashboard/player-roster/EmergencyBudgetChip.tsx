// @ts-nocheck
/**
 * Iter 187 — Emergency Budget Chip.
 *
 * Extracted from `PlayerRoster.tsx` (iter 106). Shows a small
 * "Used X/Y emergency swaps" pill when the league has the emergency
 * swap budget feature enabled. Returns null when disabled.
 *
 * Risks documented:
 *   1. `data-testid="emergency-swap-chip"` MUST be preserved (iter 106
 *      visual coverage + future testing-agent flows).
 *   2. The emerald/rose colour swap (remaining > 0 vs == 0) is
 *      meaningful UX feedback — keep the conditional.
 *   3. The `scope_label` is rendered raw inside the pill, so backend
 *      must continue to emit it pre-formatted (e.g. "this week").
 */
export type EmergencyBudget = {
  enabled: boolean;
  used: number;
  budget: number;
  remaining: number;
  scope: "per_week" | "per_season" | string;
  scope_label?: string;
} | null;

export const EmergencyBudgetChip = ({ emergencyBudget }: { emergencyBudget: EmergencyBudget }) => {
  if (!emergencyBudget?.enabled) return null;
  return (
    <div
      className="px-4 py-2 border-b border-border bg-secondary/20 flex items-center gap-2 flex-wrap"
      data-testid="emergency-swap-chip"
    >
      <span
        className={`text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-full border ${
          emergencyBudget.remaining > 0
            ? "bg-emerald-500/10 text-emerald-300 border-emerald-500/30"
            : "bg-rose-500/10 text-rose-300 border-rose-500/30"
        }`}
      >
        Used {emergencyBudget.used} / {emergencyBudget.budget} emergency swaps {emergencyBudget.scope_label}
      </span>
      {emergencyBudget.remaining > 0 ? (
        <span className="text-[11px] text-muted-foreground">
          ({emergencyBudget.remaining} left{emergencyBudget.scope === "per_season" ? " for the season" : ""})
        </span>
      ) : (
        <span className="text-[11px] text-rose-300/80">
          No swaps remaining — wait for the next reset.
        </span>
      )}
    </div>
  );
};
