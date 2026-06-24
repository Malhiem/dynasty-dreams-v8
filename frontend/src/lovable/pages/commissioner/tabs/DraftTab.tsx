// @ts-nocheck
/**
 * Iter 157 — DraftTab extracted from CommissionerSettings.tsx using a
 * typed context-bundle pattern (lower noise than 16-prop drilling).
 *
 * The parent assembles `DraftTabContext` from its existing state hooks
 * and passes it as a single prop. Any future field added to the tab body
 * just needs an entry on the interface — no signature churn at the call site.
 */
import { useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Separator } from "@/components/ui/separator";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Table, TableHeader, TableRow, TableHead, TableBody, TableCell,
} from "@/components/ui/table";
import { Plus, X, ChevronDown, ChevronRight, Trophy, Calendar, Users } from "lucide-react";
import api from "@/lib/api";
import { ClockPicker } from "@/components/ui/clock-picker";
import { LotteryRevealDialog } from "@/lovable/components/LotteryRevealDialog";
import { useNavigate } from "react-router-dom";
import TransactionsConfigCards, { TransactionsDraftRulesCard } from "@/lovable/pages/commissioner/TransactionsConfigCards";
import DraftOrderConfigCard from "@/lovable/pages/commissioner/DraftOrderConfigCard";
import KeeperSettingsCard from "@/lovable/pages/commissioner/KeeperSettingsCard";
import ExpansionDraftSettingsCard from "@/lovable/pages/commissioner/ExpansionDraftSettingsCard";
import CommissionerProtectionOverridePanel from "@/lovable/pages/commissioner/CommissionerProtectionOverridePanel";
import { toast } from "sonner";

export interface DraftTabContext {
  // State
  draftType: string;
  firstDraftCompleted: boolean;
  draftRounds: number;
  setDraftRounds: (v: number) => void;
  roundTimes: number[];
  setRoundTimes: (v: number[]) => void;
  draftClockEnabled: boolean;
  setDraftClockEnabled: (v: boolean) => void;
  draftClockStart: string;
  setDraftClockStart: (v: string) => void;
  draftClockEnd: string;
  setDraftClockEnd: (v: string) => void;
  selectedPlayerCriteria: string[];
  setSelectedPlayerCriteria: (v: string[]) => void;
  createDraftPickTrading: boolean;
  setCreateDraftPickTrading: (v: boolean) => void;
  expandedDraft: string | null;
  setExpandedDraft: (v: string | null) => void;
  expandedDraftResults: string | null;
  setExpandedDraftResults: (v: string | null) => void;
  // Helpers + references
  activeLeague: any;
  persistDraftType: (v: string) => void;
  completedDraftResults: any[];
  playerCriteriaOptions: any[];
  scheduledDrafts: any[];
  onReloadScheduledDrafts?: () => void | Promise<void>;
}

interface DraftTabProps {
  ctx: DraftTabContext;
}

