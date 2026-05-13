// @ts-nocheck
import { useEffect, useMemo, useState } from "react";
import api from "@/lib/api";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Checkbox } from "@/components/ui/checkbox";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";
import {
  Check, ChevronLeft, ChevronRight, Wand2, Trophy, DollarSign, Network, Calendar,
  Rocket, SkipForward, ArrowRightLeft, Plus, X, AlertTriangle,
} from "lucide-react";
import HelpTooltip from "@/components/ui/help-tooltip";
import SmartNumberInput from "@/components/ui/smart-number-input";
import PremiumTrialBanner from "@/lovable/components/PremiumTrialBanner";
import CBABadge from "@/lovable/components/CBABadge";
import VetoThresholdPreview from "@/lovable/components/VetoThresholdPreview";

const STEPS = [
  { id: "basics", label: "Basics", icon: Wand2 },
  { id: "cap", label: "Salary Cap", icon: DollarSign },
  { id: "divisions", label: "League Structure", icon: Network },
  { id: "schedule", label: "Schedule", icon: Calendar },
  { id: "trades", label: "Trades", icon: ArrowRightLeft },
  { id: "generate", label: "Generate", icon: Rocket },
];

const HELP = {
  rosterSpots: "Total number of active players each team carries on its NHL roster. Skaters + goalies that score points each week.",
  benchSpots: "Inactive players that don't score this week but stay on the roster — typically for matchup planning or injury cover.",
  minors: "A separate prospects pool used by Dynasty leagues. Players here don't count against your active roster or salary cap. Available when 'Minors' premium feature is enabled.",
  capEnable: "Imposes a maximum total contract value across all rostered players. Required for realistic Dynasty cap management. Premium feature.",
  capAmount: "Maximum aggregate salary across all rostered players. NHL real-world cap for 2025-26 is $82.5M. Hold ▲/▼ to step by $100k → $500k → $1M.",
  retentionEnable: "Allow trade partners to keep paying part of a traded player's salary. Off by default.",
  retentionSlots: "Each 'slot' lets a team retain 1 contract at any time. NHL CBA allows 3.",
  retentionMaxPct: "Maximum portion of a player's salary a team can retain when trading them away. NHL CBA caps this at 50%.",
  divisions: "Group teams into divisions and conferences (e.g. NHL has 4 divisions in 2 conferences). Required for division-aware scheduling, playoff seeding, and President's Trophy calculation.",
  intraDiv: "Games against teams in your OWN division (default 2 — home-and-home with each rival).",
  intraConf: "Games against teams in your OWN conference but DIFFERENT division (default 1).",
  interConf: "Games against teams in the OTHER conference (default 1).",
  weeks: "Regular season length (recommended 18-22). Playoffs are scheduled separately and don't count toward this number.",
  seasonStart: "Real-world calendar date when week 1 begins. Used by the schedule generator to map weeks → calendar dates.",
  seasonEnd: "Real-world calendar date the regular season ends. Optional — the generator derives this from weeks × matchup length when omitted.",
  matchupLen: "Days per matchup period. Most fantasy hockey leagues use 7 (weekly H2H); some use 14 for bi-weekly.",
  oppPerPeriod: "Teams a single fantasy team plays per matchup period. Set to 2+ for multi-opponent (e.g. roto-with-H2H).",
  playoffStart: "Week your playoffs begin (e.g. week 19 of a 23-week season → 5 playoff weeks).",
  playoffEnd: "Final week of the playoffs. Defaults to season end if blank.",
  consolation: "Side bracket for teams that miss the main playoffs — fight for draft lottery boost or compensation pick.",
  consolationAlong: "Run the consolation bracket on the same weeks as the main playoffs (single shared calendar window).",
  tradeReview: "Hours a trade waits before auto-executing. 0 = instant. Standard leagues use 24-72h.",
  tradeVeto: "% of league that must vote VETO for a trade to be blocked. 0 = vetoes disabled.",
  tradeDeadline: "After this week, new proposals are blocked. Typical NHL leagues set this 3-4 weeks before playoffs.",
  skip: "Skip the wizard and configure each setting later from Commissioner Settings. Setup-complete flag still gets recorded so this dialog won't open again automatically.",
  setUpLater: "Save what you have so far, mark setup as 'in progress', and finish later. The wizard will re-open next time you visit Commissioner Settings.",
};

