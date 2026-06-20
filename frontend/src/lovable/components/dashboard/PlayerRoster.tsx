// @ts-nocheck
import { useState, useMemo, useCallback, useEffect, useRef, createContext, useContext } from "react";
import { useLocation } from "react-router-dom";
import { TrendingUp, TrendingDown, Minus, ArrowUpDown, ChevronLeft, ChevronRight, MinusCircle, MoveVertical, AlertTriangle, Save, Undo2, Settings, Megaphone, Shield } from "lucide-react";
import { NewsSignalIcon } from "@/lovable/components/NewsSignalIcon";
import { MinorEligibleBadge } from "@/lovable/components/MinorEligibleBadge";
import { toast } from "sonner";
import api from "@/lib/api";
import { useActiveLeague } from "@/hooks/use-active-league";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { PlayerTradeModal } from "@/lovable/components/trade/PlayerTradeModal";
import PlayerCardModal from "@/lovable/components/dashboard/PlayerCardModal";
import { ScrollArea, ScrollBar } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Checkbox } from "@/components/ui/checkbox";
import { Separator } from "@/components/ui/separator";
// Iter 183 — sub-components extracted to ./player-roster/sub-components.tsx
// We import them locally so the PlayerRoster component body's JSX can
// reference them by name. (The bottom of this file ALSO re-exports
// them so external consumers of PlayerRoster keep working.)
import { DailyGoaliePicker } from "./player-roster/DailyGoaliePicker";
import {
  StatsTable,
  CapHitTable,
  FantasyPointsTable,
  MatchupScheduleTable,
  FullScheduleTable,
  SectionGroup,
  EmptySlotRow,
  OpenSlotRow,
  PlayerRow,
  TradeButton,
  MegaphoneButton,
  DropButton,
  OwnershipCell,
} from "./player-roster/sub-components";
// Iter 183 — use the SAME RosterConfigContext that sub-components
// subscribe to (defined in internals.tsx) so the Provider in this
// file broadcasts to them. Without this both files would create
// distinct contexts and sub-tables would silently fall back to the
// static default 7-slot layout instead of the league's
// position_breakdown.active.
import { RosterConfigContext as SharedRosterConfigContext } from "./player-roster/internals";
// ── Types ──────────────────────────────────────────────

interface Contract {
  salary: number;
  yearsRemaining: number;
  type: "RFA" | "UFA" | "ELC" | "Signed";
}

interface PlayerGame {
  date: string;
  opponent: string;
  played: boolean;
  goals?: number;
  assists?: number;
  pts?: number;
}

