// @ts-nocheck
/**
 * Iter 228c — Trades step extracted from SetupWizard.jsx
 */
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import HelpTooltip from "@/components/ui/help-tooltip";
import { ClockPicker } from "@/components/ui/clock-picker";

export default function TradesStep({ ctx }) {
  const {
    HELP,
    maxTeams,
    tradeReviewHours, setTradeReviewHours,
    tradeVetoCount, setTradeVetoCount,
    tradeDeadlineWeek, setTradeDeadlineWeek,
    tradeDeadlineDow, setTradeDeadlineDow,
    tradeDeadlineTime, setTradeDeadlineTime,
  } = ctx;

  return (
    <div className="space-y-3" data-testid="wizard-body-trades">
      <p className="text-sm text-muted-foreground">
        These settings control how trades flow through your league. You can change them later from <strong>Commissioner Settings → Rules &amp; Schedule</strong>.
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <div>
          <Label className="text-xs flex items-center">
            Review period (hours)
            <HelpTooltip text={HELP.tradeReview} testId="help-trade-review" />
          </Label>
          <Input type="number" min={0} max={168}
            value={tradeReviewHours}
            onChange={(e) => setTradeReviewHours(Math.max(0, Math.min(168, parseInt(e.target.value || "0", 10))))}
            data-testid="wizard-trade-review-hours" />
        </div>
        <div>
          <Label className="text-xs flex items-center">
            Veto threshold (# teams)
            <HelpTooltip text="How many managers must vote VETO for a trade to be blocked. 0 disables vetoes." testId="help-trade-veto" />
          </Label>
          <Input type="number" min={0} max={Math.max(1, maxTeams)}
            value={tradeVetoCount}
            onChange={(e) => setTradeVetoCount(Math.max(0, Math.min(maxTeams, parseInt(e.target.value || "0", 10))))}
            data-testid="wizard-trade-veto-count" />
          <p className="text-[10px] text-muted-foreground mt-1" data-testid="wizard-veto-preview">
            {tradeVetoCount === 0
              ? "Vetoes disabled."
              : `Trade is blocked when ${tradeVetoCount} of ${maxTeams} team${maxTeams === 1 ? "" : "s"} vote VETO.`}
          </p>
        </div>
        <div>
          <Label className="text-xs flex items-center">
            Trade deadline (week)
            <HelpTooltip text={HELP.tradeDeadline} testId="help-trade-deadline" />
          </Label>
          <Input type="number" min={1} max={30}
            value={tradeDeadlineWeek}
            onChange={(e) => setTradeDeadlineWeek(Math.max(1, Math.min(30, parseInt(e.target.value || "0", 10))))}
            data-testid="wizard-trade-deadline-week" />
          <div className="grid grid-cols-2 gap-2 mt-2">
            <div>
              <Label className="text-[10px] text-muted-foreground">Day of week</Label>
              <select
                value={tradeDeadlineDow}
                onChange={(e) => setTradeDeadlineDow(parseInt(e.target.value, 10))}
                className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm"
                data-testid="wizard-trade-deadline-dow"
              >
                <option value={0}>Sunday</option>
                <option value={1}>Monday</option>
                <option value={2}>Tuesday</option>
                <option value={3}>Wednesday</option>
                <option value={4}>Thursday</option>
                <option value={5}>Friday</option>
                <option value={6}>Saturday</option>
              </select>
            </div>
            <div>
              <Label className="text-[10px] text-muted-foreground">Time of day</Label>
              <ClockPicker
                value={tradeDeadlineTime}
                onChange={setTradeDeadlineTime}
                data-testid="wizard-trade-deadline-time"
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
