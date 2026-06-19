// @ts-nocheck
/**
 * Iter 183 — Sub-components extracted from the monolithic
 * `PlayerRoster.tsx` to break the ~2950-line file into something
 * maintainable. Contains: StatsTable, CapHitTable,
 * FantasyPointsTable, MatchupScheduleTable, FullScheduleTable,
 * SectionGroup, EmptySlotRow, OpenSlotRow, PlayerRow,
 * TradeButton, MegaphoneButton, DropButton, OwnershipCell.
 *
 * All types, constants, and helpers used by these components are
 * imported from the parent PlayerRoster module. The RosterConfig
 * context (iter180) still lives in the parent so the Provider
 * wrapping in PlayerRoster's render correctly broadcasts the
 * dynamic league config down here.
 *
 * Risks noted for future maintenance:
 *   • These components rely on `useRosterConfig()` — they MUST be
 *     rendered inside the `RosterConfigContext.Provider` in
 *     PlayerRoster. Standalone usage falls back to module defaults.
 *   • The Player type is loose (`@ts-nocheck`); strict typing is a
 *     follow-up.
 *   • Cross-file cycle: this file imports types + helpers from
 *     PlayerRoster.tsx, which in turn imports the components from
 *     here. TypeScript handles type-only cycles fine, and runtime
 *     cycles work because component references aren't dereferenced
 *     at module init time.
 */
import { useState, useMemo, useEffect, useRef } from "react";
import { TrendingUp, TrendingDown, Minus, ArrowUpDown, ChevronLeft, ChevronRight, MinusCircle, MoveVertical, AlertTriangle, Megaphone } from "lucide-react";
import { NewsSignalIcon } from "@/lovable/components/NewsSignalIcon";
import { MinorEligibleBadge } from "@/lovable/components/MinorEligibleBadge";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Checkbox } from "@/components/ui/checkbox";
import { ScrollArea, ScrollBar } from "@/components/ui/scroll-area";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  PositionBadges,
  PositionButton,
  checkIneligibility,
  isPositionHighlighted,
  rosterStatCategories,
  trackedCategories,
  untrackedCategories,
  allStatCategories,
  filterLabels,
  categoryLabels,
  sectionOrder,
  sectionConfig,
  LEAGUE_ROSTER_SLOTS,
  getSlotPositionColor,
  formatSalary,
  shouldShowOpenSlotForSection,
  findHighlightedPlayer,
  useRosterConfig,
} from "./internals";
import type {
  Player,
  RosterSection,
  RosterSlot,
  ViewFilter,
  HighlightProps,
} from "./internals";

// ── Sub-component definitions (originally lines 1842-2953 of
//    PlayerRoster.tsx) ────────────────────────────────────

