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
import BasicsStep from "./wizard/BasicsStep";
import CapStep from "./wizard/CapStep";
import DivisionsStep from "./wizard/DivisionsStep";
import ScheduleStep from "./wizard/ScheduleStep";
import TradesStep from "./wizard/TradesStep";
import GenerateStep from "./wizard/GenerateStep";

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
    capEnabled, setCapEnabled,
    capAmount, setCapAmount,
    retentionEnabled, setRetentionEnabled,
    retentionSlots, setRetentionSlots,
    retentionMaxPct, setRetentionMaxPct,
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
    tradeReviewHours, setTradeReviewHours,
    tradeVetoCount, setTradeVetoCount,
    tradeDeadlineWeek, setTradeDeadlineWeek,
    tradeDeadlineDow, setTradeDeadlineDow,
    tradeDeadlineTime, setTradeDeadlineTime,
    busy,
    generateSchedule,
    scheduleMode,
    scheduleWarnings,
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
        {step.id === "basics" && <BasicsStep ctx={stepCtx} />}

        {/* ─── Salary Cap + Retention A/B ─────────────────────── */}
        {step.id === "cap" && <CapStep ctx={stepCtx} />}

        {/* ─── League Structure ───────────────────────────────── */}
        {step.id === "divisions" && <DivisionsStep ctx={stepCtx} />}

        {/* ─── Schedule ────────────────────────────────────── */}
        {step.id === "schedule" && <ScheduleStep ctx={stepCtx} />}

        {/* ─── Trades ──────────────────────────────────────── */}
        {step.id === "trades" && <TradesStep ctx={stepCtx} />}

        {/* ─── Generate ────────────────────────────────────── */}
        {step.id === "generate" && <GenerateStep ctx={stepCtx} />}

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
