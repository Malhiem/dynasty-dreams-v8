// @ts-nocheck
// Iter 232N.34 — Refactored: TradeHistoryPopover, ScheduledDraftsPanel, and
// DraftOrderResultsTab / DraftOrderStatus were extracted to
// /components/draft/*. This file now owns just the page shell + pick grid.
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
import { Tooltip, TooltipContent, TooltipTrigger, TooltipProvider } from "@/components/ui/tooltip";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { ArrowRightLeft, Info, ShoppingCart, Megaphone, Repeat } from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { useTradeBuilder } from "@/lovable/state/TradeBuilderContext";
import TradeHistoryPopover from "@/components/draft/TradeHistoryPopover";
import ScheduledDraftsPanel from "@/components/draft/ScheduledDraftsPanel";
import { DraftOrderStatus, DraftOrderResultsTab } from "@/components/draft/DraftOrderResults";

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

const totalRoundsDefault = 5;
const maxTradeYears = 3; // League allows picks to be dealt up to 3 years out

// Iter 232N.39 — Hockey season label: 2026 → "2026/27 Draft Year".
function seasonLabel(year: string | number): string {
  const y = Number(year);
  const next = String((y + 1) % 100).padStart(2, "0");
  return `${y}/${next} Draft Year`;
}

interface PickOwnership {
  originalTeam: string;
  currentOwner: string;
  tradeHistory: any[];
}