export const StatsTable = ({
  grouped,
  onTrade,
  onDrop,
  onMegaphone,
  tradeBlockPlayerIds = [],
  onToggleProtection,
  protectedPlayerIds = [],
  protectionEnabled = false,
  protectionDraftType = null,
  ownershipMap = {},
  newsMap = {},
  onPlayerClick,
  getPlayerPoints,
  getSectionTotal,
  filterLabel,
  isOwnTeam = true,
  commissionerMode = false,
  highlightedPlayerId,
  highlightedPositions,
  onToggleHighlight,
  onMoveToSection,
  sectionCounts,
  visibleCategories,
  showFpts = true,
  showOwnership = true,
  showPositionEligibility = true,
  lineupWarnings = {},
}: {
  grouped: Record<RosterSection, Player[]>;
  onTrade: (p: Player) => void;
  onDrop?: (p: Player) => void;
  onMegaphone?: (p: Player) => void;
  tradeBlockPlayerIds?: string[];
  onToggleProtection?: (p: Player) => void;
  protectedPlayerIds?: string[];
  protectionEnabled?: boolean;
  protectionDraftType?: "keeper" | "expansion" | null;
  ownershipMap?: Record<string, any>;
  newsMap?: Record<string, any>;
  onPlayerClick: (p: Player) => void;
  getPlayerPoints: (p: Player) => number;
  getSectionTotal: (s: RosterSection) => number;
  filterLabel: string;
  isOwnTeam?: boolean;
  commissionerMode?: boolean;
  visibleCategories?: string[];
  showFpts?: boolean;
  showOwnership?: boolean;
  showPositionEligibility?: boolean;
  lineupWarnings?: Record<string, any[]>;
} & HighlightProps) => {
  // Iter 180 (fix) — pick up league-driven roster slots from
  // PlayerRoster's RosterConfigContext. Destructured names match the
  // legacy module-level constants so the rest of this component's
  // references just resolve to the dynamic values.
  const { slots: LEAGUE_ROSTER_SLOTS, sections: sectionConfig } = useRosterConfig();
  const displayCategories = visibleCategories ?? rosterStatCategories;
  const statCols = displayCategories.length;
  // Columns: POS, Player, Age, Cap [+ FPTS, FP/G when showFpts] + statCols + OWN%? + Actions
  const colSpan = 4 + (showFpts ? 2 : 0) + statCols + (showOwnership ? 1 : 0) + 1;
  const fptsColIndex = showFpts ? 4 : 4 + statCols;
  const fpgOf = (p: Player) => {
    const gp = p.gamesPlayed || 0;
    return gp > 0 ? (getPlayerPoints(p) / gp).toFixed(2) : "—";
  };
  return (
    <div className="overflow-x-auto">
      <table className="w-full table-fixed">
        <thead>
          <tr className="border-b border-border bg-secondary/30">
            <th className="text-center text-xs font-medium text-muted-foreground p-2 w-[56px]">POS</th>
            <th className="text-left text-xs font-medium text-muted-foreground p-3 w-[220px]">Player</th>
            <th className="text-center text-xs font-medium text-muted-foreground p-2 w-[40px]">Age</th>
            <th className="text-right text-xs font-medium text-muted-foreground p-2 w-[64px]">Cap</th>
            {showFpts && <th className="text-right text-xs font-medium text-muted-foreground p-2 w-[52px]" data-testid="roster-col-fpts">FPTS</th>}
            {showFpts && (
              <th className="text-right text-xs font-medium text-muted-foreground p-2 w-[52px]" data-testid="roster-col-fpg">
                <TooltipProvider>
                  <Tooltip>
                    <TooltipTrigger><span>FP/G</span></TooltipTrigger>
                    <TooltipContent><p>Fantasy points per game played</p></TooltipContent>
                  </Tooltip>
                </TooltipProvider>
              </th>
            )}
            {displayCategories.map(cat => (
              <th key={cat} className="text-center text-xs font-medium text-muted-foreground p-2 w-[48px]">
                <TooltipProvider>
                  <Tooltip>
                    <TooltipTrigger><span>{cat}</span></TooltipTrigger>
                    <TooltipContent><p>{categoryLabels[cat]}</p></TooltipContent>
                  </Tooltip>
                </TooltipProvider>
              </th>
            ))}
            {showOwnership && (
              <th className="text-center text-xs font-medium text-muted-foreground p-2 w-[64px]">
                <TooltipProvider>
                  <Tooltip>
                    <TooltipTrigger><span>OWN%</span></TooltipTrigger>
                    <TooltipContent><p>% of league teams that own this player</p></TooltipContent>
                  </Tooltip>
                </TooltipProvider>
              </th>
            )}
            <th className="text-center text-xs font-medium text-muted-foreground p-2 w-[72px]">Actions</th>
          </tr>
        </thead>
        <tbody>
          {sectionOrder.map((section) => {
            const sectionPlayers = grouped[section];
            const config = sectionConfig[section];

            if (section === "starting") {
              // Render all slots, with empty rows for unfilled ones
              const filledSlotIds = new Set(sectionPlayers.map(p => p.rosterSlotId));
              return (
                <SectionGroup key={section} config={config} sectionTotal={getSectionTotal(section)} colSpan={colSpan} fptsColIndex={fptsColIndex} section={section} playerCount={sectionPlayers.length} sectionPlayers={sectionPlayers} sectionTimeframe="season" getPlayerPoints={getPlayerPoints}>
                  {LEAGUE_ROSTER_SLOTS.map((slot, slotIdx) => {
                    const player = sectionPlayers.find(p => p.rosterSlotId === slot.id);
                    if (player) {
                      return (
                        <PlayerRow key={player.id} player={player} index={slotIdx} onTrade={onTrade} onDrop={onDrop} onMegaphone={onMegaphone} isOnTradeBlock={tradeBlockPlayerIds.includes(String(player.id))} onToggleProtection={onToggleProtection} isProtected={protectedPlayerIds.includes(String(player.id))} protectionEnabled={protectionEnabled} protectionDraftType={protectionDraftType} newsInfo={newsMap[String(player.id)]} onPlayerClick={onPlayerClick} isOwnTeam={isOwnTeam} commissionerMode={commissionerMode} highlightedPlayerId={highlightedPlayerId} highlightedPositions={highlightedPositions} onToggleHighlight={onToggleHighlight} showPositionEligibility={showPositionEligibility} warnings={lineupWarnings[String(player.id)]}>
                          {showFpts && <td className="p-2 text-right font-bold text-primary" data-testid={`row-fpts-${player.id}`}>{getPlayerPoints(player)}</td>}
                          {showFpts && <td className="p-2 text-right text-muted-foreground tabular-nums" data-testid={`row-fpg-${player.id}`}>{fpgOf(player)}</td>}
                          {displayCategories.map(cat => (
                            <td key={cat} className="p-2 text-center text-sm">
                              {player.categoryBreakdown[cat] ?? 0}
                            </td>
                          ))}
                          {showOwnership && <OwnershipCell player={player} ownership={ownershipMap[String(player.id)]} />}
                        </PlayerRow>
                      );
                    }
                    return <EmptySlotRow key={slot.id} slot={slot} colSpan={colSpan} />;
                  })}
                </SectionGroup>
              );
            }

            // Non-starting sections: always show header even if empty
            return (
              <SectionGroup key={section} config={config} sectionTotal={getSectionTotal(section)} colSpan={colSpan} fptsColIndex={fptsColIndex} section={section} playerCount={sectionPlayers.length} sectionPlayers={sectionPlayers} sectionTimeframe="season" getPlayerPoints={getPlayerPoints}>
                {sectionPlayers.length === 0 ? (
                  <>
                    {shouldShowOpenSlotForSection(section, highlightedPlayerId, onMoveToSection, sectionCounts, findHighlightedPlayer(grouped, highlightedPlayerId)) ? (
                      <OpenSlotRow section={section} colSpan={colSpan} onMoveToSection={onMoveToSection!} />
                    ) : (
                      <tr className="border-b border-border/50 opacity-50">
                        <td colSpan={colSpan} className="p-3 text-center">
                          <span className="text-xs text-muted-foreground italic">No players</span>
                        </td>
                      </tr>
                    )}
                  </>
                ) : (
                  <>
                    {sectionPlayers.map((player, index) => (
                      <PlayerRow key={player.id} player={player} index={index} onTrade={onTrade} onDrop={onDrop} onMegaphone={onMegaphone} isOnTradeBlock={tradeBlockPlayerIds.includes(String(player.id))} onToggleProtection={onToggleProtection} isProtected={protectedPlayerIds.includes(String(player.id))} protectionEnabled={protectionEnabled} protectionDraftType={protectionDraftType} newsInfo={newsMap[String(player.id)]} onPlayerClick={onPlayerClick} isOwnTeam={isOwnTeam} commissionerMode={commissionerMode} highlightedPlayerId={highlightedPlayerId} highlightedPositions={highlightedPositions} onToggleHighlight={onToggleHighlight} showPositionEligibility={showPositionEligibility} warnings={lineupWarnings[String(player.id)]}>
                        {showFpts && <td className="p-2 text-right font-bold text-primary" data-testid={`row-fpts-${player.id}`}>{getPlayerPoints(player)}</td>}
                        {showFpts && <td className="p-2 text-right text-muted-foreground tabular-nums" data-testid={`row-fpg-${player.id}`}>{fpgOf(player)}</td>}
                        {displayCategories.map(cat => (
                          <td key={cat} className="p-2 text-center text-sm">
                            {player.categoryBreakdown[cat] ?? 0}
                          </td>
                        ))}
                        {showOwnership && <OwnershipCell player={player} ownership={ownershipMap[String(player.id)]} />}
                      </PlayerRow>
                    ))}
                    {shouldShowOpenSlotForSection(section, highlightedPlayerId, onMoveToSection, sectionCounts, findHighlightedPlayer(grouped, highlightedPlayerId)) && (
                      <OpenSlotRow section={section} colSpan={colSpan} onMoveToSection={onMoveToSection!} />
                    )}
                  </>
                )}
              </SectionGroup>
            );
          })}
        </tbody>
      </table>
    </div>
  );
};

// ── Fantasy Points Breakdown Table ─────────────────────
// ── Cap Hit Table ───────────────────────────────────────
// Rows = players, columns = upcoming seasons. Cell value is the player's
// AAV for each year the contract is active. The season AFTER the contract
// ends shows "UFA" or "RFA" depending on the player's contract type.

