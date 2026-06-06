// @ts-nocheck
/**
 * Depth Chart — Iter 111 rewrite.
 *
 * Replaces the per-position split tables with a single unified Projections
 * table, surfaces per-year committed-cap / available-cap tiles (driven by the
 * commissioner's iter-111 Year+1 / Year+2 cap inputs), and adds a second
 * "NHL Lineup" tab that renders the roster as drag-and-drop tiles in lines
 * (4 forward lines, 3 defensive pairs, 2 goalies, plus bench) for the
 * current + Year+1 + Year+2 seasons.
 *
 * Editable Projected PF text inputs are persisted per (team, season) to
 * localStorage so the user can revisit and refine. A `Reset` button restores
 * the auto-projected values.
 */
import { useEffect, useMemo, useState } from "react";
import { AppLayout } from "@/components/layout/AppLayout";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Save, RotateCcw, ArrowUpDown, ArrowUp, ArrowDown } from "lucide-react";
import { useActiveLeague } from "@/hooks/use-active-league";
import api from "@/lib/api";
import { toast } from "sonner";
import LeagueContextBanner from "@/lovable/components/dashboard/LeagueContextBanner";
import {
  DndContext, closestCenter, KeyboardSensor, PointerSensor, useSensor, useSensors,
  DragOverlay,
} from "@dnd-kit/core";
import { useDraggable, useDroppable } from "@dnd-kit/core";

const fmt = (n: number) => `$${(n / 1_000_000).toFixed(2)}M`;
const SEASON_LABEL = (yr: number) => `${yr}-${String(yr + 1).slice(-2)}`;

// ── NHL slot layout ────────────────────────────────────────────────
// Slots are computed dynamically based on the league's roster size, but
// default to the canonical NHL lineup (4 lines, 3 pairs, 2 goalies).
type SlotDef = { id: string; label: string; role: "F" | "D" | "G" | "BN"; subLabel?: string };

const buildSlotPlan = (rosterSpots: number): SlotDef[] => {
  const total = Math.max(20, rosterSpots || 23);
  const goalies = 2;
  const forwardLines = total >= 24 ? 4 : 3;
  const defensePairs = total >= 22 ? 3 : 2;
  const startersFD = forwardLines * 3 + defensePairs * 2 + goalies;
  const bench = Math.max(0, total - startersFD);

  const slots: SlotDef[] = [];
  const lineLabels = ["1st Line", "2nd Line", "3rd Line", "4th Line"];
  const pairLabels = ["1st Pair", "2nd Pair", "3rd Pair"];
  for (let i = 0; i < forwardLines; i++) {
    slots.push({ id: `L${i + 1}-LW`, label: "LW", role: "F", subLabel: lineLabels[i] });
    slots.push({ id: `L${i + 1}-C`, label: "C", role: "F", subLabel: lineLabels[i] });
    slots.push({ id: `L${i + 1}-RW`, label: "RW", role: "F", subLabel: lineLabels[i] });
  }
  for (let i = 0; i < defensePairs; i++) {
    slots.push({ id: `D${i + 1}-LD`, label: "LD", role: "D", subLabel: pairLabels[i] });
    slots.push({ id: `D${i + 1}-RD`, label: "RD", role: "D", subLabel: pairLabels[i] });
  }
  for (let i = 0; i < goalies; i++) {
    slots.push({ id: `G${i + 1}`, label: i === 0 ? "Starter" : "Backup", role: "G" });
  }
  for (let i = 0; i < bench; i++) {
    slots.push({ id: `BN-${i + 1}`, label: `Bench ${i + 1}`, role: "BN" });
  }
  return slots;
};

