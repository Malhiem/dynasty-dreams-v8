// @ts-nocheck
import { AppLayout } from "@/components/layout/AppLayout";
import { useActiveLeague } from "@/hooks/use-active-league";
import { useAuth } from "@/contexts/AuthContext";
import CapFloorWatchlistCard from "@/lovable/components/dashboard/CapFloorWatchlistCard";
import LeagueContextBanner from "@/lovable/components/dashboard/LeagueContextBanner";
import api from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { DollarSign, TrendingUp, TrendingDown, AlertTriangle, ArrowUpDown, ArrowUp, ArrowDown, HelpCircle, MinusCircle } from "lucide-react";
import {
  PieChart, Pie, Cell, ResponsiveContainer, Legend, Tooltip,
  BarChart, Bar, XAxis, YAxis, CartesianGrid, ReferenceLine,
  ComposedChart, Line,
} from "recharts";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tooltip as UITooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger } from "@/components/ui/alert-dialog";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { ChevronDown } from "lucide-react";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { useState, useEffect, useMemo } from "react";
// Iter 232N.41 — Player-card drilldown on Salary Cap surfaces.
import PlayerCardModal from "@/lovable/components/dashboard/PlayerCardModal";

interface Contract {
  id: string;
  player: string;
  position: string;
  team: string;
  salary: number;
  yearsRemaining: number;
  totalYears: number;
  currentYear: number;
  endYear: number;
  endStatus: "UFA" | "RFA" | "ELC" | "Signed";
  status: "active" | "expiring" | "ir";
}

type ChartFilter = "all" | "players" | "position" | "by_year";

// Distinct, dark-mode-friendly hex palette — replaces the broken
// `hsl(var(--chart-2))` tokens that were resolving to empty/black on the
// off-black card background. Picked for visual contrast against `#000`-ish
// surface and clear separation when shown side-by-side in a legend.
const CHART_COLORS = [
  "#00D2FF", // cyan (matches --primary)
  "#FFB020", // gold (matches --accent)
  "#22C55E", // emerald
  "#A855F7", // violet
  "#F472B6", // pink
  "#3B82F6", // blue
  "#FB923C", // orange
  "#14B8A6", // teal
  "#EAB308", // yellow
  "#EF4444", // red
  "#8B5CF6", // purple-2
  "#06B6D4", // cyan-2
];

// Iter 232N.43 — Stable module-scoped Legend formatter. Prevents
// recharts from receiving a fresh function identity on every parent
// re-render (which the linter flagged as `no-unstable-nested-components`).
const legendFormatter = (value: any) => (
  <span className="text-sm text-foreground">{String(value)}</span>
);

// Iter 232N.43 — Stable sort-direction indicator. Was previously
// defined inside `SalaryCap`, causing React to see a new component
// type on every render (destroys focus, breaks reconciliation).
type SortKey = "player" | "position" | "salary" | "year" | "contract_ends";
const SortIcon = ({ col, sortKey, sortDir }: { col: SortKey; sortKey: SortKey; sortDir: "asc" | "desc" }) => {
  if (sortKey !== col) return <ArrowUpDown className="inline h-3 w-3 ml-1 opacity-40" />;
  return sortDir === "asc" ? <ArrowUp className="inline h-3 w-3 ml-1" /> : <ArrowDown className="inline h-3 w-3 ml-1" />;
};

// Iter 232N.43 — Standalone BuyoutDialog. Was defined inside SalaryCap
// (`no-unstable-nested-components` flagged); moved to module scope with
// the buyout callback + Contract type passed as props.
interface BuyoutDialogProps {
  contract: Contract;
  onConfirm: (id: string, name: string, lengthOpt: string) => void;
}

