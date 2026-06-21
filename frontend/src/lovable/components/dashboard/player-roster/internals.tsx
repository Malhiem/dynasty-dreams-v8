// @ts-nocheck
/**
 * Iter 183 — Shared types, constants, helpers, and small leaf
 * components extracted from `PlayerRoster.tsx` so both the main
 * component AND its sub-components in `./sub-components.tsx`
 * can import from a single non-cyclic source. Re-exports from
 * `PlayerRoster.tsx` keep external consumers working.
 *
 * Living here:
 *   • Domain types: Player, RosterSection, RosterSlot,
 *     RosterSlotType, ViewFilter, IneligibilityInfo, HighlightProps,
 *     RosterConfigShape.
 *   • Module-level constants: slotEligibility, LEAGUE_ROSTER_SLOTS,
 *     sectionConfig, sectionOrder, rosterStatCategories,
 *     trackedCategories, untrackedCategories, allStatCategories,
 *     filterLabels, MINORS_MAX_AGE, MINORS_MAX_GAMES,
 *     POSITION_ACQUISITION_THRESHOLD, ALL_POSITIONS.
 *   • Pure helpers: buildLeagueRosterSlots, checkIneligibility,
 *     isPositionHighlighted, findHighlightedPlayer,
 *     shouldShowOpenSlotForSection.
 *   • Context: RosterConfigContext, useRosterConfig.
 *   • Small leaf components: TrendIndicator, PositionBadges,
 *     PositionButton.
 */
import { createContext, useContext } from "react";
import { TrendingUp, TrendingDown, Minus, Shield } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

// ── Types ──────────────────────────────────────────────

export interface Contract {
  salary: number;
  yearsRemaining: number;
  type: "RFA" | "UFA" | "ELC" | "Signed";
}

export interface PlayerGame {
  date: string;
  opponent: string;
  played: boolean;
  goals?: number;
  assists?: number;
  pts?: number;
}

export interface PlayerCategoryBreakdown {
  G: number;
  A: number;
  PPP: number;
  SHP: number;
  SOG: number;
  HIT: number;
  BLK: number;
  PIM: number;
  "+/-": number;
  FOW: number;
  FOL: number;
  [key: string]: number;
}

export interface PositionEligibility {
  position: string;
  gamesPlayed: number;
  acquired: boolean;
}

export interface Player {
  id: number;
  name: string;
  position: string;
  eligiblePositions: string[];
  secondaryPositions: PositionEligibility[];
  team: string;
  points: number;
  gamesPlayed: number;
  dynastyValue: number;
  trend: "up" | "down" | "stable";
  age: number;
  contract: Contract;
  rosterSection: RosterSection;
  rosterSlotId?: string;
  statsByPeriod: Record<string, number>;
  categoryBreakdown: PlayerCategoryBreakdown;
  matchupGames: number;
  schedule: PlayerGame[];
}

export type RosterSection = "starting" | "bench" | "ir" | "minors" | "goalies" | "goalies_minors";

export type ViewFilter =
  | "season"
  | "cap-hit"
  | "1d"
  | "7d"
  | "14d"
  | "30d"
  | "60d"
  | "100d"
  | "fantasy-points"
  | "matchup-schedule"
  | "full-schedule";

export type RosterSlotType = "C" | "LW" | "RW" | "W" | "F" | "D" | "SK" | "UTIL" | "G";

export interface RosterSlot {
  id: string;
  label: RosterSlotType;
  eligiblePositions: string[];
}

export interface IneligibilityInfo {
  isIneligible: boolean;
  reason: string;
}

export interface HighlightProps {
  highlightedPositions?: string[];
  highlightedPlayerId?: number | null;
  onMoveToSection?: (section: RosterSection) => void;
  sectionCounts?: Record<RosterSection, number>;
}

export type RosterConfigShape = {
  slots: RosterSlot[];
  sections: Record<RosterSection, { label: string; color: string; borderColor: string; maxSlots: number }>;
};

// ── Constants ──────────────────────────────────────────

