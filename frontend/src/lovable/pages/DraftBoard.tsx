// @ts-nocheck
import { useState, useMemo } from "react";
import { AppLayout } from "@/components/layout/AppLayout";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Tooltip, TooltipContent, TooltipTrigger, TooltipProvider } from "@/components/ui/tooltip";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ArrowRightLeft, Info, ChevronDown, ShoppingCart } from "lucide-react";
import { cn } from "@/lib/utils";

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
          {pick.tradeHistory.map((trade, idx) => (
            <div
              key={idx}
              className="p-2 rounded-md bg-secondary/50 border border-border/50 space-y-1"
            >
              <div className="flex items-center justify-between">
                <Badge variant="outline" className="text-[10px] px-1.5 h-4">
                  Trade {idx + 1}
                </Badge>
                <span className="text-[10px] text-muted-foreground">{trade.date}</span>
              </div>
              <p className="text-xs text-muted-foreground leading-relaxed">
                <span className="font-medium text-foreground">{trade.from}</span>
                {" → "}
                <span className="font-medium text-foreground">{trade.to}</span>
              </p>
              <p className="text-[11px] text-muted-foreground">{trade.details}</p>
            </div>
          ))}
        </div>
      </PopoverContent>
    </Popover>
  );
}

export default function DraftBoardPage() {
  const currentYear = new Date().getFullYear();
  const availableYears = Array.from({ length: maxTradeYears }, (_, i) => String(currentYear + i));
  const [selectedYear, setSelectedYear] = useState(availableYears[0]);

  const yearData = allPickData[selectedYear] || {};

  // Count how many picks each team owns for this year
  const pickCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    leagueTeams.forEach((t) => (counts[t.abbr] = 0));
    
    leagueTeams.forEach((team) => {
      for (let round = 1; round <= totalRounds; round++) {
        const pick = yearData[team.abbr]?.[round];
        if (pick) {
          counts[pick.currentOwner] = (counts[pick.currentOwner] || 0) + 1;
        }
      }
    });
    return counts;
  }, [yearData]);

  const rounds = Array.from({ length: totalRounds }, (_, i) => i + 1);

  return (
    <AppLayout>
      <TooltipProvider>
        <div className="space-y-6">
          {/* Header */}
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
            <div>
              <h1 className="text-2xl font-bold text-foreground">Draft Board</h1>
              <p className="text-sm text-muted-foreground">
                View pick ownership across the league. Click traded picks for full trade history.
              </p>
            </div>
            <Select value={selectedYear} onValueChange={setSelectedYear}>
              <SelectTrigger className="w-[160px] bg-card border-border">
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

          {/* Summary badges */}
          <div className="flex flex-wrap gap-2">
            {leagueTeams.map((team) => {
              const count = pickCounts[team.abbr] || 0;
              const diff = count - totalRounds;
              return (
                <Tooltip key={team.abbr}>
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
                      {leagueTeams.map((team, teamIdx) => (
                        <TableRow
                          key={team.abbr}
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
        </div>
      </TooltipProvider>
    </AppLayout>
  );
}
