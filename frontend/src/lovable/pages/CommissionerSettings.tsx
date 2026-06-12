// @ts-nocheck
import { AppLayout } from "@/components/layout/AppLayout";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { Settings, Users, Trophy, Shield, Target, LayoutGrid, AlertTriangle, ClipboardCheck, ScrollText, UserCog, Sliders, DollarSign } from "lucide-react";
import { useState, useRef, useEffect } from "react";
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


const CommissionerSettings = () => {

  const [selectedTeams, setSelectedTeams] = useState<string[]>([]);
  const [scoringFormat, setScoringFormat] = useState("h2h-points");
  const isH2H = scoringFormat.startsWith("h2h");
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

  // ─── Setup Wizard (first-time) ─────────────────────────────────
  const [wizardOpen, setWizardOpen] = useState(false);
  useEffect(() => {
    // Auto-open wizard once per session per league when setup isn't complete yet.
    if (activeLeague?.id && activeLeague.setup_wizard_complete === false) {
      const dismissedKey = `dd-setup-wizard-dismissed-${activeLeague.id}`;
      if (!sessionStorage.getItem(dismissedKey)) {
        setWizardOpen(true);
      }
    }
  }, [activeLeague?.id, activeLeague?.setup_wizard_complete]);
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

  const scheduledDrafts: Array<{ id: string; name: string; type: string; format: string; rounds: number; timePerPick: string; playerCriteria: string; missedPickAction: string; scheduledDate: string; scheduledTime: string; status: "scheduled" | "in-progress" | "completed"; completedDate: string | null; pickTradingEnabled: boolean; tradingWindowOpens: string | null }> = [
    {
      id: "draft-1",
      name: "2026 NHL Entry Draft",
      type: "NHL Entry Draft",
      format: "Snake Draft",
      rounds: 5,
      timePerPick: "5 minutes",
      playerCriteria: "Rookies Only, Prospects Only",
      missedPickAction: "Auto-select best available",
      scheduledDate: "June 15, 2026",
      scheduledTime: "7:00 PM EST",
      status: "scheduled" as const,
      completedDate: null,
      pickTradingEnabled: true,
      tradingWindowOpens: "2-weeks",
    },
    {
      id: "draft-2",
      name: "2026 Supplemental Draft",
      type: "Supplemental Draft",
      format: "Linear Draft",
      rounds: 3,
      timePerPick: "2 minutes",
      playerCriteria: "Unsigned / Draft Eligible",
      missedPickAction: "Allow pick anytime when they return",
      scheduledDate: "July 10, 2026",
      scheduledTime: "8:00 PM EST",
      status: "scheduled" as const,
      completedDate: null,
      pickTradingEnabled: false,
      tradingWindowOpens: null,
    },
    {
      id: "draft-3",
      name: "2025 NHL Entry Draft",
      type: "NHL Entry Draft",
      format: "Snake Draft",
      rounds: 5,
      timePerPick: "10 minutes",
      playerCriteria: "All Players",
      missedPickAction: "Auto-select best available",
      scheduledDate: "June 20, 2025",
      scheduledTime: "7:00 PM EST",
      status: "completed" as const,
      completedDate: "June 20, 2025",
      pickTradingEnabled: true,
      tradingWindowOpens: "immediately",
    },
  ];

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
            variant="outline"
            onClick={reopenWizard}
            data-testid="reopen-setup-wizard-btn"
            disabled={!activeLeague?.id}
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
            const trigger = document.querySelector(`[data-state] [value="${tab}"], [role="tab"][value="${tab}"]`);
            if (trigger instanceof HTMLElement) trigger.click();
          }}
          onReopenWizard={reopenWizard}
        />

        <Tabs defaultValue="league-setup" className="space-y-6">
          <TabsList className="bg-secondary border border-border">
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
              setScoringFormat={setScoringFormat}
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
      </div>
    </AppLayout>
  );
};

export default CommissionerSettings;
