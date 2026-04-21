// @ts-nocheck
import { useState, useMemo } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Calendar, CalendarDays, Plus, Pencil, Trash2, Trophy, ChevronRight } from "lucide-react";
import { toast } from "sonner";

interface ScoringPeriod {
  id: number;
  startDate: string;
  endDate: string;
  label?: string;
  type: "regular" | "playoff";
  bracketId?: string;
}

interface PlayoffBracket {
  id: string;
  name: string;
  rounds: number;
  teams: number;
}

const generatePeriods = (
  start: string,
  end: string,
  interval: string,
  type: "regular" | "playoff",
  startId: number = 1,
  bracketId?: string
): ScoringPeriod[] => {
  const periods: ScoringPeriod[] = [];
  const startDate = new Date(start);
  const endDate = new Date(end);
  let id = startId;
  let current = new Date(startDate);

  const intervalDays = interval === "daily" ? 1 : interval === "weekly" ? 7 : interval === "biweekly" ? 14 : 30;

  while (current < endDate) {
    const periodEnd = new Date(current);
    periodEnd.setDate(periodEnd.getDate() + intervalDays - 1);
    if (periodEnd > endDate) periodEnd.setTime(endDate.getTime());

    periods.push({
      id,
      startDate: current.toISOString().split("T")[0],
      endDate: periodEnd.toISOString().split("T")[0],
      type,
      bracketId,
    });

    current = new Date(periodEnd);
    current.setDate(current.getDate() + 1);
    id++;
  }

  return periods;
};

const formatDate = (dateStr: string) => {
  const d = new Date(dateStr + "T00:00:00");
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
};

const getDays = (start: string, end: string) => {
  const s = new Date(start);
  const e = new Date(end);
  return Math.round((e.getTime() - s.getTime()) / (1000 * 60 * 60 * 24)) + 1;
};

