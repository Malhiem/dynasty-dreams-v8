// @ts-nocheck
/**
 * RostersTab — wired commissioner editor for roster shape, position limits,
 * roster requirements, and IR rules. Replaces the cosmetic legacy mock that
 * showed hardcoded `defaultValue` numbers.
 *
 * All fields persist to `db.leagues` via `PUT /api/leagues/{id}` (single
 * source of truth) and are audit-logged with actor + before/after diff.
 */
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { Badge } from "@/components/ui/badge";
import { Save, Loader2, Users, ShieldAlert, ListChecks, HeartPulse } from "lucide-react";
import api from "@/lib/api";
import { useActiveLeague } from "@/hooks/use-active-league";

const POSITIONS = [
  { key: "C", label: "Centers (C)" },
  { key: "LW", label: "Left Wing (LW)" },
  { key: "RW", label: "Right Wing (RW)" },
  { key: "D", label: "Defensemen (D)" },
  { key: "G", label: "Goalies (G)" },
];

const IR_MODES = [
  { key: "IR", label: "Standard IR" },
  { key: "IR-LT", label: "Long-Term IR" },
  { key: "IR-NR", label: "Non-Recoverable IR" },
];

const parseIntOrNull = (v: string): number | null => {
  const t = (v ?? "").trim();
  if (t === "") return null;
  const n = parseInt(t, 10);
  return Number.isNaN(n) ? null : n;
};