// ── Tile (draggable) ──────────────────────────────────────────────
function PlayerTile({ player, dragId }: any) {
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({
    id: dragId,
    data: { player },
  });
  if (!player) return null;
  return (
    <div
      ref={setNodeRef}
      {...attributes}
      {...listeners}
      data-testid={`lineup-tile-${player.id}`}
      className={`group rounded-lg border border-border bg-secondary/40 px-2 py-1.5 cursor-grab active:cursor-grabbing transition-shadow ${
        isDragging ? "opacity-50" : "hover:border-cyan-400/50 hover:shadow-md"
      }`}
    >
      <div className="flex items-center gap-2">
        <div className="h-7 w-7 rounded bg-primary/15 flex items-center justify-center text-[10px] font-bold text-primary shrink-0">
          {player.team}
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-xs font-semibold truncate">{player.name}</p>
          <p className="text-[10px] text-muted-foreground truncate">
            {player.position} · {fmt(player.contract?.salary || 0)}
          </p>
        </div>
      </div>
    </div>
  );
}

function SlotDrop({ slot, player }: any) {
  const { isOver, setNodeRef } = useDroppable({ id: slot.id });
  const roleColor =
    slot.role === "F" ? "from-cyan-500/10 to-cyan-500/5" :
    slot.role === "D" ? "from-amber-500/10 to-amber-500/5" :
    slot.role === "G" ? "from-emerald-500/10 to-emerald-500/5" :
    "from-zinc-500/10 to-zinc-500/5";

  return (
    <div
      ref={setNodeRef}
      data-testid={`lineup-slot-${slot.id}`}
      className={`relative rounded-lg border ${
        isOver ? "border-primary/70 ring-2 ring-primary/30" : "border-border/50"
      } bg-gradient-to-br ${roleColor} p-2 min-h-[64px] transition-all`}
    >
      <div className="absolute top-1 right-1.5 text-[9px] uppercase tracking-wider font-semibold text-muted-foreground/80">
        {slot.subLabel ? `${slot.subLabel} · ${slot.label}` : slot.label}
      </div>
      <div className="mt-3.5">
        {player ? (
          <PlayerTile player={player} dragId={`assigned-${slot.id}`} />
        ) : (
          <p className="text-[10px] italic text-muted-foreground text-center mt-1">
            Drag a player here
          </p>
        )}
      </div>
    </div>
  );
}

// Bench pool — droppable for "send to bench"
function BenchPool({ players, dragIdPrefix }: any) {
  const { isOver, setNodeRef } = useDroppable({ id: "POOL" });
  return (
    <div
      ref={setNodeRef}
      data-testid="lineup-pool"
      className={`rounded-lg border ${isOver ? "border-primary/70 ring-2 ring-primary/30" : "border-border/50"} bg-card/40 p-3`}
    >
      <p className="text-xs uppercase tracking-wider text-muted-foreground mb-2">Unassigned Pool</p>
      {players.length === 0 ? (
        <p className="text-[11px] italic text-muted-foreground">All players assigned.</p>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-2">
          {players.map((p: any) => (
            <PlayerTile key={p.id} player={p} dragId={`${dragIdPrefix}-${p.id}`} />
          ))}
        </div>
      )}
    </div>
  );
}