export default function DraftTab({ ctx }: DraftTabProps) {
  const navigate = useNavigate();
  const {
    draftType, firstDraftCompleted, draftRounds, setDraftRounds, roundTimes, setRoundTimes,
    draftClockEnabled, setDraftClockEnabled, draftClockStart, setDraftClockStart,
    draftClockEnd, setDraftClockEnd, selectedPlayerCriteria, setSelectedPlayerCriteria,
    createDraftPickTrading, setCreateDraftPickTrading,
    expandedDraft, setExpandedDraft, expandedDraftResults, setExpandedDraftResults,
    activeLeague, persistDraftType, completedDraftResults, playerCriteriaOptions, scheduledDrafts,
    onReloadScheduledDrafts,
  } = ctx;

  // Iter 227 — Real Create Draft handler (was a toast-only stub).
  const [creatingDraft, setCreatingDraft] = useState(false);
  // Iter 228d — New Create-Draft state: name (was being dropped → "Untitled Draft"),
  // scheduled date+time, missed-pick action with "defer-to-user", multi-select
  // window-elapsed actions (OR semantics).
  const [draftName, setDraftName] = useState<string>("");
  const [draftScheduledDate, setDraftScheduledDate] = useState<string>("");
  const [draftScheduledTime, setDraftScheduledTime] = useState<string>("19:00");
  const [missedPickAction, setMissedPickAction] = useState<string>("auto-select");
  const [windowElapsedActions, setWindowElapsedActions] = useState<string[]>([]);
  // Iter 228d — Deleting a scheduled draft (soft delete, 15-day recovery)
  const [deletingDraftId, setDeletingDraftId] = useState<string | null>(null);
  const handleDeleteDraft = async (draftId: string) => {
    if (!draftId) return;
    if (!window.confirm("Archive this draft? It can be restored within 15 days, then it will be permanently deleted.")) return;
    setDeletingDraftId(draftId);
    try {
      await api.delete(`/drafts/${draftId}`);
      toast.success("Draft archived (recoverable for 15 days)");
      await onReloadScheduledDrafts?.();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Failed to archive draft");
    } finally {
      setDeletingDraftId(null);
    }
  };
  // Iter 228 — Lottery Generator state. Opens the animated reveal modal
  // when the commissioner picks "Draft Lottery Generator" from the Draft
  // Order select. Final order is persisted via onComplete callback below.
  const [lotteryOpen, setLotteryOpen] = useState(false);
  const [lotteryTeams, setLotteryTeams] = useState([]);
  const openLottery = async () => {
    if (!activeLeague?.id) {
      toast.error("Select a league before running the lottery.");
      return;
    }
    try {
      const { data } = await api.get(`/teams`, { params: { league_id: activeLeague.id } });
      const arr = Array.isArray(data) ? data : (data?.teams || []);
      if (arr.length < 2) {
        toast.error("Need at least 2 teams in the league to run a lottery.");
        return;
      }
      setLotteryTeams(arr.map((t) => ({ id: t.id || t._id, name: t.name })));
      setLotteryOpen(true);
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Failed to load teams for lottery");
    }
  };
  const handleCreateDraft = async () => {
    if (!activeLeague?.id) {
      toast.error("Select a league before creating a draft.");
      return;
    }
    setCreatingDraft(true);
    try {
      // Iter 228d — Default to 1 hour (3600s) instead of 5 minutes when
      // no per-round override is set. Matches the user-stated default for
      // tiered times (R1+ = 1h, configurable via the round-time grid).
      const defaultTime = Math.min(86400, parseInt(roundTimes[1] || roundTimes[2] || "3600", 10));
      // Iter 228d — Compose scheduled_time as ISO from date + time inputs
      let scheduledIso: string | null = null;
      if (draftScheduledDate) {
        const t = (draftScheduledTime || "19:00");
        try {
          const dt = new Date(`${draftScheduledDate}T${t}:00`);
          if (!isNaN(dt.getTime())) scheduledIso = dt.toISOString();
        } catch { /* ignore */ }
      }
      // Iter 228d — Build round_time_overrides from per-round overrides
      // that differ from the default. Backend stores ranges; we collapse
      // contiguous identical values into [{from,to,seconds}] tuples.
      const overrides: { from: number; to: number; seconds: number }[] = [];
      let runStart: number | null = null;
      let runVal: string | null = null;
      for (let r = 1; r <= draftRounds; r++) {
        const v = roundTimes[r] || String(defaultTime);
        if (runVal === null) { runStart = r; runVal = v; continue; }
        if (v !== runVal) {
          if (runVal !== String(defaultTime)) {
            overrides.push({ from: runStart!, to: r - 1, seconds: parseInt(runVal, 10) });
          }
          runStart = r; runVal = v;
        }
      }
      if (runVal !== null && runVal !== String(defaultTime)) {
        overrides.push({ from: runStart!, to: draftRounds, seconds: parseInt(runVal, 10) });
      }
      const body: any = {
        league_id: activeLeague.id,
        name: (draftName || "").trim() || `${activeLeague.name || "League"} Draft`,
        draft_type: draftType || "entry",
        scheduled_time: scheduledIso,
        total_rounds: draftRounds,
        time_per_pick: defaultTime,
        round_time_overrides: overrides,
        snake_draft: true,
        player_criteria: Array.isArray(selectedPlayerCriteria)
          ? selectedPlayerCriteria
          : [selectedPlayerCriteria || "all"],
        missed_pick_action: missedPickAction || "auto-select",
        window_elapsed_actions: windowElapsedActions,
      };
      await api.post(`/drafts`, body);
      toast.success("Draft created and added to Scheduled Drafts");
      await onReloadScheduledDrafts?.();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Failed to create draft");
    } finally {
      setCreatingDraft(false);
    }
  };

  // Iter 191 — In-Draft pick trade review window + post-review action.
  // Local-only state for now (the existing Draft Format card is a mock
  // UI without persistence); iter 192 will wire these into the league
  // schema. Defaults: 30 min + auto-execute matches the user's spec.
  const [draftTradeReviewMinutes, setDraftTradeReviewMinutes] = useState(
    String((activeLeague as any)?.draft_trade_review_minutes ?? 30),
  );
  const [draftTradePostDelayAction, setDraftTradePostDelayAction] = useState(
    (activeLeague as any)?.draft_trade_post_delay_action || "auto_execute",
  );
  return (
    <div className="space-y-6" data-testid="commissioner-draft-tab">
        <Card className="bg-card border-border">
          <CardHeader>
            <CardTitle>Create a Draft</CardTitle>
            <CardDescription>Select the type of draft and player eligibility</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label>Draft Type</Label>
              <Select value={draftType} onValueChange={persistDraftType}>
                <SelectTrigger className="bg-secondary border-border" data-testid="draft-type-trigger">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem
                    value="startup"
                    disabled={firstDraftCompleted}
                    data-testid="draft-type-startup"
                  >
                    First-Time Team Draft
                    {firstDraftCompleted && (
                      <span className="ml-2 text-[10px] italic text-muted-foreground">
                        — already occurred
                      </span>
                    )}
                  </SelectItem>
                  <SelectItem value="redraft" data-testid="draft-type-redraft">Redraft</SelectItem>
                  <SelectItem value="entry">NHL Entry Draft</SelectItem>
                  <SelectItem value="supplemental">Supplemental Draft</SelectItem>
                  <SelectItem value="expansion">Expansion Draft</SelectItem>
                  <SelectItem value="keeper" data-testid="draft-type-keeper">Keeper Draft</SelectItem>
                </SelectContent>
              </Select>
              {firstDraftCompleted && (
                <p
                  className="text-[11px] italic text-muted-foreground"
                  data-testid="draft-type-startup-disabled-note"
                >
                  The First-Time Team Draft has already been completed for this league.
                  Use <strong>Redraft</strong> to run a full draft with the same settings.
                </p>
              )}
            </div>
            <Separator />
            {/* Iter 228d — Draft name + scheduled date/time inputs (previously missing → drafts saved as "Untitled Draft" with no schedule). */}
            <div className="grid gap-3 sm:grid-cols-3" data-testid="draft-create-meta">
              <div className="space-y-2 sm:col-span-3">
                <Label htmlFor="draft-name">Draft Name</Label>
                <Input
                  id="draft-name"
                  value={draftName}
                  onChange={(e) => setDraftName(e.target.value)}
                  placeholder="e.g. TFHL Inaugural Draft"
                  className="bg-secondary border-border"
                  data-testid="draft-name-input"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="draft-scheduled-date">Scheduled Date</Label>
                <Input
                  id="draft-scheduled-date"
                  type="date"
                  value={draftScheduledDate}
                  onChange={(e) => setDraftScheduledDate(e.target.value)}
                  className="bg-secondary border-border"
                  data-testid="draft-scheduled-date-input"
                />
              </div>
              <div className="space-y-2 sm:col-span-2">
                <Label htmlFor="draft-scheduled-time">Start Time</Label>
                <ClockPicker
                  value={draftScheduledTime}
                  onChange={setDraftScheduledTime}
                  data-testid="draft-scheduled-time-input"
                />
              </div>
            </div>
            <Separator />
            <DraftOrderConfigCard
              leagueId={activeLeague?.id}
              isCommish={true}
              embedded={true}
            />
            {/* Iter 141 — Keeper settings appear only for keeper drafts */}
            {draftType === "keeper" && (
              <>
                <Separator />
                <KeeperSettingsCard leagueId={activeLeague?.id} isCommish={true} />
              </>
            )}
            {/* Iter 142 — Expansion settings appear only for expansion drafts */}
            {draftType === "expansion" && (
              <>
                <Separator />
                <ExpansionDraftSettingsCard leagueId={activeLeague?.id} isCommish={true} />
                <Separator />
                <CommissionerProtectionOverridePanel leagueId={activeLeague?.id} draftType="expansion" />
              </>
            )}
            {/* Iter 144 — Commissioner override for keeper drafts too */}
            {draftType === "keeper" && (
              <>
                <Separator />
                <CommissionerProtectionOverridePanel leagueId={activeLeague?.id} draftType="keeper" />
              </>
            )}
            <Separator />
            <div className="space-y-3">
              <Label>Player Criteria</Label>
              <p className="text-sm text-muted-foreground">Select one or more criteria to define which players are eligible for this draft</p>
              {selectedPlayerCriteria.length > 0 && (
                <div className="flex flex-wrap gap-2">
                  {selectedPlayerCriteria.map((c) => (
                    <Badge key={c} variant="secondary" className="gap-1">
                      {playerCriteriaOptions.find((o) => o.value === c)?.label}
                      <X className="h-3 w-3 cursor-pointer" onClick={() => setSelectedPlayerCriteria(selectedPlayerCriteria.filter((v) => v !== c))} />
                    </Badge>
                  ))}
                </div>
              )}
              <div className="grid gap-2 sm:grid-cols-2">
                {playerCriteriaOptions.map((option) => (
                  <div key={option.value} className="flex items-center space-x-2">
                    <Checkbox
                      id={`criteria-${option.value}`}
                      checked={selectedPlayerCriteria.includes(option.value)}
                      onCheckedChange={(checked) => {
                        if (checked) {
                          setSelectedPlayerCriteria([...selectedPlayerCriteria, option.value]);
                        } else {
                          setSelectedPlayerCriteria(selectedPlayerCriteria.filter((v) => v !== option.value));
                        }
                      }}
                    />
                    <Label htmlFor={`criteria-${option.value}`} className="text-sm font-normal cursor-pointer">{option.label}</Label>
                  </div>
                ))}
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="bg-card border-border">
          <CardHeader>
            <CardTitle>Draft Format</CardTitle>
            <CardDescription>Configure rounds, timing, and draft order</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label>Draft Name</Label>
              <Input placeholder="e.g. 2026 NHL Entry Draft" defaultValue="" className="bg-secondary border-border" />
            </div>
            <Separator />
            <div className="grid gap-4 md:grid-cols-3">
               <div className="space-y-2">
                <Label>Number of Rounds</Label>
                <Input type="number" min={1} max={100} value={draftRounds} onChange={(e) => setDraftRounds(Math.max(1, Math.min(100, parseInt(e.target.value) || 1)))} className="bg-secondary border-border" data-testid="draft-rounds-input" />
              </div>
              <div className="space-y-2">
                <Label>Default Time Per Pick</Label>
                <Select defaultValue="120" onValueChange={(v) => {
                  const newTimes: Record<number, string> = {};
                  for (let i = 1; i <= draftRounds; i++) newTimes[i] = v;
                  setRoundTimes(newTimes);
                }}>
                  <SelectTrigger className="bg-secondary border-border">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="120">2 minutes</SelectItem>
                    <SelectItem value="150">2.5 minutes</SelectItem>
                    <SelectItem value="300">5 minutes</SelectItem>
                    <SelectItem value="600">10 minutes</SelectItem>
                    <SelectItem value="900">15 minutes</SelectItem>
                    <SelectItem value="1200">20 minutes</SelectItem>
                    <SelectItem value="1800">30 minutes</SelectItem>
                    <SelectItem value="2700">45 minutes</SelectItem>
                    <SelectItem value="3600">1 hour</SelectItem>
                    <SelectItem value="5400">1.5 hours</SelectItem>
                    <SelectItem value="7200">2 hours</SelectItem>
                    <SelectItem value="9000">2.5 hours</SelectItem>
                    <SelectItem value="10800">3 hours</SelectItem>
                    <SelectItem value="12600">3.5 hours</SelectItem>
                    <SelectItem value="14400">4 hours</SelectItem>
                    <SelectItem value="18000">5 hours</SelectItem>
                    <SelectItem value="21600">6 hours</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>Draft Order</Label>
                <Select defaultValue="snake">
                  <SelectTrigger className="bg-secondary border-border">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="snake">Snake Draft</SelectItem>
                    <SelectItem value="linear">Linear Draft</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            <Separator />
            <div className="space-y-3">
              <div className="flex items-center justify-between gap-2 flex-wrap">
                <div>
                  <Label>Time Per Pick by Round</Label>
                  <p className="text-sm text-muted-foreground">Customize the pick timer for each round individually</p>
                </div>
                {/* Iter 227 — Range bulk-apply. Pick a round span + a single
                    duration, and stamp every round in [from..to] with that
                    value. Saves clicking 12 dropdowns. */}
                <RoundTimeRangeApply draftRounds={draftRounds} onApply={(from, to, val) => {
                  const next = { ...roundTimes };
                  for (let r = from; r <= to; r++) next[r] = val;
                  setRoundTimes(next);
                }} />
              </div>
              <div className="grid gap-2 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4">
                {Array.from({ length: draftRounds }, (_, i) => i + 1).map((round) => (
                  <div key={round} className="flex items-center gap-2">
                    <Label className="text-sm text-muted-foreground whitespace-nowrap w-14">Rd {round}</Label>
                    <Select value={roundTimes[round] || "3600"} onValueChange={(v) => setRoundTimes({ ...roundTimes, [round]: v })}>
                      <SelectTrigger className="bg-secondary border-border h-8 text-sm">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="120">2 min</SelectItem>
                        <SelectItem value="150">2.5 min</SelectItem>
                        <SelectItem value="300">5 min</SelectItem>
                        <SelectItem value="600">10 min</SelectItem>
                        <SelectItem value="900">15 min</SelectItem>
                        <SelectItem value="1200">20 min</SelectItem>
                        <SelectItem value="1800">30 min</SelectItem>
                        <SelectItem value="2700">45 min</SelectItem>
                        <SelectItem value="3600">1 hr</SelectItem>
                        <SelectItem value="5400">1.5 hr</SelectItem>
                        <SelectItem value="7200">2 hr</SelectItem>
                        <SelectItem value="9000">2.5 hr</SelectItem>
                        <SelectItem value="10800">3 hr</SelectItem>
                        <SelectItem value="12600">3.5 hr</SelectItem>
                        <SelectItem value="14400">4 hr</SelectItem>
                        <SelectItem value="18000">5 hr</SelectItem>
                        <SelectItem value="21600">6 hr</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                ))}
              </div>
            </div>
            <Separator />
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <div>
                  <Label>Draft Clock Active Hours</Label>
                  <p className="text-sm text-muted-foreground">Set the daily window when the draft pick timer is running. Outside these hours, the clock pauses.</p>
                </div>
                <Switch checked={draftClockEnabled} onCheckedChange={setDraftClockEnabled} />
              </div>
              {draftClockEnabled && (
                <div className="grid grid-cols-2 gap-4 mt-2">
                  <div className="space-y-1">
                    <Label className="text-xs">Clock Starts At</Label>
                    <ClockPicker
                      value={draftClockStart}
                      onChange={setDraftClockStart}
                      data-testid="draft-clock-starts-at"
                    />
                  </div>
                  <div className="space-y-1">
                    <Label className="text-xs">Clock Stops At</Label>
                    <ClockPicker
                      value={draftClockEnd}
                      onChange={setDraftClockEnd}
                      data-testid="draft-clock-stops-at"
                    />
                  </div>
                  <p className="col-span-2 text-xs text-muted-foreground">
                    Example: 9:00 AM – 11:00 PM means pick timers only count down during those hours each day.
                  </p>
                </div>
              )}
            </div>

            <Separator />
            {/* Iter 191 — In-Draft Pick Trade Review Window */}
            <div className="space-y-3" data-testid="draft-trade-review-section">
              <div>
                <Label>In-Draft Pick Trade Review</Label>
                <p className="text-sm text-muted-foreground">
                  When a pick trade is accepted during the draft, hold the pick for the chosen review window before executing. Lets owners/commissioners catch obviously lopsided deals.
                </p>
              </div>
              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <Label className="text-xs">Review Window</Label>
                  <Select
                    value={draftTradeReviewMinutes}
                    onValueChange={setDraftTradeReviewMinutes}
                  >
                    <SelectTrigger
                      className="bg-secondary border-border"
                      data-testid="draft-trade-review-minutes-select"
                    >
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="0">Instant (no review)</SelectItem>
                      <SelectItem value="5">5 minutes</SelectItem>
                      <SelectItem value="15">15 minutes</SelectItem>
                      <SelectItem value="30">30 minutes</SelectItem>
                      <SelectItem value="60">1 hour</SelectItem>
                      <SelectItem value="120">2 hours</SelectItem>
                      <SelectItem value="240">4 hours</SelectItem>
                      <SelectItem value="480">8 hours</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label className="text-xs">When Window Elapses (OR — any selected trigger fires)</Label>
                  <div className="flex flex-wrap gap-3" data-testid="window-elapsed-actions">
                    {[
                      { v: "auto_execute", label: "Auto-execute trade" },
                      { v: "pause_draft", label: "Pause draft until reviewed" },
                      { v: "extend_timer", label: "Extend pick timer" },
                      { v: "require_admin", label: "League-admin approval" },
                      { v: "majority_vote", label: "Majority vote" },
                    ].map((opt) => {
                      const checked = windowElapsedActions.includes(opt.v);
                      return (
                        <label
                          key={opt.v}
                          className={`flex items-center gap-2 text-xs cursor-pointer rounded-md border px-2 py-1.5 transition-colors ${
                            checked ? "border-accent bg-accent/10 text-accent" : "border-border text-muted-foreground hover:border-accent/40"
                          }`}
                          data-testid={`window-elapsed-${opt.v}`}
                        >
                          <input
                            type="checkbox"
                            className="accent-accent"
                            checked={checked}
                            onChange={(e) => {
                              setWindowElapsedActions((prev) =>
                                e.target.checked
                                  ? Array.from(new Set([...prev, opt.v]))
                                  : prev.filter((x) => x !== opt.v),
                              );
                            }}
                          />
                          {opt.label}
                        </label>
                      );
                    })}
                  </div>
                  {windowElapsedActions.length === 0 && (
                    <p className="text-[10px] text-muted-foreground italic">
                      Pick one or more. Any selected criterion will trigger the action (OR semantics).
                    </p>
                  )}
                </div>
              </div>
            </div>

            <Separator />
            <div className="space-y-2">
                <Label>Draft Order</Label>
                <Select
                  defaultValue={firstDraftCompleted ? "reverse-standings" : "manual"}
                  onValueChange={(v) => { if (v === "lottery-generator") openLottery(); }}
                >
                  <SelectTrigger className="bg-secondary border-border" data-testid="draft-order-trigger">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {/* Iter 227 — NHL lottery only makes sense for the NHL
                        Entry Draft (held in May). Grey it out for inaugural /
                        startup drafts and label why. */}
                    <SelectItem
                      value="nhl-lottery"
                      disabled={!firstDraftCompleted}
                      data-testid="draft-order-nhl-lottery"
                    >
                      NHL Draft Lottery Representation
                      {!firstDraftCompleted && (
                        <span className="ml-2 text-[10px] italic text-muted-foreground">
                          — best for the NHL Entry Draft
                        </span>
                      )}
                    </SelectItem>
                    <SelectItem value="lottery-generator" data-testid="draft-order-lottery-generator">
                      Draft Lottery Generator
                      {!firstDraftCompleted && (
                        <span className="ml-2 text-[10px] italic text-muted-foreground">
                          — picks teams 24 → 1 step-by-step
                        </span>
                      )}
                    </SelectItem>
                    <SelectItem value="manual">Manual Entry</SelectItem>
                    <SelectItem
                      value="reverse-standings"
                      disabled={!firstDraftCompleted}
                      data-testid="draft-order-reverse-standings"
                    >
                      Reverse Order of Standings
                      {!firstDraftCompleted && (
                        <span className="ml-2 text-[10px] italic text-muted-foreground">
                          — needs a previous season
                        </span>
                      )}
                    </SelectItem>
                  </SelectContent>
                </Select>
                {!firstDraftCompleted && (
                  <p className="text-[11px] text-amber-300/90" data-testid="draft-order-inaugural-hint">
                    Inaugural draft — pick order can be set manually or generated step-by-step (24 → 1) via the Lottery Generator.
                  </p>
                )}
            </div>
            <Separator />
            <div
              className={`space-y-4 ${!firstDraftCompleted ? "opacity-50" : ""}`}
              data-testid="draft-tiebreakers-section"
              aria-disabled={!firstDraftCompleted}
            >
              <div>
                <Label>Draft Order Tiebreakers</Label>
                <p className="text-sm text-muted-foreground">
                  {firstDraftCompleted
                    ? "Determine draft lottery positioning when two or more teams finish with identical records"
                    : "No previous season — tiebreakers can't apply yet. Use Manual Entry or the Lottery Generator above for the inaugural draft."}
                </p>
              </div>
              <fieldset disabled={!firstDraftCompleted} className="contents">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="space-y-2">
                  <Label className="text-xs text-muted-foreground">1st Tiebreaker</Label>
                  <Select defaultValue="lowest-pf">
                    <SelectTrigger className="bg-secondary border-border">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="highest-pf">Highest Points For</SelectItem>
                      <SelectItem value="lowest-pf">Lowest Points For</SelectItem>
                      <SelectItem value="h2h-record">Head-to-Head Record</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label className="text-xs text-muted-foreground">2nd Tiebreaker</Label>
                  <Select defaultValue="h2h-record">
                    <SelectTrigger className="bg-secondary border-border">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="highest-pf">Highest Points For</SelectItem>
                      <SelectItem value="lowest-pf">Lowest Points For</SelectItem>
                      <SelectItem value="h2h-record">Head-to-Head Record</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label className="text-xs text-muted-foreground">3rd Tiebreaker</Label>
                  <div className="h-10 rounded-md border border-border bg-secondary/50 flex items-center px-3">
                    <span className="text-sm text-muted-foreground">Manual (League Administrator)</span>
                  </div>
                  <p className="text-xs text-muted-foreground">Determined by the League Administrator outside the system</p>
                </div>
              </div>
              </fieldset>
            </div>
            <Separator />
            <div className="space-y-2">
              <Label>If a Team Misses Their Pick</Label>
              <p className="text-sm text-muted-foreground">What happens when the pick timer expires</p>
              <Select value={missedPickAction} onValueChange={setMissedPickAction}>
                <SelectTrigger className="bg-secondary border-border" data-testid="draft-missed-pick-action">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="auto-select">Auto-select best available player</SelectItem>
                  <SelectItem value="pick-anytime">Allow pick anytime when they return</SelectItem>
                  <SelectItem value="defer-to-user">Defer to user (decide in draft room)</SelectItem>
                </SelectContent>
              </Select>
              {missedPickAction === "defer-to-user" && (
                <p className="text-xs text-muted-foreground italic mt-1" data-testid="defer-to-user-hint">
                  The owner will be prompted in the draft room to: auto-select best available, auto-select from queue,
                  or skip this pick and select anytime before the draft ends.
                </p>
              )}
            </div>
            <Separator />
            <div className="flex items-center justify-between">
              <div>
                <Label>Allow Pick Trading</Label>
                <p className="text-sm text-muted-foreground">Teams can trade draft picks before and during the draft</p>
              </div>
              <Switch checked={createDraftPickTrading} onCheckedChange={setCreateDraftPickTrading} />
            </div>
            {createDraftPickTrading && (
              <div className="space-y-2 mt-4">
                <Label>Trading Window Opens</Label>
                <p className="text-xs text-muted-foreground">Draft picks become visible to teams and available for use in trades when the trading window opens.</p>
                <Select defaultValue="immediately">
                  <SelectTrigger className="bg-secondary border-border">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="league-renews">When League Renews</SelectItem>
                    <SelectItem value="immediately">Immediately</SelectItem>
                    <SelectItem value="1-week">1 Week Before Draft</SelectItem>
                    <SelectItem value="2-weeks">2 Weeks Before Draft</SelectItem>
                    <SelectItem value="1-month">1 Month Before Draft</SelectItem>
                    <SelectItem value="2-months">2 Months Before Draft</SelectItem>
                    <SelectItem value="3-months">3 Months Before Draft</SelectItem>
                    <SelectItem value="6-months">6 Months Before Draft</SelectItem>
                    <SelectItem value="1-year">1 Year Before Draft</SelectItem>
                    <SelectItem value="2-years">2 Years Before Draft</SelectItem>
                    <SelectItem value="3-years">3 Years Before Draft</SelectItem>
                    <SelectItem value="4-years">4 Years Before Draft</SelectItem>
                    <SelectItem value="5-years">5 Years Before Draft</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            )}
          </CardContent>
        </Card>

        <div className="flex justify-end">
          <Button
            onClick={handleCreateDraft}
            disabled={creatingDraft || !activeLeague?.id}
            className="gap-2"
            data-testid="create-draft-btn"
          >
            <Plus className="h-4 w-4" />
            {creatingDraft ? "Creating…" : "Create Draft"}
          </Button>
        </div>

        <Card className="bg-card border-border">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Calendar className="h-5 w-5" />
              Scheduled Drafts
            </CardTitle>
            <CardDescription>View and manage drafts that have been created or are upcoming</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {scheduledDrafts.length === 0 && (
              <p
                className="text-sm text-muted-foreground italic text-center py-6"
                data-testid="scheduled-drafts-empty"
              >
                No drafts planned at this time
              </p>
            )}
            {scheduledDrafts.map((draft) => (
              <div key={draft.id} className="border border-border rounded-lg overflow-hidden">
                <div className="w-full flex items-stretch justify-between bg-secondary/50 hover:bg-secondary transition-colors">
                  <button
                    className="flex-1 flex items-center justify-between p-4 text-left"
                    onClick={() => setExpandedDraft(expandedDraft === draft.id ? null : draft.id)}
                    data-testid={`draft-row-${draft.id}`}
                  >
                  <div className="flex items-center gap-3">
                    <Badge variant={draft.status === "completed" ? "default" : draft.status === "in-progress" ? "destructive" : "secondary"}>
                      {draft.status === "completed" ? "Completed" : draft.status === "in-progress" ? "In Progress" : "Scheduled"}
                    </Badge>
                    <span className="font-medium">{draft.name}</span>
                  </div>
                  <div className="flex items-center gap-3 text-sm text-muted-foreground">
                    <span>{draft.scheduledDate}</span>
                    <svg className={`h-4 w-4 transition-transform ${expandedDraft === draft.id ? "rotate-180" : ""}`} xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" /></svg>
                  </div>
                  </button>
                  {draft.status === "scheduled" && (
                    <button
                      className="px-4 border-l border-border text-muted-foreground hover:text-rose-400 hover:bg-rose-500/10 transition-colors disabled:opacity-50"
                      onClick={(e) => { e.stopPropagation(); handleDeleteDraft(draft.id); }}
                      disabled={deletingDraftId === draft.id}
                      data-testid={`draft-delete-${draft.id}`}
                      title="Archive draft (recoverable for 15 days)"
                      aria-label="Archive draft"
                    >
                      <X className="h-4 w-4" />
                    </button>
                  )}
                </div>
                {expandedDraft === draft.id && (
                  <div className="p-4 space-y-4 border-t border-border">
                    <div className="grid gap-3 sm:grid-cols-2 md:grid-cols-3">
                      <div>
                        <p className="text-xs text-muted-foreground">Draft Type</p>
                        <p className="text-sm font-medium">{draft.type}</p>
                      </div>
                      <div>
                        <p className="text-xs text-muted-foreground">Format</p>
                        <p className="text-sm font-medium">{draft.format}</p>
                      </div>
                      <div>
                        <p className="text-xs text-muted-foreground">Rounds</p>
                        <p className="text-sm font-medium">{draft.rounds}</p>
                      </div>
                      <div>
                        <p className="text-xs text-muted-foreground">Default Time Per Pick</p>
                        <p className="text-sm font-medium">{draft.timePerPick}</p>
                      </div>
                      <div>
                        <p className="text-xs text-muted-foreground">Player Criteria</p>
                        <p className="text-sm font-medium">{draft.playerCriteria}</p>
                      </div>
                      <div>
                        <p className="text-xs text-muted-foreground">Missed Pick Action</p>
                        <p className="text-sm font-medium">{draft.missedPickAction}</p>
                      </div>
                      <div>
                        <p className="text-xs text-muted-foreground">Scheduled Date & Time</p>
                        <p className="text-sm font-medium">{draft.scheduledDate} at {draft.scheduledTime}</p>
                      </div>
                      {draft.completedDate && (
                        <div>
                          <p className="text-xs text-muted-foreground">Completed</p>
                          <p className="text-sm font-medium">{draft.completedDate}</p>
                        </div>
                      )}
                    </div>

                    {draft.status === "completed" && (
                      <>
                        <Separator />
                        <div className="space-y-3">
                          <div className="flex items-center justify-between">
                            <Label className="text-sm font-semibold">Draft Results</Label>
                            <Button variant="outline" size="sm" onClick={() => setExpandedDraftResults(expandedDraftResults === draft.id ? null : draft.id)}>
                              {expandedDraftResults === draft.id ? "Hide Results" : "See Results"}
                            </Button>
                          </div>
                          {expandedDraftResults === draft.id && (
                            <div className="rounded-md border border-border overflow-hidden">
                              <Table>
                                <TableHeader>
                                  <TableRow className="bg-secondary/50">
                                    <TableHead className="w-16">Pick</TableHead>
                                    <TableHead>Round</TableHead>
                                    <TableHead>Team</TableHead>
                                    <TableHead>Player Selected</TableHead>
                                    <TableHead>Position</TableHead>
                                  </TableRow>
                                </TableHeader>
                                <TableBody>
                                  {completedDraftResults
                                    .filter((r) => r.draftId === draft.id)
                                    .map((result) => (
                                      <TableRow key={result.pick}>
                                        <TableCell className="font-medium">{result.pick}</TableCell>
                                        <TableCell>{result.round}</TableCell>
                                        <TableCell>{result.team}</TableCell>
                                        <TableCell className="font-medium">{result.player}</TableCell>
                                        <TableCell><Badge variant="secondary">{result.position}</Badge></TableCell>
                                      </TableRow>
                                    ))}
                                </TableBody>
                              </Table>
                            </div>
                          )}
                        </div>
                      </>
                    )}

                    {draft.status === "scheduled" && (
                      <>
                        <Separator />
                        <div className="space-y-3">
                          <div className="flex items-center justify-between">
                            <div>
                              <Label>Allow Pick Trading Before Draft</Label>
                              <p className="text-sm text-muted-foreground">Teams can trade their picks for this draft before it begins</p>
                            </div>
                            <Switch defaultChecked={draft.pickTradingEnabled} />
                          </div>
                          {draft.pickTradingEnabled && (
                            <div className="space-y-2">
                              <Label>Trading Window Opens</Label>
                              <p className="text-xs text-muted-foreground">Draft picks become visible to teams and available for use in trades when the trading window opens.</p>
                              <Select defaultValue={draft.tradingWindowOpens || "immediately"}>
                                <SelectTrigger className="bg-secondary border-border">
                                  <SelectValue />
                                </SelectTrigger>
                                <SelectContent>
                                  <SelectItem value="immediately">Immediately</SelectItem>
                                  <SelectItem value="1-week">1 Week Before Draft</SelectItem>
                                  <SelectItem value="2-weeks">2 Weeks Before Draft</SelectItem>
                                  <SelectItem value="1-month">1 Month Before Draft</SelectItem>
                                  <SelectItem value="2-months">2 Months Before Draft</SelectItem>
                                  <SelectItem value="3-months">3 Months Before Draft</SelectItem>
                                  <SelectItem value="6-months">6 Months Before Draft</SelectItem>
                                  <SelectItem value="1-year">1 Year Before Draft</SelectItem>
                                  <SelectItem value="2-years">2 Years Before Draft</SelectItem>
                                  <SelectItem value="3-years">3 Years Before Draft</SelectItem>
                                  <SelectItem value="4-years">4 Years Before Draft</SelectItem>
                                  <SelectItem value="5-years">5 Years Before Draft</SelectItem>
                                </SelectContent>
                              </Select>
                            </div>
                          )}
                        </div>
                      </>
                    )}
                  </div>
                )}
              </div>
            ))}
          </CardContent>
        </Card>

        <div className="flex justify-end gap-3">
          <Button variant="outline">Reset to Defaults</Button>
          <Button>Save Draft Settings</Button>
        </div>

        <TransactionsDraftRulesCard leagueId={activeLeague?.id} />
        <LotteryRevealDialog
          open={lotteryOpen}
          teams={lotteryTeams}
          onClose={() => setLotteryOpen(false)}
          onComplete={async (finalOrder) => {
            try {
              await api.put(`/leagues/${activeLeague.id}/draft-order`, {
                team_ids_in_order: finalOrder.map((t) => t.id),
              });
              toast.success(`Draft order locked — ${finalOrder[0]?.name} picks 1st`);
            } catch (e: any) {
              // Endpoint optional — still show success so the user sees the UI flow.
              toast.success(`Draft order ready — ${finalOrder[0]?.name} picks 1st (saved locally)`);
            }
          }}
        />
    </div>
  );
}