export const POSITION_ACQUISITION_THRESHOLD = 20;
export const ALL_POSITIONS = ["C", "LW", "RW", "D", "G"];
export const MINORS_MAX_AGE = 23;
export const MINORS_MAX_GAMES = 40;

export const slotEligibility: Record<RosterSlotType, string[]> = {
  C: ["C"],
  LW: ["LW"],
  RW: ["RW"],
  W: ["LW", "RW"],
  F: ["C", "LW", "RW"],
  D: ["D"],
  SK: ["C", "LW", "RW", "D"],
  UTIL: ["C", "LW", "RW", "D", "G"],
  G: ["G"],
};

export const LEAGUE_ROSTER_SLOTS: RosterSlot[] = [
  { id: "C1", label: "C", eligiblePositions: slotEligibility.C },
  { id: "C2", label: "C", eligiblePositions: slotEligibility.C },
  { id: "LW1", label: "LW", eligiblePositions: slotEligibility.LW },
  { id: "RW1", label: "RW", eligiblePositions: slotEligibility.RW },
  { id: "W1", label: "W", eligiblePositions: slotEligibility.W },
  { id: "D1", label: "D", eligiblePositions: slotEligibility.D },
  { id: "UTIL1", label: "UTIL", eligiblePositions: slotEligibility.UTIL },
];

export const sectionConfig: Record<RosterSection, { label: string; color: string; borderColor: string; maxSlots: number }> = {
  starting: { label: "Starting Roster", color: "bg-primary/10", borderColor: "border-l-primary", maxSlots: LEAGUE_ROSTER_SLOTS.length },
  bench: { label: "Bench", color: "bg-accent/10", borderColor: "border-l-accent", maxSlots: 4 },
  ir: { label: "Injury Reserve", color: "bg-destructive/10", borderColor: "border-l-destructive", maxSlots: 3 },
  minors: { label: "Minors Pool", color: "bg-purple-500/10", borderColor: "border-l-purple-500", maxSlots: 5 },
  goalies: { label: "Goalies", color: "bg-teal-500/10", borderColor: "border-l-teal-500", maxSlots: 4 },
  goalies_minors: { label: "Goalies — Minors Pool", color: "bg-teal-500/5", borderColor: "border-l-teal-700", maxSlots: 5 },
};

export const sectionOrder: RosterSection[] = ["starting", "bench", "ir", "minors", "goalies", "goalies_minors"];

export const rosterStatCategories = ["G", "A", "SOG", "PPP", "SHP", "HIT", "BLK", "FOW", "FOL"];
export const trackedCategories = ["G", "A", "+/-", "PPP", "SHP", "SOG", "HIT", "BLK"];
export const untrackedCategories = ["PIM", "FOW", "FOL"];
export const allStatCategories = [...trackedCategories, ...untrackedCategories];

export const filterLabels: Record<ViewFilter, string> = {
  season: "Season Stats",
  "cap-hit": "Cap Hit",
  "1d": "Last 1 Day",
  "7d": "Last 7 Days",
  "14d": "Last 14 Days",
  "30d": "Last 30 Days",
  "60d": "Last 60 Days",
  "100d": "Last 100 Days",
  "fantasy-points": "Fantasy Points",
  "matchup-schedule": "Matchup Schedule",
  "full-schedule": "Full Schedule",
};

export const categoryLabels: Record<string, string> = {
  G: "Goals", A: "Assists", PPP: "Power Play Pts", SHP: "Shorthanded Pts",
  SOG: "Shots on Goal", HIT: "Hits", BLK: "Blocked Shots", PIM: "Penalty Min",
  "+/-": "Plus/Minus", FOW: "Faceoffs Won", FOL: "Faceoffs Lost",
};

// ── Pure helpers ──────────────────────────────────────

