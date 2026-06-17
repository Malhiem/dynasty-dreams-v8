// @ts-nocheck
/**
 * Iter 151 — Truncated Roster Panel (Draft Room) with:
 *   • Position-ordered rows (C → LW → RW → W → D, with goalies pinned to the bottom)
 *   • Dynamic stat columns sourced from the league's scoring_configs
 *   • Three-click sort cycle on every column (desc → asc → reset to default order)
 *   • Trade Block icon beside the Propose-Trade icon on EVERY row:
 *       - viewing your OWN team:  clickable toggle (POST/DELETE /trade-block)
 *       - viewing another team:   read-only display (mirrors that team's block)
 *   • Team switcher (top-right) and stat-filter dropdown
 *   • Player names link to /players/{id}
 */
import { useEffect, useMemo, useState, useCallback } from "react";
import { Link } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  Tooltip, TooltipContent, TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  Users, Megaphone, Repeat, ArrowUp, ArrowDown,
} from "lucide-react";
import { cn } from "@/lib/utils";
import api from "@/lib/api";
import { toast } from "sonner";

const positionColors = {
  C:  "bg-blue-500/20 text-blue-300 border-blue-500/30",
  LW: "bg-emerald-500/20 text-emerald-300 border-emerald-500/30",
  RW: "bg-amber-500/20 text-amber-300 border-amber-500/30",
  W:  "bg-emerald-500/20 text-emerald-300 border-emerald-500/30",
  D:  "bg-violet-500/20 text-violet-300 border-violet-500/30",
  G:  "bg-rose-500/20 text-rose-300 border-rose-500/30",
};
const POSITION_ORDER = ["C", "LW", "RW", "W", "D", "G"];
function posRank(p) {
  const i = POSITION_ORDER.indexOf(p);
  return i === -1 ? 99 : i;
}

const STAT_FILTERS = [
  { value: "season", label: "Season (overall)" },
  { value: "regular", label: "Regular Season" },
  { value: "playoffs", label: "Playoffs" },
  { value: "l30", label: "Last 30 days" },
  { value: "l7", label: "Last 7 days" },
];

// Column header label for each known scoring stat (kebab → short)
const STAT_LABELS = {
  goals: "G", assists: "A", points: "PTS",
  plus_minus: "+/-", penalty_minutes: "PIM",
  power_play_goals: "PPG", power_play_points: "PPP",
  short_handed_goals: "SHG", short_handed_points: "SHP",
  game_winning_goals: "GWG", shots: "SOG",
  wins: "W", losses: "L", overtime_losses: "OTL",
  saves: "SV", goals_against: "GA", shots_against: "SA",
  shutouts: "SO", save_pct: "SV%", goals_against_avg: "GAA",
};

function fmt(n) {
  if (n == null || Number.isNaN(Number(n))) return "—";
  const v = Number(n);
  if (Math.abs(v) < 1 && v !== 0) return v.toFixed(3); // SV%
  return Number.isInteger(v) ? v.toLocaleString() : v.toFixed(2);
}
function fmtFloat(n, digits = 2) {
  if (n == null || Number.isNaN(Number(n))) return "—";
  return Number(n).toFixed(digits);
}
function fmtMoney(n) {
  if (n == null) return "—";
  const v = Number(n);
  if (!v) return "$0";
  if (v >= 1_000_000) return `$${(v / 1_000_000).toFixed(2)}M`;
  if (v >= 1_000) return `$${(v / 1_000).toFixed(0)}K`;
  return `$${v}`;
}

