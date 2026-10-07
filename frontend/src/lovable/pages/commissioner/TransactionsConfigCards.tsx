// @ts-nocheck
/**
 * Iter 117 — League Administration → Transactions configuration cards.
 *
 * Renders four cards (Claims Limits, Claim Rules, Free Agency, Waiver Wire)
 * plus a `<TransactionsDraftRulesCard>` exposed to the Draft tab. All cards
 * read/write a single `/api/leagues/{id}/transactions-config` envelope.
 *
 * The Free Agency card has the richest sub-flow: when system_type is
 * `manual_priority` the LM gets a drag-and-drop team list plus an optional
 * scheduled rotation editor (multiple windows with their own ordered
 * teams). Other system_types collapse those controls.
 */
import { useEffect, useMemo, useState } from "react";
import { ChevronUp, ChevronDown, GripVertical, Plus, Save, Loader2, Trash2 } from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { ClockPicker } from "@/components/ui/clock-picker";
import { Switch } from "@/components/ui/switch";
import { Checkbox } from "@/components/ui/checkbox";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Separator } from "@/components/ui/separator";
import InfoHint from "@/components/ui/info-hint";

const DAY_LABELS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

import { DEFAULT_CFG, useTransactionsConfig, ClaimsLimitsCard } from "./TransactionClaims";
export { useTransactionsConfig, ClaimsLimitsCard } from "./TransactionClaims";

/* ───────────── Claim Rules card ──────────────────────────────────── */

export function ClaimRulesCard({ cfg, setCfg }) {
  const set = (key) => (val) =>
    setCfg((prev) => ({ ...prev, claim_rules: { ...prev.claim_rules, [key]: val } }));

  return (
    <Card className="bg-card border-border" data-testid="transactions-claim-rules-card">
      <CardHeader>
        <CardTitle>
          Claim & Drop Rules
          <InfoHint
            testId="info-claim-rules"
            text="Universal guardrails on roster moves. These apply whether the team is grabbing a free agent or winning a waiver claim."
          />
        </CardTitle>
        <CardDescription>
          Universal rules across both free-agency and waiver flows.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="flex items-center gap-3">
          <Switch
            checked={cfg.claim_rules.lock_at_first_game}
            onCheckedChange={set("lock_at_first_game")}
            id="lock-first-game"
            data-testid="rule-lock-at-first-game"
          />
          <Label htmlFor="lock-first-game" className="cursor-pointer">
            Lock claims/drops at first game of the day
            <InfoHint
              testId="info-lock-at-first-game"
              text="Once the day's first NHL puck drops, every roster locks until tomorrow. Prevents owners from yanking starters mid-night."
            />
          </Label>
        </div>

        <div className="flex items-center gap-3">
          <Switch
            checked={cfg.claim_rules.allow_non_playoff_teams_claims}
            onCheckedChange={set("allow_non_playoff_teams_claims")}
            id="allow-non-playoff"
            data-testid="rule-allow-non-playoff"
          />
          <Label htmlFor="allow-non-playoff" className="cursor-pointer">
            Allow teams not in playoffs to make claims/drops
            <InfoHint
              testId="info-allow-non-playoff"
              text="When OFF, only teams active in the league playoffs can transact. Common in dynasty leagues to stop bottom teams from dumping for next year mid-postseason."
            />
          </Label>
        </div>

        <div className="space-y-2">
          <Label className="text-sm">
            Prevent claims for injured players
            <InfoHint
              testId="info-prevent-injured"
              text="OFF = always allowed. NHL IR = block adds for players on the team's IR. All Flags = block adds for any flagged status (IR, DTD, suspended, healthy scratch)."
            />
          </Label>
          <RadioGroup
            value={cfg.claim_rules.prevent_injured}
            onValueChange={set("prevent_injured")}
            className="flex flex-wrap gap-4"
            data-testid="rule-prevent-injured-group"
          >
            <label className="flex items-center gap-2 cursor-pointer text-sm">
              <RadioGroupItem value="off" data-testid="rule-prevent-injured-off" /> Off (allow all)
            </label>
            <label className="flex items-center gap-2 cursor-pointer text-sm">
              <RadioGroupItem value="any" data-testid="rule-prevent-injured-any" /> Yes — any injury
            </label>
            <label className="flex items-center gap-2 cursor-pointer text-sm">
              <RadioGroupItem value="nhl_ir" data-testid="rule-prevent-injured-ir" /> NHL IR list only
            </label>
            <label className="flex items-center gap-2 cursor-pointer text-sm">
              <RadioGroupItem value="all_flags" data-testid="rule-prevent-injured-flags" /> All players with injury flags
            </label>
          </RadioGroup>
        </div>

        <div className="flex items-center gap-3">
          <Switch
            checked={cfg.claim_rules.prevent_minors}
            onCheckedChange={set("prevent_minors")}
            id="prevent-minors"
            data-testid="rule-prevent-minors"
          />
          <Label htmlFor="prevent-minors" className="cursor-pointer">
            Prevent claims for minor-league players
          </Label>
        </div>

        <Separator />

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <VisibilityRadio
            label="Pending claims/drops viewable by"
            value={cfg.claim_rules.pending_visibility}
            onChange={set("pending_visibility")}
            testId="rule-pending-visibility"
          />
          <VisibilityRadio
            label="Failed claims/drops viewable by"
            value={cfg.claim_rules.failed_visibility}
            onChange={set("failed_visibility")}
            testId="rule-failed-visibility"
          />
        </div>
      </CardContent>
    </Card>
  );
}

function VisibilityRadio({ label, value, onChange, testId }) {
  return (
    <div className="space-y-2">
      <Label className="text-sm">{label}</Label>
      <RadioGroup value={value} onValueChange={onChange} className="flex flex-col gap-2" data-testid={`${testId}-group`}>
        <label className="flex items-center gap-2 cursor-pointer text-sm">
          <RadioGroupItem value="user" data-testid={`${testId}-user`} /> Only the team owner
        </label>
        <label className="flex items-center gap-2 cursor-pointer text-sm">
          <RadioGroupItem value="all_teams" data-testid={`${testId}-all`} /> All teams in the league
        </label>
        <label className="flex items-center gap-2 cursor-pointer text-sm">
          <RadioGroupItem value="league_admin" data-testid={`${testId}-admin`} /> League Admin only
        </label>
      </RadioGroup>
    </div>
  );
}

/* ───────────── Free Agency card ──────────────────────────────────── */

