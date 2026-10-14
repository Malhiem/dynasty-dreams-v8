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
import { useDraftSettings } from "./commissioner/useDraftSettings";
import CommissionerTabNavigation from "./commissioner/CommissionerTabNavigation";
import UnsavedScoringDialog from "./commissioner/UnsavedScoringDialog";
import CommissionerAccess from "./commissioner/CommissionerAccess";
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
import PersistedScoringTab from "@/lovable/pages/commissioner/tabs/PersistedScoringTab";
import { TankMonitorTab, RosterMonitorTab } from "@/lovable/pages/commissioner/tabs/MonitorTabs";
import SalaryCapContractsTab from "@/lovable/pages/commissioner/tabs/SalaryCapContractsTab";
import LeagueAdminTab from "@/lovable/pages/commissioner/tabs/LeagueAdminTab";
import TransactionsConfigCards from "@/lovable/pages/commissioner/TransactionsConfigCards";
import LeagueHealthCard from "@/lovable/components/admin/LeagueHealthCard";

import {
  nhlTeams,
  type AuditLogEntry,
  generateMockAuditLog,
  TankMonitorTable,
  RosterMonitorTable,
} from "@/lovable/pages/commissioner/data/commissionerData";


const CommissionerSettings = ({ leagueContext }) => {

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
    "prospects", "constitution", "audit", "admin",
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
  // Iter 143 — first-time draft gating + persistence (effects defined below `activeLeague`)
  const [auditLog, setAuditLog] = useState<AuditLogEntry[]>(generateMockAuditLog());
  const [auditFilterCategory, setAuditFilterCategory] = useState<string>("all");
  const { league: activeLeague, leagueTeams, reloadLeague } = leagueContext;
  const {
    draftType, firstDraftCompleted, persistDraftType, selectedPlayerCriteria,
    setSelectedPlayerCriteria, draftRounds, setDraftRounds, roundTimes,
    setRoundTimes, expandedDraft, setExpandedDraft, expandedDraftResults,
    setExpandedDraftResults, createDraftPickTrading, setCreateDraftPickTrading, draftClockEnabled,
    setDraftClockEnabled, draftClockStart, setDraftClockStart, draftClockEnd,
    setDraftClockEnd, completedDraftResults, scheduledDrafts, reloadScheduledDrafts,
    playerCriteriaOptions
  } = useDraftSettings(activeLeague);

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

  // ─── Max teams auto-save (debounced) ───────────────────────────
  const maxTeamsTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const handleMaxTeamsChange = (value: number) => {
    if (!activeLeague?.id) return;
    // Debounce so rapid typing doesn't fire many PUTs
    if (maxTeamsTimer.current) clearTimeout(maxTeamsTimer.current);
    maxTeamsTimer.current = setTimeout(async () => {
      try {
        await api.put(`/leagues/${activeLeague.id}`, { max_teams: value });
        reloadLeague();
        toast.success(`Team cap updated to ${value}`);
      } catch (e: any) {
        toast.error("Failed to update team cap", {
          description: e?.response?.data?.detail || e?.message,
        });
      }
    }, 600);
  };

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
  const [adminSubTab, setAdminSubTab] = useState("teams");

  // Roster Lock & Goalie Scoring state
  const [rosterLockType, setRosterLockType] = useState("daily");
  const [scoringPeriodStartDay, setScoringPeriodStartDay] = useState("monday");
  const [semiWeeklyEnabled, setSemiWeeklyEnabled] = useState(false);
  const [semiWeeklySplitDay, setSemiWeeklySplitDay] = useState("friday");

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
          <CommissionerTabNavigation activeTab={activeTab} onTabChange={handleTabChange} />

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
              onMaxTeamsChange={handleMaxTeamsChange}
              leagueLogo={leagueLogo}
              leagueLogoName={leagueLogoName}
              logoInputRef={logoInputRef}
              handleLogoUpload={handleLogoUpload}
              setLeagueLogo={setLeagueLogo}
              setLeagueLogoName={setLeagueLogoName}
              RosterLockCard={RosterLockCard}
              EmergencyRosterChangesCard={EmergencyRosterChangesCard}
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
            <PersistedScoringTab
              GoalieScoringCard={GoalieScoringCard}
              activeLeague={activeLeague}
              reloadLeague={reloadLeague}
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
              league={activeLeague}
            />
          </TabsContent>
        </Tabs>

        <UnsavedScoringDialog open={showUnsavedDialog} saving={savingScoringFormat}
          onCancel={handleDialogCancel} onDiscard={handleDialogDiscard} onSave={handleDialogSave} />
      </div>
    </AppLayout>
  );
};

export default function CommissionerSettingsPage() {
  return <CommissionerAccess component={CommissionerSettings} />;
}