export const CapHitTable = ({
  grouped,
  onPlayerClick,
}: {
  grouped: Record<RosterSection, Player[]>;
  onPlayerClick: (p: Player) => void;
}) => {
  const allPlayers: Player[] = sectionOrder.flatMap((s) => grouped[s] || []);

  // Determine the year range. We start at the current fantasy-hockey season
  // (season "2025-26" starts July 1, 2025) and extend out to the longest
  // contract on the roster + 1 for the UFA/RFA terminator column.
  const today = new Date();
  const seasonStart = today.getMonth() >= 6 ? today.getFullYear() : today.getFullYear() - 1;
  const maxYears = allPlayers.reduce((m, p) => Math.max(m, p.contract?.yearsRemaining || 0), 0);
  // +1 covers the "free-agency status" terminator column. Default to 5
  // columns minimum so the table doesn't look empty for short-contract
  // rosters.
  const totalYears = Math.max(5, maxYears + 1);
  const years = Array.from({ length: totalYears }, (_, i) => seasonStart + i);

  const fmtAAV = (n: number) => {
    if (!n) return "—";
    if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(2)}M`;
    if (n >= 1_000) return `$${(n / 1_000).toFixed(0)}K`;
    return `$${n}`;
  };

  const sectionLabels: Partial<Record<RosterSection, string>> = {
    starting: "Starting Lineup",
    bench: "Bench",
    minors: "Minors",
    ir: "Injured Reserve",
    ir_plus: "IR+",
    taxi: "Taxi Squad",
    goalies: "Goalies",
  };

  return (
    <div className="p-6 space-y-6" data-testid="cap-hit-table">
      {sectionOrder.map((section) => {
        const rows = grouped[section] || [];
        if (rows.length === 0) return null;
        return (
          <div key={section}>
            <h4 className="text-xs uppercase tracking-wider text-muted-foreground mb-2">
              {sectionLabels[section] || section}
            </h4>
            <div className="rounded-lg border border-border overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="bg-secondary/40">
                      <th className="text-left py-2 px-3 font-semibold sticky left-0 bg-secondary/40 z-10 min-w-[180px]">
                        Player
                      </th>
                      {years.map((y) => (
                        <th
                          key={y}
                          className="text-right py-2 px-3 font-semibold tabular-nums"
                          data-testid={`cap-hit-year-${y}`}
                        >
                          {y}-{String(y + 1).slice(-2)}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((p) => {
                      const years_remaining = p.contract?.yearsRemaining || 0;
                      const aav = p.contract?.salary || 0;
                      const type = p.contract?.type || "UFA";
                      return (
                        <tr
                          key={p.id}
                          className="border-t border-border hover:bg-secondary/30"
                          data-testid={`cap-hit-row-${p.id}`}
                        >
                          <td className="py-2 px-3 sticky left-0 bg-card hover:bg-secondary/30 z-10">
                            <button
                              type="button"
                              onClick={() => onPlayerClick(p)}
                              className="font-medium text-foreground hover:text-primary text-left flex flex-col leading-tight"
                            >
                              <span className="truncate max-w-[160px]">{p.name}</span>
                              <span className="text-[10px] text-muted-foreground">
                                {p.position} · {p.team}
                              </span>
                            </button>
                          </td>
                          {years.map((_y, idx) => {
                            if (idx < years_remaining) {
                              return (
                                <td
                                  key={idx}
                                  className="py-2 px-3 text-right tabular-nums text-foreground"
                                >
                                  {fmtAAV(aav)}
                                </td>
                              );
                            }
                            if (idx === years_remaining) {
                              // Terminator column shows the free-agency status
                              // immediately AFTER the contract ends. RFA for
                              // entry-level or restricted-FA players, UFA for
                              // everyone else.
                              const label =
                                type === "RFA" || type === "ELC" ? "RFA" : "UFA";
                              const tone =
                                label === "RFA"
                                  ? "bg-amber-500/15 text-amber-400 border-amber-500/30"
                                  : "bg-red-500/15 text-red-400 border-red-500/30";
                              return (
                                <td key={idx} className="py-2 px-3 text-right">
                                  <span
                                    className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold border ${tone}`}
                                    data-testid={`cap-hit-fa-${p.id}-${label}`}
                                  >
                                    {label}
                                  </span>
                                </td>
                              );
                            }
                            return (
                              <td key={idx} className="py-2 px-3 text-right text-muted-foreground/40">
                                —
                              </td>
                            );
                          })}
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
};



