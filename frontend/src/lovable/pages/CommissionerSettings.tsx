// @ts-nocheck
import { AppLayout } from "@/components/layout/AppLayout";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Settings, Users, Trophy, Shield, Target, LayoutGrid, AlertTriangle, ClipboardCheck, ScrollText, UserCog, Sliders, DollarSign } from "lucide-react";
import { useState, useRef, useEffect, useCallback } from "react";
import { useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { useActiveLeague } from "@/hooks/use-active-league";
import api from "@/lib/api";
import DivisionsTab from "@/lovable/pages/commissioner/DivisionsTab";
import RulesScheduleTab, { RosterLockCard } from "@/lovable/pages/commissioner/RulesScheduleTab";
import {
  EmergencyRosterChangesCard,
  GoalieScoringCard,
} from "@/lovable/pages/commissioner/PlayoffsScheduleCards";

import RostersTab from "@/lovable/pages/commissioner/RostersTab";
import SetupWizard from "@/lovable/pages/commissioner/SetupWizard";
import AuditLogTab from "@/lovable/pages/commissioner/tabs/AuditLogTab";
import LeagueSetupTab from "@/lovable/pages/commissioner/tabs/LeagueSetupTab";
import {
  AlertDialog, AlertDialogContent, AlertDialogHeader,
  AlertDialogTitle, AlertDialogDescription, AlertDialogFooter,
  AlertDialogCancel, AlertDialogAction,
} from "@/components/ui/alert-dialog";
import DraftTab from "@/lovable/pages/commissioner/tabs/DraftTab";
import PlayerPoolTab from "@/lovable/pages/commissioner/tabs/PlayerPoolTab";
import ScoringTab from "@/lovable/pages/commissioner/tabs/ScoringTab";
import { TankMonitorTab, RosterMonitorTab } from "@/lovable/pages/commissioner/tabs/MonitorTabs";
import SalaryCapContractsTab from "@/lovable/pages/commissioner/tabs/SalaryCapContractsTab";
import LeagueAdminTab from "@/lovable/pages/commissioner/tabs/LeagueAdminTab";
import TransactionsConfigCards from "@/lovable/pages/commissioner/TransactionsConfigCards";
import LeagueHealthCard from "@/lovable/components/admin/LeagueHealthCard";

import {
  nhlTeams,
  scoringCategories,
  type ScoringCategory,
  type AuditLogEntry,
  generateMockAuditLog,
  TankMonitorTable,
  RosterMonitorTable,
} from "@/lovable/pages/commissioner/data/commissionerData";


// Iter 231an — Single source of truth for the Commissioner Settings
// tab strip. Used by both the desktop `TabsList` and the mobile
// `<Select>` dropdown so labels + icons + ordering stay in sync.
const COMMISSIONER_TABS = [
  { value: "league-setup", label: "League Setup", icon: Trophy },
  { value: "player-pool", label: "Player Pool", icon: Users },
  { value: "rosters", label: "Rosters", icon: Shield },
  { value: "divisions", label: "League Structure", icon: Trophy },
  { value: "rules-schedule", label: "Transactions", icon: Sliders },
  { value: "salary-cap-contracts", label: "Salary Cap & Contracts", icon: DollarSign },
  { value: "scoring", label: "Scoring", icon: Target },
  { value: "draft", label: "Draft", icon: LayoutGrid },
  { value: "tanking", label: "Tank Monitor", icon: AlertTriangle },
  { value: "roster-monitor", label: "Roster Monitor", icon: ClipboardCheck },
  { value: "admin", label: "League Administration", icon: UserCog },
  { value: "audit-log", label: "Audit Log", icon: ScrollText },
] as const;


const CommissionerSettings = () => {

  // Iter 231an — Controlled active tab so the mobile <Select> dropdown
  // can mirror clicks on the desktop tab strip (and vice-versa) and
  // `onJumpToTab` callbacks can navigate without a DOM-click hack.
  // Iter 232j — Also honour a `?tab=` query param so deep-links from
  // the legacy /commissioner top-level nav (or any external anchor)
  // can land users directly on the right tab. The list of valid tab
  // values is kept in sync with the TabsTrigger `value=` attrs below.
  const [searchParams] = useSearchParams();
  const VALID_TABS = new Set([
    "league-setup", "player-pool", "rosters", "divisions", "rules-schedule",
    "salary-cap-contracts", "scoring", "draft", "tanking", "roster-monitor",
    "prospects", "constitution", "audit",
  ]);
  const initialTab = (() => {
    const raw = searchParams.get("tab");
    if (raw && VALID_TABS.has(raw)) return raw;
    return "league-setup";
  })();
  const [activeTab, setActiveTab] = useState<string>(initialTab);
  // Iter 232j — Keep the URL query param in sync with the active tab
  // so a browser refresh / back-button on any tab preserves state.
  useEffect(() => {
    const raw = searchParams.get("tab");
    if (raw !== activeTab) {
      const next = new URLSearchParams(searchParams);
      next.set("tab", activeTab);
      // Replace so we don't spam history with a new entry per tab click.
      window.history.replaceState(
        window.history.state,
        "",
        `${window.location.pathname}?${next.toString()}`,
      );
    }
    // Note: intentionally omit `searchParams` from deps — we only
    // want to sync when `activeTab` changes (writes), not when the
    // URL updates below (which would create a redundant loop).
  }, [activeTab]);

  // ─── Scoring format — auto-save on selection ────────────────────
  // Maps legacy backend enum values to the granular UI format keys.
  const mapBackendToUi = useCallback((v: string | undefined): string => {
    const map: Record<string, string> = {
      head_to_head: "h2h-points",
      total_points: "points",
      rotisserie: "rotisserie",
      guillotine: "h2h-points",
      all_play: "h2h-points",
    };
    return map[v || ""] || v || "h2h-points";
  }, []);

  const [selectedTeams, setSelectedTeams] = useState<string[]>([]);
  const [scoringFormat, setScoringFormatLocal] = useState("h2h-points");
  const [savedScoringFormat, setSavedScoringFormat] = useState("h2h-points");
  const [savingScoringFormat, setSavingScoringFormat] = useState(false);
  const [scoringFormatError, setScoringFormatError] = useState(false);
  const isH2H = scoringFormat.startsWith("h2h");
  // Playoffs enabled toggle (auto-save like scoring format)
  const [playoffsEnabled, setPlayoffsEnabledLocal] = useState(true);
  const [savingPlayoffsEnabled, setSavingPlayoffsEnabled] = useState(false);
  // Iter 141 — controlled draft type so we can conditionally render the Keeper settings card
  const [draftType, setDraftType] = useState<string>("startup");
  // Iter 143 — first-time draft gating + persistence (effects defined below `activeLeague`)
  const [firstDraftCompleted, setFirstDraftCompleted] = useState<boolean>(false);
  const [customInjuries, setCustomInjuries] = useState<{ type: string; timeline: string; irEligible: boolean }[]>([]);
  const [newInjuryType, setNewInjuryType] = useState("Upper Body");
  const [newInjuryTimeline, setNewInjuryTimeline] = useState("Day-to-Day");
  const [scoringSettings, setScoringSettings] = useState<Record<string, { enabled: boolean; points: number }>>(
    Object.fromEntries(scoringCategories.map(cat => [cat.id, { enabled: cat.defaultPoints !== 0, points: cat.defaultPoints }]))
  );
  const [auditLog, setAuditLog] = useState<AuditLogEntry[]>(generateMockAuditLog());
  const [auditFilterCategory, setAuditFilterCategory] = useState<string>("all");
  const { league: activeLeague, leagueTeams, reloadLeague } = useActiveLeague();

  // Iter 143 — first-time draft gating + persistence (moved here so it
  // can reference `activeLeague` after its declaration)
  useEffect(() => {
    if (!activeLeague?.id) return;
    let cancelled = false;
    (async () => {
      try {
        const { data } = await api.get(`/leagues/${activeLeague.id}`);
        if (cancelled) return;
        if (data?.first_draft_completed) setFirstDraftCompleted(true);
        if (data?.next_draft_type) setDraftType(data.next_draft_type);
        else if (!data?.first_draft_completed) setDraftType("startup");
        else setDraftType("redraft");
      } catch {/* noop */}
    })();
    return () => { cancelled = true; };
  }, [activeLeague?.id]);
  const persistDraftType = (v: string) => {
    setDraftType(v);
    if (activeLeague?.id) {
      api.put(`/leagues/${activeLeague.id}/next-draft-type`, { draft_type: v })
        .catch((e) => toast.error(e?.response?.data?.detail || "Failed to save draft type"));
    }
  };

  // ─── Setup Wizard (manual trigger only) ─────────────────────────
  // Iter 232N.82 — Previously auto-opened when `setup_wizard_complete=false`,
  // which meant its full-screen Dialog overlay would block interaction
  // with every other tab (Divisions "Save Schedule Mix", Rosters, etc.)
  // on first visit. That broke e2e tests targeting those Save buttons
  // and also frustrated commissioners who wanted to configure one thing
  // without walking through the whole wizard. The header always shows
  // a prominent "Complete Setup" / "Re-run Setup Wizard" button so
  // there's no discovery cost — we just don't auto-open anymore.
  const [wizardOpen, setWizardOpen] = useState(false);
  const handleWizardClose = () => {
    setWizardOpen(false);
    if (activeLeague?.id) {
      sessionStorage.setItem(`dd-setup-wizard-dismissed-${activeLeague.id}`, "1");
    }
  };
  const reopenWizard = async () => {
    if (activeLeague?.id) {
      sessionStorage.removeItem(`dd-setup-wizard-dismissed-${activeLeague.id}`);
    }
    setWizardOpen(true);
  };

  // ─── Privacy toggle (League Setup) ──────────────────────────────
  const [isPrivate, setIsPrivate] = useState<boolean>(false);
  const [privacyLoading, setPrivacyLoading] = useState<boolean>(false);
  const [recalcing, setRecalcing] = useState<boolean>(false);

  // ─── Injury Reserve Compliance Options ──────────────────────────
  const [irComplianceMode, setIrComplianceModeState] = useState<string>("none");
  useEffect(() => {
    if ((activeLeague as any)?.injury_reserve_compliance_mode) {
      setIrComplianceModeState((activeLeague as any).injury_reserve_compliance_mode);
    }
  }, [activeLeague?.id]);
  const setIrComplianceMode = async (mode: string) => {
    if (!activeLeague?.id) return;
    setIrComplianceModeState(mode);
    try {
      await api.put(`/leagues/${activeLeague.id}/injury-reserve-compliance-mode`, { mode });
      toast.success("Injury Reserve compliance mode updated");
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Failed to save");
    }
  };

  useEffect(() => {
    setIsPrivate(!!activeLeague?.is_private);
  }, [activeLeague?.id, activeLeague?.is_private]);

  // ─── Hydrate scoring format from league data ───────────────────
  useEffect(() => {
    if (activeLeague?.scoring_format) {
      const mapped = mapBackendToUi(activeLeague.scoring_format);
      setScoringFormatLocal(mapped);
      setSavedScoringFormat(mapped);
      setScoringFormatError(false);
    }
  }, [activeLeague?.id, activeLeague?.scoring_format, mapBackendToUi]);

  // ─── Hydrate playoffs enabled from league data ─────────────────
  useEffect(() => {
    if (activeLeague?.id != null) {
      setPlayoffsEnabledLocal(activeLeague.playoffs_enabled !== false);
    }
  }, [activeLeague?.id, activeLeague?.playoffs_enabled]);

  // ─── Playoffs enabled auto-save handler ────────────────────────
  const handlePlayoffsEnabledChange = async (enabled: boolean) => {
    if (!activeLeague?.id) return;
    const prev = playoffsEnabled;
    setPlayoffsEnabledLocal(enabled);
    setSavingPlayoffsEnabled(true);
    try {
      await api.put(`/leagues/${activeLeague.id}`, { playoffs_enabled: enabled });
      reloadLeague();
      toast.success(enabled ? "Playoffs enabled" : "Playoffs disabled — season standings determine the winner");
    } catch (e: any) {
      setPlayoffsEnabledLocal(prev);
      toast.error("Failed to update playoff setting", {
        description: e?.response?.data?.detail || e?.message,
      });
    } finally {
      setSavingPlayoffsEnabled(false);
    }
  };

  // ─── Scoring format auto-save handler ──────────────────────────
  const SCORING_FORMAT_LABELS: Record<string, string> = {
    rotisserie: "Rotisserie",
    points: "Points-Based",
    "h2h-points": "Head-to-Head Points",
    "h2h-categories": "Head-to-Head Most Categories",
    "h2h-each": "Head-to-Head Each Category",
  };

  const handleScoringFormatChange = async (newFormat: string) => {
    if (!activeLeague?.id || newFormat === scoringFormat) return;
    setScoringFormatLocal(newFormat);
    setScoringFormatError(false);
    setSavingScoringFormat(true);
    try {
      await api.put(`/leagues/${activeLeague.id}`, { scoring_format: newFormat });
      setSavedScoringFormat(newFormat);
      reloadLeague();
      toast.success("Scoring format saved", {
        description: SCORING_FORMAT_LABELS[newFormat] || newFormat,
      });
    } catch (e: any) {
      setScoringFormatError(true);
      toast.error("Failed to save scoring format", {
        description: e?.response?.data?.detail || e?.message,
      });
    } finally {
      setSavingScoringFormat(false);
    }
  };

  // ─── Unsaved changes guard ─────────────────────────────────────
  const isDirty = scoringFormat !== savedScoringFormat;
  const [showUnsavedDialog, setShowUnsavedDialog] = useState(false);
  const [pendingNavAction, setPendingNavAction] = useState<(() => void) | null>(null);

  // Browser close / refresh guard
  useEffect(() => {
    const handler = (e: BeforeUnloadEvent) => { e.preventDefault(); };
    if (isDirty) window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [isDirty]);

  // Browser back/forward guard
  useEffect(() => {
    if (!isDirty) return;
    window.history.pushState(null, "", window.location.href);
    const handler = () => {
      window.history.pushState(null, "", window.location.href);
      setShowUnsavedDialog(true);
      setPendingNavAction(() => () => window.history.back());
    };
    window.addEventListener("popstate", handler);
    return () => window.removeEventListener("popstate", handler);
  }, [isDirty]);

  // Tab-change interceptor — wraps setActiveTab to show the dialog when dirty
  const handleTabChange = (newTab: string) => {
    if (isDirty) {
      setShowUnsavedDialog(true);
      setPendingNavAction(() => () => setActiveTab(newTab));
      return;
    }
    setActiveTab(newTab);
  };

  const handleDialogSave = async () => {
    if (!activeLeague?.id) { handleDialogDiscard(); return; }
    setSavingScoringFormat(true);
    try {
      await api.put(`/leagues/${activeLeague.id}`, { scoring_format: scoringFormat });
      setSavedScoringFormat(scoringFormat);
      setScoringFormatError(false);
      reloadLeague();
      toast.success("Scoring format saved");
      setShowUnsavedDialog(false);
      pendingNavAction?.();
      setPendingNavAction(null);
    } catch (e: any) {
      toast.error("Save failed — staying on page", {
        description: e?.response?.data?.detail || e?.message,
      });
      setShowUnsavedDialog(false);
      setPendingNavAction(null);
    } finally {
      setSavingScoringFormat(false);
    }
  };

  const handleDialogDiscard = () => {
    setScoringFormatLocal(savedScoringFormat);
    setScoringFormatError(false);
    setShowUnsavedDialog(false);
    pendingNavAction?.();
    setPendingNavAction(null);
  };

  const handleDialogCancel = () => {
    setShowUnsavedDialog(false);
    setPendingNavAction(null);
  };

  // ─── Salary Retention Slots (per-team cap, default 3) ───────────
  // Controls how many retained-salary trades each team may stack. Stored
  // on the league document and consumed by /teams/{id}/compliance to drive
  // the "Retention Slots Remaining" tile on the roster page.
  const [retentionSlots, setRetentionSlots] = useState<number>(3);
  const [retentionSlotsDraft, setRetentionSlotsDraft] = useState<string>("3");
  const [savingRetentionSlots, setSavingRetentionSlots] = useState<boolean>(false);
  useEffect(() => {
    const val = Number((activeLeague as any)?.salary_retention_slots ?? 3);
    setRetentionSlots(val);
    setRetentionSlotsDraft(String(val));
  }, [activeLeague?.id, (activeLeague as any)?.salary_retention_slots]);

  const saveRetentionSlots = async () => {
    if (!activeLeague?.id) return;
    const parsed = parseInt(retentionSlotsDraft, 10);
    if (Number.isNaN(parsed) || parsed < 0 || parsed > 10) {
      toast.error("Retention slots must be a number between 0 and 10");
      return;
    }
    setSavingRetentionSlots(true);
    try {
      await api.put(`/leagues/${activeLeague.id}/salary-retention-slots`, {
        salary_retention_slots: parsed,
      });
      setRetentionSlots(parsed);
      toast.success(
        parsed === retentionSlots
          ? "No change — retention slots already set to " + parsed
          : `Retention slots updated to ${parsed} per team`,
      );
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Failed to save retention slots");
      setRetentionSlotsDraft(String(retentionSlots));
    } finally {
      setSavingRetentionSlots(false);
    }
  };

  const togglePrivacy = async (next: boolean) => {
    if (!activeLeague?.id) return;
    setPrivacyLoading(true);
    try {
      const { data } = await api.put(`/leagues/${activeLeague.id}`, { is_private: next });
      setIsPrivate(!!data.is_private);
      toast.success(next ? "League is now PRIVATE" : "League is now PUBLIC", {
        description: next
          ? "Hidden from search — invite-only."
          : "Visible in League Search to anyone with an account.",
      });
    } catch (e: any) {
      toast.error("Failed to update privacy", { description: e?.response?.data?.detail || e?.message });
    } finally {
      setPrivacyLoading(false);
    }
  };

  const recalcStats = async () => {
    if (!activeLeague?.id) return;
    setRecalcing(true);
    try {
      const { data } = await api.post(`/leagues/${activeLeague.id}/recalculate-stats`);
      toast.success("League stats recalculated", {
        description: `${data.teams_changed} team(s) updated from ${data.completed_matchups} completed matchup(s).`,
      });
    } catch (e: any) {
      toast.error("Recalculation failed", { description: e?.response?.data?.detail || e?.message });
    } finally {
      setRecalcing(false);
    }
  };

  // ─── Iter 101: ping the TBD-deadline scanner so admins get a top-bell
  // reminder ~2 days before any custom-bracket week that still has TBD slots.
  useEffect(() => {
    if (!activeLeague?.id) return;
    api.post(`/leagues/${activeLeague.id}/playoffs/check-tbd-deadlines`).catch(() => {});
  }, [activeLeague?.id]);

  // Fetch real audit log entries for the active league and merge with the seeded UI rows
  useEffect(() => {
    if (!activeLeague?.id) return;
    let cancelled = false;
    api.get(`/leagues/${activeLeague.id}/audit-log`).then(({ data }) => {
      if (cancelled) return;
      const backendEvents = (data?.events || []).map((e: any) => {
        const actionMap: Record<string, string> = {
          constitution_updated: "setting-change",
          settings_changed: "setting-change",
          trade_executed: "trade-override",
          roster_override: "roster-move",
        };
        const categoryMap: Record<string, string> = {
          constitution_updated: "League Settings",
          settings_changed: "League Settings",
          trade_executed: "Trade",
          roster_override: "Roster",
        };
        return {
          id: e.id || e._id,
          timestamp: new Date(e.created_at),
          category: categoryMap[e.action] || "League Settings",
          team: "—",
          action: actionMap[e.action] || "setting-change",
          description: (() => {
            if (e.action === "constitution_updated") {
              const n = e.diff?.new_length ?? 0;
              return `Constitution updated (${n} chars) — preview: "${(e.diff?.preview || '').slice(0, 60)}…"`;
            }
            return e.action.replace(/_/g, " ");
          })(),
          performedBy: `${e.actor_name || 'Unknown'}${e.role ? ` (${e.role.replace('_', '-')})` : ''}`,
        };
      });
      // Prepend real events so they appear on top; keep generated mock rows below for richer UI
      setAuditLog((prev: any[]) => [...backendEvents, ...prev]);
    }).catch(() => {});
    return () => { cancelled = true; };
  }, [activeLeague?.id]);
  const [duplicatePlayers, setDuplicatePlayers] = useState("not-used");
  const [leagueLogo, setLeagueLogo] = useState<string | null>(null);
  const [leagueLogoName, setLeagueLogoName] = useState<string | null>(null);
  const logoInputRef = useRef<HTMLInputElement>(null);
  const [requireMinGamesMissed, setRequireMinGamesMissed] = useState(false);
  const [selectedPlayerCriteria, setSelectedPlayerCriteria] = useState<string[]>(["all"]);
  const [draftRounds, setDraftRounds] = useState(5);
  const [roundTimes, setRoundTimes] = useState<Record<number, string>>({});
  const [expandedDraft, setExpandedDraft] = useState<string | null>(null);
  const [expandedDraftResults, setExpandedDraftResults] = useState<string | null>(null);
  const [adminSubTab, setAdminSubTab] = useState("teams");
  const [createDraftPickTrading, setCreateDraftPickTrading] = useState(true);
  const [draftClockEnabled, setDraftClockEnabled] = useState(true);
  const [draftClockStart, setDraftClockStart] = useState("09:00");
  const [draftClockEnd, setDraftClockEnd] = useState("23:00");

  // Roster Lock & Goalie Scoring state
  const [rosterLockType, setRosterLockType] = useState("daily");
  const [scoringPeriodStartDay, setScoringPeriodStartDay] = useState("monday");
  const [semiWeeklyEnabled, setSemiWeeklyEnabled] = useState(false);
  const [semiWeeklySplitDay, setSemiWeeklySplitDay] = useState("friday");

  const completedDraftResults = [
    { draftId: "draft-3", pick: 1, round: 1, team: "Ice Crushers", player: "Connor Bedard", position: "C" },
    { draftId: "draft-3", pick: 2, round: 1, team: "Glacier Kings", player: "Matvei Michkov", position: "RW" },
    { draftId: "draft-3", pick: 3, round: 1, team: "Northern Lights", player: "Adam Fantilli", position: "C" },
    { draftId: "draft-3", pick: 4, round: 1, team: "Blizzard", player: "Leo Carlsson", position: "C" },
    { draftId: "draft-3", pick: 5, round: 1, team: "Tundra Kings", player: "Will Smith", position: "C" },
    { draftId: "draft-3", pick: 6, round: 2, team: "Tundra Kings", player: "Zach Benson", position: "LW" },
    { draftId: "draft-3", pick: 7, round: 2, team: "Blizzard", player: "Ryan Leonard", position: "RW" },
    { draftId: "draft-3", pick: 8, round: 2, team: "Northern Lights", player: "Dalibor Dvorsky", position: "C" },
    { draftId: "draft-3", pick: 9, round: 2, team: "Glacier Kings", player: "Nate Danielson", position: "C" },
    { draftId: "draft-3", pick: 10, round: 2, team: "Ice Crushers", player: "Oliver Moore", position: "C" },
  ];

  // Iter 227 — Replace the previous hardcoded `scheduledDrafts` mock with a
  // live fetch from `/api/drafts?league_id=...`. New leagues start empty
  // (the TFHL "3 saved drafts" bug). Re-fetched after the Create Draft
  // wire-up below persists a new draft.
  const [scheduledDrafts, setScheduledDrafts] = useState([]);

  const reloadScheduledDrafts = async () => {
    if (!activeLeague?.id) {
      setScheduledDrafts([]);
      return;
    }
    try {
      const { data } = await api.get(`/drafts`, { params: { league_id: activeLeague.id } });
      // Iter 228d — Normalize draft rows for display:
      //   • formatSeconds: turn raw seconds (e.g. 7200) into "2 hr" / "30 min"
      //   • titleCase: capitalize "all" → "All", "auto-select" → "Auto-select"
      //   • split scheduled_time ISO into separate date + time strings
      const formatSeconds = (s) => {
        const n = parseInt(s, 10);
        if (!Number.isFinite(n) || n <= 0) return "—";
        if (n >= 3600 && n % 3600 === 0) return `${n / 3600} hr`;
        if (n >= 3600) return `${(n / 3600).toFixed(1)} hr`;
        if (n >= 60) return `${Math.round(n / 60)} min`;
        return `${n} sec`;
      };
      const titleCase = (v) => {
        if (Array.isArray(v)) return v.map(titleCase).join(", ");
        if (!v) return v;
        const s = String(v).replace(/-/g, " ").replace(/_/g, " ");
        return s.charAt(0).toUpperCase() + s.slice(1);
      };
      const splitDateTime = (iso) => {
        if (!iso) return { date: "—", time: "—" };
        try {
          const dt = new Date(iso);
          if (isNaN(dt.getTime())) return { date: String(iso), time: "—" };
          return {
            date: dt.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" }),
            time: dt.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" }),
          };
        } catch { return { date: String(iso), time: "—" }; }
      };
      const rows = (Array.isArray(data) ? data : data?.drafts || []).map((d) => {
        const { date, time } = splitDateTime(d.scheduled_time || d.scheduled_date);
        return {
          id: d.id || d._id,
          name: d.name || d.title || "Untitled draft",
          type: titleCase(d.type || d.draft_type || "snake draft"),
          format: d.format || (d.snake_draft ? "Snake Draft" : "Linear Draft"),
          rounds: d.rounds || d.total_rounds || 0,
          timePerPick: formatSeconds(d.time_per_pick || d.timePerPick),
          // Iter 228n — Raw fields so the Edit Draft dialog can
          // pre-fill date pickers + numeric inputs without re-parsing.
          scheduledISO: d.scheduled_time || d.scheduled_date || null,
          timePerPickSeconds: Number(d.time_per_pick || d.timePerPick || 3600),
          excludePreviouslyDrafted: !!d.exclude_previously_drafted,
          minorsEligibilityRequired: !!d.minors_eligibility_required,
          // Iter 228o — Raw fields for the expanded Edit Draft dialog.
          draftType: d.draft_type || d.type || "entry",
          snakeDraft: d.snake_draft !== undefined ? !!d.snake_draft : true,
          // Backend stores player_criteria as a list (modern) or string (legacy).
          playerCriteriaRaw: d.player_criteria,
          missedPickActionKey: d.missed_pick_action || "auto-select",
          deferUserOptions: Array.isArray(d.defer_user_options)
            ? d.defer_user_options
            : ["auto-best", "auto-queue", "pick-anytime"],
          roundTimeOverrides: Array.isArray(d.round_time_overrides) ? d.round_time_overrides : [],
          playerCriteria: titleCase(d.player_criteria || "all"),
          missedPickAction: titleCase(d.missed_pick_action || "auto-select best available"),
          scheduledDate: date,
          scheduledTime: time,
          status: (d.status || "scheduled"),
          completedDate: d.completed_at || d.completedDate || null,
          pickTradingEnabled: !!d.pick_trading_enabled,
          tradingWindowOpens: d.trading_window_opens || null,
        };
      });
      setScheduledDrafts(rows);
    } catch {
      setScheduledDrafts([]);
    }
  };

  useEffect(() => {
    reloadScheduledDrafts();
  }, [activeLeague?.id]);

  const playerCriteriaOptions = [
    { value: "all", label: "All Players" },
    { value: "rookies", label: "Rookies Only" },
    { value: "prospects", label: "Prospects Only" },
    { value: "nhl", label: "NHL Rostered Only" },
    { value: "unsigned", label: "Unsigned / Draft Eligible" },
  ];

  const handleLogoUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (file.size > 2 * 1024 * 1024) {
      toast.error("File is too large. Maximum size is 2MB.");
      return;
    }
    if (!file.type.startsWith("image/")) {
      toast.error("Please upload an image file (PNG, JPG, SVG, etc.)");
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      setLeagueLogo(reader.result as string);
      setLeagueLogoName(file.name);
      toast.success("League logo uploaded");
    };
    reader.readAsDataURL(file);
  };

  const addAuditEntry = (entry: Omit<AuditLogEntry, "id" | "timestamp">) => {
    setAuditLog(prev => [{
      ...entry,
      id: `al-${Date.now()}`,
      timestamp: new Date(),
    }, ...prev]);
  };

  const toggleTeam = (team: string) => {
    setSelectedTeams(prev => 
      prev.includes(team) ? prev.filter(t => t !== team) : [...prev, team]
    );
  };

  const addCustomInjury = () => {
    // Prevent duplicate type+timeline combinations
    const exists = customInjuries.some(
      (i) => i.type === newInjuryType && i.timeline === newInjuryTimeline
    );
    if (exists) {
      toast.error(
        `${newInjuryType} · ${newInjuryTimeline} is already in the list. Remove the existing entry to re-add it.`
      );
      return;
    }
    setCustomInjuries(prev => [...prev, { type: newInjuryType, timeline: newInjuryTimeline, irEligible: true }]);
  };

  const removeCustomInjury = (index: number) => {
    setCustomInjuries(prev => prev.filter((_, i) => i !== index));
  };

  const toggleScoringCategory = (id: string) => {
    setScoringSettings(prev => ({
      ...prev,
      [id]: { ...prev[id], enabled: !prev[id].enabled }
    }));
  };

  const updateScoringPoints = (id: string, points: number) => {
    setScoringSettings(prev => ({
      ...prev,
      [id]: { ...prev[id], points }
    }));
  };

  const skaterCategories = scoringCategories.filter(cat => cat.type === "skater" || cat.type === "both");
  const goalieCategories = scoringCategories.filter(cat => cat.type === "goalie" || cat.type === "both");

  return (
    <AppLayout>
      <div className="p-6 space-y-6">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-primary/20 border border-primary/30">
            <Settings className="h-6 w-6 text-primary" />
          </div>
          <div className="flex-1">
            <h1 className="text-2xl font-bold">League Administration</h1>
            <p className="text-muted-foreground">Configure your league settings, rules, and monitor team activity</p>
          </div>
          <Button
            size="sm"
            variant={activeLeague?.setup_wizard_complete ? "outline" : "default"}
            onClick={reopenWizard}
            data-testid="reopen-setup-wizard-btn"
            disabled={!activeLeague?.id}
            className={activeLeague?.setup_wizard_complete ? "" : "bg-amber-500/90 text-amber-950 hover:bg-amber-400 font-semibold"}
          >
            <Trophy className="h-4 w-4 mr-1.5" />
            {activeLeague?.setup_wizard_complete ? "Re-run Setup Wizard" : "Complete Setup"}
          </Button>
        </div>

        {/* Setup Wizard Dialog */}
        <SetupWizard
          open={wizardOpen}
          onClose={handleWizardClose}
          leagueId={activeLeague?.id}
          onComplete={() => { /* No-op; next page load will see setup_wizard_complete=true */ }}
        />

        {/* League Health Score (top of page, above tabs) */}
        <LeagueHealthCard
          leagueId={activeLeague?.id}
          onJumpToTab={(tab) => {
            // Iter 231an — Controlled tab state, so the cleanest jump
            // is to set the state directly. We keep the DOM-click
            // fallback for any old callers that arrive without a
            // useState handle.
            if (typeof tab === "string") setActiveTab(tab);
            const trigger = document.querySelector(`[data-state] [value="${tab}"], [role="tab"][value="${tab}"]`);
            if (trigger instanceof HTMLElement) trigger.click();
          }}
          onReopenWizard={reopenWizard}
        />

        {/* Iter 231an — Controlled tabs so the new mobile Select can
            drive the same active tab as the desktop TabsList. Without
            controlled state the Select would be a parallel UI that
            never reflects clicks on the (hidden) desktop tabs. */}
        <Tabs value={activeTab} onValueChange={handleTabChange} className="space-y-6">
          {/* Mobile-only tab selector. Below md the 13-item tab strip
              required heavy horizontal scrolling; a native-feeling
              dropdown gives one-tap access to every section. */}
          <div className="md:hidden">
            <Select value={activeTab} onValueChange={handleTabChange}>
              <SelectTrigger
                className="w-full bg-secondary border border-border h-11"
                data-testid="commissioner-settings-mobile-tab-select"
              >
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {COMMISSIONER_TABS.map(({ value, icon: Icon, label }) => (
                  <SelectItem
                    key={value}
                    value={value}
                    data-testid={`commissioner-settings-mobile-tab-${value}`}
                  >
                    <span className="flex items-center gap-2">
                      <Icon className="h-4 w-4" />
                      {label}
                    </span>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Desktop tab strip — hidden on mobile to reclaim the
              horizontal real-estate for the Select above. */}
          <TabsList className="hidden md:flex flex-wrap h-auto bg-secondary border border-border">
            <TabsTrigger value="league-setup" className="data-[state=active]:bg-primary/20">
              <Trophy className="h-4 w-4 mr-2" />
              League Setup
            </TabsTrigger>
            <TabsTrigger value="player-pool" className="data-[state=active]:bg-primary/20">
              <Users className="h-4 w-4 mr-2" />
              Player Pool
            </TabsTrigger>
            <TabsTrigger value="rosters" className="data-[state=active]:bg-primary/20">
              <Shield className="h-4 w-4 mr-2" />
              Rosters
            </TabsTrigger>
            <TabsTrigger value="divisions" className="data-[state=active]:bg-primary/20" data-testid="tab-divisions">
              <Trophy className="h-4 w-4 mr-2" />
              League Structure
            </TabsTrigger>
            <TabsTrigger value="rules-schedule" className="data-[state=active]:bg-primary/20" data-testid="tab-rules-schedule">
              <Sliders className="h-4 w-4 mr-2" />
              Transactions
            </TabsTrigger>
            <TabsTrigger value="salary-cap-contracts" className="data-[state=active]:bg-primary/20" data-testid="tab-salary-cap-contracts">
              <DollarSign className="h-4 w-4 mr-2" />
              Salary Cap & Contracts
            </TabsTrigger>
            <TabsTrigger value="scoring" className="data-[state=active]:bg-primary/20">
              <Target className="h-4 w-4 mr-2" />
              Scoring
            </TabsTrigger>
            <TabsTrigger value="draft" className="data-[state=active]:bg-primary/20">
              <LayoutGrid className="h-4 w-4 mr-2" />
              Draft
            </TabsTrigger>
            <TabsTrigger value="tanking" className="data-[state=active]:bg-primary/20">
              <AlertTriangle className="h-4 w-4 mr-2" />
              Tank Monitor
            </TabsTrigger>
            <TabsTrigger value="roster-monitor" className="data-[state=active]:bg-primary/20">
              <ClipboardCheck className="h-4 w-4 mr-2" />
              Roster Monitor
            </TabsTrigger>
            <TabsTrigger value="admin" className="data-[state=active]:bg-primary/20">
              <UserCog className="h-4 w-4 mr-2" />
              League Administration
            </TabsTrigger>
            <TabsTrigger value="audit-log" className="data-[state=active]:bg-primary/20">
              <ScrollText className="h-4 w-4 mr-2" />
              Audit Log
            </TabsTrigger>
          </TabsList>

          {/* League Setup Tab */}
          <TabsContent value="league-setup" className="space-y-6">
            <LeagueSetupTab
              isPrivate={isPrivate}
              togglePrivacy={togglePrivacy}
              privacyLoading={privacyLoading}
              activeLeague={activeLeague}
              recalcStats={recalcStats}
              recalcing={recalcing}
              scoringFormat={scoringFormat}
              setScoringFormat={handleScoringFormatChange}
              savingScoringFormat={savingScoringFormat}
              scoringFormatError={scoringFormatError}
              playoffsEnabled={playoffsEnabled}
              savingPlayoffsEnabled={savingPlayoffsEnabled}
              onPlayoffsEnabledChange={handlePlayoffsEnabledChange}
              leagueLogo={leagueLogo}
              leagueLogoName={leagueLogoName}
              logoInputRef={logoInputRef}
              handleLogoUpload={handleLogoUpload}
              setLeagueLogo={setLeagueLogo}
              setLeagueLogoName={setLeagueLogoName}
              RosterLockCard={RosterLockCard}
              EmergencyRosterChangesCard={EmergencyRosterChangesCard}
              GoalieScoringCard={GoalieScoringCard}
              reloadLeague={reloadLeague}
              isH2H={isH2H}
              rosterLockType={rosterLockType}
              setRosterLockType={setRosterLockType}
              scoringPeriodStartDay={scoringPeriodStartDay}
              setScoringPeriodStartDay={setScoringPeriodStartDay}
              semiWeeklySplitDay={semiWeeklySplitDay}
              setSemiWeeklySplitDay={setSemiWeeklySplitDay}
            />
          </TabsContent>

          {/* Player Pool Tab */}
          <TabsContent value="player-pool" className="space-y-6">
            <PlayerPoolTab
              nhlTeams={nhlTeams}
              selectedTeams={selectedTeams}
              toggleTeam={toggleTeam}
              duplicatePlayers={duplicatePlayers}
              setDuplicatePlayers={setDuplicatePlayers}
            />
          </TabsContent>

          {/* Rosters Tab */}
          <TabsContent value="rosters" className="space-y-6">
            <RostersTab />
          </TabsContent>

          {/* Divisions Tab */}
          <TabsContent value="divisions" className="space-y-6">
            <DivisionsTab leagueId={activeLeague?.id} />
          </TabsContent>

          {/* Rules & Schedule Tab */}
          <TabsContent value="rules-schedule" className="space-y-6">
            <TransactionsConfigCards leagueId={activeLeague?.id} leagueTeams={leagueTeams} />
            <Separator />
            <RulesScheduleTab />
          </TabsContent>

          {/* Iter 121 — Salary Cap & Contracts Tab */}
          <TabsContent value="salary-cap-contracts" className="space-y-6" data-testid="salary-cap-contracts-tab">
            <SalaryCapContractsTab activeLeague={activeLeague} reloadLeague={reloadLeague} />
          </TabsContent>

          {/* Scoring Tab */}
          <TabsContent value="scoring" className="space-y-6">
            <ScoringTab
              skaterCategories={skaterCategories}
              goalieCategories={goalieCategories}
              scoringSettings={scoringSettings}
              toggleScoringCategory={toggleScoringCategory}
              updateScoringPoints={updateScoringPoints}
            />
          </TabsContent>

          {/* Draft Tab */}
          <TabsContent value="draft" className="space-y-6">
            <DraftTab
              ctx={{
                draftType, firstDraftCompleted, draftRounds, setDraftRounds,
                roundTimes, setRoundTimes,
                draftClockEnabled, setDraftClockEnabled,
                draftClockStart, setDraftClockStart,
                draftClockEnd, setDraftClockEnd,
                selectedPlayerCriteria, setSelectedPlayerCriteria,
                createDraftPickTrading, setCreateDraftPickTrading,
                expandedDraft, setExpandedDraft,
                expandedDraftResults, setExpandedDraftResults,
                activeLeague, persistDraftType, completedDraftResults,
                playerCriteriaOptions, scheduledDrafts,
                onReloadScheduledDrafts: reloadScheduledDrafts,
              }}
            />
          </TabsContent>

          {/* Tank Monitor Tab */}
          <TabsContent value="tanking" className="space-y-6">
            <TankMonitorTab TankMonitorTable={TankMonitorTable} leagueId={activeLeague?.id} />
          </TabsContent>
          {/* Roster Monitor Tab */}
          <TabsContent value="roster-monitor" className="space-y-6">
            <RosterMonitorTab RosterMonitorTable={RosterMonitorTable} onAuditLog={addAuditEntry} leagueId={activeLeague?.id} />
          </TabsContent>

          {/* Audit Log Tab */}
          <TabsContent value="audit-log" className="space-y-6">
            <AuditLogTab
              auditLog={auditLog}
              auditFilterCategory={auditFilterCategory}
              setAuditFilterCategory={setAuditFilterCategory}
            />
          </TabsContent>

          {/* League Administration Tab */}
          <TabsContent value="admin" className="space-y-6">
            <LeagueAdminTab
              adminSubTab={adminSubTab}
              setAdminSubTab={setAdminSubTab}
              isH2H={isH2H}
            />
          </TabsContent>
        </Tabs>

        {/* Unsaved scoring format — navigation guard dialog */}
        <AlertDialog open={showUnsavedDialog} onOpenChange={(open) => { if (!open) handleDialogCancel(); }}>
          <AlertDialogContent data-testid="unsaved-changes-dialog">
            <AlertDialogHeader>
              <AlertDialogTitle>Unsaved Changes</AlertDialogTitle>
              <AlertDialogDescription>
                Your scoring format change hasn't been saved yet. Would you like to save before leaving?
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter className="gap-2 sm:gap-0">
              <AlertDialogCancel
                onClick={handleDialogCancel}
                data-testid="unsaved-changes-cancel-btn"
              >
                Stay
              </AlertDialogCancel>
              <Button
                variant="outline"
                onClick={handleDialogDiscard}
                data-testid="unsaved-changes-discard-btn"
              >
                Discard & Leave
              </Button>
              <AlertDialogAction
                onClick={handleDialogSave}
                disabled={savingScoringFormat}
                data-testid="unsaved-changes-save-btn"
              >
                {savingScoringFormat ? "Saving…" : "Save & Leave"}
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </div>
    </AppLayout>
  );
};

export default CommissionerSettings;