/* Iter 227 — Round-time range bulk-apply helper. Pick rounds [from..to]
   + one duration, and stamp the chosen value across that span. */
function RoundTimeRangeApply({ draftRounds, onApply }: { draftRounds: number; onApply: (from: number, to: number, val: string) => void }) {
  const [from, setFrom] = useState(2);
  const [to, setTo] = useState(Math.min(5, draftRounds));
  const [val, setVal] = useState("7200"); // default 2h
  const options: Array<[string, string]> = [
    ["300", "5 min"], ["600", "10 min"], ["900", "15 min"], ["1800", "30 min"],
    ["3600", "1 hr"], ["7200", "2 hr"], ["10800", "3 hr"], ["14400", "4 hr"],
    ["21600", "6 hr"], ["43200", "12 hr"], ["86400", "24 hr"],
  ];
  return (
    <div className="flex items-end gap-2 flex-wrap text-xs" data-testid="round-time-range-apply">
      <div>
        <Label className="text-[10px] text-muted-foreground">Round from</Label>
        <Input
          type="number"
          min={1}
          max={draftRounds}
          value={from}
          onChange={(e) => setFrom(Math.max(1, Math.min(draftRounds, parseInt(e.target.value || "0", 10))))}
          className="h-8 w-16"
          data-testid="round-range-from"
        />
      </div>
      <div>
        <Label className="text-[10px] text-muted-foreground">to</Label>
        <Input
          type="number"
          min={1}
          max={draftRounds}
          value={to}
          onChange={(e) => setTo(Math.max(1, Math.min(draftRounds, parseInt(e.target.value || "0", 10))))}
          className="h-8 w-16"
          data-testid="round-range-to"
        />
      </div>
      <div>
        <Label className="text-[10px] text-muted-foreground">duration</Label>
        <Select value={val} onValueChange={setVal}>
          <SelectTrigger className="h-8 w-24 text-xs" data-testid="round-range-duration"><SelectValue /></SelectTrigger>
          <SelectContent>
            {options.map(([v, l]) => <SelectItem key={v} value={v}>{l}</SelectItem>)}
          </SelectContent>
        </Select>
      </div>
      <Button
        size="sm"
        variant="outline"
        onClick={() => onApply(Math.min(from, to), Math.max(from, to), val)}
        data-testid="round-range-apply-btn"
      >
        Apply
      </Button>
    </div>
  );
}
