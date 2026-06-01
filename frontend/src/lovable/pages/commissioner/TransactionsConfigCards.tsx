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
import { Switch } from "@/components/ui/switch";
import { Checkbox } from "@/components/ui/checkbox";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Separator } from "@/components/ui/separator";

const DAY_LABELS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

const DEFAULT_CFG = {
  claim_limits: {
    season: { total: null, fa: null, waivers: null },
    week: { total: null, fa: null, waivers: null },
  },
  claim_rules: {
    lock_at_first_game: false,
    allow_non_playoff_teams_claims: true,
    prevent_injured: "off",
    prevent_minors: false,
    pending_visibility: "user",
    failed_visibility: "user",
  },
  free_agency: {
    system_type: "open",
    auto_priority_basis: "reverse_live",
    priority_recompute_cadence: "live",
    manual_priority_duration: "one_off",
    manual_priority_order: [],
    manual_priority_schedule: [],
    picks_per_round_policy: "top_then_next",
    waivers_reset_after_claim: false,
  },
  waiver: {
    enabled: false,
    // Iter 120 — Waiver Wire System + priority order
    system_type: "auto_priority",
    priority_order: "reverse_standings_serpentine",
    manual_priority_order: [],
    processing_mode: "days",
    processing_days_count: 2,
    processing_schedule: [],
    abuse_window_enabled: false,
    abuse_window_days: 3,
    // Iter 119 — waiver-section-specific overrides
    claim_limits: { total: null, fa: null, waivers: null },
    prevent_injured: "off",
    prevent_minors: false,
    prevent_prospects: false,
    pending_visibility: "own",
    failed_visibility: "own",
    force_drop_on_claim: false,
    force_claim_on_drop: false,
    // Iter 126 — FAAB system settings (visible when system_type == "faab")
    faab_budget: 100,
  },
  draft_claims: {
    allow_claims_before_draft: false,
    allow_drops_during_draft: false,
  },
};

function deepMerge(base, override) {
  if (!override) return base;
  const out = { ...base };
  for (const k of Object.keys(override)) {
    const v = override[k];
    if (v && typeof v === "object" && !Array.isArray(v)) {
      out[k] = deepMerge(base[k] || {}, v);
    } else if (v !== undefined) {
      out[k] = v;
    }
  }
  return out;
}

/* ───────────── Hook: load + persist the envelope ─────────────────── */

export function useTransactionsConfig(leagueId) {
  const [cfg, setCfg] = useState(DEFAULT_CFG);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!leagueId) return;
    let cancelled = false;
    setLoading(true);
    api.get(`/leagues/${leagueId}/transactions-config`)
      .then(({ data }) => { if (!cancelled) setCfg(deepMerge(DEFAULT_CFG, data || {})); })
      .catch(() => { if (!cancelled) setCfg(DEFAULT_CFG); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [leagueId]);

  const save = async (next) => {
    setSaving(true);
    try {
      const { data } = await api.put(`/leagues/${leagueId}/transactions-config`, next);
      setCfg(deepMerge(DEFAULT_CFG, data || {}));
      toast.success("Transactions configuration saved");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to save transactions config");
    } finally {
      setSaving(false);
    }
  };

  return { cfg, setCfg, loading, saving, save };
}

/* ───────────── Claims Limits card ────────────────────────────────── */

function LimitField({ label, value, onChange, max, testId }) {
  const unlimited = value === null || value === undefined || value === "";
  return (
    <div className="space-y-1.5">
      <Label className="text-xs">{label}</Label>
      <div className="flex items-center gap-2">
        <Switch
          checked={!unlimited}
          onCheckedChange={(checked) => onChange(checked ? 1 : null)}
          data-testid={`${testId}-toggle`}
        />
        {unlimited ? (
          <span className="text-xs text-muted-foreground italic">Unlimited</span>
        ) : (
          <Input
            type="number"
            min={1}
            max={max}
            value={value ?? ""}
            onChange={(e) => {
              const raw = e.target.value;
              if (raw === "") return onChange(null);
              const n = Math.min(Math.max(parseInt(raw, 10) || 0, 1), max);
              onChange(n);
            }}
            className="bg-secondary border-border w-28 h-8"
            data-testid={`${testId}-input`}
          />
        )}
      </div>
    </div>
  );
}

