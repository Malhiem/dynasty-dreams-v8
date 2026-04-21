// @ts-nocheck
import { useState } from "react";
import { AppLayout } from "@/components/layout/AppLayout";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Edit2, Save, RotateCcw, ChevronDown, ChevronRight } from "lucide-react";
import PlayerCardModal from "@/lovable/components/dashboard/PlayerCardModal";

interface Player {
  id: number;
  name: string;
  position: string;
  age: number;
  aav: number;
  contractYears: number;
  contractStatus: "Signed" | "RFA" | "UFA";
  currentPoints: number;
  projectedPoints: number[];
}

interface HistoricalData {
  year: number;
  totalSalary: number;
  projectedPF: number;
  actualPF: number;
}

interface HistoricalRosterPlayer {
  id: number;
  name: string;
  position: string;
  team: string;
  G: number;
  A: number;
  PPP: number;
  SOG: number;
  HIT: number;
  BLK: number;
  PIM: number;
  plusMinus: number;
  fantasyPts: number;
}

const historicalRosters: Record<number, HistoricalRosterPlayer[]> = {
  2022: [
    { id: 101, name: "Connor McDavid", position: "C", team: "EDM", G: 44, A: 79, PPP: 38, SOG: 256, HIT: 22, BLK: 14, PIM: 36, plusMinus: 20, fantasyPts: 612 },
    { id: 102, name: "Leon Draisaitl", position: "C", team: "EDM", G: 55, A: 55, PPP: 42, SOG: 238, HIT: 30, BLK: 12, PIM: 44, plusMinus: 14, fantasyPts: 581 },
    { id: 103, name: "Nathan MacKinnon", position: "C", team: "COL", G: 32, A: 56, PPP: 28, SOG: 220, HIT: 40, BLK: 26, PIM: 30, plusMinus: 18, fantasyPts: 498 },
    { id: 104, name: "Cale Makar", position: "D", team: "COL", G: 28, A: 58, PPP: 30, SOG: 214, HIT: 10, BLK: 110, PIM: 22, plusMinus: 28, fantasyPts: 472 },
    { id: 105, name: "Zach Hyman", position: "LW", team: "EDM", G: 27, A: 28, PPP: 14, SOG: 144, HIT: 74, BLK: 18, PIM: 22, plusMinus: 10, fantasyPts: 298 },
    { id: 106, name: "Artemi Panarin", position: "LW", team: "NYR", G: 22, A: 52, PPP: 28, SOG: 198, HIT: 16, BLK: 18, PIM: 34, plusMinus: 4, fantasyPts: 426 },
    { id: 107, name: "Igor Shesterkin", position: "G", team: "NYR", G: 0, A: 0, PPP: 0, SOG: 0, HIT: 0, BLK: 0, PIM: 0, plusMinus: 0, fantasyPts: 214 },
  ],
  2023: [
    { id: 101, name: "Connor McDavid", position: "C", team: "EDM", G: 64, A: 89, PPP: 45, SOG: 280, HIT: 26, BLK: 16, PIM: 32, plusMinus: 34, fantasyPts: 742 },
    { id: 102, name: "Leon Draisaitl", position: "C", team: "EDM", G: 52, A: 64, PPP: 48, SOG: 248, HIT: 32, BLK: 14, PIM: 48, plusMinus: 22, fantasyPts: 634 },
    { id: 103, name: "Nathan MacKinnon", position: "C", team: "COL", G: 39, A: 54, PPP: 32, SOG: 232, HIT: 38, BLK: 22, PIM: 28, plusMinus: 24, fantasyPts: 536 },
    { id: 104, name: "Cale Makar", position: "D", team: "COL", G: 22, A: 60, PPP: 26, SOG: 202, HIT: 12, BLK: 118, PIM: 18, plusMinus: 32, fantasyPts: 490 },
    { id: 108, name: "Quinn Hughes", position: "D", team: "VAN", G: 14, A: 68, PPP: 28, SOG: 188, HIT: 8, BLK: 96, PIM: 16, plusMinus: 26, fantasyPts: 448 },
    { id: 106, name: "Artemi Panarin", position: "LW", team: "NYR", G: 28, A: 54, PPP: 32, SOG: 210, HIT: 14, BLK: 20, PIM: 30, plusMinus: 8, fantasyPts: 468 },
    { id: 109, name: "Andrei Vasilevskiy", position: "G", team: "TBL", G: 0, A: 0, PPP: 0, SOG: 0, HIT: 0, BLK: 0, PIM: 0, plusMinus: 0, fantasyPts: 198 },
  ],
  2024: [
    { id: 101, name: "Connor McDavid", position: "C", team: "EDM", G: 54, A: 82, PPP: 42, SOG: 270, HIT: 24, BLK: 18, PIM: 34, plusMinus: 28, fantasyPts: 698 },
    { id: 102, name: "Leon Draisaitl", position: "C", team: "EDM", G: 48, A: 62, PPP: 44, SOG: 244, HIT: 28, BLK: 16, PIM: 52, plusMinus: 18, fantasyPts: 604 },
    { id: 103, name: "Nathan MacKinnon", position: "C", team: "COL", G: 51, A: 70, PPP: 40, SOG: 258, HIT: 42, BLK: 24, PIM: 32, plusMinus: 30, fantasyPts: 672 },
    { id: 104, name: "Cale Makar", position: "D", team: "COL", G: 26, A: 64, PPP: 34, SOG: 224, HIT: 14, BLK: 122, PIM: 20, plusMinus: 36, fantasyPts: 514 },
    { id: 108, name: "Quinn Hughes", position: "D", team: "VAN", G: 18, A: 72, PPP: 30, SOG: 196, HIT: 10, BLK: 100, PIM: 14, plusMinus: 30, fantasyPts: 468 },
    { id: 107, name: "Igor Shesterkin", position: "G", team: "NYR", G: 0, A: 0, PPP: 0, SOG: 0, HIT: 0, BLK: 0, PIM: 0, plusMinus: 0, fantasyPts: 228 },
    { id: 109, name: "Andrei Vasilevskiy", position: "G", team: "TBL", G: 0, A: 0, PPP: 0, SOG: 0, HIT: 0, BLK: 0, PIM: 0, plusMinus: 0, fantasyPts: 186 },
  ],
};