function BuyoutDialog({ contract, onConfirm }: BuyoutDialogProps) {
  const [lengthOpt, setLengthOpt] = useState<string>("default");
  const previewMath: Record<string, { rate: number; span: number }> = {
    full: { rate: 1.0, span: Math.max(2, 2 * contract.yearsRemaining) },
    default: { rate: 2 / 3, span: Math.max(2, 2 * contract.yearsRemaining) },
    two_thirds: { rate: 2 / 3, span: Math.max(2, 2 * contract.yearsRemaining) },
    half: { rate: 0.5, span: Math.max(2, 2 * contract.yearsRemaining) },
    one_year: { rate: 1.0, span: 1 },
    minimum: { rate: 1 / 3, span: Math.max(1, contract.yearsRemaining) },
  };
  const preview = previewMath[lengthOpt] || previewMath.default;
  const totalDead = Math.round(contract.salary * contract.yearsRemaining * preview.rate);
  const annual = Math.round(totalDead / preview.span);

  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>
        <Button size="sm" variant="outline" className="h-7 text-[10px] px-2" data-testid={`buyout-btn-${contract.id}`}>
          <MinusCircle className="h-3 w-3 mr-1" />
          Buy Out
        </Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Buy out {contract.player}?</AlertDialogTitle>
          <AlertDialogDescription>
            Choose the buyout terms. The dead-cap charge is spread over future seasons.
            <span className="block mt-1 text-muted-foreground text-xs">
              Remaining contract: {contract.yearsRemaining} year(s) × ${(contract.salary / 1_000_000).toFixed(2)}M = ${(contract.salary * contract.yearsRemaining / 1_000_000).toFixed(2)}M total.
            </span>
          </AlertDialogDescription>
        </AlertDialogHeader>
        <div className="space-y-3 py-2">
          <div>
            <label className="text-xs text-muted-foreground">Buyout length</label>
            <Select value={lengthOpt} onValueChange={setLengthOpt}>
              <SelectTrigger className="w-full mt-1" data-testid={`buyout-length-${contract.id}`}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="default">2/3 over 2× term (NHL CBA default)</SelectItem>
                <SelectItem value="full">Full salary over 2× term</SelectItem>
                <SelectItem value="half">Half salary over 2× term</SelectItem>
                <SelectItem value="one_year">Full salary as a single year hit</SelectItem>
                <SelectItem value="minimum">1/3 over remaining term (minimum)</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="rounded-lg bg-secondary/40 border border-border p-3 text-xs space-y-1">
            <div className="flex justify-between">
              <span className="text-muted-foreground">Dead cap total:</span>
              <span className="font-bold text-accent">${(totalDead / 1_000_000).toFixed(2)}M</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Annual dead cap:</span>
              <span className="font-bold">${(annual / 1_000_000).toFixed(2)}M / yr</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Span:</span>
              <span className="font-bold">{preview.span} season(s)</span>
            </div>
          </div>
        </div>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction
            onClick={() => onConfirm(contract.id, contract.player, lengthOpt)}
            data-testid={`buyout-confirm-${contract.id}`}
          >
            Confirm Buyout
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

const CAP_SPACE_COLOR = "#34C759";   // bright emerald (was broken hsl(var(--success)))
const DEAD_CAP_COLOR = "#FFB020";    // gold/accent
const RETAINED_COLOR = "#FF3B30";    // red/destructive

const SalaryCap = () => {
  const { league, leagueTeams, myTeam } = useActiveLeague();
  const { user } = useAuth();
  const isCommissioner =
    !!user?.id && !!league?.commissioner_id && league.commissioner_id === user.id;
  const leagueTeamsCount = leagueTeams?.length || 0;
  const [chartFilter, setChartFilter] = useState<ChartFilter>("all");
  const [rosterDetail, setRosterDetail] = useState<any>(null);
  // Iter 112 — Dead-cap schedule pulled from server (buyouts + retention)
  const [deadCapSchedule, setDeadCapSchedule] = useState<{ schedule: any[]; total_dead_cap: number }>({ schedule: [], total_dead_cap: 0 });
  const [reloadKey, setReloadKey] = useState(0);
  // Iter 232N.41 — Player-card modal state. `openPlayerCard` builds a
  // Player-shaped payload from a contract row / dead-cap ledger entry.
  // Prefers the roster's rich player object (with stats + schedule)
  // when available so the modal opens with the full drilldown, else
  // falls back to a lean shim that still populates identity fields.
  const [cardOpen, setCardOpen] = useState(false);
  const [cardPlayer, setCardPlayer] = useState<any>(null);

  const openPlayerCard = (playerId: string, fallbackName?: string, fallbackPosition?: string) => {
    if (!playerId) return;
    const rich = (rosterDetail?.players || []).find((p: any) => p.id === playerId);
    // Iter 232N.41 — PlayerCardModal iterates `schedule.filter(...)` on
    // mount, so a bare roster payload (which lacks `schedule`) will
    // crash the modal. Merge conservative defaults for every array/
    // dict the modal touches so the drilldown opens even for the lean
    // salary-cap payload.
    const base = {
      id: playerId,
      name: fallbackName || rich?.name || "Player",
      position: fallbackPosition || rich?.position || "—",
      team: rich?.team || "",
      points: 0,
      dynastyValue: 0,
      trend: "stable",
      age: 25,
      contract: { salary: 0, yearsRemaining: 1, type: "UFA" },
      rosterSection: "bench",
      statsByPeriod: { season: 0, "1d": 0, "7d": 0, "14d": 0, "30d": 0, "60d": 0, "100d": 0 },
      categoryBreakdown: { G: 0, A: 0, PPP: 0, SHP: 0, SOG: 0, HIT: 0, BLK: 0, PIM: 0, "+/-": 0, FOW: 0, FOL: 0 },
      matchupGames: 0,
      schedule: [],
    };
    setCardPlayer({ ...base, ...(rich || {}), schedule: rich?.schedule || [], statsByPeriod: rich?.statsByPeriod || base.statsByPeriod, categoryBreakdown: rich?.categoryBreakdown || base.categoryBreakdown, contract: rich?.contract || base.contract });
    setCardOpen(true);
  };

  useEffect(() => {
    if (!myTeam?.id) return;
    let cancelled = false;
    api.get(`/roster/${myTeam.id}/detail`)
      .then(({ data }) => { if (!cancelled) setRosterDetail(data); })
      .catch(() => {});
    api.get(`/teams/${myTeam.id}/dead-cap-schedule`)
      .then(({ data }) => { if (!cancelled) setDeadCapSchedule(data); })
      .catch(() => setDeadCapSchedule({ schedule: [], total_dead_cap: 0 }));
    return () => { cancelled = true; };
  }, [myTeam?.id, reloadKey]);

  const buyOut = async (playerId: string, playerName: string, lengthOption: string) => {
    try {
      const { data } = await api.post(`/teams/${myTeam.id}/players/${playerId}/buyout`, {
        length_option: lengthOption,
      });
      toast.success(
        `${playerName} bought out — $${(data.dead_cap_total / 1_000_000).toFixed(1)}M dead cap over ${data.span_years} seasons.`
      );
      setReloadKey((k) => k + 1);
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Buyout failed");
    }
  };

  const reverseBuyout = async (playerId: string, playerName: string) => {
    try {
      await api.delete(`/teams/${myTeam.id}/buyouts/${playerId}`);
      toast.success(`Buyout reversed — ${playerName} restored to roster.`);
      setReloadKey((k) => k + 1);
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Reversal failed");
    }
  };

  const cancelRetention = async (playerId: string, playerName: string) => {
    try {
      await api.delete(`/teams/${myTeam.id}/dead-cap/retention/${playerId}`);
      toast.success(`Retention charge waived for ${playerName}.`);
      setReloadKey((k) => k + 1);
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Reversal failed");
    }
  };

  // Iter 232N.43 — BuyoutDialog + SortIcon moved to module scope
  // (see top of file). Below they're used as normal components.

  const contracts: Contract[] = useMemo(() => {
    if (!rosterDetail?.players) return [];
    return rosterDetail.players.map((p: any) => {
      const c = p.contract || {};
      const yearsRemaining = c.yearsRemaining || 1;
      const totalYears = c.total_years || yearsRemaining;
      const currentYear = c.current_year || Math.max(1, totalYears - yearsRemaining + 1);
      // Fallback when older backend response lacks the iter-110 fields.
      const fallbackEndYear = new Date().getFullYear() + Math.max(0, yearsRemaining - 1);
      const endYear = c.end_year || fallbackEndYear;
      const endStatus = c.end_status || (c.type === "ELC" ? "RFA" : (c.type || "UFA"));
      return {
        id: p.id,
        player: p.name,
        position: p.position,
        team: p.team,
        salary: c.salary || 0,
        yearsRemaining,
        totalYears,
        currentYear,
        endYear,
        endStatus,
        status: p.rosterSection === "ir"
          ? "ir"
          : ((c.type === "UFA" || yearsRemaining === 1) ? "expiring" : "active"),
      };
    });
  }, [rosterDetail]);

  // Iter 112 — Salary cap value MUST come from the commissioner's setting,
  // not from the auto-scaling fallback that previously inflated the visual cap
  // when contracts overshot. If the league has no cap set we fall back to the
  // NHL default ($82.5M).
  const capLimit = Number(league?.salary_cap || 82_500_000);
  const currentSpending = contracts.reduce((sum, c) => sum + c.salary, 0);
  // Iter 112 — Dead cap for the *current* calendar year (current row of schedule)
  const curYear = new Date().getFullYear();
  const deadCap = (deadCapSchedule.schedule || [])
    .filter((r: any) => r.year === curYear)
    .reduce((s: number, r: any) => s + Number(r.total || 0), 0);
  const totalRetained = 0;
  const retainedSalaries: any[] = [];
  const capSpace = capLimit - currentSpending - deadCap - totalRetained;
  const capUsagePercent = ((currentSpending + deadCap + totalRetained) / capLimit) * 100;

  // ── By-Year payload (iter 110, extended iter 113) ───────────────
  // For each of the next 5 NHL seasons, sum the salaries of players whose
  // contract still covers that year. Anything unsigned counts as `unsigned`
  // (rendered as the empty/cap-space portion) so users can see how much of
  // their cap is locked vs available year-over-year. Dead cap (buyouts +
  // retention) is also stacked so the user sees the FULL committed picture.
  // Iter 121 — Surface cap FLOOR alongside the ceiling on the By-Year chart
  // and in the compliance card. Floors come from league.cap_floor (current),
  // league.cap_floor_year_plus_1, league.cap_floor_year_plus_2. Anything
  // beyond Year+2 falls back to the most recent floor (admins can extend
  // by saving new values on the Salary Cap & Contracts tab).
  const floorEnabled = !!(league as any)?.cap_floor_enabled;
  const floorCurrent = Number((league as any)?.cap_floor || 0);
  const floorYr1 = Number((league as any)?.cap_floor_year_plus_1 || floorCurrent);
  const floorYr2 = Number((league as any)?.cap_floor_year_plus_2 || floorYr1);
  const capYr1 = Number((league as any)?.salary_cap_year_plus_1 || capLimit);
  const capYr2 = Number((league as any)?.salary_cap_year_plus_2 || capYr1);

  const yearBreakdown = useMemo(() => {
    if (contracts.length === 0) return [];
    const minYear = Math.min(...contracts.map((c) => c.endYear - c.yearsRemaining + 1));
    const maxYear = Math.max(...contracts.map((c) => c.endYear));
    const start = Math.min(minYear, new Date().getFullYear());
    const end = Math.min(maxYear, start + 5); // cap at 6-year horizon
    const deadCapByYear: Record<number, number> = {};
    (deadCapSchedule.schedule || []).forEach((r: any) => {
      deadCapByYear[r.year] = (deadCapByYear[r.year] || 0) + Number(r.total || 0);
    });
    const currentYear = new Date().getFullYear();
    const capForYear = (y: number) => {
      const off = y - currentYear;
      if (off <= 0) return capLimit;
      if (off === 1) return capYr1;
      if (off === 2) return capYr2;
      return capYr2;
    };
    const floorForYear = (y: number) => {
      if (!floorEnabled) return 0;
      const off = y - currentYear;
      if (off <= 0) return floorCurrent;
      if (off === 1) return floorYr1;
      if (off === 2) return floorYr2;
      return floorYr2;
    };
    const out: { year: number; locked: number; dead: number; available: number; label: string; cap: number; floor: number }[] = [];
    for (let y = start; y <= end; y++) {
      const yearCap = capForYear(y);
      const locked = contracts.reduce((sum, c) => {
        const contractStart = c.endYear - c.yearsRemaining + 1;
        return (y >= contractStart && y <= c.endYear) ? sum + c.salary : sum;
      }, 0);
      const dead = deadCapByYear[y] || 0;
      out.push({
        year: y,
        locked,
        dead,
        available: Math.max(0, yearCap - locked - dead),
        cap: yearCap,
        floor: floorForYear(y),
        label: String(y),
      });
    }
    return out;
  }, [contracts, capLimit, capYr1, capYr2, floorEnabled, floorCurrent, floorYr1, floorYr2, deadCapSchedule.schedule]);

  const getChartData = () => {
    switch (chartFilter) {
      case "players":
        const playerData = contracts.slice(0, 12).map((c, index) => ({
          name: c.player,
          value: c.salary,
          color: CHART_COLORS[index % CHART_COLORS.length],
        }));
        if (capSpace > 0) playerData.push({ name: "Cap Space", value: capSpace, color: CAP_SPACE_COLOR });
        return playerData;

      case "position":
        const positionGroups: Record<string, number> = {};
        contracts.forEach((c) => {
          positionGroups[c.position] = (positionGroups[c.position] || 0) + c.salary;
        });
        const posData = Object.entries(positionGroups).map(([pos, value], index) => ({
          name: pos,
          value,
          color: CHART_COLORS[index % CHART_COLORS.length],
        }));
        if (capSpace > 0) posData.push({ name: "Cap Space", value: capSpace, color: CAP_SPACE_COLOR });
        return posData;

      default:
        const allData: any[] = [
          { name: "Player Salaries", value: currentSpending, color: CHART_COLORS[0] },
        ];
        if (capSpace > 0) allData.push({ name: "Cap Space", value: capSpace, color: CAP_SPACE_COLOR });
        return allData;
    }
  };

  const chartData = getChartData();
  const formatCurrency = (value: number) => `$${(value / 1000000).toFixed(2)}M`;

  // ── Iter 111 — Sortable Active-Contracts table ────────────────
  // Iter 232N.43 — `SortKey` moved to module scope; local alias removed.
  const [sortKey, setSortKey] = useState<SortKey>("salary");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const handleSort = (key: SortKey) => {
    if (sortKey === key) setSortDir(sortDir === "asc" ? "desc" : "asc");
    else { setSortKey(key); setSortDir(key === "salary" ? "desc" : "asc"); }
  };
  // Iter 232N.43 — SortIcon moved to module scope (see top of file).
  const sortedContracts = useMemo(() => {
    const arr = [...contracts];
    const dir = sortDir === "asc" ? 1 : -1;
    arr.sort((a, b) => {
      switch (sortKey) {
        case "player": return a.player.localeCompare(b.player) * dir;
        case "position": return a.position.localeCompare(b.position) * dir;
        case "salary": return (a.salary - b.salary) * dir;
        case "year": return ((a.currentYear / Math.max(1, a.totalYears)) - (b.currentYear / Math.max(1, b.totalYears))) * dir;
        case "contract_ends": return (a.endYear - b.endYear) * dir
          || a.endStatus.localeCompare(b.endStatus) * dir;
        default: return 0;
      }
    });
    return arr;
  }, [contracts, sortKey, sortDir]);

  // Dead-cap tooltip copy varies by whether the league has buyouts enabled.
  const buyoutsEnabled = !!(league as any)?.contract_buyouts_enabled;
  const deadCapTooltip = buyoutsEnabled
    ? "Dead cap represents charges that stay on your books even though the player is no longer on your roster. In this league it can come from (1) salary retained on an outgoing trade, or (2) a contract buyout (spreads remaining $ across future seasons)."
    : "Dead cap represents charges that stay on your books even though the player is no longer on your roster. Currently this is limited to salary retained on outgoing trades. Your commissioner can also enable Contract Buyouts (Commissioner → Transactions) which would add buyout-spread dead cap to future seasons.";

  return (
    <AppLayout>
        <div className="container py-8 space-y-6">
          <LeagueContextBanner title="Salary Cap" kpiLabel="Teams on roster" kpiValue={leagueTeamsCount} primaryHref="/commissioner" primaryLabel="Manage in Commissioner" />
        <div>
          <h1 className="text-2xl font-bold">Salary Cap Management</h1>
          <p className="text-muted-foreground">Contracts, cap space, and roster management</p>
        </div>

        {/* Cap Overview Cards */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <Card className="bg-card border-border" data-testid="cap-overview-card-limit">
            <CardContent className="p-6">
              <div className="flex items-center gap-3 mb-3">
                <div className="h-10 w-10 rounded-lg bg-primary/20 flex items-center justify-center">
                  <DollarSign className="h-5 w-5 text-primary" />
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Salary Cap</p>
                  <p className="text-xl font-bold">${(capLimit / 1000000).toFixed(1)}M</p>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card className="bg-card border-border" data-testid="cap-overview-card-hit">
            <CardContent className="p-6">
              <div className="flex items-center gap-3 mb-3">
                <div className="h-10 w-10 rounded-lg bg-destructive/20 flex items-center justify-center">
                  <TrendingUp className="h-5 w-5 text-destructive" />
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Cap Hit</p>
                  <p className="text-xl font-bold">${(currentSpending / 1000000).toFixed(1)}M</p>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card className="bg-card border-border" data-testid="cap-overview-card-space">
            <CardContent className="p-6">
              <div className="flex items-center gap-3 mb-3">
                <div className="h-10 w-10 rounded-lg flex items-center justify-center" style={{ backgroundColor: "rgba(52, 199, 89, 0.18)" }}>
                  <TrendingDown className="h-5 w-5" style={{ color: CAP_SPACE_COLOR }} />
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Cap Space</p>
                  <p className="text-xl font-bold" style={{ color: CAP_SPACE_COLOR }}>${(capSpace / 1000000).toFixed(1)}M</p>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* ── Dead Cap tile + drop-down ledger (Iter 113) ────────── */}
          <Card className="bg-card border-border md:col-span-1" data-testid="cap-overview-card-dead">
            <CardContent className="p-6">
              <div className="flex items-center gap-3 mb-3">
                <div className="h-10 w-10 rounded-lg bg-accent/20 flex items-center justify-center shrink-0">
                  <AlertTriangle className="h-5 w-5 text-accent" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1 text-sm text-muted-foreground">
                    <span>Dead Cap</span>
                    <TooltipProvider delayDuration={150}>
                      <UITooltip>
                        <TooltipTrigger asChild>
                          <button
                            type="button"
                            aria-label="What is Dead Cap?"
                            className="inline-flex items-center justify-center rounded-full hover:bg-muted/40 transition-colors p-0.5"
                            data-testid="cap-dead-cap-help"
                          >
                            <HelpCircle className="h-3.5 w-3.5 text-muted-foreground" />
                          </button>
                        </TooltipTrigger>
                        <TooltipContent side="bottom" className="max-w-xs text-xs leading-relaxed">
                          {deadCapTooltip}
                        </TooltipContent>
                      </UITooltip>
                    </TooltipProvider>
                  </div>
                  <p className="text-xl font-bold text-accent">${(deadCap / 1000000).toFixed(1)}M</p>
                </div>
              </div>
              {/* ── Per-player ledger dropdown ── */}
              {(() => {
                const currentYearEntries = (deadCapSchedule.schedule || [])
                  .find((r: any) => r.year === curYear)?.entries || [];
                if (currentYearEntries.length === 0) {
                  return (
                    <p className="text-[10px] text-muted-foreground italic mt-1">
                      No dead-cap charges this season.
                    </p>
                  );
                }
                return (
                  <Collapsible className="mt-1">
                    <CollapsibleTrigger asChild>
                      <button
                        className="flex items-center gap-1 text-[11px] text-cyan-300 hover:text-cyan-200 transition-colors group"
                        data-testid="cap-dead-cap-ledger-toggle"
                      >
                        <ChevronDown className="h-3 w-3 transition-transform group-data-[state=open]:rotate-180" />
                        <span>View {currentYearEntries.length} dead-cap charge{currentYearEntries.length !== 1 ? "s" : ""}</span>
                      </button>
                    </CollapsibleTrigger>
                    <CollapsibleContent>
                      <div className="mt-2 space-y-1 max-h-40 overflow-auto pr-1" data-testid="cap-dead-cap-ledger">
                        {currentYearEntries.map((e: any, i: number) => (
                          <div
                            key={`${e.player_id || "x"}-${i}`}
                            className="flex items-center justify-between gap-2 text-[10px] rounded px-1.5 py-1 bg-secondary/30 border border-border/30"
                          >
                            <div className="flex items-center gap-1 min-w-0">
                              <Badge
                                variant="outline"
                                className={`text-[9px] px-1 py-0 shrink-0 ${
                                  e.source === "retention"
                                    ? "border-rose-500/40 text-rose-400"
                                    : "border-amber-500/40 text-amber-400"
                                }`}
                              >
                                {e.source === "retention" ? "RET" : "BO"}
                              </Badge>
                              <button
                                type="button"
                                onClick={() => openPlayerCard(e.player_id, e.player_name, undefined)}
                                className="truncate text-left hover:text-primary hover:underline transition-colors cursor-pointer"
                                data-testid={`salary-cap-deadcap-link-${e.player_id || "unknown"}`}
                                disabled={!e.player_id}
                              >
                                {e.player_name || "—"}
                              </button>
                            </div>
                            <span className="font-mono text-accent shrink-0">
                              ${(Number(e.amount) / 1_000_000).toFixed(2)}M
                            </span>
                          </div>
                        ))}
                      </div>
                    </CollapsibleContent>
                  </Collapsible>
                );
              })()}
            </CardContent>
          </Card>
        </div>

        {/* Iter 121 — Cap Floor compliance card. Shown only when the league
            has the floor enabled. Highlights teams below the floor + how
            much they need to spend to comply (per current year). */}
        {floorEnabled && floorCurrent > 0 && (
          <Card className="bg-card border-border" data-testid="cap-floor-compliance-card">
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2 text-base">
                <MinusCircle className="h-4 w-4 text-amber-400" />
                Cap Floor Compliance
              </CardTitle>
              <CardDescription>
                Minimum team payroll required by this league for {new Date().getFullYear()}: <strong className="text-amber-400">${(floorCurrent / 1_000_000).toFixed(1)}M</strong>.
                {' '}Teams below the floor on the league&apos;s compliance date may be assessed a penalty per the league constitution.
              </CardDescription>
            </CardHeader>
            <CardContent className="pt-0">
              {(() => {
                const cur = currentSpending + deadCap + totalRetained;
                const isMyTeamCompliant = cur >= floorCurrent;
                const shortfall = floorCurrent - cur;
                return (
                  <div className="flex items-center justify-between gap-3 flex-wrap">
                    <div className="flex items-center gap-2 text-sm">
                      <span className="text-muted-foreground">Your team&apos;s payroll:</span>
                      <span className="font-mono font-bold">${(cur / 1_000_000).toFixed(1)}M</span>
                    </div>
                    {isMyTeamCompliant ? (
                      <Badge className="bg-emerald-500/15 border border-emerald-500/40 text-emerald-300" data-testid="cap-floor-compliant">
                        Above floor
                      </Badge>
                    ) : (
                      <div className="flex items-center gap-2" data-testid="cap-floor-below">
                        <Badge className="bg-rose-500/15 border border-rose-500/40 text-rose-300">
                          Below floor
                        </Badge>
                        <span className="text-xs text-amber-300">
                          ${(shortfall / 1_000_000).toFixed(1)}M short
                        </span>
                      </div>
                    )}
                  </div>
                );
              })()}
              {/* Year-by-year floor preview */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mt-4">
                <div className="rounded-md border border-border bg-secondary/30 px-3 py-2">
                  <div className="text-[10px] text-muted-foreground uppercase tracking-wide">This year</div>
                  <div className="text-sm font-bold text-amber-300" data-testid="cap-floor-current">
                    ${(floorCurrent / 1_000_000).toFixed(1)}M
                  </div>
                </div>
                <div className="rounded-md border border-border bg-secondary/30 px-3 py-2">
                  <div className="text-[10px] text-muted-foreground uppercase tracking-wide">Year + 1</div>
                  <div className="text-sm font-bold text-amber-300" data-testid="cap-floor-yr1">
                    ${(floorYr1 / 1_000_000).toFixed(1)}M
                  </div>
                </div>
                <div className="rounded-md border border-border bg-secondary/30 px-3 py-2">
                  <div className="text-[10px] text-muted-foreground uppercase tracking-wide">Year + 2</div>
                  <div className="text-sm font-bold text-amber-300" data-testid="cap-floor-yr2">
                    ${(floorYr2 / 1_000_000).toFixed(1)}M
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Iter 122 — Cap Floor Watchlist (commissioner-only) */}
        <CapFloorWatchlistCard leagueId={league?.id} isCommissioner={isCommissioner} />

        {/* Salary Cap Chart — pie or by-year bar */}
        <Card className="bg-card border-border">
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>Cap Breakdown</CardTitle>
            <Select value={chartFilter} onValueChange={(value: ChartFilter) => setChartFilter(value)}>
              <SelectTrigger className="w-[180px]" data-testid="cap-chart-filter">
                <SelectValue placeholder="Filter by..." />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Overview</SelectItem>
                <SelectItem value="players">By Player</SelectItem>
                <SelectItem value="position">By Position</SelectItem>
                <SelectItem value="by_year">By Year</SelectItem>
              </SelectContent>
            </Select>
          </CardHeader>
          <CardContent>
            <div className="h-[350px]" data-testid="cap-chart-container">
              <ResponsiveContainer width="100%" height="100%">
                {chartFilter === "by_year" ? (
                  <ComposedChart data={yearBreakdown} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="hsl(222, 30%, 20%)" />
                    <XAxis dataKey="label" stroke="hsl(215, 20%, 65%)" tick={{ fill: "hsl(215, 20%, 75%)" }} />
                    <YAxis
                      stroke="hsl(215, 20%, 65%)"
                      tick={{ fill: "hsl(215, 20%, 75%)" }}
                      tickFormatter={(v) => `$${(v / 1_000_000).toFixed(0)}M`}
                    />
                    <Tooltip
                      formatter={(value: number, name: string) => [formatCurrency(value), name]}
                      contentStyle={{
                        backgroundColor: "hsl(var(--card))",
                        border: "1px solid hsl(var(--border))",
                        borderRadius: "8px",
                        color: "hsl(var(--foreground))",
                      }}
                      labelStyle={{ color: "hsl(var(--foreground))" }}
                    />
                    <Legend
                      verticalAlign="bottom"
                      height={36}
                      formatter={legendFormatter}
                    />
                    <Bar dataKey="locked" stackId="cap" name="Locked Salary" fill={CHART_COLORS[0]} radius={[0, 0, 0, 0]} />
                    <Bar dataKey="dead" stackId="cap" name="Dead Cap (buyouts + retention)" fill={DEAD_CAP_COLOR} radius={[0, 0, 0, 0]} />
                    <Bar dataKey="available" stackId="cap" name="Available (UFAs/RFAs unsigned)" fill={CAP_SPACE_COLOR} radius={[4, 4, 0, 0]} />
                    {/* Iter 121 — Cap floor reference line. Only shown when the
                        league actually has a floor configured. Since floors are
                        year-specific, render a per-year ReferenceLine segment
                        using the same dataKey hook that recharts provides. */}
                    {floorEnabled && (
                      <Line
                        type="stepAfter"
                        dataKey="floor"
                        stroke="#f59e0b"
                        strokeWidth={2}
                        strokeDasharray="5 5"
                        dot={{ r: 3, fill: "#f59e0b" }}
                        name="Cap Floor"
                        legendType="line"
                      />
                    )}
                  </ComposedChart>
                ) : (
                  <PieChart>
                    <Pie
                      data={chartData}
                      cx="50%"
                      cy="50%"
                      innerRadius={60}
                      outerRadius={120}
                      paddingAngle={2}
                      dataKey="value"
                      nameKey="name"
                      label={({ name, value }) => `${name}: ${formatCurrency(value)}`}
                      labelLine={false}
                    >
                      {chartData.map((entry, index) => (
                        <Cell key={`cell-${index}`} fill={entry.color} stroke="hsl(222, 30%, 12%)" strokeWidth={1} />
                      ))}
                    </Pie>
                    <Tooltip
                      formatter={(value: number) => formatCurrency(value)}
                      contentStyle={{
                        backgroundColor: "hsl(var(--card))",
                        border: "1px solid hsl(var(--border))",
                        borderRadius: "8px",
                        color: "hsl(var(--foreground))",
                      }}
                      labelStyle={{ color: "hsl(var(--foreground))" }}
                    />
                    <Legend
                      verticalAlign="bottom"
                      height={36}
                      formatter={legendFormatter}
                    />
                  </PieChart>
                )}
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>

        {/* Cap Usage Progress */}
        <Card className="bg-card border-border">
          <CardHeader>
            <CardTitle>Cap Usage</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Used: {capUsagePercent.toFixed(1)}%</span>
                <span className="text-muted-foreground">Available: {(100 - capUsagePercent).toFixed(1)}%</span>
              </div>
              <Progress
                value={capUsagePercent}
                className={`h-4 ${capUsagePercent > 95 ? "bg-destructive/20" : "bg-secondary"}`}
              />
              <div className="flex flex-wrap gap-4 text-sm">
                <div className="flex items-center gap-2">
                  <div className="h-3 w-3 rounded-full" style={{ backgroundColor: CHART_COLORS[0] }}></div>
                  <span className="text-muted-foreground">Active Contracts</span>
                </div>
                {totalRetained > 0 && (
                  <div className="flex items-center gap-2">
                    <div className="h-3 w-3 rounded-full" style={{ backgroundColor: RETAINED_COLOR }}></div>
                    <span className="text-muted-foreground">Retained Salary</span>
                  </div>
                )}
                <div className="flex items-center gap-2">
                  <div className="h-3 w-3 rounded-full" style={{ backgroundColor: DEAD_CAP_COLOR }}></div>
                  <span className="text-muted-foreground">Dead Cap</span>
                </div>
                <div className="flex items-center gap-2">
                  <div className="h-3 w-3 rounded-full" style={{ backgroundColor: CAP_SPACE_COLOR }}></div>
                  <span className="text-muted-foreground">Cap Space</span>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Retained Salary Table */}
        {retainedSalaries.length > 0 && (
          <Card className="bg-card border-border">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                Retained Salary
                <Badge variant="destructive" className="ml-2">
                  ${(totalRetained / 1000000).toFixed(2)}M
                </Badge>
              </CardTitle>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow className="border-border">
                    <TableHead>Player</TableHead>
                    <TableHead>Traded To</TableHead>
                    <TableHead className="text-right">Retained Amount</TableHead>
                    <TableHead className="text-center">Years Left</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {retainedSalaries.map((retained) => (
                    <TableRow key={retained.id} className="border-border">
                      <TableCell className="font-medium">{retained.player}</TableCell>
                      <TableCell>
                        <Badge variant="outline" className="bg-secondary/50">
                          {retained.tradedTo}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-right font-semibold text-destructive">
                        ${(retained.retainedAmount / 1000000).toFixed(2)}M
                      </TableCell>
                      <TableCell className="text-center">
                        {retained.yearsRemaining} {retained.yearsRemaining === 1 ? "year" : "years"}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        )}

        {/* Contracts Table */}
        <Card className="bg-card border-border">
          <CardHeader>
            <CardTitle>Active Contracts</CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow className="border-border">
                  <TableHead
                    className="cursor-pointer select-none hover:text-foreground transition-colors"
                    onClick={() => handleSort("player")}
                    data-testid="contract-sort-player"
                  >
                    Player <SortIcon col="player" sortKey={sortKey} sortDir={sortDir} />
                  </TableHead>
                  <TableHead
                    className="text-center cursor-pointer select-none hover:text-foreground transition-colors"
                    onClick={() => handleSort("position")}
                    data-testid="contract-sort-position"
                  >
                    POS <SortIcon col="position" sortKey={sortKey} sortDir={sortDir} />
                  </TableHead>
                  <TableHead
                    className="text-right cursor-pointer select-none hover:text-foreground transition-colors"
                    onClick={() => handleSort("salary")}
                    data-testid="contract-sort-salary"
                  >
                    Salary <SortIcon col="salary" sortKey={sortKey} sortDir={sortDir} />
                  </TableHead>
                  <TableHead
                    className="text-center cursor-pointer select-none hover:text-foreground transition-colors"
                    onClick={() => handleSort("year")}
                    data-testid="contract-sort-year"
                  >
                    Year <SortIcon col="year" sortKey={sortKey} sortDir={sortDir} />
                  </TableHead>
                  <TableHead
                    className="text-center cursor-pointer select-none hover:text-foreground transition-colors"
                    onClick={() => handleSort("contract_ends")}
                    data-testid="contract-sort-ends"
                  >
                    Contract Ends <SortIcon col="contract_ends" sortKey={sortKey} sortDir={sortDir} />
                  </TableHead>
                  {buyoutsEnabled && (
                    <TableHead className="text-center text-xs">Actions</TableHead>
                  )}
                </TableRow>
              </TableHeader>
              <TableBody>
                {sortedContracts.map((contract) => (
                  <TableRow key={contract.id} className="border-border" data-testid={`contract-row-${contract.id}`}>
                    <TableCell>
                      <div className="flex items-center gap-3">
                        <div className="h-10 w-10 rounded-lg bg-secondary flex items-center justify-center text-xs font-bold">
                          {contract.team}
                        </div>
                        <div>
                          <button
                            type="button"
                            onClick={() => openPlayerCard(contract.id, contract.player, contract.position)}
                            className="font-medium hover:text-primary hover:underline transition-colors cursor-pointer text-left"
                            data-testid={`salary-cap-contract-link-${contract.id}`}
                          >
                            {contract.player}
                          </button>
                          <p className="text-xs text-muted-foreground">{contract.team}</p>
                        </div>
                      </div>
                    </TableCell>
                    <TableCell className="text-center">
                      <Badge variant="outline" className="bg-secondary/50">
                        {contract.position}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right font-semibold">
                      ${(contract.salary / 1000000).toFixed(2)}M
                    </TableCell>
                    <TableCell className="text-center" data-testid={`contract-year-${contract.id}`}>
                      <span className={contract.yearsRemaining <= 1 ? "text-accent font-medium" : "font-medium"}>
                        {contract.currentYear}/{contract.totalYears}
                      </span>
                    </TableCell>
                    <TableCell className="text-center" data-testid={`contract-ends-${contract.id}`}>
                      <Badge
                        variant="outline"
                        className={
                          contract.endStatus === "UFA"
                            ? "border-amber-500/40"
                            : contract.endStatus === "RFA"
                              ? "border-cyan-500/40"
                              : "border-border"
                        }
                        style={
                          contract.endStatus === "UFA"
                            ? { color: DEAD_CAP_COLOR, backgroundColor: "rgba(255, 176, 32, 0.12)" }
                            : contract.endStatus === "RFA"
                              ? { color: CHART_COLORS[0], backgroundColor: "rgba(0, 210, 255, 0.12)" }
                              : undefined
                        }
                      >
                        {contract.endStatus}/{contract.endYear}
                      </Badge>
                    </TableCell>
                    {buyoutsEnabled && (
                      <TableCell className="text-center">
                        {contract.yearsRemaining > 1 ? (
                          <BuyoutDialog contract={contract} onConfirm={buyOut} />
                        ) : (
                          <span className="text-[10px] text-muted-foreground italic">expiring</span>
                        )}
                      </TableCell>
                    )}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>

        {/* ── Iter 114: Dead Cap Ledger card ─────────────────────────── */}
        {deadCapSchedule.schedule.length > 0 && (
          <Card className="bg-card border-border">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <AlertTriangle className="h-5 w-5 text-accent" />
                Dead Cap Ledger
                <Badge variant="outline" className="ml-2 border-amber-500/40 text-amber-400">
                  ${(deadCapSchedule.total_dead_cap / 1_000_000).toFixed(2)}M total
                </Badge>
              </CardTitle>
              <p className="text-xs text-muted-foreground mt-1">
                Full history of every active buyout or salary retention this team is paying.
              </p>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow className="border-border">
                    <TableHead>Year</TableHead>
                    <TableHead className="text-center">Source</TableHead>
                    <TableHead>Player</TableHead>
                    <TableHead className="text-right">Annual Charge</TableHead>
                    <TableHead className="text-center">Action Date</TableHead>
                    {buyoutsEnabled && <TableHead className="text-center text-xs">Reverse</TableHead>}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {deadCapSchedule.schedule.flatMap((row: any) =>
                    row.entries.map((e: any, i: number) => (
                      <TableRow key={`${row.year}-${e.player_id}-${i}`} className="border-border" data-testid={`ledger-row-${row.year}-${e.player_id || i}`}>
                        <TableCell className="font-mono text-xs">{row.year}</TableCell>
                        <TableCell className="text-center">
                          <Badge
                            variant="outline"
                            className={
                              e.source === "retention"
                                ? "text-rose-400 border-rose-500/40"
                                : "text-amber-400 border-amber-500/40"
                            }
                          >
                            {e.source === "retention" ? "Retention" : "Buyout"}
                          </Badge>
                        </TableCell>
                        <TableCell>
                          <button
                            type="button"
                            onClick={() => openPlayerCard(e.player_id, e.player_name, undefined)}
                            className="font-medium text-sm hover:text-primary hover:underline transition-colors cursor-pointer text-left disabled:cursor-default disabled:hover:text-current disabled:no-underline"
                            data-testid={`salary-cap-ledger-link-${e.player_id || i}`}
                            disabled={!e.player_id}
                          >
                            {e.player_name || "—"}
                          </button>
                          {e.source === "buyout" && e.original_salary && (
                            <div className="text-[10px] text-muted-foreground">
                              {e.length_option || "default"} · was ${(e.original_salary / 1_000_000).toFixed(2)}M × {e.original_years_remaining}y
                            </div>
                          )}
                        </TableCell>
                        <TableCell className="text-right font-mono text-accent">
                          ${(e.amount / 1_000_000).toFixed(2)}M
                        </TableCell>
                        <TableCell className="text-center text-xs text-muted-foreground">
                          {e.created_at ? new Date(e.created_at).toLocaleDateString() : "—"}
                        </TableCell>
                        {buyoutsEnabled && (
                          <TableCell className="text-center">
                            {e.player_id && (
                              <AlertDialog>
                                <AlertDialogTrigger asChild>
                                  <Button
                                    size="sm"
                                    variant="ghost"
                                    className="h-7 w-7 p-0 text-rose-400 hover:bg-rose-500/15"
                                    title={`Commissioner: ${e.source === "buyout" ? "reverse buyout" : "waive retention"}`}
                                    data-testid={`ledger-reverse-${e.source}-${e.player_id}`}
                                  >
                                    ↺
                                  </Button>
                                </AlertDialogTrigger>
                                <AlertDialogContent>
                                  <AlertDialogHeader>
                                    <AlertDialogTitle>
                                      {e.source === "buyout" ? "Reverse buyout?" : "Waive retention?"}
                                    </AlertDialogTitle>
                                    <AlertDialogDescription>
                                      {e.source === "buyout"
                                        ? `This will remove every remaining buyout charge for ${e.player_name} and restore them to the roster.`
                                        : `This will waive the salary retention for ${e.player_name} across all remaining seasons.`}
                                      <span className="block mt-1 text-amber-400">
                                        Commissioner-only action.
                                      </span>
                                    </AlertDialogDescription>
                                  </AlertDialogHeader>
                                  <AlertDialogFooter>
                                    <AlertDialogCancel>Cancel</AlertDialogCancel>
                                    <AlertDialogAction
                                      onClick={() =>
                                        e.source === "buyout"
                                          ? reverseBuyout(e.player_id, e.player_name || "player")
                                          : cancelRetention(e.player_id, e.player_name || "player")
                                      }
                                      data-testid={`ledger-confirm-${e.source}-${e.player_id}`}
                                    >
                                      Confirm
                                    </AlertDialogAction>
                                  </AlertDialogFooter>
                                </AlertDialogContent>
                              </AlertDialog>
                            )}
                          </TableCell>
                        )}
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        )}
      </div>
      {/* Iter 232N.41 — Player-card drilldown modal */}
      {cardPlayer && (
        <PlayerCardModal open={cardOpen} onOpenChange={setCardOpen} player={cardPlayer} />
      )}
    </AppLayout>
  );
};

export default SalaryCap;
