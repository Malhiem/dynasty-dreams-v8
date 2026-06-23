// @ts-nocheck
/**
 * Iter 228c — Generate step extracted from SetupWizard.jsx
 */
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import HelpTooltip from "@/components/ui/help-tooltip";

const fmtMoney = (n) => `${(Number(n) || 0).toLocaleString()}`;

export default function GenerateStep({ ctx }) {
  const {
    HELP,
    capEnabled, capAmount,
    retentionEnabled, retentionSlots, retentionMaxPct,
    divSet,
    tradeDeadlineWeek,
    playoffStartWeek, playoffEndWeek,
    numWeeks, setNumWeeks,
    busy,
    generateSchedule,
    scheduleMode,
    scheduleWarnings,
  } = ctx;

  return (
    <div className="space-y-4" data-testid="wizard-body-generate">
      <div className="stat-card p-4 space-y-3">
        <h3 className="text-sm font-bold">Ready to generate the season schedule</h3>
        <div className="grid grid-cols-2 gap-3 text-xs">
          <div><span className="text-muted-foreground">Salary cap:</span> <strong>{capEnabled ? `$${fmtMoney(capAmount)}` : "Disabled"}</strong></div>
          <div><span className="text-muted-foreground">Retention:</span> <strong>{retentionEnabled ? `${retentionSlots} slots · ${retentionMaxPct}% max` : "Disabled"}</strong></div>
          <div><span className="text-muted-foreground">Divisions:</span> <strong>{divSet.size}</strong></div>
          <div><span className="text-muted-foreground">Mode:</span> <strong>{divSet.size >= 2 ? "Division-aware" : "Round-robin"}</strong></div>
          <div><span className="text-muted-foreground">Trade deadline:</span> <strong>Week {tradeDeadlineWeek}</strong></div>
          <div><span className="text-muted-foreground">Playoffs:</span> <strong>Wk {playoffStartWeek}–{playoffEndWeek}</strong></div>
        </div>
        <div className="flex items-end gap-2">
          <div className="flex-1">
            <Label className="text-xs flex items-center">
              Regular season weeks
              <HelpTooltip text={HELP.weeks} testId="help-weeks-final" />
            </Label>
            <Input type="number" min={4} max={30} value={numWeeks}
              onChange={(e) => setNumWeeks(Math.max(4, Math.min(30, parseInt(e.target.value || "0", 10))))}
              data-testid="wizard-final-num-weeks" />
          </div>
          <Button size="sm" onClick={generateSchedule} disabled={busy} data-testid="wizard-generate-btn">
            Generate schedule
          </Button>
        </div>
        {scheduleMode && (
          <p className="text-xs text-success" data-testid="wizard-schedule-success">✓ Schedule generated ({scheduleMode}). Click Finish to complete setup.</p>
        )}
        {scheduleWarnings.length > 0 && (
          <div className="rounded-md border border-amber-500/40 bg-amber-500/10 p-2 space-y-1" data-testid="wizard-schedule-warnings">
            <p className="text-xs font-semibold text-amber-200">Schedule generated with warnings:</p>
            <ul className="text-xs text-amber-100 list-disc list-inside space-y-0.5">
              {scheduleWarnings.map((w, i) => <li key={i}>{w}</li>)}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}