// Mock data: pick ownership by year (kept as fallback when the league has
// no live pick data yet). Iter 191 removed all mock trade injections — every
// pick returns to its original owner with empty tradeHistory. Live trades
// will repopulate as draft-day picks are traded via the iter191 trade flow.
const generatePickData = (): Record<string, Record<string, Record<number, PickOwnership>>> => {
  const data: Record<string, Record<string, Record<number, PickOwnership>>> = {};
  const years = ["2025", "2026", "2027"];
  years.forEach((year) => {
    data[year] = {};
    leagueTeams.forEach((team) => {
      data[year][team.abbr] = {};
      for (let round = 1; round <= totalRoundsDefault; round++) {
        data[year][team.abbr][round] = {
          originalTeam: team.abbr,
          currentOwner: team.abbr,
          tradeHistory: [],
        };
      }
    });
  });
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

export default function DraftBoardPage() {
  const currentYear = new Date().getFullYear();
  const availableYears = Array.from({ length: maxTradeYears }, (_, i) => String(currentYear + i));
  const [selectedYear, setSelectedYear] = useState(availableYears[0]);
  const { league, leagueTeams: liveLeagueTeams } = useActiveLeague();
  const { user } = useAuth();
  const [livePicks, setLivePicks] = useState<any[]>([]);
  // Iter 137 — league's canonical draft order (lottery applied OR reverse standings fallback)
  const [draftOrder, setDraftOrder] = useState<any | null>(null);
  // Iter 232N.39 — Multi-draft support. `scheduledDrafts` is fed by
  // the ScheduledDraftsPanel; `selectedDraftId` scopes the pick-
  // ownership grid + count summary to a single scheduled draft.
  const [scheduledDrafts, setScheduledDrafts] = useState<any[]>([]);
  const [selectedDraftId, setSelectedDraftId] = useState<string | null>(null);

  // Auto-select the first draft (active → nearest scheduled → completed)
  // whenever the list arrives or the year filter changes.
  const handleDraftsLoaded = (list: any[]) => {
    setScheduledDrafts(list);
    if (!list.length) {
      setSelectedDraftId(null);
      return;
    }
    const still = list.find(
      (d) => selectedDraftId && (d.id || d._id) === selectedDraftId,
    );
    if (!still) {
      const first = list[0];
      setSelectedDraftId(first.id || first._id || null);
    }
  };

  // Selected draft object (for its `total_rounds`, `team_abbrs`, etc.)
  const selectedDraft = useMemo(
    () => scheduledDrafts.find((d) => (d.id || d._id) === selectedDraftId) || null,
    [scheduledDrafts, selectedDraftId],
  );
  const totalRounds = Number(selectedDraft?.total_rounds) || totalRoundsDefault;

  useEffect(() => {
    if (!league?.id) return;
    let cancelled = false;
    // Iter 232N.39 — Filter picks by the SPECIFIC selected draft rather
    // than year-aggregating everything. When no draft is selected yet
    // we fall back to the year filter so the summary is at least
    // populated with something.
    const picksUrl = selectedDraftId
      ? `/drafts/${league.id}/picks?draft_id=${selectedDraftId}`
      : `/drafts/${league.id}/picks?year=${selectedYear}`;
    api.get(picksUrl).then(({ data }) => {
      if (!cancelled) setLivePicks(data?.picks || []);
    }).catch(() => setLivePicks([]));
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
  }, [league?.id, selectedYear, selectedDraftId]);

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

  // Iter 232N.39 — Key by team.id (not abbr) so that leagues with
  // duplicate placeholder abbrs (e.g. "OS1"/"OS2" for multiple open
  // slots) don't collapse rows onto one another and mis-count picks.
  // Falls back to abbr when id is missing (mock data path).
  const keyOf = (t: any) => (t?.id ? `id:${t.id}` : `abbr:${t.abbr}`);
  const abbrToKey = useMemo(() => {
    const m: Record<string, string> = {};
    teams.forEach((t) => { m[t.abbr] = keyOf(t); });
    return m;
  }, [teams]);
  const teamIdToKey = useMemo(() => {
    const m: Record<string, string> = {};
    teams.forEach((t) => { if ((t as any).id) m[(t as any).id] = keyOf(t); });
    return m;
  }, [teams]);

  // Map live pick rows -> {originalKey: {round: {currentOwner: abbr, tradeHistory:[]}}}
  const teamIdToAbbr = useMemo(() => {
    const m: Record<string, string> = {};
    teams.forEach(t => { if ((t as any).id) m[(t as any).id] = t.abbr; });
    return m;
  }, [teams]);
  const liveYearData = useMemo(() => {
    if (!livePicks?.length) return null;
    const data: Record<string, Record<number, any>> = {};
    livePicks.forEach(p => {
      const origKey = teamIdToKey[p.original_team_id];
      if (!origKey) return;
      if (!data[origKey]) data[origKey] = {};
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
      data[origKey][p.round] = {
        // originalTeam stored as key so we can still detect trades
        originalTeamKey: origKey,
        originalTeam: teamIdToAbbr[p.original_team_id] || "",
        currentOwnerKey: teamIdToKey[p.current_team_id] || origKey,
        currentOwner: teamIdToAbbr[p.current_team_id] || teamIdToAbbr[p.original_team_id] || "",
        isTraded: p.current_team_id !== p.original_team_id,
        tradeHistory: history,
        pickId: p._id,
        pendingProtections: p.pending_protections || [],
      };
    });
    return data;
  }, [livePicks, teamIdToKey, teamIdToAbbr]);

  // Legacy mock path expects abbr keys — normalise to team-key form so
  // both branches feed the same rendering logic.
  const yearData = useMemo(() => {
    if (liveYearData) return liveYearData;
    const raw = allPickData[selectedYear] || {};
    const out: Record<string, Record<number, any>> = {};
    Object.entries(raw).forEach(([abbr, byRound]) => {
      const k = abbrToKey[abbr] || `abbr:${abbr}`;
      out[k] = {};
      Object.entries(byRound as any).forEach(([r, pick]) => {
        out[k][Number(r)] = {
          ...(pick as any),
          originalTeamKey: k,
          currentOwnerKey: k,
        };
      });
    });
    return out;
  }, [liveYearData, selectedYear, abbrToKey]);

  // Count how many picks each team owns in the SELECTED draft.
  // Keys are team ids (via keyOf) so identical placeholder abbrs
  // don't over-count. Total row count for a team = number of rounds
  // in this specific draft × 1 pick per team per round (before
  // trades). After trades, the count for the acquiring team goes up,
  // and the losing team's count goes down.
  const pickCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    teams.forEach((t) => (counts[keyOf(t)] = 0));
    teams.forEach((team) => {
      const bucket = yearData[keyOf(team)] || {};
      for (let round = 1; round <= totalRounds; round++) {
        const pick = bucket[round];
        if (pick) {
          const ownerKey = pick.currentOwnerKey || keyOf(team);
          counts[ownerKey] = (counts[ownerKey] || 0) + 1;
        }
      }
    });
    return counts;
  }, [yearData, teams, totalRounds]);

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

  const rounds = Array.from({ length: totalRoundsDefault }, (_, i) => i + 1); // legacy helper — not used in the live grid

  const handleAddPickToTrade = (pickInfo: any, teamAbbr: string, round: number) => {
    if (!league?.id) {
      toast.error("League context missing");
      return;
    }
    if (!myTeam) {
      toast.error("Join a team in this league to propose trades");
      return;
    }
    tradeBuilder.openBuilder({ leagueId: league.id, myTeam });
    const ownerAbbr = pickInfo?.currentOwner || teamAbbr;
    const ownerTeam = (liveLeagueTeams || []).find(
      (t: any) => (t.logo_abbr || t.name.slice(0, 3).toUpperCase()) === ownerAbbr,
    );
    // Iter 232N.39 — Include draft_id + draft_name so a manager can mix
    // picks from Summer Entry + Winter Draft in the same trade proposal.
    const draftLabel = selectedDraft?.name || `${selectedYear}`;
    const pickPayload: any = {
      id: pickInfo?.pickId || `${selectedDraftId || selectedYear}-${ownerAbbr}-R${round}`,
      year: Number(selectedYear),
      round,
      draftId: selectedDraftId || undefined,
      draftName: selectedDraft?.name || undefined,
      ownerTeamId: ownerTeam?.id,
      ownerTeamName: ownerTeam?.name || ownerAbbr,
      originalTeamId: (liveLeagueTeams || []).find(
        (t: any) => (t.logo_abbr || t.name.slice(0, 3).toUpperCase()) === teamAbbr,
      )?.id,
      originalTeamName: teamAbbr,
      label: `${draftLabel} · Round ${round} (${teamAbbr})`,
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
            primaryHref="/draft-room"
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
                {tradeMode ? "Trade Mode: On" : "Trade Mode: Off"}
              </Button>
              <Select value={selectedYear} onValueChange={setSelectedYear}>
                <SelectTrigger className="w-[200px] bg-card border-border" data-testid="draft-board-year-select">
                  <SelectValue placeholder="Select Year" />
                </SelectTrigger>
                <SelectContent>
                  {availableYears.map((year) => (
                    <SelectItem key={year} value={year}>
                      {seasonLabel(year)}
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

          {/* Iter 232N.39 — Scheduled Drafts tiles. Clickable — the
              summary + ownership grid below scope to the selected draft.
              Selection persists across the parent's year-filter change
              (auto-selects first draft when the previous one falls out). */}
          <ScheduledDraftsPanel
            leagueId={league?.id}
            year={selectedYear}
            selectedDraftId={selectedDraftId}
            onSelectDraft={setSelectedDraftId}
            onDraftsLoaded={handleDraftsLoaded}
          />

          {/* Summary badges — scoped to the SELECTED draft (Iter 232N.39). */}
          <div className="flex flex-wrap gap-2" data-testid="draft-board-pick-summary">
            {teams.map((team) => {
              const key = keyOf(team);
              const count = pickCounts[key] || 0;
              const diff = count - totalRounds;
              return (
                <Tooltip key={key}>
                  <TooltipTrigger asChild>
                    <div
                      className={cn(
                        "px-3 py-1.5 rounded-md text-xs font-medium border cursor-default transition-colors",
                        diff > 0
                          ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-400"
                          : diff < 0
                          ? "bg-amber-500/10 border-amber-500/30 text-amber-400"
                          : "bg-secondary border-border text-muted-foreground",
                      )}
                      data-testid={`draft-board-summary-${team.abbr}`}
                    >
                      {team.abbr}: {count} pick{count !== 1 ? "s" : ""}
                    </div>
                  </TooltipTrigger>
                  <TooltipContent>
                    <p>{team.name} — {count} of {totalRounds} picks in this draft</p>
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
              <CardTitle className="text-base flex items-center gap-2" data-testid="draft-board-grid-title">
                {selectedDraft?.name || `${selectedYear} Draft`} — Pick Ownership
                <Tooltip>
                  <TooltipTrigger>
                    <Info className="h-4 w-4 text-muted-foreground" />
                  </TooltipTrigger>
                  <TooltipContent className="max-w-xs">
                    <p>Teams are listed alphabetically (default draft order). Traded picks show the current owner — click for full trade chain. Trade Mode lets you add picks from any draft to the same trade proposal.</p>
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
                        {Array.from({ length: totalRounds }, (_, i) => i + 1).map((round) => (
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
                          key={keyOf(team) + "-row"}
                          className={cn(
                            "border-border/50 transition-colors",
                            teamIdx % 2 === 0 ? "bg-card/30" : "bg-card/10",
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
                                  {pickCounts[keyOf(team)] || 0} pick{(pickCounts[keyOf(team)] || 0) !== 1 ? "s" : ""}
                                </p>
                              </div>
                            </div>
                          </TableCell>
                          {Array.from({ length: totalRounds }, (_, i) => i + 1).map((round) => {
                            const pick = yearData[keyOf(team)]?.[round];
                            const isTraded = pick && pick.currentOwnerKey && pick.currentOwnerKey !== keyOf(team);
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
                                    <TradeHistoryPopover pick={pick} leagueTeams={leagueTeams} />
                                    <span className="text-[10px] text-muted-foreground/60 flex items-center gap-0.5">
                                      <ArrowRightLeft className="h-2.5 w-2.5" />
                                      traded
                                    </span>
                                    {isOnTradeBlock && (
                                      <Badge variant="outline" className="text-[9px] px-1 h-3.5 bg-amber-500/10 border-amber-500/30 text-amber-400 gap-0.5 mt-0.5"
                                             data-testid={`draft-board-block-icon-traded-${team.abbr}-r${round}`}>
                                        <Megaphone className="h-2 w-2" />
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
                                      <Badge variant="outline" className="text-[9px] px-1 h-3.5 bg-amber-500/10 border-amber-500/30 text-amber-400 gap-0.5 mt-0.5"
                                             data-testid={`draft-board-block-icon-${team.abbr}-r${round}`}>
                                        <Megaphone className="h-2 w-2" />
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
