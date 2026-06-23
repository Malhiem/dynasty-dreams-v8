// @ts-nocheck
/**
 * Iter 228c — Salary Cap + Retention step extracted from SetupWizard.jsx
 */
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import HelpTooltip from "@/components/ui/help-tooltip";
import SmartNumberInput from "@/components/ui/smart-number-input";
import CBABadge from "@/lovable/components/CBABadge";

const fmtMoney = (n) => `${(Number(n) || 0).toLocaleString()}`;

export default function CapStep({ ctx }) {
  const {
    HELP,
    capEnabled, setCapEnabled,
    capAmount, setCapAmount,
    retentionEnabled, setRetentionEnabled,
    retentionSlots, setRetentionSlots,
    retentionMaxPct, setRetentionMaxPct,
  } = ctx;

  return (
    <div className="space-y-4" data-testid="wizard-body-cap">
      <div className="flex items-center gap-3">
        <Switch checked={capEnabled} onCheckedChange={setCapEnabled} id="wiz-cap" data-testid="wizard-cap-enabled" />
        <Label htmlFor="wiz-cap" className="cursor-pointer flex items-center">
          Enable salary cap (Premium)
          <HelpTooltip text={HELP.capEnable} testId="help-cap-enable" />
        </Label>
      </div>
      {capEnabled && (
        <div className="space-y-3">
          <div>
            <Label className="text-xs flex items-center" htmlFor="wiz-cap-amt">
              Cap amount
              <HelpTooltip text={HELP.capAmount} testId="help-cap-amount" />
            </Label>
            <SmartNumberInput
              value={capAmount}
              onChange={setCapAmount}
              min={0}
              max={300000000}
              step={100000}
              fastStep={500000}
              turboStep={1000000}
              prefix="$"
              format={fmtMoney}
              testId="wizard-cap-amount"
            />
            <p className="text-xs text-muted-foreground mt-1">Hold ▲/▼ to step by $100k → $500k → $1M.</p>
          </div>
        </div>
      )}
      {!capEnabled && <p className="text-xs text-muted-foreground italic">Salary cap is disabled — teams can roster any combination of players.</p>}

      {/* Salary Retention A/B switch */}
      <div className="space-y-3 border-t border-border pt-3" data-testid="wizard-retention-card">
        <div className="flex items-center gap-3 flex-wrap">
          <Switch
            checked={retentionEnabled}
            onCheckedChange={setRetentionEnabled}
            id="wiz-retention"
            data-testid="wizard-retention-enabled"
          />
          <Label htmlFor="wiz-retention" className="cursor-pointer flex items-center font-semibold">
            Allow salary retention in trades?
            <HelpTooltip text={HELP.retentionEnable} testId="help-retention-enable" />
          </Label>
          {retentionEnabled && (
            <CBABadge slots={retentionSlots} maxPct={retentionMaxPct} testId="wizard-retention-cba-badge" />
          )}
        </div>
        {retentionEnabled && (
          <div className="grid grid-cols-2 gap-3 pl-1">
            <div>
              <Label className="text-xs flex items-center" htmlFor="wiz-ret-slots">
                Retention slots per team
                <HelpTooltip text={HELP.retentionSlots} testId="help-retention-slots" />
              </Label>
              <Input
                id="wiz-ret-slots"
                type="number" min={1} max={10} value={retentionSlots}
                onChange={(e) => setRetentionSlots(Math.max(1, Math.min(10, parseInt(e.target.value || "0", 10))))}
                data-testid="wizard-retention-slots"
              />
            </div>
            <div>
              <Label className="text-xs flex items-center" htmlFor="wiz-ret-pct">
                Max % of contract
                <HelpTooltip text={HELP.retentionMaxPct} testId="help-retention-max-pct" />
              </Label>
              <div className="relative">
                <Input
                  id="wiz-ret-pct"
                  type="number" min={1} max={100} value={retentionMaxPct}
                  onChange={(e) => setRetentionMaxPct(Math.max(1, Math.min(100, parseInt(e.target.value || "0", 10))))}
                  className="pr-7"
                  data-testid="wizard-retention-max-pct"
                />
                <span className="absolute inset-y-0 right-3 flex items-center text-xs text-muted-foreground">%</span>
              </div>
            </div>
          </div>
        )}
        {!retentionEnabled && (
          <p className="text-xs text-muted-foreground italic">
            Retention is OFF — trades transfer the full contract to the new team.
          </p>
        )}
      </div>
    </div>
  );
}
