// @ts-nocheck
/**
 * RostersTab — wired commissioner editor for roster shape, position breakdown,
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
import InfoHint from "@/components/ui/info-hint";
import { useActiveLeague } from "@/hooks/use-active-league";

// Iter 176 — Expanded position taxonomy for "Position Breakdown".
// `S` (Skater) and `W` (Wing) are categorical buckets; the
// enforcement helper treats them as supersets:
//   S → matches any non-goalie player
//   W → matches LW or RW
// Leaving any cell blank disables that limit (no restriction).
const POSITIONS = [
  { key: "S", label: "Skater (S)", help: "Any non-goalie. Covers C, LW, RW, and D." },
  { key: "C", label: "Center (C)", help: "" },
  { key: "LW", label: "Left Wing (LW)", help: "" },
  { key: "RW", label: "Right Wing (RW)", help: "" },
  { key: "W", label: "Wing (W)", help: "Either LW or RW. Useful when leagues lump wingers together." },
  { key: "D", label: "Defenseman (D)", help: "" },
  { key: "G", label: "Goalie (G)", help: "" },
];

// Iter 176 — Three editable rows. `bench` and `minors` are only
// surfaced when the league actually has those sections enabled
// (benchSpots > 0 / minors_enabled).
// Iter 177 — Added a second bench row ("Bench Reserve") so leagues
// that run a tiered bench (e.g. active bench + deep reserve) can cap
// each tier independently. Both bench rows share the same
// visibility predicate.
// Iter 180 — User feedback: the "Bench (Reserve)" tier was
// confusingly redundant with the Minors row. Dropped from the UI
// (still kept in state shape + save payload for backward compat with
// any leagues that wrote bench2 caps under iter 177 — those values
// stay in Mongo, just no longer rendered). Minors row visibility
// widened so it surfaces whenever the league has bench spots OR
// minors capacity OR pre-existing saved data — no more "where did
// my row go" confusion when toggling premium features.
const BREAKDOWN_ROWS: Array<{ key: "active" | "bench" | "bench2" | "minors"; label: string; help: string }> = [
  { key: "active", label: "Active Roster",
    help: "Players eligible to earn points each scoring period. The total Active Roster size is the SUM of the values you enter on this row — leave a cell blank to keep it unlimited." },
  { key: "bench",  label: "Bench",
    help: "Reserves that don't earn points but still count against the cap. Only shown when the league has bench spots configured." },
  { key: "minors", label: "Minors",
    help: "Farm-system slots (minor-eligible prospects). Surfaces whenever the league has bench spots configured, minors capacity, or existing saved caps." },
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

  // Iter 176 — Position Breakdown: three editable rows (active / bench
  // / minors) each holding the same 7-position dict. Leaving any cell
  // blank means "no limit" for that row+position. The Active row's
  // sum (when any value is set) drives the league's `roster_spots`.
  const [positionBreakdown, setPositionBreakdown] = useState<{
    active: Record<string, string>;
    bench: Record<string, string>;
    bench2: Record<string, string>;
    minors: Record<string, string>;
  }>({ active: {}, bench: {}, bench2: {}, minors: {} });
  const [enforcePositions, setEnforcePositions] = useState(false);

  // Requirements
  const [minActivePlayers, setMinActivePlayers] = useState("");
  const [minGamesPlayed, setMinGamesPlayed] = useState("");
  const [prorateByPeriod, setProrateByPeriod] = useState(false);
  const [allowIllegal, setAllowIllegal] = useState(true);

  // IR Settings
  const [irModes, setIrModes] = useState<string[]>(["IR"]);

  // Iter 121 — Prospect eligibility guidelines (consumed by waiver-section
  // `prevent_prospects` toggle in League Admin → Transactions). Defaults
  // mirror the NHL convention used by the enforcement helper.
  const [prospectMaxAge, setProspectMaxAge] = useState("");
  const [prospectMaxGames, setProspectMaxGames] = useState("");

  // Seed local state from the league document
  useEffect(() => {
    if (!league?.id) return;
    setRosterSpots(league.roster_spots != null ? String(league.roster_spots) : "");
    setBenchSpots(league.bench_spots != null ? String(league.bench_spots) : "");
    setIrSlots(league.ir_slots != null ? String(league.ir_slots) : "");
    setIrPlusSlots(league.ir_plus_slots != null ? String(league.ir_plus_slots) : "");
    setProspectPool(league.minors_spots != null ? String(league.minors_spots) : "");
    setTaxiSquad(league.taxi_squad_size != null ? String(league.taxi_squad_size) : "");
    // Iter 176/177 — Hydrate the 3- (or 4-, when bench-reserve is in
    // use) row Position Breakdown. New canonical field is
    // `position_breakdown`; legacy `position_limits` (single dict,
    // active-row only) is migrated transparently on first save.
    const breakdownDoc = (league as any).position_breakdown
      || { active: league.position_limits || {}, bench: {}, bench2: {}, minors: {} };
    const hydrateRow = (src: Record<string, any> | undefined): Record<string, string> => {
      const out: Record<string, string> = {};
      for (const p of POSITIONS) {
        out[p.key] = src && src[p.key] != null ? String(src[p.key]) : "";
      }
      return out;
    };
    setPositionBreakdown({
      active: hydrateRow(breakdownDoc.active),
      bench: hydrateRow(breakdownDoc.bench),
      bench2: hydrateRow(breakdownDoc.bench2),
      minors: hydrateRow(breakdownDoc.minors),
    });
    setEnforcePositions(!!league.enforce_position_maxes);
    setMinActivePlayers(league.min_active_players != null ? String(league.min_active_players) : "");
    setMinGamesPlayed(league.min_games_played != null ? String(league.min_games_played) : "");
    setProrateByPeriod(!!league.prorate_min_max_by_period);
    setAllowIllegal(league.allow_illegal_rosters !== false);
    setIrModes(Array.isArray(league.ir_eligibility_modes) ? league.ir_eligibility_modes : ["IR"]);
    setProspectMaxAge(league.prospect_max_age != null ? String(league.prospect_max_age) : "");
    setProspectMaxGames(league.prospect_max_career_games != null ? String(league.prospect_max_career_games) : "");
  }, [league?.id, league]);

  const toggleIrMode = (key: string) => {
    setIrModes((prev) => prev.includes(key) ? prev.filter((m) => m !== key) : [...prev, key]);
  };

  // Iter 181 — Inline cap validation. Computes per-row error
  // strings the moment the commissioner edits a Position Breakdown
  // cell or a Roster Size input. Surfaces under the matrix BEFORE
  // they hit Save so they can fix the problem in one go. Mirrors
  // the backend's `check_position_breakdown_within_caps` rule.
  const _rowSumFor = (rowKey: string): number => {
    const row = (positionBreakdown as any)[rowKey] || {};
    return POSITIONS.reduce((s, p) => s + (parseIntOrNull(row[p.key]) ?? 0), 0);
  };
  const breakdownCapErrors: Record<string, string | null> = (() => {
    const errs: Record<string, string | null> = { active: null, bench: null, minors: null };
    const checks: Array<[string, string, number | null]> = [
      ["active", "Active Roster", parseIntOrNull(rosterSpots)],
      ["bench",  "Bench",         parseIntOrNull(benchSpots)],
      ["minors", "Minors Team",   parseIntOrNull(prospectPool)],
    ];
    for (const [key, label, cap] of checks) {
      if (cap === null || cap <= 0) continue;
      const s = _rowSumFor(key);
      if (s > cap) {
        errs[key] = (
          `${label} per-position caps sum to ${s} but ${label} size is only ${cap}. `
          + `Increase ${label} size first, or lower the caps on this row.`
        );
      }
    }
    return errs;
  })();
  const hasBreakdownCapError = Object.values(breakdownCapErrors).some(Boolean);

  const buildPayload = () => {
    const payload: Record<string, any> = {};
    const numFields: Array<[string, string, number, number]> = [
      ["roster_spots", rosterSpots, 10, 100],
      ["bench_spots", benchSpots, 0, 20],
      ["ir_slots", irSlots, 0, 15],
      ["ir_plus_slots", irPlusSlots, 0, 10],
      ["minors_spots", prospectPool, 0, 100],
      ["taxi_squad_size", taxiSquad, 0, 100],
      ["min_active_players", minActivePlayers, 0, 40],
      ["min_games_played", minGamesPlayed, 0, 200],
      ["prospect_max_age", prospectMaxAge, 16, 30],
      ["prospect_max_career_games", prospectMaxGames, 0, 500],
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
    // Iter 176 — Persist the new 3-row Position Breakdown. Each row
    // only carries the cells the commissioner actually filled in so
    // blank = "no limit" survives a round-trip. The Active row's
    // total is the source of truth for `roster_spots`; if the
    // commissioner DID set any active limits we override the manual
    // roster_spots input to keep things consistent.
    const rowToDict = (row: Record<string, string>): Record<string, number> => {
      const out: Record<string, number> = {};
      for (const p of POSITIONS) {
        const n = parseIntOrNull(row?.[p.key]);
        if (n !== null) out[p.key] = n;
      }
      return out;
    };
    const breakdown = {
      active: rowToDict(positionBreakdown.active),
      bench: rowToDict(positionBreakdown.bench),
      bench2: rowToDict(positionBreakdown.bench2),
      minors: rowToDict(positionBreakdown.minors),
    };
    payload.position_breakdown = breakdown;
    // Legacy mirror — keeps callers that still read `position_limits`
    // (waivers, trade engine helpers) working until they migrate.
    // Iter 178 — When the commissioner has set any per-position
    // Active Roster cap, the input PRE-FILLS to the derived sum but
    // STAYS EDITABLE so they can override. Manual value (if it differs
    // from the derived sum) wins on save. Previously this was locked
    // read-only which silently dropped the user's manual override.
    payload.position_limits = breakdown.active;
    const manualRoster = parseIntOrNull(rosterSpots);
    const activeSum = Object.values(breakdown.active).reduce((s, n) => s + (Number.isFinite(n) ? n : 0), 0);
    if (manualRoster !== null) {
      // Explicit value the commissioner typed (or pre-filled, then kept).
      payload.roster_spots = manualRoster;
    } else if (Object.keys(breakdown.active).length > 0 && activeSum > 0) {
      // No manual input but per-position caps drive a derived sum.
      payload.roster_spots = activeSum;
    }
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
          <CardTitle>
            Roster Size
            <InfoHint
              testId="info-roster-size"
              text="Defines the total capacity each team has across every roster section. Bench is non-active backup, IR holds players the NHL has flagged as injured (no cap relief), and IR+ holds long-term injury (frees their cap hit). Prospect pool is the dynasty farm system."
            />
          </CardTitle>
          <CardDescription>Active roster, bench, IR, and Minors team capacity.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 md:grid-cols-4">
            <div className="space-y-2">
              <Label htmlFor="roster-size-active">
                Active Roster (10–100)
                <InfoHint testId="info-active-roster" text="Players eligible to earn points each scoring period. Excludes bench, IR, IR+, prospects, and taxi squad. If you've set per-position caps in Position Breakdown → Active Roster, the total is derived from that row." />
              </Label>
              {/* Iter 176/178 — When the commissioner has set any
                  per-position Active Roster cap, this input pre-fills
                  with the derived sum but STAYS EDITABLE so they can
                  override (e.g. set caps that sum to 20 but allow a
                  19-player active roster). On save, the manual value
                  wins; clearing the input falls back to the derived
                  sum. */}
              {(() => {
                const activeSum = POSITIONS.reduce((s, p) => {
                  const n = parseIntOrNull(positionBreakdown.active?.[p.key]);
                  return s + (n ?? 0);
                }, 0);
                const hasCaps = POSITIONS.some(
                  (p) => parseIntOrNull(positionBreakdown.active?.[p.key]) !== null,
                ) && activeSum > 0;
                // Manual input drives the value; the derived sum acts
                // as a placeholder hint when the input is empty.
                return (
                  <>
                    <Input
                      id="roster-size-active"
                      type="number"
                      min={10}
                      max={100}
                      value={rosterSpots}
                      onChange={(e) => setRosterSpots(e.target.value)}
                      placeholder={hasCaps ? String(activeSum) : "20"}
                      data-testid="rosters-roster-spots-input"
                    />
                    {hasCaps && (
                      <p
                        className="text-[11px] text-muted-foreground"
                        data-testid="rosters-roster-spots-derived-note"
                      >
                        Position Breakdown → Active sums to <strong>{activeSum}</strong>. Leave blank to inherit, or type a different value to override.
                      </p>
                    )}
                  </>
                );
              })()}
            </div>
            <div className="space-y-2">
              <Label htmlFor="roster-size-bench">Bench Spots (0–20)</Label>
              <Input id="roster-size-bench" type="number" min={0} max={20}
                value={benchSpots} onChange={(e) => setBenchSpots(e.target.value)}
                placeholder="4" data-testid="rosters-bench-spots-input" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="roster-size-ir">
                IR Slots (0–15)
                <InfoHint testId="info-ir-slots" text="Short-term IR holds NHL-flagged injured players. Frees an active slot but their cap hit still counts. Eligibility usually requires IR/DTD/Suspended designation." />
              </Label>
              <Input id="roster-size-ir" type="number" min={0} max={15}
                value={irSlots} onChange={(e) => setIrSlots(e.target.value)}
                placeholder="3" data-testid="rosters-ir-slots-input" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="roster-size-ir-plus">
                IR+ Slots (0–10)
                <InfoHint testId="info-ir-plus-slots" text="Long-term IR. Frees BOTH an active slot AND the player's cap hit. Designed for season-ending injuries; commissioner usually has to approve placements." />
              </Label>
              <Input id="roster-size-ir-plus" type="number" min={0} max={10}
                value={irPlusSlots} onChange={(e) => setIrPlusSlots(e.target.value)}
                placeholder="2" data-testid="rosters-ir-plus-slots-input" />
            </div>
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="roster-size-prospects">
                Minors Team Size (0–100)
                <InfoHint testId="info-prospect-pool" text="Dynasty farm system slots. Players in the Minors don't earn fantasy points and are excluded from cap math, but they auto-promote when they hit your league's age/games threshold." />
              </Label>
              <Input id="roster-size-prospects" type="number" min={0} max={100}
                value={prospectPool} onChange={(e) => setProspectPool(e.target.value)}
                placeholder="10" data-testid="rosters-minors-spots-input" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="roster-size-taxi">
                Taxi Squad Size (0–100)
                <InfoHint testId="info-taxi-squad" text="Mid-season stash for emerging NHL talent. Unlike prospects, taxi-squad players can be activated mid-week with a single move. Cap hit still applies." />
              </Label>
              <Input id="roster-size-taxi" type="number" min={0} max={100}
                value={taxiSquad} onChange={(e) => setTaxiSquad(e.target.value)}
                placeholder="5" data-testid="rosters-taxi-squad-input" />
            </div>
          </div>

          {/* Iter 181 — Position Breakdown is now nested inside the
              Roster Size card so commissioners see the per-position
              caps alongside the section sizes they constrain. Cap
              enforcement (see backend `check_position_breakdown_within_caps`)
              rejects any per-row sum that exceeds its section size with
              a clear "increase Roster Size first" error. */}
          <Separator className="my-2" />
          <div className="space-y-3">
            <div className="flex items-start gap-2">
              <ShieldAlert className="h-5 w-5 text-amber-400 shrink-0 mt-0.5" />
              <div className="flex-1">
                <div className="flex items-center gap-2 text-base font-semibold">
                  Position Breakdown
                  <InfoHint testId="info-position-breakdown" text="Caps the number of players each team can roster at each position, per section. Leave a cell blank for no cap. Per-section sums cannot exceed the section sizes above — increase Roster Size first to allow larger caps." />
                </div>
                <p className="text-sm text-muted-foreground">
                  Per-position caps for Active Roster, Bench (if any), and Minors (if enabled).
                  <span className="block text-[12px] text-muted-foreground/80 mt-1">
                    <em>Untouched cells = unlimited. Each row's total must stay within its section size above.</em>
                  </span>
                </p>
              </div>
            </div>

            {/* Column headers */}
            <div className="grid gap-2" style={{ gridTemplateColumns: `120px repeat(${POSITIONS.length}, minmax(72px, 1fr)) 90px` }}>
              <div className="text-[11px] uppercase tracking-wider text-muted-foreground self-end">Section</div>
              {POSITIONS.map((p) => (
                <div key={p.key} className="text-[11px] uppercase tracking-wider text-muted-foreground text-center self-end">
                  <div className="flex items-center justify-center gap-1">
                    {p.key}
                    {p.help && <InfoHint testId={`info-position-${p.key}`} text={p.help} />}
                  </div>
                </div>
              ))}
              <div className="text-[11px] uppercase tracking-wider text-muted-foreground text-right self-end">Total</div>
            </div>

          {BREAKDOWN_ROWS.map((row) => {
            const rowState = positionBreakdown[row.key] || {};
            // Iter 179 — Always show a row if it has previously-saved
            // data, even when the visibility predicate (bench_spots > 0,
            // minors_enabled) would otherwise hide it. Without this, a
            // commissioner who lowers `bench_spots` to 0 after setting
            // bench caps would see the bench row vanish AND their caps
            // appear lost on reload — the actual root cause of "the
            // Position Breakdown menu seems to reset when reentering
            // the league administration menus" bug report.
            const hasExistingData = POSITIONS.some(
              (p) => parseIntOrNull(rowState[p.key]) !== null,
            );
            const benchOn = (parseIntOrNull(benchSpots) || 0) > 0;
            const minorsOn =
              !!(league as any).minors_enabled
              || (parseIntOrNull(prospectPool) || 0) > 0
              || benchOn; // Iter 180 — surface Minors row by default
                          // whenever the league runs a bench. Dynasty
                          // leagues almost always use both, and the
                          // separate `minors_enabled` premium flag was
                          // confusing UX.
            const visible =
              row.key === "active"
              || hasExistingData
              || (row.key === "bench" && benchOn)
              || (row.key === "minors" && minorsOn);
            if (!visible) return null;
            const rowSum = POSITIONS.reduce((s, p) => {
              const n = parseIntOrNull(rowState[p.key]);
              return s + (n ?? 0);
            }, 0);
            const anySet = POSITIONS.some((p) => parseIntOrNull(rowState[p.key]) !== null);
            return (
              <div
                key={row.key}
                className="grid gap-2 items-center"
                style={{ gridTemplateColumns: `120px repeat(${POSITIONS.length}, minmax(72px, 1fr)) 90px` }}
                data-testid={`rosters-position-breakdown-row-${row.key}`}
              >
                <div className="flex items-center gap-1 text-sm font-medium text-foreground">
                  {row.label}
                  <InfoHint testId={`info-row-${row.key}`} text={row.help} />
                </div>
                {POSITIONS.map((p) => (
                  <Input
                    key={`${row.key}-${p.key}`}
                    type="number"
                    min={0}
                    max={30}
                    value={rowState[p.key] ?? ""}
                    onChange={(e) =>
                      setPositionBreakdown((prev) => ({
                        ...prev,
                        [row.key]: { ...prev[row.key], [p.key]: e.target.value },
                      }))
                    }
                    placeholder="—"
                    className="h-9 text-center"
                    data-testid={`rosters-position-${row.key}-${p.key}-input`}
                  />
                ))}
                <div
                  className="text-right text-sm font-mono text-muted-foreground"
                  data-testid={`rosters-position-${row.key}-total`}
                >
                  {anySet ? rowSum : "—"}
                </div>
                {breakdownCapErrors[row.key] && (
                  <div
                    className="col-span-full text-[12px] text-destructive bg-destructive/10 border border-destructive/30 rounded-md px-3 py-2"
                    data-testid={`rosters-position-${row.key}-cap-error`}
                  >
                    {breakdownCapErrors[row.key]}
                  </div>
                )}
              </div>
            );
          })}

          <div className="flex items-center justify-between pt-2 border-t border-border/40">
            <div>
              <Label>
                Enforce Position Maximums
                <InfoHint testId="info-enforce-position" text="When ON, the system rejects any add/trade/draft that would put a team over a position cap in any section. When OFF, the caps are advisory only — owners get a warning but can still pile up D-men." />
              </Label>
              <p className="text-sm text-muted-foreground">
                Block acquisitions (waivers, trades, draft picks) that exceed any active-section limit.
              </p>
            </div>
            <Switch
              checked={enforcePositions}
              onCheckedChange={setEnforcePositions}
              data-testid="rosters-enforce-positions"
            />
          </div>
          </div>
        </CardContent>
      </Card>

      {/* Roster Requirements */}
      <Card className="bg-card border-border" data-testid="rosters-requirements-card">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <ListChecks className="h-5 w-5 text-emerald-400" />
            Roster Requirements
            <InfoHint testId="info-roster-requirements" text="Validity rules checked each scoring period. Lineups that don't meet these are flagged invalid. Used to prevent owners from fielding empty rosters for tanking." />
          </CardTitle>
          <CardDescription>Minimums and validity rules checked by the scoring engine.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="req-min-active">
                Minimum Active Players (0–40)
                <InfoHint testId="info-min-active" text="Smallest number of starters a team can field each scoring period without being flagged for a forfeit." />
              </Label>
              <Input id="req-min-active" type="number" min={0} max={40}
                value={minActivePlayers} onChange={(e) => setMinActivePlayers(e.target.value)}
                placeholder="15" data-testid="rosters-min-active-input" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="req-min-games">
                Minimum Games Played (0–200)
                <InfoHint testId="info-min-games" text="Per-team minimum total games-played by all active players over the scoring period. Stops tanking via 'parked' lineups." />
              </Label>
              <Input id="req-min-games" type="number" min={0} max={200}
                value={minGamesPlayed} onChange={(e) => setMinGamesPlayed(e.target.value)}
                placeholder="50" data-testid="rosters-min-games-input" />
            </div>
          </div>
          <div className="flex items-center justify-between">
            <div>
              <Label>
                Prorate Min/Max by Period
                <InfoHint testId="info-prorate-period" text="When ON, the min-games requirement scales with the scoring period length (daily/weekly/2-week). Off-week or split-week periods auto-adjust so a 3-day window doesn't require a full week's games." />
              </Label>
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
              <Label>
                Allow Illegal Rosters
                <InfoHint testId="info-allow-illegal" text="If ON, lineups that violate the rules above STILL score — owners just see a warning. If OFF, the scoring engine refuses to score the period until the lineup is legal." />
              </Label>
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

      {/* Iter 121 — Prospect Eligibility (consumed by waiver "Prevent claims on prospects") */}
      <Card className="bg-card border-border" data-testid="rosters-prospect-eligibility-card">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <ListChecks className="h-5 w-5 text-indigo-400" />
            Prospect Eligibility
            <InfoHint testId="info-prospect-eligibility" text="Defines who counts as a 'prospect' for league rules. Used by the 'Prevent claims on prospects' waiver toggle. A player is a prospect if BOTH thresholds apply — young AND inexperienced." />
          </CardTitle>
          <CardDescription>
            Defines who counts as a "prospect" for league rules — used by the
            <em className="px-1">Prevent claims on prospects</em> toggle in
            League Administration → Transactions → Waivers. A player who is
            BOTH under the age limit AND under the career-games limit is
            treated as a prospect.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="prospect-max-age">Max age (16–30, default 24)</Label>
              <Input
                id="prospect-max-age"
                type="number" min={16} max={30}
                value={prospectMaxAge}
                onChange={(e) => setProspectMaxAge(e.target.value)}
                placeholder="24"
                data-testid="rosters-prospect-max-age"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="prospect-max-games">Max career games (0–500, default 100)</Label>
              <Input
                id="prospect-max-games"
                type="number" min={0} max={500}
                value={prospectMaxGames}
                onChange={(e) => setProspectMaxGames(e.target.value)}
                placeholder="100"
                data-testid="rosters-prospect-max-games"
              />
            </div>
          </div>
          <p className="text-xs text-muted-foreground">
            Leave blank to use the league-wide defaults (24 years / 100 GP).
            Players explicitly flagged <code className="text-xs">is_prospect: true</code>
            in the player record are also treated as prospects regardless of these
            thresholds.
          </p>
        </CardContent>
      </Card>

      {/* IR Eligibility */}
      <Card className="bg-card border-border" data-testid="rosters-ir-card">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <HeartPulse className="h-5 w-5 text-rose-400" />
            IR Eligibility
            <InfoHint testId="info-ir-eligibility" text="Which official NHL status codes can occupy an IR slot. IR (Injured Reserve), DTD (Day-to-Day), SUSPended, HEALthy scratch. Most leagues only allow IR / DTD." />
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

      {hasBreakdownCapError && (
        <div
          className="rounded-md bg-destructive/10 border border-destructive/40 px-4 py-3 text-sm text-destructive"
          data-testid="rosters-cap-error-banner"
        >
          One or more Position Breakdown rows exceed their section size.
          Increase Roster Size first, or lower the per-position caps to save.
        </div>
      )}
      <div className="flex justify-end">
        <Button onClick={onSave} disabled={saving || hasBreakdownCapError} className="gap-2" data-testid="rosters-save-btn">
          {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
          {saving ? "Saving…" : "Save Roster Settings"}
        </Button>
      </div>
    </div>
  );
}
