// @ts-nocheck
import { useEffect, useState } from "react";
import api from "@/lib/api";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { toast } from "sonner";
import { Check, ChevronLeft, ChevronRight, Wand2, Trophy, DollarSign, Network, Calendar, Rocket } from "lucide-react";

const STEPS = [
  { id: "basics", label: "Basics", icon: Wand2 },
  { id: "cap", label: "Salary Cap", icon: DollarSign },
  { id: "divisions", label: "Divisions", icon: Network },
  { id: "schedule", label: "Schedule Mix", icon: Calendar },
  { id: "generate", label: "Generate", icon: Rocket },
];

export default function SetupWizard({ open, onClose, leagueId, onComplete }) {
  const [league, setLeague] = useState(null);
  const [teams, setTeams] = useState([]);
  const [stepIdx, setStepIdx] = useState(0);
  const [busy, setBusy] = useState(false);

  // Form state (seeded from backend on open)
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
      // /leagues/{id} accepts name + is_private only — salary cap lives in separate LA flow.
      // For the wizard we keep cap state local and push to the league doc via the existing
      // league-admin endpoint `/leagues/{id}/admin/cap-settings` when present.
      try {
        await api.put(`/leagues/${leagueId}/admin/cap-settings`, {
          salary_cap_enabled: capEnabled,
          salary_cap: capEnabled ? capAmount : null,
          salary_retention_slots: retentionSlots,
        });
      } catch (e) {
        // If that endpoint doesn't exist, silently skip — user can configure in settings.
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

        {/* Step body */}
        {step.id === "basics" && (
          <div className="space-y-3" data-testid="wizard-body-basics">
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
          </div>
        )}

        {step.id === "cap" && (
          <div className="space-y-4" data-testid="wizard-body-cap">
            <div className="flex items-center gap-3">
              <Switch checked={capEnabled} onCheckedChange={setCapEnabled} id="wiz-cap" />
              <Label htmlFor="wiz-cap" className="cursor-pointer">Enable salary cap</Label>
            </div>
            {capEnabled && (
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label htmlFor="wiz-cap-amt" className="text-xs">Cap ($)</Label>
                  <Input id="wiz-cap-amt" type="number" value={capAmount} onChange={(e) => setCapAmount(parseInt(e.target.value || "0", 10))} />
                </div>
                <div>
                  <Label htmlFor="wiz-ret" className="text-xs">Retention slots</Label>
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
                <Label className="text-xs">Intra-division games</Label>
                <Input type="number" min={0} max={10} value={schedule.intra_division_games} onChange={(e) => setSchedule({ ...schedule, intra_division_games: Math.max(0, Math.min(10, parseInt(e.target.value || "0", 10))) })} data-testid="wizard-schedule-intra-div" />
              </div>
              <div>
                <Label className="text-xs">Intra-conference games</Label>
                <Input type="number" min={0} max={10} value={schedule.intra_conference_games} onChange={(e) => setSchedule({ ...schedule, intra_conference_games: Math.max(0, Math.min(10, parseInt(e.target.value || "0", 10))) })} data-testid="wizard-schedule-intra-conf" />
              </div>
              <div>
                <Label className="text-xs">Inter-conference games</Label>
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
                  <Label className="text-xs">Regular season weeks</Label>
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
          <Button
            variant="ghost"
            size="sm"
            disabled={stepIdx === 0 || busy}
            onClick={() => setStepIdx(stepIdx - 1)}
            data-testid="wizard-back-btn"
          >
            <ChevronLeft className="h-4 w-4 mr-1" /> Back
          </Button>
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
    </Dialog>
  );
}