const SchedulesTab = () => {
  const [subTab, setSubTab] = useState("regular");

  // Regular season config
  const [seasonStart, setSeasonStart] = useState("2025-10-07");
  const [seasonEnd, setSeasonEnd] = useState("2026-03-29");
  const [scoringInterval, setScoringInterval] = useState("weekly");
  const [startDay, setStartDay] = useState("monday");
  const [mergeWeeks, setMergeWeeks] = useState("1");
  const [schedulingStrategy, setSchedulingStrategy] = useState("even");
  const [matchupsPerPeriod, setMatchupsPerPeriod] = useState("1");

  // Playoff config
  const [playoffStart, setPlayoffStart] = useState("2026-03-30");
  const [playoffEnd, setPlayoffEnd] = useState("2026-04-14");
  const [playoffInterval, setPlayoffInterval] = useState("weekly");

  // Scoring periods
  const [regularPeriods, setRegularPeriods] = useState<ScoringPeriod[]>(
    generatePeriods("2025-10-07", "2026-03-29", "weekly", "regular")
  );
  const [playoffPeriods, setPlayoffPeriods] = useState<ScoringPeriod[]>(
    generatePeriods("2026-03-30", "2026-04-14", "weekly", "playoff")
  );

  // Playoff brackets
  const [brackets, setBrackets] = useState<PlayoffBracket[]>([
    { id: "championship", name: "Championship Bracket", rounds: 3, teams: 8 },
  ]);
  const [newBracketName, setNewBracketName] = useState("");

  // Edit modal
  const [editingPeriod, setEditingPeriod] = useState<ScoringPeriod | null>(null);
  const [editStart, setEditStart] = useState("");
  const [editEnd, setEditEnd] = useState("");

  // Bracket dialog
  const [bracketDialogOpen, setBracketDialogOpen] = useState(false);
  const [editingBracket, setEditingBracket] = useState<PlayoffBracket | null>(null);
  const [bracketName, setBracketName] = useState("");
  const [bracketRounds, setBracketRounds] = useState("3");
  const [bracketTeams, setBracketTeams] = useState("8");

  const numTeams = 12;

  const regenerateRegular = () => {
    const periods = generatePeriods(seasonStart, seasonEnd, scoringInterval, "regular");
    const merge = parseInt(mergeWeeks);
    if (merge > 1 && periods.length >= merge) {
      const merged: ScoringPeriod = {
        id: 1,
        startDate: periods[0].startDate,
        endDate: periods[merge - 1].endDate,
        type: "regular",
      };
      const rest = periods.slice(merge).map((p, i) => ({ ...p, id: i + 2 }));
      setRegularPeriods([merged, ...rest]);
    } else {
      setRegularPeriods(periods);
    }
    toast.success("Regular season periods regenerated");
  };

  const regeneratePlayoffs = () => {
    const periods = generatePeriods(playoffStart, playoffEnd, playoffInterval, "playoff");
    setPlayoffPeriods(periods);
    toast.success("Playoff periods regenerated");
  };

  const openEditPeriod = (period: ScoringPeriod) => {
    setEditingPeriod(period);
    setEditStart(period.startDate);
    setEditEnd(period.endDate);
  };

  const saveEditPeriod = () => {
    if (!editingPeriod) return;
    const update = (periods: ScoringPeriod[]) =>
      periods.map((p) => (p.id === editingPeriod.id && p.type === editingPeriod.type ? { ...p, startDate: editStart, endDate: editEnd } : p));
    if (editingPeriod.type === "regular") {
      setRegularPeriods(update);
    } else {
      setPlayoffPeriods(update);
    }
    setEditingPeriod(null);
    toast.success(`Period ${editingPeriod.id} updated`);
  };

  const openBracketDialog = (bracket?: PlayoffBracket) => {
    if (bracket) {
      setEditingBracket(bracket);
      setBracketName(bracket.name);
      setBracketRounds(bracket.rounds.toString());
      setBracketTeams(bracket.teams.toString());
    } else {
      setEditingBracket(null);
      setBracketName("");
      setBracketRounds("3");
      setBracketTeams("4");
    }
    setBracketDialogOpen(true);
  };

  const saveBracket = () => {
    if (!bracketName.trim()) return;
    if (editingBracket) {
      setBrackets((prev) =>
        prev.map((b) =>
          b.id === editingBracket.id
            ? { ...b, name: bracketName, rounds: parseInt(bracketRounds), teams: parseInt(bracketTeams) }
            : b
        )
      );
      toast.success(`"${bracketName}" updated`);
    } else {
      const newBracket: PlayoffBracket = {
        id: `bracket-${Date.now()}`,
        name: bracketName,
        rounds: parseInt(bracketRounds),
        teams: parseInt(bracketTeams),
      };
      setBrackets((prev) => [...prev, newBracket]);
      toast.success(`"${bracketName}" created`);
    }
    setBracketDialogOpen(false);
  };

  const deleteBracket = (id: string) => {
    setBrackets((prev) => prev.filter((b) => b.id !== id));
    toast.success("Bracket removed");
  };

  // Combined projection
  const allPeriods = useMemo(() => {
    const combined: (ScoringPeriod & { globalIndex: number; sectionLabel: string })[] = [];
    regularPeriods.forEach((p, i) => {
      combined.push({ ...p, globalIndex: i + 1, sectionLabel: "Regular Season" });
    });
    playoffPeriods.forEach((p, i) => {
      combined.push({ ...p, globalIndex: regularPeriods.length + i + 1, sectionLabel: "Playoffs" });
    });
    return combined;
  }, [regularPeriods, playoffPeriods]);

  const totalRegularDays = regularPeriods.reduce((sum, p) => sum + getDays(p.startDate, p.endDate), 0);
  const totalPlayoffDays = playoffPeriods.reduce((sum, p) => sum + getDays(p.startDate, p.endDate), 0);

  const PeriodTable = ({ periods, type }: { periods: ScoringPeriod[]; type: "regular" | "playoff" }) => (
    <div className="max-h-[400px] overflow-y-auto">
      <Table>
        <TableHeader>
          <TableRow className="border-border">
            <TableHead className="text-muted-foreground w-[70px]">Period</TableHead>
            <TableHead className="text-muted-foreground">Start Date</TableHead>
            <TableHead className="text-muted-foreground">End Date</TableHead>
            <TableHead className="text-muted-foreground text-right w-[70px]">Days</TableHead>
            <TableHead className="text-muted-foreground text-right w-[70px]">Actions</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {periods.map((period) => {
            const days = getDays(period.startDate, period.endDate);
            return (
              <TableRow key={`${type}-${period.id}`} className="border-border">
                <TableCell className="font-medium text-sm">{period.id}</TableCell>
                <TableCell className="text-sm">{formatDate(period.startDate)}</TableCell>
                <TableCell className="text-sm">{formatDate(period.endDate)}</TableCell>
                <TableCell className="text-right tabular-nums text-sm">
                  <span className={days < 5 ? "text-yellow-400 font-medium" : "text-muted-foreground"}>
                    {days}d
                  </span>
                </TableCell>
                <TableCell className="text-right">
                  <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => openEditPeriod(period)}>
                    <Pencil className="h-3.5 w-3.5" />
                  </Button>
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );

  return (
    <div className="space-y-6">
      <Tabs value={subTab} onValueChange={setSubTab}>
        <TabsList className="bg-secondary border border-border">
          <TabsTrigger value="regular" className="data-[state=active]:bg-primary/20">
            <Calendar className="h-4 w-4 mr-2" />
            Regular Season
          </TabsTrigger>
          <TabsTrigger value="playoffs" className="data-[state=active]:bg-primary/20">
            <Trophy className="h-4 w-4 mr-2" />
            Playoffs
          </TabsTrigger>
          <TabsTrigger value="projection" className="data-[state=active]:bg-primary/20">
            <CalendarDays className="h-4 w-4 mr-2" />
            Full Schedule Projection
          </TabsTrigger>
        </TabsList>

        {/* ── Regular Season ── */}
        <TabsContent value="regular" className="space-y-6">
          <Card className="bg-card border-border">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Calendar className="h-5 w-5 text-primary" />
                Regular Season Dates
              </CardTitle>
              <CardDescription>Set the start and end dates for the regular season</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <Label>Beginning Scoring Period</Label>
                  <Input type="date" value={seasonStart} onChange={(e) => setSeasonStart(e.target.value)} className="bg-secondary border-border" />
                </div>
                <div className="space-y-2">
                  <Label>Ending Scoring Period</Label>
                  <Input type="date" value={seasonEnd} onChange={(e) => setSeasonEnd(e.target.value)} className="bg-secondary border-border" />
                </div>
              </div>
            </CardContent>
          </Card>

          <Card className="bg-card border-border">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <CalendarDays className="h-5 w-5 text-primary" />
                Scoring Period Configuration
              </CardTitle>
              <CardDescription>Define how the regular season is divided into scoring periods</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                <div className="space-y-2">
                  <Label>Scoring Period Interval</Label>
                  <Select value={scoringInterval} onValueChange={setScoringInterval}>
                    <SelectTrigger className="bg-secondary border-border"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="daily">Daily</SelectItem>
                      <SelectItem value="weekly">Weekly</SelectItem>
                      <SelectItem value="biweekly">Bi-Weekly</SelectItem>
                      <SelectItem value="monthly">Monthly</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label>Scoring Period Start Day</Label>
                  <Select value={startDay} onValueChange={setStartDay}>
                    <SelectTrigger className="bg-secondary border-border"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"].map((day) => (
                        <SelectItem key={day} value={day}>{day.charAt(0).toUpperCase() + day.slice(1)}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label>Merge First N Weeks</Label>
                  <Select value={mergeWeeks} onValueChange={setMergeWeeks}>
                    <SelectTrigger className="bg-secondary border-border"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="1">1 Week (No Merge)</SelectItem>
                      <SelectItem value="2">2 Weeks</SelectItem>
                      <SelectItem value="3">3 Weeks</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <Separator />

              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <Label>Scheduling Strategy</Label>
                  <Select value={schedulingStrategy} onValueChange={setSchedulingStrategy}>
                    <SelectTrigger className="bg-secondary border-border"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="even">Evenly distributed</SelectItem>
                      <SelectItem value="division">Within division</SelectItem>
                      <SelectItem value="conference">Within conference</SelectItem>
                      <SelectItem value="set-division">Set # vs division teams</SelectItem>
                      <SelectItem value="set-conference">Set # vs conference teams</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label>Matchups per Scoring Period</Label>
                  <Select value={matchupsPerPeriod} onValueChange={setMatchupsPerPeriod}>
                    <SelectTrigger className="bg-secondary border-border"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {Array.from({ length: numTeams }, (_, i) => i + 1).map((n) => (
                        <SelectItem key={n} value={n.toString()}>{n}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <div className="flex justify-end">
                <Button onClick={regenerateRegular} variant="outline" size="sm">Regenerate Periods</Button>
              </div>
            </CardContent>
          </Card>

          <Card className="bg-card border-border">
            <CardHeader>
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle>Regular Season Scoring Periods</CardTitle>
                  <CardDescription>
                    {regularPeriods.length} periods · {totalRegularDays} total days · Click edit to adjust individual periods
                  </CardDescription>
                </div>
                <Badge variant="secondary" className="text-xs">
                  {regularPeriods.length} periods
                </Badge>
              </div>
            </CardHeader>
            <CardContent>
              <PeriodTable periods={regularPeriods} type="regular" />
              <p className="text-xs text-muted-foreground mt-3">
                Periods shorter than 5 days are highlighted in yellow.
              </p>
            </CardContent>
          </Card>
        </TabsContent>

        {/* ── Playoffs ── */}
        <TabsContent value="playoffs" className="space-y-6">
          <Card className="bg-card border-border">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Trophy className="h-5 w-5 text-primary" />
                Playoff Dates
              </CardTitle>
              <CardDescription>Set the start and end dates for the playoff period</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <Label>Playoff Beginning Scoring Period</Label>
                  <Input type="date" value={playoffStart} onChange={(e) => setPlayoffStart(e.target.value)} className="bg-secondary border-border" />
                </div>
                <div className="space-y-2">
                  <Label>Playoff Ending Scoring Period</Label>
                  <Input type="date" value={playoffEnd} onChange={(e) => setPlayoffEnd(e.target.value)} className="bg-secondary border-border" />
                </div>
              </div>

              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <Label>Playoff Scoring Interval</Label>
                  <Select value={playoffInterval} onValueChange={setPlayoffInterval}>
                    <SelectTrigger className="bg-secondary border-border"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="daily">Daily</SelectItem>
                      <SelectItem value="weekly">Weekly</SelectItem>
                      <SelectItem value="biweekly">Bi-Weekly</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <div className="flex justify-end">
                <Button onClick={regeneratePlayoffs} variant="outline" size="sm">Regenerate Playoff Periods</Button>
              </div>
            </CardContent>
          </Card>

          <Card className="bg-card border-border">
            <CardHeader>
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle>Playoff Scoring Periods</CardTitle>
                  <CardDescription>
                    {playoffPeriods.length} periods · {totalPlayoffDays} total days
                  </CardDescription>
                </div>
                <Badge variant="secondary" className="text-xs">
                  {playoffPeriods.length} periods
                </Badge>
              </div>
            </CardHeader>
            <CardContent>
              <PeriodTable periods={playoffPeriods} type="playoff" />
            </CardContent>
          </Card>

          {/* Playoff Brackets */}
          <Card className="bg-card border-border">
            <CardHeader>
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle className="flex items-center gap-2">
                    <Trophy className="h-5 w-5 text-primary" />
                    Playoff Brackets
                  </CardTitle>
                  <CardDescription>Create and manage playoff brackets (championship, consolation, loser's bracket, etc.)</CardDescription>
                </div>
                <Button size="sm" onClick={() => openBracketDialog()}>
                  <Plus className="h-4 w-4 mr-1" /> Add Bracket
                </Button>
              </div>
            </CardHeader>
            <CardContent>
              {brackets.length === 0 ? (
                <p className="text-sm text-muted-foreground text-center py-6">No brackets configured. Add one to get started.</p>
              ) : (
                <div className="space-y-3">
                  {brackets.map((bracket) => (
                    <div key={bracket.id} className="flex items-center justify-between p-3 rounded-lg bg-secondary/50 border border-border">
                      <div className="flex items-center gap-3">
                        <Trophy className="h-4 w-4 text-primary" />
                        <div>
                          <p className="font-medium text-sm">{bracket.name}</p>
                          <p className="text-xs text-muted-foreground">
                            {bracket.teams} teams · {bracket.rounds} rounds
                          </p>
                        </div>
                      </div>
                      <div className="flex items-center gap-1">
                        <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => openBracketDialog(bracket)}>
                          <Pencil className="h-3.5 w-3.5" />
                        </Button>
                        {bracket.id !== "championship" && (
                          <Button variant="ghost" size="icon" className="h-7 w-7 text-destructive" onClick={() => deleteBracket(bracket.id)}>
                            <Trash2 className="h-3.5 w-3.5" />
                          </Button>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* ── Full Schedule Projection ── */}
        <TabsContent value="projection" className="space-y-6">
          <Card className="bg-card border-border">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <CalendarDays className="h-5 w-5 text-primary" />
                Full Season Schedule Projection
              </CardTitle>
              <CardDescription>
                Review all scoring periods across the entire season to ensure no gaps or overlaps exist
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-3 gap-4 mb-4">
                <div className="p-3 rounded-lg bg-secondary/50 border border-border text-center">
                  <p className="text-2xl font-bold">{regularPeriods.length}</p>
                  <p className="text-xs text-muted-foreground">Regular Season Periods</p>
                </div>
                <div className="p-3 rounded-lg bg-secondary/50 border border-border text-center">
                  <p className="text-2xl font-bold">{playoffPeriods.length}</p>
                  <p className="text-xs text-muted-foreground">Playoff Periods</p>
                </div>
                <div className="p-3 rounded-lg bg-secondary/50 border border-border text-center">
                  <p className="text-2xl font-bold">{totalRegularDays + totalPlayoffDays}</p>
                  <p className="text-xs text-muted-foreground">Total Days</p>
                </div>
              </div>

              {/* Gap / overlap warnings */}
              {(() => {
                const warnings: string[] = [];
                const checkGaps = (periods: ScoringPeriod[], label: string) => {
                  for (let i = 1; i < periods.length; i++) {
                    const prevEnd = new Date(periods[i - 1].endDate);
                    const currStart = new Date(periods[i].startDate);
                    const diff = Math.round((currStart.getTime() - prevEnd.getTime()) / (1000 * 60 * 60 * 24));
                    if (diff > 1) warnings.push(`${label}: ${diff - 1} day gap between Period ${periods[i - 1].id} and ${periods[i].id}`);
                    if (diff < 1) warnings.push(`${label}: Overlap between Period ${periods[i - 1].id} and ${periods[i].id}`);
                  }
                };
                checkGaps(regularPeriods, "Regular Season");
                checkGaps(playoffPeriods, "Playoffs");
                // Check transition
                if (regularPeriods.length > 0 && playoffPeriods.length > 0) {
                  const lastReg = new Date(regularPeriods[regularPeriods.length - 1].endDate);
                  const firstPlay = new Date(playoffPeriods[0].startDate);
                  const diff = Math.round((firstPlay.getTime() - lastReg.getTime()) / (1000 * 60 * 60 * 24));
                  if (diff > 1) warnings.push(`${diff - 1} day gap between Regular Season and Playoffs`);
                  if (diff < 1) warnings.push(`Overlap between Regular Season and Playoffs`);
                }
                if (warnings.length === 0) return null;
                return (
                  <div className="mb-4 p-3 rounded-lg bg-yellow-500/10 border border-yellow-500/30 space-y-1">
                    <p className="text-sm font-medium text-yellow-400">⚠ Schedule Warnings</p>
                    {warnings.map((w, i) => (
                      <p key={i} className="text-xs text-yellow-400/80">• {w}</p>
                    ))}
                  </div>
                );
              })()}

              <div className="max-h-[500px] overflow-y-auto">
                <Table>
                  <TableHeader>
                    <TableRow className="border-border">
                      <TableHead className="text-muted-foreground w-[50px]">#</TableHead>
                      <TableHead className="text-muted-foreground w-[120px]">Phase</TableHead>
                      <TableHead className="text-muted-foreground">Start Date</TableHead>
                      <TableHead className="text-muted-foreground">End Date</TableHead>
                      <TableHead className="text-muted-foreground text-right w-[70px]">Days</TableHead>
                      <TableHead className="text-muted-foreground text-right w-[70px]">Edit</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {allPeriods.map((period, idx) => {
                      const days = getDays(period.startDate, period.endDate);
                      const showSectionHeader = idx === 0 || period.sectionLabel !== allPeriods[idx - 1].sectionLabel;
                      return (
                        <>
                          {showSectionHeader && (
                            <TableRow key={`header-${period.sectionLabel}`} className="border-border bg-secondary/30">
                              <TableCell colSpan={6} className="py-2">
                                <div className="flex items-center gap-2">
                                  {period.type === "regular" ? (
                                    <Calendar className="h-4 w-4 text-primary" />
                                  ) : (
                                    <Trophy className="h-4 w-4 text-primary" />
                                  )}
                                  <span className="font-semibold text-sm">{period.sectionLabel}</span>
                                  <Badge variant="outline" className="text-xs">
                                    {period.type === "regular" ? regularPeriods.length : playoffPeriods.length} periods
                                  </Badge>
                                </div>
                              </TableCell>
                            </TableRow>
                          )}
                          <TableRow key={`${period.type}-${period.id}`} className="border-border">
                            <TableCell className="text-sm tabular-nums text-muted-foreground">{period.globalIndex}</TableCell>
                            <TableCell>
                              <Badge variant={period.type === "regular" ? "secondary" : "default"} className="text-xs">
                                {period.type === "regular" ? `Week ${period.id}` : `Playoff ${period.id}`}
                              </Badge>
                            </TableCell>
                            <TableCell className="text-sm">{formatDate(period.startDate)}</TableCell>
                            <TableCell className="text-sm">{formatDate(period.endDate)}</TableCell>
                            <TableCell className="text-right tabular-nums text-sm">
                              <span className={days < 5 ? "text-yellow-400 font-medium" : "text-muted-foreground"}>
                                {days}d
                              </span>
                            </TableCell>
                            <TableCell className="text-right">
                              <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => openEditPeriod(period)}>
                                <Pencil className="h-3.5 w-3.5" />
                              </Button>
                            </TableCell>
                          </TableRow>
                        </>
                      );
                    })}
                  </TableBody>
                </Table>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      <div className="flex justify-end gap-3">
        <Button variant="outline">Reset to Defaults</Button>
        <Button>Save Schedule</Button>
      </div>

      {/* Edit Period Dialog */}
      <Dialog open={!!editingPeriod} onOpenChange={(open) => !open && setEditingPeriod(null)}>
        <DialogContent className="bg-card border-border">
          <DialogHeader>
            <DialogTitle>
              Edit {editingPeriod?.type === "regular" ? "Regular Season" : "Playoff"} Period {editingPeriod?.id}
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label>Start Date</Label>
              <Input type="date" value={editStart} onChange={(e) => setEditStart(e.target.value)} className="bg-secondary border-border" />
            </div>
            <div className="space-y-2">
              <Label>End Date</Label>
              <Input type="date" value={editEnd} onChange={(e) => setEditEnd(e.target.value)} className="bg-secondary border-border" />
            </div>
            {editStart && editEnd && (
              <p className="text-sm text-muted-foreground">
                Duration: <span className="font-medium text-foreground">{getDays(editStart, editEnd)} days</span>
              </p>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditingPeriod(null)}>Cancel</Button>
            <Button onClick={saveEditPeriod}>Save Changes</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Bracket Dialog */}
      <Dialog open={bracketDialogOpen} onOpenChange={setBracketDialogOpen}>
        <DialogContent className="bg-card border-border">
          <DialogHeader>
            <DialogTitle>{editingBracket ? "Edit Bracket" : "Create Playoff Bracket"}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label>Bracket Name</Label>
              <Input
                value={bracketName}
                onChange={(e) => setBracketName(e.target.value)}
                placeholder="e.g. Consolation Bracket"
                className="bg-secondary border-border"
              />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Number of Teams</Label>
                <Select value={bracketTeams} onValueChange={setBracketTeams}>
                  <SelectTrigger className="bg-secondary border-border"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {[2, 4, 6, 8, 10, 12].map((n) => (
                      <SelectItem key={n} value={n.toString()}>{n} teams</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>Number of Rounds</Label>
                <Select value={bracketRounds} onValueChange={setBracketRounds}>
                  <SelectTrigger className="bg-secondary border-border"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {[1, 2, 3, 4].map((n) => (
                      <SelectItem key={n} value={n.toString()}>{n} round{n > 1 ? "s" : ""}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setBracketDialogOpen(false)}>Cancel</Button>
            <Button onClick={saveBracket}>{editingBracket ? "Save" : "Create"}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default SchedulesTab;