export function FreeAgencyCard({ cfg, setCfg, leagueTeams }) {
  const fa = cfg.free_agency;
  const set = (key) => (val) =>
    setCfg((prev) => ({ ...prev, free_agency: { ...prev.free_agency, [key]: val } }));

  // Auto-seed manual_priority_order with all teams when switching to manual
  useEffect(() => {
    if (fa.system_type === "manual_priority" && fa.manual_priority_order.length === 0 && (leagueTeams || []).length > 0) {
      set("manual_priority_order")(leagueTeams.map((t) => t.id));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fa.system_type, leagueTeams?.length]);

  const moveOrder = (idx, dir) => {
    const next = [...fa.manual_priority_order];
    const swap = idx + dir;
    if (swap < 0 || swap >= next.length) return;
    [next[idx], next[swap]] = [next[swap], next[idx]];
    set("manual_priority_order")(next);
  };

  const teamName = (id) => (leagueTeams || []).find((t) => t.id === id)?.name || id;

  const addScheduleRow = () => {
    set("manual_priority_schedule")([
      ...fa.manual_priority_schedule,
      {
        starts_on: new Date().toISOString().slice(0, 10),
        ends_on: new Date(Date.now() + 30 * 86400000).toISOString().slice(0, 10),
        team_order: (leagueTeams || []).map((t) => t.id),
      },
    ]);
  };

  return (
    <Card className="bg-card border-border" data-testid="transactions-free-agency-card">
      <CardHeader>
        <CardTitle>
          Free Agency
          <InfoHint
            testId="info-free-agency"
            text="How free-agent acquisitions are processed. Open = first-come-first-served, no waiting; Bidding = blind FAAB bids; Priority Order = highest-priority team wins."
          />
        </CardTitle>
        <CardDescription>
          How free-agent pickups are processed in this league.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="space-y-2">
          <Label className="text-sm">Free Agent System Type</Label>
          <RadioGroup
            value={fa.system_type}
            onValueChange={set("system_type")}
            className="grid grid-cols-1 md:grid-cols-2 gap-2"
            data-testid="fa-system-type-group"
          >
            <label className="flex items-start gap-2 cursor-pointer text-sm rounded-md border border-border p-3">
              <RadioGroupItem value="open" data-testid="fa-system-open" />
              <span><strong>Open</strong> — free-for-all, first come first served</span>
            </label>
            <label className="flex items-start gap-2 cursor-pointer text-sm rounded-md border border-border p-3">
              <RadioGroupItem value="auto_priority" data-testid="fa-system-auto" />
              <span>
                <strong>Automated Priority Order</strong> — An automated system that determines waiver claim priority. When claims process, players are awarded based on a fixed order — once you claim a player, you drop to the bottom of the priority list.
              </span>
            </label>
            <label className="flex items-start gap-2 cursor-pointer text-sm rounded-md border border-border p-3">
              <RadioGroupItem value="manual_priority" data-testid="fa-system-manual" />
              <span><strong>Manual Priority Order</strong> — LM-selected ordered list</span>
            </label>
            <label className="flex items-start gap-2 cursor-pointer text-sm rounded-md border border-border p-3">
              <RadioGroupItem value="bidding" data-testid="fa-system-bidding" />
              <span><strong>Bidding</strong> — FAAB-style blind bidding</span>
            </label>
          </RadioGroup>
        </div>

        {fa.system_type === "auto_priority" && (
          <div className="rounded-md border border-border p-4 space-y-3" data-testid="fa-auto-priority-block">
            <div className="space-y-2">
              <Label className="text-sm">Priority basis</Label>
              <RadioGroup value={fa.auto_priority_basis} onValueChange={set("auto_priority_basis")} className="flex flex-col gap-2">
                <label className="flex items-center gap-2 cursor-pointer text-sm">
                  <RadioGroupItem value="reverse_live" data-testid="fa-auto-reverse-live" />
                  Reverse order of live standings
                </label>
                <label className="flex items-center gap-2 cursor-pointer text-sm">
                  <RadioGroupItem value="reverse_prev" data-testid="fa-auto-reverse-prev" />
                  Reverse order of previous year's standings (defaults to live in year 1)
                </label>
                <label className="flex items-center gap-2 cursor-pointer text-sm">
                  <RadioGroupItem value="random" data-testid="fa-auto-random" /> Random
                </label>
                <label className="flex items-center gap-2 cursor-pointer text-sm">
                  <RadioGroupItem value="manual" data-testid="fa-auto-manual" /> Manual Entry (LM ordered list)
                </label>
              </RadioGroup>
            </div>
            <div className="space-y-2">
              <Label className="text-sm">Priority recompute</Label>
              <RadioGroup value={fa.priority_recompute_cadence} onValueChange={set("priority_recompute_cadence")} className="flex gap-4">
                <label className="flex items-center gap-2 cursor-pointer text-sm">
                  <RadioGroupItem value="live" data-testid="fa-priority-live" /> Live (recompute on every claim)
                </label>
                <label className="flex items-center gap-2 cursor-pointer text-sm">
                  <RadioGroupItem value="weekly" data-testid="fa-priority-weekly" /> Frozen weekly (Mon 00:00)
                </label>
              </RadioGroup>
            </div>
          </div>
        )}

        {fa.system_type === "manual_priority" && (
          <div className="rounded-md border border-border p-4 space-y-4" data-testid="fa-manual-priority-block">
            <div className="space-y-2">
              <Label className="text-sm flex items-center">
                Duration
                <InfoHint
                  testId="info-manual-priority-duration"
                  text="One-off: commissioner sets the order ONCE; after the first set of claims is processed, the league reverts to the Automated Priority Order. 1 Month / 3 Months: the manual order stays in effect for that rolling window, then auto-reverts. Full Season: the manual order remains in effect for the entire regular season."
                />
              </Label>
              <RadioGroup value={fa.manual_priority_duration} onValueChange={set("manual_priority_duration")} className="grid grid-cols-2 md:grid-cols-4 gap-2">
                <label className="flex items-center gap-2 cursor-pointer text-sm">
                  <RadioGroupItem value="one_off" data-testid="fa-manual-one-off" /> One-off
                </label>
                <label className="flex items-center gap-2 cursor-pointer text-sm">
                  <RadioGroupItem value="month" data-testid="fa-manual-month" /> 1 Month
                </label>
                <label className="flex items-center gap-2 cursor-pointer text-sm">
                  <RadioGroupItem value="three_month" data-testid="fa-manual-three-month" /> 3 Months
                </label>
                <label className="flex items-center gap-2 cursor-pointer text-sm">
                  <RadioGroupItem value="season" data-testid="fa-manual-season" /> Full Season
                </label>
              </RadioGroup>
            </div>

            <div className="space-y-2">
              <Label className="text-sm">Priority order (highest priority first)</Label>
              <div className="rounded-md border border-border max-h-72 overflow-y-auto" data-testid="fa-manual-order-list">
                {fa.manual_priority_order.length === 0 ? (
                  <div className="text-sm text-muted-foreground italic p-3">No teams yet — switch to manual priority to seed automatically.</div>
                ) : fa.manual_priority_order.map((tid, idx) => (
                  <div key={tid} className="flex items-center justify-between gap-2 p-2 border-b border-border last:border-0" data-testid={`fa-manual-row-${idx}`}>
                    <div className="flex items-center gap-2">
                      <GripVertical className="h-4 w-4 text-muted-foreground" />
                      <span className="text-xs text-muted-foreground w-6">{idx + 1}.</span>
                      <span className="text-sm font-medium">{teamName(tid)}</span>
                    </div>
                    <div className="flex gap-1">
                      <Button size="icon" variant="ghost" className="h-7 w-7" onClick={() => moveOrder(idx, -1)} disabled={idx === 0} data-testid={`fa-manual-up-${idx}`}>
                        <ChevronUp className="h-4 w-4" />
                      </Button>
                      <Button size="icon" variant="ghost" className="h-7 w-7" onClick={() => moveOrder(idx, +1)} disabled={idx === fa.manual_priority_order.length - 1} data-testid={`fa-manual-down-${idx}`}>
                        <ChevronDown className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Label className="text-sm">Scheduled rotation windows (optional)</Label>
                <Button size="sm" variant="outline" onClick={addScheduleRow} className="gap-1" data-testid="fa-manual-schedule-add">
                  <Plus className="h-3 w-3" /> Add window
                </Button>
              </div>
              {(fa.manual_priority_schedule || []).length === 0 ? (
                <p className="text-xs text-muted-foreground italic">Use the base order above for the whole duration, or add windows with their own ordered teams.</p>
              ) : (
                <div className="space-y-2">
                  {fa.manual_priority_schedule.map((row, idx) => (
                    <ScheduleRow
                      key={idx}
                      row={row}
                      idx={idx}
                      onChange={(next) => {
                        const arr = [...fa.manual_priority_schedule];
                        arr[idx] = next;
                        set("manual_priority_schedule")(arr);
                      }}
                      onRemove={() => set("manual_priority_schedule")(
                        fa.manual_priority_schedule.filter((_, i) => i !== idx),
                      )}
                      leagueTeams={leagueTeams}
                      teamName={teamName}
                    />
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        <Separator />

        <div className="space-y-2">
          <Label className="text-sm">Waiver-wire pick policy (when multiple claims succeed)</Label>
          <RadioGroup value={fa.picks_per_round_policy} onValueChange={set("picks_per_round_policy")} className="flex flex-col gap-2">
            <label className="flex items-start gap-2 cursor-pointer text-sm">
              <RadioGroupItem value="top_then_next" data-testid="fa-policy-top-then-next" />
              <span>1st team gets their <strong>top selected</strong> player, then the 2nd team's top, and so on</span>
            </label>
            <label className="flex items-start gap-2 cursor-pointer text-sm">
              <RadioGroupItem value="all_then_next" data-testid="fa-policy-all-then-next" />
              <span>1st team gets <strong>all selected</strong> players, then the 2nd team gets all of theirs</span>
            </label>
          </RadioGroup>
        </div>

        <div className="flex items-center gap-3">
          <Switch
            checked={fa.waivers_reset_after_claim}
            onCheckedChange={set("waivers_reset_after_claim")}
            id="waivers-reset"
            data-testid="fa-waivers-reset"
          />
          <Label htmlFor="waivers-reset" className="cursor-pointer text-sm">
            Waiver-wire priority resets after claim (winning team drops to lowest priority)
          </Label>
        </div>
      </CardContent>
    </Card>
  );
}

function ScheduleRow({ row, idx, onChange, onRemove, leagueTeams, teamName }) {
  const move = (i, dir) => {
    const arr = [...row.team_order];
    const swap = i + dir;
    if (swap < 0 || swap >= arr.length) return;
    [arr[i], arr[swap]] = [arr[swap], arr[i]];
    onChange({ ...row, team_order: arr });
  };

  return (
    <div className="rounded-md border border-border p-3 space-y-2" data-testid={`fa-manual-schedule-row-${idx}`}>
      <div className="flex items-center gap-2 flex-wrap">
        <Input
          type="date"
          value={row.starts_on}
          onChange={(e) => onChange({ ...row, starts_on: e.target.value })}
          className="bg-secondary border-border w-44 h-8 text-xs"
          data-testid={`fa-manual-schedule-${idx}-start`}
        />
        <span className="text-xs text-muted-foreground">to</span>
        <Input
          type="date"
          value={row.ends_on}
          onChange={(e) => onChange({ ...row, ends_on: e.target.value })}
          className="bg-secondary border-border w-44 h-8 text-xs"
          data-testid={`fa-manual-schedule-${idx}-end`}
        />
        <div className="flex-1" />
        <Button size="icon" variant="ghost" onClick={onRemove} className="h-7 w-7 text-rose-400" data-testid={`fa-manual-schedule-${idx}-remove`}>
          <Trash2 className="h-4 w-4" />
        </Button>
      </div>
      <div className="border border-border rounded max-h-44 overflow-y-auto">
        {row.team_order.map((tid, i) => (
          <div key={tid} className="flex items-center justify-between gap-2 px-2 py-1 border-b border-border last:border-0">
            <div className="flex items-center gap-2">
              <span className="text-xs text-muted-foreground w-5">{i + 1}.</span>
              <span className="text-xs">{teamName(tid)}</span>
            </div>
            <div className="flex gap-1">
              <Button size="icon" variant="ghost" className="h-6 w-6" onClick={() => move(i, -1)} disabled={i === 0}><ChevronUp className="h-3 w-3" /></Button>
              <Button size="icon" variant="ghost" className="h-6 w-6" onClick={() => move(i, +1)} disabled={i === row.team_order.length - 1}><ChevronDown className="h-3 w-3" /></Button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ───────────── Waiver Wire card ──────────────────────────────────── */

function WaiverLimitField({ label, value, onChange, error, testId }) {
  const unlimited = value === null || value === undefined || value === "";
  return (
    <div className="space-y-1.5">
      <Label className="text-xs">{label}</Label>
      <div className="flex items-center gap-2">
        <Select
          value={unlimited ? "unlimited" : "limited"}
          onValueChange={(v) => onChange(v === "unlimited" ? null : (value ?? 1))}
        >
          <SelectTrigger className="bg-secondary border-border w-32 h-8" data-testid={`${testId}-mode`}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent className="bg-popover border-border z-50">
            <SelectItem value="unlimited">Unlimited</SelectItem>
            <SelectItem value="limited">Limited…</SelectItem>
          </SelectContent>
        </Select>
        {!unlimited && (
          <Input
            type="number" min={1} max={500}
            value={value ?? ""}
            onChange={(e) => {
              const raw = e.target.value;
              if (raw === "") return onChange(null);
              const n = Math.min(Math.max(parseInt(raw, 10) || 0, 1), 500);
              onChange(n);
            }}
            className={`bg-secondary border-border w-24 h-8 ${error ? "border-rose-500" : ""}`}
            data-testid={`${testId}-input`}
          />
        )}
      </div>
      {error && (
        <p className="text-[10px] text-rose-400" data-testid={`${testId}-error`}>{error}</p>
      )}
    </div>
  );
}

function WaiverVisibilityRadio({ label, value, onChange, testId }) {
  return (
    <div className="space-y-2">
      <Label className="text-sm">{label}</Label>
      <RadioGroup value={value} onValueChange={onChange} className="flex flex-col gap-2" data-testid={`${testId}-group`}>
        <label className="flex items-center gap-2 cursor-pointer text-sm">
          <RadioGroupItem value="own" data-testid={`${testId}-own`} /> Own Team
        </label>
        <label className="flex items-center gap-2 cursor-pointer text-sm">
          <RadioGroupItem value="all_teams" data-testid={`${testId}-all`} /> All Teams
        </label>
        <label className="flex items-center gap-2 cursor-pointer text-sm">
          <RadioGroupItem value="all_teams_anonymous" data-testid={`${testId}-anon`} /> All Teams (anonymous — number only)
        </label>
        <label className="flex items-center gap-2 cursor-pointer text-sm">
          <RadioGroupItem value="league_admin" data-testid={`${testId}-admin`} /> League Admin only
        </label>
      </RadioGroup>
    </div>
  );
}

export function WaiverWireCard({ cfg, setCfg, leagueTeams }) {
  const w = cfg.waiver;
  const set = (key) => (val) => setCfg((prev) => ({ ...prev, waiver: { ...prev.waiver, [key]: val } }));
  const setLimit = (key) => (val) =>
    setCfg((prev) => ({
      ...prev,
      waiver: {
        ...prev.waiver,
        claim_limits: { ...(prev.waiver.claim_limits || {}), [key]: val },
      },
    }));

  // Iter 120 — auto-seed manual priority list with all teams the first
  // time the LM picks "manual" so the page isn't a confusing empty list.
  useEffect(() => {
    if (w.enabled
      && w.priority_order === "manual"
      && (w.manual_priority_order || []).length === 0
      && (leagueTeams || []).length > 0
    ) {
      set("manual_priority_order")(leagueTeams.map((t) => t.id));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [w.enabled, w.priority_order, leagueTeams?.length]);

  const moveOrder = (idx, dir) => {
    const next = [...(w.manual_priority_order || [])];
    const swap = idx + dir;
    if (swap < 0 || swap >= next.length) return;
    [next[idx], next[swap]] = [next[swap], next[idx]];
    set("manual_priority_order")(next);
  };
  const teamName = (id) => (leagueTeams || []).find((t) => t.id === id)?.name || id;

  // Inline validation: FA / Waiver cap must not exceed Total when set
  const limits = w.claim_limits || {};
  const faError = limits.total != null && limits.fa != null && limits.fa > limits.total
    ? `Exceeds Total (${limits.total})` : null;
  const wvError = limits.total != null && limits.waivers != null && limits.waivers > limits.total
    ? `Exceeds Total (${limits.total})` : null;

  const addSlot = () => {
    if (w.processing_schedule.length >= 3) {
      toast("Up to 3 processing slots per week");
      return;
    }
    set("processing_schedule")([...w.processing_schedule, { day_of_week: 2, time: "21:00" }]);
  };

  return (
    <Card className="bg-card border-border" data-testid="transactions-waiver-card">
      <CardHeader>
        <CardTitle>
          Waivers
          <InfoHint
            testId="info-waivers"
            text="Separate rule set for the waiver wire (priority claims) versus open free-agency. Turn off to make every add/drop run through free-agency rules."
          />
        </CardTitle>
        <CardDescription>
          Enable a separate waiver-wire rule set distinct from free-agency.
          When off, free-agency rules govern all add/drop flows.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-center gap-3">
          <Switch
            checked={w.enabled}
            onCheckedChange={set("enabled")}
            id="waivers-enabled"
            data-testid="waiver-enabled"
          />
          <Label htmlFor="waivers-enabled" className="cursor-pointer text-sm">
            Enable waiver wire (use distinct rules — claims with priority)
          </Label>
        </div>

        {w.enabled && (
          <div className="rounded-md border border-border p-4 space-y-5">

            {/* Iter 120 — Waiver Wire System dropdown */}
            <div className="space-y-2">
              <Label className="text-sm font-semibold">
                Waiver Wire System
                <InfoHint
                  testId="info-waiver-system-type"
                  text="Automated Priority Order = teams win claims by current priority rank, recalculated each cycle. FAAB = teams bid blind dollars, highest bid wins (priority breaks ties)."
                />
              </Label>
              <Select value={w.system_type} onValueChange={set("system_type")}>
                <SelectTrigger className="bg-secondary border-border w-full md:w-80" data-testid="waiver-system-type">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="bg-popover border-border z-50">
                  <SelectItem value="auto_priority" data-testid="waiver-system-auto-priority">Automated Priority Order</SelectItem>
                  <SelectItem value="faab" data-testid="waiver-system-faab">Free Agent Acquisition Budget (FAAB)</SelectItem>
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground">
                {w.system_type === "faab"
                  ? "Teams bid blind FAAB dollars on claims; highest bid wins (priority order tiebreaks ties)."
                  : "Highest priority team wins each claim; the order recalculates each processing cycle."}
              </p>
            </div>

            {/* Iter 126 — FAAB customization (visible only when FAAB system) */}
            {w.system_type === "faab" && (
              <div
                className="space-y-3 rounded-md border border-emerald-500/30 bg-emerald-500/5 p-4"
                data-testid="waiver-faab-block"
              >
                <div className="flex items-start gap-3">
                  <div className="flex-1">
                    <Label className="text-sm font-semibold text-emerald-200">
                      FAAB Customization
                      <InfoHint
                        testId="info-faab-customization"
                        text="FAAB (Free Agent Acquisition Budget) gives every team a single budget at draft. Owners enter blind dollar bids on each claim; highest bid wins, ties broken by current priority order. Unspent budget can roll over or reset depending on the per-season setting below."
                      />
                    </Label>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      Configure the per-team blind-bid budget and the clearing
                      window before winning bids are processed.
                    </p>
                  </div>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  <div className="space-y-1">
                    <Label htmlFor="waiver-faab-budget" className="text-xs">
                      FAAB Budget per Team ($)
                      <InfoHint
                        testId="info-faab-budget"
                        text="Dollars each team gets to spend on FAAB bids this season. Common values: $100 (default), $200, $500 (deep markets). Reset at the start of each draft."
                      />
                    </Label>
                    <Input
                      id="waiver-faab-budget"
                      type="number"
                      min={0}
                      max={10000}
                      value={w.faab_budget ?? ""}
                      onChange={(e) => {
                        const v = e.target.value === "" ? null : Number(e.target.value);
                        set("faab_budget")(v ?? 0);
                      }}
                      data-testid="waiver-faab-budget-input"
                      placeholder="100"
                      className="bg-background"
                    />
                    <p className="text-[10px] text-muted-foreground">
                      Reset per season at draft. Common values: $100 (default), $500 (deep markets).
                    </p>
                  </div>
                  <div className="space-y-1">
                    <Label htmlFor="waiver-clearing-period" className="text-xs">
                      Waiver Clearing Period (days)
                      <InfoHint
                        testId="info-clearing-period"
                        text="Number of days a claim sits before bids are evaluated. 0 = instant (bid placed, processed immediately). 1-2 days is standard. 7 = weekly process."
                      />
                    </Label>
                    <Input
                      id="waiver-clearing-period"
                      type="number"
                      min={0}
                      max={7}
                      value={w.processing_days_count ?? ""}
                      onChange={(e) => {
                        const v = e.target.value === "" ? 0 : Number(e.target.value);
                        set("processing_days_count")(Math.max(0, Math.min(7, v)));
                      }}
                      data-testid="waiver-clearing-period-input"
                      placeholder="1"
                      className="bg-background"
                    />
                    <p className="text-[10px] text-muted-foreground">
                      Days a claim sits before bids are evaluated. 0 = instant.
                    </p>
                  </div>
                </div>
              </div>
            )}

            {w.system_type === "auto_priority" && (
              <div className="space-y-3 rounded-md border border-border p-3" data-testid="waiver-auto-priority-block">
                <Label className="text-sm font-semibold">
                  Priority Order
                  <InfoHint
                    testId="info-priority-order"
                    text="How the priority queue is recalculated each waiver cycle. Serpentine reverses direction every round (snake draft style). Non-serpentine keeps the same order. Manual lets the commissioner drag teams. Random reseeds each cycle."
                  />
                </Label>
                <RadioGroup
                  value={w.priority_order}
                  onValueChange={set("priority_order")}
                  className="flex flex-col gap-3"
                  data-testid="waiver-priority-order-group"
                >
                  <label className="flex items-start gap-2 cursor-pointer text-sm rounded-md border border-border p-3">
                    <RadioGroupItem value="reverse_standings_serpentine" data-testid="waiver-priority-serpentine" className="mt-0.5" />
                    <span>
                      <strong>Reverse Order of Standings — Serpentine</strong>
                      <p className="text-xs text-muted-foreground mt-1">
                        When claims process, the lowest-ranked team in the current
                        standings gets first pick, then the second lowest, and so on
                        up to first place. The next round reverses: first place picks
                        first, then second, down to last. Teams with no pending claims
                        are skipped. In a 4-team league: 4, 3, 2, 1, 1, 2, 3, 4, 4, 3,
                        2, 1, … until everyone is out of claims.
                      </p>
                    </span>
                  </label>
                  <label className="flex items-start gap-2 cursor-pointer text-sm rounded-md border border-border p-3">
                    <RadioGroupItem value="reverse_standings" data-testid="waiver-priority-reverse" className="mt-0.5" />
                    <span>
                      <strong>Reverse Order of Standings (non-serpentine)</strong>
                      <p className="text-xs text-muted-foreground mt-1">
                        Same order every round: lowest-ranked team always picks first,
                        first place always picks last. Round-robin until all claims
                        are processed.
                      </p>
                    </span>
                  </label>
                  <label className="flex items-start gap-2 cursor-pointer text-sm rounded-md border border-border p-3">
                    <RadioGroupItem value="manual" data-testid="waiver-priority-manual" className="mt-0.5" />
                    <span>
                      <strong>Manual</strong>
                      <p className="text-xs text-muted-foreground mt-1">
                        League Administrator sets the priority order below. Same
                        order applies every round.
                      </p>
                    </span>
                  </label>
                  <label className="flex items-start gap-2 cursor-pointer text-sm rounded-md border border-border p-3">
                    <RadioGroupItem value="random" data-testid="waiver-priority-random" className="mt-0.5" />
                    <span>
                      <strong>Random</strong>
                      <p className="text-xs text-muted-foreground mt-1">
                        Each processing cycle assigns a fresh random order.
                      </p>
                    </span>
                  </label>
                </RadioGroup>

                {w.priority_order === "manual" && (
                  <div className="space-y-2 pt-1">
                    <Label className="text-xs">Manual order (highest priority first)</Label>
                    <div className="rounded-md border border-border max-h-72 overflow-y-auto" data-testid="waiver-manual-order-list">
                      {(w.manual_priority_order || []).length === 0 ? (
                        <div className="text-sm text-muted-foreground italic p-3">
                          No teams yet — auto-seeds when leagueTeams loads.
                        </div>
                      ) : (w.manual_priority_order || []).map((tid, idx) => (
                        <div key={tid} className="flex items-center justify-between gap-2 p-2 border-b border-border last:border-0" data-testid={`waiver-manual-row-${idx}`}>
                          <div className="flex items-center gap-2">
                            <GripVertical className="h-4 w-4 text-muted-foreground" />
                            <span className="text-xs text-muted-foreground w-6">{idx + 1}.</span>
                            <span className="text-sm font-medium">{teamName(tid)}</span>
                          </div>
                          <div className="flex gap-1">
                            <Button size="icon" variant="ghost" className="h-7 w-7" onClick={() => moveOrder(idx, -1)} disabled={idx === 0} data-testid={`waiver-manual-up-${idx}`}>
                              <ChevronUp className="h-4 w-4" />
                            </Button>
                            <Button size="icon" variant="ghost" className="h-7 w-7" onClick={() => moveOrder(idx, +1)} disabled={idx === (w.manual_priority_order || []).length - 1} data-testid={`waiver-manual-down-${idx}`}>
                              <ChevronDown className="h-4 w-4" />
                            </Button>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}

            <Separator />
            {/* Iter 119 — per-Setting claim limits */}
            <div>
              <div className="text-sm font-semibold mb-2">Max claims per Setting (1-500 or Unlimited)</div>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <WaiverLimitField label="Total" value={limits.total} onChange={setLimit("total")} testId="waiver-limit-total" />
                <WaiverLimitField label="Free Agency" value={limits.fa} onChange={setLimit("fa")} error={faError} testId="waiver-limit-fa" />
                <WaiverLimitField label="Waiver Wire" value={limits.waivers} onChange={setLimit("waivers")} error={wvError} testId="waiver-limit-waivers" />
              </div>
              <p className="text-[11px] text-muted-foreground mt-2">
                Free Agency and Waiver Wire caps cannot exceed the Total cap when Total is finite.
              </p>
            </div>

            <Separator />

            {/* Processing window */}
            <div className="space-y-2">
              <Label className="text-sm">Claims processed</Label>
              <RadioGroup value={w.processing_mode} onValueChange={set("processing_mode")} className="flex flex-col gap-2">
                <label className="flex items-center gap-2 cursor-pointer text-sm">
                  <RadioGroupItem value="days" data-testid="waiver-mode-days" /> After N days
                </label>
                <label className="flex items-center gap-2 cursor-pointer text-sm">
                  <RadioGroupItem value="scheduled" data-testid="waiver-mode-scheduled" /> On specific day(s) & time(s)
                </label>
              </RadioGroup>
            </div>

            {w.processing_mode === "days" && (
              <div className="space-y-1.5 max-w-xs">
                <Label className="text-xs">Days until processing (0 = next worker cycle)</Label>
                <Input
                  type="number" min={0} max={7}
                  value={w.processing_days_count}
                  onChange={(e) => set("processing_days_count")(Math.min(Math.max(parseInt(e.target.value, 10) || 0, 0), 7))}
                  className="bg-secondary border-border w-24"
                  data-testid="waiver-days-input"
                />
              </div>
            )}

            {w.processing_mode === "scheduled" && (
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <Label className="text-sm">Processing slots (up to 3 per week)</Label>
                  <Button size="sm" variant="outline" onClick={addSlot} disabled={w.processing_schedule.length >= 3} className="gap-1" data-testid="waiver-schedule-add">
                    <Plus className="h-3 w-3" /> Add slot
                  </Button>
                </div>
                {(w.processing_schedule || []).length === 0 ? (
                  <p className="text-xs text-muted-foreground italic">Add at least one slot — e.g. Wednesday 21:00.</p>
                ) : (
                  <div className="space-y-2">
                    {w.processing_schedule.map((slot, idx) => (
                      <div key={idx} className="flex items-center gap-2" data-testid={`waiver-schedule-row-${idx}`}>
                        <Select
                          value={String(slot.day_of_week)}
                          onValueChange={(v) => {
                            const arr = [...w.processing_schedule];
                            arr[idx] = { ...slot, day_of_week: parseInt(v, 10) };
                            set("processing_schedule")(arr);
                          }}
                        >
                          <SelectTrigger className="bg-secondary border-border w-40 h-8" data-testid={`waiver-schedule-${idx}-day`}>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent className="bg-popover border-border z-50">
                            {DAY_LABELS.map((d, i) => (<SelectItem key={i} value={String(i)}>{d}</SelectItem>))}
                          </SelectContent>
                        </Select>
                        <ClockPicker
                          value={slot.time}
                          onChange={(time) => {
                            const arr = [...w.processing_schedule];
                            arr[idx] = { ...slot, time };
                            set("processing_schedule")(arr);
                          }}
                          className="w-32"
                          data-testid={`waiver-schedule-${idx}-time`}
                        />
                        <Button
                          size="icon" variant="ghost" className="h-7 w-7 text-rose-400"
                          onClick={() => set("processing_schedule")(w.processing_schedule.filter((_, i) => i !== idx))}
                          data-testid={`waiver-schedule-${idx}-remove`}
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            <Separator />

            {/* Iter 119 — player filters */}
            <div className="space-y-3">
              <Label className="text-sm font-semibold">Player eligibility filters</Label>

              <div className="space-y-2">
                <Label className="text-xs">Prevent claims for injured players</Label>
                <RadioGroup value={w.prevent_injured} onValueChange={set("prevent_injured")} className="flex flex-wrap gap-4" data-testid="waiver-prevent-injured-group">
                  <label className="flex items-center gap-2 cursor-pointer text-sm">
                    <RadioGroupItem value="off" data-testid="waiver-prevent-injured-off" /> Off
                  </label>
                  <label className="flex items-center gap-2 cursor-pointer text-sm">
                    <RadioGroupItem value="nhl_ir" data-testid="waiver-prevent-injured-ir" /> NHL Injury Reserve
                  </label>
                  <label className="flex items-center gap-2 cursor-pointer text-sm">
                    <RadioGroupItem value="all_flags" data-testid="waiver-prevent-injured-flags" /> All Injury Flags
                  </label>
                </RadioGroup>
              </div>

              <div className="flex items-center gap-3">
                <Switch checked={w.prevent_minors} onCheckedChange={set("prevent_minors")} id="waiver-prevent-minors" data-testid="waiver-prevent-minors" />
                <Label htmlFor="waiver-prevent-minors" className="cursor-pointer text-sm">
                  Prevent claims on players in minors
                </Label>
              </div>

              <div className="flex items-center gap-3">
                <Switch checked={w.prevent_prospects} onCheckedChange={set("prevent_prospects")} id="waiver-prevent-prospects" data-testid="waiver-prevent-prospects" />
                <Label htmlFor="waiver-prevent-prospects" className="cursor-pointer text-sm">
                  Prevent claims on prospects (per league prospect guidelines)
                </Label>
              </div>
            </div>

            <Separator />

            {/* Iter 119 — visibility */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <WaiverVisibilityRadio
                label="Pending claims viewable by"
                value={w.pending_visibility}
                onChange={set("pending_visibility")}
                testId="waiver-pending-visibility"
              />
              <WaiverVisibilityRadio
                label="Failed claims viewable by"
                value={w.failed_visibility}
                onChange={set("failed_visibility")}
                testId="waiver-failed-visibility"
              />
            </div>

            <Separator />

            {/* Iter 119 — force toggles */}
            <div className="space-y-3">
              <div className="flex items-center gap-3">
                <Switch checked={w.force_drop_on_claim} onCheckedChange={set("force_drop_on_claim")} id="waiver-force-drop" data-testid="waiver-force-drop-on-claim" />
                <Label htmlFor="waiver-force-drop" className="cursor-pointer text-sm">
                  Force drop on each claim (or move a player to injury reserve)
                </Label>
              </div>
              <div className="flex items-center gap-3">
                <Switch checked={w.force_claim_on_drop} onCheckedChange={set("force_claim_on_drop")} id="waiver-force-claim" data-testid="waiver-force-claim-on-drop" />
                <Label htmlFor="waiver-force-claim" className="cursor-pointer text-sm">
                  Force claim on each drop (require an add when dropping)
                </Label>
              </div>
            </div>

            <Separator />

            {/* Existing abuse rule */}
            <div className="space-y-2">
              <div className="flex items-center gap-3">
                <Switch
                  checked={w.abuse_window_enabled}
                  onCheckedChange={set("abuse_window_enabled")}
                  id="waiver-abuse"
                  data-testid="waiver-abuse-enabled"
                />
                <Label htmlFor="waiver-abuse" className="cursor-pointer text-sm">
                  Waiver-wire abuse rule (drop-then-readd block)
                </Label>
              </div>
              {w.abuse_window_enabled && (
                <div className="pl-12 flex items-center gap-2">
                  <Label className="text-xs">Window (days)</Label>
                  <Input
                    type="number" min={1} max={7}
                    value={w.abuse_window_days}
                    onChange={(e) => set("abuse_window_days")(Math.min(Math.max(parseInt(e.target.value, 10) || 1, 1), 7))}
                    className="bg-secondary border-border w-20 h-8"
                    data-testid="waiver-abuse-days"
                  />
                  <span className="text-xs text-muted-foreground">
                    A team that drops a player can't re-add them within this window.
                  </span>
                </div>
              )}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

/* ───────────── Draft tab — claim/drop rules card ─────────────────── */

export function TransactionsDraftRulesCard({ leagueId }) {
  const { cfg, setCfg, loading, saving, save, error, retry } = useTransactionsConfig(leagueId);
  if (error) return <div role="alert">{error} <Button onClick={retry}>Retry loading transactions</Button></div>;

  if (loading) {
    return <Card className="bg-card border-border"><CardContent className="py-6 text-sm text-muted-foreground italic">Loading draft rules…</CardContent></Card>;
  }

  const set = (key) => (val) =>
    setCfg((prev) => ({ ...prev, draft_claims: { ...prev.draft_claims, [key]: val } }));

  return (
    <Card className="bg-card border-border" data-testid="transactions-draft-rules-card">
      <CardHeader>
        <CardTitle>
          Draft Day Transactions
          <InfoHint
            testId="info-draft-day-transactions"
            text="Rules that apply only during the live draft. Useful for dynasty leagues that want to allow drops mid-draft to clear roster space for prospects."
          />
        </CardTitle>
        <CardDescription>Allow claim or drop activity around the league's scheduled draft.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex items-center gap-3">
          <Switch
            checked={cfg.draft_claims.allow_claims_before_draft}
            onCheckedChange={set("allow_claims_before_draft")}
            id="draft-allow-claims-before"
            data-testid="draft-allow-claims-before"
          />
          <Label htmlFor="draft-allow-claims-before" className="cursor-pointer text-sm">
            Allow claims/drops before scheduled drafts
          </Label>
        </div>
        <div className="flex items-center gap-3">
          <Switch
            checked={cfg.draft_claims.allow_drops_during_draft}
            onCheckedChange={set("allow_drops_during_draft")}
            id="draft-allow-drops-during"
            data-testid="draft-allow-drops-during"
          />
          <Label htmlFor="draft-allow-drops-during" className="cursor-pointer text-sm">
            Allow drops during the draft
          </Label>
        </div>
        <div className="flex justify-end pt-2">
          <Button onClick={() => save(cfg)} disabled={saving} className="gap-2" data-testid="draft-rules-save-btn">
            {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
            Save Draft Rules
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

/* ───────────── Container that ties everything together ───────────── */

export default function TransactionsConfigCards({ leagueId, leagueTeams }) {
  const { cfg, setCfg, loading, saving, save, error, retry } = useTransactionsConfig(leagueId);
  if (error) return <div role="alert">{error} <Button onClick={retry}>Retry loading transactions</Button></div>;

  if (!leagueId) return null;
  if (loading) {
    return <Card className="bg-card border-border"><CardContent className="py-6 text-sm text-muted-foreground italic">Loading transactions configuration…</CardContent></Card>;
  }

  return (
    <div className="space-y-6" data-testid="transactions-config-cards">
      <ClaimsLimitsCard cfg={cfg} setCfg={setCfg} onSave={() => save(cfg)} saving={saving} />
      <ClaimRulesCard cfg={cfg} setCfg={setCfg} />
      <FreeAgencyCard cfg={cfg} setCfg={setCfg} leagueTeams={leagueTeams || []} />
      <WaiverWireCard cfg={cfg} setCfg={setCfg} leagueTeams={leagueTeams || []} />
      <TradesConfigCard cfg={cfg} setCfg={setCfg} totalTeams={(leagueTeams || []).length} />
      <div className="flex justify-end">
        <Button onClick={() => save(cfg)} disabled={saving} className="gap-2" data-testid="transactions-bottom-save-btn">
          {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
          Save All Transactions Settings
        </Button>
      </div>
    </div>
  );
}


/* ───────────── Iter 231g — Trades configuration card ────────────────
 *
 * Single card grouping every trade-related knob the Commissioner needs.
 * Mounted in the Transactions tab between Waiver Wire and the Save row.
 * All controls bind into `cfg.trades.*` and persist via the shared
 * useTransactionsConfig hook. The trade engine (routes/trades.py) reads
 * from `transactions_config.trades.*` with fallback to the legacy
 * top-level league fields for backward compat.
 */
export function TradesConfigCard({ cfg, setCfg, totalTeams }) {
  const t = cfg.trades || DEFAULT_CFG.trades;
  const set = (key) => (val) =>
    setCfg((prev) => ({ ...prev, trades: { ...(prev.trades || DEFAULT_CFG.trades), [key]: val } }));

  const maxTradesUnlimited = t.max_trades_per_team === null || t.max_trades_per_team === undefined;

  return (
    <Card className="bg-card border-border" data-testid="transactions-trades-card">
      <CardHeader>
        <CardTitle>
          Trades
          <InfoHint
            testId="info-trades-card"
            text="Controls how trades flow through the league — review window, voting, draft-window rules, and what happens to illegal rosters."
          />
        </CardTitle>
        <CardDescription>
          Configure the trade lifecycle: review period, veto voting, per-team caps, and pre/in-draft allowances.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Review period + veto threshold */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="space-y-2">
            <Label htmlFor="trade-review-hours" className="text-sm">
              Review period (hours)
              <InfoHint
                testId="info-trade-review-hours"
                text="How long a trade sits in Pending Review after both sides accept. League members can vote to veto during this window."
              />
            </Label>
            <Input
              id="trade-review-hours"
              type="number"
              min={0}
              max={336}
              value={t.review_period_hours}
              onChange={(e) => set("review_period_hours")(Math.max(0, Math.min(336, Number(e.target.value) || 0)))}
              data-testid="trade-review-hours-input"
            />
            <p className="text-xs text-muted-foreground">0 = process immediately. Up to 14 days (336h).</p>
          </div>

          <div className="space-y-2">
            <Label htmlFor="trade-veto-teams" className="text-sm">
              Veto threshold (number of teams)
              <InfoHint
                testId="info-trade-veto-teams"
                text="How many distinct teams must vote No to veto a trade. Multiple owners of the same team count as one vote."
              />
            </Label>
            <Input
              id="trade-veto-teams"
              type="number"
              min={0}
              max={50}
              value={t.veto_threshold_teams}
              onChange={(e) => set("veto_threshold_teams")(Math.max(0, Math.min(50, Number(e.target.value) || 0)))}
              data-testid="trade-veto-teams-input"
            />
            <p className="text-xs text-muted-foreground">
              0 = no vetoes allowed. Currently {totalTeams || "—"} teams in this league.
            </p>
          </div>
        </div>

        <Separator />

        {/* Max trades per team */}
        <div className="space-y-2">
          <Label className="text-sm">
            Maximum trades per team (season)
            <InfoHint
              testId="info-trade-max-per-team"
              text="Cap the number of trades a team can execute in one season. Unlimited removes the cap entirely."
            />
          </Label>
          <div className="flex items-center gap-3">
            <Switch
              checked={maxTradesUnlimited}
              onCheckedChange={(checked) => set("max_trades_per_team")(checked ? null : 10)}
              id="trade-max-unlimited"
              data-testid="trade-max-unlimited-switch"
            />
            <Label htmlFor="trade-max-unlimited" className="cursor-pointer text-sm">Unlimited</Label>
            <Input
              type="number"
              min={1}
              max={50}
              value={maxTradesUnlimited ? "" : t.max_trades_per_team}
              onChange={(e) => set("max_trades_per_team")(Math.max(1, Math.min(50, Number(e.target.value) || 1)))}
              disabled={maxTradesUnlimited}
              className="w-32"
              placeholder="e.g. 10"
              data-testid="trade-max-per-team-input"
            />
            <span className="text-xs text-muted-foreground">trades per team (1–50)</span>
          </div>
        </div>

        <Separator />

        {/* Voting system + anonymous */}
        <div className="space-y-2">
          <Label className="text-sm">
            Trade voting system
            <InfoHint
              testId="info-trade-voting-system"
              text="Who is eligible to cast veto votes during the review window."
            />
          </Label>
          <RadioGroup
            value={t.voting_system}
            onValueChange={set("voting_system")}
            className="flex flex-wrap gap-4"
            data-testid="trade-voting-system-group"
          >
            <label className="flex items-center gap-2 cursor-pointer text-sm">
              <RadioGroupItem value="managers" data-testid="trade-voting-managers" /> Managers (team owners)
            </label>
            <label className="flex items-center gap-2 cursor-pointer text-sm">
              <RadioGroupItem value="commissioners" data-testid="trade-voting-commissioners" /> Commissioners only
            </label>
            <label className="flex items-center gap-2 cursor-pointer text-sm">
              <RadioGroupItem value="both" data-testid="trade-voting-both" /> Both (managers + commissioners)
            </label>
          </RadioGroup>
        </div>

        <div className="flex items-center gap-3">
          <Switch
            checked={t.anonymous_voting}
            onCheckedChange={set("anonymous_voting")}
            id="trade-anon-voting"
            data-testid="trade-anonymous-voting-switch"
          />
          <Label htmlFor="trade-anon-voting" className="cursor-pointer text-sm">
            Anonymous voting
            <InfoHint
              testId="info-trade-anonymous"
              text="When on, individual ballots aren't publicly attributed — only the running vote count is shown. Commissioners always see who voted."
            />
          </Label>
        </div>

        <Separator />

        {/* Lock & draft window rules */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-y-4 gap-x-6">
          <div className="flex items-center gap-3">
            <Switch
              checked={t.lock_at_first_game}
              onCheckedChange={set("lock_at_first_game")}
              id="trade-lock-first-game"
              data-testid="trade-lock-first-game-switch"
            />
            <Label htmlFor="trade-lock-first-game" className="cursor-pointer text-sm">
              Lock trades at first game of day
              <InfoHint
                testId="info-trade-lock-first-game"
                text="Once the day's first NHL puck drops, no new trade proposals can be created until tomorrow."
              />
            </Label>
          </div>

          <div className="flex items-center gap-3">
            <Switch
              checked={t.allow_before_draft}
              onCheckedChange={set("allow_before_draft")}
              id="trade-allow-before-draft"
              data-testid="trade-allow-before-draft-switch"
            />
            <Label htmlFor="trade-allow-before-draft" className="cursor-pointer text-sm">
              Allow trades before the draft
              <InfoHint
                testId="info-trade-before-draft"
                text="Permits pre-draft pick swaps. Off = trade window opens only after the draft completes."
              />
            </Label>
          </div>

          <div className="flex items-center gap-3">
            <Switch
              checked={t.allow_during_draft}
              onCheckedChange={set("allow_during_draft")}
              id="trade-allow-during-draft"
              data-testid="trade-allow-during-draft-switch"
            />
            <Label htmlFor="trade-allow-during-draft" className="cursor-pointer text-sm">
              Allow trades during the draft
              <InfoHint
                testId="info-trade-during-draft"
                text="Permits live pick swaps mid-draft (advanced). Off = trade engine pauses while a draft is active."
              />
            </Label>
          </div>

          <div className="flex items-center gap-3">
            <Switch
              checked={t.allow_illegal_rosters}
              onCheckedChange={set("allow_illegal_rosters")}
              id="trade-allow-illegal"
              data-testid="trade-allow-illegal-rosters-switch"
            />
            <Label htmlFor="trade-allow-illegal" className="cursor-pointer text-sm">
              Allow execution with illegal rosters
              <InfoHint
                testId="info-trade-illegal-rosters"
                text="When on, trades execute even if either team is left over the salary cap, short on skaters, or otherwise non-compliant. The roster monitor will flag the team for cleanup."
              />
            </Label>
          </div>

          <div className="flex items-center gap-3">
            <Switch
              checked={t.comments_visible_to_all}
              onCheckedChange={set("comments_visible_to_all")}
              id="trade-comments-public"
              data-testid="trade-comments-public-switch"
            />
            <Label htmlFor="trade-comments-public" className="cursor-pointer text-sm">
              Trade comments visible to all managers
              <InfoHint
                testId="info-trade-comments-public"
                text="When on, every league manager can read the comment thread on pending trades. Off = only the two trading teams + commissioners see comments."
              />
            </Label>
          </div>

          <div className="flex items-center gap-3">
            <Switch
              checked={t.conditional_trades_enabled}
              onCheckedChange={set("conditional_trades_enabled")}
              id="trade-conditional"
              data-testid="trade-conditional-switch"
            />
            <Label htmlFor="trade-conditional" className="cursor-pointer text-sm">
              Enable conditional trades
              <InfoHint
                testId="info-trade-conditional"
                text="Managers may attach conditions (e.g. pick upgrades if a team makes playoffs) when authoring a trade. The trade engine resolves conditions automatically at the trigger date."
              />
            </Label>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