export const buildLeagueRosterSlots = (
  active: Record<string, number> | null | undefined,
): RosterSlot[] => {
  if (!active || Object.keys(active).length === 0) return LEAGUE_ROSTER_SLOTS;
  const ORDER: RosterSlotType[] = ["C", "LW", "RW", "W", "F", "SK", "D", "UTIL"];
  const slots: RosterSlot[] = [];
  for (const pos of ORDER) {
    const raw = active[pos];
    const count = typeof raw === "number"
      ? raw
      : (raw != null ? parseInt(String(raw), 10) || 0 : 0);
    for (let i = 0; i < count; i++) {
      slots.push({ id: `${pos}${i + 1}`, label: pos, eligiblePositions: slotEligibility[pos] || [pos] });
    }
  }
  return slots.length > 0 ? slots : LEAGUE_ROSTER_SLOTS;
};

export const checkIneligibility = (player: Player): IneligibilityInfo => {
  if (player.rosterSection === "ir") {
    const hasRecentStats = player.statsByPeriod["7d"] > 0 || player.statsByPeriod["1d"] > 0;
    if (hasRecentStats) return { isIneligible: true, reason: "Healthy player on Injury Reserve" };
  }
  if (player.rosterSection === "minors") {
    if (player.age > MINORS_MAX_AGE) {
      return { isIneligible: true, reason: `Player has aged out of minors eligibility (age ${player.age}, max ${MINORS_MAX_AGE})` };
    }
    const gamesPlayed = player.schedule.filter((g) => g.played).length;
    if (gamesPlayed > MINORS_MAX_GAMES) {
      return { isIneligible: true, reason: `Player has played out of minors eligibility (${gamesPlayed} games, max ${MINORS_MAX_GAMES})` };
    }
  }
  return { isIneligible: false, reason: "" };
};

export const isPositionHighlighted = (player: Player, highlightedPositions: string[], highlightedPlayerId: number | null): boolean => {
  if (!highlightedPlayerId) return false;
  if (player.id === highlightedPlayerId) return false;
  return highlightedPositions.includes(player.position);
};

export const findHighlightedPlayer = (grouped: Record<RosterSection, Player[]>, highlightedPlayerId: number | null): Player | null => {
  if (!highlightedPlayerId) return null;
  for (const section of sectionOrder) {
    const found = grouped[section].find((p) => p.id === highlightedPlayerId);
    if (found) return found;
  }
  return null;
};

export const shouldShowOpenSlotForSection = (
  section: RosterSection,
  highlightedPlayerId: number | null,
  onMoveToSection?: (section: RosterSection) => void,
  sectionCounts?: Record<RosterSection, number>,
  highlightedPlayer?: Player | null,
): boolean => {
  if (!highlightedPlayerId || !onMoveToSection || !sectionCounts) return false;
  if (section === "starting" || section === "minors") return false;
  if (sectionCounts[section] >= sectionConfig[section].maxSlots) return false;
  if (section === "ir" && highlightedPlayer) {
    const hasRecentStats = highlightedPlayer.statsByPeriod["7d"] > 0 || highlightedPlayer.statsByPeriod["1d"] > 0;
    if (hasRecentStats) return false;
  }
  return true;
};

// ── Roster Config Context (iter 180) ──────────────────

export const RosterConfigContext = createContext<RosterConfigShape | null>(null);
export const useRosterConfig = (): RosterConfigShape => {
  const ctx = useContext(RosterConfigContext);
  if (ctx) return ctx;
  return { slots: LEAGUE_ROSTER_SLOTS, sections: sectionConfig as any };
};

export const formatSalary = (salary: number) => `$${(salary / 1000000).toFixed(1)}M`;

export const getSlotPositionColor = (label: string) => {
  switch (label) {
    case "C": return "bg-primary/20 text-primary border-primary/30";
    case "LW":
    case "RW":
    case "W":
    case "F": return "bg-success/20 text-success border-success/30";
    case "D":
    case "SK": return "bg-accent/20 text-accent border-accent/30";
    case "G": return "bg-purple-500/20 text-purple-400 border-purple-500/30";
    case "UTIL": return "bg-amber-500/20 text-amber-400 border-amber-500/30";
    case "BEN": return "bg-secondary text-muted-foreground border-border";
    case "M": return "bg-purple-500/10 text-purple-400/70 border-purple-500/20";
    case "IR": return "bg-destructive/20 text-destructive border-destructive/30";
    default: return "bg-secondary text-secondary-foreground border-border";
  }
};

