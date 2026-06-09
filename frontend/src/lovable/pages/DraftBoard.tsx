// @ts-nocheck
import { useState, useMemo, useEffect } from "react";
import { AppLayout } from "@/components/layout/AppLayout";
import { useActiveLeague } from "@/hooks/use-active-league";
import { useAuth } from "@/contexts/AuthContext";
import api from "@/lib/api";
import LeagueContextBanner from "@/lovable/components/dashboard/LeagueContextBanner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Tooltip, TooltipContent, TooltipTrigger, TooltipProvider } from "@/components/ui/tooltip";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { ArrowRightLeft, Info, ChevronDown, ShoppingCart, CheckCircle2, Clock, AlertTriangle, CalendarDays, Repeat } from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { useTradeBuilder } from "@/lovable/state/TradeBuilderContext";

// League teams with acronyms (alphabetical default order)
const leagueTeams = [
  { name: "Arctic Wolves", abbr: "ARC" },
  { name: "Blizzard Kings", abbr: "BLZ" },
  { name: "Frozen Fury", abbr: "FRZ" },
  { name: "Glacier Bears", abbr: "GLC" },
  { name: "Ice Breakers", abbr: "ICE" },
  { name: "Northern Lights", abbr: "NTH" },
  { name: "Polar Phantoms", abbr: "POL" },
  { name: "Snow Hawks", abbr: "SNW" },
  { name: "Team Frostbite", abbr: "FRST" },
  { name: "Tundra Titans", abbr: "TND" },
  { name: "Winter Storm", abbr: "WST" },
  { name: "Zero Below", abbr: "ZRO" },
].sort((a, b) => a.name.localeCompare(b.name));

const totalRounds = 5;
const maxTradeYears = 3; // League allows picks to be dealt up to 3 years out

interface TradeRecord {
  date: string;
  from: string;
  to: string;
  details: string;
}

interface PickOwnership {
  originalTeam: string;
  currentOwner: string;
  tradeHistory: TradeRecord[];
}

// Mock data: pick ownership by year
const generatePickData = (): Record<string, Record<string, Record<number, PickOwnership>>> => {
  const data: Record<string, Record<string, Record<number, PickOwnership>>> = {};
  const years = ["2025", "2026", "2027"];

  years.forEach((year) => {
    data[year] = {};
    leagueTeams.forEach((team) => {
      data[year][team.abbr] = {};
      for (let round = 1; round <= totalRounds; round++) {
        data[year][team.abbr][round] = {
          originalTeam: team.abbr,
          currentOwner: team.abbr,
          tradeHistory: [],
        };
      }
    });
  });

  // 2025 trades
  data["2025"]["FRST"][1] = {
    originalTeam: "FRST",
    currentOwner: "ICE",
    tradeHistory: [
      { date: "2024-11-15", from: "FRST", to: "ICE", details: "FRST traded 2025 1st to ICE for Tyler Brooks + 2026 3rd" },
    ],
  };
  data["2025"]["BLZ"][2] = {
    originalTeam: "BLZ",
    currentOwner: "NTH",
    tradeHistory: [
      { date: "2024-09-20", from: "BLZ", to: "ARC", details: "BLZ traded 2025 2nd to ARC for Jake Miller" },
      { date: "2025-01-05", from: "ARC", to: "NTH", details: "ARC traded BLZ 2025 2nd to NTH for 2026 2nd" },
    ],
  };
  data["2025"]["POL"][3] = {
    originalTeam: "POL",
    currentOwner: "GLC",
    tradeHistory: [
      { date: "2025-02-10", from: "POL", to: "GLC", details: "POL traded 2025 3rd to GLC for Ryan Cooper" },
    ],
  };
  data["2025"]["SNW"][1] = {
    originalTeam: "SNW",
    currentOwner: "WST",
    tradeHistory: [
      { date: "2024-12-01", from: "SNW", to: "WST", details: "SNW traded 2025 1st to WST for Marcus Lee + 2026 4th" },
    ],
  };
  data["2025"]["TND"][4] = {
    originalTeam: "TND",
    currentOwner: "ZRO",
    tradeHistory: [
      { date: "2025-01-18", from: "TND", to: "ZRO", details: "TND traded 2025 4th to ZRO for prospect David Chen" },
    ],
  };

  // 2026 trades
  data["2026"]["ICE"][2] = {
    originalTeam: "ICE",
    currentOwner: "FRST",
    tradeHistory: [
      { date: "2025-01-10", from: "ICE", to: "FRST", details: "ICE traded 2026 2nd to FRST for 2025 waiver priority" },
    ],
  };
  data["2026"]["GLC"][1] = {
    originalTeam: "GLC",
    currentOwner: "ARC",
    tradeHistory: [
      { date: "2024-10-30", from: "GLC", to: "ARC", details: "GLC traded 2026 1st to ARC for Nick Andersen + 2025 5th" },
    ],
  };

  // 2027 trade
  data["2027"]["NTH"][1] = {
    originalTeam: "NTH",
    currentOwner: "BLZ",
    tradeHistory: [
      { date: "2025-02-01", from: "NTH", to: "BLZ", details: "NTH traded 2027 1st to BLZ for 2025 2nd + prospect" },
    ],
  };

  return data;
};

