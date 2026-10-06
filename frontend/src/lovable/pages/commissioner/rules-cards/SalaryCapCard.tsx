// @ts-nocheck
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Checkbox } from "@/components/ui/checkbox";
import { DollarSign, Save, Loader2 } from "lucide-react";
import SmartNumberInput from "@/components/ui/smart-number-input";
import InfoHint from "@/components/ui/info-hint";
import api from "@/lib/api";
import { fmtMoney } from "./_shared";

export function SalaryCapCard({ league, reloadLeague }: any) {
  const [adherence, setAdherence] = useState(league?.salary_adherence_mode || "informal");
  const [irCharge, setIrCharge] = useState(league?.ir_salary_charge_pct ?? 100);
  const [target, setTarget] = useState(league?.draft_roster_target ?? ((league?.roster_spots || 20) + (league?.bench_spots || 0) + (league?.minors_spots || 0)));
  useEffect(() => {
    setAdherence(league?.salary_adherence_mode || "informal");
    setIrCharge(league?.ir_salary_charge_pct ?? 100);
    setTarget(league?.draft_roster_target ?? ((league?.roster_spots || 20) + (league?.bench_spots || 0) + (league?.minors_spots || 0)));
  }, [league]);
  const [enabled, setEnabled] = useState(!!league?.salary_cap_enabled);
  const [amount, setAmount] = useState<number>(league?.salary_cap ?? 82500000);
  // Iter 111 — future-year caps + tentative flags
  const [yr1, setYr1] = useState<number>(league?.salary_cap_year_plus_1 ?? (league?.salary_cap ?? 82500000));
  const [yr2, setYr2] = useState<number>(league?.salary_cap_year_plus_2 ?? (league?.salary_cap ?? 82500000));
  const [yr1Tentative, setYr1Tentative] = useState(!!league?.salary_cap_year_plus_1_tentative);
  const [yr2Tentative, setYr2Tentative] = useState(!!league?.salary_cap_year_plus_2_tentative);
  // Iter 120 — Cap Floor (mirrors the ceiling). Default seeds at 70% of
  // the current ceiling — typical of pro leagues. The LM can edit before
  // saving; doesn't write until enabled is on.
  const [floorEnabled, setFloorEnabled] = useState(!!league?.cap_floor_enabled);
  const [floor, setFloor] = useState<number>(league?.cap_floor ?? Math.round((league?.salary_cap ?? 82500000) * 0.7));
  const [floorYr1, setFloorYr1] = useState<number>(league?.cap_floor_year_plus_1 ?? Math.round((league?.salary_cap_year_plus_1 ?? league?.salary_cap ?? 82500000) * 0.7));
  const [floorYr2, setFloorYr2] = useState<number>(league?.cap_floor_year_plus_2 ?? Math.round((league?.salary_cap_year_plus_2 ?? league?.salary_cap ?? 82500000) * 0.7));
  const [floorYr1Tentative, setFloorYr1Tentative] = useState(!!league?.cap_floor_year_plus_1_tentative);
  const [floorYr2Tentative, setFloorYr2Tentative] = useState(!!league?.cap_floor_year_plus_2_tentative);
  // Iter 232N.62 — Draft cap view settings (default rookie AAV +
  // treatment of minors against cap)
  const [defaultRookieAav, setDefaultRookieAav] = useState<number>(
    league?.default_rookie_aav ?? 950_000,
  );
  const [minorsCapTreatment, setMinorsCapTreatment] = useState<string>(
    league?.minors_cap_treatment || "full",
  );
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    setEnabled(!!league?.salary_cap_enabled);
    setAmount(league?.salary_cap ?? 82500000);
    setYr1(league?.salary_cap_year_plus_1 ?? (league?.salary_cap ?? 82500000));
    setYr2(league?.salary_cap_year_plus_2 ?? (league?.salary_cap ?? 82500000));
    setYr1Tentative(!!league?.salary_cap_year_plus_1_tentative);
    setYr2Tentative(!!league?.salary_cap_year_plus_2_tentative);
    setFloorEnabled(!!league?.cap_floor_enabled);
    setFloor(league?.cap_floor ?? Math.round((league?.salary_cap ?? 82500000) * 0.7));
    setFloorYr1(league?.cap_floor_year_plus_1 ?? Math.round((league?.salary_cap_year_plus_1 ?? league?.salary_cap ?? 82500000) * 0.7));
    setFloorYr2(league?.cap_floor_year_plus_2 ?? Math.round((league?.salary_cap_year_plus_2 ?? league?.salary_cap ?? 82500000) * 0.7));
    setFloorYr1Tentative(!!league?.cap_floor_year_plus_1_tentative);
    setFloorYr2Tentative(!!league?.cap_floor_year_plus_2_tentative);
    setDefaultRookieAav(league?.default_rookie_aav ?? 950_000);
    setMinorsCapTreatment(league?.minors_cap_treatment || "full");
  }, [league?.id, league?.salary_cap_enabled, league?.salary_cap, league?.salary_cap_year_plus_1, league?.salary_cap_year_plus_2, league?.salary_cap_year_plus_1_tentative, league?.salary_cap_year_plus_2_tentative, league?.cap_floor_enabled, league?.cap_floor, league?.cap_floor_year_plus_1, league?.cap_floor_year_plus_2, league?.cap_floor_year_plus_1_tentative, league?.cap_floor_year_plus_2_tentative, league?.default_rookie_aav, league?.minors_cap_treatment]);

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
        salary_adherence_mode: adherence,
        ir_salary_charge_pct: Number(irCharge),
        draft_roster_target: Number(target),
        salary_cap_enabled: enabled,
        salary_cap: enabled ? amount : null,
        salary_cap_year_plus_1: enabled ? yr1 : null,
        salary_cap_year_plus_2: enabled ? yr2 : null,
        salary_cap_year_plus_1_tentative: yr1Tentative,
        salary_cap_year_plus_2_tentative: yr2Tentative,
        // Floor can be enabled independently of the ceiling.
        cap_floor_enabled: floorEnabled,
        cap_floor: floorEnabled ? floor : null,
        cap_floor_year_plus_1: floorEnabled ? floorYr1 : null,
        cap_floor_year_plus_2: floorEnabled ? floorYr2 : null,
        cap_floor_year_plus_1_tentative: floorYr1Tentative,
        cap_floor_year_plus_2_tentative: floorYr2Tentative,
        // Iter 232N.62 — Draft cap view settings
        default_rookie_aav: defaultRookieAav,
        minors_cap_treatment: minorsCapTreatment,
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

        {/* Minimum payroll can be configured without a ceiling. */}
        {(
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
        {/* Iter 232N.62 — Draft-room cap view settings */}
        {(enabled || floorEnabled) && (
          <div className="pt-3 border-t border-border/40 space-y-3">
            <div className="text-[10px] uppercase tracking-wider text-muted-foreground">
              Draft-room cap view
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div>
                <Label className="text-[11px]">
                  Default rookie / unpriced AAV
                </Label>
                <p className="text-[10px] text-muted-foreground mb-1">
                  Charged for undrafted rookies + free agents with no
                  contract on file (used in cap view + greying).
                </p>
                <input
                  type="number"
                  min={0}
                  step={50_000}
                  value={defaultRookieAav}
                  onChange={(e) =>
                    setDefaultRookieAav(Number(e.target.value) || 0)
                  }
                  className="w-full h-9 px-2 rounded-md bg-secondary/40 border border-border/60 text-xs font-mono"
                  data-testid="rules-cap-default-rookie-aav"
                />
              </div>
              <div>
                <Label className="text-[11px]">
                  Count minor-league players against cap?
                </Label>
                <p className="text-[10px] text-muted-foreground mb-1">
                  How minors contracts factor into cap calculations.
                </p>
                <select
                  value={minorsCapTreatment}
                  onChange={(e) => setMinorsCapTreatment(e.target.value)}
                  className="w-full h-9 px-2 rounded-md bg-secondary/40 border border-border/60 text-xs"
                  data-testid="rules-cap-minors-treatment"
                >
                  <option value="full">Yes — full value</option>
                  <option value="default">Yes — default AAV</option>
                  <option value="tiered">Yes — tiered value</option>
                  <option value="none">No — minors are cap-exempt</option>
                </select>
              </div>
            </div>
          </div>
        )}
        <div className="space-y-3 border-t border-border pt-3">
          <label className="block">Draft salary adherence
            <select aria-label="Draft salary adherence" value={adherence} onChange={e => setAdherence(e.target.value)} className="ml-2 bg-secondary p-2 rounded">
              <option value="strict">Strict</option><option value="informal">Informal</option>
            </select>
          </label>
          <p className="text-xs text-muted-foreground">Strict blocks selections that cannot complete within salary bounds. Informal warns and allows post-draft adjustments.</p>
          <label className="block">Required draft roster size (excludes IR)
            <input aria-label="Required draft roster size" type="number" min="1" max="200" value={target} onChange={e => setTarget(e.target.value)} className="ml-2 bg-secondary p-2 rounded w-24" />
          </label>
          <label className="block">Salary charged on IR (%)
            <input aria-label="Salary charged on IR (%)" type="number" min="0" max="100" value={irCharge} onChange={e => setIrCharge(e.target.value)} className="ml-2 bg-secondary p-2 rounded w-24" />
          </label>
          <p className="text-xs text-muted-foreground">100% charges full salary; 0% exempts IR. IR relief can also reduce payroll below the floor.</p>
        </div>
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

