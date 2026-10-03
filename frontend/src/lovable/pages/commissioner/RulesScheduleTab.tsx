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
import { ClockPicker } from "@/components/ui/clock-picker";
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
                  {/* Iter 128/130 — exact trade deadline picker, now split into
                      separate Date + Time inputs so users can clearly see they
                      need to set both (the combined datetime-local input was
                      reading as "date only" because the time field is rendered
                      inside the calendar popover on most browsers). */}
                  {field.key === "trade_deadline_week" && draft.trade_deadline_week && (
                    <div
                      className="space-y-2 mt-3 p-3 rounded-md border border-amber-500/30 bg-amber-500/5"
                      data-testid="trade-deadline-at-block"
                    >
                      <Label htmlFor="rs-trade-deadline-at-date" className="text-xs flex items-center">
                        Exact Trade Deadline (date &amp; time)
                        <InfoHint
                          testId="info-trade-deadline-at"
                          text="Optional: pin the deadline to an exact moment instead of waiting until the end of the configured week. Set BOTH the date and the time inputs — saved in your local timezone, enforced UTC server-side."
                        />
                      </Label>
                      <div className="flex flex-wrap items-end gap-2">
                        <div className="flex flex-col gap-1">
                          <span className="text-[10px] uppercase tracking-wide text-muted-foreground">
                            Date
                          </span>
                          <Input
                            id="rs-trade-deadline-at-date"
                            type="date"
                            value={deadlineAt.slice(0, 10)}
                            onChange={(e) => {
                              const date = e.target.value;
                              const time = deadlineAt.slice(11, 16) || "12:00";
                              setDeadlineAt(date ? `${date}T${time}` : "");
                            }}
                            className="bg-secondary border-border w-40"
                            data-testid="rules-schedule-trade-deadline-at-date-input"
                          />
                        </div>
                        <div className="flex flex-col gap-1">
                          <span className="text-[10px] uppercase tracking-wide text-muted-foreground">
                            Time
                          </span>
                          <ClockPicker
                            value={deadlineAt.slice(11, 16)}
                            onChange={(time) => {
                              const t = time || "12:00";
                              const date = deadlineAt.slice(0, 10);
                              if (date) setDeadlineAt(`${date}T${t}`);
                            }}
                            disabled={!deadlineAt.slice(0, 10)}
                            className="w-32"
                            data-testid="rules-schedule-trade-deadline-at-time-input"
                          />
                        </div>
                        {/* Iter 128 — hidden combined input preserved for legacy
                            tests that target the datetime-local testid. */}
                        <Input
                          id="rs-trade-deadline-at"
                          type="datetime-local"
                          value={deadlineAt}
                          onChange={(e) => setDeadlineAt(e.target.value)}
                          className="hidden"
                          data-testid="rules-schedule-trade-deadline-at-input"
                          tabIndex={-1}
                          aria-hidden="true"
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
                        {deadlineAt && deadlineAt.length >= 16
                          ? `Trades lock at ${new Date(deadlineAt).toLocaleString(undefined, { weekday: "short", month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit" })} (your local time).`
                          : deadlineAt
                            ? "Now set the time using the field above ↑"
                            : "Leave both blank to use the week-end fallback from the value above."}
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

// ─── Re-export cards extracted to rules-cards/ (iter 228c) ────────
export { RosterLockCard } from "./rules-cards/RosterLockCard";
export { SalaryCapCard } from "./rules-cards/SalaryCapCard";
export { SalaryRetentionCard } from "./rules-cards/SalaryRetentionCard";
export { ContractBuyoutsCard } from "./rules-cards/ContractBuyoutsCard";