export const FantasyPointsTable = ({
  grouped,
  onTrade,
  onPlayerClick,
  getSectionTotal,
  isOwnTeam = true,
  commissionerMode = false,
  highlightedPlayerId,
  highlightedPositions,
  onToggleHighlight,
  onMoveToSection,
  sectionCounts,
  visibleCategories,
  showFpts = true,
  showPositionEligibility = true,
  scoringConfig,
}: {
  grouped: Record<RosterSection, Player[]>;
  onTrade: (p: Player) => void;
  onPlayerClick: (p: Player) => void;
  getSectionTotal: (s: RosterSection) => number;
  isOwnTeam?: boolean;
  commissionerMode?: boolean;
  visibleCategories?: string[];
  showFpts?: boolean;
  showPositionEligibility?: boolean;
  scoringConfig?: any;
} & HighlightProps) => {
  // Iter 180 (fix) — see RosterConfigContext comment in StatsTable.
  const { slots: LEAGUE_ROSTER_SLOTS, sections: sectionConfig } = useRosterConfig();
  const defaultCategories = ["G", "A", "PPP", "SOG", "HIT", "BLK", "PIM", "+/-"];
  const categories = visibleCategories ?? defaultCategories;

  // Map UI category abbreviation → scoring_config key
  const CAT_TO_CFG_KEY: Record<string, string> = {
    G: "goals", A: "assists", PPG: "power_play_goals", PPP: "power_play_points",
    SHG: "short_handed_goals", SHP: "short_handed_points", GWG: "game_winning_goals",
    SOG: "shots", HIT: "hits", BLK: "blocked_shots", PIM: "penalty_minutes", "+/-": "plus_minus",
    W: "wins", L: "losses", SV: "saves", GA: "goals_against", SO: "shutouts", OTL: "overtime_losses",
  };
  const skaterCfg = scoringConfig?.skater_scoring || {};
  const goalieCfg = scoringConfig?.goalie_scoring || {};

  const weightFor = (cat: string, isGoalie: boolean): number | null => {
    const k = CAT_TO_CFG_KEY[cat];
    if (!k) return null;
    const cfg = isGoalie ? goalieCfg : skaterCfg;
    const w = cfg?.[k];
    return typeof w === "number" ? w : null;
  };

  // Render a single category cell — when scoring weight is known, show
  // "count × w = pts" so the user sees per-category point contribution.
  const CatCell = ({ player, cat }: { player: Player; cat: string }) => {
    const count = Number((player.categoryBreakdown as any)[cat] ?? 0);
    const isGoalie = (player as any).position === "G" || (player as any).player_type === "goalie";
    const w = weightFor(cat, isGoalie);
    if (w == null || count === 0) {
      return <td className="p-3 text-center text-sm font-medium" data-testid={`fp-cell-${cat}-${player.id}`}>{count}</td>;
    }
    const pts = +(count * w).toFixed(1);
    const ptsTone = pts >= 0 ? "text-emerald-400" : "text-rose-400";
    return (
      <td className="p-2 text-center text-[11px] leading-tight" data-testid={`fp-cell-${cat}-${player.id}`}>
        <div className="font-medium">{count}</div>
        <div className={`text-[9px] ${ptsTone} tabular-nums`} data-testid={`fp-pts-${cat}-${player.id}`}>{pts > 0 ? `+${pts}` : pts} pt{Math.abs(pts) === 1 ? "" : "s"}</div>
      </td>
    );
  };
  return (
    <div className="overflow-x-auto">
      <table className="w-full">
        <thead>
          <tr className="border-b border-border bg-secondary/30">
            <th className="text-center text-xs font-medium text-muted-foreground p-3 w-[56px]">POS</th>
            <th className="text-left text-xs font-medium text-muted-foreground p-4">Player</th>
            {categories.map(cat => {
              const w = skaterCfg[CAT_TO_CFG_KEY[cat]] ?? goalieCfg[CAT_TO_CFG_KEY[cat]];
              return (
                <th key={cat} className="text-center text-xs font-medium text-muted-foreground p-3 min-w-[60px]">
                  <TooltipProvider>
                    <Tooltip>
                      <TooltipTrigger>
                        <span>{cat}{typeof w === "number" && w !== 1 ? <span className="text-[9px] text-muted-foreground/70 ml-0.5">×{w}</span> : null}</span>
                      </TooltipTrigger>
                      <TooltipContent><p>{categoryLabels[cat]}{typeof w === "number" ? ` (${w} pt${Math.abs(w) === 1 ? "" : "s"} each)` : ""}</p></TooltipContent>
                    </Tooltip>
                  </TooltipProvider>
                </th>
              );
            })}
            {showFpts && <th className="text-right text-xs font-medium text-muted-foreground p-4">Total</th>}
            <th className="text-center text-xs font-medium text-muted-foreground p-4">Trade</th>
          </tr>
        </thead>
        <tbody>
          {sectionOrder.map((section) => {
            const sectionPlayers = grouped[section];
            const config = sectionConfig[section];
            const colSpan = categories.length + 3 + (showFpts ? 1 : 0);

            if (section === "starting") {
              return (
                <SectionGroup key={section} config={config} sectionTotal={getSectionTotal(section)} colSpan={colSpan} section={section} playerCount={sectionPlayers.length} sectionPlayers={sectionPlayers} sectionTimeframe="season" getPlayerPoints={getPlayerPoints}>
                  {LEAGUE_ROSTER_SLOTS.map((slot, slotIdx) => {
                    const player = sectionPlayers.find(p => p.rosterSlotId === slot.id);
                    if (!player) return <EmptySlotRow key={slot.id} slot={slot} colSpan={colSpan} />;
                    const highlighted = isPositionHighlighted(player, highlightedPositions, highlightedPlayerId);
                    const ineligibility = checkIneligibility(player);
                    return (
                      <tr key={player.id} className={`border-b border-border/50 hover:bg-secondary/20 transition-colors animate-fade-in ${highlighted ? "bg-success/10" : ""} ${ineligibility.isIneligible ? "bg-destructive/10 border-l-2 border-l-destructive" : ""}`} style={{ animationDelay: `${slotIdx * 50}ms` }}>
                        <td className="p-3 text-center"><PositionButton player={player} highlightedPlayerId={highlightedPlayerId} onToggleHighlight={onToggleHighlight} /></td>
                        <td className="p-4">
                          <div className="flex items-center gap-3">
                            <div className="h-8 w-8 rounded-lg bg-gradient-to-br from-secondary to-muted flex items-center justify-center text-xs font-bold shrink-0">{player.team}</div>
                            <div className="flex flex-col gap-0.5">
                              <button onClick={() => onPlayerClick(player)} className="font-medium text-foreground text-sm hover:text-primary transition-colors cursor-pointer text-left">{player.name}</button>
                              {showPositionEligibility && <PositionBadges player={player} />}
                            </div>
                          </div>
                        </td>
                        {categories.map(cat => (<CatCell key={cat} player={player} cat={cat} />))}
                        {showFpts && <td className="p-4 text-right font-bold text-primary">{player.points}</td>}
                        <td className="p-4 text-center"><TradeButton player={player} onTrade={onTrade} /></td>
                      </tr>
                    );
                  })}
                </SectionGroup>
              );
            }

            return (
              <SectionGroup key={section} config={config} sectionTotal={getSectionTotal(section)} colSpan={colSpan} section={section} playerCount={sectionPlayers.length} sectionPlayers={sectionPlayers} sectionTimeframe="season" getPlayerPoints={getPlayerPoints}>
                {sectionPlayers.length === 0 ? (
                  <>
                    {shouldShowOpenSlotForSection(section, highlightedPlayerId, onMoveToSection, sectionCounts, findHighlightedPlayer(grouped, highlightedPlayerId)) ? (
                      <OpenSlotRow section={section} colSpan={colSpan} onMoveToSection={onMoveToSection!} />
                    ) : (
                      <tr className="border-b border-border/50 opacity-50"><td colSpan={colSpan} className="p-3 text-center"><span className="text-xs text-muted-foreground italic">No players</span></td></tr>
                    )}
                  </>
                ) : (
                  <>
                    {sectionPlayers.map((player, index) => {
                      const highlighted = isPositionHighlighted(player, highlightedPositions, highlightedPlayerId);
                      const ineligibility = checkIneligibility(player);
                      return (
                        <tr key={player.id} className={`border-b border-border/50 hover:bg-secondary/20 transition-colors animate-fade-in ${highlighted ? "bg-success/10" : ""} ${ineligibility.isIneligible ? "bg-destructive/10 border-l-2 border-l-destructive" : ""}`} style={{ animationDelay: `${index * 50}ms` }}>
                          <td className="p-3 text-center"><PositionButton player={player} highlightedPlayerId={highlightedPlayerId} onToggleHighlight={onToggleHighlight} /></td>
                          <td className="p-4">
                            <div className="flex items-center gap-3">
                              <div className="h-8 w-8 rounded-lg bg-gradient-to-br from-secondary to-muted flex items-center justify-center text-xs font-bold shrink-0">{player.team}</div>
                              <div className="flex flex-col gap-0.5">
                                <button onClick={() => onPlayerClick(player)} className="font-medium text-foreground text-sm hover:text-primary transition-colors cursor-pointer text-left">{player.name}</button>
                                {showPositionEligibility && <PositionBadges player={player} />}
                              </div>
                            </div>
                          </td>
                          {categories.map(cat => (<CatCell key={cat} player={player} cat={cat} />))}
                          {showFpts && <td className="p-4 text-right font-bold text-primary">{player.points}</td>}
                          <td className="p-4 text-center"><TradeButton player={player} onTrade={onTrade} /></td>
                        </tr>
                      );
                    })}
                    {shouldShowOpenSlotForSection(section, highlightedPlayerId, onMoveToSection, sectionCounts, findHighlightedPlayer(grouped, highlightedPlayerId)) && (
                      <OpenSlotRow section={section} colSpan={colSpan} onMoveToSection={onMoveToSection!} />
                    )}
                  </>
                )}
              </SectionGroup>
            );
          })}
        </tbody>
      </table>
    </div>
  );
};

// ── Matchup Schedule Table ─────────────────────────────

