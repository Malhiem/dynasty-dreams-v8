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