const mockPlayers: Player[] = [
  { id: 1, name: "Connor McDavid", position: "C", age: 28, aav: 12500000, contractYears: 4, contractStatus: "Signed", currentPoints: 128, projectedPoints: [130, 125, 120, 115, 110] },
  { id: 2, name: "Leon Draisaitl", position: "C", age: 29, aav: 8500000, contractYears: 2, contractStatus: "Signed", currentPoints: 110, projectedPoints: [108, 105, 100, 95, 90] },
  { id: 3, name: "Nathan MacKinnon", position: "C", age: 29, aav: 12600000, contractYears: 6, contractStatus: "Signed", currentPoints: 118, projectedPoints: [115, 112, 108, 105, 100] },
  { id: 4, name: "Cale Makar", position: "D", age: 26, aav: 9000000, contractYears: 5, contractStatus: "Signed", currentPoints: 90, projectedPoints: [92, 95, 93, 90, 88] },
  { id: 5, name: "Quinn Hughes", position: "D", age: 25, aav: 7850000, contractYears: 4, contractStatus: "Signed", currentPoints: 85, projectedPoints: [88, 90, 92, 90, 88] },
  { id: 6, name: "Zach Hyman", position: "LW", age: 32, aav: 5500000, contractYears: 3, contractStatus: "Signed", currentPoints: 54, projectedPoints: [50, 45, 40, 35, 30] },
  { id: 7, name: "Mikko Rantanen", position: "RW", age: 28, aav: 9250000, contractYears: 1, contractStatus: "Signed", currentPoints: 105, projectedPoints: [102, 100, 98, 95, 92] },
  { id: 8, name: "Artemi Panarin", position: "LW", age: 33, aav: 11642857, contractYears: 2, contractStatus: "Signed", currentPoints: 96, projectedPoints: [90, 85, 80, 75, 70] },
  { id: 9, name: "Igor Shesterkin", position: "G", age: 29, aav: 11500000, contractYears: 7, contractStatus: "Signed", currentPoints: 45, projectedPoints: [44, 43, 42, 40, 38] },
  { id: 10, name: "Andrei Vasilevskiy", position: "G", age: 30, aav: 9500000, contractYears: 4, contractStatus: "Signed", currentPoints: 42, projectedPoints: [41, 40, 38, 36, 34] },
];

