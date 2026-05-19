// @ts-nocheck
/**
 * Transactions tab — Commissioner-facing editor for trade settings, waivers,
 * roster locks, salary cap & salary retention. Playoffs / Regular-season /
 * Consolation now live under the **League Structure** tab.
 *
 * Backed by `PUT /api/leagues/{id}` with a sparse payload.
 */
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ArrowRightLeft, Trophy, Users, Save, Loader2, DollarSign, LockKeyhole } from "lucide-react";
import { Switch } from "@/components/ui/switch";
import { Checkbox } from "@/components/ui/checkbox";
import SmartNumberInput from "@/components/ui/smart-number-input";
import CBABadge from "@/lovable/components/CBABadge";
import VetoThresholdPreview from "@/lovable/components/VetoThresholdPreview";
import api from "@/lib/api";
import { useActiveLeague } from "@/hooks/use-active-league";

type FieldSpec = {
  key: string;
  label: string;
  min?: number;
  max?: number;
  helper?: string;
  unit?: string;
  defaultPlaceholder?: string;
};

type SectionSpec = {
  title: string;
  description: string;
  icon: React.ReactNode;
  testid: string;
  fields: FieldSpec[];
};

const sections: SectionSpec[] = [
  {
    title: "Roster Shape",
    description: "Defines the active roster + bench + minor-league pool sizes for every team.",
    icon: <Users className="h-5 w-5 text-cyan-400" />,
    testid: "rules-schedule-roster-card",
    fields: [
      { key: "roster_spots", label: "Active Roster Slots", min: 10, max: 40, defaultPlaceholder: "20" },
      { key: "bench_spots", label: "Bench Spots", min: 0, max: 20, defaultPlaceholder: "4" },
      { key: "minors_spots", label: "Minor League Spots", min: 0, max: 20, defaultPlaceholder: "5" },
    ],
  },
  {
    title: "Trade Settings",
    description: "Controls how trades are reviewed, vetoed, and locked at the deadline.",
    icon: <ArrowRightLeft className="h-5 w-5 text-amber-400" />,
    testid: "rules-schedule-trade-card",
    fields: [
      {
        key: "trade_review_period_hours",
        label: "Review Period (hours)",
        min: 0,
        max: 168,
        helper: "How long a trade waits before auto-executing. 0 = instant.",
        defaultPlaceholder: "72",
      },
      {
        key: "trade_veto_threshold_pct",
        label: "Veto Threshold (%)",
        min: 0,
        max: 100,
        helper: "% of league that must vote VETO. 0 = vetoes disabled.",
        defaultPlaceholder: "50",
      },
      {
        key: "trade_deadline_week",
        label: "Trade Deadline (week #)",
        min: 1,
        max: 30,
        helper: "After this week, new proposals are blocked.",
      },
    ],
  },
  {
    title: "Waivers",
    description: "FAAB budgets + waiver clearing period.",
    icon: <Trophy className="h-5 w-5 text-emerald-400" />,
    testid: "rules-schedule-waivers-card",
    fields: [
      {
        key: "waiver_faab_budget",
        label: "FAAB Budget per Team",
        min: 0,
        max: 10000,
        unit: "$",
        defaultPlaceholder: "100",
      },
      {
        key: "waiver_period_days",
        label: "Waiver Period (days)",
        min: 0,
        max: 7,
        helper: "Days a claim sits before processing.",
        defaultPlaceholder: "1",
      },
    ],
  },
];

const ALL_KEYS = sections.flatMap((s) => s.fields.map((f) => f.key));

