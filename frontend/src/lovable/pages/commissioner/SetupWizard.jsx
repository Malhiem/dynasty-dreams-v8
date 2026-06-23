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
import { ClockPicker } from "@/components/ui/clock-picker";
import VetoThresholdPreview from "@/lovable/components/VetoThresholdPreview";
// Iter 228 — Extracted step components
import DivisionsStep from "./wizard/DivisionsStep";
import ScheduleStep from "./wizard/ScheduleStep";

// Iter 225 — Robust extractor for the assorted `detail` shapes the
// backend returns (string, Pydantic-422 list, or our custom
// `{code, message, missing|errors}` objects). Always yields a string so
// `toast.error(...)` never receives a raw object (which would crash React).
function formatErrDetail(detail, fallback = "Something went wrong") {
  if (!detail) return fallback;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail.map((d) => d?.msg || d?.message || String(d)).join(" · ") || fallback;
  }
  if (typeof detail === "object") {
    const base = detail.message || detail.detail || fallback;
    const errs = detail.errors;
    if (Array.isArray(errs) && errs.length) return `${base} — ${errs.join(" · ")}`;
    return base;
  }
  return String(detail);
}

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
  // Iter 225 — Editable team slots so the commissioner can size the league
  // before invitees join. Pads the generated schedule with placeholder slots.
  const [maxTeams, setMaxTeams] = useState(12);
  // Iter 226 — Editable Basics fields. The Teams stat becomes an editable
  // max_teams input, format & scoring become inline selects.
  const [leagueFormat, setLeagueFormat] = useState("dynasty");
  const [scoringFormat, setScoringFormat] = useState("head_to_head");

  // Iter 226 — Title-case label helpers shared by the wizard and the
  // backend persistence (which still stores enum-style lowercase ids).
  const FORMAT_LABELS = { dynasty: "Dynasty", keeper: "Keeper", redraft: "Redraft" };
  const SCORING_LABELS = { head_to_head: "Head to Head", roto: "Roto", points: "Points" };

  // Salary cap + retention
  const [capEnabled, setCapEnabled] = useState(false);
  // Iter 226 — Default cap to $100M (closer to what commissioners actually set).
  const [capAmount, setCapAmount] = useState(100_000_000);
  const [retentionEnabled, setRetentionEnabled] = useState(false);
  const [retentionSlots, setRetentionSlots] = useState(3);
  const [retentionMaxPct, setRetentionMaxPct] = useState(50);

  // Divisions
  const [divisionList, setDivisionList] = useState([]); // ["Atlantic", "Metropolitan", ...]
  const [conferenceList, setConferenceList] = useState([]); // ["Eastern", "Western"]
  const [newDivisionName, setNewDivisionName] = useState("");
  const [newConferenceName, setNewConferenceName] = useState("");
  const [divisionAssignments, setDivisionAssignments] = useState({}); // teamId → {division, conference}
  // Iter 226 — Mandatory division → conference mapping. Each division must
  // be assigned to exactly ONE conference. Teams inherit their conference
  // automatically from the division mapping at save time.
  const [divisionToConference, setDivisionToConference] = useState({}); // divisionName → conferenceName

  // Schedule
  const [schedule, setSchedule] = useState({ intra_division_games: 2, intra_conference_games: 1, inter_conference_games: 1 });
  const [seasonStart, setSeasonStart] = useState("");
  const [seasonEnd, setSeasonEnd] = useState("");
  const [matchupLength, setMatchupLength] = useState(7);
  // Iter 226 — Per-week matchup-length overrides. Each row:
  //   { week_num: int, length_days: int, label?: string }
  // Schedule generator widens the named week without shifting later weeks.
  const [weekOverrides, setWeekOverrides] = useState([]);
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
  // Iter 225 — Veto by COUNT (was %). UI shows "N of M teams". State stores
  // the absolute number; we still POST the legacy `trade_veto_threshold_pct`
  // computed on save.
  const [tradeVetoCount, setTradeVetoCount] = useState(6);
  const [tradeDeadlineWeek, setTradeDeadlineWeek] = useState(16);
  // Iter 225 — Optional day-of-week (0=Sunday … 6=Saturday) + time-of-day
  // (HH:MM in 24h) that bind the trade deadline to a precise moment instead
  // of "anytime during week N". Backend assembles `trade_deadline_at`.
  const [tradeDeadlineDow, setTradeDeadlineDow] = useState(5); // Friday
  const [tradeDeadlineTime, setTradeDeadlineTime] = useState("15:00");

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
        setCapAmount(capCfg?.amount || lgR.data?.salary_cap || 100_000_000);
        setRetentionEnabled(lgR.data?.salary_retention_enabled ?? (lgR.data?.salary_retention_slots > 0));
        setRetentionSlots(capCfg?.retention_slots ?? lgR.data?.salary_retention_slots ?? 3);
        setRetentionMaxPct(lgR.data?.salary_retention_max_pct ?? 50);
        setMinorsEnabled(!!lgR.data?.minors_enabled);
        setRosterSpots(lgR.data?.roster_spots ?? 20);
        setBenchSpots(lgR.data?.bench_spots ?? 5);
        setMinorsSpots(lgR.data?.minors_spots ?? 5);
        setMaxTeams(lgR.data?.max_teams ?? 12);
        setLeagueFormat(lgR.data?.format || "dynasty");
        setScoringFormat(lgR.data?.scoring_format || "head_to_head");
        setTeams(teamsR.data || []);
        // Trade defaults from league
        setTradeReviewHours(lgR.data?.trade_review_period_hours ?? 72);
        const teamsForVeto = (teamsR.data || []).length || lgR.data?.max_teams || 12;
        const storedPct = lgR.data?.trade_veto_threshold_pct ?? 50;
        setTradeVetoCount(Math.max(1, Math.round((storedPct / 100) * teamsForVeto)));
        setTradeDeadlineWeek(lgR.data?.trade_deadline_week ?? 16);
        // Iter 225 — Reverse-parse `trade_deadline_at` (ISO) into dow + time
        // so the wizard re-opens with the previously-saved precise moment.
        const tdAt = lgR.data?.trade_deadline_at;
        if (tdAt) {
          try {
            const d = new Date(tdAt);
            setTradeDeadlineDow(d.getDay());
            setTradeDeadlineTime(d.toTimeString().slice(0, 5));
          } catch (_e) { /* ignore parse errors */ }
        }
        // Schedule defaults
        setSeasonStart(lgR.data?.season_start_date ?? "");
        setSeasonEnd(lgR.data?.season_end_date ?? "");
        setMatchupLength(lgR.data?.matchup_length_days ?? 7);
        setWeekOverrides(Array.isArray(lgR.data?.week_overrides) ? lgR.data.week_overrides : []);
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
        const divToConf = {};
        (teamsR.data || []).forEach((t) => {
          seeded[t.id] = { division: t.division || "", conference: t.conference || "" };
          if (t.division) divs.add(t.division);
          if (t.conference) confs.add(t.conference);
          // Reconstruct the division→conference map from existing team rows.
          if (t.division && t.conference && !divToConf[t.division]) {
            divToConf[t.division] = t.conference;
          }
        });
        setDivisionAssignments(seeded);
        setDivisionList(Array.from(divs));
        setConferenceList(Array.from(confs));
        setDivisionToConference(divToConf);
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
    setDivisionToConference((prev) => {
      const next = { ...prev };
      delete next[name];
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
    setDivisionToConference((prev) => {
      const next = { ...prev };
      Object.keys(next).forEach((d) => {
        if (next[d] === name) delete next[d];
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
    setDivisionToConference({
      Atlantic: "Eastern",
      Metropolitan: "Eastern",
      Central: "Western",
      Pacific: "Western",
    });
    const next = {};
    teams.forEach((t, idx) => {
      const div = divs[idx % 4];
      next[t.id] = { division: div, conference: confOf(div) };
    });
    setDivisionAssignments(next);
    toast.info("Auto-assigned 4 divisions / 2 conferences");
  };

  // ─── Save helpers ─────────────────────────────────────────────
  // Iter 199 — Stamp the league's setup_progress[<key>] = true after a
  // wizard step's save succeeds. Sections start at 0 for new leagues so
  // the Health Score increments naturally as the commissioner walks
  // through the wizard.
  // Iter 200 — also refresh the floating Health chip so the score bumps
  // visibly after every save.
  const [health, setHealth] = useState({ score: 0, sections: [], _bump: 0 });
  const refreshHealth = async () => {
    try {
      const { data } = await api.get(`/leagues/${leagueId}/health-score`);
      setHealth((prev) => ({
        score: data?.score ?? 0,
        sections: data?.sections || [],
        // bump on every refresh so the chip can flash even when the score
        // didn't change (re-saving an already-complete step still feels
        // like progress to the user).
        _bump: prev._bump + 1,
      }));
    } catch (_e) { /* best-effort */ }
  };
  // Hydrate on open / league change.
  useEffect(() => {
    if (open && leagueId) refreshHealth();
  }, [open, leagueId]);

  const stampProgress = async (sections) => {
    try {
      await api.post(`/leagues/${leagueId}/setup-progress`, { sections });
      await refreshHealth();
    } catch (_e) { /* best-effort */ }
  };

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
        max_teams: maxTeams,
        format: leagueFormat,
        scoring_format: scoringFormat,
        salary_retention_enabled: retentionEnabled,
        salary_retention_max_pct: retentionMaxPct,
        salary_retention_slots: retentionEnabled ? retentionSlots : 0,
      });
      // Iter 199 — both Basics + Cap finish on this single save.
      await stampProgress(["basics", "cap"]);
    } catch (e) {
      toast.error(formatErrDetail(e?.response?.data?.detail, "Failed to save basics"));
    } finally {
      setBusy(false);
    }
  };

  const saveDivisions = async () => {
    setBusy(true);
    try {
      // Iter 226 — Validate division → conference mapping. Each division
      // listed must be mapped to exactly ONE conference (when conferences
      // are in use). Bail early with a precise toast.
      if (conferenceList.length > 0 && divisionList.length > 0) {
        const unmapped = divisionList.filter((d) => !divisionToConference[d]);
        if (unmapped.length) {
          toast.error(
            `Each division needs a conference. Unassigned: ${unmapped.join(", ")}`,
          );
          setBusy(false);
          return;
        }
      }
      const assignments = teams.map((t) => {
        const div = divisionAssignments[t.id]?.division || null;
        // Iter 226 — Conference is INHERITED from the division→conference
        // mapping so a team's conference is always consistent with its
        // division. Falls back to the per-team selection only when no
        // mapping exists (legacy data).
        const conf = div
          ? (divisionToConference[div] || divisionAssignments[t.id]?.conference || null)
          : (divisionAssignments[t.id]?.conference || null);
        return { team_id: t.id, division: div, conference: conf };
      });
      await api.put(`/leagues/${leagueId}/divisions`, { assignments });
      await stampProgress(["divisions"]);
      toast.success("Divisions saved");
    } catch (e) {
      toast.error(formatErrDetail(e?.response?.data?.detail, "Failed to save divisions"));
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
        // Iter 226 — Persist per-week overrides. Sanitize entries that
        // are missing required fields (so the backend never gets junk).
        week_overrides: (weekOverrides || [])
          .map((w) => ({
            week_num: Math.max(1, parseInt(w.week_num || 0, 10)),
            length_days: Math.max(1, Math.min(21, parseInt(w.length_days || 0, 10))),
            label: (w.label || "").slice(0, 40) || null,
          }))
          .filter((w) => w.week_num > 0 && w.length_days > 0),
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
      // Iter 199 — Schedule + Playoffs both completed on this single save.
      await stampProgress(["schedule", "playoffs"]);
      toast.success("Schedule saved");
    } catch (e) {
      toast.error(formatErrDetail(e?.response?.data?.detail, "Failed to save schedule"));
    } finally {
      setBusy(false);
    }
  };

  const saveTrades = async () => {
    setBusy(true);
    try {
      // Iter 225 — Convert veto-by-count → legacy % for the backend store.
      const denom = Math.max(1, teams.length || maxTeams || 12);
      const vetoPct = Math.max(0, Math.min(100, Math.round((tradeVetoCount / denom) * 100)));
      // Iter 225 — Build a precise trade_deadline_at from dow + time, anchored
      // to the upcoming N-th week of the season (caller will refine; here we
      // just persist the next occurrence of the configured day+time so the
      // commissioner sees something coherent).
      const now = new Date();
      const targetDow = Math.max(0, Math.min(6, tradeDeadlineDow));
      const [hh, mm] = (tradeDeadlineTime || "15:00").split(":").map((x) => parseInt(x, 10) || 0);
      const daysAhead = (targetDow - now.getDay() + 7) % 7 || 7;
      const target = new Date(now);
      target.setDate(now.getDate() + daysAhead + Math.max(0, (tradeDeadlineWeek - 1)) * 7);
      target.setHours(hh, mm, 0, 0);
      const tradeDeadlineAt = target.toISOString();

      await api.put(`/leagues/${leagueId}`, {
        trade_review_period_hours: tradeReviewHours,
        trade_veto_threshold_pct: vetoPct,
        trade_deadline_week: tradeDeadlineWeek,
        trade_deadline_at: tradeDeadlineAt,
      });
      await stampProgress(["trades"]);
      toast.success("Trade settings saved");
    } catch (e) {
      toast.error(formatErrDetail(e?.response?.data?.detail, "Failed to save trade settings"));
    } finally {
      setBusy(false);
    }
  };

  const [scheduleWarnings, setScheduleWarnings] = useState([]);

  const generateSchedule = async () => {
    setBusy(true);
    setScheduleWarnings([]);
    try {
      const res = await api.post("/matchups/generate-schedule", { league_id: leagueId, num_weeks: numWeeks });
      setScheduleMode(res.data?.mode);
      setScheduleWarnings(res.data?.warnings || []);
      // Iter 199 — Generating schedule satisfies the "schedule" health
      // section even if the user skipped the prior schedule-config save.
      await stampProgress(["schedule"]);
      const placeholders = res.data?.placeholder_team_slots || 0;
      const placeholderNote = placeholders > 0 ? ` · ${placeholders} placeholder slot${placeholders === 1 ? "" : "s"}` : "";
      toast.success(
        `Generated ${res.data?.weeks || numWeeks}-week schedule (${res.data?.mode || "round_robin"})${placeholderNote}`,
      );
    } catch (e) {
      const reason = e?.response?.data?.detail;
      const status = e?.response?.status;
      let prefix = "Failed to generate schedule";
      if (status === 403) prefix = "Can't generate schedule";
      else if (status === 400) prefix = "Couldn't generate schedule";
      // Iter 225 — Backend returns {message, errors:[]} for the calendar-fit
      // check. Surface the structured errors in the toast.
      let msg = "";
      if (reason && typeof reason === "object") {
        const errs = (reason.errors || []).join(" · ");
        msg = `${reason.message || prefix}${errs ? ` — ${errs}` : ""}`;
      } else {
        msg = `${prefix}${reason ? ` — ${reason}` : ""}`;
      }
      toast.error(msg, { duration: 10000 });
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

  // Iter 228 — Bundle state + helpers as `ctx` for extracted step components.
  const stepCtx = {
    HELP,
    teams,
    divisionList, conferenceList,
    newDivisionName, setNewDivisionName,
    newConferenceName, setNewConferenceName,
    divisionAssignments, setDivisionAssignments,
    divisionToConference, setDivisionToConference,
    addDivision, removeDivision,
    addConference, removeConference,
    autoAssignNHL,
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
  };

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
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm" data-testid="wizard-basics-editable-stats">
              <div className="stat-card p-3">
                <Label className="text-muted-foreground text-xs" htmlFor="wiz-stat-teams">Teams</Label>
                <Input
                  id="wiz-stat-teams"
                  type="number"
                  min={2}
                  max={32}
                  value={maxTeams}
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
        {step.id === "divisions" && <DivisionsStep ctx={stepCtx} />}

        {/* ─── Schedule ────────────────────────────────────── */}
        {step.id === "schedule" && <ScheduleStep ctx={stepCtx} />}

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
            </Button>
            <HelpTooltip text={HELP.setUpLater} testId="help-set-up-later" />
            <Button variant="ghost" size="sm" onClick={() => setSkipConfirmOpen(true)} disabled={busy}
              className="text-muted-foreground hover:text-foreground"
              data-testid="wizard-skip-btn" title="Skip setup wizard">
              <SkipForward className="h-4 w-4 mr-1" /> Skip
            </Button>
            <HelpTooltip text={HELP.skip} testId="help-skip" />
          </div>
          <div className="flex items-center gap-3" data-testid="wizard-footer-progress">
            <HealthChip
              score={health.score}
              done={health.sections.filter((s) => s.complete).length}
              total={health.sections.length || 6}
              bump={health._bump}
            />
            <div className="text-xs text-muted-foreground whitespace-nowrap">Step {stepIdx + 1} of {STEPS.length}</div>
          </div>
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

/* ────────────────────────────────────────────────────────────────
 * Iter 200 — HealthChip
 * Floating progress chip rendered in the wizard footer. Shows the
 * current `score%` + a `done of total` step counter. Bumps with a
 * brief scale + amber glow animation each time `bump` increments,
 * giving the commissioner a small "dopamine hit" after each save.
 * ──────────────────────────────────────────────────────────────── */
function HealthChip({ score = 0, done = 0, total = 6, bump = 0 }) {
  const [flash, setFlash] = useState(false);
  useEffect(() => {
    if (bump === 0) return;
    setFlash(true);
    const t = setTimeout(() => setFlash(false), 900);
    return () => clearTimeout(t);
  }, [bump]);

  // Color tier — red → amber → emerald as score climbs.
  const tier =
    score >= 80 ? "emerald" :
    score >= 50 ? "cyan" :
    score >= 25 ? "amber" : "rose";
  const palette = {
    emerald: { bg: "bg-emerald-500/15", border: "border-emerald-500/40", text: "text-emerald-300", dot: "bg-emerald-400" },
    cyan:    { bg: "bg-cyan-500/15",    border: "border-cyan-500/40",    text: "text-cyan-300",    dot: "bg-cyan-400" },
    amber:   { bg: "bg-amber-500/15",   border: "border-amber-500/40",   text: "text-amber-300",   dot: "bg-amber-400" },
    rose:    { bg: "bg-rose-500/15",    border: "border-rose-500/40",    text: "text-rose-300",    dot: "bg-rose-400" },
  }[tier];

  return (
    <div
      className={`inline-flex items-center gap-2 px-2.5 py-1 rounded-full border ${palette.bg} ${palette.border} ${palette.text} transition-transform duration-300 ${flash ? "scale-110 shadow-[0_0_20px_rgba(245,158,11,0.45)]" : "scale-100"}`}
      data-testid="wizard-health-chip"
      title="League setup progress"
    >
      <span className={`relative inline-flex h-2 w-2 rounded-full ${palette.dot}`}>
        {flash && (
          <span className={`absolute inline-flex h-full w-full rounded-full ${palette.dot} opacity-75 animate-ping`} />
        )}
      </span>
      <span className="text-[11px] font-semibold tracking-wide whitespace-nowrap">
        League Health: <span data-testid="wizard-health-score">{score}%</span>
        <span className="opacity-60 mx-1">·</span>
        <span data-testid="wizard-health-steps">{done} of {total}</span> steps
      </span>
    </div>
  );
}
