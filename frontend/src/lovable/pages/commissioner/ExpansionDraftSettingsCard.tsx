// @ts-nocheck
/**
 * Iter 142 — Expansion Draft configuration card.
 *
 * Renders only when draft_type === "expansion". Captures everything the
 * league admin needs to run an expansion draft:
 *
 *   • Number of keepers (carry-over from a keeper-style setup)
 *   • Number of expansion teams
 *   • Protection rules
 *       – max_protected (0 → roster_size-1)
 *       – list visibility (public / secret) + reveal days
 *       – max_taken_per_roster (0-5)
 *   • Compensation pick
 *       – enabled + after_round
 *       – applies to: every | threshold (salary_cap | aav | fppg + value)
 *   • Pick order for expansion teams
 *       – method (manual / automatic) + snake/linear
 *   • Additional expansion picks (list)
 *       – each pick: round + placement (top/bottom/random) OR
 *         "lottery_odds" mode with an odds-array
 *   • Roster minimums
 *       – salary_cap_floor + cap_credit per_player
 */
import { useEffect, useState } from "react";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Plus, Trash2, Save } from "lucide-react";
import InfoHint from "@/components/ui/info-hint";
import { toast } from "sonner";
import api from "@/lib/api";

type Props = {
  leagueId?: string | null;
  isCommish?: boolean;
};

const DEFAULTS = {
  enabled: true,
  num_keepers: 0,
  num_expansion_teams: 1,
  protection: {
    max_protected: 8,
    list_visibility: "secret", // "public" | "secret"
    reveal_days_before: 3,
    max_taken_per_roster: 1,
  },
  compensation_pick: {
    enabled: false,
    after_round: 1,
    applies_to: "every", // "every" | "threshold"
    threshold_type: "salary_cap", // "salary_cap" | "aav" | "fppg"
    threshold_value: 5_000_000,
  },
  pick_order: {
    method: "automatic", // "automatic" | "manual"
    style: "snake", // "snake" | "linear"
  },
  expansion_picks: [] as Array<{
    round: number;
    placement: "top" | "bottom" | "random" | "lottery_odds";
    lottery_odds?: number[];
  }>,
  roster_minimums: {
    salary_cap_floor: 60_000_000,
    cap_credit_enabled: false,
    cap_credit_per_player: 0,
  },
};