export default function RulesScheduleTab() {
  const { league, reloadLeague } = useActiveLeague();
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);

  // Seed local draft from the league document
  useEffect(() => {
    if (!league?.id) return;
    const next: Record<string, string> = {};
    for (const key of ALL_KEYS) {
      const v = (league as any)[key];
      next[key] = v === null || v === undefined ? "" : String(v);
    }
    setDraft(next);
  }, [league?.id, ...ALL_KEYS.map((k) => (league as any)?.[k])]);

  const onChange = (key: string, value: string) => {
    setDraft((prev) => ({ ...prev, [key]: value }));
  };

  const buildPayload = (): Record<string, number> | null => {
    const payload: Record<string, number> = {};
    for (const section of sections) {
      for (const field of section.fields) {
        const raw = (draft[field.key] ?? "").trim();
        if (raw === "") continue;
        const parsed = parseInt(raw, 10);
        if (Number.isNaN(parsed)) {
          toast.error(`${field.label} must be a number`);
          return null;
        }
        if (field.min !== undefined && parsed < field.min) {
          toast.error(`${field.label} must be ≥ ${field.min}`);
          return null;
        }
        if (field.max !== undefined && parsed > field.max) {
          toast.error(`${field.label} must be ≤ ${field.max}`);
          return null;
        }
        const current = (league as any)?.[field.key];
        if (current !== parsed) payload[field.key] = parsed;
      }
    }
    return payload;
  };

  const onSave = async () => {
    if (!league?.id) return;
    const payload = buildPayload();
    if (payload === null) return;
    if (Object.keys(payload).length === 0) {
      toast("Nothing to save — values already match.", { description: "Edit a field first." });
      return;
    }
    setSaving(true);
    try {
      const { data } = await api.put(`/leagues/${league.id}`, payload);
      const changedKeys = Object.keys(data?.changes ?? payload);
      toast.success(`Saved ${changedKeys.length} setting${changedKeys.length === 1 ? "" : "s"}`);
      reloadLeague?.();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Failed to save league settings");
    } finally {
      setSaving(false);
    }
  };

  if (!league?.id) {
    return (
      <Card className="bg-card border-border">
        <CardContent className="py-6 text-sm text-muted-foreground">
          Select a league to edit its transactions settings.
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-6" data-testid="rules-schedule-tab">
      <Card className="bg-card border-border">
        <CardHeader>
          <div className="flex items-center justify-between gap-4 flex-wrap">
            <div>
              <CardTitle className="flex items-center gap-2">
                <Save className="h-5 w-5 text-cyan-400" />
                Transactions
              </CardTitle>
              <CardDescription>
                Trades, waivers, roster locks, salary cap &amp; retention.
                Changes are audit-logged with actor + before/after diff.
              </CardDescription>
            </div>
            <Badge variant="secondary" className="border-cyan-500/40 text-cyan-300">
              Single source of truth
            </Badge>
          </div>
        </CardHeader>
      </Card>

      {/* Roster Lock & Lineup Lock moved to League Setup tab per Iter 103 */}

      {/* Salary Cap (with hold-to-accelerate) */}
      <SalaryCapCard league={league} reloadLeague={reloadLeague} />

      {/* Salary Retention A/B */}
      <SalaryRetentionCard league={league} reloadLeague={reloadLeague} />

      {sections.map((section) => (
        <Card
          key={section.title}
          className="bg-card border-border"
          data-testid={section.testid}
        >
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-lg">
              {section.icon}
              {section.title}
            </CardTitle>
            <CardDescription>{section.description}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
              {section.fields.map((field) => (
                <div key={field.key} className="space-y-2">
                  <Label htmlFor={`rs-${field.key}`} className="text-sm">
                    {field.label}
                    {field.min !== undefined && field.max !== undefined && (
                      <span className="ml-2 text-xs text-muted-foreground">
                        ({field.min}–{field.max})
                      </span>
                    )}
                  </Label>
                  <div className="relative">
                    {field.unit && (
                      <span className="absolute inset-y-0 left-3 flex items-center text-muted-foreground text-sm">
                        {field.unit}
                      </span>
                    )}
                    <Input
                      id={`rs-${field.key}`}
                      type="number"
                      inputMode="numeric"
                      min={field.min}
                      max={field.max}
                      value={draft[field.key] ?? ""}
                      placeholder={field.defaultPlaceholder ?? "—"}
                      onChange={(e) => onChange(field.key, e.target.value)}
                      className={`bg-secondary border-border ${field.unit ? "pl-7" : ""}`}
                      data-testid={`rules-schedule-${field.key}-input`}
                    />
                  </div>
                  {field.helper && (
                    <p className="text-xs text-muted-foreground">{field.helper}</p>
                  )}
                  {field.key === "trade_veto_threshold_pct" && (
                    <VetoThresholdPreview
                      leagueId={league.id}
                      pct={parseInt(draft.trade_veto_threshold_pct || "0", 10)}
                      testId="rules-schedule-veto-preview"
                    />
                  )}
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      ))}

      <Separator />

      <div className="flex justify-end">
        <Button
          onClick={onSave}
          disabled={saving}
          className="gap-2"
          data-testid="rules-schedule-save-btn"
        >
          {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
          {saving ? "Saving…" : "Save All Changes"}
        </Button>
      </div>
    </div>
  );
}

const fmtMoney = (n: number) => (Number(n) || 0).toLocaleString();

const DAY_OPTIONS = [
  { value: "monday", label: "Monday" },
  { value: "tuesday", label: "Tuesday" },
  { value: "wednesday", label: "Wednesday" },
  { value: "thursday", label: "Thursday" },
  { value: "friday", label: "Friday" },
  { value: "saturday", label: "Saturday" },
  { value: "sunday", label: "Sunday" },
];

// 5-minute increments from 0 to 1440 (24 hrs)
const LOCK_TIME_OPTIONS = (() => {
  const opts: { value: string; label: string }[] = [];
  for (let m = 0; m <= 1440; m += 5) {
    let label: string;
    if (m === 0) label = "At first match start (0 min)";
    else if (m < 60) label = `${m} min before first match`;
    else if (m % 60 === 0) label = `${m / 60} hr before first match`;
    else label = `${Math.floor(m / 60)} hr ${m % 60} min before first match`;
    opts.push({ value: String(m), label });
  }
  return opts;
})();

export function RosterLockCard({ league, reloadLeague }: any) {
  const [lockType, setLockType] = useState<string>(league?.roster_lock_type || "daily");
  const [lockDay, setLockDay] = useState<string>(league?.roster_lock_day || "monday");
  const [lockSecondDay, setLockSecondDay] = useState<string>(league?.roster_lock_second_day || "thursday");
  const [lineupLockMins, setLineupLockMins] = useState<string>(
    String(league?.lineup_lock_minutes_before ?? 5),
  );
  const [playoffOverride, setPlayoffOverride] = useState<boolean>(!!league?.playoff_roster_lock_override);
  const [pLockType, setPLockType] = useState<string>(league?.playoff_roster_lock_type || "weekly");
  const [pLockDay, setPLockDay] = useState<string>(league?.playoff_roster_lock_day || "monday");
  const [pLockSecondDay, setPLockSecondDay] = useState<string>(league?.playoff_roster_lock_second_day || "thursday");
  const [pLineupLockMins, setPLineupLockMins] = useState<string>(
    String(league?.playoff_lineup_lock_minutes_before ?? 5),
  );
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setLockType(league?.roster_lock_type || "daily");
    setLockDay(league?.roster_lock_day || "monday");
    setLockSecondDay(league?.roster_lock_second_day || "thursday");
    setLineupLockMins(String(league?.lineup_lock_minutes_before ?? 5));
    setPlayoffOverride(!!league?.playoff_roster_lock_override);
    setPLockType(league?.playoff_roster_lock_type || "weekly");
    setPLockDay(league?.playoff_roster_lock_day || "monday");
    setPLockSecondDay(league?.playoff_roster_lock_second_day || "thursday");
    setPLineupLockMins(String(league?.playoff_lineup_lock_minutes_before ?? 5));
  }, [
    league?.id,
    league?.roster_lock_type,
    league?.roster_lock_day,
    league?.roster_lock_second_day,
    league?.lineup_lock_minutes_before,
    league?.playoff_roster_lock_override,
    league?.playoff_roster_lock_type,
    league?.playoff_roster_lock_day,
    league?.playoff_roster_lock_second_day,
    league?.playoff_lineup_lock_minutes_before,
  ]);

  const save = async () => {
    setSaving(true);
    try {
      await api.put(`/leagues/${league.id}`, {
        roster_lock_type: lockType,
        roster_lock_day: lockType === "daily" ? null : lockDay,
        roster_lock_second_day: lockType === "semi_weekly" ? lockSecondDay : null,
        lineup_lock_minutes_before: parseInt(lineupLockMins, 10) || 0,
        playoff_roster_lock_override: playoffOverride,
        playoff_roster_lock_type: playoffOverride ? pLockType : null,
        playoff_roster_lock_day: playoffOverride && pLockType !== "daily" ? pLockDay : null,
        playoff_roster_lock_second_day: playoffOverride && pLockType === "semi_weekly" ? pLockSecondDay : null,
        playoff_lineup_lock_minutes_before: playoffOverride ? (parseInt(pLineupLockMins, 10) || 0) : null,
      });
      toast.success("Roster lock rules saved");
      reloadLeague?.();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Failed to save roster lock rules");
    } finally {
      setSaving(false);
    }
  };

  const renderLockBlock = (
    prefix: string,
    type: string,
    setType: (v: string) => void,
    day: string,
    setDay: (v: string) => void,
    secondDay: string,
    setSecondDay: (v: string) => void,
    lockMins: string,
    setLockMins: (v: string) => void,
  ) => (
    <div className="space-y-4">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <div className="space-y-2">
          <Label className="text-xs">Lock cadence</Label>
          <Select value={type} onValueChange={setType}>
            <SelectTrigger className="bg-secondary border-border" data-testid={`${prefix}-lock-type`}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent className="bg-popover border-border z-50">
              <SelectItem value="daily">Daily Lock</SelectItem>
              <SelectItem value="semi_weekly">Semi-Weekly Lock</SelectItem>
              <SelectItem value="weekly">Weekly Lock</SelectItem>
            </SelectContent>
          </Select>
        </div>
        {type !== "daily" && (
          <div className="space-y-2">
            <Label className="text-xs">Primary lock day</Label>
            <Select value={day} onValueChange={setDay}>
              <SelectTrigger className="bg-secondary border-border" data-testid={`${prefix}-lock-day`}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent className="bg-popover border-border z-50">
                {DAY_OPTIONS.map((d) => (
                  <SelectItem key={d.value} value={d.value}>
                    {d.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )}
        {type === "semi_weekly" && (
          <div className="space-y-2">
            <Label className="text-xs">Second lock day</Label>
            <Select value={secondDay} onValueChange={setSecondDay}>
              <SelectTrigger className="bg-secondary border-border" data-testid={`${prefix}-lock-second-day`}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent className="bg-popover border-border z-50">
                {DAY_OPTIONS.map((d) => (
                  <SelectItem key={d.value} value={d.value}>
                    {d.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )}
      </div>
      <div className="space-y-2 max-w-md">
        <Label className="text-xs">Lineup lock time (5-min increments)</Label>
        <Select value={lockMins} onValueChange={setLockMins}>
          <SelectTrigger className="bg-secondary border-border" data-testid={`${prefix}-lineup-lock-mins`}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent className="bg-popover border-border z-50 max-h-72">
            {LOCK_TIME_OPTIONS.map((o) => (
              <SelectItem key={o.value} value={o.value}>
                {o.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <p className="text-[11px] text-muted-foreground">
          Lineup slots freeze this many minutes before the first NHL game of the scoring period.
        </p>
      </div>
    </div>
  );

  return (
    <Card className="bg-card border-border" data-testid="rules-schedule-roster-lock-card">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-lg">
          <LockKeyhole className="h-5 w-5 text-violet-400" />
          Roster Lock &amp; Lineup Lock
        </CardTitle>
        <CardDescription>
          Cadence of when transactions/lineups freeze for the scoring period.
          Optionally override the lock rules for playoff weeks only.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        <div>
          <div className="text-sm font-semibold mb-3 text-cyan-300">Regular Season Lock</div>
          {renderLockBlock(
            "regular",
            lockType,
            setLockType,
            lockDay,
            setLockDay,
            lockSecondDay,
            setLockSecondDay,
            lineupLockMins,
            setLineupLockMins,
          )}
        </div>

        <Separator />

        <div className="flex items-center gap-3">
          <Checkbox
            checked={playoffOverride}
            onCheckedChange={(c) => setPlayoffOverride(!!c)}
            id="rs-playoff-lock-override"
            data-testid="rules-schedule-playoff-lock-override"
          />
          <Label htmlFor="rs-playoff-lock-override" className="cursor-pointer text-sm">
            Change roster lock type for playoffs
          </Label>
        </div>

        {playoffOverride && (
          <div className="pl-1 border-l-2 border-amber-500/30 pl-4">
            <div className="text-sm font-semibold mb-3 text-amber-300">Playoff Lock Override</div>
            {renderLockBlock(
              "playoff",
              pLockType,
              setPLockType,
              pLockDay,
              setPLockDay,
              pLockSecondDay,
              setPLockSecondDay,
              pLineupLockMins,
              setPLineupLockMins,
            )}
          </div>
        )}

        <div className="flex justify-end">
          <Button size="sm" onClick={save} disabled={saving} data-testid="rules-schedule-roster-lock-save">
            {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4 mr-1" />}
            Save Lock Rules
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function SalaryCapCard({ league, reloadLeague }: any) {
  const [enabled, setEnabled] = useState(!!league?.salary_cap_enabled);
  const [amount, setAmount] = useState<number>(league?.salary_cap || 82500000);
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    setEnabled(!!league?.salary_cap_enabled);
    setAmount(league?.salary_cap || 82500000);
  }, [league?.id, league?.salary_cap_enabled, league?.salary_cap]);

  const save = async () => {
    setSaving(true);
    try {
      await api.put(`/leagues/${league.id}/admin/cap-settings`, {
        salary_cap_enabled: enabled,
        salary_cap: enabled ? amount : null,
      });
      toast.success(enabled ? `Salary cap set to $${fmtMoney(amount)}` : "Salary cap disabled");
      reloadLeague?.();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Failed to save salary cap");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card className="bg-card border-border" data-testid="rules-schedule-salary-cap-card">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-lg">
          <DollarSign className="h-5 w-5 text-emerald-400" />
          Salary Cap
        </CardTitle>
        <CardDescription>
          Hold the ▲/▼ buttons to accelerate by $100k → $500k → $1M.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-center gap-3">
          <Switch
            checked={enabled}
            onCheckedChange={setEnabled}
            id="rs-cap-enabled"
            data-testid="rules-schedule-cap-enabled"
          />
          <Label htmlFor="rs-cap-enabled" className="cursor-pointer">
            Enable salary cap
          </Label>
        </div>
        {enabled && (
          <div className="max-w-sm">
            <Label className="text-xs">Cap amount</Label>
            <SmartNumberInput
              value={amount}
              onChange={setAmount}
              min={0}
              max={300000000}
              step={100000}
              fastStep={500000}
              turboStep={1000000}
              prefix="$"
              format={fmtMoney}
              testId="rules-schedule-cap-amount"
            />
          </div>
        )}
        <div className="flex justify-end">
          <Button size="sm" onClick={save} disabled={saving} data-testid="rules-schedule-cap-save">
            {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4 mr-1" />}
            Save Cap
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function SalaryRetentionCard({ league, reloadLeague }: any) {
  const [enabled, setEnabled] = useState(!!league?.salary_retention_enabled);
  const [slots, setSlots] = useState<string>(String(league?.salary_retention_slots ?? 3));
  const [maxPct, setMaxPct] = useState<string>(String(league?.salary_retention_max_pct ?? 50));
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    setEnabled(!!league?.salary_retention_enabled);
    setSlots(String(league?.salary_retention_slots ?? 3));
    setMaxPct(String(league?.salary_retention_max_pct ?? 50));
  }, [league?.id, league?.salary_retention_enabled, league?.salary_retention_slots, league?.salary_retention_max_pct]);

  const save = async () => {
    const slotsN = parseInt(slots, 10);
    const pctN = parseInt(maxPct, 10);
    if (enabled) {
      if (Number.isNaN(slotsN) || slotsN < 1 || slotsN > 10) {
        toast.error("Retention slots must be between 1 and 10");
        return;
      }
      if (Number.isNaN(pctN) || pctN < 1 || pctN > 100) {
        toast.error("Max retention % must be between 1 and 100");
        return;
      }
    }
    setSaving(true);
    try {
      await api.put(`/leagues/${league.id}`, {
        salary_retention_enabled: enabled,
        salary_retention_slots: enabled ? slotsN : 0,
        salary_retention_max_pct: enabled ? pctN : 50,
      });
      toast.success(enabled ? `Retention: ${slotsN} slots @ ${pctN}% max` : "Retention disabled");
      reloadLeague?.();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Failed to save retention");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card className="bg-card border-border" data-testid="rules-schedule-retention-card">
      <CardHeader>
        <div className="flex items-center justify-between gap-4 flex-wrap">
          <div>
            <CardTitle className="flex items-center gap-2 text-lg">
              <ArrowRightLeft className="h-5 w-5 text-amber-400" />
              Salary Retention in Trades
            </CardTitle>
            <CardDescription>
              Toggle whether teams can keep paying part of a traded player's salary.
            </CardDescription>
          </div>
          {enabled && (
            <CBABadge
              slots={parseInt(slots, 10) || 0}
              maxPct={parseInt(maxPct, 10) || 0}
              testId="rules-schedule-retention-cba-badge"
            />
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-center gap-3">
          <Switch
            checked={enabled}
            onCheckedChange={setEnabled}
            id="rs-retention-enabled"
            data-testid="rules-schedule-retention-enabled"
          />
          <Label htmlFor="rs-retention-enabled" className="cursor-pointer font-semibold">
            Allow salary retention in trades?
          </Label>
        </div>
        {enabled && (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 max-w-xl">
            <div>
              <Label className="text-xs">Retention slots per team (1–10)</Label>
              <Input
                type="number"
                min={1}
                max={10}
                value={slots}
                onChange={(e) => setSlots(e.target.value)}
                data-testid="rules-schedule-retention-slots-input"
              />
            </div>
            <div>
              <Label className="text-xs">Max % of contract (1–100)</Label>
              <Input
                type="number"
                min={1}
                max={100}
                value={maxPct}
                onChange={(e) => setMaxPct(e.target.value)}
                data-testid="rules-schedule-retention-max-pct-input"
              />
            </div>
          </div>
        )}
        {!enabled && (
          <p className="text-xs text-muted-foreground italic">
            Retention is OFF — trades transfer the full contract value to the new team.
          </p>
        )}
        <div className="flex justify-end">
          <Button size="sm" onClick={save} disabled={saving} data-testid="rules-schedule-retention-save">
            {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4 mr-1" />}
            Save Retention
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