interface PlayerCategoryBreakdown {
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

interface PositionEligibility {
  position: string;
  gamesPlayed: number;
  acquired: boolean; // true if >= threshold games played
}

export interface Player {
  id: number;
  name: string;
  position: string; // primary position
  eligiblePositions: string[]; // all positions currently eligible for
  secondaryPositions: PositionEligibility[]; // progress toward new positions
  team: string;
  points: number;
  gamesPlayed: number;
  dynastyValue: number;
  trend: "up" | "down" | "stable";
  age: number;
  contract: Contract;
  rosterSection: RosterSection;
  rosterSlotId?: string; // links to a LEAGUE_ROSTER_SLOTS id for starting players
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

// ── Position Eligibility Config ────────────────────────

export const POSITION_ACQUISITION_THRESHOLD = 20; // default games to acquire new position

export const ALL_POSITIONS = ["C", "LW", "RW", "D", "G"];

// ── League Manager Roster Slot Configuration ──────────
// These define the fixed starting roster positions and their order.
// Options: C, LW, RW, W (Wing), F (Forward), D, SK (Skater), UTIL (Utility), G
export type RosterSlotType = "C" | "LW" | "RW" | "W" | "F" | "D" | "SK" | "UTIL" | "G";

export interface RosterSlot {
  id: string;       // unique slot id e.g. "C1", "LW1"
  label: RosterSlotType; // display label
  eligiblePositions: string[]; // which player positions can fill this slot
}

// Map slot types to which player positions are eligible
export const slotEligibility: Record<RosterSlotType, string[]> = {
  C: ["C"],
  LW: ["LW"],
  RW: ["RW"],
  W: ["LW", "RW"],         // Wing = LW or RW
  F: ["C", "LW", "RW"],    // Forward = any forward
  D: ["D"],
  SK: ["C", "LW", "RW", "D"], // Skater = any skater
  UTIL: ["C", "LW", "RW", "D", "G"], // Utility = anyone
  G: ["G"],
};

// League manager configured starting roster slots (order matters)
// Iter 180 — DEFAULT shape only. Real leagues drive this from
// `league.position_breakdown.active` via the `LEAGUE_ROSTER_SLOTS`
// useMemo inside the PlayerRoster component (which shadows this
// constant). Used as a fallback when no league config is loaded.
export const LEAGUE_ROSTER_SLOTS: RosterSlot[] = [
  { id: "C1", label: "C", eligiblePositions: slotEligibility.C },
  { id: "C2", label: "C", eligiblePositions: slotEligibility.C },
  { id: "LW1", label: "LW", eligiblePositions: slotEligibility.LW },
  { id: "RW1", label: "RW", eligiblePositions: slotEligibility.RW },
  { id: "W1", label: "W", eligiblePositions: slotEligibility.W },
  { id: "D1", label: "D", eligiblePositions: slotEligibility.D },
  { id: "UTIL1", label: "UTIL", eligiblePositions: slotEligibility.UTIL },
  // Note: G slot intentionally omitted — goalies render in their dedicated
  // "Goalies" section below, not in the skater Starting Roster grid.
];

// Iter 180 — Build the dynamic starting-roster slot list from a
// league's `position_breakdown.active` config. Goalie slots are
// omitted (rendered in a dedicated section). Returns the default
// list when the breakdown is empty/unset so the team page still
// renders before the league config is loaded.
export const buildLeagueRosterSlots = (
  active: Record<string, number> | null | undefined,
): RosterSlot[] => {
  if (!active || Object.keys(active).length === 0) {
    return LEAGUE_ROSTER_SLOTS;
  }
  // Render slots in a stable, scannable order: C, LW, RW, W, F, SK, D, UTIL.
  // G is intentionally omitted (goalie section renders separately).
  const ORDER: RosterSlotType[] = ["C", "LW", "RW", "W", "F", "SK", "D", "UTIL"];
  const slots: RosterSlot[] = [];
  for (const pos of ORDER) {
    const raw = active[pos];
    const count = typeof raw === "number"
      ? raw
      : (raw != null ? parseInt(String(raw), 10) || 0 : 0);
    for (let i = 0; i < count; i++) {
      slots.push({
        id: `${pos}${i + 1}`,
        label: pos,
        eligiblePositions: slotEligibility[pos] || [pos],
      });
    }
  }
  // Empty breakdown after coercion — fall back to default
  return slots.length > 0 ? slots : LEAGUE_ROSTER_SLOTS;
};

// Iter 180 (fix) — React Context so the StatsTable, StatsTableSeason,
// StatsTableRange (etc.) sub-components — which live at module scope
// and therefore can't see the shadowed `LEAGUE_ROSTER_SLOTS` /
// `sectionConfig` inside PlayerRoster — still pick up the dynamic,
// league-driven values. The Provider lives at the top of
// PlayerRoster's render and broadcasts the memoized config. Falls
// back to module defaults when no Provider is mounted (for callers
// that render these tables standalone outside the dashboard).
export type RosterConfigShape = {
  slots: RosterSlot[];
  sections: Record<RosterSection, { label: string; color: string; borderColor: string; maxSlots: number }>;
};
export const RosterConfigContext = createContext<RosterConfigShape | null>(null);
export const useRosterConfig = (): RosterConfigShape => {
  const ctx = useContext(RosterConfigContext);
  if (ctx) return ctx;
  // Defaults — only hit when a sub-table is rendered outside the
  // PlayerRoster provider (rare). Keep behaviour identical to the
  // legacy hardcoded constants.
  return { slots: LEAGUE_ROSTER_SLOTS, sections: sectionConfig as any };
};

// ── Mock Data ──────────────────────────────────────────

const generateSchedule = (seed: number = 0): PlayerGame[] => {
  const teams = ["MTL", "BOS", "TBL", "FLA", "DET", "OTT", "BUF", "NYR", "NYI", "PIT", "WSH", "PHI", "CAR", "NJD", "CBJ"];
  const schedule: PlayerGame[] = [];
  const startDate = new Date(2025, 9, 8);
  for (let i = 0; i < 82; i++) {
    const gameDate = new Date(startDate);
    gameDate.setDate(gameDate.getDate() + Math.floor(i * 2.2));
    const isPast = gameDate < new Date();
    const s = seed + i;
    schedule.push({
      date: gameDate.toISOString().split("T")[0],
      opponent: teams[(i + seed) % teams.length],
      played: isPast,
      goals: isPast ? ((s * 7 + 3) % 3) : undefined,
      assists: isPast ? ((s * 13 + 5) % 4) : undefined,
      pts: isPast ? ((s * 11 + 2) % 5) : undefined,
    });
  }
  return schedule;
};

// Seeded pseudo-random for deterministic per-team rosters
const seededRand = (seed: number) => {
  let s = seed;
  return () => {
    s = (s * 1103515245 + 12345) & 0x7fffffff;
    return s / 0x7fffffff;
  };
};

const frostbitePlayers: Player[] = [
  { id: 1, name: "Connor McDavid", position: "C", eligiblePositions: ["C", "LW"], secondaryPositions: [{ position: "LW", gamesPlayed: 25, acquired: true }, { position: "RW", gamesPlayed: 8, acquired: false }], team: "EDM", points: 142, dynastyValue: 9800, trend: "up", age: 27, contract: { salary: 12500000, yearsRemaining: 4, type: "Signed" }, rosterSection: "starting", rosterSlotId: "C1", statsByPeriod: { season: 142, "1d": 4, "7d": 18, "14d": 32, "30d": 58, "60d": 98, "100d": 130 }, categoryBreakdown: { G: 42, A: 68, PPP: 38, SHP: 2, SOG: 285, HIT: 22, BLK: 15, PIM: 18, "+/-": 32, FOW: 812, FOL: 604 }, matchupGames: 4, schedule: generateSchedule(1) },
  { id: 2, name: "Nathan MacKinnon", position: "C", eligiblePositions: ["C"], secondaryPositions: [{ position: "LW", gamesPlayed: 12, acquired: false }, { position: "RW", gamesPlayed: 3, acquired: false }], team: "COL", points: 128, dynastyValue: 9200, trend: "stable", age: 28, contract: { salary: 12600000, yearsRemaining: 6, type: "Signed" }, rosterSection: "starting", rosterSlotId: "C2", statsByPeriod: { season: 128, "1d": 2, "7d": 14, "14d": 28, "30d": 52, "60d": 88, "100d": 118 }, categoryBreakdown: { G: 38, A: 62, PPP: 34, SHP: 4, SOG: 310, HIT: 30, BLK: 12, PIM: 22, "+/-": 28, FOW: 756, FOL: 580 }, matchupGames: 3, schedule: generateSchedule(2) },
  { id: 3, name: "Auston Matthews", position: "C", eligiblePositions: ["C", "RW"], secondaryPositions: [{ position: "RW", gamesPlayed: 22, acquired: true }, { position: "LW", gamesPlayed: 5, acquired: false }], team: "TOR", points: 115, dynastyValue: 8900, trend: "up", age: 26, contract: { salary: 13250000, yearsRemaining: 3, type: "UFA" }, rosterSection: "starting", rosterSlotId: "RW1", statsByPeriod: { season: 115, "1d": 5, "7d": 16, "14d": 30, "30d": 48, "60d": 82, "100d": 105 }, categoryBreakdown: { G: 52, A: 40, PPP: 28, SHP: 3, SOG: 340, HIT: 28, BLK: 8, PIM: 14, "+/-": 18, FOW: 890, FOL: 650 }, matchupGames: 4, schedule: generateSchedule(3) },
  { id: 4, name: "Nikita Kucherov", position: "RW", eligiblePositions: ["RW", "LW"], secondaryPositions: [{ position: "LW", gamesPlayed: 30, acquired: true }, { position: "C", gamesPlayed: 2, acquired: false }], team: "TBL", points: 124, dynastyValue: 8400, trend: "up", age: 30, contract: { salary: 9500000, yearsRemaining: 2, type: "UFA" }, rosterSection: "starting", rosterSlotId: "W1", statsByPeriod: { season: 124, "1d": 3, "7d": 15, "14d": 26, "30d": 50, "60d": 86, "100d": 112 }, categoryBreakdown: { G: 36, A: 60, PPP: 42, SHP: 1, SOG: 260, HIT: 18, BLK: 10, PIM: 12, "+/-": 24, FOW: 45, FOL: 38 }, matchupGames: 3, schedule: generateSchedule(4) },
  { id: 5, name: "Cale Makar", position: "D", eligiblePositions: ["D"], secondaryPositions: [], team: "COL", points: 89, dynastyValue: 9500, trend: "stable", age: 25, contract: { salary: 9000000, yearsRemaining: 5, type: "Signed" }, rosterSection: "starting", rosterSlotId: "D1", statsByPeriod: { season: 89, "1d": 2, "7d": 10, "14d": 18, "30d": 36, "60d": 62, "100d": 80 }, categoryBreakdown: { G: 18, A: 52, PPP: 30, SHP: 0, SOG: 220, HIT: 42, BLK: 88, PIM: 16, "+/-": 30, FOW: 0, FOL: 0 }, matchupGames: 3, schedule: generateSchedule(5) },
  { id: 6, name: "Igor Shesterkin", position: "G", eligiblePositions: ["G"], secondaryPositions: [], team: "NYR", points: 76, dynastyValue: 7200, trend: "down", age: 28, contract: { salary: 5666667, yearsRemaining: 1, type: "UFA" }, rosterSection: "starting", rosterSlotId: "G1", statsByPeriod: { season: 76, "1d": 0, "7d": 8, "14d": 14, "30d": 30, "60d": 52, "100d": 68 }, categoryBreakdown: { G: 0, A: 2, PPP: 0, SHP: 0, SOG: 0, HIT: 0, BLK: 0, PIM: 0, "+/-": 0, FOW: 0, FOL: 0 }, matchupGames: 2, schedule: generateSchedule(6) },
  { id: 12, name: "Brad Marchand", position: "LW", eligiblePositions: ["LW", "C"], secondaryPositions: [{ position: "C", gamesPlayed: 18, acquired: false }], team: "BOS", points: 85, dynastyValue: 5800, trend: "stable", age: 36, contract: { salary: 6125000, yearsRemaining: 2, type: "UFA" }, rosterSection: "starting", rosterSlotId: "LW1", statsByPeriod: { season: 85, "1d": 1, "7d": 10, "14d": 18, "30d": 34, "60d": 58, "100d": 76 }, categoryBreakdown: { G: 24, A: 38, PPP: 18, SHP: 3, SOG: 195, HIT: 65, BLK: 12, PIM: 48, "+/-": 12, FOW: 180, FOL: 140 }, matchupGames: 3, schedule: generateSchedule(12) },
  { id: 13, name: "Quinn Hughes", position: "D", eligiblePositions: ["D"], secondaryPositions: [], team: "VAN", points: 78, dynastyValue: 7600, trend: "up", age: 24, contract: { salary: 7850000, yearsRemaining: 4, type: "Signed" }, rosterSection: "starting", rosterSlotId: "UTIL1", statsByPeriod: { season: 78, "1d": 2, "7d": 9, "14d": 16, "30d": 32, "60d": 54, "100d": 70 }, categoryBreakdown: { G: 12, A: 48, PPP: 26, SHP: 0, SOG: 180, HIT: 28, BLK: 72, PIM: 10, "+/-": 22, FOW: 0, FOL: 0 }, matchupGames: 3, schedule: generateSchedule(13) },
  { id: 7, name: "Mitch Marner", position: "RW", eligiblePositions: ["RW", "LW", "C"], secondaryPositions: [{ position: "LW", gamesPlayed: 28, acquired: true }, { position: "C", gamesPlayed: 21, acquired: true }], team: "TOR", points: 98, dynastyValue: 7800, trend: "stable", age: 27, contract: { salary: 10903000, yearsRemaining: 1, type: "UFA" }, rosterSection: "bench", statsByPeriod: { season: 98, "1d": 1, "7d": 12, "14d": 22, "30d": 40, "60d": 68, "100d": 88 }, categoryBreakdown: { G: 22, A: 58, PPP: 28, SHP: 2, SOG: 180, HIT: 15, BLK: 6, PIM: 8, "+/-": 14, FOW: 32, FOL: 28 }, matchupGames: 4, schedule: generateSchedule(7) },
  { id: 8, name: "Brady Tkachuk", position: "LW", eligiblePositions: ["LW", "RW"], secondaryPositions: [{ position: "RW", gamesPlayed: 20, acquired: true }, { position: "C", gamesPlayed: 6, acquired: false }], team: "OTT", points: 72, dynastyValue: 7100, trend: "up", age: 25, contract: { salary: 8214286, yearsRemaining: 5, type: "Signed" }, rosterSection: "bench", statsByPeriod: { season: 72, "1d": 3, "7d": 9, "14d": 16, "30d": 30, "60d": 50, "100d": 65 }, categoryBreakdown: { G: 28, A: 30, PPP: 16, SHP: 1, SOG: 240, HIT: 180, BLK: 22, PIM: 92, "+/-": 8, FOW: 120, FOL: 95 }, matchupGames: 3, schedule: generateSchedule(8) },
  { id: 9, name: "Aleksander Barkov", position: "C", eligiblePositions: ["C", "LW"], secondaryPositions: [{ position: "LW", gamesPlayed: 24, acquired: true }, { position: "RW", gamesPlayed: 10, acquired: false }], team: "FLA", points: 0, dynastyValue: 6500, trend: "down", age: 29, contract: { salary: 10000000, yearsRemaining: 6, type: "Signed" }, rosterSection: "ir", statsByPeriod: { season: 0, "1d": 0, "7d": 0, "14d": 0, "30d": 0, "60d": 0, "100d": 0 }, categoryBreakdown: { G: 0, A: 0, PPP: 0, SHP: 0, SOG: 0, HIT: 0, BLK: 0, PIM: 0, "+/-": 0, FOW: 0, FOL: 0 }, matchupGames: 0, schedule: generateSchedule(9) },
  { id: 10, name: "Connor Bedard", position: "C", eligiblePositions: ["C"], secondaryPositions: [{ position: "RW", gamesPlayed: 14, acquired: false }, { position: "LW", gamesPlayed: 4, acquired: false }], team: "CHI", points: 52, dynastyValue: 8800, trend: "up", age: 19, contract: { salary: 950000, yearsRemaining: 2, type: "ELC" }, rosterSection: "minors", statsByPeriod: { season: 52, "1d": 2, "7d": 8, "14d": 14, "30d": 24, "60d": 38, "100d": 48 }, categoryBreakdown: { G: 18, A: 24, PPP: 12, SHP: 0, SOG: 160, HIT: 10, BLK: 4, PIM: 6, "+/-": 4, FOW: 340, FOL: 310 }, matchupGames: 4, schedule: generateSchedule(10) },
  { id: 11, name: "Macklin Celebrini", position: "C", eligiblePositions: ["C"], secondaryPositions: [{ position: "LW", gamesPlayed: 7, acquired: false }], team: "SJS", points: 38, dynastyValue: 8200, trend: "up", age: 18, contract: { salary: 950000, yearsRemaining: 3, type: "ELC" }, rosterSection: "minors", statsByPeriod: { season: 38, "1d": 1, "7d": 6, "14d": 10, "30d": 18, "60d": 28, "100d": 35 }, categoryBreakdown: { G: 14, A: 16, PPP: 8, SHP: 1, SOG: 130, HIT: 8, BLK: 3, PIM: 4, "+/-": 2, FOW: 280, FOL: 260 }, matchupGames: 3, schedule: generateSchedule(11) },
];

// Pool of NHL players to create unique rosters per team
const playerPool: Omit<Player, "id" | "rosterSection" | "rosterSlotId" | "schedule">[] = [
  { name: "Leon Draisaitl", position: "C", eligiblePositions: ["C", "LW"], secondaryPositions: [{ position: "LW", gamesPlayed: 22, acquired: true }], team: "EDM", points: 135, dynastyValue: 9400, trend: "up", age: 28, contract: { salary: 8500000, yearsRemaining: 1, type: "UFA" }, statsByPeriod: { season: 135, "1d": 3, "7d": 16, "14d": 30, "30d": 55, "60d": 92, "100d": 122 }, categoryBreakdown: { G: 48, A: 58, PPP: 36, SHP: 2, SOG: 295, HIT: 35, BLK: 18, PIM: 24, "+/-": 26, FOW: 780, FOL: 590 }, matchupGames: 4 },
  { name: "David Pastrnak", position: "RW", eligiblePositions: ["RW"], secondaryPositions: [{ position: "LW", gamesPlayed: 8, acquired: false }], team: "BOS", points: 118, dynastyValue: 8600, trend: "up", age: 27, contract: { salary: 11250000, yearsRemaining: 7, type: "Signed" }, statsByPeriod: { season: 118, "1d": 4, "7d": 14, "14d": 26, "30d": 48, "60d": 80, "100d": 108 }, categoryBreakdown: { G: 44, A: 48, PPP: 32, SHP: 1, SOG: 330, HIT: 20, BLK: 8, PIM: 16, "+/-": 20, FOW: 10, FOL: 8 }, matchupGames: 3 },
  { name: "Kirill Kaprizov", position: "LW", eligiblePositions: ["LW", "RW"], secondaryPositions: [{ position: "RW", gamesPlayed: 25, acquired: true }], team: "MIN", points: 112, dynastyValue: 8800, trend: "up", age: 27, contract: { salary: 9000000, yearsRemaining: 3, type: "Signed" }, statsByPeriod: { season: 112, "1d": 2, "7d": 13, "14d": 24, "30d": 46, "60d": 76, "100d": 102 }, categoryBreakdown: { G: 40, A: 46, PPP: 28, SHP: 2, SOG: 300, HIT: 32, BLK: 10, PIM: 20, "+/-": 18, FOW: 25, FOL: 20 }, matchupGames: 4 },
  { name: "Jack Hughes", position: "C", eligiblePositions: ["C"], secondaryPositions: [{ position: "LW", gamesPlayed: 10, acquired: false }], team: "NJD", points: 105, dynastyValue: 8500, trend: "up", age: 23, contract: { salary: 8000000, yearsRemaining: 6, type: "Signed" }, statsByPeriod: { season: 105, "1d": 3, "7d": 12, "14d": 22, "30d": 42, "60d": 72, "100d": 95 }, categoryBreakdown: { G: 32, A: 50, PPP: 24, SHP: 1, SOG: 260, HIT: 18, BLK: 6, PIM: 12, "+/-": 14, FOW: 620, FOL: 480 }, matchupGames: 3 },
  { name: "Mikko Rantanen", position: "RW", eligiblePositions: ["RW", "LW"], secondaryPositions: [{ position: "LW", gamesPlayed: 30, acquired: true }], team: "COL", points: 110, dynastyValue: 7900, trend: "stable", age: 27, contract: { salary: 9250000, yearsRemaining: 4, type: "Signed" }, statsByPeriod: { season: 110, "1d": 2, "7d": 13, "14d": 24, "30d": 44, "60d": 74, "100d": 100 }, categoryBreakdown: { G: 36, A: 48, PPP: 30, SHP: 0, SOG: 280, HIT: 40, BLK: 14, PIM: 18, "+/-": 22, FOW: 15, FOL: 12 }, matchupGames: 3 },
  { name: "Sebastian Aho", position: "C", eligiblePositions: ["C", "LW"], secondaryPositions: [{ position: "LW", gamesPlayed: 20, acquired: true }], team: "CAR", points: 95, dynastyValue: 7600, trend: "stable", age: 27, contract: { salary: 8460000, yearsRemaining: 5, type: "Signed" }, statsByPeriod: { season: 95, "1d": 1, "7d": 11, "14d": 20, "30d": 38, "60d": 64, "100d": 85 }, categoryBreakdown: { G: 30, A: 42, PPP: 22, SHP: 3, SOG: 250, HIT: 28, BLK: 10, PIM: 14, "+/-": 16, FOW: 700, FOL: 540 }, matchupGames: 3 },
  { name: "Timo Meier", position: "LW", eligiblePositions: ["LW", "RW"], secondaryPositions: [{ position: "RW", gamesPlayed: 18, acquired: false }], team: "NJD", points: 82, dynastyValue: 6800, trend: "down", age: 27, contract: { salary: 8800000, yearsRemaining: 6, type: "Signed" }, statsByPeriod: { season: 82, "1d": 1, "7d": 9, "14d": 16, "30d": 32, "60d": 56, "100d": 74 }, categoryBreakdown: { G: 28, A: 32, PPP: 18, SHP: 1, SOG: 240, HIT: 120, BLK: 18, PIM: 42, "+/-": 6, FOW: 8, FOL: 6 }, matchupGames: 4 },
  { name: "Rasmus Dahlin", position: "D", eligiblePositions: ["D"], secondaryPositions: [], team: "BUF", points: 72, dynastyValue: 7800, trend: "up", age: 24, contract: { salary: 10900000, yearsRemaining: 7, type: "Signed" }, statsByPeriod: { season: 72, "1d": 1, "7d": 8, "14d": 14, "30d": 28, "60d": 50, "100d": 65 }, categoryBreakdown: { G: 14, A: 42, PPP: 22, SHP: 0, SOG: 190, HIT: 38, BLK: 78, PIM: 14, "+/-": 8, FOW: 0, FOL: 0 }, matchupGames: 3 },
  { name: "Adam Fox", position: "D", eligiblePositions: ["D"], secondaryPositions: [], team: "NYR", points: 80, dynastyValue: 8200, trend: "stable", age: 26, contract: { salary: 9500000, yearsRemaining: 5, type: "Signed" }, statsByPeriod: { season: 80, "1d": 2, "7d": 9, "14d": 16, "30d": 32, "60d": 56, "100d": 72 }, categoryBreakdown: { G: 10, A: 54, PPP: 28, SHP: 0, SOG: 170, HIT: 24, BLK: 82, PIM: 12, "+/-": 20, FOW: 0, FOL: 0 }, matchupGames: 4 },
  { name: "Andrei Vasilevskiy", position: "G", eligiblePositions: ["G"], secondaryPositions: [], team: "TBL", points: 70, dynastyValue: 6800, trend: "stable", age: 30, contract: { salary: 9500000, yearsRemaining: 4, type: "Signed" }, statsByPeriod: { season: 70, "1d": 0, "7d": 7, "14d": 12, "30d": 28, "60d": 48, "100d": 62 }, categoryBreakdown: { G: 0, A: 1, PPP: 0, SHP: 0, SOG: 0, HIT: 0, BLK: 0, PIM: 2, "+/-": 0, FOW: 0, FOL: 0 }, matchupGames: 2 },
  { name: "Miro Heiskanen", position: "D", eligiblePositions: ["D"], secondaryPositions: [], team: "DAL", points: 74, dynastyValue: 8000, trend: "up", age: 25, contract: { salary: 8450000, yearsRemaining: 6, type: "Signed" }, statsByPeriod: { season: 74, "1d": 1, "7d": 8, "14d": 14, "30d": 30, "60d": 52, "100d": 66 }, categoryBreakdown: { G: 12, A: 44, PPP: 20, SHP: 1, SOG: 180, HIT: 36, BLK: 92, PIM: 10, "+/-": 24, FOW: 0, FOL: 0 }, matchupGames: 3 },
  { name: "Tim Stützle", position: "C", eligiblePositions: ["C", "LW"], secondaryPositions: [{ position: "LW", gamesPlayed: 22, acquired: true }], team: "OTT", points: 88, dynastyValue: 7400, trend: "up", age: 22, contract: { salary: 8350000, yearsRemaining: 7, type: "Signed" }, statsByPeriod: { season: 88, "1d": 2, "7d": 10, "14d": 18, "30d": 36, "60d": 60, "100d": 78 }, categoryBreakdown: { G: 26, A: 40, PPP: 20, SHP: 1, SOG: 220, HIT: 22, BLK: 8, PIM: 16, "+/-": 10, FOW: 580, FOL: 460 }, matchupGames: 4 },
  { name: "Jake Oettinger", position: "G", eligiblePositions: ["G"], secondaryPositions: [], team: "DAL", points: 65, dynastyValue: 6200, trend: "up", age: 25, contract: { salary: 4000000, yearsRemaining: 2, type: "RFA" }, statsByPeriod: { season: 65, "1d": 0, "7d": 6, "14d": 12, "30d": 26, "60d": 44, "100d": 58 }, categoryBreakdown: { G: 0, A: 1, PPP: 0, SHP: 0, SOG: 0, HIT: 0, BLK: 0, PIM: 0, "+/-": 0, FOW: 0, FOL: 0 }, matchupGames: 3 },
  { name: "Trevor Zegras", position: "C", eligiblePositions: ["C", "LW"], secondaryPositions: [{ position: "LW", gamesPlayed: 15, acquired: false }], team: "ANA", points: 58, dynastyValue: 6000, trend: "down", age: 23, contract: { salary: 5750000, yearsRemaining: 2, type: "RFA" }, statsByPeriod: { season: 58, "1d": 1, "7d": 7, "14d": 12, "30d": 24, "60d": 40, "100d": 52 }, categoryBreakdown: { G: 18, A: 28, PPP: 14, SHP: 0, SOG: 180, HIT: 14, BLK: 4, PIM: 10, "+/-": -4, FOW: 420, FOL: 380 }, matchupGames: 3 },
  { name: "Moritz Seider", position: "D", eligiblePositions: ["D"], secondaryPositions: [], team: "DET", points: 62, dynastyValue: 7200, trend: "up", age: 23, contract: { salary: 7875000, yearsRemaining: 6, type: "Signed" }, statsByPeriod: { season: 62, "1d": 1, "7d": 7, "14d": 12, "30d": 24, "60d": 42, "100d": 56 }, categoryBreakdown: { G: 8, A: 36, PPP: 14, SHP: 1, SOG: 160, HIT: 140, BLK: 120, PIM: 28, "+/-": 6, FOW: 0, FOL: 0 }, matchupGames: 4 },
  { name: "Juuse Saros", position: "G", eligiblePositions: ["G"], secondaryPositions: [], team: "NSH", points: 68, dynastyValue: 6400, trend: "stable", age: 29, contract: { salary: 5000000, yearsRemaining: 2, type: "UFA" }, statsByPeriod: { season: 68, "1d": 0, "7d": 7, "14d": 12, "30d": 26, "60d": 46, "100d": 60 }, categoryBreakdown: { G: 0, A: 2, PPP: 0, SHP: 0, SOG: 0, HIT: 0, BLK: 0, PIM: 2, "+/-": 0, FOW: 0, FOL: 0 }, matchupGames: 2 },
  { name: "Matthew Tkachuk", position: "LW", eligiblePositions: ["LW", "RW"], secondaryPositions: [{ position: "RW", gamesPlayed: 26, acquired: true }], team: "FLA", points: 102, dynastyValue: 8100, trend: "up", age: 26, contract: { salary: 9500000, yearsRemaining: 6, type: "Signed" }, statsByPeriod: { season: 102, "1d": 2, "7d": 12, "14d": 22, "30d": 42, "60d": 70, "100d": 92 }, categoryBreakdown: { G: 30, A: 48, PPP: 24, SHP: 2, SOG: 260, HIT: 160, BLK: 20, PIM: 88, "+/-": 16, FOW: 40, FOL: 32 }, matchupGames: 3 },
  { name: "Jason Robertson", position: "LW", eligiblePositions: ["LW"], secondaryPositions: [{ position: "RW", gamesPlayed: 6, acquired: false }], team: "DAL", points: 96, dynastyValue: 7500, trend: "stable", age: 25, contract: { salary: 7750000, yearsRemaining: 3, type: "Signed" }, statsByPeriod: { season: 96, "1d": 2, "7d": 11, "14d": 20, "30d": 38, "60d": 66, "100d": 86 }, categoryBreakdown: { G: 34, A: 40, PPP: 22, SHP: 1, SOG: 270, HIT: 24, BLK: 8, PIM: 12, "+/-": 14, FOW: 12, FOL: 10 }, matchupGames: 4 },
  { name: "Elias Pettersson", position: "C", eligiblePositions: ["C"], secondaryPositions: [{ position: "LW", gamesPlayed: 12, acquired: false }], team: "VAN", points: 90, dynastyValue: 7800, trend: "down", age: 25, contract: { salary: 11600000, yearsRemaining: 7, type: "Signed" }, statsByPeriod: { season: 90, "1d": 1, "7d": 10, "14d": 18, "30d": 36, "60d": 62, "100d": 80 }, categoryBreakdown: { G: 28, A: 42, PPP: 22, SHP: 2, SOG: 230, HIT: 16, BLK: 6, PIM: 14, "+/-": 10, FOW: 680, FOL: 520 }, matchupGames: 3 },
  { name: "Zach Werenski", position: "D", eligiblePositions: ["D"], secondaryPositions: [], team: "CBJ", points: 70, dynastyValue: 7000, trend: "up", age: 27, contract: { salary: 9583000, yearsRemaining: 5, type: "Signed" }, statsByPeriod: { season: 70, "1d": 1, "7d": 8, "14d": 14, "30d": 28, "60d": 48, "100d": 62 }, categoryBreakdown: { G: 16, A: 38, PPP: 20, SHP: 0, SOG: 200, HIT: 30, BLK: 70, PIM: 18, "+/-": 2, FOW: 0, FOL: 0 }, matchupGames: 3 },
  { name: "Wyatt Johnston", position: "C", eligiblePositions: ["C"], secondaryPositions: [{ position: "RW", gamesPlayed: 8, acquired: false }], team: "DAL", points: 72, dynastyValue: 7200, trend: "up", age: 21, contract: { salary: 925000, yearsRemaining: 1, type: "ELC" }, statsByPeriod: { season: 72, "1d": 2, "7d": 8, "14d": 14, "30d": 28, "60d": 50, "100d": 64 }, categoryBreakdown: { G: 24, A: 32, PPP: 14, SHP: 1, SOG: 200, HIT: 26, BLK: 10, PIM: 10, "+/-": 12, FOW: 540, FOL: 420 }, matchupGames: 4 },
  { name: "Luke Hughes", position: "D", eligiblePositions: ["D"], secondaryPositions: [], team: "NJD", points: 58, dynastyValue: 7400, trend: "up", age: 21, contract: { salary: 925000, yearsRemaining: 1, type: "ELC" }, statsByPeriod: { season: 58, "1d": 1, "7d": 6, "14d": 12, "30d": 22, "60d": 40, "100d": 52 }, categoryBreakdown: { G: 10, A: 32, PPP: 14, SHP: 0, SOG: 160, HIT: 44, BLK: 68, PIM: 12, "+/-": 8, FOW: 0, FOL: 0 }, matchupGames: 3 },
  { name: "Alexandar Georgiev", position: "G", eligiblePositions: ["G"], secondaryPositions: [], team: "COL", points: 55, dynastyValue: 4800, trend: "down", age: 28, contract: { salary: 3400000, yearsRemaining: 2, type: "UFA" }, statsByPeriod: { season: 55, "1d": 0, "7d": 5, "14d": 10, "30d": 22, "60d": 38, "100d": 48 }, categoryBreakdown: { G: 0, A: 0, PPP: 0, SHP: 0, SOG: 0, HIT: 0, BLK: 0, PIM: 2, "+/-": 0, FOW: 0, FOL: 0 }, matchupGames: 2 },
  { name: "Cole Caufield", position: "RW", eligiblePositions: ["RW"], secondaryPositions: [{ position: "LW", gamesPlayed: 4, acquired: false }], team: "MTL", points: 85, dynastyValue: 7000, trend: "up", age: 23, contract: { salary: 7850000, yearsRemaining: 7, type: "Signed" }, statsByPeriod: { season: 85, "1d": 2, "7d": 10, "14d": 18, "30d": 34, "60d": 58, "100d": 76 }, categoryBreakdown: { G: 36, A: 28, PPP: 20, SHP: 1, SOG: 290, HIT: 12, BLK: 4, PIM: 8, "+/-": 8, FOW: 6, FOL: 4 }, matchupGames: 4 },
  { name: "Brock Boeser", position: "RW", eligiblePositions: ["RW"], secondaryPositions: [], team: "VAN", points: 78, dynastyValue: 5600, trend: "stable", age: 27, contract: { salary: 6650000, yearsRemaining: 3, type: "Signed" }, statsByPeriod: { season: 78, "1d": 1, "7d": 9, "14d": 16, "30d": 32, "60d": 54, "100d": 70 }, categoryBreakdown: { G: 30, A: 30, PPP: 18, SHP: 0, SOG: 250, HIT: 20, BLK: 6, PIM: 10, "+/-": 6, FOW: 4, FOL: 3 }, matchupGames: 3 },
  { name: "Logan Cooley", position: "C", eligiblePositions: ["C"], secondaryPositions: [{ position: "LW", gamesPlayed: 5, acquired: false }], team: "ARI", points: 48, dynastyValue: 7600, trend: "up", age: 20, contract: { salary: 925000, yearsRemaining: 2, type: "ELC" }, statsByPeriod: { season: 48, "1d": 1, "7d": 6, "14d": 10, "30d": 20, "60d": 34, "100d": 44 }, categoryBreakdown: { G: 14, A: 22, PPP: 10, SHP: 0, SOG: 150, HIT: 16, BLK: 4, PIM: 8, "+/-": 0, FOW: 380, FOL: 340 }, matchupGames: 3 },
  { name: "Lane Hutson", position: "D", eligiblePositions: ["D"], secondaryPositions: [], team: "MTL", points: 42, dynastyValue: 7000, trend: "up", age: 20, contract: { salary: 925000, yearsRemaining: 2, type: "ELC" }, statsByPeriod: { season: 42, "1d": 1, "7d": 5, "14d": 8, "30d": 16, "60d": 28, "100d": 38 }, categoryBreakdown: { G: 6, A: 26, PPP: 12, SHP: 0, SOG: 120, HIT: 18, BLK: 52, PIM: 6, "+/-": 4, FOW: 0, FOL: 0 }, matchupGames: 4 },
];

const slotLabels = LEAGUE_ROSTER_SLOTS.map(s => s.label);

const generateTeamRoster = (teamId: string, seed: number): Player[] => {
  if (teamId === "frostbite") return frostbitePlayers;

  const rand = seededRand(seed);
  const poolCopy = [...playerPool].sort(() => rand() - 0.5);
  const selected = poolCopy.slice(0, 13);
  const trends: Array<"up" | "down" | "stable"> = ["up", "down", "stable"];

  // Assign to roster sections and slots
  const players: Player[] = selected.map((p, i) => {
    const id = seed * 100 + i + 100;
    let rosterSection: RosterSection;
    let rosterSlotId: string | undefined;

    if (i < LEAGUE_ROSTER_SLOTS.length) {
      rosterSection = "starting";
      rosterSlotId = LEAGUE_ROSTER_SLOTS[i].id;
    } else if (i < LEAGUE_ROSTER_SLOTS.length + 2) {
      rosterSection = "bench";
    } else if (i < LEAGUE_ROSTER_SLOTS.length + 3) {
      rosterSection = "ir";
      // Make IR player have 0 stats so they're eligible
      return {
        ...p,
        id,
        rosterSection: "ir" as RosterSection,
        rosterSlotId: undefined,
        schedule: generateSchedule(id),
        points: 0,
        statsByPeriod: { season: 0, "1d": 0, "7d": 0, "14d": 0, "30d": 0, "60d": 0, "100d": 0 },
        categoryBreakdown: { G: 0, A: 0, PPP: 0, SHP: 0, SOG: 0, HIT: 0, BLK: 0, PIM: 0, "+/-": 0, FOW: 0, FOL: 0 },
        matchupGames: 0,
        trend: "down" as const,
      };
    } else {
      rosterSection = "minors";
    }

    // Slightly vary stats with seed
    const mult = 0.8 + rand() * 0.4;
    return {
      ...p,
      id,
      rosterSection,
      rosterSlotId,
      schedule: generateSchedule(id),
      points: Math.round(p.points * mult),
      dynastyValue: Math.round(p.dynastyValue * mult),
      trend: trends[Math.floor(rand() * 3)],
    };
  });

  return players;
};

// Mock weekly matchup data
interface WeekMatchup {
  week: number;
  opponent: string;
  opponentFull: string;
  score: { mine: number; theirs: number };
  result: "W" | "L";
}

const weeklyMatchups: WeekMatchup[] = [
  { week: 1, opponent: "ICE", opponentFull: "Ice Dragons", score: { mine: 412, theirs: 388 }, result: "W" },
  { week: 2, opponent: "BLZ", opponentFull: "Blazers", score: { mine: 380, theirs: 395 }, result: "L" },
  { week: 3, opponent: "THU", opponentFull: "Thunder", score: { mine: 425, theirs: 410 }, result: "W" },
  { week: 4, opponent: "WLV", opponentFull: "Wolverines", score: { mine: 398, theirs: 372 }, result: "W" },
  { week: 5, opponent: "PHX", opponentFull: "Phoenix", score: { mine: 445, theirs: 420 }, result: "W" },
  { week: 6, opponent: "STM", opponentFull: "Storm Chasers", score: { mine: 390, theirs: 402 }, result: "L" },
  { week: 7, opponent: "VPR", opponentFull: "Vipers", score: { mine: 0, theirs: 0 }, result: "W" },
];

const currentWeek = 7;

// ── Helpers ────────────────────────────────────────────

const formatSalary = (salary: number) => `$${(salary / 1000000).toFixed(1)}M`;

const getContractTypeColor = (type: Contract["type"]) => {
  switch (type) {
    case "ELC": return "bg-success/20 text-success";
    case "RFA": return "bg-accent/20 text-accent";
    case "UFA": return "bg-destructive/20 text-destructive";
    case "Signed": return "bg-primary/20 text-primary";
    default: return "bg-secondary text-secondary-foreground";
  }
};

const getPositionColor = (position: string) => {
  switch (position) {
    case "C": return "bg-primary/20 text-primary border-primary/30";
    case "LW":
    case "RW": return "bg-success/20 text-success border-success/30";
    case "D": return "bg-accent/20 text-accent border-accent/30";
    case "G": return "bg-purple-500/20 text-purple-400 border-purple-500/30";
    default: return "bg-secondary text-secondary-foreground border-border";
  }
};

const TrendIndicator = ({ trend }: { trend: "up" | "down" | "stable" }) => {
  if (trend === "up") return <TrendingUp className="h-4 w-4 text-success mx-auto" />;
  if (trend === "down") return <TrendingDown className="h-4 w-4 text-destructive mx-auto" />;
  return <Minus className="h-4 w-4 text-muted-foreground mx-auto" />;
};

export const sectionConfig: Record<RosterSection, { label: string; color: string; borderColor: string; maxSlots: number }> = {
  starting: { label: "Starting Roster", color: "bg-primary/10", borderColor: "border-l-primary", maxSlots: LEAGUE_ROSTER_SLOTS.length },
  bench: { label: "Bench", color: "bg-accent/10", borderColor: "border-l-accent", maxSlots: 4 },
  ir: { label: "Injury Reserve", color: "bg-destructive/10", borderColor: "border-l-destructive", maxSlots: 3 },
  minors: { label: "Minors Pool", color: "bg-purple-500/10", borderColor: "border-l-purple-500", maxSlots: 5 },
  goalies: { label: "Goalies", color: "bg-teal-500/10", borderColor: "border-l-teal-500", maxSlots: 4 },
  // Goalies minors max defaults to the same value as the skater minors pool
  // unless the league commissioner configures `goalies_minors_slots` separately
  // (see useLeagueRosterConfig — overrides applied at runtime via mergedSectionConfig).
  goalies_minors: { label: "Goalies — Minors Pool", color: "bg-teal-500/5", borderColor: "border-l-teal-700", maxSlots: 5 },
};

// ── Ineligibility Checks ──────────────────────────────
const MINORS_MAX_AGE = 23;
const MINORS_MAX_GAMES = 40; // games played in season before losing minors eligibility

export interface IneligibilityInfo {
  isIneligible: boolean;
  reason: string;
}

export const checkIneligibility = (player: Player): IneligibilityInfo => {
  if (player.rosterSection === "ir") {
    // Healthy player on IR — if they have recent stats, they're healthy
    const hasRecentStats = player.statsByPeriod["7d"] > 0 || player.statsByPeriod["1d"] > 0;
    if (hasRecentStats) {
      return { isIneligible: true, reason: `Healthy player on Injury Reserve` };
    }
  }
  if (player.rosterSection === "minors") {
    if (player.age > MINORS_MAX_AGE) {
      return { isIneligible: true, reason: `Player has aged out of minors eligibility (age ${player.age}, max ${MINORS_MAX_AGE})` };
    }
    // Check games played threshold
    const gamesPlayed = player.schedule.filter(g => g.played).length;
    if (gamesPlayed > MINORS_MAX_GAMES) {
      return { isIneligible: true, reason: `Player has played out of minors eligibility (${gamesPlayed} games, max ${MINORS_MAX_GAMES})` };
    }
  }
  return { isIneligible: false, reason: "" };
};

// ── Roster Violation Detection ─────────────────────────

const getRosterViolations = (playerList: Player[]): { player: Player; reason: string }[] => {
  const violations: { player: Player; reason: string }[] = [];
  playerList.forEach(p => {
    const info = checkIneligibility(p);
    if (info.isIneligible) {
      violations.push({ player: p, reason: info.reason });
    }
  });
  // Check section over-limits
  const sectionCounts: Record<RosterSection, number> = { starting: 0, bench: 0, ir: 0, minors: 0, goalies: 0, goalies_minors: 0 };
  playerList.forEach(p => { sectionCounts[p.rosterSection]++; });
  if (sectionCounts.bench > sectionConfig.bench.maxSlots) {
    violations.push({ player: playerList.find(p => p.rosterSection === "bench")!, reason: `Bench over limit (${sectionCounts.bench}/${sectionConfig.bench.maxSlots})` });
  }
  if (sectionCounts.ir > sectionConfig.ir.maxSlots) {
    violations.push({ player: playerList.find(p => p.rosterSection === "ir")!, reason: `IR over limit (${sectionCounts.ir}/${sectionConfig.ir.maxSlots})` });
  }
  if (sectionCounts.minors > sectionConfig.minors.maxSlots) {
    violations.push({ player: playerList.find(p => p.rosterSection === "minors")!, reason: `Minors over limit (${sectionCounts.minors}/${sectionConfig.minors.maxSlots})` });
  }
  // Check for empty starting roster slots
  const filledSlotIds = new Set(playerList.filter(p => p.rosterSection === "starting" && p.rosterSlotId).map(p => p.rosterSlotId));
  LEAGUE_ROSTER_SLOTS.forEach(slot => {
    if (!filledSlotIds.has(slot.id)) {
      // Create a dummy reference for the violation — use first available player
      const anyPlayer = playerList[0];
      if (anyPlayer) {
        violations.push({ player: anyPlayer, reason: `Empty starting position: ${slot.label} (${slot.id})` });
      }
    }
  });
  return violations;
};

// Check if any possible swap can reduce violations
const canOwnerFixViolations = (playerList: Player[]): boolean => {
  const currentViolationCount = getRosterViolations(playerList).length;
  if (currentViolationCount === 0) return true;
  
  for (let i = 0; i < playerList.length; i++) {
    for (let j = i + 1; j < playerList.length; j++) {
      const a = playerList[i];
      const b = playerList[j];
      // Simulate swap
      const simulated = playerList.map(p => {
        if (p.id === a.id) return { ...p, rosterSection: b.rosterSection, rosterSlotId: b.rosterSlotId };
        if (p.id === b.id) return { ...p, rosterSection: a.rosterSection, rosterSlotId: a.rosterSlotId };
        return p;
      });
      // Check slot eligibility
      const aSlot = b.rosterSlotId ? LEAGUE_ROSTER_SLOTS.find(s => s.id === b.rosterSlotId) : null;
      const bSlot = a.rosterSlotId ? LEAGUE_ROSTER_SLOTS.find(s => s.id === a.rosterSlotId) : null;
      const aCanFill = aSlot ? aSlot.eligiblePositions.some(ep => a.eligiblePositions.includes(ep)) : true;
      const bCanFill = bSlot ? bSlot.eligiblePositions.some(ep => b.eligiblePositions.includes(ep)) : true;
      if (!aCanFill || !bCanFill) continue;
      
      if (getRosterViolations(simulated).length < currentViolationCount) return true;
    }
  }
  return false;
};

export const sectionOrder: RosterSection[] = ["starting", "bench", "ir", "minors", "goalies", "goalies_minors"];




const categoryLabels: Record<string, string> = {
  G: "Goals", A: "Assists", PPP: "Power Play Pts", SHP: "Shorthanded Pts",
  SOG: "Shots on Goal", HIT: "Hits", BLK: "Blocked Shots", PIM: "Penalty Min",
  "+/-": "Plus/Minus", FOW: "Faceoffs Won", FOL: "Faceoffs Lost",
};

export const rosterStatCategories = ["G", "A", "SOG", "PPP", "SHP", "HIT", "BLK", "FOW", "FOL"];

// Categories the league is actively scoring
export const trackedCategories = ["G", "A", "+/-", "PPP", "SHP", "SOG", "HIT", "BLK"];
// Categories not part of league scoring
export const untrackedCategories = ["PIM", "FOW", "FOL"];
// All available stat categories
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

// ── Position Eligibility Badge ─────────────────────────

export const PositionBadges = ({ player }: { player: Player }) => {
  return (
    <div className="flex items-center gap-0.5 flex-wrap">
      {player.eligiblePositions.map(pos => (
        <span
          key={pos}
          className={`text-[9px] font-bold px-1.5 py-0.5 rounded ${getPositionColor(pos)}`}
        >
          {pos}
        </span>
      ))}
      {player.secondaryPositions
        .filter(sp => !sp.acquired)
        .map(sp => (
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

// ── Helper: get display label for a player's roster slot ──

const getSlotDisplayLabel = (player: Player): string => {
  if (player.rosterSection === "bench") return "BEN";
  if (player.rosterSection === "minors") return "M";
  if (player.rosterSection === "ir") return "IR";
  if (player.rosterSection === "starting" && player.rosterSlotId) {
    const slot = LEAGUE_ROSTER_SLOTS.find(s => s.id === player.rosterSlotId);
    return slot?.label ?? player.position;
  }
  return player.position;
};

const getSlotPositionColor = (label: string) => {
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

// ── Main Position Button (clickable, highlights eligible slots) ──

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

// ── Component ──────────────────────────────────────────

interface PlayerRosterProps {
  isOwnTeam?: boolean;
  commissionerMode?: boolean;
  onTradePlayer?: (player: any) => void;
  onDropPlayer?: (player: any) => void;
  onAddToTradeBlock?: (player: any) => void;
  tradeBlockPlayerIds?: string[];
  /** Iter 144 — protection list integration */
  onToggleProtection?: (player: any) => void;
  protectedPlayerIds?: string[];
  protectionEnabled?: boolean;
  protectionDraftType?: "keeper" | "expansion" | null;
  isTradeBuilderOpen?: boolean;
  currentTeamContext?: string;
  teamId?: string;
  /** Bump this number to force a re-fetch of /roster/{teamId}/detail.
   * Used after drops, trade-block toggles, or other mutations so the table
   * reflects the latest server state without a full page reload. */
  refreshKey?: number;
  /** League ID — required for fetching per-league ownership. */
  leagueId?: string;
}
/* ───────── Iter 106: Daily Goalie Picker (per-day starter) ───────── */

const PlayerRoster = ({
  isOwnTeam = true,
  commissionerMode = false,
  onTradePlayer,
  onDropPlayer,
  onAddToTradeBlock,
  tradeBlockPlayerIds = [],
  // Iter 144 — protection list props
  onToggleProtection,
  protectedPlayerIds = [],
  protectionEnabled = false,
  protectionDraftType = null,
  isTradeBuilderOpen = false,
  currentTeamContext = "mine",
  teamId = "frostbite",
  refreshKey = 0,
  leagueId,
}: PlayerRosterProps) => {
  const location = useLocation();
  const isTeamRosterPage = location.pathname.startsWith("/team");

  // Iter 180 — Shadow the module-level LEAGUE_ROSTER_SLOTS with a
  // league-driven version derived from `position_breakdown.active`.
  // Falls back to the module default when no breakdown is configured
  // (e.g. legacy leagues, or before the league has loaded). The
  // shadow only takes effect inside this component scope; module-level
  // helpers (mock-data generation, etc.) continue to read the default.
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const { league: activeLeagueFromHook } = useActiveLeague();
  const LEAGUE_ROSTER_SLOTS = useMemo(
    () => buildLeagueRosterSlots((activeLeagueFromHook as any)?.position_breakdown?.active),
    [(activeLeagueFromHook as any)?.position_breakdown],
  );

  // Iter 180 — Section maxSlots also need to honor the active
  // league config (bench_spots / ir_slots / minors_spots). Shadow the
  // module-level `sectionConfig` so the move-validation logic and
  // section headers all read the right caps. Falls back to the
  // module defaults when a value isn't configured.
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const sectionConfig = useMemo(() => {
    const l: any = activeLeagueFromHook || {};
    const _modDefaults = ({
      starting: { label: "Starting Roster", color: "bg-primary/10", borderColor: "border-l-primary", maxSlots: LEAGUE_ROSTER_SLOTS.length },
      bench: { label: "Bench", color: "bg-accent/10", borderColor: "border-l-accent", maxSlots: typeof l.bench_spots === "number" ? l.bench_spots : 4 },
      ir: { label: "Injury Reserve", color: "bg-destructive/10", borderColor: "border-l-destructive", maxSlots: typeof l.ir_slots === "number" ? l.ir_slots : 3 },
      minors: { label: "Minors Pool", color: "bg-purple-500/10", borderColor: "border-l-purple-500", maxSlots: typeof l.minors_spots === "number" ? l.minors_spots : 5 },
      goalies: { label: "Goalies", color: "bg-teal-500/10", borderColor: "border-l-teal-500", maxSlots: 4 },
      goalies_minors: { label: "Goalies — Minors Pool", color: "bg-teal-500/5", borderColor: "border-l-teal-700", maxSlots: typeof l.minors_spots === "number" ? l.minors_spots : 5 },
    });
    return _modDefaults;
  }, [activeLeagueFromHook, LEAGUE_ROSTER_SLOTS.length]);

  // Detect MongoDB ObjectId (24 hex) — if so, load the real roster from the backend.
  const isRealTeamId = useMemo(() => /^[a-f0-9]{24}$/i.test(teamId), [teamId]);
  const [livePlayers, setLivePlayers] = useState<Player[] | null>(null);
  const [liveLoading, setLiveLoading] = useState(false);

  useEffect(() => {
    if (!isRealTeamId) {
      setLivePlayers(null);
      return;
    }
    let cancelled = false;
    setLiveLoading(true);
    api.get(`/roster/${teamId}/detail`)
      .then(({ data }) => {
        if (cancelled) return;
        const raw = data?.players || [];
        const shaped: Player[] = raw.map((p: any, idx: number) => ({
          id: p.id,
          name: p.name,
          position: p.position,
          eligiblePositions: p.eligiblePositions || [p.position],
          secondaryPositions: [],
          team: p.team || "",
          points: Math.round(p.fantasy_points || 0),
          gamesPlayed: Number(p.games_played || p.gp || 0),
          dynastyValue: p.dynastyValue || 1000,
          trend: (p.trend || "stable") as "up" | "down" | "stable",
          age: p.age || 27,
          contract: {
            salary: p.contract?.salary || 950000,
            yearsRemaining: p.contract?.yearsRemaining || 1,
            type: (p.contract?.type || "Signed") as any,
          },
          rosterSection: (p.rosterSection || "bench") as RosterSection,
          rosterSlotId: p.rosterSlotId || undefined,
          statsByPeriod: p.statsByPeriod || { season: 0, "1d": 0, "7d": 0, "14d": 0, "30d": 0, "60d": 0, "100d": 0 },
          categoryBreakdown: p.categoryBreakdown || { G: 0, A: 0, PPP: 0, SHP: 0, SOG: 0, HIT: 0, BLK: 0, PIM: 0, "+/-": 0, FOW: 0, FOL: 0 },
          matchupGames: p.matchupGames || 0,
          schedule: generateSchedule(idx + 1),
          // Iter 181 — propagate minor_eligible + player_type so the
          // MinorEligibleBadge renders consistently on the team page.
          minor_eligible: !!p.minor_eligible,
          player_type: p.player_type || "skater",
        }));
        setLivePlayers(shaped);
      })
      .catch((e) => { console.error("roster detail load failed", e); setLivePlayers([]); })
      .finally(() => { if (!cancelled) setLiveLoading(false); });
    return () => { cancelled = true; };
  }, [teamId, isRealTeamId, refreshKey]);

  // ── Ownership map: { player_id: {league_pct, league_owned, ...} } ──
  // Fetched once we know every roster player; bumps with refreshKey so adds
  // and drops re-pull fresh ownership numbers.
  const [ownershipMap, setOwnershipMap] = useState<Record<string, any>>({});
  useEffect(() => {
    if (!livePlayers || livePlayers.length === 0) { setOwnershipMap({}); return; }
    const ids = Array.from(new Set(livePlayers.map((p: any) => String(p.id))));
    let cancelled = false;
    api.post("/players/ownership-bulk", { player_ids: ids, league_id: leagueId })
      .then(({ data }) => {
        if (cancelled) return;
        setOwnershipMap(data?.ownership || {});
      })
      .catch(() => { if (!cancelled) setOwnershipMap({}); });
    return () => { cancelled = true; };
  }, [livePlayers, leagueId, refreshKey]);

  // ── Scoring config (per-category fantasy point weights) ──
  // Used by the "Fantasy Points" filter to break down each player's FPTS
  // into per-category contribution (e.g. 10 goals × 3 = 30 pts).
  const [scoringConfig, setScoringConfig] = useState<any>(null);
  // ── Iter 103: Live lineup-lock status banner ───────────────────
  // Polls `/leagues/{id}/lock-status` every 60s so the manager sees a
  // warning BEFORE the save fails. Server-side gate in `save_team_lineup`
  // is still the source of truth — this is purely a friendly pre-warn.
  const [lockStatus, setLockStatus] = useState<any>(null);
  useEffect(() => {
    if (!leagueId) { setLockStatus(null); return; }
    let cancelled = false;
    const fetchOnce = () => {
      api.get(`/leagues/${leagueId}/lock-status`)
        .then(({ data }) => { if (!cancelled) setLockStatus(data); })
        .catch(() => { if (!cancelled) setLockStatus(null); });
    };
    fetchOnce();
    const t = setInterval(fetchOnce, 60_000);
    return () => { cancelled = true; clearInterval(t); };
  }, [leagueId]);

  // ── Iter 106: Emergency swap budget + per-day goalie lock map ──
  const [emergencyBudget, setEmergencyBudget] = useState<any>(null);
  const [goalieLockMap, setGoalieLockMap] = useState<Record<string, string>>({});
  const [savingDailyLock, setSavingDailyLock] = useState(false);
  useEffect(() => {
    if (!teamId || !isRealTeamId) { setEmergencyBudget(null); return; }
    api.get(`/teams/${teamId}/emergency-swap-budget`)
      .then(({ data }) => setEmergencyBudget(data))
      .catch(() => setEmergencyBudget(null));
  }, [teamId, isRealTeamId, lockStatus?.locked]);  // refetch when lock state changes

  useEffect(() => {
    if (!teamId || !isRealTeamId) { setGoalieLockMap({}); return; }
    api.get(`/teams/${teamId}`)
      .then(({ data }) => setGoalieLockMap(data?.goalie_daily_lock || {}))
      .catch(() => setGoalieLockMap({}));
  }, [teamId, isRealTeamId]);

  // Pull league goalie config so we know when to render the picker
  const [leagueGoalieCfg, setLeagueGoalieCfg] = useState<any>(null);
  useEffect(() => {
    if (!leagueId) { setLeagueGoalieCfg(null); return; }
    api.get(`/leagues/${leagueId}`)
      .then(({ data }) => setLeagueGoalieCfg({
        differentiate_goalie_scoring: !!data?.differentiate_goalie_scoring,
        goalie_scoring_method: data?.goalie_scoring_method,
        goalie_gp_limit_enabled: !!data?.goalie_gp_limit_enabled,
        goalie_gp_limit: data?.goalie_gp_limit,
      }))
      .catch(() => setLeagueGoalieCfg(null));
  }, [leagueId]);

  const saveGoalieLockMap = async (nextMap: Record<string, string>) => {
    if (!teamId || !isRealTeamId) return;
    setSavingDailyLock(true);
    try {
      const { data } = await api.put(`/teams/${teamId}/goalie-daily-lock`, { lock_map: nextMap });
      setGoalieLockMap(data?.lock_map || {});
      toast.success(`Daily goalie lock saved (${data?.count || 0} day${(data?.count || 0) === 1 ? "" : "s"})`);
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Failed to save goalie lock");
    } finally {
      setSavingDailyLock(false);
    }
  };
  // ── Lineup warnings (iter 84) ───────────────────────────────────
  // Backend returns `warnings: [{code, player_id, message, ...}]` after a
  // successful lineup save. Map them by player_id so the row can render
  // a yellow chip explaining why the player is flagged (e.g. below the
  // league's `min_games_played` threshold).
  const [lineupWarnings, setLineupWarnings] = useState<Record<string, any[]>>({});
  useEffect(() => {
    if (!leagueId) return;
    let cancelled = false;
    api.get(`/scoring/config?league_id=${leagueId}`)
      .then(({ data }) => { if (!cancelled) setScoringConfig(data); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [leagueId]);

  // ── News map: { player_id: {news_headline, news_summary, news_signal, ...} } ──
  // Powers the inline news icon next to each player's name. The icon opens
  // a small in-app modal (no external browser hop) from NewsSignalIcon.
  const [newsMap, setNewsMap] = useState<Record<string, any>>({});
  useEffect(() => {
    if (!livePlayers || livePlayers.length === 0) { setNewsMap({}); return; }
    const ids = Array.from(new Set(livePlayers.map((p: any) => String(p.id))));
    let cancelled = false;
    api.post("/players/news-bulk", { player_ids: ids })
      .then(({ data }) => {
        if (cancelled) return;
        setNewsMap(data?.news || {});
      })
      .catch(() => { if (!cancelled) setNewsMap({}); });
    return () => { cancelled = true; };
  }, [livePlayers, refreshKey]);

  const teamRoster = useMemo(() => {
    if (isRealTeamId) {
      // For real (DB) team IDs, NEVER fall back to the mock player pool
      // (that's why Vasilevskiy/Saros toasted as "ineligible" even though
      // they aren't on the user's roster). Wait until livePlayers resolves.
      return livePlayers || [];
    }
    // Use a numeric seed from teamId string (mock fallback for non-DB ids)
    let seed = 0;
    for (let i = 0; i < teamId.length; i++) seed += teamId.charCodeAt(i) * (i + 1);
    return generateTeamRoster(teamId, seed);
  }, [teamId, isRealTeamId, livePlayers]);

  // Load saved roster from localStorage if available
  const loadSavedRoster = useCallback((tid: string, fallback: Player[]): Player[] => {
    try {
      const stored = localStorage.getItem(`roster_${tid}`);
      if (stored) {
        const savedSections: Record<number, { rosterSection: RosterSection; rosterSlotId?: string }> = JSON.parse(stored);
        return fallback.map(p => {
          const override = savedSections[p.id];
          if (override) {
            return { ...p, rosterSection: override.rosterSection, rosterSlotId: override.rosterSlotId };
          }
          return p;
        });
      }
    } catch { /* ignore parse errors */ }
    return fallback;
  }, []);

  const persistRoster = useCallback((tid: string, roster: Player[]) => {
    const sections: Record<number, { rosterSection: RosterSection; rosterSlotId?: string }> = {};
    roster.forEach(p => {
      sections[p.id] = { rosterSection: p.rosterSection, rosterSlotId: p.rosterSlotId };
    });
    localStorage.setItem(`roster_${tid}`, JSON.stringify(sections));
  }, []);

  const [players, setPlayers] = useState<Player[]>(() => loadSavedRoster(teamId, teamRoster));
  const [savedPlayers, setSavedPlayers] = useState<Player[]>(() => loadSavedRoster(teamId, teamRoster));

  // Reset players when teamId changes
  useEffect(() => {
    const loaded = loadSavedRoster(teamId, teamRoster);
    setPlayers(loaded);
    setSavedPlayers(loaded);
    setHasUnsavedChanges(false);
    setHighlightedPlayerId(null);
    toastShownRef.current = false; // reset toast guard so new team's ineligibility re-evaluates
  }, [teamRoster, teamId, loadSavedRoster]);
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);
  const [emergencyChangesUsed, setEmergencyChangesUsed] = useState(() => {
    try {
      return parseInt(localStorage.getItem(`emergency_changes_${teamId}`) || "0", 10);
    } catch { return 0; }
  });
  const emergencyChangesAllowed = 2; // from league settings (mock)
  const emergencyChangesRemaining = Math.max(0, emergencyChangesAllowed - emergencyChangesUsed);
  const isRosterLocked = true; // mock: current week rosters are locked (weekly lock)
  const [tradeModalOpen, setTradeModalOpen] = useState(false);
  const [selectedPlayer, setSelectedPlayer] = useState<Player | null>(null);
  const [cardPlayer, setCardPlayer] = useState<Player | null>(null);
  const [cardOpen, setCardOpen] = useState(false);
  const [viewFilter, setViewFilter] = useState<ViewFilter>("season");
  // Iter 185 — Section-summary timeframe. Powers the per-section
  // "Avg X fpts/g · {timeframe}" + top/bottom performer pill in
  // every SectionGroup. Independent from `viewFilter` (which drives
  // the stat-table column selection) — owners often want to see
  // Cap-Hit / Season Stats columns while assessing Last 7 Days
  // trade upside per section.
  const [sectionTimeframe, setSectionTimeframe] = useState<string>("season");
  const [selectedWeek, setSelectedWeek] = useState<number>(currentWeek);
  const [highlightedPlayerId, setHighlightedPlayerId] = useState<number | null>(null);
  const [visibleColumns, setVisibleColumns] = useState<Set<string>>(() => new Set([...rosterStatCategories, "FPTS"]));
  const [showPositionEligibility, setShowPositionEligibility] = useState(true);
  const toastShownRef = useRef(false);
  const saveToastId = useRef<string | number | undefined>(undefined);

  // ── Roster violation state ──
  const currentViolations = useMemo(() => getRosterViolations(players), [players]);
  const hasIllegalRoster = currentViolations.length > 0;

  // ── Ineligibility toast notifications on mount ──
  useEffect(() => {
    if (toastShownRef.current) return;
    // For real teams, wait until livePlayers loads so we don't toast about
    // mock-pool players (e.g. Vasilevskiy/Saros) that aren't on the actual
    // roster.
    if (isRealTeamId && (liveLoading || livePlayers === null)) return;
    if (players.length === 0) return;
    const ineligible = players.filter(p => checkIneligibility(p).isIneligible);
    if (ineligible.length > 0) {
      ineligible.forEach(p => {
        const info = checkIneligibility(p);
        toast.error(`${p.name}: ${info.reason}`);
      });
      // Check if owner can fix
      if (isTeamRosterPage && !canOwnerFixViolations(players)) {
        toast.error("No available roster move can resolve violations", {
          description: "Please contact League Administration for assistance.",
          icon: <AlertTriangle className="h-4 w-4" />,
          duration: Infinity,
        });
      }
      toastShownRef.current = true;
    }
  }, [livePlayers, liveLoading, isRealTeamId, players, isTeamRosterPage]);

  // ── Show save/undo toast when unsaved changes exist ──
  useEffect(() => {
    if (hasUnsavedChanges) {
      // Dismiss previous save toast if any
      if (saveToastId.current) toast.dismiss(saveToastId.current);
      
      const violations = getRosterViolations(players);
      const isLegal = violations.length === 0;

      saveToastId.current = toast(
        isLegal ? "Roster changes pending" : "⚠️ Illegal roster — fix required before saving",
        {
          description: isLegal
            ? "Save your roster changes or undo to revert."
            : violations.map(v => `${v.player.name}: ${v.reason}`).join(" · "),
          duration: Infinity,
          action: isLegal
            ? {
                label: "Save Roster",
                onClick: async () => {
                  setSavedPlayers([...players]);
                  persistRoster(teamId, players);
                  // Persist active lineup to backend so % Start reflects this team.
                  // We map each player's local rosterSection (forward/defense/
                  // goalie/bench/ir/minors) to the team's lineup map.
                  let saveOk = !isRealTeamId; // demo teams always succeed
                  if (isRealTeamId) {
                    try {
                      const lineup: Record<string, { section: string; slot: string }> = {};
                      players.forEach((p: any) => {
                        const section = (p.rosterSection || "bench").toString();
                        lineup[String(p.id)] = { section, slot: p.position || section.toUpperCase().slice(0, 3) };
                      });
                      const { data } = await api.post(`/teams/${teamId}/lineup`, { lineup });
                      saveOk = true;
                      // ── Lineup warnings (iter 84) ─────────────────────
                      // Backend returns `warnings: [{code, player_id, ...}]`
                      // for things like `min_games_played` violations. Cache
                      // them per player so the card can render a yellow chip
                      // and toast a top-level summary so the user knows the
                      // save succeeded WITH caveats.
                      const warns = Array.isArray(data?.warnings) ? data.warnings : [];
                      const byPlayer: Record<string, any[]> = {};
                      warns.forEach((w: any) => {
                        const pid = String(w.player_id || "__league__");
                        (byPlayer[pid] ||= []).push(w);
                      });
                      setLineupWarnings(byPlayer);
                      if (warns.length > 0) {
                        toast.warning(
                          `Saved with ${warns.length} warning${warns.length === 1 ? "" : "s"}`,
                          {
                            description: warns
                              .slice(0, 3)
                              .map((w: any) => w.message)
                              .join(" · "),
                            duration: 8000,
                          },
                        );
                      }
                    } catch (e: any) {
                      const detail = e?.response?.data?.detail;
                      // ── Iter 108: Polished emergency-eligibility denial toast ──
                      if (typeof detail === "string" && detail.startsWith("Emergency swap denied for ")) {
                        // Parse "Emergency swap denied for <name>: player status doesn't match any allowed criteria (a, b, c)."
                        const nameMatch = detail.match(/Emergency swap denied for ([^:]+):/);
                        const critMatch = detail.match(/\(([^)]+)\)/);
                        const name = nameMatch?.[1]?.trim() || "Player";
                        const crits = (critMatch?.[1] || "")
                          .split(",")
                          .map((s: string) => s.trim())
                          .filter((s: string) => s && s !== "any");
                        const allowedHuman = crits.length
                          ? crits.map((c: string) => ({
                              scratched: "healthy scratch",
                              injured: "injured / IR",
                              minors: "in minors",
                              suspended: "suspended",
                              personal: "personal leave",
                            } as Record<string, string>)[c] || c).join(", ")
                          : "any eligible status";
                        toast.error(
                          `${name} isn't eligible for an emergency swap`,
                          {
                            description: `Allowed only for players who are: ${allowedHuman}. Pick a different starter or wait for the lock to release.`,
                            duration: 10000,
                            icon: <AlertTriangle className="h-4 w-4" />,
                          },
                        );
                      } else if (detail) {
                        toast.error(`Lineup save blocked: ${detail}`, { duration: 8000 });
                      } else {
                        console.warn("lineup save failed", e);
                        toast.error("Lineup save failed. Please try again.", { duration: 6000 });
                      }
                    }
                  }
                  if (saveOk) {
                    setHasUnsavedChanges(false);
                    toast.success("Roster saved successfully!");
                  }
                },
              }
            : undefined,
          cancel: {
            label: "Undo",
            onClick: () => {
              setPlayers([...savedPlayers]);
              setHasUnsavedChanges(false);
              toast.info("Roster changes reverted.");
            },
          },
        }
      );
    } else {
      if (saveToastId.current) {
        toast.dismiss(saveToastId.current);
        saveToastId.current = undefined;
      }
    }
  }, [hasUnsavedChanges, players, savedPlayers]);

  const handleOpenTrade = (player: Player) => {
    if (onTradePlayer) {
      // Use the new TradeBuilder flow
      const tradePlayer = {
        id: player.id,
        name: player.name,
        position: player.position,
        eligiblePositions: player.eligiblePositions,
        team: player.team,
        points: player.points,
        dynastyValue: player.dynastyValue,
        trend: player.trend,
        age: player.age,
        contract: player.contract,
        categoryBreakdown: player.categoryBreakdown,
        statsByPeriod: player.statsByPeriod,
        fromTeam: currentTeamContext,
      };
      onTradePlayer(tradePlayer);
    } else {
      setSelectedPlayer(player);
      setTradeModalOpen(true);
    }
  };

  const handleOpenCard = (player: Player) => {
    setCardPlayer(player);
    setCardOpen(true);
  };

  const handleToggleHighlight = useCallback((playerId: number) => {
    setHighlightedPlayerId(prev => {
      if (prev === null || prev === playerId) {
        return prev === playerId ? null : playerId;
      }

      // Attempt roster spot swap
      setPlayers(currentPlayers => {
        const source = currentPlayers.find(p => p.id === prev);
        const target = currentPlayers.find(p => p.id === playerId);
        if (!source || !target) return currentPlayers;

        const sourceSlot = source.rosterSlotId ? LEAGUE_ROSTER_SLOTS.find(s => s.id === source.rosterSlotId) : null;
        const targetSlot = target.rosterSlotId ? LEAGUE_ROSTER_SLOTS.find(s => s.id === target.rosterSlotId) : null;

        const targetCanFillSourceSlot = sourceSlot
          ? sourceSlot.eligiblePositions.some(ep => target.eligiblePositions.includes(ep))
          : true;
        const sourceCanFillTargetSlot = targetSlot
          ? targetSlot.eligiblePositions.some(ep => source.eligiblePositions.includes(ep))
          : true;

        if (!targetCanFillSourceSlot || !sourceCanFillTargetSlot) {
          const reasons: string[] = [];
          if (!targetCanFillSourceSlot) reasons.push(`${target.name} is not eligible for the ${getSlotDisplayLabel(source)} slot`);
          if (!sourceCanFillTargetSlot) reasons.push(`${source.name} is not eligible for the ${getSlotDisplayLabel(target)} slot`);
          toast.error("Swap denied", { description: reasons.join(". ") });
          return currentPlayers;
        }

        // Simulate the swap
        const updated = currentPlayers.map(p => {
          if (p.id === source.id) return { ...p, rosterSection: target.rosterSection, rosterSlotId: target.rosterSlotId };
          if (p.id === target.id) return { ...p, rosterSection: source.rosterSection, rosterSlotId: source.rosterSlotId };
          return p;
        });

        // If roster is currently illegal, only allow moves that reduce violations
        const currentViolationCount = getRosterViolations(currentPlayers).length;
        const newViolationCount = getRosterViolations(updated).length;

        if (currentViolationCount > 0 && newViolationCount >= currentViolationCount) {
          // This move doesn't fix anything — deny it
          const violations = getRosterViolations(currentPlayers);
          const violationReasons = violations.map(v => `${v.player.name}: ${v.reason}`).join(". ");
          
          toast.error("Move denied — illegal roster must be corrected first", {
            description: violationReasons,
          });

          // Check if ANY move can fix it
          if (isTeamRosterPage && !canOwnerFixViolations(currentPlayers)) {
            toast.error("No available roster move can resolve violations", {
              description: "Please contact League Administration for assistance.",
              icon: <AlertTriangle className="h-4 w-4" />,
              duration: 8000,
            });
          }
          return currentPlayers;
        }

        const sourceLabel = getSlotDisplayLabel(source);
        const targetLabel = getSlotDisplayLabel(target);
        toast.success(`Roster swap: ${target.name} → ${sourceLabel}, ${source.name} → ${targetLabel}`);
        setHasUnsavedChanges(true);
        return updated;
      });

      return null;
    });
  }, []);

  // ── Move highlighted player to a section (bench/IR) ──
  const handleMoveToSection = useCallback((targetSection: RosterSection) => {
    setHighlightedPlayerId(prev => {
      if (!prev) return null;

      setPlayers(currentPlayers => {
        const source = currentPlayers.find(p => p.id === prev);
        if (!source) return currentPlayers;

        // Check section capacity
        const sectionCount = currentPlayers.filter(p => p.rosterSection === targetSection).length;
        if (sectionCount >= sectionConfig[targetSection].maxSlots) {
          toast.error(`Cannot move to ${sectionConfig[targetSection].label}`, {
            description: `Section is full (${sectionCount}/${sectionConfig[targetSection].maxSlots})`,
          });
          return currentPlayers;
        }

        // IR eligibility: player must have no recent stats (injured)
        if (targetSection === "ir") {
          const hasRecentStats = source.statsByPeriod["7d"] > 0 || source.statsByPeriod["1d"] > 0;
          if (hasRecentStats) {
            toast.error("Cannot place on Injury Reserve", {
              description: `${source.name} is healthy and not eligible for IR`,
            });
            return currentPlayers;
          }
        }

        // Simulate the move
        const updated = currentPlayers.map(p => {
          if (p.id === source.id) return { ...p, rosterSection: targetSection as RosterSection, rosterSlotId: undefined };
          return p;
        });

        const newViolations = getRosterViolations(updated);

        const targetLabel = sectionConfig[targetSection].label;
        toast.success(`${source.name} moved to ${targetLabel}`);
        
        // Warn about any violations in the new roster state
        if (newViolations.length > 0) {
          const emptySlotViolations = newViolations.filter(v => v.reason.startsWith("Empty starting position"));
          const otherViolations = newViolations.filter(v => !v.reason.startsWith("Empty starting position"));
          if (emptySlotViolations.length > 0) {
            toast.warning("Roster is now illegal", {
              description: emptySlotViolations.map(v => v.reason).join(". "),
            });
          }
          if (otherViolations.length > 0) {
            toast.warning("Roster violations remain", {
              description: otherViolations.map(v => `${v.player.name}: ${v.reason}`).join(". "),
            });
          }
        }
        
        setHasUnsavedChanges(true);
        return updated;
      });

      return null;
    });
  }, []);

  // Get the highlighted player's eligible positions
  const highlightedPlayer = highlightedPlayerId
    ? players.find(p => p.id === highlightedPlayerId)
    : null;
  const highlightedPositions = highlightedPlayer?.eligiblePositions ?? [];

  const matchup = weeklyMatchups.find(w => w.week === selectedWeek);
  const isPastWeek = selectedWeek < currentWeek;

  const grouped = sectionOrder.reduce((acc, section) => {
    const sectionPlayers = players.filter(p => p.rosterSection === section);
    // Sort starting players by their slot order
    if (section === "starting") {
      const slotOrder = LEAGUE_ROSTER_SLOTS.map(s => s.id);
      sectionPlayers.sort((a, b) => {
        const aIdx = a.rosterSlotId ? slotOrder.indexOf(a.rosterSlotId) : 999;
        const bIdx = b.rosterSlotId ? slotOrder.indexOf(b.rosterSlotId) : 999;
        return aIdx - bIdx;
      });
    }
    acc[section] = sectionPlayers;
    return acc;
  }, {} as Record<RosterSection, Player[]>);

  // Section counts for open slot logic
  const currentSectionCounts = useMemo(() => {
    const counts: Record<RosterSection, number> = { starting: 0, bench: 0, ir: 0, minors: 0 };
    players.forEach(p => { counts[p.rosterSection]++; });
    return counts;
  }, [players]);

  const effectiveFilter = isPastWeek && viewFilter === "season" ? "7d" : viewFilter;

  const getPlayerPoints = (player: Player): number => {
    if (effectiveFilter === "fantasy-points" || effectiveFilter === "matchup-schedule" || effectiveFilter === "full-schedule") {
      return player.points;
    }
    return player.statsByPeriod[effectiveFilter] ?? player.points;
  };

  const getSectionTotal = (section: RosterSection): number => {
    return grouped[section].reduce((sum, p) => sum + getPlayerPoints(p), 0);
  };

  const filteredStatCategories = useMemo(() =>
    allStatCategories.filter(cat => visibleColumns.has(cat)),
    [visibleColumns]
  );
  const showFpts = visibleColumns.has("FPTS");

  return (
    <SharedRosterConfigContext.Provider
      value={useMemo(
        () => ({ slots: LEAGUE_ROSTER_SLOTS, sections: sectionConfig as any }),
        [LEAGUE_ROSTER_SLOTS, sectionConfig],
      )}
    >
    <>
      <div className="stat-card p-0 overflow-hidden">
        {/* ── Iter 103: Lineup Lock Status Banner ── */}
        {lockStatus?.locked && (
          <div
            className="px-4 py-2.5 border-b border-amber-500/40 bg-amber-500/10 flex items-start gap-2"
            data-testid="lineup-lock-banner"
          >
            <AlertTriangle className="h-4 w-4 text-amber-400 mt-0.5 shrink-0" />
            <div className="flex-1">
              <div className="text-xs font-semibold text-amber-300">
                Lineup locked — saves will be rejected
              </div>
              <div className="text-[11px] text-amber-200/80 leading-snug">
                {lockStatus.reason}
                {lockStatus.next_unlock_iso && (
                  <span className="ml-1 opacity-80">
                    Unlocks at {new Date(lockStatus.next_unlock_iso).toLocaleString(undefined, {
                      weekday: "short",
                      hour: "numeric",
                      minute: "2-digit",
                    })}.
                  </span>
                )}
              </div>
            </div>
          </div>
        )}
        {/* ── Iter 106: Emergency Swaps chip ── */}
        {emergencyBudget?.enabled && (
          <div className="px-4 py-2 border-b border-border bg-secondary/20 flex items-center gap-2 flex-wrap"
               data-testid="emergency-swap-chip">
            <span className={`text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-full border ${
              emergencyBudget.remaining > 0
                ? "bg-emerald-500/10 text-emerald-300 border-emerald-500/30"
                : "bg-rose-500/10 text-rose-300 border-rose-500/30"
            }`}>
              Used {emergencyBudget.used} / {emergencyBudget.budget} emergency swaps {emergencyBudget.scope_label}
            </span>
            {emergencyBudget.remaining > 0 ? (
              <span className="text-[11px] text-muted-foreground">
                ({emergencyBudget.remaining} left{emergencyBudget.scope === "per_season" ? " for the season" : ""})
              </span>
            ) : (
              <span className="text-[11px] text-rose-300/80">No swaps remaining — wait for the next reset.</span>
            )}
          </div>
        )}
        {/* ── Iter 106: Per-Day Goalie Picker ── */}
        {leagueGoalieCfg?.differentiate_goalie_scoring && leagueGoalieCfg?.goalie_scoring_method === "daily_lock" && (
          <DailyGoaliePicker
            roster={teamRoster}
            lockMap={goalieLockMap}
            onSave={saveGoalieLockMap}
            saving={savingDailyLock}
            gpLimit={leagueGoalieCfg.goalie_gp_limit_enabled ? leagueGoalieCfg.goalie_gp_limit : null}
            week={selectedWeek}
          />
        )}
        {/* ── Matchup Bar ── */}
        <div className="p-4 border-b border-border bg-secondary/20">
          <div className="flex flex-wrap items-center gap-3">
            <div className="flex items-center gap-1">
              <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => setSelectedWeek(w => Math.max(1, w - 1))} disabled={selectedWeek <= 1}>
                <ChevronLeft className="h-4 w-4" />
              </Button>
              <span className="text-sm font-semibold min-w-[60px] text-center">Week {selectedWeek}</span>
              <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => setSelectedWeek(w => Math.min(weeklyMatchups.length, w + 1))} disabled={selectedWeek >= weeklyMatchups.length}>
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>

            {matchup && (
              <div className="flex items-center gap-2">
                <span className="text-xs text-muted-foreground">vs</span>
                <TooltipProvider>
                  <Tooltip>
                    <TooltipTrigger>
                      <span className="text-sm font-bold">{matchup.opponent}</span>
                    </TooltipTrigger>
                    <TooltipContent><p>{matchup.opponentFull}</p></TooltipContent>
                  </Tooltip>
                </TooltipProvider>
                {isPastWeek || selectedWeek === currentWeek ? (
                  <div className="flex items-center gap-2">
                    <span className="text-sm text-muted-foreground">{matchup.score.mine} – {matchup.score.theirs}</span>
                    <Badge variant="outline" className={`text-xs font-bold px-2 py-0.5 ${matchup.result === "W" ? "border-success text-success bg-success/10" : "border-destructive text-destructive bg-destructive/10"}`}>
                      {matchup.result}
                    </Badge>
                  </div>
                ) : (
                  <span className="text-xs text-muted-foreground">Upcoming</span>
                )}
              </div>
            )}

            <div className="flex-1" />

            {/* Highlight indicator */}
            {highlightedPlayer && (
              <div className="flex items-center gap-2 px-3 py-1 rounded-lg bg-success/10 border border-success/30">
                <span className="text-[10px] font-semibold text-success">
                  {highlightedPlayer.name} selected — click another player's position to swap
                </span>
                <button
                  onClick={() => setHighlightedPlayerId(null)}
                  className="text-success hover:text-success/70 text-xs font-bold"
                >
                  ✕
                </button>
              </div>
            )}

            <Select value={viewFilter} onValueChange={(v) => setViewFilter(v as ViewFilter)}>
              <SelectTrigger className="w-[180px] h-8 text-xs bg-secondary border-border">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="season">Season Stats</SelectItem>
                <SelectItem value="cap-hit">Cap Hit</SelectItem>
                <SelectItem value="1d">Last 1 Day</SelectItem>
                <SelectItem value="7d">Last 7 Days</SelectItem>
                <SelectItem value="14d">Last 14 Days</SelectItem>
                <SelectItem value="30d">Last 30 Days</SelectItem>
                <SelectItem value="60d">Last 60 Days</SelectItem>
                <SelectItem value="100d">Last 100 Days</SelectItem>
                <SelectItem value="fantasy-points">Fantasy Points</SelectItem>
                <SelectItem value="matchup-schedule">Matchup Schedule</SelectItem>
                <SelectItem value="full-schedule">Full Schedule</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>

        {/* ── Header ── */}
        <div className="p-6 pb-0 border-b border-border">
          <div className="flex items-center justify-between pb-4">
            <div className="flex items-center gap-3">
              <h3 className="text-lg font-semibold">Team Roster</h3>
              {commissionerMode && (
                <Badge variant="outline" className="border-primary text-primary bg-primary/10 text-[10px] font-bold">
                  COMMISSIONER EDIT MODE
                </Badge>
              )}
              {isOwnTeam && isRosterLocked && emergencyChangesAllowed > 0 && (
                <TooltipProvider>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Badge
                        variant="outline"
                        className={`text-[10px] font-bold ${
                          emergencyChangesRemaining > 0
                            ? "border-amber-500/50 text-amber-400 bg-amber-500/10"
                            : "border-destructive/50 text-destructive bg-destructive/10"
                        }`}
                      >
                        <AlertTriangle className="h-3 w-3 mr-1" />
                        {emergencyChangesRemaining} / {emergencyChangesAllowed} Emergency Changes
                      </Badge>
                    </TooltipTrigger>
                    <TooltipContent className="max-w-[240px]">
                      <p className="text-xs">
                        {emergencyChangesRemaining > 0
                          ? "Roster is locked. You can use an emergency change to swap a starting player with a bench player. Points already earned by the swapped-out player still count."
                          : "No emergency roster changes remaining this season."}
                      </p>
                    </TooltipContent>
                  </Tooltip>
                </TooltipProvider>
              )}

              {/* Column Settings Cog */}
              <Popover>
                <PopoverTrigger asChild>
                  <Button variant="ghost" size="icon" className="h-7 w-7 text-muted-foreground hover:text-foreground">
                    <Settings className="h-4 w-4" />
                  </Button>
                </PopoverTrigger>
                <PopoverContent className="w-[280px] p-0" align="start">
                  <div className="p-3 border-b border-border">
                    <p className="text-sm font-semibold">Roster Display Settings</p>
                    <p className="text-xs text-muted-foreground">Choose which columns to show</p>
                  </div>

                  {/* Tracked Categories */}
                  <div className="p-3 space-y-2">
                    <p className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Tracked Categories</p>
                    <div className="grid grid-cols-2 gap-1.5">
                      {trackedCategories.map(cat => (
                        <label key={cat} className="flex items-center gap-2 text-xs cursor-pointer hover:bg-secondary/50 rounded px-1.5 py-1">
                          <Checkbox
                            checked={visibleColumns.has(cat)}
                            onCheckedChange={(checked) => {
                              setVisibleColumns(prev => {
                                const next = new Set(prev);
                                if (checked) next.add(cat); else next.delete(cat);
                                return next;
                              });
                            }}
                            className="h-3.5 w-3.5"
                          />
                          <span className="font-medium">{cat}</span>
                          <span className="text-muted-foreground ml-auto text-[10px]">{categoryLabels[cat]}</span>
                        </label>
                      ))}
                    </div>
                  </div>

                  <Separator />

                  {/* Untracked Categories */}
                  <div className="p-3 space-y-2">
                    <p className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Untracked Categories</p>
                    <div className="grid grid-cols-2 gap-1.5">
                      {untrackedCategories.map(cat => (
                        <label key={cat} className="flex items-center gap-2 text-xs cursor-pointer hover:bg-secondary/50 rounded px-1.5 py-1">
                          <Checkbox
                            checked={visibleColumns.has(cat)}
                            onCheckedChange={(checked) => {
                              setVisibleColumns(prev => {
                                const next = new Set(prev);
                                if (checked) next.add(cat); else next.delete(cat);
                                return next;
                              });
                            }}
                            className="h-3.5 w-3.5"
                          />
                          <span className="font-medium">{cat}</span>
                          <span className="text-muted-foreground ml-auto text-[10px]">{categoryLabels[cat]}</span>
                        </label>
                      ))}
                    </div>
                  </div>

                  <Separator />

                  {/* Fantasy Points & Position Eligibility */}
                  <div className="p-3 space-y-2">
                    <p className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Display Options</p>
                    <label className="flex items-center gap-2 text-xs cursor-pointer hover:bg-secondary/50 rounded px-1.5 py-1">
                      <Checkbox
                        checked={visibleColumns.has("FPTS")}
                        onCheckedChange={(checked) => {
                          setVisibleColumns(prev => {
                            const next = new Set(prev);
                            if (checked) next.add("FPTS"); else next.delete("FPTS");
                            return next;
                          });
                        }}
                        className="h-3.5 w-3.5"
                      />
                      <span className="font-medium">Fantasy Points</span>
                    </label>
                    <label className="flex items-center gap-2 text-xs cursor-pointer hover:bg-secondary/50 rounded px-1.5 py-1">
                      <Checkbox
                        checked={showPositionEligibility}
                        onCheckedChange={(checked) => setShowPositionEligibility(!!checked)}
                        className="h-3.5 w-3.5"
                      />
                      <span className="font-medium">Position Eligibility</span>
                    </label>
                  </div>

                  <Separator />

                  {/* Quick toggles */}
                  <div className="p-3 flex gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      className="text-[10px] h-6 px-2"
                      onClick={() => setVisibleColumns(new Set([...allStatCategories, "FPTS"]))}
                    >
                      Show All
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      className="text-[10px] h-6 px-2"
                      onClick={() => setVisibleColumns(new Set([...trackedCategories, "FPTS"]))}
                    >
                      Tracked Only
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      className="text-[10px] h-6 px-2"
                      onClick={() => setVisibleColumns(new Set(["FPTS"]))}
                    >
                      Points Only
                    </Button>
                  </div>
                </PopoverContent>
              </Popover>
            </div>
            <span className="text-xs text-muted-foreground bg-secondary px-2 py-1 rounded-full">
              {players.length} Players
            </span>
          </div>
        </div>

        {/* ── Table ── */}
        {effectiveFilter === "full-schedule" ? (
          <FullScheduleTable sectionTimeframe={sectionTimeframe} grouped={grouped} onTrade={handleOpenTrade} onPlayerClick={handleOpenCard} isOwnTeam={isOwnTeam} commissionerMode={commissionerMode} highlightedPlayerId={highlightedPlayerId} highlightedPositions={highlightedPositions} onToggleHighlight={handleToggleHighlight} onMoveToSection={handleMoveToSection} sectionCounts={currentSectionCounts} showPositionEligibility={showPositionEligibility} />
        ) : effectiveFilter === "matchup-schedule" ? (
          <MatchupScheduleTable sectionTimeframe={sectionTimeframe} grouped={grouped} onTrade={handleOpenTrade} onPlayerClick={handleOpenCard} isOwnTeam={isOwnTeam} commissionerMode={commissionerMode} highlightedPlayerId={highlightedPlayerId} highlightedPositions={highlightedPositions} onToggleHighlight={handleToggleHighlight} onMoveToSection={handleMoveToSection} sectionCounts={currentSectionCounts} showPositionEligibility={showPositionEligibility} />
        ) : effectiveFilter === "fantasy-points" ? (
          <FantasyPointsTable sectionTimeframe={sectionTimeframe} grouped={grouped} onTrade={handleOpenTrade} getSectionTotal={getSectionTotal} onPlayerClick={handleOpenCard} isOwnTeam={isOwnTeam} commissionerMode={commissionerMode} highlightedPlayerId={highlightedPlayerId} highlightedPositions={highlightedPositions} onToggleHighlight={handleToggleHighlight} onMoveToSection={handleMoveToSection} sectionCounts={currentSectionCounts} visibleCategories={filteredStatCategories} showFpts={showFpts} showPositionEligibility={showPositionEligibility} scoringConfig={scoringConfig} />
        ) : effectiveFilter === "cap-hit" ? (
          <CapHitTable sectionTimeframe={sectionTimeframe} grouped={grouped} onPlayerClick={handleOpenCard} />
        ) : (
          <StatsTable
            grouped={grouped}
            onTrade={handleOpenTrade}
            onDrop={onDropPlayer}
            onMegaphone={onAddToTradeBlock}
            tradeBlockPlayerIds={tradeBlockPlayerIds}
            onToggleProtection={onToggleProtection}
            protectedPlayerIds={protectedPlayerIds}
            protectionEnabled={protectionEnabled}
            protectionDraftType={protectionDraftType}
            ownershipMap={ownershipMap}
            newsMap={newsMap}
            onPlayerClick={handleOpenCard}
            getPlayerPoints={getPlayerPoints}
            getSectionTotal={getSectionTotal}
            filterLabel={filterLabels[effectiveFilter]}
            isOwnTeam={isOwnTeam}
            commissionerMode={commissionerMode}
            highlightedPlayerId={highlightedPlayerId}
            highlightedPositions={highlightedPositions}
            onToggleHighlight={handleToggleHighlight}
            onMoveToSection={handleMoveToSection}
            sectionCounts={currentSectionCounts}
            visibleCategories={filteredStatCategories}
            showFpts={showFpts}
            showPositionEligibility={showPositionEligibility}
            lineupWarnings={lineupWarnings}
          />
        )}
      </div>

      {selectedPlayer && (
        <PlayerTradeModal
          open={tradeModalOpen}
          onOpenChange={setTradeModalOpen}
          initialPlayer={selectedPlayer}
          allPlayers={players}
        />
      )}

      {cardPlayer && (
        <PlayerCardModal
          open={cardOpen}
          onOpenChange={setCardOpen}
          player={cardPlayer}
          scoringConfig={scoringConfig}
        />
      )}
    </>
    </SharedRosterConfigContext.Provider>
  );
};

// ── Highlight props shared across tables ───────────────

export interface HighlightProps {
  highlightedPlayerId: number | null;
  highlightedPositions: string[];
  onToggleHighlight: (playerId: number) => void;
  onMoveToSection?: (section: RosterSection) => void;
  sectionCounts?: Record<RosterSection, number>;
}

// ── Helper: is this player's position highlighted ──────

export const isPositionHighlighted = (player: Player, highlightedPositions: string[], highlightedPlayerId: number | null): boolean => {
  if (!highlightedPlayerId) return false;
  if (player.id === highlightedPlayerId) return false; // don't highlight the source player itself
  return highlightedPositions.includes(player.position);
};

// Helper: find highlighted player from grouped data
export const findHighlightedPlayer = (grouped: Record<RosterSection, Player[]>, highlightedPlayerId: number | null): Player | null => {
  if (!highlightedPlayerId) return null;
  for (const section of sectionOrder) {
    const found = grouped[section].find(p => p.id === highlightedPlayerId);
    if (found) return found;
  }
  return null;
};

// Helper: should we show an open slot for moving highlighted player to this section?
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
  // Don't show IR open slot if player is healthy (ineligible for IR)
  if (section === "ir" && highlightedPlayer) {
    const hasRecentStats = highlightedPlayer.statsByPeriod["7d"] > 0 || highlightedPlayer.statsByPeriod["1d"] > 0;
    if (hasRecentStats) return false;
  }
  return true;
};

// ── Stats Table (default, season, time-range) ──────────

// ── Iter 183 — Sub-components moved to ./player-roster/sub-components.tsx
//    Re-exported here so existing imports of these from PlayerRoster.tsx
//    keep working (the file's surface area is unchanged from a consumer
//    perspective). Risks noted: cross-file cycle is deliberate and safe
//    because module-init never dereferences these names — only the
//    React render tree does.
export {
  StatsTable,
  CapHitTable,
  FantasyPointsTable,
  MatchupScheduleTable,
  FullScheduleTable,
  SectionGroup,
  EmptySlotRow,
  OpenSlotRow,
  PlayerRow,
  TradeButton,
  MegaphoneButton,
  DropButton,
  OwnershipCell,
} from "./player-roster/sub-components";

export default PlayerRoster;
