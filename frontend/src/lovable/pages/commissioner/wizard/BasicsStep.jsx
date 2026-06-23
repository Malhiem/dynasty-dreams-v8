// @ts-nocheck
/**
 * Iter 228c — Basics step extracted from SetupWizard.jsx
 */
import { Trophy } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import HelpTooltip from "@/components/ui/help-tooltip";

const FORMAT_LABELS = { dynasty: "Dynasty", keeper: "Keeper", redraft: "Redraft" };
const SCORING_LABELS = { head_to_head: "Head to Head", roto: "Roto", points: "Points" };

export default function BasicsStep({ ctx }) {
  const {
    HELP,
    league,
    previousSeasonSuggestion,
    teams,
    maxTeams, setMaxTeams,
    leagueFormat, setLeagueFormat,
    scoringFormat, setScoringFormat,
    rosterSpots, setRosterSpots,
    benchSpots, setBenchSpots,
    minorsSpots, setMinorsSpots,
    minorsEnabled, setMinorsEnabled,
  } = ctx;

  return (
    <div className="space-y-3" data-testid="wizard-body-basics">
      {previousSeasonSuggestion && (
        <div className="rounded-md border border-accent/40 bg-accent/10 p-3 text-xs flex items-start gap-2" data-testid="wizard-prev-season-banner">
          <Trophy className="h-4 w-4 text-accent mt-0.5 shrink-0" />
          <div>
            <p className="font-semibold text-accent">Suggesting last year&apos;s setup</p>
            <p className="text-muted-foreground mt-0.5">
              Pre-filled from your <strong>{previousSeasonSuggestion.previous_season_year}</strong> season
              {previousSeasonSuggestion.champion ? ` (champion: ${previousSeasonSuggestion.champion})` : ""}.
            </p>
          </div>
        </div>
      )}
      <p className="text-sm text-muted-foreground">
        Welcome to <strong>{league?.name || "your league"}</strong>! We&apos;ll walk you through the core setup.
        You can revisit each step anytime from Commissioner Settings.
      </p>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm" data-testid="wizard-basics-editable-stats">
        <div className="stat-card p-3">
          <Label className="text-muted-foreground text-xs" htmlFor="wiz-stat-teams">Teams</Label>
          <Input
            id="wiz-stat-teams"
            type="number" min={2} max={32} value={maxTeams}
            onChange={(e) => setMaxTeams(Math.max(2, Math.min(32, parseInt(e.target.value || "0", 10))))}
            className="font-bold h-8 mt-1"
            data-testid="wizard-max-teams"
          />
          {teams.length < maxTeams && (
            <p className="text-[10px] text-muted-foreground mt-1" data-testid="wizard-placeholder-hint">
              {teams.length}/{maxTeams} filled · {maxTeams - teams.length} open slot{maxTeams - teams.length === 1 ? "" : "s"}
            </p>
          )}
        </div>
        <div className="stat-card p-3">
          <Label className="text-muted-foreground text-xs" htmlFor="wiz-stat-format">Format</Label>
          <select
            id="wiz-stat-format"
            value={leagueFormat}
            onChange={(e) => setLeagueFormat(e.target.value)}
            className="w-full mt-1 h-8 rounded-md border border-input bg-background px-2 text-sm font-bold"
            data-testid="wizard-format-select"
          >
            {Object.entries(FORMAT_LABELS).map(([v, label]) => (
              <option key={v} value={v}>{label}</option>
            ))}
          </select>
        </div>
        <div className="stat-card p-3">
          <Label className="text-muted-foreground text-xs" htmlFor="wiz-stat-scoring">Scoring</Label>
          <select
            id="wiz-stat-scoring"
            value={scoringFormat}
            onChange={(e) => setScoringFormat(e.target.value)}
            className="w-full mt-1 h-8 rounded-md border border-input bg-background px-2 text-sm font-bold"
            data-testid="wizard-scoring-select"
          >
            {Object.entries(SCORING_LABELS).map(([v, label]) => (
              <option key={v} value={v}>{label}</option>
            ))}
          </select>
        </div>
        <div className="stat-card p-3">
          <span className="text-muted-foreground text-xs">Sport</span>
          <div className="font-bold uppercase mt-1">{league?.sport || "nhl"}</div>
        </div>
      </div>

      <div className="space-y-3 border-t border-border pt-3">
        <h3 className="text-sm font-semibold text-white">Roster Shape</h3>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
          <div>
            <Label className="text-xs flex items-center" htmlFor="wiz-roster">
              Roster spots
              <HelpTooltip text={HELP.rosterSpots} testId="help-roster-spots" />
            </Label>
            <Input id="wiz-roster" type="number" min={10} max={40} value={rosterSpots}
              onChange={(e) => setRosterSpots(Math.max(10, Math.min(40, parseInt(e.target.value || "0", 10))))}
              data-testid="wizard-roster-spots" />
          </div>
          <div>
            <Label className="text-xs flex items-center" htmlFor="wiz-bench">
              Bench spots
              <HelpTooltip text={HELP.benchSpots} testId="help-bench-spots" />
            </Label>
            <Input id="wiz-bench" type="number" min={0} max={20} value={benchSpots}
              onChange={(e) => setBenchSpots(Math.max(0, Math.min(20, parseInt(e.target.value || "0", 10))))}
              data-testid="wizard-bench-spots" />
          </div>
          {minorsEnabled && (
            <div>
              <Label className="text-xs flex items-center" htmlFor="wiz-minors">
                Minors spots
                <HelpTooltip text={HELP.minors} testId="help-minors-spots" />
              </Label>
              <Input id="wiz-minors" type="number" min={0} max={100} value={minorsSpots}
                onChange={(e) => setMinorsSpots(Math.max(0, Math.min(100, parseInt(e.target.value || "0", 10))))}
                data-testid="wizard-minors-spots" />
            </div>
          )}
        </div>
        <div className="flex items-center gap-3 pt-1">
          <Switch checked={minorsEnabled} onCheckedChange={setMinorsEnabled} id="wiz-minors-enabled" data-testid="wizard-minors-enabled" />
          <Label htmlFor="wiz-minors-enabled" className="cursor-pointer flex items-center text-sm">
            Enable minors pool (Premium)
            <HelpTooltip text={HELP.minors} testId="help-minors-toggle" />
          </Label>
        </div>
      </div>
    </div>
  );
}
