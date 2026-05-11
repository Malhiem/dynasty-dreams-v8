// @ts-nocheck
/**
 * Rules & Schedule — Commissioner-facing editor for every league setting that
 * the runtime now reads from `db.leagues` (single source of truth). Mirrors
 * the Setup Wizard fields so commissioners can adjust the configuration after
 * setup completes.
 *
 * Backed by `PUT /api/leagues/{id}` with a sparse payload — only changed
 * fields are persisted, and the response echoes the full canonical config so
 * the local cache stays in sync.
 */
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { Badge } from "@/components/ui/badge";
import { ArrowRightLeft, Trophy, Users, Save, Loader2, DollarSign, Calendar } from "lucide-react";
import { Switch } from "@/components/ui/switch";
import { Checkbox } from "@/components/ui/checkbox";
import SmartNumberInput from "@/components/ui/smart-number-input";
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
  {
    title: "Playoffs & Schedule",
    description: "Bracket size, start/end weeks, round count, and regular-season length.",
    icon: <Trophy className="h-5 w-5 text-violet-400" />,
    testid: "rules-schedule-playoffs-card",
    fields: [
      { key: "playoff_teams", label: "Playoff Teams", min: 2, max: 16, defaultPlaceholder: "6" },
      { key: "playoff_start_week", label: "Playoffs Start Week", min: 1, max: 30, defaultPlaceholder: "19" },
      { key: "playoff_end_week", label: "Playoffs End Week", min: 1, max: 40, defaultPlaceholder: "21" },
      { key: "playoff_rounds", label: "Playoff Rounds", min: 1, max: 5, defaultPlaceholder: "3" },
      {
        key: "regular_season_weeks",
        label: "Regular Season Weeks",
        min: 4,
        max: 30,
        helper: "Default schedule length for the season.",
        defaultPlaceholder: "18",
      },
      {
        key: "matchup_length_days",
        label: "Matchup Length (days)",
        min: 1,
        max: 30,
        helper: "Most leagues use 7 (weekly H2H).",
        defaultPlaceholder: "7",
      },
      {
        key: "opponents_per_matchup_period",
        label: "Opponents / Period",
        min: 1,
        max: 10,
        helper: "Teams played per matchup period.",
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
        // Only include if changed
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
          Select a league to edit its rules & schedule.
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
                Rules &amp; Schedule
              </CardTitle>
              <CardDescription>
                Edit every league-level setting that the runtime reads from{" "}
                <code className="text-xs bg-secondary px-1 rounded">db.leagues</code>.
                Changes are audit-logged with actor + before/after diff.
              </CardDescription>
            </div>
            <Badge variant="secondary" className="border-cyan-500/40 text-cyan-300">
              Single source of truth
            </Badge>
          </div>
        </CardHeader>
      </Card>

      {/* Salary Cap (with hold-to-accelerate) */}
      <SalaryCapCard league={league} reloadLeague={reloadLeague} />

      {/* Salary Retention A/B */}
      <SalaryRetentionCard league={league} reloadLeague={reloadLeague} />

      {/* Calendar window + consolation */}
      <CalendarConsolationCard league={league} reloadLeague={reloadLeague} />

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
        <CardTitle className="flex items-center gap-2 text-lg">
          <ArrowRightLeft className="h-5 w-5 text-amber-400" />
          Salary Retention in Trades
        </CardTitle>
        <CardDescription>
          Toggle whether teams can keep paying part of a traded player's salary.
        </CardDescription>
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

function CalendarConsolationCard({ league, reloadLeague }: any) {
  const [start, setStart] = useState<string>(league?.season_start_date || "");
  const [end, setEnd] = useState<string>(league?.season_end_date || "");
  const [consolation, setConsolation] = useState(!!league?.consolation_enabled);
  const [alongPlayoffs, setAlongPlayoffs] = useState(league?.consolation_uses_playoff_schedule !== false);
  const [consStart, setConsStart] = useState<string>(String(league?.consolation_start_week ?? ""));
  const [consEnd, setConsEnd] = useState<string>(String(league?.consolation_end_week ?? ""));
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setStart(league?.season_start_date || "");
    setEnd(league?.season_end_date || "");
    setConsolation(!!league?.consolation_enabled);
    setAlongPlayoffs(league?.consolation_uses_playoff_schedule !== false);
    setConsStart(String(league?.consolation_start_week ?? ""));
    setConsEnd(String(league?.consolation_end_week ?? ""));
  }, [
    league?.id,
    league?.season_start_date,
    league?.season_end_date,
    league?.consolation_enabled,
    league?.consolation_uses_playoff_schedule,
    league?.consolation_start_week,
    league?.consolation_end_week,
  ]);

  const save = async () => {
    setSaving(true);
    try {
      await api.put(`/leagues/${league.id}`, {
        season_start_date: start || null,
        season_end_date: end || null,
        consolation_enabled: consolation,
        consolation_uses_playoff_schedule: alongPlayoffs,
        consolation_start_week: consolation && !alongPlayoffs && consStart ? parseInt(consStart, 10) : (consolation && alongPlayoffs ? (league?.playoff_start_week || null) : null),
        consolation_end_week: consolation && !alongPlayoffs && consEnd ? parseInt(consEnd, 10) : (consolation && alongPlayoffs ? (league?.playoff_end_week || null) : null),
      });
      toast.success("Season calendar saved");
      reloadLeague?.();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Failed to save calendar");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card className="bg-card border-border" data-testid="rules-schedule-calendar-card">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-lg">
          <Calendar className="h-5 w-5 text-cyan-400" />
          Season Calendar &amp; Consolation
        </CardTitle>
        <CardDescription>
          Wall-clock start / end dates and the optional consolation bracket window.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 max-w-2xl">
          <div>
            <Label className="text-xs">Season start date</Label>
            <Input type="date" value={start} onChange={(e) => setStart(e.target.value)}
              data-testid="rules-schedule-season-start" />
          </div>
          <div>
            <Label className="text-xs">Season end date</Label>
            <Input type="date" value={end} onChange={(e) => setEnd(e.target.value)}
              data-testid="rules-schedule-season-end" />
          </div>
        </div>

        <div className="border-t border-border pt-3 space-y-3">
          <div className="flex items-center gap-3">
            <Switch checked={consolation} onCheckedChange={setConsolation}
              id="rs-consolation" data-testid="rules-schedule-consolation-enabled" />
            <Label htmlFor="rs-consolation" className="cursor-pointer font-semibold">
              Enable consolation playoff bracket
            </Label>
          </div>
          {consolation && (
            <div className="pl-1 space-y-2">
              <div className="flex items-center gap-2">
                <Checkbox checked={alongPlayoffs} onCheckedChange={(c) => setAlongPlayoffs(!!c)}
                  id="rs-consolation-along" data-testid="rules-schedule-consolation-along" />
                <Label htmlFor="rs-consolation-along" className="cursor-pointer text-sm">
                  Schedule along with the main playoffs
                </Label>
              </div>
              {!alongPlayoffs && (
                <div className="grid grid-cols-2 gap-3 max-w-lg">
                  <div>
                    <Label className="text-xs">Consolation start (week)</Label>
                    <Input type="number" min={1} max={40} value={consStart}
                      onChange={(e) => setConsStart(e.target.value)}
                      data-testid="rules-schedule-consolation-start" />
                  </div>
                  <div>
                    <Label className="text-xs">Consolation end (week)</Label>
                    <Input type="number" min={1} max={40} value={consEnd}
                      onChange={(e) => setConsEnd(e.target.value)}
                      data-testid="rules-schedule-consolation-end" />
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        <div className="flex justify-end">
          <Button size="sm" onClick={save} disabled={saving} data-testid="rules-schedule-calendar-save">
            {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4 mr-1" />}
            Save Calendar
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