export default function ExpansionDraftSettingsCard({ leagueId, isCommish }: Props) {
  const [cfg, setCfg] = useState<any>(DEFAULTS);
  const [loaded, setLoaded] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!leagueId) return;
    let cancelled = false;
    api.get(`/leagues/${leagueId}/expansion-config`).then(({ data }) => {
      if (cancelled) return;
      setCfg({ ...DEFAULTS, ...(data?.config || {}) });
      setLoaded(true);
    }).catch(() => setLoaded(true));
    return () => { cancelled = true; };
  }, [leagueId]);

  const setTop = (k: string) => (v: any) => setCfg((p: any) => ({ ...p, [k]: v }));
  const setNested = (group: string, k: string) => (v: any) =>
    setCfg((p: any) => ({ ...p, [group]: { ...(p[group] || {}), [k]: v } }));

  const addExpansionPick = () =>
    setCfg((p: any) => ({
      ...p,
      expansion_picks: [...(p.expansion_picks || []), { round: 1, placement: "top" }],
    }));
  const removeExpansionPick = (idx: number) =>
    setCfg((p: any) => ({
      ...p,
      expansion_picks: (p.expansion_picks || []).filter((_: any, i: number) => i !== idx),
    }));
  const updatePick = (idx: number, key: string, value: any) =>
    setCfg((p: any) => ({
      ...p,
      expansion_picks: (p.expansion_picks || []).map((row: any, i: number) =>
        i === idx ? { ...row, [key]: value } : row,
      ),
    }));

  const save = async () => {
    if (!leagueId) return;
    setSaving(true);
    try {
      await api.put(`/leagues/${leagueId}/expansion-config`, { config: cfg });
      toast.success("Expansion draft configuration saved");
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Failed to save expansion config");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-4" data-testid="expansion-settings-card">
      <div>
        <Label className="text-sm">Expansion Draft Settings</Label>
        <p className="text-xs text-muted-foreground">
          Configure protection rules, compensation picks, additional expansion picks, and
          roster minimums for the expansion draft.
        </p>
      </div>

      {/* Counts */}
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label className="text-xs" htmlFor="exp-num-keepers">
            Number of keepers
            <InfoHint testId="info-exp-num-keepers" text="Players each existing team keeps from their current roster before the expansion draft." />
          </Label>
          <Input
            id="exp-num-keepers"
            type="number"
            min={0}
            max={50}
            value={cfg.num_keepers}
            disabled={!isCommish}
            onChange={(e) => setTop("num_keepers")(Number(e.target.value || 0))}
            data-testid="expansion-num-keepers-input"
          />
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs" htmlFor="exp-num-teams">
            Number of expansion teams
          </Label>
          <Input
            id="exp-num-teams"
            type="number"
            min={1}
            max={10}
            value={cfg.num_expansion_teams}
            disabled={!isCommish}
            onChange={(e) => setTop("num_expansion_teams")(Number(e.target.value || 0))}
            data-testid="expansion-num-teams-input"
          />
        </div>
      </div>

      {/* Protection rules */}
      <div className="rounded-md border border-border p-3 space-y-3" data-testid="expansion-protection-block">
        <Label className="text-sm">Protection Rules</Label>
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label className="text-xs" htmlFor="exp-prot-max">
              Players a team may protect
              <InfoHint testId="info-exp-protect-max" text="From 0 up to (full roster − 1). Higher values protect more players from selection." />
            </Label>
            <Input
              id="exp-prot-max"
              type="number"
              min={0}
              max={50}
              value={cfg.protection.max_protected}
              disabled={!isCommish}
              onChange={(e) => setNested("protection", "max_protected")(Number(e.target.value || 0))}
              data-testid="expansion-protect-max-input"
            />
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs">Protection list visibility</Label>
            <Select
              value={cfg.protection.list_visibility}
              onValueChange={setNested("protection", "list_visibility")}
              disabled={!isCommish}
            >
              <SelectTrigger data-testid="expansion-visibility-trigger">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="public" data-testid="expansion-visibility-public">Public before expansion draft</SelectItem>
                <SelectItem value="secret" data-testid="expansion-visibility-secret">Secret until expansion draft</SelectItem>
              </SelectContent>
            </Select>
          </div>
          {cfg.protection.list_visibility === "public" && (
            <div className="space-y-1.5">
              <Label className="text-xs" htmlFor="exp-reveal-days">
                Reveal protection lists (days before)
              </Label>
              <Input
                id="exp-reveal-days"
                type="number"
                min={0}
                max={60}
                value={cfg.protection.reveal_days_before}
                disabled={!isCommish}
                onChange={(e) => setNested("protection", "reveal_days_before")(Number(e.target.value || 0))}
                data-testid="expansion-reveal-days-input"
              />
            </div>
          )}
          <div className="space-y-1.5">
            <Label className="text-xs" htmlFor="exp-max-taken">
              Max players taken from a single roster (0-5)
            </Label>
            <Input
              id="exp-max-taken"
              type="number"
              min={0}
              max={5}
              value={cfg.protection.max_taken_per_roster}
              disabled={!isCommish}
              onChange={(e) => setNested("protection", "max_taken_per_roster")(Number(e.target.value || 0))}
              data-testid="expansion-max-taken-input"
            />
          </div>
        </div>
      </div>

      {/* Compensation pick */}
      <div className="rounded-md border border-border p-3 space-y-3" data-testid="expansion-compensation-block">
        <div className="flex items-center justify-between">
          <Label className="text-sm" htmlFor="exp-comp-switch">
            Compensation Pick
            <InfoHint testId="info-exp-comp" text="Award an extra pick to existing teams that lose a player to the expansion draft." />
          </Label>
          <Switch
            id="exp-comp-switch"
            checked={!!cfg.compensation_pick.enabled}
            disabled={!isCommish}
            onCheckedChange={setNested("compensation_pick", "enabled")}
            data-testid="expansion-comp-switch"
          />
        </div>
        {cfg.compensation_pick.enabled && (
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label className="text-xs" htmlFor="exp-comp-after">After which round?</Label>
              <Input
                id="exp-comp-after"
                type="number"
                min={1}
                max={30}
                value={cfg.compensation_pick.after_round}
                disabled={!isCommish}
                onChange={(e) => setNested("compensation_pick", "after_round")(Number(e.target.value || 0))}
                data-testid="expansion-comp-after-input"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Applies to</Label>
              <Select
                value={cfg.compensation_pick.applies_to}
                onValueChange={setNested("compensation_pick", "applies_to")}
                disabled={!isCommish}
              >
                <SelectTrigger data-testid="expansion-comp-applies-trigger">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="every" data-testid="expansion-comp-applies-every">Every selection</SelectItem>
                  <SelectItem value="threshold" data-testid="expansion-comp-applies-threshold">Only above a value threshold</SelectItem>
                </SelectContent>
              </Select>
            </div>
            {cfg.compensation_pick.applies_to === "threshold" && (
              <>
                <div className="space-y-1.5">
                  <Label className="text-xs">Threshold type</Label>
                  <Select
                    value={cfg.compensation_pick.threshold_type}
                    onValueChange={setNested("compensation_pick", "threshold_type")}
                    disabled={!isCommish}
                  >
                    <SelectTrigger data-testid="expansion-comp-threshold-type-trigger">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="salary_cap">Salary cap hit</SelectItem>
                      <SelectItem value="aav">AAV</SelectItem>
                      <SelectItem value="fppg">Fantasy points / game</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs" htmlFor="exp-comp-threshold-value">Threshold value</Label>
                  <Input
                    id="exp-comp-threshold-value"
                    type="number"
                    min={0}
                    step={cfg.compensation_pick.threshold_type === "fppg" ? 0.1 : 100_000}
                    value={cfg.compensation_pick.threshold_value}
                    disabled={!isCommish}
                    onChange={(e) => setNested("compensation_pick", "threshold_value")(Number(e.target.value || 0))}
                    data-testid="expansion-comp-threshold-value-input"
                  />
                </div>
              </>
            )}
          </div>
        )}
      </div>

      {/* Pick order */}
      <div className="rounded-md border border-border p-3 space-y-3" data-testid="expansion-pick-order-block">
        <Label className="text-sm">Pick Order for Expansion Teams</Label>
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label className="text-xs">Method</Label>
            <Select
              value={cfg.pick_order.method}
              onValueChange={setNested("pick_order", "method")}
              disabled={!isCommish}
            >
              <SelectTrigger data-testid="expansion-order-method-trigger">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="automatic" data-testid="expansion-order-method-automatic">Automatic</SelectItem>
                <SelectItem value="manual" data-testid="expansion-order-method-manual">Manual</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs">Order style</Label>
            <Select
              value={cfg.pick_order.style}
              onValueChange={setNested("pick_order", "style")}
              disabled={!isCommish}
            >
              <SelectTrigger data-testid="expansion-order-style-trigger">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="snake" data-testid="expansion-order-style-snake">Snake</SelectItem>
                <SelectItem value="linear" data-testid="expansion-order-style-linear">Linear</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
      </div>

      {/* Additional expansion picks */}
      <div className="rounded-md border border-border p-3 space-y-3" data-testid="expansion-picks-block">
        <div className="flex items-center justify-between">
          <Label className="text-sm">
            Expansion Team Picks
            <InfoHint testId="info-expansion-picks" text="Additional picks awarded to expansion teams. Each entry can be placed at the top, bottom, or random within a chosen round — or assigned draft lottery odds." />
          </Label>
          {isCommish && (
            <Button
              size="sm"
              variant="outline"
              onClick={addExpansionPick}
              data-testid="expansion-picks-add"
            >
              <Plus className="h-4 w-4 mr-1" /> Add
            </Button>
          )}
        </div>
        {(cfg.expansion_picks || []).length === 0 && (
          <p className="text-xs italic text-muted-foreground">No additional picks configured.</p>
        )}
        {(cfg.expansion_picks || []).map((row: any, idx: number) => (
          <div
            key={idx}
            className="flex flex-wrap items-end gap-2 border-t border-border/60 pt-2 first:border-t-0 first:pt-0"
            data-testid={`expansion-pick-row-${idx}`}
          >
            <div className="space-y-1">
              <Label className="text-[10px] uppercase tracking-wider">Round</Label>
              <Input
                type="number"
                min={1}
                max={30}
                value={row.round}
                disabled={!isCommish}
                onChange={(e) => updatePick(idx, "round", Number(e.target.value || 1))}
                className="w-20"
                data-testid={`expansion-pick-round-${idx}`}
              />
            </div>
            <div className="space-y-1">
              <Label className="text-[10px] uppercase tracking-wider">Placement</Label>
              <Select
                value={row.placement}
                onValueChange={(v) => updatePick(idx, "placement", v)}
                disabled={!isCommish}
              >
                <SelectTrigger className="w-[180px]" data-testid={`expansion-pick-placement-${idx}`}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="top">Top of round</SelectItem>
                  <SelectItem value="bottom">Bottom of round</SelectItem>
                  <SelectItem value="random">Random in round</SelectItem>
                  <SelectItem value="lottery_odds">Draft lottery odds</SelectItem>
                </SelectContent>
              </Select>
            </div>
            {row.placement === "lottery_odds" && (
              <div className="space-y-1 flex-1 min-w-[200px]">
                <Label className="text-[10px] uppercase tracking-wider">
                  Lottery odds (comma-separated, %)
                </Label>
                <Input
                  value={(row.lottery_odds || []).join(",")}
                  disabled={!isCommish}
                  onChange={(e) => {
                    const arr = e.target.value
                      .split(",")
                      .map((s) => Number(s.trim()))
                      .filter((n) => !Number.isNaN(n));
                    updatePick(idx, "lottery_odds", arr);
                  }}
                  placeholder="18.5, 13.5, 11.5, …"
                  data-testid={`expansion-pick-lottery-${idx}`}
                />
              </div>
            )}
            {isCommish && (
              <Button
                size="icon"
                variant="ghost"
                onClick={() => removeExpansionPick(idx)}
                data-testid={`expansion-pick-remove-${idx}`}
                aria-label="Remove pick"
              >
                <Trash2 className="h-4 w-4" />
              </Button>
            )}
          </div>
        ))}
      </div>

      {/* Roster minimums */}
      <div className="rounded-md border border-border p-3 space-y-3" data-testid="expansion-minimums-block">
        <Label className="text-sm">
          Roster Minimums
          <InfoHint testId="info-exp-minimums" text="Set a salary cap floor each team must meet after the expansion draft. Optionally award a cap credit to teams that lose a player to expansion." />
        </Label>
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label className="text-xs" htmlFor="exp-cap-floor">Salary cap floor ($)</Label>
            <Input
              id="exp-cap-floor"
              type="number"
              min={0}
              step={100_000}
              value={cfg.roster_minimums.salary_cap_floor}
              disabled={!isCommish}
              onChange={(e) => setNested("roster_minimums", "salary_cap_floor")(Number(e.target.value || 0))}
              data-testid="expansion-cap-floor-input"
            />
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs flex items-center gap-2" htmlFor="exp-cap-credit-switch">
              Cap credit for losing a player
              <Switch
                id="exp-cap-credit-switch"
                checked={!!cfg.roster_minimums.cap_credit_enabled}
                disabled={!isCommish}
                onCheckedChange={setNested("roster_minimums", "cap_credit_enabled")}
                data-testid="expansion-cap-credit-switch"
              />
            </Label>
            {cfg.roster_minimums.cap_credit_enabled && (
              <Input
                type="number"
                min={0}
                step={100_000}
                value={cfg.roster_minimums.cap_credit_per_player}
                disabled={!isCommish}
                onChange={(e) => setNested("roster_minimums", "cap_credit_per_player")(Number(e.target.value || 0))}
                data-testid="expansion-cap-credit-value-input"
              />
            )}
          </div>
        </div>
      </div>

      {isCommish ? (
        <div className="flex justify-end">
          <Button size="sm" onClick={save} disabled={saving || !loaded} data-testid="expansion-save">
            <Save className="h-4 w-4 mr-1" /> Save expansion settings
          </Button>
        </div>
      ) : (
        <div className="text-xs italic text-muted-foreground">
          Only commissioners may change expansion draft settings.
        </div>
      )}
    </div>
  );
}