const mockHistoricalData: HistoricalData[] = [
  { year: 2022, totalSalary: 75000000, projectedPF: 850, actualPF: 872 },
  { year: 2023, totalSalary: 78000000, projectedPF: 880, actualPF: 865 },
  { year: 2024, totalSalary: 82000000, projectedPF: 900, actualPF: 918 },
];

const currentYear = 2025;
const positionOrder = ["C", "LW", "RW", "D", "G"];
const salaryCapLimit = 88000000;

const DepthChart = () => {
  const [selectedYear, setSelectedYear] = useState<number>(currentYear);
  const [players, setPlayers] = useState<Player[]>(mockPlayers);
  const [editingProjections, setEditingProjections] = useState(false);
  const [customProjections, setCustomProjections] = useState<Record<number, number[]>>(() => {
    const initial: Record<number, number[]> = {};
    mockPlayers.forEach(p => {
      initial[p.id] = [...p.projectedPoints];
    });
    return initial;
  });
  const [expandedHistoryYears, setExpandedHistoryYears] = useState<Set<number>>(new Set());
  const [playerCardOpen, setPlayerCardOpen] = useState(false);
  const [selectedHistoricalPlayer, setSelectedHistoricalPlayer] = useState<HistoricalRosterPlayer | null>(null);

  const yearOffset = selectedYear - currentYear;
  const years = Array.from({ length: 6 }, (_, i) => currentYear + i);

  const getPlayerStatusForYear = (player: Player, yearOffset: number): { status: string; aav: number | null } => {
    if (yearOffset < player.contractYears) {
      return { status: "Signed", aav: player.aav };
    }
    const yearsAfterContract = yearOffset - player.contractYears;
    if (yearsAfterContract === 0) {
      return { status: player.age + yearOffset >= 27 ? "UFA" : "RFA", aav: null };
    }
    return { status: player.age + yearOffset >= 27 ? "UFA" : "RFA", aav: null };
  };

  const getProjectedPoints = (player: Player, yearOffset: number): number => {
    if (yearOffset < 0) return player.currentPoints;
    return customProjections[player.id]?.[yearOffset] ?? player.projectedPoints[yearOffset] ?? 0;
  };

  const handleProjectionChange = (playerId: number, yearIndex: number, value: string) => {
    const numValue = parseInt(value) || 0;
    setCustomProjections(prev => ({
      ...prev,
      [playerId]: prev[playerId].map((v, i) => i === yearIndex ? numValue : v)
    }));
  };

  const resetProjections = () => {
    const reset: Record<number, number[]> = {};
    mockPlayers.forEach(p => {
      reset[p.id] = [...p.projectedPoints];
    });
    setCustomProjections(reset);
  };

  const groupedPlayers = positionOrder.reduce((acc, pos) => {
    acc[pos] = players.filter(p => p.position === pos);
    return acc;
  }, {} as Record<string, Player[]>);

  const calculateTeamSummary = (yearOffset: number) => {
    let totalSalary = 0;
    let totalProjectedPF = 0;
    let signedCount = 0;
    let rfaCount = 0;
    let ufaCount = 0;

    players.forEach(player => {
      const status = getPlayerStatusForYear(player, yearOffset);
      if (status.aav) {
        totalSalary += status.aav;
        signedCount++;
      } else if (status.status === "RFA") {
        rfaCount++;
      } else {
        ufaCount++;
      }
      totalProjectedPF += getProjectedPoints(player, yearOffset);
    });

    return { totalSalary, totalProjectedPF, signedCount, rfaCount, ufaCount };
  };

  const summary = calculateTeamSummary(yearOffset);
  const capSpace = salaryCapLimit - summary.totalSalary;

  const formatSalary = (value: number) => {
    return `$${(value / 1000000).toFixed(2)}M`;
  };

  return (
    <AppLayout>
      <div className="space-y-6">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div>
            <h1 className="text-3xl font-bold">Depth Chart</h1>
            <p className="text-muted-foreground">Long-term team planning and projections</p>
          </div>
          <div className="flex items-center gap-3">
            <Select value={selectedYear.toString()} onValueChange={(v) => setSelectedYear(parseInt(v))}>
              <SelectTrigger className="w-[140px]">
                <SelectValue placeholder="Select Year" />
              </SelectTrigger>
              <SelectContent>
                {years.map(year => (
                  <SelectItem key={year} value={year.toString()}>
                    {year}-{(year + 1).toString().slice(-2)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {editingProjections ? (
              <div className="flex gap-2">
                <Button size="sm" variant="outline" onClick={resetProjections}>
                  <RotateCcw className="h-4 w-4 mr-1" /> Reset
                </Button>
                <Button size="sm" onClick={() => setEditingProjections(false)}>
                  <Save className="h-4 w-4 mr-1" /> Save
                </Button>
              </div>
            ) : (
              <Button size="sm" variant="outline" onClick={() => setEditingProjections(true)}>
                <Edit2 className="h-4 w-4 mr-1" /> Edit Projections
              </Button>
            )}
          </div>
        </div>

        {/* Team Summary */}
        <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">Total Salary</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{formatSalary(summary.totalSalary)}</div>
              <p className="text-xs text-muted-foreground">of {formatSalary(salaryCapLimit)} cap</p>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">Cap Space</CardTitle>
            </CardHeader>
            <CardContent>
              <div className={`text-2xl font-bold ${capSpace < 0 ? 'text-destructive' : 'text-green-500'}`}>
                {formatSalary(capSpace)}
              </div>
              <p className="text-xs text-muted-foreground">{capSpace < 0 ? 'Over cap!' : 'Available'}</p>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">Projected PF</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{summary.totalProjectedPF}</div>
              <p className="text-xs text-muted-foreground">Fantasy Points</p>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">Signed Players</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{summary.signedCount}</div>
              <p className="text-xs text-muted-foreground">Under contract</p>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">Pending FAs</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{summary.rfaCount + summary.ufaCount}</div>
              <p className="text-xs text-muted-foreground">{summary.rfaCount} RFA, {summary.ufaCount} UFA</p>
            </CardContent>
          </Card>
        </div>

        <Tabs defaultValue="depth" className="space-y-4">
          <TabsList>
            <TabsTrigger value="depth">Depth Chart</TabsTrigger>
            <TabsTrigger value="projections">Multi-Year Projections</TabsTrigger>
            <TabsTrigger value="history">Historical Data</TabsTrigger>
          </TabsList>

          <TabsContent value="depth">
            <Card>
              <CardHeader>
                <CardTitle>Roster Depth - {selectedYear}-{(selectedYear + 1).toString().slice(-2)} Season</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-6">
                  {positionOrder.map(position => (
                    <div key={position}>
                      <h3 className="font-semibold text-lg mb-2 flex items-center gap-2">
                        <Badge variant="outline">{position}</Badge>
                        <span className="text-muted-foreground text-sm">
                          ({groupedPlayers[position]?.length || 0} players)
                        </span>
                      </h3>
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead>Player</TableHead>
                            <TableHead>Age</TableHead>
                            <TableHead>AAV / Status</TableHead>
                            <TableHead>Contract</TableHead>
                            <TableHead className="text-right">Proj. PF</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {groupedPlayers[position]?.map(player => {
                            const status = getPlayerStatusForYear(player, yearOffset);
                            const projectedAge = player.age + yearOffset;
                            return (
                              <TableRow key={player.id}>
                                <TableCell className="font-medium">{player.name}</TableCell>
                                <TableCell>{projectedAge}</TableCell>
                                <TableCell>
                                  {status.aav ? (
                                    <span className="font-mono">{formatSalary(status.aav)}</span>
                                  ) : (
                                    <Badge variant={status.status === "RFA" ? "secondary" : "destructive"}>
                                      {status.status}
                                    </Badge>
                                  )}
                                </TableCell>
                                <TableCell>
                                  {player.contractYears - yearOffset > 0 ? (
                                    <span className="text-muted-foreground">
                                      {player.contractYears - yearOffset} yr{player.contractYears - yearOffset > 1 ? 's' : ''} left
                                    </span>
                                  ) : (
                                    <span className="text-muted-foreground">Expired</span>
                                  )}
                                </TableCell>
                                <TableCell className="text-right font-mono">
                                  {getProjectedPoints(player, yearOffset)}
                                </TableCell>
                              </TableRow>
                            );
                          })}
                        </TableBody>
                      </Table>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="projections">
            <Card>
              <CardHeader>
                <CardTitle>Multi-Year Player Projections</CardTitle>
              </CardHeader>
              <CardContent>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Player</TableHead>
                      <TableHead>Pos</TableHead>
                      {years.map(year => (
                        <TableHead key={year} className="text-center">
                          {year}-{(year + 1).toString().slice(-2)}
                        </TableHead>
                      ))}
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {players.map(player => (
                      <TableRow key={player.id}>
                        <TableCell className="font-medium">{player.name}</TableCell>
                        <TableCell>
                          <Badge variant="outline">{player.position}</Badge>
                        </TableCell>
                        {years.map((year, idx) => {
                          const status = getPlayerStatusForYear(player, idx);
                          const isUFA = status.status === "UFA" && !status.aav;
                          return (
                            <TableCell key={year} className="text-center">
                              <div className="flex flex-col items-center gap-1">
                                {isUFA ? (
                                  <Badge variant="destructive" className="text-xs">UFA</Badge>
                                ) : (
                                  <>
                                    {editingProjections ? (
                                      <Input
                                        type="number"
                                        value={customProjections[player.id]?.[idx] ?? 0}
                                        onChange={(e) => handleProjectionChange(player.id, idx, e.target.value)}
                                        className="w-16 h-8 text-center text-sm"
                                      />
                                    ) : (
                                      <span className="font-mono">{getProjectedPoints(player, idx)}</span>
                                    )}
                                    {!status.aav && status.status === "RFA" && (
                                      <Badge variant="secondary" className="text-xs">RFA</Badge>
                                    )}
                                  </>
                                )}
                              </div>
                            </TableCell>
                          );
                        })}
                      </TableRow>
                    ))}
                    <TableRow className="bg-muted/50 font-bold">
                      <TableCell colSpan={2}>Team Total PF</TableCell>
                      {years.map((_, idx) => (
                        <TableCell key={idx} className="text-center font-mono">
                          {players.reduce((sum, p) => {
                            const s = getPlayerStatusForYear(p, idx);
                            const isUFA = s.status === "UFA" && !s.aav;
                            return sum + (isUFA ? 0 : getProjectedPoints(p, idx));
                          }, 0)}
                        </TableCell>
                      ))}
                    </TableRow>
                    <TableRow className="bg-muted/50 font-bold">
                      <TableCell colSpan={2}>Committed Salary</TableCell>
                      {years.map((_, idx) => {
                        const totalSal = players.reduce((sum, p) => {
                          const status = getPlayerStatusForYear(p, idx);
                          return sum + (status.aav || 0);
                        }, 0);
                        return (
                          <TableCell key={idx} className="text-center font-mono">
                            {formatSalary(totalSal)}
                          </TableCell>
                        );
                      })}
                    </TableRow>
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="history">
            <Card>
              <CardHeader>
                <CardTitle>Historical Performance vs Projections</CardTitle>
              </CardHeader>
              <CardContent>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="w-8"></TableHead>
                      <TableHead>Season</TableHead>
                      <TableHead>Total Salary</TableHead>
                      <TableHead>Projected PF</TableHead>
                      <TableHead>Actual PF</TableHead>
                      <TableHead>Variance</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {mockHistoricalData.map(data => {
                      const variance = data.actualPF - data.projectedPF;
                      const isExpanded = expandedHistoryYears.has(data.year);
                      const roster = historicalRosters[data.year] ?? [];
                      return (
                        <>
                          <TableRow
                            key={data.year}
                            className="cursor-pointer hover:bg-muted/50"
                            onClick={() => {
                              setExpandedHistoryYears(prev => {
                                const next = new Set(prev);
                                isExpanded ? next.delete(data.year) : next.add(data.year);
                                return next;
                              });
                            }}
                          >
                            <TableCell>
                              {isExpanded
                                ? <ChevronDown className="h-4 w-4 text-muted-foreground" />
                                : <ChevronRight className="h-4 w-4 text-muted-foreground" />}
                            </TableCell>
                            <TableCell className="font-medium">
                              {data.year}-{(data.year + 1).toString().slice(-2)}
                            </TableCell>
                            <TableCell className="font-mono">{formatSalary(data.totalSalary)}</TableCell>
                            <TableCell className="font-mono">{data.projectedPF}</TableCell>
                            <TableCell className="font-mono">{data.actualPF}</TableCell>
                            <TableCell>
                              <span className={`font-mono ${variance >= 0 ? 'text-green-500' : 'text-destructive'}`}>
                                {variance >= 0 ? '+' : ''}{variance}
                              </span>
                            </TableCell>
                          </TableRow>

                          {isExpanded && (
                            <TableRow key={`${data.year}-roster`} className="bg-muted/20">
                              <TableCell colSpan={6} className="p-0">
                                <div className="px-6 py-4">
                                  <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-3">
                                    {data.year}-{(data.year + 1).toString().slice(-2)} Roster — Player Contributions
                                  </p>
                                  <div className="overflow-x-auto">
                                    <table className="w-full text-sm">
                                      <thead>
                                        <tr className="border-b border-border">
                                          <th className="text-left py-2 pr-4 text-xs text-muted-foreground font-medium">Player</th>
                                          <th className="text-center py-2 px-2 text-xs text-muted-foreground font-medium">POS</th>
                                          <th className="text-center py-2 px-2 text-xs text-muted-foreground font-medium">G</th>
                                          <th className="text-center py-2 px-2 text-xs text-muted-foreground font-medium">A</th>
                                          <th className="text-center py-2 px-2 text-xs text-muted-foreground font-medium">PPP</th>
                                          <th className="text-center py-2 px-2 text-xs text-muted-foreground font-medium">SOG</th>
                                          <th className="text-center py-2 px-2 text-xs text-muted-foreground font-medium">HIT</th>
                                          <th className="text-center py-2 px-2 text-xs text-muted-foreground font-medium">BLK</th>
                                          <th className="text-center py-2 px-2 text-xs text-muted-foreground font-medium">PIM</th>
                                          <th className="text-center py-2 px-2 text-xs text-muted-foreground font-medium">+/-</th>
                                          <th className="text-right py-2 pl-4 text-xs text-muted-foreground font-medium">FPTS</th>
                                        </tr>
                                      </thead>
                                      <tbody>
                                        {roster.map(p => (
                                          <tr key={p.id} className="border-b border-border/30 hover:bg-muted/30">
                                            <td className="py-2 pr-4">
                                              <button
                                                className="text-primary hover:underline font-medium text-left"
                                                onClick={(e) => {
                                                  e.stopPropagation();
                                                  setSelectedHistoricalPlayer(p);
                                                  setPlayerCardOpen(true);
                                                }}
                                              >
                                                {p.name}
                                              </button>
                                            </td>
                                            <td className="py-2 px-2 text-center">
                                              <Badge variant="outline" className="text-[10px] px-1 py-0">{p.position}</Badge>
                                            </td>
                                            <td className="py-2 px-2 text-center font-mono">{p.G}</td>
                                            <td className="py-2 px-2 text-center font-mono">{p.A}</td>
                                            <td className="py-2 px-2 text-center font-mono">{p.PPP}</td>
                                            <td className="py-2 px-2 text-center font-mono">{p.SOG}</td>
                                            <td className="py-2 px-2 text-center font-mono">{p.HIT}</td>
                                            <td className="py-2 px-2 text-center font-mono">{p.BLK}</td>
                                            <td className="py-2 px-2 text-center font-mono">{p.PIM}</td>
                                            <td className="py-2 px-2 text-center font-mono">{p.plusMinus >= 0 ? `+${p.plusMinus}` : p.plusMinus}</td>
                                            <td className="py-2 pl-4 text-right font-mono font-semibold text-primary">{p.fantasyPts}</td>
                                          </tr>
                                        ))}
                                        <tr className="bg-muted/40 font-bold">
                                          <td colSpan={10} className="py-2 pr-4 text-right text-xs text-muted-foreground">Team Total Fantasy Points</td>
                                          <td className="py-2 pl-4 text-right font-mono text-primary">
                                            {roster.reduce((sum, p) => sum + p.fantasyPts, 0)}
                                          </td>
                                        </tr>
                                      </tbody>
                                    </table>
                                  </div>
                                </div>
                              </TableCell>
                            </TableRow>
                          )}
                        </>
                      );
                    })}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>

        {selectedHistoricalPlayer && (
          <PlayerCardModal
            open={playerCardOpen}
            onOpenChange={(open) => {
              setPlayerCardOpen(open);
              if (!open) setSelectedHistoricalPlayer(null);
            }}
            defaultTab="career-stats"
            player={{
              id: selectedHistoricalPlayer.id,
              name: selectedHistoricalPlayer.name,
              position: selectedHistoricalPlayer.position,
              team: selectedHistoricalPlayer.team,
              points: selectedHistoricalPlayer.fantasyPts,
              dynastyValue: 75,
              trend: "stable" as const,
              age: 28,
              contract: { salary: 7500000, yearsRemaining: 2, type: "Signed" as const },
              rosterSection: "Starting",
              statsByPeriod: { "1d": 2, "7d": 14, "14d": 26, "30d": 48, "60d": 92, "100d": 140, season: selectedHistoricalPlayer.fantasyPts },
              categoryBreakdown: {
                G: selectedHistoricalPlayer.G,
                A: selectedHistoricalPlayer.A,
                PPP: selectedHistoricalPlayer.PPP,
                SOG: selectedHistoricalPlayer.SOG,
                HIT: selectedHistoricalPlayer.HIT,
                BLK: selectedHistoricalPlayer.BLK,
                PIM: selectedHistoricalPlayer.PIM,
                "+/-": selectedHistoricalPlayer.plusMinus,
              },
              matchupGames: 3,
              schedule: Array.from({ length: 15 }, (_, i) => ({
                date: `Feb ${i + 1}, 2026`,
                opponent: ["BOS", "TOR", "MTL", "NYR", "COL"][i % 5],
                played: i < 10,
                goals: i < 10 ? Math.floor(Math.random() * 2) : undefined,
                assists: i < 10 ? Math.floor(Math.random() * 2) : undefined,
                pts: i < 10 ? Math.floor(Math.random() * 3) : undefined,
              })),
            }}
          />
        )}
      </div>
    </AppLayout>
  );
};

export default DepthChart;
