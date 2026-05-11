// @ts-nocheck
import { useEffect, useState } from "react";
import api from "@/lib/api";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { toast } from "sonner";
import { Check, ChevronLeft, ChevronRight, Wand2, Trophy, DollarSign, Network, Calendar, Rocket, SkipForward } from "lucide-react";
import HelpTooltip from "@/components/ui/help-tooltip";
import PremiumTrialBanner from "@/lovable/components/PremiumTrialBanner";

const STEPS = [
  { id: "basics", label: "Basics", icon: Wand2 },
  { id: "cap", label: "Salary Cap", icon: DollarSign },
  { id: "divisions", label: "League Structure", icon: Network },
  { id: "schedule", label: "Schedule Mix", icon: Calendar },
  { id: "generate", label: "Generate", icon: Rocket },
];

const HELP = {
  rosterSpots: "Total number of active players each team carries on its NHL roster. Skaters + goalies that score points each week.",
  benchSpots: "Inactive players that don't score this week but stay on the roster — typically for matchup planning or injury cover.",
  minors: "A separate prospects pool used by Dynasty leagues. Players here don't count against your active roster or salary cap. Available when 'Minors' premium feature is enabled.",
  capEnable: "Imposes a maximum total contract value across all rostered players. Required for realistic Dynasty cap management. Premium feature.",
  capAmount: "Maximum aggregate salary across all rostered players. NHL real-world cap for 2025-26 is $82.5M.",
  retentionSlots: "When you trade a player, you can keep paying a portion of their salary. Each 'slot' lets you retain 1 contract at any time.",
  divisions: "Group teams into divisions and conferences (e.g. NHL has 4 divisions in 2 conferences). Required for division-aware scheduling, playoff seeding, and President's Trophy calculation.",
  intraDiv: "Games against teams in your OWN division (default 2 — home-and-home with each rival).",
  intraConf: "Games against teams in your OWN conference but DIFFERENT division (default 1).",
  interConf: "Games against teams in the OTHER conference (default 1).",
  weeks: "Regular season length (recommended 18-22). Playoffs are scheduled separately and don't count toward this number.",
  skip: "Skip the wizard and configure each setting later from Commissioner Settings. Setup-complete flag still gets recorded so this dialog won't open again automatically.",
};