const allPickData = generatePickData();

// Picks that teams have made available on the trade block
const tradeBlockPicks: Set<string> = new Set([
  "2025-ICE-3",    // ICE has their 3rd round pick on the block
  "2025-GLC-2",    // GLC offering their 2nd
  "2025-NTH-4",    // NTH offering their 4th
  "2025-WST-5",    // WST offering their 5th
  "2026-ARC-1",    // ARC offering GLC's 2026 1st they acquired
  "2026-FRST-2",   // FRST offering ICE's 2026 2nd they acquired
  "2027-BLZ-1",    // BLZ offering NTH's 2027 1st they acquired
]);

function TradeHistoryPopover({ pick }: { pick: PickOwnership }) {
  const originalTeam = leagueTeams.find((t) => t.abbr === pick.originalTeam);
  const currentOwner = leagueTeams.find((t) => t.abbr === pick.currentOwner);

  return (
    <Popover>
      <PopoverTrigger asChild>
        <button className="flex items-center gap-1 text-xs font-semibold text-primary hover:text-primary/80 transition-colors cursor-pointer group">
          <span>{pick.currentOwner}</span>
          <ChevronDown className="h-3 w-3 opacity-60 group-hover:opacity-100 transition-opacity" />
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-80 p-0" align="start">
        <div className="p-3 border-b border-border">
          <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
            <ArrowRightLeft className="h-4 w-4 text-primary" />
            Trade History
          </div>
          <p className="text-xs text-muted-foreground mt-1">
            Originally: <span className="font-medium text-foreground">{originalTeam?.name} ({pick.originalTeam})</span>
            {" → "}
            Now: <span className="font-medium text-primary">{currentOwner?.name} ({pick.currentOwner})</span>
          </p>
        </div>
        <div className="p-2 space-y-2 max-h-60 overflow-y-auto">
          {pick.tradeHistory.map((trade: any, idx) => (
            <div
              key={idx}
              data-testid={trade.kind === "pick_upgrade" ? `pick-upgrade-${idx}` : `pick-trade-${idx}`}
              className={`p-2 rounded-md border space-y-1 ${
                trade.kind === "pick_upgrade"
                  ? "bg-amber-500/10 border-amber-500/30"
                  : "bg-secondary/50 border-border/50"
              }`}
            >
              <div className="flex items-center justify-between">
                <Badge
                  variant="outline"
                  className={`text-[10px] px-1.5 h-4 ${
                    trade.kind === "pick_upgrade" ? "border-amber-500/50 text-amber-500" : ""
                  }`}
                >
                  {trade.kind === "pick_upgrade"
                    ? (trade.toRound < trade.fromRound ? "PASS · Upgrade" : "PASS · Downgrade")
                    : `Trade ${idx + 1}`}
                </Badge>
                <span className="text-[10px] text-muted-foreground">
                  {trade.date ? (typeof trade.date === "string" ? trade.date.slice(0, 10) : String(trade.date)) : ""}
                </span>
              </div>
              {trade.kind === "pick_upgrade" ? (
                <>
                  <p className="text-xs leading-relaxed">
                    <span className="font-medium text-amber-500">
                      {trade.fromYear || ""} R{trade.fromRound} → {trade.toYear || trade.fromYear || ""} R{trade.toRound}
                    </span>
                  </p>
                  {trade.trigger && (
                    <p className="text-[11px] text-muted-foreground italic">
                      Trigger: {trade.trigger}
                    </p>
                  )}
                </>
              ) : (
                <>
                  <p className="text-xs text-muted-foreground leading-relaxed">
                    <span className="font-medium text-foreground">{trade.from}</span>
                    {" → "}
                    <span className="font-medium text-foreground">{trade.to}</span>
                  </p>
                  {trade.details && (
                    <p className="text-[11px] text-muted-foreground">{trade.details}</p>
                  )}
                </>
              )}
            </div>
          ))}
        </div>
      </PopoverContent>
    </Popover>
  );
}

