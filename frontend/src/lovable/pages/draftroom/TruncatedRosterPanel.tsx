// @ts-nocheck
/**
 * Iter 150 — Truncated Roster Panel for Draft Room
 *
 * Shows a compact view of a team's roster (default: viewer's team) with:
 *   - Team switcher dropdown (top-right) to peek at any other team
 *   - Per-row Player · Pos · Total FP · FP/Game · Cap Hit (when cap_enabled)
 *   - Megaphone overlay icon (read-only) if the player is on the team's trade block
 *   - Repeat icon to add the player into the Trade Builder (only enabled when
 *     viewing another team's roster — clicking proposes a trade for that player)
 *   - Stat filter dropdown: Season · Regular Season · Playoffs · Last 30 · Last 7
 *   - Player names link to /players/{id} for the existing PlayerCard route
 *   - Truncated to 10 rows for desktop, 5 rows for mobile (responsive),
 *     with ScrollArea for overflow.
 */
import { useEffect, useMemo, useState, useCallback } from "react";
import { Link } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Users, Megaphone, Repeat, ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";
import api from "@/lib/api";

const positionColors = {
  C: "bg-blue-500/20 text-blue-300 border-blue-500/30",
  LW: "bg-emerald-500/20 text-emerald-300 border-emerald-500/30",
  RW: "bg-amber-500/20 text-amber-300 border-amber-500/30",
  D: "bg-violet-500/20 text-violet-300 border-violet-500/30",
  G: "bg-rose-500/20 text-rose-300 border-rose-500/30",
};

const STAT_FILTERS = [
  { value: "season", label: "Season (overall)" },
  { value: "regular", label: "Regular Season" },
  { value: "playoffs", label: "Playoffs" },
  { value: "l30", label: "Last 30 days" },
  { value: "l7", label: "Last 7 days" },
];

function fmt(n) {
  if (n == null || Number.isNaN(Number(n))) return "—";
  return Number(n).toLocaleString();
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
  capEnabled = false,
}) {
  const [selectedTeamId, setSelectedTeamId] = useState(myTeamId || teams?.[0]?.id || null);
  const [statFilter, setStatFilter] = useState("season");
  const [players, setPlayers] = useState([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (myTeamId && !selectedTeamId) setSelectedTeamId(myTeamId);
  }, [myTeamId, selectedTeamId]);

  const isMyTeam = selectedTeamId === myTeamId;
  const selectedTeam = useMemo(
    () => (teams || []).find((t) => t.id === selectedTeamId) || null,
    [teams, selectedTeamId],
  );

  // Fetch roster + stats whenever team or filter changes
  useEffect(() => {
    if (!selectedTeamId) return;
    let cancelled = false;
    setLoading(true);
    (async () => {
      try {
        const { data } = await api.get(
          `/teams/${selectedTeamId}/roster-truncated`,
          { params: { stat_filter: statFilter } },
        );
        if (!cancelled) setPlayers(Array.isArray(data?.players) ? data.players : []);
      } catch {
        if (!cancelled) setPlayers([]);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [selectedTeamId, statFilter]);

  const teamTradeBlockPlayerIds = useMemo(
    () => new Set(
      (tradeBlockItems || [])
        .filter((x) => x.item_type === "player" && x.team_id === selectedTeamId && x.player_id)
        .map((x) => String(x.player_id))
    ),
    [tradeBlockItems, selectedTeamId],
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
          {/* Team switcher (Iter 150) — top-right */}
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
            {players.length} players
          </span>
        </div>
      </CardHeader>
      <CardContent className="p-2">
        {/* Header row */}
        <div className={cn(
          "grid gap-1 px-1.5 py-1 text-[10px] uppercase tracking-wider text-muted-foreground border-b border-border",
          capEnabled ? "grid-cols-[auto_1fr_auto_auto_auto_auto]" : "grid-cols-[auto_1fr_auto_auto_auto]",
        )}>
          <span>Pos</span>
          <span>Player</span>
          <span className="text-right">FP</span>
          <span className="text-right">FP/G</span>
          {capEnabled && <span className="text-right">Cap</span>}
          <span className="text-right">·</span>
        </div>

        {/* Rows — 10 on desktop, 5 on mobile (sm:max-h-* + h-* override) */}
        <ScrollArea className="h-[260px] sm:h-[420px]">
          {loading ? (
            <div className="text-center py-6 text-xs text-muted-foreground">Loading…</div>
          ) : players.length === 0 ? (
            <div className="text-center py-6 text-xs text-muted-foreground" data-testid="draft-room-roster-empty">
              No roster data
            </div>
          ) : (
            <div className="space-y-0.5">
              {players.map((p) => {
                const onBlock = teamTradeBlockPlayerIds.has(String(p.id));
                return (
                  <div
                    key={p.id}
                    className={cn(
                      "grid gap-1 px-1.5 py-1.5 rounded items-center text-xs hover:bg-secondary/30 transition-colors",
                      capEnabled ? "grid-cols-[auto_1fr_auto_auto_auto_auto]" : "grid-cols-[auto_1fr_auto_auto_auto]",
                      onBlock && "bg-amber-500/5",
                    )}
                    data-testid={`draft-room-roster-row-${p.id}`}
                  >
                    <Badge className={cn("text-[9px] px-1 py-0 h-3.5 border", positionColors[p.position])}>
                      {p.position}
                    </Badge>
                    <div className="flex items-center gap-1 min-w-0">
                      <Link
                        to={`/players/${p.id}`}
                        className="text-xs font-medium text-foreground truncate hover:text-primary"
                        data-testid={`draft-room-roster-player-link-${p.id}`}
                      >
                        {p.name}
                      </Link>
                      {onBlock && (
                        /* Iter 150 — Megaphone is READ-ONLY (mirrors the league's trade block) */
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <span
                              className="inline-flex h-4 w-4 items-center justify-center rounded-sm bg-amber-500/20 text-amber-300"
                              data-testid={`draft-room-roster-block-${p.id}`}
                            >
                              <Megaphone className="h-2.5 w-2.5" />
                            </span>
                          </TooltipTrigger>
                          <TooltipContent>On {isMyTeam ? "your" : "team's"} trade block</TooltipContent>
                        </Tooltip>
                      )}
                    </div>
                    <span className="text-[11px] text-foreground tabular-nums text-right">
                      {fmt(p.fantasy_points)}
                    </span>
                    <span className="text-[11px] text-muted-foreground tabular-nums text-right">
                      {fmtFloat(p.fp_per_game)}
                    </span>
                    {capEnabled && (
                      <span className="text-[11px] text-muted-foreground tabular-nums text-right">
                        {fmtMoney(p.cap_hit)}
                      </span>
                    )}
                    {/* Iter 150 — Propose Trade icon (clickable on ANY team, including yours) */}
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
                );
              })}
            </div>
          )}
        </ScrollArea>
      </CardContent>
    </Card>
  );
}