export default function RostersTab() {
  const { league, reloadLeague } = useActiveLeague();
  const [saving, setSaving] = useState(false);

  // Roster Size
  const [rosterSpots, setRosterSpots] = useState("");
  const [benchSpots, setBenchSpots] = useState("");
  const [irSlots, setIrSlots] = useState("");
  const [irPlusSlots, setIrPlusSlots] = useState("");
  const [prospectPool, setProspectPool] = useState("");
  const [taxiSquad, setTaxiSquad] = useState("");

  // Position Limits
  const [positionLimits, setPositionLimits] = useState<Record<string, string>>({});
  const [enforcePositions, setEnforcePositions] = useState(false);

  // Requirements
  const [minActivePlayers, setMinActivePlayers] = useState("");
  const [minGamesPlayed, setMinGamesPlayed] = useState("");
  const [prorateByPeriod, setProrateByPeriod] = useState(false);
  const [allowIllegal, setAllowIllegal] = useState(true);

  // IR Settings
  const [irModes, setIrModes] = useState<string[]>(["IR"]);

  // Seed local state from the league document
  useEffect(() => {
    if (!league?.id) return;
    setRosterSpots(league.roster_spots != null ? String(league.roster_spots) : "");
    setBenchSpots(league.bench_spots != null ? String(league.bench_spots) : "");
    setIrSlots(league.ir_slots != null ? String(league.ir_slots) : "");
    setIrPlusSlots(league.ir_plus_slots != null ? String(league.ir_plus_slots) : "");
    setProspectPool(league.minors_spots != null ? String(league.minors_spots) : "");
    setTaxiSquad(league.taxi_squad_size != null ? String(league.taxi_squad_size) : "");
    const pl = league.position_limits || {};
    const seeded: Record<string, string> = {};
    for (const p of POSITIONS) seeded[p.key] = pl[p.key] != null ? String(pl[p.key]) : "";
    setPositionLimits(seeded);
    setEnforcePositions(!!league.enforce_position_maxes);
    setMinActivePlayers(league.min_active_players != null ? String(league.min_active_players) : "");
    setMinGamesPlayed(league.min_games_played != null ? String(league.min_games_played) : "");
    setProrateByPeriod(!!league.prorate_min_max_by_period);
    setAllowIllegal(league.allow_illegal_rosters !== false);
    setIrModes(Array.isArray(league.ir_eligibility_modes) ? league.ir_eligibility_modes : ["IR"]);
  }, [league?.id, league]);

  const toggleIrMode = (key: string) => {
    setIrModes((prev) => prev.includes(key) ? prev.filter((m) => m !== key) : [...prev, key]);
  };

  const buildPayload = () => {
    const payload: Record<string, any> = {};
    const numFields: Array<[string, string, number, number]> = [
      ["roster_spots", rosterSpots, 10, 40],
      ["bench_spots", benchSpots, 0, 20],
      ["ir_slots", irSlots, 0, 15],
      ["ir_plus_slots", irPlusSlots, 0, 10],
      ["minors_spots", prospectPool, 0, 20],
      ["taxi_squad_size", taxiSquad, 0, 20],
      ["min_active_players", minActivePlayers, 0, 40],
      ["min_games_played", minGamesPlayed, 0, 200],
    ];
    for (const [key, raw, lo, hi] of numFields) {
      const n = parseIntOrNull(raw);
      if (n === null) continue;
      if (n < lo || n > hi) {
        toast.error(`${key.replace(/_/g, " ")} must be between ${lo} and ${hi}`);
        return null;
      }
      payload[key] = n;
    }
    const limits: Record<string, number> = {};
    for (const p of POSITIONS) {
      const n = parseIntOrNull(positionLimits[p.key]);
      if (n !== null) limits[p.key] = n;
    }
    payload.position_limits = limits;
    payload.enforce_position_maxes = enforcePositions;
    payload.prorate_min_max_by_period = prorateByPeriod;
    payload.allow_illegal_rosters = allowIllegal;
    payload.ir_eligibility_modes = irModes;
    return payload;
  };

  const onSave = async () => {
    if (!league?.id) return;
    const payload = buildPayload();
    if (payload === null) return;
    setSaving(true);
    try {
      const { data } = await api.put(`/leagues/${league.id}`, payload);
      const changedKeys = Object.keys(data?.changes ?? {});
      if (changedKeys.length === 0) {
        toast("No changes to save", { description: "Values already match what's stored." });
      } else {
        toast.success(`Saved ${changedKeys.length} roster setting${changedKeys.length === 1 ? "" : "s"}`);
      }
      reloadLeague?.();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Failed to save roster settings");
    } finally {
      setSaving(false);
    }
  };

  if (!league?.id) {
    return (
      <Card className="bg-card border-border">
        <CardContent className="py-6 text-sm text-muted-foreground">
          Select a league to edit its roster settings.
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-6" data-testid="rosters-tab">
      <Card className="bg-card border-border">
        <CardHeader>
          <div className="flex items-center justify-between gap-4 flex-wrap">
            <div>
              <CardTitle className="flex items-center gap-2">
                <Users className="h-5 w-5 text-cyan-400" />
                Roster Configuration
              </CardTitle>
              <CardDescription>
                Every value here is persisted to{" "}
                <code className="text-xs bg-secondary px-1 rounded">db.leagues</code>{" "}
                and read by the lineup validator, waiver engine, and trade processor.
              </CardDescription>
            </div>
            <Badge variant="secondary" className="border-cyan-500/40 text-cyan-300">
              Wired to backend
            </Badge>
          </div>
        </CardHeader>
      </Card>

      {/* Roster Size */}
      <Card className="bg-card border-border" data-testid="rosters-size-card">
        <CardHeader>
          <CardTitle>Roster Size</CardTitle>
          <CardDescription>Active roster, bench, IR, and prospect pool capacity.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 md:grid-cols-4">
            <div className="space-y-2">
              <Label htmlFor="roster-size-active">Active Roster (10–40)</Label>
              <Input id="roster-size-active" type="number" min={10} max={40}
                value={rosterSpots} onChange={(e) => setRosterSpots(e.target.value)}
                placeholder="20" data-testid="rosters-roster-spots-input" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="roster-size-bench">Bench Spots (0–20)</Label>
              <Input id="roster-size-bench" type="number" min={0} max={20}
                value={benchSpots} onChange={(e) => setBenchSpots(e.target.value)}
                placeholder="4" data-testid="rosters-bench-spots-input" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="roster-size-ir">IR Slots (0–15)</Label>
              <Input id="roster-size-ir" type="number" min={0} max={15}
                value={irSlots} onChange={(e) => setIrSlots(e.target.value)}
                placeholder="3" data-testid="rosters-ir-slots-input" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="roster-size-ir-plus">IR+ Slots (0–10)</Label>
              <Input id="roster-size-ir-plus" type="number" min={0} max={10}
                value={irPlusSlots} onChange={(e) => setIrPlusSlots(e.target.value)}
                placeholder="2" data-testid="rosters-ir-plus-slots-input" />
            </div>
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="roster-size-prospects">Prospect Pool Size (0–20)</Label>
              <Input id="roster-size-prospects" type="number" min={0} max={20}
                value={prospectPool} onChange={(e) => setProspectPool(e.target.value)}
                placeholder="10" data-testid="rosters-minors-spots-input" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="roster-size-taxi">Taxi Squad Size (0–20)</Label>
              <Input id="roster-size-taxi" type="number" min={0} max={20}
                value={taxiSquad} onChange={(e) => setTaxiSquad(e.target.value)}
                placeholder="5" data-testid="rosters-taxi-squad-input" />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Position Limits */}
      <Card className="bg-card border-border" data-testid="rosters-positions-card">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <ShieldAlert className="h-5 w-5 text-amber-400" />
            Position Limits
          </CardTitle>
          <CardDescription>Maximum players allowed at each position. Leave blank for no limit.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 md:grid-cols-5">
            {POSITIONS.map((p) => (
              <div key={p.key} className="space-y-2">
                <Label htmlFor={`pos-${p.key}`}>{p.label}</Label>
                <Input
                  id={`pos-${p.key}`}
                  type="number"
                  min={0}
                  max={30}
                  value={positionLimits[p.key] ?? ""}
                  onChange={(e) =>
                    setPositionLimits((prev) => ({ ...prev, [p.key]: e.target.value }))
                  }
                  placeholder="—"
                  data-testid={`rosters-position-${p.key}-input`}
                />
              </div>
            ))}
          </div>
          <div className="flex items-center justify-between">
            <div>
              <Label>Enforce Position Maximums</Label>
              <p className="text-sm text-muted-foreground">
                Block acquisitions (waivers, trades, draft picks) that exceed any position limit.
              </p>
            </div>
            <Switch
              checked={enforcePositions}
              onCheckedChange={setEnforcePositions}
              data-testid="rosters-enforce-positions"
            />
          </div>
        </CardContent>
      </Card>

      {/* Roster Requirements */}
      <Card className="bg-card border-border" data-testid="rosters-requirements-card">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <ListChecks className="h-5 w-5 text-emerald-400" />
            Roster Requirements
          </CardTitle>
          <CardDescription>Minimums and validity rules checked by the scoring engine.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="req-min-active">Minimum Active Players (0–40)</Label>
              <Input id="req-min-active" type="number" min={0} max={40}
                value={minActivePlayers} onChange={(e) => setMinActivePlayers(e.target.value)}
                placeholder="15" data-testid="rosters-min-active-input" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="req-min-games">Minimum Games Played (0–200)</Label>
              <Input id="req-min-games" type="number" min={0} max={200}
                value={minGamesPlayed} onChange={(e) => setMinGamesPlayed(e.target.value)}
                placeholder="50" data-testid="rosters-min-games-input" />
            </div>
          </div>
          <div className="flex items-center justify-between">
            <div>
              <Label>Prorate Min/Max by Period</Label>
              <p className="text-sm text-muted-foreground">
                Adjust min-games requirements based on scoring period length.
              </p>
            </div>
            <Switch
              checked={prorateByPeriod}
              onCheckedChange={setProrateByPeriod}
              data-testid="rosters-prorate-period"
            />
          </div>
          <Separator />
          <div className="flex items-center justify-between">
            <div>
              <Label>Allow Illegal Rosters</Label>
              <p className="text-sm text-muted-foreground">
                Teams can save lineups that violate the rules above (the engine will warn but still score).
              </p>
            </div>
            <Switch
              checked={allowIllegal}
              onCheckedChange={setAllowIllegal}
              data-testid="rosters-allow-illegal"
            />
          </div>
        </CardContent>
      </Card>

      {/* IR Eligibility */}
      <Card className="bg-card border-border" data-testid="rosters-ir-card">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <HeartPulse className="h-5 w-5 text-rose-400" />
            IR Eligibility
          </CardTitle>
          <CardDescription>
            Which player status codes can occupy an IR slot. Toggle each mode on/off.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {IR_MODES.map((m) => (
            <div key={m.key} className="flex items-center justify-between">
              <div>
                <Label>{m.label}</Label>
                <p className="text-xs text-muted-foreground">Code: <code className="text-xs">{m.key}</code></p>
              </div>
              <Switch
                checked={irModes.includes(m.key)}
                onCheckedChange={() => toggleIrMode(m.key)}
                data-testid={`rosters-ir-mode-${m.key}`}
              />
            </div>
          ))}
        </CardContent>
      </Card>

      <div className="flex justify-end">
        <Button onClick={onSave} disabled={saving} className="gap-2" data-testid="rosters-save-btn">
          {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
          {saving ? "Saving…" : "Save Roster Settings"}
        </Button>
      </div>
    </div>
  );
}