export function ClaimsLimitsCard({ cfg, setCfg, onSave, saving }) {
  const set = (path) => (val) => {
    setCfg((prev) => {
      const next = JSON.parse(JSON.stringify(prev));
      const keys = path.split(".");
      let ref = next;
      for (let i = 0; i < keys.length - 1; i++) ref = ref[keys[i]];
      ref[keys[keys.length - 1]] = val;
      return next;
    });
  };

  return (
    <Card className="bg-card border-border" data-testid="transactions-claim-limits-card">
      <CardHeader>
        <CardTitle>Claims Limits</CardTitle>
        <CardDescription>
          Per-team caps on roster claims. Toggle a field on to set a number,
          off to leave it unlimited. Season values are 1-600, weekly values
          are 1-100.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div>
          <div className="text-sm font-semibold text-foreground/80 mb-2">Per Season</div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <LimitField label="Total" value={cfg.claim_limits.season.total} onChange={set("claim_limits.season.total")} max={600} testId="claims-season-total" />
            <LimitField label="Free Agency" value={cfg.claim_limits.season.fa} onChange={set("claim_limits.season.fa")} max={600} testId="claims-season-fa" />
            <LimitField label="Waivers" value={cfg.claim_limits.season.waivers} onChange={set("claim_limits.season.waivers")} max={600} testId="claims-season-waivers" />
          </div>
        </div>
        <Separator />
        <div>
          <div className="text-sm font-semibold text-foreground/80 mb-2">Per Week</div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <LimitField label="Total" value={cfg.claim_limits.week.total} onChange={set("claim_limits.week.total")} max={100} testId="claims-week-total" />
            <LimitField label="Free Agency" value={cfg.claim_limits.week.fa} onChange={set("claim_limits.week.fa")} max={100} testId="claims-week-fa" />
            <LimitField label="Waivers" value={cfg.claim_limits.week.waivers} onChange={set("claim_limits.week.waivers")} max={100} testId="claims-week-waivers" />
          </div>
        </div>
        <div className="flex justify-end">
          <Button onClick={onSave} disabled={saving} className="gap-2" data-testid="transactions-save-btn">
            {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
            Save All Transactions Settings
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

/* ───────────── Claim Rules card ──────────────────────────────────── */

export function ClaimRulesCard({ cfg, setCfg }) {
  const set = (key) => (val) =>
    setCfg((prev) => ({ ...prev, claim_rules: { ...prev.claim_rules, [key]: val } }));

  return (
    <Card className="bg-card border-border" data-testid="transactions-claim-rules-card">
      <CardHeader>
        <CardTitle>Claim & Drop Rules</CardTitle>
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
          </Label>
        </div>

        <div className="space-y-2">
          <Label className="text-sm">Prevent claims for injured players</Label>
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
        <CardTitle>Free Agency</CardTitle>
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
              <span><strong>Automated Priority Order</strong> — used when waivers are disabled</span>
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
              <Label className="text-sm">Duration</Label>
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
        <CardTitle>Waivers</CardTitle>
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
              <Label className="text-sm font-semibold">Waiver Wire System</Label>
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
                <Label className="text-sm font-semibold">Priority Order</Label>
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
                        <Input
                          type="time"
                          value={slot.time}
                          onChange={(e) => {
                            const arr = [...w.processing_schedule];
                            arr[idx] = { ...slot, time: e.target.value };
                            set("processing_schedule")(arr);
                          }}
                          className="bg-secondary border-border w-32 h-8"
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
  const { cfg, setCfg, loading, saving, save } = useTransactionsConfig(leagueId);

  if (loading) {
    return <Card className="bg-card border-border"><CardContent className="py-6 text-sm text-muted-foreground italic">Loading draft rules…</CardContent></Card>;
  }

  const set = (key) => (val) =>
    setCfg((prev) => ({ ...prev, draft_claims: { ...prev.draft_claims, [key]: val } }));

  return (
    <Card className="bg-card border-border" data-testid="transactions-draft-rules-card">
      <CardHeader>
        <CardTitle>Draft Day Transactions</CardTitle>
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
  const { cfg, setCfg, loading, saving, save } = useTransactionsConfig(leagueId);

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
      <div className="flex justify-end">
        <Button onClick={() => save(cfg)} disabled={saving} className="gap-2" data-testid="transactions-bottom-save-btn">
          {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
          Save All Transactions Settings
        </Button>
      </div>
    </div>
  );
}