export const MatchupScheduleTable = ({
  grouped,
  onTrade,
  onPlayerClick,
  isOwnTeam = true,
  commissionerMode = false,
  highlightedPlayerId,
  highlightedPositions,
  onToggleHighlight,
  onMoveToSection,
  sectionCounts,
  showPositionEligibility: _showPosElig,
}: {
  grouped: Record<RosterSection, Player[]>;
  onTrade: (p: Player) => void;
  onPlayerClick: (p: Player) => void;
  isOwnTeam?: boolean;
  commissionerMode?: boolean;
  showPositionEligibility?: boolean;
} & HighlightProps) => {
  // Iter 180 (fix) — see RosterConfigContext comment in StatsTable.
  const { slots: LEAGUE_ROSTER_SLOTS, sections: sectionConfig } = useRosterConfig();
  const matchupDays = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

  return (
    <div className="overflow-x-auto">
      <table className="w-full">
        <thead>
          <tr className="border-b border-border bg-secondary/30">
            <th className="text-center text-xs font-medium text-muted-foreground p-3 w-[56px]">POS</th>
            <th className="text-left text-xs font-medium text-muted-foreground p-4">Player</th>
            {matchupDays.map(day => (
              <th key={day} className="text-center text-xs font-medium text-muted-foreground p-3 min-w-[50px]">{day}</th>
            ))}
            <th className="text-center text-xs font-medium text-muted-foreground p-4">GP</th>
            <th className="text-center text-xs font-medium text-muted-foreground p-4">Trade</th>
          </tr>
        </thead>
        <tbody>
          {sectionOrder.map((section) => {
            const sectionPlayers = grouped[section];
            const config = sectionConfig[section];
            const colSpan = matchupDays.length + 4;

            const renderMatchupPlayerRow = (player: Player, index: number) => {
              const gameDays = new Set<number>();
              const teamOpps = ["MTL", "BOS", "TBL", "NYR", "DET", "OTT", "BUF"];
              for (let i = 0; i < player.matchupGames; i++) {
                let d: number;
                do { d = Math.floor(Math.random() * 7); } while (gameDays.has(d));
                gameDays.add(d);
              }
              const highlighted = isPositionHighlighted(player, highlightedPositions, highlightedPlayerId);
              const ineligibility = checkIneligibility(player);
              return (
                <tr key={player.id} className={`border-b border-border/50 hover:bg-secondary/20 transition-colors animate-fade-in ${highlighted ? "bg-success/10" : ""} ${ineligibility.isIneligible ? "bg-destructive/10 border-l-2 border-l-destructive" : ""}`} style={{ animationDelay: `${index * 50}ms` }}>
                  <td className="p-3 text-center"><PositionButton player={player} highlightedPlayerId={highlightedPlayerId} onToggleHighlight={onToggleHighlight} /></td>
                  <td className="p-4">
                    <div className="flex items-center gap-3">
                      <div className="h-8 w-8 rounded-lg bg-gradient-to-br from-secondary to-muted flex items-center justify-center text-xs font-bold shrink-0">{player.team}</div>
                      <div className="flex flex-col gap-0.5">
                        <button onClick={() => onPlayerClick(player)} className="font-medium text-foreground text-sm hover:text-primary transition-colors cursor-pointer text-left">{player.name}</button>
                        <PositionBadges player={player} />
                      </div>
                    </div>
                  </td>
                  {matchupDays.map((_, di) => (
                    <td key={di} className="p-3 text-center">
                      {gameDays.has(di) ? (<span className="text-xs font-bold bg-primary/20 text-primary px-2 py-1 rounded">{teamOpps[di % teamOpps.length]}</span>) : (<span className="text-xs text-muted-foreground">—</span>)}
                    </td>
                  ))}
                  <td className="p-3 text-center font-bold text-primary">{player.matchupGames}</td>
                  <td className="p-4 text-center"><TradeButton player={player} onTrade={onTrade} /></td>
                </tr>
              );
            };

            if (section === "starting") {
              return (
                <SectionGroup key={section} config={config} colSpan={colSpan} section={section} playerCount={sectionPlayers.length} sectionPlayers={sectionPlayers} sectionTimeframe="season" getPlayerPoints={getPlayerPoints}>
                  {LEAGUE_ROSTER_SLOTS.map((slot, slotIdx) => {
                    const player = sectionPlayers.find(p => p.rosterSlotId === slot.id);
                    if (!player) return <EmptySlotRow key={slot.id} slot={slot} colSpan={colSpan} />;
                    return renderMatchupPlayerRow(player, slotIdx);
                  })}
                </SectionGroup>
              );
            }

            return (
              <SectionGroup key={section} config={config} colSpan={colSpan} section={section} playerCount={sectionPlayers.length} sectionPlayers={sectionPlayers} sectionTimeframe="season" getPlayerPoints={getPlayerPoints}>
                {sectionPlayers.length === 0 ? (
                  <>
                    {shouldShowOpenSlotForSection(section, highlightedPlayerId, onMoveToSection, sectionCounts, findHighlightedPlayer(grouped, highlightedPlayerId)) ? (
                      <OpenSlotRow section={section} colSpan={colSpan} onMoveToSection={onMoveToSection!} />
                    ) : (
                      <tr className="border-b border-border/50 opacity-50"><td colSpan={colSpan} className="p-3 text-center"><span className="text-xs text-muted-foreground italic">No players</span></td></tr>
                    )}
                  </>
                ) : (
                  <>
                    {sectionPlayers.map((player, index) => renderMatchupPlayerRow(player, index))}
                    {shouldShowOpenSlotForSection(section, highlightedPlayerId, onMoveToSection, sectionCounts, findHighlightedPlayer(grouped, highlightedPlayerId)) && (
                      <OpenSlotRow section={section} colSpan={colSpan} onMoveToSection={onMoveToSection!} />
                    )}
                  </>
                )}
              </SectionGroup>
            );
          })}
        </tbody>
      </table>
    </div>
  );
};

// ── Full Schedule Table (scrollable) ───────────────────