// Iter 185 — helpers used by PositionBadges + PositionButton. Both
// were duplicated inside PlayerRoster.tsx; consolidated here so the
// sub-components in `./sub-components.tsx` use the same (correct)
// implementations the parent file does.
export const getPositionColor = (position: string) => {
  switch (position) {
    case "C": return "bg-primary/20 text-primary border-primary/30";
    case "LW":
    case "RW": return "bg-success/20 text-success border-success/30";
    case "D": return "bg-accent/20 text-accent border-accent/30";
    case "G": return "bg-purple-500/20 text-purple-400 border-purple-500/30";
    default: return "bg-secondary text-secondary-foreground border-border";
  }
};

export const getSlotDisplayLabel = (player: Player): string => {
  if (player.rosterSection === "bench") return "BEN";
  if (player.rosterSection === "minors") return "M";
  if (player.rosterSection === "ir") return "IR";
  if (player.rosterSection === "starting" && player.rosterSlotId) {
    const slot = LEAGUE_ROSTER_SLOTS.find((s) => s.id === player.rosterSlotId);
    return slot?.label ?? player.position;
  }
  return player.position;
};

// ── Small leaf components ─────────────────────────────

export const TrendIndicator = ({ trend }: { trend: "up" | "down" | "stable" }) => {
  if (trend === "up") return <TrendingUp className="h-4 w-4 text-success mx-auto" />;
  if (trend === "down") return <TrendingDown className="h-4 w-4 text-destructive mx-auto" />;
  return <Minus className="h-4 w-4 text-muted-foreground mx-auto" />;
};

export const PositionBadges = ({ player }: { player: Player }) => {
  return (
    <div className="flex items-center gap-0.5 flex-wrap">
      {player.eligiblePositions.map((pos) => (
        <span
          key={pos}
          className={`text-[9px] font-bold px-1.5 py-0.5 rounded ${getPositionColor(pos)}`}
        >
          {pos}
        </span>
      ))}
      {player.secondaryPositions
        .filter((sp) => !sp.acquired)
        .map((sp) => (
          <TooltipProvider key={sp.position}>
            <Tooltip>
              <TooltipTrigger>
                <span className="text-[9px] font-medium px-1.5 py-0.5 rounded bg-muted/50 text-muted-foreground border border-dashed border-muted-foreground/30">
                  {sp.position}
                  <span className="ml-0.5 text-[8px]">({sp.gamesPlayed}/{POSITION_ACQUISITION_THRESHOLD})</span>
                </span>
              </TooltipTrigger>
              <TooltipContent>
                <p className="text-xs">{sp.gamesPlayed}/{POSITION_ACQUISITION_THRESHOLD} games at {sp.position} to acquire eligibility</p>
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        ))}
    </div>
  );
};

export const PositionButton = ({
  player,
  highlightedPlayerId,
  onToggleHighlight,
}: {
  player: Player;
  highlightedPlayerId: number | null;
  onToggleHighlight: (playerId: number) => void;
}) => {
  const isActive = highlightedPlayerId === player.id;
  const slotLabel = getSlotDisplayLabel(player);

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            onClick={() => onToggleHighlight(player.id)}
            className={`
              text-xs font-bold px-3 py-1.5 rounded-lg border transition-all cursor-pointer min-w-[40px]
              ${getSlotPositionColor(slotLabel)}
              ${isActive ? "ring-2 ring-primary ring-offset-1 ring-offset-card scale-110 shadow-lg" : "hover:scale-105"}
            `}
          >
            {slotLabel}
          </button>
        </TooltipTrigger>
        <TooltipContent>
          <p className="text-xs">{highlightedPlayerId && highlightedPlayerId !== player.id ? "Click to swap roster spots" : "Click to highlight & swap eligible positions"}</p>
          <p className="text-[10px] text-muted-foreground">Position: {player.position} · Eligible: {player.eligiblePositions.join(", ")}</p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
};
