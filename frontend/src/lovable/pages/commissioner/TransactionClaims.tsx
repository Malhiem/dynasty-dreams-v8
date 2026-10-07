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

export const DEFAULT_CFG = {
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
  // Iter 231g — Trades configuration
  trades: {
    review_period_hours: 72,
    veto_threshold_teams: 4,
    max_trades_per_team: null,
    voting_system: "managers",
    anonymous_voting: true,
    lock_at_first_game: false,
    allow_before_draft: true,
    allow_during_draft: false,
    allow_illegal_rosters: false,
    comments_visible_to_all: false,
    conditional_trades_enabled: false,
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
  const [error, setError] = useState("");
  const [loadedLeague, setLoadedLeague] = useState("");
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (!leagueId) return;
    let cancelled = false;
    setLoading(true); setError(""); setLoadedLeague("");
    api.get(`/leagues/${leagueId}/transactions-config`)
      .then(({ data }) => { if (!cancelled) { setCfg(deepMerge(DEFAULT_CFG, data || {})); setLoadedLeague(leagueId); } })
      .catch(e => { if (!cancelled) setError(e?.response?.data?.detail || "Failed to load transactions configuration"); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [leagueId, attempt]);

  const save = async (next) => {
    if (loadedLeague !== leagueId || saving) return;
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

  return { cfg, setCfg, loading, saving, save, error, retry: () => setAttempt(n => n + 1) };
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
        <CardTitle>
          Claims Limits
          <InfoHint
            testId="info-claims-limits"
            text="Caps how many add/drop transactions each team can make. Per Season caps the entire year; Per Week resets every Tuesday at midnight. Leave a row blank for unlimited."
          />
        </CardTitle>
        <CardDescription>
          Per-team caps on roster claims. Toggle a field on to set a number,
          off to leave it unlimited. Season values are 1-600, weekly values
          are 1-100.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div>
          <div className="text-sm font-semibold text-foreground/80 mb-2">
            Per Season
            <InfoHint testId="info-claims-season" text="Maximum claims per team for the entire regular season. Resets at draft day each year." />
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <LimitField label="Total" value={cfg.claim_limits.season.total} onChange={set("claim_limits.season.total")} max={600} testId="claims-season-total" />
            <LimitField label="Free Agency" value={cfg.claim_limits.season.fa} onChange={set("claim_limits.season.fa")} max={600} testId="claims-season-fa" />
            <LimitField label="Waivers" value={cfg.claim_limits.season.waivers} onChange={set("claim_limits.season.waivers")} max={600} testId="claims-season-waivers" />
          </div>
        </div>
        <Separator />
        <div>
          <div className="text-sm font-semibold text-foreground/80 mb-2">
            Per Week
            <InfoHint testId="info-claims-week" text="Rolling weekly cap. Resets every Tuesday at 12:00 AM local league time. Useful for stopping waiver-wire spam." />
          </div>
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

