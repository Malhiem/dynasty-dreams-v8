// @ts-nocheck
/**
 * Iter 228c — Basics step extracted from SetupWizard.jsx
 * Iter 232N.80 — Sandbox admins can bulk-add test teams in this step.
 */
import { useState } from "react";
import { Trophy, FlaskConical, Plus, RefreshCw } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Button } from "@/components/ui/button";
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
    allowDuplicatePlayers, setAllowDuplicatePlayers,
    addSandboxTeams,
    addingSandboxTeams,
  } = ctx;

  const isSandbox = Boolean(league?.is_test_sandbox);
  // Iter 232N.83 — Duplicate-player mode unlocks max_teams > 32
  // (up to 100). Without it, the wizard clamps to the classic
  // mutually-exclusive draft-pool ceiling.
  const teamCapMax = allowDuplicatePlayers ? 100 : 32;
  const openSlots = Math.max(0, maxTeams - teams.length);
  // Default the "how many to add" input to whatever gets the league to
  // the target maxTeams (or 4 when we're already at capacity).
  const [addN, setAddN] = useState(() => Math.max(1, openSlots || 4));

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
            type="number" min={2} max={teamCapMax} value={maxTeams}
            onChange={(e) => setMaxTeams(Math.max(2, Math.min(teamCapMax, parseInt(e.target.value || "0", 10))))}
            className="font-bold h-8 mt-1"
            data-testid="wizard-max-teams"
          />
          {teams.length < maxTeams && (
            <p className="text-[10px] text-muted-foreground mt-1" data-testid="wizard-placeholder-hint">
              {teams.length}/{maxTeams} filled · {maxTeams - teams.length} open slot{maxTeams - teams.length === 1 ? "" : "s"}
            </p>
          )}
          {maxTeams > 32 && !allowDuplicatePlayers && (
            <p className="text-[10px] text-rose-300 mt-1" data-testid="wizard-teams-over-cap-warning">
              &gt; 32 teams requires duplicate-player mode below.
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

      {/* Iter 232N.83 — Duplicate-players toggle. Required to unlock
          max_teams > 32 (see server-side gate in routes/leagues.py). */}
      <div
        className="rounded-md border border-border p-3 flex items-start justify-between gap-3"
        data-testid="wizard-duplicate-players-row"
      >
        <div>
          <Label
            className="text-xs font-semibold text-white flex items-center gap-1"
            htmlFor="wizard-duplicate-players-toggle"
          >
            Duplicate players for selection
          </Label>
          <p className="text-[11px] text-muted-foreground mt-0.5">
            Let the same player be drafted onto multiple teams. Required
            for leagues with more than 32 teams (large leagues would
            otherwise run out of starters). Team cap:&nbsp;
            <strong className="text-white">{teamCapMax}</strong>.
          </p>
        </div>
        <Switch
          id="wizard-duplicate-players-toggle"
          checked={Boolean(allowDuplicatePlayers)}
          onCheckedChange={(v) => {
            setAllowDuplicatePlayers(Boolean(v));
            if (!v && maxTeams > 32) {
              // Coming back OFF — clamp maxTeams back to 32.
              setMaxTeams(32);
            }
          }}
          data-testid="wizard-duplicate-players-toggle"
        />
      </div>

      {/* Iter 232N.80 — Sandbox-only bulk-team-add panel. Lets platform
          admins seed the sandbox up to the target team count in one
          click before running the Divisions + Schedule steps. */}
      {isSandbox && (
        <div
          className="border border-fuchsia-500/40 bg-fuchsia-500/5 rounded p-3 space-y-2"
          data-testid="wizard-basics-sandbox-teams-panel"
        >
          <div className="flex items-center gap-2 flex-wrap">
            <FlaskConical className="h-3.5 w-3.5 text-fuchsia-300 shrink-0" />
            <h4 className="text-xs font-semibold uppercase tracking-wide text-fuchsia-200">
              Sandbox test teams
            </h4>
            <span
              className="text-[11px] text-fuchsia-100/80"
              data-testid="wizard-sandbox-teams-count"
            >
              Currently: {teams.length} team{teams.length === 1 ? "" : "s"} · {openSlots} open slot{openSlots === 1 ? "" : "s"}
            </span>
          </div>
          <p className="text-[11px] text-muted-foreground">
            Each added team gets a fake owner (auto-generated username +
            password), an empty roster, and joins the league instantly —
            perfect for prepping a sandbox before running Divisions or
            simulating a draft.
          </p>
          <div className="flex items-center gap-2 flex-wrap">
            <Label
              htmlFor="wizard-sandbox-add-count"
              className="text-[11px] text-fuchsia-100"
            >
              Add
            </Label>
            <Input
              id="wizard-sandbox-add-count"
              type="number"
              min={1}
              max={32}
              value={addN}
              onChange={(e) => setAddN(Math.max(1, Math.min(32, parseInt(e.target.value || "0", 10))))}
              className="h-8 text-xs w-16"
              data-testid="wizard-sandbox-add-count"
            />
            <span className="text-[11px] text-fuchsia-100">team(s)</span>
            <Button
              size="sm"
              variant="outline"
              className="h-8 text-[11px] bg-fuchsia-500/20 border-fuchsia-500/40 text-fuchsia-50 hover:bg-fuchsia-500/30"
              onClick={() => addSandboxTeams(addN)}
              disabled={addingSandboxTeams}
              data-testid="wizard-sandbox-add-teams-btn"
            >
              {addingSandboxTeams ? (
                <RefreshCw className="h-3 w-3 mr-1 animate-spin" />
              ) : (
                <Plus className="h-3 w-3 mr-1" />
              )}
              Add sandbox teams
            </Button>
            {openSlots > 0 && (
              <Button
                size="sm"
                variant="ghost"
                className="h-8 text-[10px] text-fuchsia-200 hover:text-fuchsia-50"
                onClick={() => addSandboxTeams(openSlots)}
                disabled={addingSandboxTeams}
                data-testid="wizard-sandbox-fill-btn"
                title={`Fill every open slot to reach ${maxTeams} teams`}
              >
                Fill to {maxTeams}
              </Button>
            )}
          </div>
        </div>
      )}

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
