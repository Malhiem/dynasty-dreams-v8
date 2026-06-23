// @ts-nocheck
/**
 * Iter 228 — Schedule step extracted from SetupWizard.jsx
 *
 * Receives the full ctx bundle (state + setters + helpers) from the
 * parent wizard so all behaviour stays unchanged. This file is purely
 * presentational JSX for the Schedule step.
 */
import { AlertTriangle, Plus, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Checkbox } from "@/components/ui/checkbox";
import HelpTooltip from "@/components/ui/help-tooltip";

export default function ScheduleStep({ ctx }) {
  const {
    HELP,
    divSet,
    seasonStart, setSeasonStart,
    seasonEnd, setSeasonEnd,
    matchupLength, setMatchupLength,
    opponentsPerPeriod, setOpponentsPerPeriod,
    numWeeks, setNumWeeks,
    weekOverrides, setWeekOverrides,
    schedule, setSchedule,
    playoffStartWeek, setPlayoffStartWeek,
    playoffEndWeek, setPlayoffEndWeek,
    consolationEnabled, setConsolationEnabled,
    consolationAlongPlayoffs, setConsolationAlongPlayoffs,
    consolationStartWeek, setConsolationStartWeek,
    consolationEndWeek, setConsolationEndWeek,
  } = ctx;

  return (
    <div className="space-y-4" data-testid="wizard-body-schedule">
      {divSet.size < 2 && (
        <div className="rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-xs text-amber-200 flex items-start gap-2">
          <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" />
          <span>
            You don&apos;t have 2+ divisions yet. Schedule-mix settings will save but only take effect once divisions are in place — or skip ahead to generate a vanilla round-robin.
          </span>
        </div>
      )}

      {/* Calendar window */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div>
          <Label className="text-xs flex items-center" htmlFor="wiz-season-start">
            Season start date
            <HelpTooltip text={HELP.seasonStart} testId="help-season-start" />
          </Label>
          <Input id="wiz-season-start" type="date" value={seasonStart}
            onChange={(e) => setSeasonStart(e.target.value)}
            data-testid="wizard-season-start" />
        </div>
        <div>
          <Label className="text-xs flex items-center" htmlFor="wiz-season-end">
            Season end date
            <HelpTooltip text={HELP.seasonEnd} testId="help-season-end" />
          </Label>
          <Input id="wiz-season-end" type="date" value={seasonEnd}
            onChange={(e) => setSeasonEnd(e.target.value)}
            data-testid="wizard-season-end" />
        </div>
      </div>

      {/* Matchup period config */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <div>
          <Label className="text-xs flex items-center" htmlFor="wiz-matchup-len">
            Matchup length (days)
            <HelpTooltip text={HELP.matchupLen} testId="help-matchup-len" />
          </Label>
          <Input id="wiz-matchup-len" type="number" min={1} max={30}
            value={matchupLength}
            onChange={(e) => setMatchupLength(Math.max(1, Math.min(30, parseInt(e.target.value || "0", 10))))}
            data-testid="wizard-matchup-length" />
        </div>
        <div>
          <Label className="text-xs flex items-center" htmlFor="wiz-opp-per">
            Opponents per period
            <HelpTooltip text={HELP.oppPerPeriod} testId="help-opp-per" />
          </Label>
          <Input id="wiz-opp-per" type="number" min={1} max={10}
            value={opponentsPerPeriod}
            onChange={(e) => setOpponentsPerPeriod(Math.max(1, Math.min(10, parseInt(e.target.value || "0", 10))))}
            data-testid="wizard-opponents-per-period" />
        </div>
        <div>
          <Label className="text-xs flex items-center" htmlFor="wiz-weeks">
            Regular season weeks
            <HelpTooltip text={HELP.weeks} testId="help-weeks" />
          </Label>
          <Input id="wiz-weeks" type="number" min={4} max={30}
            value={numWeeks}
            onChange={(e) => setNumWeeks(Math.max(4, Math.min(30, parseInt(e.target.value || "0", 10))))}
            data-testid="wizard-num-weeks" />
        </div>
      </div>

      {/* Iter 226 — Per-week matchup-length overrides */}
      <div className="rounded border border-border p-3 space-y-2" data-testid="wizard-week-overrides">
        <div className="flex items-center justify-between">
          <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground flex items-center">
            Custom-length weeks
            <HelpTooltip
              text="Override matchup length for irregular weeks — late-season starts, winter-break returns, all-star, etc. Each override widens that week's calendar window without shifting later weeks."
              testId="help-week-overrides"
            />
          </h4>
          <Button
            size="sm"
            variant="outline"
            onClick={() => setWeekOverrides([...weekOverrides, { week_num: 1, length_days: 10, label: "" }])}
            data-testid="wizard-add-week-override-btn"
          >
            <Plus className="h-3.5 w-3.5 mr-1" /> Add custom week
          </Button>
        </div>
        {weekOverrides.length === 0 ? (
          <p className="text-[11px] text-muted-foreground italic">
            Every week defaults to {matchupLength} days. Add an override for weeks that should be longer or shorter.
          </p>
        ) : (
          <ul className="space-y-2">
            {weekOverrides.map((ov, idx) => (
              <li
                key={idx}
                className="grid grid-cols-12 items-center gap-2 text-xs"
                data-testid={`wizard-week-override-row-${idx}`}
              >
                <div className="col-span-3">
                  <Label className="text-[10px] text-muted-foreground">Week #</Label>
                  <Input
                    type="number" min={1} max={numWeeks}
                    value={ov.week_num || 1}
                    onChange={(e) => {
                      const next = [...weekOverrides];
                      next[idx] = { ...next[idx], week_num: Math.max(1, parseInt(e.target.value || "0", 10)) };
                      setWeekOverrides(next);
                    }}
                    className="h-8"
                    data-testid={`wizard-week-override-week-${idx}`}
                  />
                </div>
                <div className="col-span-3">
                  <Label className="text-[10px] text-muted-foreground">Length (days)</Label>
                  <Input
                    type="number" min={1} max={21}
                    value={ov.length_days || 7}
                    onChange={(e) => {
                      const next = [...weekOverrides];
                      next[idx] = { ...next[idx], length_days: Math.max(1, Math.min(21, parseInt(e.target.value || "0", 10))) };
                      setWeekOverrides(next);
                    }}
                    className="h-8"
                    data-testid={`wizard-week-override-length-${idx}`}
                  />
                </div>
                <div className="col-span-5">
                  <Label className="text-[10px] text-muted-foreground">Label (optional)</Label>
                  <Input
                    type="text"
                    placeholder="Winter break, All-Star, etc."
                    value={ov.label || ""}
                    onChange={(e) => {
                      const next = [...weekOverrides];
                      next[idx] = { ...next[idx], label: e.target.value };
                      setWeekOverrides(next);
                    }}
                    className="h-8"
                    data-testid={`wizard-week-override-label-${idx}`}
                  />
                </div>
                <div className="col-span-1 flex justify-end pt-3">
                  <button
                    type="button"
                    onClick={() => setWeekOverrides(weekOverrides.filter((_, i) => i !== idx))}
                    className="text-muted-foreground hover:text-rose-400"
                    aria-label="Remove override"
                    data-testid={`wizard-week-override-remove-${idx}`}
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Schedule mix */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <div>
          <Label className="text-xs flex items-center">
            Intra-division games
            <HelpTooltip text={HELP.intraDiv} testId="help-intra-div" />
          </Label>
          <Input type="number" min={0} max={10} value={schedule.intra_division_games}
            onChange={(e) => setSchedule({ ...schedule, intra_division_games: Math.max(0, Math.min(10, parseInt(e.target.value || "0", 10))) })}
            data-testid="wizard-schedule-intra-div" />
        </div>
        <div>
          <Label className="text-xs flex items-center">
            Intra-conference games
            <HelpTooltip text={HELP.intraConf} testId="help-intra-conf" />
          </Label>
          <Input type="number" min={0} max={10} value={schedule.intra_conference_games}
            onChange={(e) => setSchedule({ ...schedule, intra_conference_games: Math.max(0, Math.min(10, parseInt(e.target.value || "0", 10))) })}
            data-testid="wizard-schedule-intra-conf" />
        </div>
        <div>
          <Label className="text-xs flex items-center">
            Inter-conference games
            <HelpTooltip text={HELP.interConf} testId="help-inter-conf" />
          </Label>
          <Input type="number" min={0} max={10} value={schedule.inter_conference_games}
            onChange={(e) => setSchedule({ ...schedule, inter_conference_games: Math.max(0, Math.min(10, parseInt(e.target.value || "0", 10))) })}
            data-testid="wizard-schedule-inter-conf" />
        </div>
      </div>

      {/* Playoffs window */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 border-t border-border pt-3">
        <div>
          <Label className="text-xs flex items-center">
            Playoffs start (week)
            <HelpTooltip text={HELP.playoffStart} testId="help-playoff-start" />
          </Label>
          <Input type="number" min={1} max={30} value={playoffStartWeek}
            onChange={(e) => setPlayoffStartWeek(Math.max(1, Math.min(30, parseInt(e.target.value || "0", 10))))}
            data-testid="wizard-playoff-start" />
        </div>
        <div>
          <Label className="text-xs flex items-center">
            Playoffs end (week)
            <HelpTooltip text={HELP.playoffEnd} testId="help-playoff-end" />
          </Label>
          <Input type="number" min={1} max={40} value={playoffEndWeek}
            onChange={(e) => setPlayoffEndWeek(Math.max(1, Math.min(40, parseInt(e.target.value || "0", 10))))}
            data-testid="wizard-playoff-end" />
        </div>
      </div>

      {/* Consolation A/B */}
      <div className="space-y-3 border-t border-border pt-3" data-testid="wizard-consolation-card">
        <div className="flex items-center gap-3">
          <Switch
            checked={consolationEnabled}
            onCheckedChange={setConsolationEnabled}
            id="wiz-consolation-enabled"
            data-testid="wizard-consolation-enabled"
          />
          <Label htmlFor="wiz-consolation-enabled" className="cursor-pointer flex items-center font-semibold">
            Run a consolation playoff bracket?
            <HelpTooltip text={HELP.consolation} testId="help-consolation" />
          </Label>
        </div>
        {consolationEnabled && (
          <div className="space-y-2 pl-1">
            <div className="flex items-center gap-2">
              <Checkbox
                id="wiz-consolation-along"
                checked={consolationAlongPlayoffs}
                onCheckedChange={(c) => setConsolationAlongPlayoffs(!!c)}
                data-testid="wizard-consolation-along"
              />
              <Label htmlFor="wiz-consolation-along" className="cursor-pointer text-sm flex items-center">
                Schedule along with playoffs
                <HelpTooltip text={HELP.consolationAlong} testId="help-consolation-along" />
              </Label>
            </div>
            {!consolationAlongPlayoffs && (
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label className="text-xs">Consolation start (week)</Label>
                  <Input type="number" min={1} max={40}
                    value={consolationStartWeek}
                    onChange={(e) => setConsolationStartWeek(Math.max(1, Math.min(40, parseInt(e.target.value || "0", 10))))}
                    data-testid="wizard-consolation-start" />
                </div>
                <div>
                  <Label className="text-xs">Consolation end (week)</Label>
                  <Input type="number" min={1} max={40}
                    value={consolationEndWeek}
                    onChange={(e) => setConsolationEndWeek(Math.max(1, Math.min(40, parseInt(e.target.value || "0", 10))))}
                    data-testid="wizard-consolation-end" />
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