export default function SetupWizard({ open, onClose, leagueId, onComplete }) {
  const [league, setLeague] = useState(null);
  const [teams, setTeams] = useState([]);
  const [stepIdx, setStepIdx] = useState(0);
  const [busy, setBusy] = useState(false);
  const [skipConfirmOpen, setSkipConfirmOpen] = useState(false);

  // Form state (seeded from backend on open)
  const [rosterSpots, setRosterSpots] = useState(20);
  const [benchSpots, setBenchSpots] = useState(5);
  const [minorsSpots, setMinorsSpots] = useState(5);
  const [minorsEnabled, setMinorsEnabled] = useState(false);
  const [capEnabled, setCapEnabled] = useState(false);
  const [capAmount, setCapAmount] = useState(82500000);
  const [retentionSlots, setRetentionSlots] = useState(3);

  const [divisionAssignments, setDivisionAssignments] = useState({}); // teamId → {division, conference}
  const [schedule, setSchedule] = useState({ intra_division_games: 2, intra_conference_games: 1, inter_conference_games: 1 });
  const [numWeeks, setNumWeeks] = useState(18);
  const [scheduleMode, setScheduleMode] = useState(null);
  const [previousSeasonSuggestion, setPreviousSeasonSuggestion] = useState(null);

  // Load everything once when wizard opens
  useEffect(() => {
    if (!open || !leagueId) return;
    let cancelled = false;
    (async () => {
      try {
        const [lgR, teamsR, cfgR, sugR] = await Promise.all([
          api.get(`/leagues/${leagueId}`),
          api.get(`/teams?league_id=${leagueId}`),
          api.get(`/leagues/${leagueId}/schedule-config`).catch(() => ({ data: null })),
          api.get(`/leagues/${leagueId}/setup-suggestions`).catch(() => ({ data: null })),
        ]);
        if (cancelled) return;
        setLeague(lgR.data);
        const sug = sugR?.data?.has_previous_season ? sugR.data : null;
        setPreviousSeasonSuggestion(sug);
        // Prefer previous-season cap config when present
        const capCfg = sug?.salary_cap_config;
        setCapEnabled(capCfg ? !!capCfg.enabled : !!lgR.data?.salary_cap_enabled);
        setCapAmount(capCfg?.amount || lgR.data?.salary_cap || 82500000);
        setRetentionSlots(capCfg?.retention_slots ?? lgR.data?.salary_retention_slots ?? 3);
        setMinorsEnabled(!!lgR.data?.minors_enabled);
        setRosterSpots(lgR.data?.roster_spots ?? 20);
        setBenchSpots(lgR.data?.bench_spots ?? 5);
        setMinorsSpots(lgR.data?.minors_spots ?? 5);
        setTeams(teamsR.data || []);
        const seeded = {};
        (teamsR.data || []).forEach((t) => {
          seeded[t.id] = { division: t.division || "", conference: t.conference || "" };
        });
        setDivisionAssignments(seeded);
        // Prefer previous-season schedule_config when present
        const schCfg = sug?.schedule_config || cfgR?.data;
        if (schCfg) setSchedule({
          intra_division_games: schCfg.intra_division_games ?? 2,
          intra_conference_games: schCfg.intra_conference_games ?? 1,
          inter_conference_games: schCfg.inter_conference_games ?? 1,
        });
      } catch (e) {
        toast.error("Failed to load league for setup wizard");
      }
    })();
    return () => { cancelled = true; };
  }, [open, leagueId]);

  const step = STEPS[stepIdx];
  const isLast = stepIdx === STEPS.length - 1;

  const autoAssignNHL = () => {
    const divs = ["Atlantic", "Metropolitan", "Central", "Pacific"];
    const confOf = (d) => (d === "Atlantic" || d === "Metropolitan") ? "Eastern" : "Western";
    const next = {};
    teams.forEach((t, idx) => {
      const div = divs[idx % 4];
      next[t.id] = { division: div, conference: confOf(div) };
    });
    setDivisionAssignments(next);
    toast.info("Auto-assigned 4 divisions / 2 conferences");
  };

  const saveBasicsAndCap = async () => {
    setBusy(true);
    try {
      // Cap + minors settings go through the league admin endpoint. This
      // also starts the 14-day premium trial clock when either premium
      // feature is freshly enabled.
      try {
        await api.put(`/leagues/${leagueId}/admin/cap-settings`, {
          salary_cap_enabled: capEnabled,
          salary_cap: capEnabled ? capAmount : null,
          salary_retention_slots: retentionSlots,
          minors_enabled: minorsEnabled,
        });
      } catch (e) {
        // If that endpoint doesn't exist, silently skip — user can configure in settings.
      }
      // Roster shape lives on the league doc.
      try {
        await api.put(`/leagues/${leagueId}`, {
          roster_spots: rosterSpots,
          bench_spots: benchSpots,
          minors_spots: minorsEnabled ? minorsSpots : 0,
        });
      } catch (e) {
        // Silent — league update endpoint may not yet accept these fields.
      }
    } finally {
      setBusy(false);
    }
  };

  const saveDivisions = async () => {
    setBusy(true);
    try {
      const assignments = teams.map((t) => ({
        team_id: t.id,
        division: divisionAssignments[t.id]?.division || null,
        conference: divisionAssignments[t.id]?.conference || null,
      }));
      await api.put(`/leagues/${leagueId}/divisions`, { assignments });
      toast.success("Divisions saved");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to save divisions");
    } finally {
      setBusy(false);
    }
  };

  const saveSchedule = async () => {
    setBusy(true);
    try {
      await api.put(`/leagues/${leagueId}/schedule-config`, schedule);
      toast.success("Schedule mix saved");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to save schedule mix");
    } finally {
      setBusy(false);
    }
  };

  const generateSchedule = async () => {
    setBusy(true);
    try {
      const res = await api.post("/matchups/generate-schedule", { league_id: leagueId, num_weeks: numWeeks });
      setScheduleMode(res.data?.mode);
      toast.success(`Generated ${res.data?.weeks || numWeeks}-week schedule (${res.data?.mode || "round_robin"})`);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to generate schedule");
    } finally {
      setBusy(false);
    }
  };

  const finish = async () => {
    setBusy(true);
    try {
      await api.post(`/leagues/${leagueId}/setup-complete`);
      toast.success("Setup complete! Your league is ready.");
      onComplete && onComplete();
      onClose();
    } catch (e) {
      toast.error("Failed to mark setup complete");
    } finally {
      setBusy(false);
    }
  };

  const skipWizard = async () => {
    setBusy(true);
    try {
      // Mark setup complete without saving any pending changes, then close
      await api.post(`/leagues/${leagueId}/setup-complete`).catch(() => {});
      toast.info("Setup skipped — you can configure each step later from Commissioner Settings.");
      onComplete && onComplete();
      onClose();
    } finally {
      setBusy(false);
      setSkipConfirmOpen(false);
    }
  };

  const next = async () => {
    if (step.id === "basics") await saveBasicsAndCap();
    else if (step.id === "cap") await saveBasicsAndCap();
    else if (step.id === "divisions") await saveDivisions();
    else if (step.id === "schedule") await saveSchedule();
    if (!isLast) setStepIdx(stepIdx + 1);
  };

  const divSet = new Set(Object.values(divisionAssignments).map((a) => a.division).filter(Boolean));

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto" data-testid="setup-wizard-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-xl">
            <Trophy className="h-5 w-5 text-accent" />
            League Setup Wizard
          </DialogTitle>
          <DialogDescription>
            Walk through 5 quick steps to configure your league: basics, salary cap, divisions, schedule mix, and regular-season generation.
          </DialogDescription>
        </DialogHeader>

        {/* Stepper */}
        <div className="flex items-center gap-2 overflow-x-auto pb-2 mb-2" data-testid="setup-wizard-stepper">
          {STEPS.map((s, i) => {
            const Icon = s.icon;
            const active = i === stepIdx;
            const done = i < stepIdx;
            return (
              <div key={s.id} className="flex items-center gap-2 shrink-0">
                <div
                  className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-xs font-semibold transition-colors ${
                    active ? "bg-accent text-accent-foreground border-accent" :
                    done ? "bg-success/20 text-success border-success/40" :
                    "bg-secondary/30 text-muted-foreground border-border"
                  }`}
                  data-testid={`wizard-step-${s.id}`}
                >
                  {done ? <Check className="h-3.5 w-3.5" /> : <Icon className="h-3.5 w-3.5" />}
                  {s.label}
                </div>
                {i < STEPS.length - 1 && <ChevronRight className="h-3.5 w-3.5 text-muted-foreground/60" />}
              </div>
            );
          })}
        </div>

        {/* Premium trial banner — visible from step 1 once user toggles a premium feature */}
        {(capEnabled || minorsEnabled) && (
          <PremiumTrialBanner leagueId={leagueId} isCommissioner />
        )}

        {/* Step body */}
        {step.id === "basics" && (
          <div className="space-y-3" data-testid="wizard-body-basics">
            {previousSeasonSuggestion && (
              <div className="rounded-md border border-accent/40 bg-accent/10 p-3 text-xs flex items-start gap-2" data-testid="wizard-prev-season-banner">
                <Trophy className="h-4 w-4 text-accent mt-0.5 shrink-0" />
                <div>
                  <p className="font-semibold text-accent">Suggesting last year&apos;s setup</p>
                  <p className="text-muted-foreground mt-0.5">
                    Pre-filled from your <strong>{previousSeasonSuggestion.previous_season_year}</strong> season
                    {previousSeasonSuggestion.champion ? ` (champion: ${previousSeasonSuggestion.champion})` : ""}.
                    You can override anything below.
                  </p>
                </div>
              </div>
            )}
            <p className="text-sm text-muted-foreground">
              Welcome to <strong>{league?.name || "your league"}</strong>! We&apos;ll walk you through the core setup.
              You can revisit each step anytime from Commissioner Settings.
            </p>
            <div className="grid grid-cols-2 gap-3 text-sm">
              <div className="stat-card p-3"><span className="text-muted-foreground">Teams</span><div className="font-bold">{teams.length}</div></div>
              <div className="stat-card p-3"><span className="text-muted-foreground">Format</span><div className="font-bold">{league?.format || "—"}</div></div>
              <div className="stat-card p-3"><span className="text-muted-foreground">Scoring</span><div className="font-bold">{league?.scoring_format || "head_to_head"}</div></div>
              <div className="stat-card p-3"><span className="text-muted-foreground">Sport</span><div className="font-bold uppercase">{league?.sport || "nhl"}</div></div>
            </div>

            {/* Roster shape configuration */}
            <div className="space-y-3 border-t border-border pt-3">
              <h3 className="text-sm font-semibold text-white">Roster Shape</h3>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                <div>
                  <Label className="text-xs flex items-center" htmlFor="wiz-roster">
                    Roster spots
                    <HelpTooltip text={HELP.rosterSpots} testId="help-roster-spots" />
                  </Label>
                  <Input
                    id="wiz-roster" type="number" min={10} max={40} value={rosterSpots}
                    onChange={(e) => setRosterSpots(Math.max(10, Math.min(40, parseInt(e.target.value || "0", 10))))}
                    data-testid="wizard-roster-spots"
                  />
                </div>
                <div>
                  <Label className="text-xs flex items-center" htmlFor="wiz-bench">
                    Bench spots
                    <HelpTooltip text={HELP.benchSpots} testId="help-bench-spots" />
                  </Label>
                  <Input
                    id="wiz-bench" type="number" min={0} max={20} value={benchSpots}
                    onChange={(e) => setBenchSpots(Math.max(0, Math.min(20, parseInt(e.target.value || "0", 10))))}
                    data-testid="wizard-bench-spots"
                  />
                </div>
                {minorsEnabled && (
                  <div>
                    <Label className="text-xs flex items-center" htmlFor="wiz-minors">
                      Minors spots
                      <HelpTooltip text={HELP.minors} testId="help-minors-spots" />
                    </Label>
                    <Input
                      id="wiz-minors" type="number" min={0} max={20} value={minorsSpots}
                      onChange={(e) => setMinorsSpots(Math.max(0, Math.min(20, parseInt(e.target.value || "0", 10))))}
                      data-testid="wizard-minors-spots"
                    />
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
        )}

        {step.id === "cap" && (
          <div className="space-y-4" data-testid="wizard-body-cap">
            <div className="flex items-center gap-3">
              <Switch checked={capEnabled} onCheckedChange={setCapEnabled} id="wiz-cap" />
              <Label htmlFor="wiz-cap" className="cursor-pointer flex items-center">
                Enable salary cap (Premium)
                <HelpTooltip text={HELP.capEnable} testId="help-cap-enable" />
              </Label>
            </div>
            {capEnabled && (
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label htmlFor="wiz-cap-amt" className="text-xs flex items-center">
                    Cap ($)
                    <HelpTooltip text={HELP.capAmount} testId="help-cap-amount" />
                  </Label>
                  <Input id="wiz-cap-amt" type="number" value={capAmount} onChange={(e) => setCapAmount(parseInt(e.target.value || "0", 10))} />
                </div>
                <div>
                  <Label htmlFor="wiz-ret" className="text-xs flex items-center">
                    Retention slots
                    <HelpTooltip text={HELP.retentionSlots} testId="help-retention-slots" />
                  </Label>
                  <Input id="wiz-ret" type="number" min={0} max={10} value={retentionSlots} onChange={(e) => setRetentionSlots(parseInt(e.target.value || "0", 10))} />
                </div>
              </div>
            )}
            {!capEnabled && <p className="text-xs text-muted-foreground italic">Salary cap is disabled — teams can roster any combination of players.</p>}
          </div>
        )}

        {step.id === "divisions" && (
          <div className="space-y-3" data-testid="wizard-body-divisions">
            <div className="flex items-center gap-2">
              <h3 className="text-sm font-semibold text-white flex items-center">
                League Structure
                <HelpTooltip text={HELP.divisions} testId="help-divisions" />
              </h3>
              <Button size="sm" variant="outline" onClick={autoAssignNHL} data-testid="wizard-auto-assign-nhl">
                Auto-assign NHL style
              </Button>
              <span className="text-xs text-muted-foreground">or configure manually below</span>
            </div>
            <div className="border border-border rounded max-h-[280px] overflow-y-auto">
              <table className="w-full text-sm">
                <thead className="bg-secondary/30 sticky top-0">
                  <tr className="text-xs font-medium text-muted-foreground">
                    <th className="py-2 pl-3 text-left">Team</th>
                    <th className="py-2 text-left">Division</th>
                    <th className="py-2 pr-3 text-left">Conference</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/50">
                  {teams.map((t) => (
                    <tr key={t.id}>
                      <td className="py-1.5 pl-3 font-medium">{t.name}</td>
                      <td className="py-1.5 pr-2">
                        <Input
                          className="h-7 text-xs"
                          value={divisionAssignments[t.id]?.division || ""}
                          onChange={(e) => setDivisionAssignments((prev) => ({ ...prev, [t.id]: { ...(prev[t.id] || {}), division: e.target.value } }))}
                          placeholder="—"
                        />
                      </td>
                      <td className="py-1.5 pr-3">
                        <Input
                          className="h-7 text-xs"
                          value={divisionAssignments[t.id]?.conference || ""}
                          onChange={(e) => setDivisionAssignments((prev) => ({ ...prev, [t.id]: { ...(prev[t.id] || {}), conference: e.target.value } }))}
                          placeholder="—"
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="text-xs text-muted-foreground">
              {divSet.size < 2
                ? "⚠️ Configure at least 2 divisions to unlock division-aware scheduling in the next step."
                : `✓ ${divSet.size} divisions configured.`}
            </p>
          </div>
        )}

        {step.id === "schedule" && (
          <div className="space-y-4" data-testid="wizard-body-schedule">
            {divSet.size < 2 && (
              <div className="rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-xs text-amber-200">
                You don&apos;t have 2+ divisions yet. Schedule-mix settings will save but only take effect once divisions are in place — or skip ahead to generate a vanilla round-robin.
              </div>
            )}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <div>
                <Label className="text-xs flex items-center">
                  Intra-division games
                  <HelpTooltip text={HELP.intraDiv} testId="help-intra-div" />
                </Label>
                <Input type="number" min={0} max={10} value={schedule.intra_division_games} onChange={(e) => setSchedule({ ...schedule, intra_division_games: Math.max(0, Math.min(10, parseInt(e.target.value || "0", 10))) })} data-testid="wizard-schedule-intra-div" />
              </div>
              <div>
                <Label className="text-xs flex items-center">
                  Intra-conference games
                  <HelpTooltip text={HELP.intraConf} testId="help-intra-conf" />
                </Label>
                <Input type="number" min={0} max={10} value={schedule.intra_conference_games} onChange={(e) => setSchedule({ ...schedule, intra_conference_games: Math.max(0, Math.min(10, parseInt(e.target.value || "0", 10))) })} data-testid="wizard-schedule-intra-conf" />
              </div>
              <div>
                <Label className="text-xs flex items-center">
                  Inter-conference games
                  <HelpTooltip text={HELP.interConf} testId="help-inter-conf" />
                </Label>
                <Input type="number" min={0} max={10} value={schedule.inter_conference_games} onChange={(e) => setSchedule({ ...schedule, inter_conference_games: Math.max(0, Math.min(10, parseInt(e.target.value || "0", 10))) })} data-testid="wizard-schedule-inter-conf" />
              </div>
            </div>
          </div>
        )}

        {step.id === "generate" && (
          <div className="space-y-4" data-testid="wizard-body-generate">
            <div className="stat-card p-4 space-y-3">
              <h3 className="text-sm font-bold">Ready to generate the season schedule</h3>
              <div className="grid grid-cols-2 gap-3 text-xs">
                <div><span className="text-muted-foreground">Salary cap:</span> <strong>{capEnabled ? `$${capAmount.toLocaleString()}` : "Disabled"}</strong></div>
                <div><span className="text-muted-foreground">Divisions:</span> <strong>{divSet.size}</strong></div>
                <div><span className="text-muted-foreground">Schedule mode:</span> <strong>{divSet.size >= 2 ? "Division-aware" : "Round-robin"}</strong></div>
                <div><span className="text-muted-foreground">Mix:</span> <strong>{schedule.intra_division_games}/{schedule.intra_conference_games}/{schedule.inter_conference_games}</strong></div>
              </div>
              <div className="flex items-end gap-2">
                <div className="flex-1">
                  <Label className="text-xs flex items-center">
                    Regular season weeks
                    <HelpTooltip text={HELP.weeks} testId="help-weeks" />
                  </Label>
                  <Input type="number" min={4} max={30} value={numWeeks} onChange={(e) => setNumWeeks(Math.max(4, Math.min(30, parseInt(e.target.value || "0", 10))))} data-testid="wizard-num-weeks" />
                </div>
                <Button size="sm" onClick={generateSchedule} disabled={busy} data-testid="wizard-generate-btn">
                  Generate schedule
                </Button>
              </div>
              {scheduleMode && (
                <p className="text-xs text-success">✓ Schedule generated ({scheduleMode}). Click Finish to complete setup.</p>
              )}
            </div>
          </div>
        )}

        {/* Nav buttons */}
        <div className="flex justify-between items-center pt-2 border-t border-border">
          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              size="sm"
              disabled={stepIdx === 0 || busy}
              onClick={() => setStepIdx(stepIdx - 1)}
              data-testid="wizard-back-btn"
            >
              <ChevronLeft className="h-4 w-4 mr-1" /> Back
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setSkipConfirmOpen(true)}
              disabled={busy}
              className="text-muted-foreground hover:text-foreground"
              data-testid="wizard-skip-btn"
              title="Skip setup wizard"
            >
              <SkipForward className="h-4 w-4 mr-1" /> Skip
              <HelpTooltip text={HELP.skip} testId="help-skip" />
            </Button>
          </div>
          <div className="text-xs text-muted-foreground">Step {stepIdx + 1} of {STEPS.length}</div>
          {!isLast ? (
            <Button size="sm" onClick={next} disabled={busy} data-testid="wizard-next-btn">
              Next <ChevronRight className="h-4 w-4 ml-1" />
            </Button>
          ) : (
            <Button size="sm" onClick={finish} disabled={busy} data-testid="wizard-finish-btn">
              <Check className="h-4 w-4 mr-1" /> Finish
            </Button>
          )}
        </div>
      </DialogContent>

      {/* Skip confirmation dialog */}
      <AlertDialog open={skipConfirmOpen} onOpenChange={setSkipConfirmOpen}>
        <AlertDialogContent data-testid="wizard-skip-confirm">
          <AlertDialogHeader>
            <AlertDialogTitle>Skip the setup wizard?</AlertDialogTitle>
            <AlertDialogDescription>
              Your league will be marked as set up, but none of the unsaved choices on this screen will be persisted.
              You can configure salary cap, league structure, schedule mix, and roster size later from
              <strong> Commissioner Settings</strong>.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel data-testid="wizard-skip-cancel">Keep setting up</AlertDialogCancel>
            <AlertDialogAction onClick={skipWizard} data-testid="wizard-skip-confirm-btn">
              Yes, skip
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Dialog>
  );
}