export const FullScheduleTable = ({
  grouped,
  onTrade,
  onPlayerClick,
  isOwnTeam = true,
  commissionerMode = false,
  highlightedPlayerId,
  highlightedPositions,
  onToggleHighlight,
  onMoveToSection,
  sectionCounts,
  showPositionEligibility: _showPosElig2,
}: {
  grouped: Record<RosterSection, Player[]>;
  onTrade: (p: Player) => void;
  onPlayerClick: (p: Player) => void;
  isOwnTeam?: boolean;
  commissionerMode?: boolean;
  showPositionEligibility?: boolean;
} & HighlightProps) => {
  // Iter 180 (fix) — see RosterConfigContext comment in StatsTable.
  const { slots: LEAGUE_ROSTER_SLOTS, sections: sectionConfig } = useRosterConfig();
  const allPlayers = Object.values(grouped).flat();
  const scheduleLength = allPlayers[0]?.schedule.length ?? 82;

  return (
    <ScrollArea className="w-full">
      <div className="min-w-[3000px]">
        <table className="w-full">
          <thead>
            <tr className="border-b border-border bg-secondary/30">
              <th className="text-center text-xs font-medium text-muted-foreground p-2 sticky left-0 bg-card z-10 min-w-[56px]">POS</th>
              <th className="text-left text-xs font-medium text-muted-foreground p-4 sticky left-[56px] bg-card z-10 min-w-[200px]">Player</th>
              {Array.from({ length: scheduleLength }, (_, i) => (
                <th key={i} className="text-center text-xs font-medium text-muted-foreground p-2 min-w-[48px]">
                  {i + 1}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sectionOrder.map((section) => {
              const sectionPlayers = grouped[section];
              const config = sectionConfig[section];
              const colSpan = scheduleLength + 2;

              const renderFullScheduleRow = (player: Player, index: number) => {
                const highlighted = isPositionHighlighted(player, highlightedPositions, highlightedPlayerId);
                const ineligibility = checkIneligibility(player);
                return (
                  <tr key={player.id} className={`border-b border-border/50 hover:bg-secondary/20 transition-colors ${highlighted ? "bg-success/10" : ""} ${ineligibility.isIneligible ? "bg-destructive/10 border-l-2 border-l-destructive" : ""}`}>
                    <td className="p-2 text-center sticky left-0 bg-card z-10">
                      <PositionButton player={player} highlightedPlayerId={highlightedPlayerId} onToggleHighlight={onToggleHighlight} />
                    </td>
                    <td className="p-4 sticky left-[56px] bg-card z-10">
                      <div className="flex items-center gap-2">
                        <div className="h-7 w-7 rounded bg-gradient-to-br from-secondary to-muted flex items-center justify-center text-[10px] font-bold shrink-0">{player.team}</div>
                        <div className="flex flex-col gap-0.5">
                          <button onClick={() => onPlayerClick(player)} className="font-medium text-foreground text-sm whitespace-nowrap hover:text-primary transition-colors cursor-pointer text-left">{player.name}</button>
                          <PositionBadges player={player} />
                        </div>
                      </div>
                    </td>
                    {player.schedule.map((game, gi) => (
                      <td key={gi} className="p-1 text-center">
                        <TooltipProvider><Tooltip><TooltipTrigger>
                          <span className={`text-[10px] font-bold px-1 py-0.5 rounded ${game.played ? "bg-primary/15 text-primary" : "bg-secondary/50 text-muted-foreground"}`}>{game.opponent}</span>
                        </TooltipTrigger><TooltipContent><p className="text-xs">{game.date} vs {game.opponent}{game.played && ` • ${game.goals}G ${game.assists}A ${game.pts}PTS`}</p></TooltipContent></Tooltip></TooltipProvider>
                      </td>
                    ))}
                  </tr>
                );
              };

              if (section === "starting") {
                return (
                  <SectionGroup key={section} config={config} colSpan={colSpan} section={section} playerCount={sectionPlayers.length} sectionPlayers={sectionPlayers} sectionTimeframe="season" getPlayerPoints={getPlayerPoints}>
                    {LEAGUE_ROSTER_SLOTS.map((slot, slotIdx) => {
                      const player = sectionPlayers.find(p => p.rosterSlotId === slot.id);
                      if (!player) return <EmptySlotRow key={slot.id} slot={slot} colSpan={colSpan} />;
                      return renderFullScheduleRow(player, slotIdx);
                    })}
                  </SectionGroup>
                );
              }

              return (
                <SectionGroup key={section} config={config} colSpan={colSpan} section={section} playerCount={sectionPlayers.length} sectionPlayers={sectionPlayers} sectionTimeframe="season" getPlayerPoints={getPlayerPoints}>
                  {sectionPlayers.length === 0 ? (
                    <>
                      {shouldShowOpenSlotForSection(section, highlightedPlayerId, onMoveToSection, sectionCounts, findHighlightedPlayer(grouped, highlightedPlayerId)) ? (
                        <OpenSlotRow section={section} colSpan={colSpan} onMoveToSection={onMoveToSection!} />
                      ) : (
                        <tr className="border-b border-border/50 opacity-50"><td colSpan={colSpan} className="p-3 text-center"><span className="text-xs text-muted-foreground italic">No players</span></td></tr>
                      )}
                    </>
                  ) : (
                    <>
                      {sectionPlayers.map((player, index) => renderFullScheduleRow(player, index))}
                      {shouldShowOpenSlotForSection(section, highlightedPlayerId, onMoveToSection, sectionCounts, findHighlightedPlayer(grouped, highlightedPlayerId)) && (
                        <OpenSlotRow section={section} colSpan={colSpan} onMoveToSection={onMoveToSection!} />
                      )}
                    </>
                  )}
                </SectionGroup>
              );
            })}
          </tbody>
        </table>
      </div>
      <ScrollBar orientation="horizontal" />
    </ScrollArea>
  );
};

// ── Shared Sub-components ──────────────────────────────

export const SectionGroup = ({
  config,
  children,
  sectionTotal,
  colSpan = 9,
  fptsColIndex,
  section,
  playerCount,
  // Iter 184 — per-section stats summary props. When all three are
  // provided we render a collapsible summary row beneath the header
  // showing average fpts/game over the chosen timeframe plus the
  // top + bottom performer in this section.
  sectionPlayers,
  sectionTimeframe,
  getPlayerPoints,
}: {
  config: { label: string; color: string; borderColor: string; maxSlots: number };
  children: React.ReactNode;
  sectionTotal?: number;
  colSpan?: number;
  fptsColIndex?: number;
  section?: RosterSection;
  playerCount?: number;
  sectionPlayers?: Player[];
  sectionTimeframe?: string;
  getPlayerPoints?: (p: Player) => number;
}) => {
  const showCount = section && section !== "starting" && playerCount !== undefined;
  const headerLabel = showCount
    ? `${config.label} - ${playerCount}/${config.maxSlots}`
    : config.label;

  // Iter 184 — Compute summary metrics. Uses `statsByPeriod` (which
  // backend populates per timeframe) when present, else falls back
  // to the season points. Only renders when caller supplied props.
  const summary = useMemo(() => {
    if (!sectionPlayers || sectionPlayers.length === 0 || !getPlayerPoints) {
      return null;
    }
    const tf = sectionTimeframe || "season";
    const ptsFor = (p: Player): number => {
      const periodPts = (p.statsByPeriod && p.statsByPeriod[tf]);
      if (typeof periodPts === "number" && periodPts > 0) return periodPts;
      return getPlayerPoints(p);
    };
    const ranked = [...sectionPlayers]
      .map((p) => ({ p, fpts: ptsFor(p), gp: Math.max(1, p.gamesPlayed || 1) }))
      .sort((a, b) => (b.fpts / b.gp) - (a.fpts / a.gp));
    if (ranked.length === 0) return null;
    const avg = ranked.reduce((s, r) => s + (r.fpts / r.gp), 0) / ranked.length;
    return {
      avg: avg.toFixed(1),
      top: ranked[0],
      bottom: ranked[ranked.length - 1],
      timeframeLabel: ({
        "7d": "Last 7 Days", "14d": "Last 14 Days",
        "30d": "Last 30 Days", "60d": "Last 60 Days",
        "season": "Season",
      } as Record<string, string>)[tf] || tf,
    };
  }, [sectionPlayers, sectionTimeframe, getPlayerPoints]);

  const [expanded, setExpanded] = useState<boolean>(false);

  return (
    <>
      <tr>
        {fptsColIndex !== undefined && sectionTotal !== undefined ? (
          <>
            <td colSpan={fptsColIndex} className={`px-4 py-2 ${config.color} border-l-4 ${config.borderColor}`}>
              <button
                type="button"
                className="flex items-center gap-2 text-left"
                onClick={() => setExpanded((x) => !x)}
                data-testid={`section-toggle-${section || "default"}`}
              >
                <span className="text-xs font-bold uppercase tracking-wider text-foreground">
                  {headerLabel}
                </span>
                {summary && (
                  <span className="text-[10px] font-normal text-muted-foreground normal-case tracking-normal">
                    · Avg {summary.avg} fpts/g · {summary.timeframeLabel}
                    <ChevronRight className={`inline h-3 w-3 ml-1 transition-transform ${expanded ? "rotate-90" : ""}`} />
                  </span>
                )}
              </button>
            </td>
            <td className={`px-2 py-2 text-right ${config.color}`}>
              <span className="text-xs font-semibold text-primary">{sectionTotal} pts</span>
            </td>
            <td colSpan={colSpan - fptsColIndex - 1} className={`${config.color}`} />
          </>
        ) : (
          <td colSpan={colSpan} className={`px-4 py-2 ${config.color} border-l-4 ${config.borderColor}`}>
            <div className="flex items-center justify-between">
              <button
                type="button"
                className="flex items-center gap-2 text-left"
                onClick={() => setExpanded((x) => !x)}
                data-testid={`section-toggle-${section || "default"}`}
              >
                <span className="text-xs font-bold uppercase tracking-wider text-foreground">
                  {headerLabel}
                </span>
                {summary && (
                  <span className="text-[10px] font-normal text-muted-foreground normal-case tracking-normal">
                    · Avg {summary.avg} fpts/g · {summary.timeframeLabel}
                    <ChevronRight className={`inline h-3 w-3 ml-1 transition-transform ${expanded ? "rotate-90" : ""}`} />
                  </span>
                )}
              </button>
              {sectionTotal !== undefined && (
                <span className="text-xs font-semibold text-primary">{sectionTotal} pts</span>
              )}
            </div>
          </td>
        )}
      </tr>
      {expanded && summary && (
        <tr data-testid={`section-summary-${section || "default"}`}>
          <td colSpan={colSpan} className={`px-4 py-2 ${config.color} border-l-4 ${config.borderColor} text-[11px]`}>
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-muted-foreground">
              <span className="font-semibold text-emerald-300">
                ↑ Top: {summary.top.p.name} — {(summary.top.fpts / summary.top.gp).toFixed(1)} fpts/g
              </span>
              <span className="font-semibold text-rose-300">
                ↓ Low: {summary.bottom.p.name} — {(summary.bottom.fpts / summary.bottom.gp).toFixed(1)} fpts/g
              </span>
              <span className="opacity-70">
                ({sectionPlayers!.length} player{sectionPlayers!.length === 1 ? "" : "s"} · {summary.timeframeLabel})
              </span>
            </div>
          </td>
        </tr>
      )}
      {children}
    </>
  );
};

// ── Empty Slot Row ─────────────────────────────────────

export const EmptySlotRow = ({ slot, colSpan }: { slot: RosterSlot; colSpan: number }) => (
  <tr className="border-b border-border/50 opacity-50">
    <td className="p-2 text-center">
      <span className={`text-xs font-bold px-3 py-1.5 rounded-lg border min-w-[40px] inline-block ${getSlotPositionColor(slot.label)}`}>
        {slot.label}
      </span>
    </td>
    <td colSpan={colSpan - 1} className="p-3">
      <span className="text-xs text-muted-foreground italic">Empty slot</span>
    </td>
  </tr>
);

// ── Open Slot Row (clickable, appears when player highlighted) ──

export const OpenSlotRow = ({ section, colSpan, onMoveToSection }: { section: RosterSection; colSpan: number; onMoveToSection: (section: RosterSection) => void }) => {
  // Iter 180 (fix) — see RosterConfigContext comment in StatsTable.
  const { sections: sectionConfig } = useRosterConfig();
  const config = sectionConfig[section];
  const label = section === "bench" ? "BEN" : section === "ir" ? "IR" : "M";
  return (
    <tr
      className="border-b border-border/50 cursor-pointer hover:bg-success/10 transition-colors animate-fade-in"
      onClick={() => onMoveToSection(section)}
    >
      <td className="p-2 text-center">
        <span className={`text-xs font-bold px-3 py-1.5 rounded-lg border border-dashed border-success/50 min-w-[40px] inline-block bg-success/10 text-success`}>
          {label}
        </span>
      </td>
      <td colSpan={colSpan - 1} className="p-3">
        <span className="text-xs text-success font-medium italic">
          ↓ Move here — open {config.label.toLowerCase()} slot
        </span>
      </td>
    </tr>
  );
};

export const PlayerRow = ({
  player,
  index,
  onTrade,
  onDrop,
  onMegaphone,
  isOnTradeBlock = false,
  onToggleProtection,
  isProtected = false,
  protectionEnabled = false,
  protectionDraftType = null,
  newsInfo,
  onPlayerClick,
  children,
  isOwnTeam = true,
  commissionerMode = false,
  highlightedPlayerId,
  highlightedPositions,
  onToggleHighlight,
  showPositionEligibility = true,
  warnings,
}: {
  player: Player;
  index: number;
  onTrade: (p: Player) => void;
  onDrop?: (p: Player) => void;
  onMegaphone?: (p: Player) => void;
  isOnTradeBlock?: boolean;
  onToggleProtection?: (p: Player) => void;
  isProtected?: boolean;
  protectionEnabled?: boolean;
  protectionDraftType?: "keeper" | "expansion" | null;
  newsInfo?: any;
  onPlayerClick: (p: Player) => void;
  children: React.ReactNode;
  isOwnTeam?: boolean;
  commissionerMode?: boolean;
  showPositionEligibility?: boolean;
  warnings?: any[];
} & HighlightProps) => {
  const canEdit = isOwnTeam || commissionerMode;
  const otherSections = sectionOrder.filter(s => s !== player.rosterSection);
  const highlighted = isPositionHighlighted(player, highlightedPositions, highlightedPlayerId);
  const ineligibility = checkIneligibility(player);
  const hasWarnings = Array.isArray(warnings) && warnings.length > 0;
  const warningMessages = hasWarnings ? warnings!.map((w: any) => w.message).filter(Boolean) : [];
  // Iter 180 (fix) — see RosterConfigContext comment in StatsTable.
  const { sections: sectionConfig } = useRosterConfig();

  return (
    <tr
      className={`border-b border-border/50 hover:bg-secondary/20 transition-colors animate-fade-in ${highlighted ? "bg-success/10" : ""} ${ineligibility.isIneligible ? "bg-destructive/10 border-l-2 border-l-destructive" : ""}`}
      style={{ animationDelay: `${index * 50}ms` }}
    >
      <td className="p-2 text-center">
        <PositionButton player={player} highlightedPlayerId={highlightedPlayerId} onToggleHighlight={onToggleHighlight} />
      </td>
      <td className="p-3">
        <div className="flex items-center gap-2">
          <div className="h-8 w-8 rounded-md bg-gradient-to-br from-secondary to-muted flex items-center justify-center text-[10px] font-bold shrink-0">
            {player.team}
          </div>
          <div className="flex flex-col gap-0.5 min-w-0">
            <div className="flex items-center gap-1.5 min-w-0">
              <button onClick={() => onPlayerClick(player)} className="font-medium text-sm text-foreground hover:text-primary transition-colors cursor-pointer truncate text-left">{player.name}</button>
              <MinorEligibleBadge eligible={(player as any).minor_eligible || (player as any).player_type === "prospect"} />
              {newsInfo && <NewsSignalIcon player={{ ...newsInfo, _id: player.id, name: player.name }} />}
              {hasWarnings && (
                <TooltipProvider>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Badge
                        variant="outline"
                        className="h-5 px-1.5 py-0 text-[10px] font-medium bg-yellow-500/15 text-yellow-500 border-yellow-500/40 hover:bg-yellow-500/25 cursor-help flex items-center gap-1 shrink-0"
                        data-testid={`lineup-warning-${player.id}`}
                      >
                        <AlertTriangle className="h-3 w-3" />
                        <span>Warning</span>
                      </Badge>
                    </TooltipTrigger>
                    <TooltipContent side="top" className="max-w-xs">
                      <div className="space-y-1">
                        {warningMessages.map((m: string, i: number) => (
                          <p key={i} className="text-xs">{m}</p>
                        ))}
                      </div>
                    </TooltipContent>
                  </Tooltip>
                </TooltipProvider>
              )}
            </div>
            {showPositionEligibility && <PositionBadges player={player} />}
          </div>
        </div>
      </td>
      <td className="p-2 text-center text-xs text-muted-foreground">{player.age}</td>
      <td className="p-2 text-right text-xs font-semibold text-accent">{formatSalary(player.contract.salary)}</td>
      {children}
      <td className="p-2 text-center">
        <div className="flex items-center justify-center gap-0.5">
          <TradeButton player={player} onTrade={onTrade} />
          {canEdit && onMegaphone && (
            <MegaphoneButton player={player} active={isOnTradeBlock} onMegaphone={onMegaphone} />
          )}
          {canEdit && protectionEnabled && onToggleProtection && (
            <ShieldButton
              player={player}
              active={isProtected}
              draftType={protectionDraftType}
              onToggle={onToggleProtection}
            />
          )}
          {canEdit && <DropButton player={player} onDrop={onDrop || onTrade} />}
          {commissionerMode && (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="icon" className="h-7 w-7 text-muted-foreground hover:text-primary hover:bg-primary/10">
                  <MoveVertical className="h-3.5 w-3.5" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="min-w-[140px]">
                {otherSections.map(section => (
                  <DropdownMenuItem key={section} className="text-xs cursor-pointer">
                    Move to {sectionConfig[section].label}
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
          )}
        </div>
      </td>
    </tr>
  );
};

export const TradeButton = ({ player, onTrade }: { player: Player; onTrade: (p: Player) => void }) => (
  <TooltipProvider>
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          className="h-7 w-7 text-muted-foreground hover:text-primary hover:bg-primary/10"
          onClick={() => onTrade(player)}
          data-testid={`roster-trade-btn-${player.id}`}
        >
          <ArrowUpDown className="h-3.5 w-3.5" />
        </Button>
      </TooltipTrigger>
      <TooltipContent><p>Propose Trade</p></TooltipContent>
    </Tooltip>
  </TooltipProvider>
);

export const MegaphoneButton = ({
  player, active, onMegaphone,
}: { player: Player; active?: boolean; onMegaphone: (p: Player) => void }) => (
  <TooltipProvider>
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          className={`h-7 w-7 transition-colors ${
            active
              ? "text-amber-300 bg-amber-400/15 hover:bg-amber-400/25 ring-1 ring-amber-400/40"
              : "text-muted-foreground hover:text-amber-300 hover:bg-amber-400/10"
          }`}
          onClick={() => onMegaphone(player)}
          data-testid={`roster-megaphone-btn-${player.id}`}
          aria-label={active ? "Remove from trade block" : "Add to trade block"}
        >
          <Megaphone className="h-3.5 w-3.5" />
        </Button>
      </TooltipTrigger>
      <TooltipContent>
        <p>{active ? "On trade block — click to remove" : "Add to trade block"}</p>
      </TooltipContent>
    </Tooltip>
  </TooltipProvider>
);

// Iter 144 — Shield button: toggles a player's keeper/expansion protection.
const ShieldButton = (props: any) => {
  const { player, active, draftType, onToggle } = props;
  const label = draftType === "keeper" ? "keeper" : "protection list";
  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            variant="ghost"
            size="icon"
            className={`h-7 w-7 transition-colors ${
              active
                ? "text-emerald-300 bg-emerald-400/15 hover:bg-emerald-400/25 ring-1 ring-emerald-400/40"
                : "text-muted-foreground hover:text-emerald-300 hover:bg-emerald-400/10"
            }`}
            onClick={() => onToggle(player)}
            data-testid={`roster-protect-btn-${player.id}`}
            aria-label={active ? `Remove from ${label}` : `Add to ${label}`}
          >
            <Shield className="h-3.5 w-3.5" />
          </Button>
        </TooltipTrigger>
        <TooltipContent>
          <p>
            {active
              ? `On ${label} — click to remove`
              : `Add to ${label}`}
          </p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
};

export const DropButton = ({ player, onDrop }: { player: Player; onDrop: (p: Player) => void }) => (
  <TooltipProvider>
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          className="h-7 w-7 text-muted-foreground hover:text-destructive hover:bg-destructive/10"
          onClick={() => onDrop(player)}
          data-testid={`roster-drop-btn-${player.id}`}
        >
          <MinusCircle className="h-3.5 w-3.5" />
        </Button>
      </TooltipTrigger>
      <TooltipContent><p>Drop Player</p></TooltipContent>
    </Tooltip>
  </TooltipProvider>
);

export const OwnershipCell = ({ player, ownership }: { player: Player; ownership?: any }) => {
  if (!ownership || ownership.league_pct == null) {
    return <td className="p-2 text-center text-[11px] text-muted-foreground" data-testid={`roster-own-cell-${player.id}`}>—</td>;
  }
  const pct = ownership.league_pct;
  const tone = pct >= 75 ? "text-emerald-300" : pct >= 25 ? "text-cyan-300" : "text-amber-300";
  return (
    <td className="p-2 text-center" data-testid={`roster-own-cell-${player.id}`}>
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <span className={`text-xs font-semibold cursor-help ${tone}`}>
              {pct}%
            </span>
          </TooltipTrigger>
          <TooltipContent side="top" className="text-[11px]">
            <div>{pct}% owned in league</div>
            {ownership.global_pct != null && (
              <div className="text-muted-foreground">
                {ownership.global_pct}% across DD
              </div>
            )}
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
    </td>
  );
};

