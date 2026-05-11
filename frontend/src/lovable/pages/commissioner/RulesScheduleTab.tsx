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
import { ArrowRightLeft, Trophy, Users, Save, Loader2 } from "lucide-react";
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
    description: "Bracket size, start week, round count, and regular-season length.",
    icon: <Trophy className="h-5 w-5 text-violet-400" />,
    testid: "rules-schedule-playoffs-card",
    fields: [
      { key: "playoff_teams", label: "Playoff Teams", min: 2, max: 16, defaultPlaceholder: "6" },
      { key: "playoff_start_week", label: "Playoffs Start Week", min: 1, max: 30, defaultPlaceholder: "19" },
      { key: "playoff_rounds", label: "Playoff Rounds", min: 1, max: 5, defaultPlaceholder: "3" },
      {
        key: "regular_season_weeks",
        label: "Regular Season Weeks",
        min: 4,
        max: 30,
        helper: "Default schedule length for the season.",
        defaultPlaceholder: "18",
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