export default function TruncatedRosterPanel({
  leagueId,
  myTeamId,
  teams = [],
  tradeBlockItems = [],
  onPickPlayerForTrade,
  onToggleTradeBlock, // (player) => Promise — toggles for the LOGGED-IN user's team
  capEnabled = false,
  reloadTrigger = 0, // Iter 170h — bump to force a roster refetch (e.g. after a draft pick)
}) {
  const [selectedTeamId, setSelectedTeamId] = useState(myTeamId || teams?.[0]?.id || null);
  const [statFilter, setStatFilter] = useState("season");
  const [data, setData] = useState({ players: [], scoring: { skater: [], goalie: [] } });
  const [loading, setLoading] = useState(false);
  const [sort, setSort] = useState({ col: null, dir: null }); // dir: 'desc' | 'asc' | null

  useEffect(() => {
    if (myTeamId && !selectedTeamId) setSelectedTeamId(myTeamId);
  }, [myTeamId, selectedTeamId]);

  const isMyTeam = selectedTeamId === myTeamId;
  const selectedTeam = useMemo(
    () => (teams || []).find((t) => t.id === selectedTeamId) || null,
    [teams, selectedTeamId],
  );

  useEffect(() => {
    if (!selectedTeamId) return;
    let cancelled = false;
    setLoading(true);
    (async () => {
      try {
        const { data: res } = await api.get(
          `/teams/${selectedTeamId}/roster-truncated`,
          { params: { stat_filter: statFilter } },
        );
        if (!cancelled) setData(res || { players: [], scoring: { skater: [], goalie: [] } });
      } catch {
        if (!cancelled) setData({ players: [], scoring: { skater: [], goalie: [] } });
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [selectedTeamId, statFilter, reloadTrigger]);

  // Reset sort whenever the team or filter changes so the new bucket starts clean.
  useEffect(() => { setSort({ col: null, dir: null }); }, [selectedTeamId, statFilter]);

  // Which categories the league actually scores — fed by backend.
  const skaterCats = data?.scoring?.skater || [];
  const goalieCats = data?.scoring?.goalie || [];

  // For the bucket Regular Season / Playoffs we render the configured scoring
  // categories. For Season / L30 / L7 keep the lean view (just FP + FP/G).
  const showCategoryCols = statFilter === "regular" || statFilter === "playoffs";

  // Compose the row order: position order + tied by fantasy_points desc.
  // Goalies *always* go at the bottom regardless of sort (visually separated).
  const sortedSkaters = useMemo(() => {
    const skaters = (data?.players || []).filter((p) => p.position !== "G");
    if (sort.dir && sort.col) {
      const dir = sort.dir === "desc" ? -1 : 1;
      return [...skaters].sort((a, b) => {
        const av = sort.col === "fp" ? (a.fantasy_points || 0)
          : sort.col === "fppg" ? (a.fp_per_game || 0)
          : (a.stats?.[sort.col] || 0);
        const bv = sort.col === "fp" ? (b.fantasy_points || 0)
          : sort.col === "fppg" ? (b.fp_per_game || 0)
          : (b.stats?.[sort.col] || 0);
        return (av - bv) * dir;
      });
    }
    // Default: position-order then fp desc
    return [...skaters].sort((a, b) => {
      const r = posRank(a.position) - posRank(b.position);
      return r !== 0 ? r : (b.fantasy_points || 0) - (a.fantasy_points || 0);
    });
  }, [data, sort]);

  const sortedGoalies = useMemo(() => {
    const g = (data?.players || []).filter((p) => p.position === "G");
    if (sort.dir && sort.col) {
      const dir = sort.dir === "desc" ? -1 : 1;
      return [...g].sort((a, b) => {
        const av = sort.col === "fp" ? (a.fantasy_points || 0)
          : sort.col === "fppg" ? (a.fp_per_game || 0)
          : (a.stats?.[sort.col] || 0);
        const bv = sort.col === "fp" ? (b.fantasy_points || 0)
          : sort.col === "fppg" ? (b.fp_per_game || 0)
          : (b.stats?.[sort.col] || 0);
        return (av - bv) * dir;
      });
    }
    return [...g].sort((a, b) => (b.fantasy_points || 0) - (a.fantasy_points || 0));
  }, [data, sort]);

  // Per-team trade-block player_id sets (used both for self-toggle state and
  // for read-only display on other teams' rows). Drives the icon's on-state.
  const selectedTeamBlockSet = useMemo(
    () => new Set(
      (tradeBlockItems || [])
        .filter((x) => x.item_type === "player" && x.team_id === selectedTeamId && x.player_id)
        .map((x) => String(x.player_id))
    ),
    [tradeBlockItems, selectedTeamId],
  );

  // Three-click sort cycle: desc → asc → reset (none)
  const cycleSort = useCallback((col) => {
    setSort((s) => {
      if (s.col !== col) return { col, dir: "desc" };
      if (s.dir === "desc") return { col, dir: "asc" };
      return { col: null, dir: null };
    });
  }, []);

  const SortHead = ({ col, label, align = "right" }) => {
    const active = sort.col === col;
    const Icon = active && sort.dir === "asc" ? ArrowUp : ArrowDown;
    return (
      <button
        type="button"
        onClick={() => cycleSort(col)}
        data-testid={`draft-room-roster-sort-${col}`}
        className={cn(
          "inline-flex items-center gap-0.5 text-[10px] uppercase tracking-wider hover:text-foreground transition-colors",
          align === "right" && "justify-end w-full",
          active ? "text-primary" : "text-muted-foreground",
        )}
      >
        {label}
        {active && <Icon className="h-2.5 w-2.5" />}
      </button>
    );
  };

  // ─── render helpers ──────────────────────────────────────────────
  const baseSkaterCols = showCategoryCols ? skaterCats : [];
  const baseGoalieCols = showCategoryCols ? goalieCats : [];

  // Grid template:  [pos][player][...stats][fp][fp/g][cap?][action]
  const skaterGridTemplate = useMemo(() => {
    const stats = baseSkaterCols.map(() => "auto").join(" ");
    return `auto 1fr ${stats}${stats ? " " : ""}auto auto${capEnabled ? " auto" : ""} auto`;
  }, [baseSkaterCols, capEnabled]);
  const goalieGridTemplate = useMemo(() => {
    const stats = baseGoalieCols.map(() => "auto").join(" ");
    return `auto 1fr ${stats}${stats ? " " : ""}auto auto${capEnabled ? " auto" : ""} auto`;
  }, [baseGoalieCols, capEnabled]);

  const renderRow = (p, scoringCats) => {
    const onBlock = selectedTeamBlockSet.has(String(p.id));
    const canToggle = isMyTeam;
    return (
      <div
        key={p.id}
        className={cn(
          "grid gap-1 px-1.5 py-1.5 rounded items-center text-xs hover:bg-secondary/30 transition-colors",
          onBlock && "bg-amber-500/5",
        )}
        style={{ gridTemplateColumns: p.position === "G" ? goalieGridTemplate : skaterGridTemplate }}
        data-testid={`draft-room-roster-row-${p.id}`}
      >
        <Badge className={cn("text-[9px] px-1 py-0 h-3.5 border", positionColors[p.position])}>
          {p.position}
        </Badge>
        <Link
          to={`/players/${p.id}`}
          className="text-xs font-medium text-foreground truncate hover:text-primary"
          data-testid={`draft-room-roster-player-link-${p.id}`}
        >
          {p.name}
        </Link>
        {scoringCats.map((k) => (
          <span key={k} className="text-[11px] text-foreground tabular-nums text-right min-w-[28px]">
            {fmt(p.stats?.[k])}
          </span>
        ))}
        <span className="text-[11px] text-foreground tabular-nums text-right font-semibold min-w-[36px]">
          {fmt(p.fantasy_points)}
        </span>
        <span className="text-[11px] text-muted-foreground tabular-nums text-right min-w-[36px]">
          {fmtFloat(p.fp_per_game)}
        </span>
        {capEnabled && (
          <span className="text-[11px] text-muted-foreground tabular-nums text-right min-w-[44px]">
            {fmtMoney(p.cap_hit)}
          </span>
        )}
        <div className="flex items-center gap-0.5 justify-end">
          {/* Trade-block icon — togglable on my team, read-only on others */}
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                disabled={!canToggle}
                className={cn(
                  "h-5 w-5",
                  onBlock ? "text-amber-300 hover:bg-amber-500/15" : "text-muted-foreground/40 hover:text-amber-300",
                  !canToggle && "opacity-90 hover:bg-transparent cursor-default",
                )}
                data-testid={`draft-room-roster-block-${p.id}`}
                aria-pressed={onBlock}
                onClick={() => canToggle && onToggleTradeBlock?.(p)}
              >
                <Megaphone className={cn("h-2.5 w-2.5", onBlock && "fill-current")} />
              </Button>
            </TooltipTrigger>
            <TooltipContent>
              {canToggle
                ? (onBlock ? "Remove from your trade block" : "Add to your trade block")
                : (onBlock ? `On ${selectedTeam?.name || "team"}'s trade block` : "Not on team's trade block")}
            </TooltipContent>
          </Tooltip>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className="h-5 w-5 text-emerald-300 hover:text-emerald-200 hover:bg-emerald-500/15"
                data-testid={`draft-room-roster-trade-${p.id}`}
                onClick={() => onPickPlayerForTrade?.(selectedTeam, p)}
              >
                <Repeat className="h-2.5 w-2.5" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>
              {isMyTeam ? "Offer this player in a trade" : `Propose trade for ${p.name}`}
            </TooltipContent>
          </Tooltip>
        </div>
      </div>
    );
  };

  const renderHeader = (scoringCats, isGoalieSection = false) => (
    <div
      className="grid gap-1 px-1.5 py-1 border-b border-border"
      style={{ gridTemplateColumns: isGoalieSection ? goalieGridTemplate : skaterGridTemplate }}
    >
      <span className="text-[10px] uppercase tracking-wider text-muted-foreground">Pos</span>
      <span className="text-[10px] uppercase tracking-wider text-muted-foreground">Player</span>
      {scoringCats.map((k) => (
        <SortHead key={k} col={k} label={STAT_LABELS[k] || k.slice(0, 3).toUpperCase()} />
      ))}
      <SortHead col="fp" label="FP" />
      <SortHead col="fppg" label="FP/G" />
      {capEnabled && (
        <span className="text-[10px] uppercase tracking-wider text-muted-foreground text-right">Cap</span>
      )}
      <span className="text-[10px] uppercase tracking-wider text-muted-foreground text-right">·</span>
    </div>
  );

  return (
    <Card className="border-border" data-testid="draft-room-roster-panel">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <CardTitle className="text-sm flex items-center gap-2">
            <Users className="h-4 w-4 text-accent" />
            <span data-testid="draft-room-roster-team-name">
              {isMyTeam ? "My Roster" : (selectedTeam?.name || "Team")}
            </span>
          </CardTitle>
          <Select value={selectedTeamId || ""} onValueChange={setSelectedTeamId}>
            <SelectTrigger
              className="h-7 text-xs bg-secondary/50 w-[150px]"
              data-testid="draft-room-roster-team-switcher"
            >
              <SelectValue placeholder="Switch team" />
            </SelectTrigger>
            <SelectContent className="bg-popover border-border z-50 max-h-[280px]">
              {(teams || []).map((t) => (
                <SelectItem key={t.id} value={t.id} className="text-xs">
                  {t.id === myTeamId ? `${t.name} (you)` : t.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="flex items-center justify-between mt-1.5 gap-2 flex-wrap">
          <Select value={statFilter} onValueChange={setStatFilter}>
            <SelectTrigger
              className="h-7 text-[11px] bg-secondary/50 w-[160px]"
              data-testid="draft-room-roster-stat-filter"
            >
              <SelectValue />
            </SelectTrigger>
            <SelectContent className="bg-popover border-border z-50">
              {STAT_FILTERS.map((o) => (
                <SelectItem key={o.value} value={o.value} className="text-[11px]">
                  {o.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <span className="text-[10px] text-muted-foreground" data-testid="draft-room-roster-count">
            {(data?.players || []).length} players
          </span>
        </div>
      </CardHeader>
      <CardContent className="p-2">
        {loading ? (
          <div className="text-center py-6 text-xs text-muted-foreground">Loading…</div>
        ) : (data?.players || []).length === 0 ? (
          <div className="text-center py-6 text-xs text-muted-foreground" data-testid="draft-room-roster-empty">
            No roster data
          </div>
        ) : (
          <ScrollArea className="h-[300px] sm:h-[440px]">
            {/* Skaters */}
            {renderHeader(baseSkaterCols, false)}
            <div className="space-y-0.5" data-testid="draft-room-roster-skaters">
              {sortedSkaters.map((p) => renderRow(p, baseSkaterCols))}
            </div>
            {/* Goalies (always pinned to the bottom in a separated block) */}
            {sortedGoalies.length > 0 && (
              <>
                <div className="mt-2 pt-1 px-1.5 text-[9px] uppercase tracking-wider text-muted-foreground border-t border-border"
                     data-testid="draft-room-roster-goalies-header">
                  Goalies
                </div>
                {renderHeader(baseGoalieCols, true)}
                <div className="space-y-0.5" data-testid="draft-room-roster-goalies">
                  {sortedGoalies.map((p) => renderRow(p, baseGoalieCols))}
                </div>
              </>
            )}
          </ScrollArea>
        )}
      </CardContent>
    </Card>
  );
}