// ────────────────────────────────────────────────────────────────
// Iter 138 — Draft Order Status banner + Results tab
// ────────────────────────────────────────────────────────────────

const METHOD_META: Record<string, { label: string; description: string }> = {
  nhl_lottery: {
    label: "NHL team draft lottery",
    description: "Pick order will mirror the official NHL Draft Lottery — date set by the system administrator.",
  },
  lottery_generator: {
    label: "Draft Lottery Generator",
    description: "League will run its own weighted lottery — commissioner schedules the date.",
  },
  manual_entry: {
    label: "Manual Entry",
    description: "Commissioner enters the draft order manually after the regular season — optional date.",
  },
};

function formatScheduled(iso?: string | null): string {
  if (!iso) return "TBD";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

function DraftOrderStatus({ draftOrder, year }: any) {
  if (!draftOrder) return null;
  const method = draftOrder.method || "manual_entry";
  const meta = METHOD_META[method] || METHOD_META.manual_entry;
  const isSet = !!draftOrder.is_set;
  const scheduled = formatScheduled(draftOrder.scheduled_at);
  return (
    <div
      className={cn(
        "rounded-md border p-3 flex flex-wrap items-center gap-3 text-sm",
        isSet
          ? "border-emerald-500/40 bg-emerald-500/5"
          : "border-amber-500/30 bg-amber-500/5",
      )}
      data-testid="draft-order-status-banner"
    >
      {isSet ? (
        <CheckCircle2 className="h-5 w-5 text-emerald-400 shrink-0" />
      ) : (
        <Clock className="h-5 w-5 text-amber-400 shrink-0" />
      )}
      <div className="flex flex-col">
        <span className="font-semibold" data-testid="draft-order-status-headline">
          {year} pick order: {isSet ? "SET" : "Not yet set"}
        </span>
        <span className="text-xs text-muted-foreground" data-testid="draft-order-status-method">
          Format: {meta.label}
          {!isSet && (
            <>
              {" · "}
              <span data-testid="draft-order-status-scheduled">
                Scheduled: {scheduled}
              </span>
              {draftOrder.schedule_source === "system" && scheduled !== "TBD" && (
                <span className="ml-1 italic">(set by system admin)</span>
              )}
            </>
          )}
        </span>
      </div>
    </div>
  );
}

function DraftOrderResultsTab({ leagueId, draftOrder, teams }: any) {
  const orderOK = !!draftOrder?.is_set;
  const method = draftOrder?.method || "manual_entry";
  const meta = METHOD_META[method] || METHOD_META.manual_entry;
  const scheduled = formatScheduled(draftOrder?.scheduled_at);
  const seedById: Record<string, number> = {};
  (draftOrder?.order || []).forEach((o: any) => { seedById[String(o.team_id)] = o.seed; });
  const orderedTeams = [...(teams || [])].sort((a: any, b: any) => {
    const aSeed = seedById[String(a.id)] ?? 9999;
    const bSeed = seedById[String(b.id)] ?? 9999;
    return aSeed - bSeed;
  });

  // Iter 143 — Expansion draft: show unprotected → protected players per team
  const [expansionBoard, setExpansionBoard] = useState<any[]>([]);
  const [showExpansion, setShowExpansion] = useState(false);
  useEffect(() => {
    if (!leagueId) return;
    api.get(`/leagues/${leagueId}/expansion-draft-board`)
      .then(({ data }) => {
        const rows = data?.teams || [];
        // Only show the listing when at least one team has players (else this is not an expansion league)
        const anyPlayers = rows.some((r: any) => (r.unprotected?.length || 0) + (r.protected?.length || 0) > 0);
        setExpansionBoard(rows);
        setShowExpansion(anyPlayers);
      })
      .catch(() => setShowExpansion(false));
  }, [leagueId]);

  return (
    <div className="space-y-6">
      {/* Iter 139 — Read-only summary; configuration lives in League Admin */}
      <Card className="border-border gradient-card" data-testid="draft-order-summary-card">
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2">
            <CalendarDays className="h-4 w-4 text-cyan-300" />
            Draft Order Configuration
            <Badge
              variant="outline"
              className="ml-1 text-[10px] border-border text-muted-foreground"
              data-testid="draft-order-summary-method"
            >
              {meta.label}
            </Badge>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          <div className="text-xs text-muted-foreground">{meta.description}</div>
          <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
            <div data-testid="draft-order-summary-status">
              <span className="text-muted-foreground text-xs uppercase tracking-wider mr-2">Status</span>
              {orderOK ? (
                <Badge variant="outline" className="border-emerald-500/40 text-emerald-300">SET</Badge>
              ) : (
                <Badge variant="outline" className="border-amber-500/40 text-amber-300">Not yet set</Badge>
              )}
            </div>
            <div data-testid="draft-order-summary-scheduled">
              <span className="text-muted-foreground text-xs uppercase tracking-wider mr-2">Scheduled</span>
              <span className="font-mono">{scheduled}</span>
              {draftOrder?.schedule_source === "system" && scheduled !== "TBD" && (
                <span className="ml-1 text-xs italic text-muted-foreground">(set by system admin)</span>
              )}
            </div>
          </div>
          <div className="rounded-md bg-muted/30 border border-border p-2 text-xs text-muted-foreground" data-testid="draft-order-admin-hint">
            Format + schedule are configured by the commissioner in{" "}
            <a
              href="/commissioner/settings"
              className="text-cyan-300 hover:underline"
              data-testid="draft-order-admin-link"
            >
              League Administration → Draft
            </a>.
          </div>
        </CardContent>
      </Card>

      {/* Results card — ordered list */}
      <Card className="border-border gradient-card" data-testid="draft-order-results-card">
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2">
            Draft Order Results
            {orderOK ? (
              <Badge variant="outline" className="border-emerald-500/40 text-emerald-300 text-[10px]">
                Final
              </Badge>
            ) : (
              <Badge variant="outline" className="border-amber-500/40 text-amber-300 text-[10px]">
                Pre-lottery preview
              </Badge>
            )}
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow className="border-border hover:bg-transparent">
                <TableHead className="w-[80px] text-xs uppercase tracking-wider text-muted-foreground pl-4">Pick</TableHead>
                <TableHead className="text-xs uppercase tracking-wider text-muted-foreground">Team</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {orderedTeams.map((t: any, idx: number) => (
                <TableRow key={t.id || t.abbr} className="border-border/50" data-testid={`draft-order-row-${idx + 1}`}>
                  <TableCell className="pl-4 font-mono text-sm">#{seedById[String(t.id)] || idx + 1}</TableCell>
                  <TableCell className="text-sm">{t.name} <span className="text-muted-foreground">({t.abbr})</span></TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
      {/* Iter 143 — Expansion draft: unprotected → protected listing */}
      {showExpansion && (
        <Card className="border-border gradient-card" data-testid="expansion-board-card">
          <CardHeader className="pb-3">
            <CardTitle className="text-base">Expansion Draft Board · Available Players</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-xs text-muted-foreground">
              Each team's unprotected players are listed first (available to be selected),
              followed by their protected list.
            </p>
            <div className="space-y-3" data-testid="expansion-board-teams">
              {expansionBoard.map((row: any) => (
                <div
                  key={row.team_id}
                  className="rounded-md border border-border p-3 space-y-2"
                  data-testid={`expansion-board-team-${row.team_abbr}`}
                >
                  <div className="flex items-center justify-between">
                    <div className="font-semibold text-sm">{row.team_name} <span className="text-muted-foreground">({row.team_abbr})</span></div>
                    {row.submitted ? (
                      <Badge variant="outline" className="text-[10px] border-emerald-500/40 text-emerald-300">
                        List submitted
                      </Badge>
                    ) : (
                      <Badge variant="outline" className="text-[10px] border-amber-500/40 text-amber-300">
                        No list yet
                      </Badge>
                    )}
                  </div>
                  <div>
                    <div className="text-[10px] uppercase tracking-wider text-emerald-300 font-semibold mb-1">
                      Unprotected ({row.unprotected?.length || 0})
                    </div>
                    {(row.unprotected || []).length === 0 ? (
                      <div className="text-xs italic text-muted-foreground">— no unprotected players —</div>
                    ) : (
                      <ul className="grid sm:grid-cols-2 gap-1 text-xs" data-testid={`expansion-unprotected-${row.team_abbr}`}>
                        {row.unprotected.map((p: any) => (
                          <li key={p.id} className="flex items-center justify-between gap-2 px-2 py-1 rounded bg-emerald-500/5">
                            <span>{p.name} <span className="text-muted-foreground">({p.position})</span></span>
                            {p.salary != null && (
                              <span className="font-mono text-muted-foreground">
                                ${(Number(p.salary) / 1_000_000).toFixed(2)}M
                              </span>
                            )}
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                  <div>
                    <div className="text-[10px] uppercase tracking-wider text-amber-300 font-semibold mb-1 mt-2">
                      Protected ({row.protected?.length || 0})
                    </div>
                    {(row.protected || []).length === 0 ? (
                      <div className="text-xs italic text-muted-foreground">— none —</div>
                    ) : (
                      <ul className="grid sm:grid-cols-2 gap-1 text-xs" data-testid={`expansion-protected-${row.team_abbr}`}>
                        {row.protected.map((p: any) => (
                          <li key={p.id} className="flex items-center justify-between gap-2 px-2 py-1 rounded bg-amber-500/5 text-muted-foreground">
                            <span>{p.name} <span>({p.position})</span></span>
                            {p.salary != null && (
                              <span className="font-mono">
                                ${(Number(p.salary) / 1_000_000).toFixed(2)}M
                              </span>
                            )}
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

export default function DraftBoardPage() {
  const currentYear = new Date().getFullYear();
  const availableYears = Array.from({ length: maxTradeYears }, (_, i) => String(currentYear + i));
  const [selectedYear, setSelectedYear] = useState(availableYears[0]);
  const { league, leagueTeams: liveLeagueTeams } = useActiveLeague();
  const { user } = useAuth();
  const isCommish = !!league && user && (
    league.commissioner_id === user.id ||
    (league.co_commissioners || []).includes(user.id) ||
    user.role === "admin"
  );
  const isSystemAdmin = user?.role === "admin";
  const [livePicks, setLivePicks] = useState<any[]>([]);
  // Iter 137 — league's canonical draft order (lottery applied OR reverse standings fallback)
  const [draftOrder, setDraftOrder] = useState<{ source: string; order: any[] } | null>(null);

  useEffect(() => {
    if (!league?.id) return;
    let cancelled = false;
    api.get(`/drafts/${league.id}/picks?year=${selectedYear}`).then(({ data }) => {
      if (!cancelled) setLivePicks(data?.picks || []);
    }).catch(() => {});
    api.get(`/leagues/${league.id}/draft-order?year=${selectedYear}`).then(({ data }) => {
      if (!cancelled) setDraftOrder({
        source: data?.source,
        order: data?.order || [],
        is_set: data?.is_set,
        method: data?.method,
        scheduled_at: data?.scheduled_at,
        schedule_source: data?.schedule_source,
      });
    }).catch(() => setDraftOrder(null));
    return () => { cancelled = true; };
  }, [league?.id, selectedYear]);

  // Build teams list + per-team abbr mapping from live data when available.
  const teams = useMemo(() => {
    const base = (() => {
      if (!liveLeagueTeams?.length) return leagueTeams;
      return liveLeagueTeams.map(t => ({
        name: t.name,
        abbr: t.logo_abbr || t.name.slice(0, 3).toUpperCase(),
        id: t.id,
      }));
    })();
    // Iter 137 — reorder by the league's canonical draft order when we have it.
    if (!draftOrder?.order?.length) return base;
    const seedById: Record<string, number> = {};
    draftOrder.order.forEach((o: any) => { seedById[String(o.team_id)] = o.seed; });
    return [...base].sort((a, b) => {
      const aSeed = seedById[String((a as any).id)] ?? 9999;
      const bSeed = seedById[String((b as any).id)] ?? 9999;
      return aSeed - bSeed;
    });
  }, [liveLeagueTeams, draftOrder]);

  // Map live pick rows -> {originalAbbr: {round: {currentOwner: abbr, tradeHistory:[]}}}
  const teamIdToAbbr = useMemo(() => {
    const m: Record<string, string> = {};
    teams.forEach(t => { if ((t as any).id) m[(t as any).id] = t.abbr; });
    return m;
  }, [teams]);
  const liveYearData = useMemo(() => {
    if (!livePicks?.length) return null;
    const data: Record<string, Record<number, any>> = {};
    livePicks.forEach(p => {
      const origAbbr = teamIdToAbbr[p.original_team_id];
      if (!origAbbr) return;
      if (!data[origAbbr]) data[origAbbr] = {};
      const history = (p.trade_history || []).map((h: any, i: number) => ({
        step: i + 1,
        from: teamIdToAbbr[h.from_team_id] || h.from_team_name,
        to: teamIdToAbbr[h.to_team_id] || h.to_team_name,
        date: h.traded_at || h.applied_at,
        tradeId: h.trade_id,
        kind: h.kind || "trade",
        fromRound: h.from_round,
        toRound: h.to_round,
        fromYear: h.from_year,
        toYear: h.to_year,
        trigger: h.trigger,
      }));
      data[origAbbr][p.round] = {
        currentOwner: teamIdToAbbr[p.current_team_id] || origAbbr,
        isTraded: p.current_team_id !== p.original_team_id,
        tradeHistory: history,
        pickId: p._id,
        pendingProtections: p.pending_protections || [],
      };
    });
    return data;
  }, [livePicks, teamIdToAbbr]);

  const yearData = liveYearData || allPickData[selectedYear] || {};

  // Count how many picks each team owns for this year
  const pickCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    teams.forEach((t) => (counts[t.abbr] = 0));

    teams.forEach((team) => {
      for (let round = 1; round <= totalRounds; round++) {
        const pick = yearData[team.abbr]?.[round];
        if (pick) {
          counts[pick.currentOwner] = (counts[pick.currentOwner] || 0) + 1;
        }
      }
    });
    return counts;
  }, [yearData, teams]);

  // Iter 140 — Propose-trade toggle: when ON, every pick cell shows a quick-add button
  const [tradeMode, setTradeMode] = useState(false);
  const tradeBuilder = useTradeBuilder();
  const myTeam = useMemo(() => {
    if (!user || !liveLeagueTeams?.length) return null;
    const mine = liveLeagueTeams.find((t: any) => t.owner_id === user.id);
    if (!mine) return null;
    return {
      id: mine.id,
      name: mine.name,
      abbr: mine.logo_abbr || mine.name.slice(0, 3).toUpperCase(),
      owner: user.username || user.email,
    };
  }, [user, liveLeagueTeams]);

  const handleAddPickToTrade = (pickInfo: any, teamAbbr: string, round: number) => {
    if (!league?.id) {
      toast.error("League context missing");
      return;
    }
    if (!myTeam) {
      toast.error("Join a team in this league to propose trades");
      return;
    }
    // Open the trade builder if it isn't open yet
    tradeBuilder.openBuilder({ leagueId: league.id, myTeam });
    // Resolve owner team object for the partner side
    const ownerAbbr = pickInfo?.currentOwner || teamAbbr;
    const ownerTeam = (liveLeagueTeams || []).find(
      (t: any) => (t.logo_abbr || t.name.slice(0, 3).toUpperCase()) === ownerAbbr,
    );
    const pickPayload: any = {
      id: pickInfo?.pickId || `${selectedYear}-${ownerAbbr}-R${round}`,
      year: Number(selectedYear),
      round,
      ownerTeamId: ownerTeam?.id,
      ownerTeamName: ownerTeam?.name || ownerAbbr,
      originalTeamId: (liveLeagueTeams || []).find(
        (t: any) => (t.logo_abbr || t.name.slice(0, 3).toUpperCase()) === teamAbbr,
      )?.id,
      originalTeamName: teamAbbr,
      label: `${selectedYear} Round ${round} (${teamAbbr})`,
    };
    tradeBuilder.addPick(pickPayload);
  };

  return (
    <AppLayout>
      <TooltipProvider>
        <div className="space-y-6">
          <LeagueContextBanner
            title="Draft Board"
            kpiLabel="Teams drafting"
            kpiValue={liveLeagueTeams?.length || 0}
            primaryHref="/drafts"
            primaryLabel="Open Draft Room"
          />
          {/* Header */}
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
            <div>
              <h1 className="text-2xl font-bold text-foreground">Draft Board</h1>
              <p className="text-sm text-muted-foreground">
                View pick ownership across the league. Click traded picks for full trade history.
              </p>
            </div>
            <div className="flex items-center gap-2">
              {/* Iter 140 — Propose Trade toggle */}
              <Button
                size="sm"
                variant={tradeMode ? "default" : "outline"}
                onClick={() => setTradeMode(v => !v)}
                data-testid="draft-board-trade-toggle"
                aria-pressed={tradeMode}
                className={tradeMode ? "bg-emerald-500 hover:bg-emerald-600 text-white" : ""}
              >
                <Repeat className="h-4 w-4 mr-1" />
                {tradeMode ? "Trade Mode: ON" : "Propose Trade"}
              </Button>
              <Select value={selectedYear} onValueChange={setSelectedYear}>
                <SelectTrigger className="w-[160px] bg-card border-border" data-testid="draft-board-year-select">
                  <SelectValue placeholder="Select Year" />
                </SelectTrigger>
                <SelectContent>
                  {availableYears.map((year) => (
                    <SelectItem key={year} value={year}>
                      {year} Draft
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          {/* Iter 138 — Pick-order status banner */}
          <DraftOrderStatus draftOrder={draftOrder} year={selectedYear} />

          {/* Iter 138 — Tabs: Board / Draft Order Results */}
          <Tabs defaultValue="board" className="w-full">
            <TabsList data-testid="draft-board-tabs">
              <TabsTrigger value="board" data-testid="draft-board-tab-board">Pick Ownership</TabsTrigger>
              <TabsTrigger value="order" data-testid="draft-board-tab-order">Draft Order Results</TabsTrigger>
            </TabsList>

            <TabsContent value="board" className="space-y-6 mt-6">

          {/* Summary badges */}
          <div className="flex flex-wrap gap-2">
            {teams.map((team) => {
              const count = pickCounts[team.abbr] || 0;
              const diff = count - totalRounds;
              return (
                <Tooltip key={(team as any).id || `${team.abbr}-summary`}>
                  <TooltipTrigger asChild>
                    <div
                      className={cn(
                        "px-3 py-1.5 rounded-md text-xs font-medium border cursor-default transition-colors",
                        diff > 0
                          ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-400"
                          : diff < 0
                          ? "bg-amber-500/10 border-amber-500/30 text-amber-400"
                          : "bg-secondary border-border text-muted-foreground"
                      )}
                    >
                      {team.abbr}: {count} pick{count !== 1 ? "s" : ""}
                    </div>
                  </TooltipTrigger>
                  <TooltipContent>
                    <p>{team.name} — {count} of {totalRounds} picks owned</p>
                    {diff > 0 && <p className="text-emerald-400">+{diff} acquired via trade</p>}
                    {diff < 0 && <p className="text-amber-400">{diff} traded away</p>}
                  </TooltipContent>
                </Tooltip>
              );
            })}
          </div>

          {/* Draft Board Table */}
          <Card className="border-border gradient-card">
            <CardHeader className="pb-3">
              <CardTitle className="text-base flex items-center gap-2">
                {selectedYear} Draft Pick Ownership
                <Tooltip>
                  <TooltipTrigger>
                    <Info className="h-4 w-4 text-muted-foreground" />
                  </TooltipTrigger>
                  <TooltipContent className="max-w-xs">
                    <p>Teams are listed alphabetically (default draft order). Traded picks show the current owner — click for full trade chain.</p>
                  </TooltipContent>
                </Tooltip>
              </CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              <ScrollArea className="w-full">
                <div className="min-w-[700px]">
                  <Table>
                    <TableHeader>
                      <TableRow className="border-border hover:bg-transparent">
                        <TableHead className="w-[180px] text-xs uppercase tracking-wider text-muted-foreground font-semibold pl-4">
                          Team
                        </TableHead>
                        {rounds.map((round) => (
                          <TableHead
                            key={round}
                            className="text-center text-xs uppercase tracking-wider text-muted-foreground font-semibold"
                          >
                            Rd {round}
                          </TableHead>
                        ))}
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {teams.map((team, teamIdx) => (
                        <TableRow
                          key={(team as any).id || `${team.abbr}-${teamIdx}`}
                          className={cn(
                            "border-border/50 transition-colors",
                            teamIdx % 2 === 0 ? "bg-card/30" : "bg-card/10"
                          )}
                        >
                          <TableCell className="pl-4">
                            <div className="flex items-center gap-2">
                              <div className="h-7 w-7 rounded-md bg-primary/10 border border-primary/20 flex items-center justify-center text-[10px] font-bold text-primary">
                                {team.abbr}
                              </div>
                              <div>
                                <p className="text-sm font-medium text-foreground leading-tight">{team.name}</p>
                                <p className="text-[10px] text-muted-foreground">
                                  {pickCounts[team.abbr] || 0} pick{(pickCounts[team.abbr] || 0) !== 1 ? "s" : ""}
                                </p>
                              </div>
                            </div>
                          </TableCell>
                          {rounds.map((round) => {
                            const pick = yearData[team.abbr]?.[round];
                            const isTraded = pick && pick.currentOwner !== pick.originalTeam;
                            const pickKey = `${selectedYear}-${pick?.currentOwner || team.abbr}-${round}`;
                            const isOnTradeBlock = tradeBlockPicks.has(pickKey);
                            const protections = (pick?.pendingProtections as any[]) || [];
                            const protectionLabel = (() => {
                              if (!protections.length) return null;
                              const p = protections[0];
                              if (p.subject_type === "pick" && p.metric === "pick_slot") {
                                return `Top-${p.threshold ?? "?"}`;
                              }
                              if (p.subject_type === "team") {
                                return p.metric === "won_championship" ? "Champ trigger"
                                  : p.metric === "won_draft_lottery" ? "Lottery trigger"
                                  : p.metric === "made_playoffs" ? "Playoffs trigger"
                                  : "Conditional";
                              }
                              if (p.subject_type === "player") return "Player trigger";
                              return "Conditional";
                            })();
                            const newRound = protections[0]?.new_round;
                            const direction = newRound && newRound < round ? "upgrade"
                              : newRound && newRound > round ? "downgrade" : null;

                            return (
                              <TableCell key={round} className="text-center py-3">
                                {pick && isTraded ? (
                                  <div className="flex flex-col items-center gap-0.5">
                                    <TradeHistoryPopover pick={pick} />
                                    <span className="text-[10px] text-muted-foreground/60 flex items-center gap-0.5">
                                      <ArrowRightLeft className="h-2.5 w-2.5" />
                                      traded
                                    </span>
                                    {isOnTradeBlock && (
                                      <Badge variant="outline" className="text-[9px] px-1 h-3.5 bg-amber-500/10 border-amber-500/30 text-amber-400 gap-0.5 mt-0.5">
                                        <ShoppingCart className="h-2 w-2" />
                                        Available
                                      </Badge>
                                    )}
                                    {tradeMode && (
                                      <Button
                                        size="sm"
                                        variant="ghost"
                                        className="h-5 px-1.5 mt-0.5 text-emerald-300 hover:bg-emerald-500/10"
                                        onClick={() => handleAddPickToTrade(pick, team.abbr, round)}
                                        data-testid={`draft-board-pick-trade-${team.abbr}-r${round}`}
                                        aria-label="Add pick to trade"
                                      >
                                        <Repeat className="h-3 w-3" />
                                      </Button>
                                    )}
                                    {protectionLabel && (
                                      <Badge
                                        data-testid={`pick-protection-${pick.pickId}`}
                                        variant="outline"
                                        className={`text-[9px] px-1 h-3.5 gap-0.5 mt-0.5 ${
                                          direction === "downgrade"
                                            ? "bg-rose-500/10 border-rose-500/30 text-rose-400"
                                            : "bg-emerald-500/10 border-emerald-500/30 text-emerald-400"
                                        }`}
                                      >
                                        Protected: {protectionLabel}
                                      </Badge>
                                    )}
                                  </div>
                                ) : (
                                  <div className="flex flex-col items-center gap-0.5">
                                    <span className="text-xs text-muted-foreground">{team.abbr}</span>
                                    {isOnTradeBlock && (
                                      <Badge variant="outline" className="text-[9px] px-1 h-3.5 bg-amber-500/10 border-amber-500/30 text-amber-400 gap-0.5 mt-0.5">
                                        <ShoppingCart className="h-2 w-2" />
                                        Available
                                      </Badge>
                                    )}
                                    {tradeMode && (
                                      <Button
                                        size="sm"
                                        variant="ghost"
                                        className="h-5 px-1.5 mt-0.5 text-emerald-300 hover:bg-emerald-500/10"
                                        onClick={() => handleAddPickToTrade(pick || { currentOwner: team.abbr }, team.abbr, round)}
                                        data-testid={`draft-board-pick-trade-${team.abbr}-r${round}`}
                                        aria-label="Add pick to trade"
                                      >
                                        <Repeat className="h-3 w-3" />
                                      </Button>
                                    )}
                                    {protectionLabel && (
                                      <Badge
                                        data-testid={`pick-protection-${pick?.pickId}`}
                                        variant="outline"
                                        className="text-[9px] px-1 h-3.5 bg-emerald-500/10 border-emerald-500/30 text-emerald-400 gap-0.5 mt-0.5"
                                      >
                                        Protected: {protectionLabel}
                                      </Badge>
                                    )}
                                  </div>
                                )}
                              </TableCell>
                            );
                          })}
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              </ScrollArea>
            </CardContent>
          </Card>

          {/* Legend */}
          <div className="flex items-center gap-4 text-xs text-muted-foreground">
            <div className="flex items-center gap-1.5">
              <div className="w-3 h-3 rounded bg-secondary border border-border" />
              <span>Owns original pick</span>
            </div>
            <div className="flex items-center gap-1.5">
              <div className="w-3 h-3 rounded bg-primary/20 border border-primary/30" />
              <span>Traded — click for history</span>
            </div>
            <div className="flex items-center gap-1.5">
              <ShoppingCart className="h-3 w-3 text-amber-400" />
              <span>Available on trade block</span>
            </div>
          </div>
            </TabsContent>

            {/* Iter 138/139 — Draft Order Results tab (READ-ONLY; config in League Admin) */}
            <TabsContent value="order" className="space-y-6 mt-6">
              <DraftOrderResultsTab
                leagueId={league?.id}
                draftOrder={draftOrder}
                teams={teams}
              />
            </TabsContent>
          </Tabs>
        </div>
      </TooltipProvider>
    </AppLayout>
  );
}
