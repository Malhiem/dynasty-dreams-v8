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
import InfoHint from "@/components/ui/info-hint";
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
  // Iter 121 — "Roster Shape" removed (was a duplicate of the same controls
  // already exposed on the dedicated Rosters tab).
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
];

const ALL_KEYS = sections.flatMap((s) => s.fields.map((f) => f.key));

export default function RulesScheduleTab() {
  const { league, reloadLeague } = useActiveLeague();
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  // Iter 128 — exact trade deadline datetime. Stored separately from the
  // numeric `draft` map since this value is an ISO string and shouldn't be
  // run through `parseInt` in buildPayload. Bound to <Input type="datetime-local">.
  const [deadlineAt, setDeadlineAt] = useState<string>("");

  // Seed local draft from the league document
  useEffect(() => {
    if (!league?.id) return;
    const next: Record<string, string> = {};
    for (const key of ALL_KEYS) {
      const v = (league as any)[key];
      next[key] = v === null || v === undefined ? "" : String(v);
    }
    setDraft(next);
    // Iter 128 — seed the deadline picker; datetime-local needs "YYYY-MM-DDTHH:mm" form
    const rawAt = (league as any)?.trade_deadline_at;
    if (rawAt) {
      try {
        const d = new Date(rawAt);
        if (!Number.isNaN(d.getTime())) {
          // Convert UTC ISO → local "YYYY-MM-DDTHH:mm" for the input
          const pad = (n: number) => String(n).padStart(2, "0");
          setDeadlineAt(
            `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`,
          );
        } else {
          setDeadlineAt("");
        }
      } catch {
        setDeadlineAt("");
      }
    } else {
      setDeadlineAt("");
    }
  }, [league?.id, ...ALL_KEYS.map((k) => (league as any)?.[k]), (league as any)?.trade_deadline_at]);

  const onChange = (key: string, value: string) => {
    setDraft((prev) => ({ ...prev, [key]: value }));
  };

  const buildPayload = (): Record<string, number | string | null> | null => {
    const payload: Record<string, number | string | null> = {};
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

    // ── Iter 128: trade_deadline_at (local datetime → ISO UTC) ──
    const currentAt = (league as any)?.trade_deadline_at || null;
    const trimmed = deadlineAt.trim();
    if (trimmed === "") {
      if (currentAt) payload.trade_deadline_at = null;
    } else {
      const dt = new Date(trimmed);
      if (Number.isNaN(dt.getTime())) {
        toast.error("Trade deadline date/time is invalid");
        return null;
      }
      const iso = dt.toISOString();
      if (currentAt !== iso) payload.trade_deadline_at = iso;
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

      {/* Iter 121 — Salary Cap, Salary Retention, Contract Buyouts moved to
          the dedicated "Salary Cap and Contracts" tab. */}

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
                    {field.helper && (
                      <InfoHint
                        testId={`info-${field.key}`}
                        text={field.helper}
                      />
                    )}
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
                  {/* Iter 128 — exact trade deadline date+time picker */}
                  {field.key === "trade_deadline_week" && draft.trade_deadline_week && (
                    <div
                      className="space-y-1 mt-3 p-3 rounded-md border border-amber-500/30 bg-amber-500/5"
                      data-testid="trade-deadline-at-block"
                    >
                      <Label htmlFor="rs-trade-deadline-at" className="text-xs flex items-center">
                        Exact Trade Deadline (date &amp; time)
                        <InfoHint
                          testId="info-trade-deadline-at"
                          text="Optional: pin the deadline to an exact moment instead of waiting until the end of the configured week. When set, this datetime takes precedence over the week number. Saved in your local timezone and enforced UTC-server-side."
                        />
                      </Label>
                      <div className="flex items-center gap-2">
                        <Input
                          id="rs-trade-deadline-at"
                          type="datetime-local"
                          value={deadlineAt}
                          onChange={(e) => setDeadlineAt(e.target.value)}
                          className="bg-secondary border-border max-w-xs"
                          data-testid="rules-schedule-trade-deadline-at-input"
                        />
                        {deadlineAt && (
                          <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            className="text-xs text-muted-foreground hover:text-rose-300"
                            onClick={() => setDeadlineAt("")}
                            data-testid="rules-schedule-trade-deadline-at-clear"
                          >
                            Clear
                          </Button>
                        )}
                      </div>
                      <p className="text-[10px] text-muted-foreground">
                        {deadlineAt
                          ? `Trades lock at ${new Date(deadlineAt).toLocaleString(undefined, { weekday: "short", month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit" })} (your local time).`
                          : "Leave blank to use the week-end fallback from the value above."}
                      </p>
                    </div>
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

export function SalaryCapCard({ league, reloadLeague }: any) {
  const [enabled, setEnabled] = useState(!!league?.salary_cap_enabled);
  const [amount, setAmount] = useState<number>(league?.salary_cap || 82500000);
  // Iter 111 — future-year caps + tentative flags
  const [yr1, setYr1] = useState<number>(league?.salary_cap_year_plus_1 || (league?.salary_cap || 82500000));
  const [yr2, setYr2] = useState<number>(league?.salary_cap_year_plus_2 || (league?.salary_cap || 82500000));
  const [yr1Tentative, setYr1Tentative] = useState(!!league?.salary_cap_year_plus_1_tentative);
  const [yr2Tentative, setYr2Tentative] = useState(!!league?.salary_cap_year_plus_2_tentative);
  // Iter 120 — Cap Floor (mirrors the ceiling). Default seeds at 70% of
  // the current ceiling — typical of pro leagues. The LM can edit before
  // saving; doesn't write until enabled is on.
  const [floorEnabled, setFloorEnabled] = useState(!!league?.cap_floor_enabled);
  const [floor, setFloor] = useState<number>(league?.cap_floor || Math.round((league?.salary_cap || 82500000) * 0.7));
  const [floorYr1, setFloorYr1] = useState<number>(league?.cap_floor_year_plus_1 || Math.round((league?.salary_cap_year_plus_1 || league?.salary_cap || 82500000) * 0.7));
  const [floorYr2, setFloorYr2] = useState<number>(league?.cap_floor_year_plus_2 || Math.round((league?.salary_cap_year_plus_2 || league?.salary_cap || 82500000) * 0.7));
  const [floorYr1Tentative, setFloorYr1Tentative] = useState(!!league?.cap_floor_year_plus_1_tentative);
  const [floorYr2Tentative, setFloorYr2Tentative] = useState(!!league?.cap_floor_year_plus_2_tentative);
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    setEnabled(!!league?.salary_cap_enabled);
    setAmount(league?.salary_cap || 82500000);
    setYr1(league?.salary_cap_year_plus_1 || (league?.salary_cap || 82500000));
    setYr2(league?.salary_cap_year_plus_2 || (league?.salary_cap || 82500000));
    setYr1Tentative(!!league?.salary_cap_year_plus_1_tentative);
    setYr2Tentative(!!league?.salary_cap_year_plus_2_tentative);
    setFloorEnabled(!!league?.cap_floor_enabled);
    setFloor(league?.cap_floor || Math.round((league?.salary_cap || 82500000) * 0.7));
    setFloorYr1(league?.cap_floor_year_plus_1 || Math.round((league?.salary_cap_year_plus_1 || league?.salary_cap || 82500000) * 0.7));
    setFloorYr2(league?.cap_floor_year_plus_2 || Math.round((league?.salary_cap_year_plus_2 || league?.salary_cap || 82500000) * 0.7));
    setFloorYr1Tentative(!!league?.cap_floor_year_plus_1_tentative);
    setFloorYr2Tentative(!!league?.cap_floor_year_plus_2_tentative);
  }, [league?.id, league?.salary_cap_enabled, league?.salary_cap, league?.salary_cap_year_plus_1, league?.salary_cap_year_plus_2, league?.salary_cap_year_plus_1_tentative, league?.salary_cap_year_plus_2_tentative, league?.cap_floor_enabled, league?.cap_floor, league?.cap_floor_year_plus_1, league?.cap_floor_year_plus_2, league?.cap_floor_year_plus_1_tentative, league?.cap_floor_year_plus_2_tentative]);

  const save = async () => {
    // Iter 120 — block floors above ceilings before round-tripping to the API
    if (enabled && floorEnabled) {
      if (floor > amount) { toast.error("Cap floor can't exceed the cap ceiling"); return; }
      if (floorYr1 > yr1) { toast.error("Year+1 floor can't exceed Year+1 ceiling"); return; }
      if (floorYr2 > yr2) { toast.error("Year+2 floor can't exceed Year+2 ceiling"); return; }
    }
    setSaving(true);
    try {
      await api.put(`/leagues/${league.id}/admin/cap-settings`, {
        salary_cap_enabled: enabled,
        salary_cap: enabled ? amount : null,
        salary_cap_year_plus_1: enabled ? yr1 : null,
        salary_cap_year_plus_2: enabled ? yr2 : null,
        salary_cap_year_plus_1_tentative: yr1Tentative,
        salary_cap_year_plus_2_tentative: yr2Tentative,
        // Iter 120 — Cap Floor (only meaningful when ceiling is on)
        cap_floor_enabled: enabled && floorEnabled,
        cap_floor: enabled && floorEnabled ? floor : null,
        cap_floor_year_plus_1: enabled && floorEnabled ? floorYr1 : null,
        cap_floor_year_plus_2: enabled && floorEnabled ? floorYr2 : null,
        cap_floor_year_plus_1_tentative: floorYr1Tentative,
        cap_floor_year_plus_2_tentative: floorYr2Tentative,
      });
      toast.success(enabled ? `Salary cap set to $${fmtMoney(amount)}` : "Salary cap disabled");
      reloadLeague?.();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Failed to save salary cap");
    } finally {
      setSaving(false);
    }
  };

  const curYr = new Date().getFullYear();

  return (
    <Card className="bg-card border-border" data-testid="rules-schedule-salary-cap-card">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-lg">
          <DollarSign className="h-5 w-5 text-emerald-400" />
          Salary Cap
        </CardTitle>
        <CardDescription>
          Hold the ▲/▼ buttons to accelerate by $100k → $500k → $1M. Future-year
          caps drive the Depth-Chart multi-year cap planner.
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
            <InfoHint
              testId="info-cap-enabled"
              text="When ON, teams have a maximum payroll. Going over the cap blocks adds/trades. Pair with the Cap Floor below to also enforce a minimum payroll."
            />
          </Label>
        </div>
        {enabled && (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <Label className="text-xs">Current cap ({curYr}-{String(curYr + 1).slice(-2)})</Label>
              <SmartNumberInput
                value={amount} onChange={setAmount}
                min={0} max={300000000}
                step={100000} fastStep={500000} turboStep={1000000}
                prefix="$" format={fmtMoney}
                testId="rules-schedule-cap-amount"
              />
            </div>
            <div>
              <Label className="text-xs">Year + 1 ({curYr + 1}-{String(curYr + 2).slice(-2)})</Label>
              <SmartNumberInput
                value={yr1} onChange={setYr1}
                min={0} max={300000000}
                step={100000} fastStep={500000} turboStep={1000000}
                prefix="$" format={fmtMoney}
                testId="rules-schedule-cap-yr1"
              />
              <div className="flex items-center gap-2 mt-2">
                <Checkbox
                  id="cap-yr1-tentative"
                  checked={yr1Tentative}
                  onCheckedChange={(v) => setYr1Tentative(!!v)}
                  data-testid="rules-schedule-cap-yr1-tentative"
                />
                <Label htmlFor="cap-yr1-tentative" className="text-xs cursor-pointer">
                  Tentative — subject to change
                </Label>
              </div>
            </div>
            <div>
              <Label className="text-xs">Year + 2 ({curYr + 2}-{String(curYr + 3).slice(-2)})</Label>
              <SmartNumberInput
                value={yr2} onChange={setYr2}
                min={0} max={300000000}
                step={100000} fastStep={500000} turboStep={1000000}
                prefix="$" format={fmtMoney}
                testId="rules-schedule-cap-yr2"
              />
              <div className="flex items-center gap-2 mt-2">
                <Checkbox
                  id="cap-yr2-tentative"
                  checked={yr2Tentative}
                  onCheckedChange={(v) => setYr2Tentative(!!v)}
                  data-testid="rules-schedule-cap-yr2-tentative"
                />
                <Label htmlFor="cap-yr2-tentative" className="text-xs cursor-pointer">
                  Tentative — subject to change
                </Label>
              </div>
            </div>
          </div>
        )}

        {/* Iter 120 — Cap Floor (parallels the ceiling). Only meaningful
            when the ceiling is enabled; backend clears these fields if
            the ceiling is turned off in the same save. */}
        {enabled && (
          <div className="rounded-md border border-border p-4 space-y-3" data-testid="rules-schedule-cap-floor-block">
            <div className="flex items-center gap-3">
              <Switch
                checked={floorEnabled}
                onCheckedChange={setFloorEnabled}
                id="rs-cap-floor-enabled"
                data-testid="rules-schedule-cap-floor-enabled"
              />
              <Label htmlFor="rs-cap-floor-enabled" className="cursor-pointer text-sm">
                Enable cap floor (minimum team payroll)
                <InfoHint
                  testId="info-cap-floor-enabled"
                  text="Forces teams to spend at least this much every year. Used to stop tanking. Teams below the floor at season start trigger a Cap Floor Watchlist alert."
                />
              </Label>
            </div>
            {floorEnabled && (
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div>
                  <Label className="text-xs">Current floor ({curYr}-{String(curYr + 1).slice(-2)})</Label>
                  <SmartNumberInput
                    value={floor} onChange={setFloor}
                    min={0} max={300000000}
                    step={100000} fastStep={500000} turboStep={1000000}
                    prefix="$" format={fmtMoney}
                    testId="rules-schedule-cap-floor-amount"
                  />
                </div>
                <div>
                  <Label className="text-xs">Year + 1 floor ({curYr + 1}-{String(curYr + 2).slice(-2)})</Label>
                  <SmartNumberInput
                    value={floorYr1} onChange={setFloorYr1}
                    min={0} max={300000000}
                    step={100000} fastStep={500000} turboStep={1000000}
                    prefix="$" format={fmtMoney}
                    testId="rules-schedule-cap-floor-yr1"
                  />
                  <div className="flex items-center gap-2 mt-2">
                    <Checkbox
                      id="cap-floor-yr1-tentative"
                      checked={floorYr1Tentative}
                      onCheckedChange={(v) => setFloorYr1Tentative(!!v)}
                      data-testid="rules-schedule-cap-floor-yr1-tentative"
                    />
                    <Label htmlFor="cap-floor-yr1-tentative" className="text-xs cursor-pointer">
                      Tentative — subject to change
                    </Label>
                  </div>
                </div>
                <div>
                  <Label className="text-xs">Year + 2 floor ({curYr + 2}-{String(curYr + 3).slice(-2)})</Label>
                  <SmartNumberInput
                    value={floorYr2} onChange={setFloorYr2}
                    min={0} max={300000000}
                    step={100000} fastStep={500000} turboStep={1000000}
                    prefix="$" format={fmtMoney}
                    testId="rules-schedule-cap-floor-yr2"
                  />
                  <div className="flex items-center gap-2 mt-2">
                    <Checkbox
                      id="cap-floor-yr2-tentative"
                      checked={floorYr2Tentative}
                      onCheckedChange={(v) => setFloorYr2Tentative(!!v)}
                      data-testid="rules-schedule-cap-floor-yr2-tentative"
                    />
                    <Label htmlFor="cap-floor-yr2-tentative" className="text-xs cursor-pointer">
                      Tentative — subject to change
                    </Label>
                  </div>
                </div>
              </div>
            )}
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

export function SalaryRetentionCard({ league, reloadLeague }: any) {
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
            <InfoHint
              testId="info-retention-enabled"
              text="Mirrors the NHL CBA: when ON, the trading team can keep a % of a player's cap hit on their books to make the deal work. Configure the per-team slot count and max retained % below."
            />
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


export function ContractBuyoutsCard({ league, reloadLeague }: any) {
  const [enabled, setEnabled] = useState(!!league?.contract_buyouts_enabled);
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    setEnabled(!!league?.contract_buyouts_enabled);
  }, [league?.id, league?.contract_buyouts_enabled]);

  const save = async () => {
    setSaving(true);
    try {
      await api.put(`/leagues/${league.id}/admin/cap-settings`, {
        contract_buyouts_enabled: enabled,
      });
      toast.success(enabled ? "Contract buyouts enabled" : "Contract buyouts disabled");
      reloadLeague?.();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Failed to update buyouts setting");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card className="bg-card border-border" data-testid="rules-schedule-contract-buyouts-card">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-lg">
          <ArrowRightLeft className="h-5 w-5 text-amber-400" />
          Contract Buyouts
          <InfoHint
            testId="info-contract-buyouts"
            text="Per NHL CBA: a bought-out contract creates a dead-cap charge spread over 2× the remaining term, at roughly 1/3 of the AAV. Useful escape hatch for albatross contracts in dynasty leagues."
          />
        </CardTitle>
        <CardDescription>
          When enabled, teams may buy out a player&apos;s remaining contract. Buyouts
          create dead-cap charges spread over subsequent seasons (per NHL CBA
          convention — typically 2× the remaining term).
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex items-center gap-3">
          <Switch
            checked={enabled}
            onCheckedChange={setEnabled}
            id="rs-buyouts-enabled"
            data-testid="rules-schedule-contract-buyouts-toggle"
          />
          <Label htmlFor="rs-buyouts-enabled" className="cursor-pointer">
            Allow contract buyouts (creates dead cap)
          </Label>
        </div>
        <div className="flex justify-end">
          <Button size="sm" onClick={save} disabled={saving} data-testid="rules-schedule-contract-buyouts-save">
            {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4 mr-1" />}
            Save Buyouts
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