// ─── Helpers ─────────────────────────────────────────────────
const fmtMoney = (n) => `${(Number(n) || 0).toLocaleString()}`;

export default function SetupWizard({ open, onClose, leagueId, onComplete }) {
  const [league, setLeague] = useState(null);
  const [teams, setTeams] = useState([]);
  const [stepIdx, setStepIdx] = useState(0);
  const [busy, setBusy] = useState(false);
  const [skipConfirmOpen, setSkipConfirmOpen] = useState(false);
  const [scheduleMode, setScheduleMode] = useState(null);
  const [previousSeasonSuggestion, setPreviousSeasonSuggestion] = useState(null);

  // Basics
  const [rosterSpots, setRosterSpots] = useState(20);
  const [benchSpots, setBenchSpots] = useState(5);
  const [minorsSpots, setMinorsSpots] = useState(5);
  const [minorsEnabled, setMinorsEnabled] = useState(false);

  // Salary cap + retention
  const [capEnabled, setCapEnabled] = useState(false);
  const [capAmount, setCapAmount] = useState(82500000);
  const [retentionEnabled, setRetentionEnabled] = useState(false);
  const [retentionSlots, setRetentionSlots] = useState(3);
  const [retentionMaxPct, setRetentionMaxPct] = useState(50);

  // Divisions
  const [divisionList, setDivisionList] = useState([]); // ["Atlantic", "Metropolitan", ...]
  const [conferenceList, setConferenceList] = useState([]); // ["Eastern", "Western"]
  const [newDivisionName, setNewDivisionName] = useState("");
  const [newConferenceName, setNewConferenceName] = useState("");
  const [divisionAssignments, setDivisionAssignments] = useState({}); // teamId → {division, conference}

  // Schedule
  const [schedule, setSchedule] = useState({ intra_division_games: 2, intra_conference_games: 1, inter_conference_games: 1 });
  const [seasonStart, setSeasonStart] = useState("");
  const [seasonEnd, setSeasonEnd] = useState("");
  const [matchupLength, setMatchupLength] = useState(7);
  const [opponentsPerPeriod, setOpponentsPerPeriod] = useState(1);
  const [playoffStartWeek, setPlayoffStartWeek] = useState(19);
  const [playoffEndWeek, setPlayoffEndWeek] = useState(21);
  const [numWeeks, setNumWeeks] = useState(18);
  const [consolationEnabled, setConsolationEnabled] = useState(false);
  const [consolationAlongPlayoffs, setConsolationAlongPlayoffs] = useState(true);
  const [consolationStartWeek, setConsolationStartWeek] = useState(19);
  const [consolationEndWeek, setConsolationEndWeek] = useState(21);

  // Trades
  const [tradeReviewHours, setTradeReviewHours] = useState(72);
  const [tradeVetoPct, setTradeVetoPct] = useState(50);
  const [tradeDeadlineWeek, setTradeDeadlineWeek] = useState(16);

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
        const capCfg = sug?.salary_cap_config;
        setCapEnabled(capCfg ? !!capCfg.enabled : !!lgR.data?.salary_cap_enabled);
        setCapAmount(capCfg?.amount || lgR.data?.salary_cap || 82500000);
        setRetentionEnabled(lgR.data?.salary_retention_enabled ?? (lgR.data?.salary_retention_slots > 0));
        setRetentionSlots(capCfg?.retention_slots ?? lgR.data?.salary_retention_slots ?? 3);
        setRetentionMaxPct(lgR.data?.salary_retention_max_pct ?? 50);
        setMinorsEnabled(!!lgR.data?.minors_enabled);
        setRosterSpots(lgR.data?.roster_spots ?? 20);
        setBenchSpots(lgR.data?.bench_spots ?? 5);
        setMinorsSpots(lgR.data?.minors_spots ?? 5);
        setTeams(teamsR.data || []);
        // Trade defaults from league
        setTradeReviewHours(lgR.data?.trade_review_period_hours ?? 72);
        setTradeVetoPct(lgR.data?.trade_veto_threshold_pct ?? 50);
        setTradeDeadlineWeek(lgR.data?.trade_deadline_week ?? 16);
        // Schedule defaults
        setSeasonStart(lgR.data?.season_start_date ?? "");
        setSeasonEnd(lgR.data?.season_end_date ?? "");
        setMatchupLength(lgR.data?.matchup_length_days ?? 7);
        setOpponentsPerPeriod(lgR.data?.opponents_per_matchup_period ?? 1);
        setPlayoffStartWeek(lgR.data?.playoff_start_week ?? 19);
        setPlayoffEndWeek(lgR.data?.playoff_end_week ?? 21);
        setNumWeeks(lgR.data?.regular_season_weeks ?? 18);
        setConsolationEnabled(!!lgR.data?.consolation_enabled);
        setConsolationAlongPlayoffs(lgR.data?.consolation_uses_playoff_schedule ?? true);
        setConsolationStartWeek(lgR.data?.consolation_start_week ?? 19);
        setConsolationEndWeek(lgR.data?.consolation_end_week ?? 21);

        const seeded = {};
        const divs = new Set();
        const confs = new Set();
        (teamsR.data || []).forEach((t) => {
          seeded[t.id] = { division: t.division || "", conference: t.conference || "" };
          if (t.division) divs.add(t.division);
          if (t.conference) confs.add(t.conference);
        });
        setDivisionAssignments(seeded);
        setDivisionList(Array.from(divs));
        setConferenceList(Array.from(confs));
        const schCfg = sug?.schedule_config || cfgR?.data;
        if (schCfg) setSchedule({
          intra_division_games: schCfg.intra_division_games ?? 2,
          intra_conference_games: schCfg.intra_conference_games ?? 1,
          inter_conference_games: schCfg.inter_conference_games ?? 1,
        });
      } catch (e) {
        const msg = e?.response?.data?.detail || e?.message || "Failed to load league for setup wizard";
        toast.error(msg);
      }
    })();
    return () => { cancelled = true; };
  }, [open, leagueId]);

  const step = STEPS[stepIdx];
  const isLast = stepIdx === STEPS.length - 1;

  // ─── Division / conference helpers ───────────────────────────
  const addDivision = () => {
    const name = newDivisionName.trim();
    if (!name) return;
    if (divisionList.includes(name)) { toast.error(`Division "${name}" already exists`); return; }
    setDivisionList([...divisionList, name]);
    setNewDivisionName("");
  };
  const removeDivision = (name) => {
    setDivisionList(divisionList.filter((d) => d !== name));
    // Clear assignments referencing this division
    setDivisionAssignments((prev) => {
      const next = { ...prev };
      Object.keys(next).forEach((tid) => {
        if (next[tid]?.division === name) next[tid] = { ...next[tid], division: "" };
      });
      return next;
    });
  };
  const addConference = () => {
    const name = newConferenceName.trim();
    if (!name) return;
    if (conferenceList.includes(name)) { toast.error(`Conference "${name}" already exists`); return; }
    setConferenceList([...conferenceList, name]);
    setNewConferenceName("");
  };
  const removeConference = (name) => {
    setConferenceList(conferenceList.filter((c) => c !== name));
    setDivisionAssignments((prev) => {
      const next = { ...prev };
      Object.keys(next).forEach((tid) => {
        if (next[tid]?.conference === name) next[tid] = { ...next[tid], conference: "" };
      });
      return next;
    });
  };

  const autoAssignNHL = () => {
    const divs = ["Atlantic", "Metropolitan", "Central", "Pacific"];
    const confs = ["Eastern", "Western"];
    const confOf = (d) => (d === "Atlantic" || d === "Metropolitan") ? "Eastern" : "Western";
    setDivisionList(divs);
    setConferenceList(confs);
    const next = {};
    teams.forEach((t, idx) => {
      const div = divs[idx % 4];
      next[t.id] = { division: div, conference: confOf(div) };
    });
    setDivisionAssignments(next);
    toast.info("Auto-assigned 4 divisions / 2 conferences");
  };

  // ─── Save helpers ─────────────────────────────────────────────
  const saveBasicsAndCap = async () => {
    setBusy(true);
    try {
      try {
        await api.put(`/leagues/${leagueId}/admin/cap-settings`, {
          salary_cap_enabled: capEnabled,
          salary_cap: capEnabled ? capAmount : null,
          salary_retention_slots: retentionEnabled ? retentionSlots : 0,
          minors_enabled: minorsEnabled,
        });
      } catch (e) { /* silent */ }
      await api.put(`/leagues/${leagueId}`, {
        roster_spots: rosterSpots,
        bench_spots: benchSpots,
        minors_spots: minorsEnabled ? minorsSpots : 0,
        salary_retention_enabled: retentionEnabled,
        salary_retention_max_pct: retentionMaxPct,
        salary_retention_slots: retentionEnabled ? retentionSlots : 0,
      });
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to save basics");
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
      // Schedule mix → dedicated endpoint
      await api.put(`/leagues/${leagueId}/schedule-config`, schedule).catch(() => {});
      // Calendar + matchup-period + playoff config → main league doc
      await api.put(`/leagues/${leagueId}`, {
        season_start_date: seasonStart || null,
        season_end_date: seasonEnd || null,
        matchup_length_days: matchupLength,
        opponents_per_matchup_period: opponentsPerPeriod,
        regular_season_weeks: numWeeks,
        playoff_start_week: playoffStartWeek,
        playoff_end_week: playoffEndWeek,
        consolation_enabled: consolationEnabled,
        consolation_uses_playoff_schedule: consolationAlongPlayoffs,
        consolation_start_week: consolationEnabled
          ? (consolationAlongPlayoffs ? playoffStartWeek : consolationStartWeek)
          : null,
        consolation_end_week: consolationEnabled
          ? (consolationAlongPlayoffs ? playoffEndWeek : consolationEndWeek)
          : null,
      });
      toast.success("Schedule saved");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to save schedule");
    } finally {
      setBusy(false);
    }
  };

  const saveTrades = async () => {
    setBusy(true);
    try {
      await api.put(`/leagues/${leagueId}`, {
        trade_review_period_hours: tradeReviewHours,
        trade_veto_threshold_pct: tradeVetoPct,
        trade_deadline_week: tradeDeadlineWeek,
      });
      toast.success("Trade settings saved");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to save trade settings");
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
      const reason = e?.response?.data?.detail;
      const status = e?.response?.status;
      let prefix = "Failed to generate schedule";
      if (status === 403) prefix = "Can't generate schedule";
      else if (status === 400) prefix = "Couldn't generate schedule";
      toast.error(`${prefix}${reason ? ` — ${reason}` : ""}`, { duration: 8000 });
    } finally {
      setBusy(false);
    }
  };

  const finish = async () => {
    setBusy(true);
    try {
      // Pre-flight check so we can surface a precise reason
      try {
        const pre = await api.post(`/leagues/${leagueId}/validate-setup`);
        const issues = pre?.data?.issues || [];
        if (!pre?.data?.ok && issues.length > 0) {
          toast.error(`Can't finish setup yet: ${issues.join(" · ")}`, { duration: 10000 });
          return;
        }
      } catch (e) { /* tolerate older backends */ }
      await api.post(`/leagues/${leagueId}/setup-complete`);
      toast.success("Setup complete! Your league is ready.");
      onComplete && onComplete();
      onClose();
    } catch (e) {
      const reason = e?.response?.data?.detail || e?.message;
      toast.error(`Failed to mark setup complete${reason ? ` — ${reason}` : ""}`, { duration: 10000 });
    } finally {
      setBusy(false);
    }
  };

  const skipWizard = async () => {
    setBusy(true);
    try {
      await api.post(`/leagues/${leagueId}/setup-complete`).catch(() => {});
      toast.info("Setup skipped — you can configure each step later from Commissioner Settings.");
      onComplete && onComplete();
      onClose();
    } finally {
      setBusy(false);
      setSkipConfirmOpen(false);
    }
  };

  const setUpLater = async () => {
    // Save the current step's values but DON'T mark setup complete — so the
    // wizard re-opens automatically next time. Different from "Skip" which
    // marks the league as set up.
    if (step.id === "basics" || step.id === "cap") await saveBasicsAndCap();
    else if (step.id === "divisions") await saveDivisions();
    else if (step.id === "schedule") await saveSchedule();
    else if (step.id === "trades") await saveTrades();
    toast.info("Saved your progress — finish setup whenever you're ready.");
    onClose();
  };

  const next = async () => {
    if (step.id === "basics") await saveBasicsAndCap();
    else if (step.id === "cap") await saveBasicsAndCap();
    else if (step.id === "divisions") await saveDivisions();
    else if (step.id === "schedule") await saveSchedule();
    else if (step.id === "trades") await saveTrades();
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
            Walk through {STEPS.length} quick steps: basics, salary cap, league structure, schedule, trades, and regular-season generation.
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

        {(capEnabled || minorsEnabled) && (
          <PremiumTrialBanner leagueId={leagueId} isCommissioner />
        )}

        {/* ─── Basics ─────────────────────────────────────────── */}
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
                    <Input id="wiz-minors" type="number" min={0} max={20} value={minorsSpots}
                      onChange={(e) => setMinorsSpots(Math.max(0, Math.min(20, parseInt(e.target.value || "0", 10))))}
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
        )}

        {/* ─── Salary Cap + Retention A/B ─────────────────────── */}
        {step.id === "cap" && (
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
                      type="number"
                      min={1}
                      max={10}
                      value={retentionSlots}
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
                        type="number"
                        min={1}
                        max={100}
                        value={retentionMaxPct}
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
        )}

        {/* ─── League Structure ───────────────────────────────── */}
        {step.id === "divisions" && (
          <div className="space-y-3" data-testid="wizard-body-divisions">
            <div className="flex items-center gap-2 flex-wrap">
              <h3 className="text-sm font-semibold text-white flex items-center">
                League Structure
                <HelpTooltip text={HELP.divisions} testId="help-divisions" />
              </h3>
              <Button size="sm" variant="outline" onClick={autoAssignNHL} data-testid="wizard-auto-assign-nhl">
                Auto-assign NHL style
              </Button>
            </div>

            {/* Step A: Create divisions + conferences */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="space-y-2 border border-border rounded p-3" data-testid="wizard-division-list">
                <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Divisions ({divisionList.length})</h4>
                <div className="flex gap-2">
                  <Input
                    placeholder="e.g. Atlantic"
                    value={newDivisionName}
                    onChange={(e) => setNewDivisionName(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && addDivision()}
                    className="h-8 text-xs"
                    data-testid="wizard-new-division-input"
                  />
                  <Button size="sm" variant="outline" onClick={addDivision} data-testid="wizard-add-division-btn">
                    <Plus className="h-3.5 w-3.5" />
                  </Button>
                </div>
                <div className="flex flex-wrap gap-1.5 min-h-[28px]">
                  {divisionList.map((d) => (
                    <Badge key={d} variant="secondary" className="gap-1 pl-2 pr-1" data-testid={`wizard-division-chip-${d}`}>
                      {d}
                      <button onClick={() => removeDivision(d)} className="hover:text-destructive" aria-label={`Remove ${d}`}>
                        <X className="h-3 w-3" />
                      </button>
                    </Badge>
                  ))}
                  {divisionList.length === 0 && <span className="text-xs text-muted-foreground italic">No divisions yet</span>}
                </div>
              </div>

              <div className="space-y-2 border border-border rounded p-3" data-testid="wizard-conference-list">
                <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Conferences ({conferenceList.length})</h4>
                <div className="flex gap-2">
                  <Input
                    placeholder="e.g. Eastern"
                    value={newConferenceName}
                    onChange={(e) => setNewConferenceName(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && addConference()}
                    className="h-8 text-xs"
                    data-testid="wizard-new-conference-input"
                  />
                  <Button size="sm" variant="outline" onClick={addConference} data-testid="wizard-add-conference-btn">
                    <Plus className="h-3.5 w-3.5" />
                  </Button>
                </div>
                <div className="flex flex-wrap gap-1.5 min-h-[28px]">
                  {conferenceList.map((c) => (
                    <Badge key={c} variant="secondary" className="gap-1 pl-2 pr-1" data-testid={`wizard-conference-chip-${c}`}>
                      {c}
                      <button onClick={() => removeConference(c)} className="hover:text-destructive" aria-label={`Remove ${c}`}>
                        <X className="h-3 w-3" />
                      </button>
                    </Badge>
                  ))}
                  {conferenceList.length === 0 && <span className="text-xs text-muted-foreground italic">No conferences yet</span>}
                </div>
              </div>
            </div>

            {/* Step B: Assign each team via dropdown */}
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
                        <Select
                          value={divisionAssignments[t.id]?.division || ""}
                          onValueChange={(v) => setDivisionAssignments((prev) => ({
                            ...prev,
                            [t.id]: { ...(prev[t.id] || {}), division: v === "__none__" ? "" : v },
                          }))}
                        >
                          <SelectTrigger className="h-7 text-xs" data-testid={`wizard-team-division-${t.id}`}>
                            <SelectValue placeholder="—" />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="__none__">—</SelectItem>
                            {divisionList.map((d) => <SelectItem key={d} value={d}>{d}</SelectItem>)}
                          </SelectContent>
                        </Select>
                      </td>
                      <td className="py-1.5 pr-3">
                        <Select
                          value={divisionAssignments[t.id]?.conference || ""}
                          onValueChange={(v) => setDivisionAssignments((prev) => ({
                            ...prev,
                            [t.id]: { ...(prev[t.id] || {}), conference: v === "__none__" ? "" : v },
                          }))}
                        >
                          <SelectTrigger className="h-7 text-xs" data-testid={`wizard-team-conference-${t.id}`}>
                            <SelectValue placeholder="—" />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="__none__">—</SelectItem>
                            {conferenceList.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}
                          </SelectContent>
                        </Select>
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

        {/* ─── Schedule ────────────────────────────────────── */}
        {step.id === "schedule" && (
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
                <Input
                  id="wiz-season-start"
                  type="date"
                  value={seasonStart}
                  onChange={(e) => setSeasonStart(e.target.value)}
                  data-testid="wizard-season-start"
                />
              </div>
              <div>
                <Label className="text-xs flex items-center" htmlFor="wiz-season-end">
                  Season end date
                  <HelpTooltip text={HELP.seasonEnd} testId="help-season-end" />
                </Label>
                <Input
                  id="wiz-season-end"
                  type="date"
                  value={seasonEnd}
                  onChange={(e) => setSeasonEnd(e.target.value)}
                  data-testid="wizard-season-end"
                />
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
        )}

        {/* ─── Trades ──────────────────────────────────────── */}
        {step.id === "trades" && (
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
                  Veto threshold (%)
                  <HelpTooltip text={HELP.tradeVeto} testId="help-trade-veto" />
                </Label>
                <Input type="number" min={0} max={100}
                  value={tradeVetoPct}
                  onChange={(e) => setTradeVetoPct(Math.max(0, Math.min(100, parseInt(e.target.value || "0", 10))))}
                  data-testid="wizard-trade-veto-pct" />
                <div className="mt-2">
                  <VetoThresholdPreview
                    leagueId={leagueId}
                    pct={tradeVetoPct}
                    testId="wizard-veto-threshold-preview"
                  />
                </div>
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
              </div>
            </div>
          </div>
        )}

        {/* ─── Generate ────────────────────────────────────── */}
        {step.id === "generate" && (
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
                <p className="text-xs text-success">✓ Schedule generated ({scheduleMode}). Click Finish to complete setup.</p>
              )}
            </div>
          </div>
        )}

        {/* Nav buttons */}
        <div className="flex justify-between items-center pt-2 border-t border-border flex-wrap gap-2">
          <div className="flex items-center gap-2 flex-wrap">
            <Button variant="ghost" size="sm" disabled={stepIdx === 0 || busy}
              onClick={() => setStepIdx(stepIdx - 1)} data-testid="wizard-back-btn">
              <ChevronLeft className="h-4 w-4 mr-1" /> Back
            </Button>
            <Button variant="ghost" size="sm" onClick={setUpLater} disabled={busy}
              className="text-muted-foreground hover:text-foreground"
              data-testid="wizard-setup-later-btn"
              title="Save and finish later">
              Set Up Later
              <HelpTooltip text={HELP.setUpLater} testId="help-set-up-later" />
            </Button>
            <Button variant="ghost" size="sm" onClick={() => setSkipConfirmOpen(true)} disabled={busy}
              className="text-muted-foreground hover:text-foreground"
              data-testid="wizard-skip-btn" title="Skip setup wizard">
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

      <AlertDialog open={skipConfirmOpen} onOpenChange={setSkipConfirmOpen}>
        <AlertDialogContent data-testid="wizard-skip-confirm">
          <AlertDialogHeader>
            <AlertDialogTitle>Skip the setup wizard?</AlertDialogTitle>
            <AlertDialogDescription>
              Your league will be marked as set up, but none of the unsaved choices on this screen will be persisted.
              You can configure everything later from <strong>Commissioner Settings</strong>.
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