const DepthChart = () => {
  const { league, myTeam } = useActiveLeague();
  const [rosterDetail, setRosterDetail] = useState<any>(null);
  const [yearOffset, setYearOffset] = useState<0 | 1 | 2>(0);

  useEffect(() => {
    if (!myTeam?.id) return;
    let cancelled = false;
    api.get(`/roster/${myTeam.id}/detail`)
      .then(({ data }) => { if (!cancelled) setRosterDetail(data); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [myTeam?.id]);

  // ── Player projection state (per team, per year), server-side persisted ──
  const [projections, setProjections] = useState<Record<string, number[]>>({});
  const [projectionsLoaded, setProjectionsLoaded] = useState(false);
  const [savingProj, setSavingProj] = useState(false);

  useEffect(() => {
    if (!myTeam?.id || !rosterDetail) return;
    let cancelled = false;
    api.get(`/teams/${myTeam.id}/depth-projections`)
      .then(({ data }) => {
        if (cancelled) return;
        const stored = data.projections || {};
        // Hydrate missing player rows with auto-baseline so the table is never empty.
        const fresh: Record<string, number[]> = { ...stored };
        (rosterDetail.players || []).forEach((p: any) => {
          if (!fresh[p.id]) {
            const baseline = Math.round(p.fantasy_points || 0);
            fresh[p.id] = [baseline, Math.round(baseline * 0.97), Math.round(baseline * 0.94)];
          }
        });
        setProjections(fresh);
        setProjectionsLoaded(true);
      })
      .catch(() => {
        // Fallback to localStorage if server-side hasn't been populated yet
        const fresh: Record<string, number[]> = {};
        (rosterDetail.players || []).forEach((p: any) => {
          const baseline = Math.round(p.fantasy_points || 0);
          fresh[p.id] = [baseline, Math.round(baseline * 0.97), Math.round(baseline * 0.94)];
        });
        setProjections(fresh);
        setProjectionsLoaded(true);
      });
    return () => { cancelled = true; };
  }, [myTeam?.id, rosterDetail]);

  const saveProjections = async () => {
    if (!myTeam?.id) return;
    setSavingProj(true);
    try {
      await api.put(`/teams/${myTeam.id}/depth-projections`, { projections });
      toast.success("Projected PFs saved");
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Failed to save projections");
    } finally {
      setSavingProj(false);
    }
  };
  const resetProjections = async () => {
    const fresh: Record<string, number[]> = {};
    (rosterDetail?.players || []).forEach((p: any) => {
      const baseline = Math.round(p.fantasy_points || 0);
      fresh[p.id] = [baseline, Math.round(baseline * 0.97), Math.round(baseline * 0.94)];
    });
    setProjections(fresh);
    try {
      if (myTeam?.id) await api.put(`/teams/${myTeam.id}/depth-projections`, { projections: fresh });
    } catch {}
    toast.success("Projections reset to auto-calculated baseline");
  };

  // ── Future-year caps (iter 111) ─────────────────────────────────
  const curYear = new Date().getFullYear();
  const capLimits: { year: number; cap: number; tentative: boolean }[] = [
    {
      year: curYear,
      cap: Number(league?.salary_cap || 82_500_000),
      tentative: false,
    },
    {
      year: curYear + 1,
      cap: Number(league?.salary_cap_year_plus_1 || league?.salary_cap || 82_500_000),
      tentative: !!league?.salary_cap_year_plus_1_tentative,
    },
    {
      year: curYear + 2,
      cap: Number(league?.salary_cap_year_plus_2 || league?.salary_cap || 82_500_000),
      tentative: !!league?.salary_cap_year_plus_2_tentative,
    },
  ];

  // ── Dead-cap schedule (Iter 112) — fed into committed-cap arithmetic ──
  const [deadCapByYear, setDeadCapByYear] = useState<Record<number, number>>({});
  useEffect(() => {
    if (!myTeam?.id) return;
    let cancelled = false;
    api.get(`/teams/${myTeam.id}/dead-cap-schedule`)
      .then(({ data }) => {
        if (cancelled) return;
        const m: Record<number, number> = {};
        (data.schedule || []).forEach((r: any) => { m[r.year] = r.total; });
        setDeadCapByYear(m);
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [myTeam?.id]);

  // ── Compute per-year committed cap (active contract for that year) ──
  const players = rosterDetail?.players || [];
  const yearCommitments = useMemo(() => {
    return [0, 1, 2].map((offset) => {
      let committed = 0;
      let signed = 0;
      let ufaCount = 0;
      let rfaCount = 0;
      players.forEach((p: any) => {
        const c = p.contract || {};
        const yearsRem = c.yearsRemaining || 1;
        if (offset < yearsRem) {
          committed += Number(c.salary || 0);
          signed++;
        } else if (c.end_status === "UFA") ufaCount++;
        else rfaCount++;
      });
      // Add dead cap for the specific calendar year
      const yr = capLimits[offset].year;
      committed += Number(deadCapByYear[yr] || 0);
      return { committed, signed, ufaCount, rfaCount, deadCap: Number(deadCapByYear[yr] || 0) };
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [players, deadCapByYear, capLimits[0]?.year]);

  // ── Projected PF total for selected year ─────────────────────────
  const teamProjPF = useMemo(() => {
    let total = 0;
    players.forEach((p: any) => {
      const arr = projections[p.id] || [];
      total += Number(arr[yearOffset] || 0);
    });
    return Math.round(total);
  }, [players, projections, yearOffset]);

  // ── Sortable Projections table (iter 111) ────────────────────────
  type SortKey = "name" | "position" | "team" | "age" | "salary" | "contract_ends" | "pf_y0" | "pf_y1" | "pf_y2";
  const [sortKey, setSortKey] = useState<SortKey>("pf_y0");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const SortIcon = ({ col }: { col: SortKey }) => {
    if (sortKey !== col) return <ArrowUpDown className="inline h-3 w-3 ml-1 opacity-40" />;
    return sortDir === "asc" ? <ArrowUp className="inline h-3 w-3 ml-1" /> : <ArrowDown className="inline h-3 w-3 ml-1" />;
  };
  const handleSort = (k: SortKey) => {
    if (sortKey === k) setSortDir(sortDir === "asc" ? "desc" : "asc");
    else { setSortKey(k); setSortDir(["name", "position", "team"].includes(k) ? "asc" : "desc"); }
  };
  const sortedPlayers = useMemo(() => {
    const dir = sortDir === "asc" ? 1 : -1;
    const arr = [...players];
    arr.sort((a, b) => {
      const proj = (p: any, idx: number) => Number(projections[p.id]?.[idx] || 0);
      switch (sortKey) {
        case "name": return a.name.localeCompare(b.name) * dir;
        case "position": return a.position.localeCompare(b.position) * dir;
        case "team": return (a.team || "").localeCompare(b.team || "") * dir;
        case "age": return ((a.age || 0) - (b.age || 0)) * dir;
        case "salary": return ((a.contract?.salary || 0) - (b.contract?.salary || 0)) * dir;
        case "contract_ends": return ((a.contract?.end_year || 0) - (b.contract?.end_year || 0)) * dir;
        case "pf_y0": return (proj(a, 0) - proj(b, 0)) * dir;
        case "pf_y1": return (proj(a, 1) - proj(b, 1)) * dir;
        case "pf_y2": return (proj(a, 2) - proj(b, 2)) * dir;
        default: return 0;
      }
    });
    return arr;
  }, [players, sortKey, sortDir, projections]);

  // ── NHL Lineup state (per-year), server-side persisted ────────
  const [lineups, setLineups] = useState<Record<string, Record<string, string>>>({});
  useEffect(() => {
    if (!myTeam?.id) return;
    let cancelled = false;
    api.get(`/teams/${myTeam.id}/depth-lineup`)
      .then(({ data }) => {
        if (cancelled) return;
        const stored = data.lineups || {};
        setLineups({
          y0: stored.y0 || {},
          y1: stored.y1 || {},
          y2: stored.y2 || {},
        });
      })
      .catch(() => setLineups({ y0: {}, y1: {}, y2: {} }));
    return () => { cancelled = true; };
  }, [myTeam?.id]);

  // Debounced persist whenever lineups change locally (skips initial empty)
  useEffect(() => {
    if (!myTeam?.id || Object.keys(lineups).length === 0) return;
    const timer = setTimeout(() => {
      api.put(`/teams/${myTeam.id}/depth-lineup`, { lineups }).catch(() => {});
    }, 500);
    return () => clearTimeout(timer);
  }, [myTeam?.id, lineups]);

  const slotPlan = useMemo(() => buildSlotPlan(Number(league?.roster_spots) || 23), [league?.roster_spots]);
  const yearKey = `y${yearOffset}` as const;
  const assignedMap = lineups[yearKey] || {};

  const playerById: Record<string, any> = useMemo(() => {
    const m: Record<string, any> = {};
    players.forEach((p: any) => { m[p.id] = p; });
    return m;
  }, [players]);

  // For year+1/+2, only signed-through-that-year players are eligible.
  const eligibleForYear = (p: any, offset: number) => {
    const yearsRem = p.contract?.yearsRemaining || 1;
    return offset < yearsRem;
  };
  const eligiblePlayers = useMemo(() => players.filter((p: any) => eligibleForYear(p, yearOffset)), [players, yearOffset]);

  const assignedPlayerIds = new Set(Object.values(assignedMap));
  const poolPlayers = eligiblePlayers.filter((p: any) => !assignedPlayerIds.has(p.id));

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor),
  );

  const handleDragEnd = (event: any) => {
    const overId = event.over?.id;
    if (!overId) return;
    const activeData = event.active?.data?.current;
    const player = activeData?.player;
    if (!player) return;

    setLineups((prev) => {
      const next = { ...prev };
      const cur = { ...(next[yearKey] || {}) };
      // Remove player from any existing slot
      Object.keys(cur).forEach((slotId) => {
        if (cur[slotId] === player.id) delete cur[slotId];
      });
      if (overId === "POOL") {
        // Sent to bench pool: just remove (already done above)
      } else {
        // If another player was in that slot, push them to the pool
        cur[overId as string] = player.id;
      }
      next[yearKey] = cur;
      return next;
    });
  };

  const resetLineup = () => {
    setLineups((prev) => ({ ...prev, [yearKey]: {} }));
    toast.success(`${SEASON_LABEL(capLimits[yearOffset].year)} lineup cleared`);
  };

  const handleProjectionChange = (playerId: string, value: string) => {
    const num = Math.max(0, Math.min(1500, parseInt(value, 10) || 0));
    setProjections((prev) => {
      const cur = prev[playerId] || [0, 0, 0];
      const next = [...cur];
      next[yearOffset] = num;
      return { ...prev, [playerId]: next };
    });
  };

  return (
    <AppLayout>
      <div className="container py-8 space-y-6">
        <LeagueContextBanner
          title="Depth Chart"
          kpiLabel="Projected PF"
          kpiValue={teamProjPF}
          primaryHref="/rosters"
          primaryLabel="Manage Roster"
        />
        <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold">Depth Chart</h1>
            <p className="text-muted-foreground">
              Long-term planning · {SEASON_LABEL(capLimits[yearOffset].year)} view
            </p>
          </div>
          <div className="flex gap-2">
            <Select
              value={String(yearOffset)}
              onValueChange={(v) => setYearOffset(Number(v) as 0 | 1 | 2)}
            >
              <SelectTrigger
                className="w-[260px]"
                data-testid="depth-year-select"
                aria-label="Depth chart season"
              >
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {[0, 1, 2].map((y) => (
                  <SelectItem
                    key={y}
                    value={String(y)}
                    data-testid={`depth-year-option-${y}`}
                  >
                    {SEASON_LABEL(capLimits[y].year)}
                    {capLimits[y].tentative ? "  · tentative" : ""}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        {/* 4-tile cap summary for selected year */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <Card className="bg-card border-border" data-testid="depth-tile-cap">
            <CardContent className="p-4">
              <p className="text-xs text-muted-foreground">Salary Cap</p>
              <p className="text-xl font-bold">{fmt(capLimits[yearOffset].cap)}</p>
              <p className="text-[10px] text-muted-foreground mt-1">
                {SEASON_LABEL(capLimits[yearOffset].year)}
                {capLimits[yearOffset].tentative && (
                  <span className="ml-1 text-amber-400">· tentative</span>
                )}
              </p>
            </CardContent>
          </Card>
          <Card className="bg-card border-border" data-testid="depth-tile-committed">
            <CardContent className="p-4">
              <p className="text-xs text-muted-foreground">Committed Cap</p>
              <p className="text-xl font-bold">{fmt(yearCommitments[yearOffset].committed)}</p>
              <p className="text-[10px] text-muted-foreground mt-1">
                {yearCommitments[yearOffset].signed} signed
                {yearCommitments[yearOffset].deadCap > 0 && (
                  <span className="ml-1 text-amber-400">
                    · {fmt(yearCommitments[yearOffset].deadCap)} dead
                  </span>
                )}
              </p>
            </CardContent>
          </Card>
          <Card className="bg-card border-border" data-testid="depth-tile-space">
            <CardContent className="p-4">
              <p className="text-xs text-muted-foreground">Available Cap Space</p>
              <p
                className="text-xl font-bold"
                style={{
                  color:
                    capLimits[yearOffset].cap - yearCommitments[yearOffset].committed < 0
                      ? "#FF3B30"
                      : "#34C759",
                }}
              >
                {fmt(capLimits[yearOffset].cap - yearCommitments[yearOffset].committed)}
              </p>
              <p className="text-[10px] text-muted-foreground mt-1">
                {yearCommitments[yearOffset].ufaCount} UFA · {yearCommitments[yearOffset].rfaCount} RFA
              </p>
            </CardContent>
          </Card>
          <Card className="bg-card border-border" data-testid="depth-tile-projpf">
            <CardContent className="p-4">
              <p className="text-xs text-muted-foreground">Team Projected PF</p>
              <p className="text-xl font-bold">{teamProjPF}</p>
              <p className="text-[10px] text-muted-foreground mt-1">Editable below ↓</p>
            </CardContent>
          </Card>
        </div>

        <Tabs defaultValue="table" className="space-y-4">
          <TabsList>
            <TabsTrigger value="table" data-testid="depth-view-table">Projections Table</TabsTrigger>
            <TabsTrigger value="lineup" data-testid="depth-view-lineup">NHL Lineup</TabsTrigger>
          </TabsList>

          {/* ── Projections table — single unified column layout ── */}
          <TabsContent value="table">
            <Card className="bg-card border-border">
              <CardHeader className="flex flex-row items-center justify-between">
                <CardTitle>Roster — Single-Column View</CardTitle>
                <div className="flex gap-2">
                  <Button size="sm" variant="outline" onClick={resetProjections} data-testid="depth-proj-reset">
                    <RotateCcw className="h-4 w-4 mr-1" /> Reset PFs
                  </Button>
                  <Button size="sm" onClick={saveProjections} disabled={savingProj} data-testid="depth-proj-save">
                    <Save className="h-4 w-4 mr-1" /> {savingProj ? "Saving…" : "Save PFs"}
                  </Button>
                </div>
              </CardHeader>
              <CardContent>
                <Table>
                  <TableHeader>
                    <TableRow className="border-border">
                      <TableHead className="cursor-pointer select-none" onClick={() => handleSort("name")} data-testid="depth-sort-name">
                        Player <SortIcon col="name" />
                      </TableHead>
                      <TableHead className="text-center cursor-pointer select-none" onClick={() => handleSort("position")} data-testid="depth-sort-pos">
                        Pos <SortIcon col="position" />
                      </TableHead>
                      <TableHead className="text-center cursor-pointer select-none" onClick={() => handleSort("team")}>
                        NHL Team <SortIcon col="team" />
                      </TableHead>
                      <TableHead className="text-center cursor-pointer select-none" onClick={() => handleSort("age")}>
                        Age <SortIcon col="age" />
                      </TableHead>
                      <TableHead className="text-right cursor-pointer select-none" onClick={() => handleSort("salary")} data-testid="depth-sort-salary">
                        Salary <SortIcon col="salary" />
                      </TableHead>
                      <TableHead className="text-center cursor-pointer select-none" onClick={() => handleSort("contract_ends")}>
                        Contract Ends <SortIcon col="contract_ends" />
                      </TableHead>
                      <TableHead className="text-center cursor-pointer select-none" onClick={() => handleSort("pf_y0")}>
                        {SEASON_LABEL(capLimits[0].year)} PF <SortIcon col="pf_y0" />
                      </TableHead>
                      <TableHead className="text-center cursor-pointer select-none" onClick={() => handleSort("pf_y1")}>
                        {SEASON_LABEL(capLimits[1].year)} PF <SortIcon col="pf_y1" />
                      </TableHead>
                      <TableHead className="text-center cursor-pointer select-none" onClick={() => handleSort("pf_y2")}>
                        {SEASON_LABEL(capLimits[2].year)} PF <SortIcon col="pf_y2" />
                      </TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {sortedPlayers.map((p: any) => {
                      const c = p.contract || {};
                      const elig = (offset: number) => eligibleForYear(p, offset);
                      return (
                        <TableRow key={p.id} className="border-border" data-testid={`depth-row-${p.id}`}>
                          <TableCell className="font-medium">{p.name}</TableCell>
                          <TableCell className="text-center">
                            <Badge variant="outline" className="text-[10px]">{p.position}</Badge>
                          </TableCell>
                          <TableCell className="text-center text-muted-foreground">{p.team || "—"}</TableCell>
                          <TableCell className="text-center">{p.age}</TableCell>
                          <TableCell className="text-right font-mono">{fmt(c.salary || 0)}</TableCell>
                          <TableCell className="text-center text-xs">
                            <span className={c.end_status === "UFA" ? "text-amber-400" : "text-cyan-400"}>
                              {c.end_status || "Signed"}
                            </span>
                            <span className="text-muted-foreground">/{c.end_year || curYear}</span>
                          </TableCell>
                          {[0, 1, 2].map((off) => (
                            <TableCell key={off} className="text-center">
                              {elig(off) ? (
                                <Input
                                  type="number"
                                  value={projections[p.id]?.[off] ?? 0}
                                  onChange={(e) => {
                                    const cur = projections[p.id] || [0, 0, 0];
                                    const next = [...cur];
                                    next[off] = Math.max(0, Math.min(1500, parseInt(e.target.value, 10) || 0));
                                    setProjections((prev) => ({ ...prev, [p.id]: next }));
                                  }}
                                  className="w-20 h-7 text-center text-xs mx-auto"
                                  data-testid={`depth-pf-${p.id}-${off}`}
                                />
                              ) : (
                                <Badge variant="outline" className="text-[9px] text-amber-400 border-amber-500/30">
                                  {c.end_status === "UFA" ? "UFA" : "RFA"}
                                </Badge>
                              )}
                            </TableCell>
                          ))}
                        </TableRow>
                      );
                    })}
                    <TableRow className="bg-muted/30 font-bold">
                      <TableCell colSpan={6} className="text-right text-xs">Team Projected PF</TableCell>
                      {[0, 1, 2].map((off) => {
                        const total = players.reduce((s: number, p: any) => {
                          if (!eligibleForYear(p, off)) return s;
                          return s + Number(projections[p.id]?.[off] || 0);
                        }, 0);
                        return (
                          <TableCell key={off} className="text-center font-mono" data-testid={`depth-team-pf-${off}`}>
                            {Math.round(total)}
                          </TableCell>
                        );
                      })}
                    </TableRow>
                    <TableRow className="bg-muted/30 font-bold">
                      <TableCell colSpan={6} className="text-right text-xs">Committed Cap</TableCell>
                      {[0, 1, 2].map((off) => (
                        <TableCell key={off} className="text-center font-mono">
                          {fmt(yearCommitments[off].committed)}
                        </TableCell>
                      ))}
                    </TableRow>
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          </TabsContent>

          {/* ── NHL Lineup — drag-drop tile view ─────────────────── */}
          <TabsContent value="lineup">
            <Card className="bg-card border-border">
              <CardHeader className="flex flex-row items-center justify-between">
                <div>
                  <CardTitle>NHL Lineup — {SEASON_LABEL(capLimits[yearOffset].year)}</CardTitle>
                  <p className="text-xs text-muted-foreground mt-1">
                    Drag eligible players from the pool into starting lines + pairs + goalies.
                    {capLimits[yearOffset].tentative && (
                      <span className="ml-2 text-amber-400">Cap is tentative — values may change.</span>
                    )}
                  </p>
                </div>
                <Button size="sm" variant="outline" onClick={resetLineup} data-testid="depth-lineup-reset">
                  <RotateCcw className="h-4 w-4 mr-1" /> Clear Lineup
                </Button>
              </CardHeader>
              <CardContent>
                <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
                  {/* Iter 133 — Forwards as rows-per-line, Defense as rows-per-pair */}
                  <div className="space-y-4">
                    <div>
                      <p className="text-[11px] uppercase tracking-widest text-cyan-300 font-bold mb-2">Forwards</p>
                      <div className="space-y-2" data-testid="depth-lineup-forwards">
                        {Array.from(
                          new Set(
                            slotPlan
                              .filter((s) => s.role === "F")
                              .map((s) => s.id.split("-")[0]) // e.g. "L1", "L2"…
                          ),
                        ).map((lineId, idx) => (
                          <div
                            key={lineId}
                            className="flex items-center gap-3"
                            data-testid={`depth-lineup-line-${idx + 1}`}
                          >
                            <div className="w-16 shrink-0 text-[11px] uppercase tracking-widest text-muted-foreground font-semibold">
                              Line {idx + 1}
                            </div>
                            <div className="grid grid-cols-3 gap-2 flex-1">
                              {slotPlan
                                .filter((s) => s.role === "F" && s.id.startsWith(`${lineId}-`))
                                .map((slot) => (
                                  <SlotDrop
                                    key={slot.id}
                                    slot={slot}
                                    player={assignedMap[slot.id] ? playerById[assignedMap[slot.id]] : null}
                                  />
                                ))}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                    <div>
                      <p className="text-[11px] uppercase tracking-widest text-amber-300 font-bold mb-2">Defense</p>
                      <div className="space-y-2" data-testid="depth-lineup-defense">
                        {Array.from(
                          new Set(
                            slotPlan
                              .filter((s) => s.role === "D")
                              .map((s) => s.id.split("-")[0]) // e.g. "D1", "D2"…
                          ),
                        ).map((pairId, idx) => (
                          <div
                            key={pairId}
                            className="flex items-center gap-3"
                            data-testid={`depth-lineup-pair-${idx + 1}`}
                          >
                            <div className="w-16 shrink-0 text-[11px] uppercase tracking-widest text-muted-foreground font-semibold">
                              Pair {idx + 1}
                            </div>
                            {/* Same 3-col grid as Forwards so tile width matches.
                                Only 2 of 3 cells render real slots; the 3rd is a spacer. */}
                            <div className="grid grid-cols-3 gap-2 flex-1">
                              {slotPlan
                                .filter((s) => s.role === "D" && s.id.startsWith(`${pairId}-`))
                                .map((slot) => (
                                  <SlotDrop
                                    key={slot.id}
                                    slot={slot}
                                    player={assignedMap[slot.id] ? playerById[assignedMap[slot.id]] : null}
                                  />
                                ))}
                              <div aria-hidden="true" />
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                    <div>
                      <p className="text-[11px] uppercase tracking-widest text-emerald-300 font-bold mb-2">Goalies</p>
                      <div className="space-y-2" data-testid="depth-lineup-goalies">
                        <div className="flex items-center gap-3" data-testid="depth-lineup-goalie-row">
                          <div className="w-16 shrink-0 text-[11px] uppercase tracking-widest text-muted-foreground font-semibold">
                            Goalies
                          </div>
                          <div className="grid grid-cols-3 gap-2 flex-1">
                            {slotPlan.filter((s) => s.role === "G").map((slot) => (
                              <SlotDrop
                                key={slot.id}
                                slot={slot}
                                player={assignedMap[slot.id] ? playerById[assignedMap[slot.id]] : null}
                              />
                            ))}
                            <div aria-hidden="true" />
                          </div>
                        </div>
                      </div>
                    </div>
                    {/* Pool (unassigned players) */}
                    <BenchPool players={poolPlayers} dragIdPrefix="pool" />
                  </div>
                </DndContext>
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </div>
    </AppLayout>
  );
};

export default DepthChart;
