// @ts-nocheck
// Iter 186 — Extracted from `PlayerRoster.tsx`. Pure deterministic
// mock data + small helpers used to seed the dashboard before the
// real league/team APIs return. Lives in its own file so the parent
// component stays focused on render orchestration.

import type { Player, PlayerGame, RosterSection } from "./internals";
import { LEAGUE_ROSTER_SLOTS } from "./internals";

// ── Deterministic schedule generator ──────────────────────────
export const generateSchedule = (seed: number = 0): PlayerGame[] => {
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
export const seededRand = (seed: number) => {
  let s = seed;
  return () => {
    s = (s * 1103515245 + 12345) & 0x7fffffff;
    return s / 0x7fffffff;
  };
};

// ── Default Frostbite roster (the demo team used on Team page) ──
export const frostbitePlayers: Player[] = [
  { id: 1, name: "Connor McDavid", position: "C", eligiblePositions: ["C", "LW"], secondaryPositions: [{ position: "LW", gamesPlayed: 25, acquired: true }, { position: "RW", gamesPlayed: 8, acquired: false }], team: "EDM", points: 142, gamesPlayed: 65, dynastyValue: 9800, trend: "up", age: 27, contract: { salary: 12500000, yearsRemaining: 4, type: "Signed" }, rosterSection: "starting", rosterSlotId: "C1", statsByPeriod: { season: 142, "1d": 4, "7d": 18, "14d": 32, "30d": 58, "60d": 98, "100d": 130 }, categoryBreakdown: { G: 42, A: 68, PPP: 38, SHP: 2, SOG: 285, HIT: 22, BLK: 15, PIM: 18, "+/-": 32, FOW: 812, FOL: 604 }, matchupGames: 4, schedule: generateSchedule(1) },
  { id: 2, name: "Nathan MacKinnon", position: "C", eligiblePositions: ["C"], secondaryPositions: [{ position: "LW", gamesPlayed: 12, acquired: false }, { position: "RW", gamesPlayed: 3, acquired: false }], team: "COL", points: 128, gamesPlayed: 62, dynastyValue: 9200, trend: "stable", age: 28, contract: { salary: 12600000, yearsRemaining: 6, type: "Signed" }, rosterSection: "starting", rosterSlotId: "C2", statsByPeriod: { season: 128, "1d": 2, "7d": 14, "14d": 28, "30d": 52, "60d": 88, "100d": 118 }, categoryBreakdown: { G: 38, A: 62, PPP: 34, SHP: 4, SOG: 310, HIT: 30, BLK: 12, PIM: 22, "+/-": 28, FOW: 756, FOL: 580 }, matchupGames: 3, schedule: generateSchedule(2) },
  { id: 3, name: "Auston Matthews", position: "C", eligiblePositions: ["C", "RW"], secondaryPositions: [{ position: "RW", gamesPlayed: 22, acquired: true }, { position: "LW", gamesPlayed: 5, acquired: false }], team: "TOR", points: 115, gamesPlayed: 60, dynastyValue: 8900, trend: "up", age: 26, contract: { salary: 13250000, yearsRemaining: 3, type: "UFA" }, rosterSection: "starting", rosterSlotId: "RW1", statsByPeriod: { season: 115, "1d": 5, "7d": 16, "14d": 30, "30d": 48, "60d": 82, "100d": 105 }, categoryBreakdown: { G: 52, A: 40, PPP: 28, SHP: 3, SOG: 340, HIT: 28, BLK: 8, PIM: 14, "+/-": 18, FOW: 890, FOL: 650 }, matchupGames: 4, schedule: generateSchedule(3) },
  { id: 4, name: "Nikita Kucherov", position: "RW", eligiblePositions: ["RW", "LW"], secondaryPositions: [{ position: "LW", gamesPlayed: 30, acquired: true }, { position: "C", gamesPlayed: 2, acquired: false }], team: "TBL", points: 124, gamesPlayed: 64, dynastyValue: 8400, trend: "up", age: 30, contract: { salary: 9500000, yearsRemaining: 2, type: "UFA" }, rosterSection: "starting", rosterSlotId: "W1", statsByPeriod: { season: 124, "1d": 3, "7d": 15, "14d": 26, "30d": 50, "60d": 86, "100d": 112 }, categoryBreakdown: { G: 36, A: 60, PPP: 42, SHP: 1, SOG: 260, HIT: 18, BLK: 10, PIM: 12, "+/-": 24, FOW: 45, FOL: 38 }, matchupGames: 3, schedule: generateSchedule(4) },
  { id: 5, name: "Cale Makar", position: "D", eligiblePositions: ["D"], secondaryPositions: [], team: "COL", points: 89, gamesPlayed: 62, dynastyValue: 9500, trend: "stable", age: 25, contract: { salary: 9000000, yearsRemaining: 5, type: "Signed" }, rosterSection: "starting", rosterSlotId: "D1", statsByPeriod: { season: 89, "1d": 2, "7d": 10, "14d": 18, "30d": 36, "60d": 62, "100d": 80 }, categoryBreakdown: { G: 18, A: 52, PPP: 30, SHP: 0, SOG: 220, HIT: 42, BLK: 88, PIM: 16, "+/-": 30, FOW: 0, FOL: 0 }, matchupGames: 3, schedule: generateSchedule(5) },
  { id: 6, name: "Igor Shesterkin", position: "G", eligiblePositions: ["G"], secondaryPositions: [], team: "NYR", points: 76, gamesPlayed: 50, dynastyValue: 7200, trend: "down", age: 28, contract: { salary: 5666667, yearsRemaining: 1, type: "UFA" }, rosterSection: "starting", rosterSlotId: "G1", statsByPeriod: { season: 76, "1d": 0, "7d": 8, "14d": 14, "30d": 30, "60d": 52, "100d": 68 }, categoryBreakdown: { G: 0, A: 2, PPP: 0, SHP: 0, SOG: 0, HIT: 0, BLK: 0, PIM: 0, "+/-": 0, FOW: 0, FOL: 0 }, matchupGames: 2, schedule: generateSchedule(6) },
  { id: 12, name: "Brad Marchand", position: "LW", eligiblePositions: ["LW", "C"], secondaryPositions: [{ position: "C", gamesPlayed: 18, acquired: false }], team: "BOS", points: 85, gamesPlayed: 60, dynastyValue: 5800, trend: "stable", age: 36, contract: { salary: 6125000, yearsRemaining: 2, type: "UFA" }, rosterSection: "starting", rosterSlotId: "LW1", statsByPeriod: { season: 85, "1d": 1, "7d": 10, "14d": 18, "30d": 34, "60d": 58, "100d": 76 }, categoryBreakdown: { G: 24, A: 38, PPP: 18, SHP: 3, SOG: 195, HIT: 65, BLK: 12, PIM: 48, "+/-": 12, FOW: 180, FOL: 140 }, matchupGames: 3, schedule: generateSchedule(12) },
  { id: 13, name: "Quinn Hughes", position: "D", eligiblePositions: ["D"], secondaryPositions: [], team: "VAN", points: 78, gamesPlayed: 60, dynastyValue: 7600, trend: "up", age: 24, contract: { salary: 7850000, yearsRemaining: 4, type: "Signed" }, rosterSection: "starting", rosterSlotId: "UTIL1", statsByPeriod: { season: 78, "1d": 2, "7d": 9, "14d": 16, "30d": 32, "60d": 54, "100d": 70 }, categoryBreakdown: { G: 12, A: 48, PPP: 26, SHP: 0, SOG: 180, HIT: 28, BLK: 72, PIM: 10, "+/-": 22, FOW: 0, FOL: 0 }, matchupGames: 3, schedule: generateSchedule(13) },
  { id: 7, name: "Mitch Marner", position: "RW", eligiblePositions: ["RW", "LW", "C"], secondaryPositions: [{ position: "LW", gamesPlayed: 28, acquired: true }, { position: "C", gamesPlayed: 21, acquired: true }], team: "TOR", points: 98, gamesPlayed: 60, dynastyValue: 7800, trend: "stable", age: 27, contract: { salary: 10903000, yearsRemaining: 1, type: "UFA" }, rosterSection: "bench", statsByPeriod: { season: 98, "1d": 1, "7d": 12, "14d": 22, "30d": 40, "60d": 68, "100d": 88 }, categoryBreakdown: { G: 22, A: 58, PPP: 28, SHP: 2, SOG: 180, HIT: 15, BLK: 6, PIM: 8, "+/-": 14, FOW: 32, FOL: 28 }, matchupGames: 4, schedule: generateSchedule(7) },
  { id: 8, name: "Brady Tkachuk", position: "LW", eligiblePositions: ["LW", "RW"], secondaryPositions: [{ position: "RW", gamesPlayed: 20, acquired: true }, { position: "C", gamesPlayed: 6, acquired: false }], team: "OTT", points: 72, gamesPlayed: 58, dynastyValue: 7100, trend: "up", age: 25, contract: { salary: 8214286, yearsRemaining: 5, type: "Signed" }, rosterSection: "bench", statsByPeriod: { season: 72, "1d": 3, "7d": 9, "14d": 16, "30d": 30, "60d": 50, "100d": 65 }, categoryBreakdown: { G: 28, A: 30, PPP: 16, SHP: 1, SOG: 240, HIT: 180, BLK: 22, PIM: 92, "+/-": 8, FOW: 120, FOL: 95 }, matchupGames: 3, schedule: generateSchedule(8) },
  { id: 9, name: "Aleksander Barkov", position: "C", eligiblePositions: ["C", "LW"], secondaryPositions: [{ position: "LW", gamesPlayed: 24, acquired: true }, { position: "RW", gamesPlayed: 10, acquired: false }], team: "FLA", points: 0, gamesPlayed: 0, dynastyValue: 6500, trend: "down", age: 29, contract: { salary: 10000000, yearsRemaining: 6, type: "Signed" }, rosterSection: "ir", statsByPeriod: { season: 0, "1d": 0, "7d": 0, "14d": 0, "30d": 0, "60d": 0, "100d": 0 }, categoryBreakdown: { G: 0, A: 0, PPP: 0, SHP: 0, SOG: 0, HIT: 0, BLK: 0, PIM: 0, "+/-": 0, FOW: 0, FOL: 0 }, matchupGames: 0, schedule: generateSchedule(9) },
  { id: 10, name: "Connor Bedard", position: "C", eligiblePositions: ["C"], secondaryPositions: [{ position: "RW", gamesPlayed: 14, acquired: false }, { position: "LW", gamesPlayed: 4, acquired: false }], team: "CHI", points: 52, gamesPlayed: 40, dynastyValue: 8800, trend: "up", age: 19, contract: { salary: 950000, yearsRemaining: 2, type: "ELC" }, rosterSection: "minors", statsByPeriod: { season: 52, "1d": 2, "7d": 8, "14d": 14, "30d": 24, "60d": 38, "100d": 48 }, categoryBreakdown: { G: 18, A: 24, PPP: 12, SHP: 0, SOG: 160, HIT: 10, BLK: 4, PIM: 6, "+/-": 4, FOW: 340, FOL: 310 }, matchupGames: 4, schedule: generateSchedule(10) },
  { id: 11, name: "Macklin Celebrini", position: "C", eligiblePositions: ["C"], secondaryPositions: [{ position: "LW", gamesPlayed: 7, acquired: false }], team: "SJS", points: 38, gamesPlayed: 38, dynastyValue: 8200, trend: "up", age: 18, contract: { salary: 950000, yearsRemaining: 3, type: "ELC" }, rosterSection: "minors", statsByPeriod: { season: 38, "1d": 1, "7d": 6, "14d": 10, "30d": 18, "60d": 28, "100d": 35 }, categoryBreakdown: { G: 14, A: 16, PPP: 8, SHP: 1, SOG: 130, HIT: 8, BLK: 3, PIM: 4, "+/-": 2, FOW: 280, FOL: 260 }, matchupGames: 3, schedule: generateSchedule(11) },
];

// Pool of NHL players to create unique rosters per team
export const playerPool: Omit<Player, "id" | "rosterSection" | "rosterSlotId" | "schedule">[] = [
  { name: "Leon Draisaitl", position: "C", eligiblePositions: ["C", "LW"], secondaryPositions: [{ position: "LW", gamesPlayed: 22, acquired: true }], team: "EDM", points: 135, gamesPlayed: 64, dynastyValue: 9400, trend: "up", age: 28, contract: { salary: 8500000, yearsRemaining: 1, type: "UFA" }, statsByPeriod: { season: 135, "1d": 3, "7d": 16, "14d": 30, "30d": 55, "60d": 92, "100d": 122 }, categoryBreakdown: { G: 48, A: 58, PPP: 36, SHP: 2, SOG: 295, HIT: 35, BLK: 18, PIM: 24, "+/-": 26, FOW: 780, FOL: 590 }, matchupGames: 4 },
  { name: "David Pastrnak", position: "RW", eligiblePositions: ["RW"], secondaryPositions: [{ position: "LW", gamesPlayed: 8, acquired: false }], team: "BOS", points: 118, gamesPlayed: 62, dynastyValue: 8600, trend: "up", age: 27, contract: { salary: 11250000, yearsRemaining: 7, type: "Signed" }, statsByPeriod: { season: 118, "1d": 4, "7d": 14, "14d": 26, "30d": 48, "60d": 80, "100d": 108 }, categoryBreakdown: { G: 44, A: 48, PPP: 32, SHP: 1, SOG: 330, HIT: 20, BLK: 8, PIM: 16, "+/-": 20, FOW: 10, FOL: 8 }, matchupGames: 3 },
  { name: "Kirill Kaprizov", position: "LW", eligiblePositions: ["LW", "RW"], secondaryPositions: [{ position: "RW", gamesPlayed: 25, acquired: true }], team: "MIN", points: 112, gamesPlayed: 60, dynastyValue: 8800, trend: "up", age: 27, contract: { salary: 9000000, yearsRemaining: 3, type: "Signed" }, statsByPeriod: { season: 112, "1d": 2, "7d": 13, "14d": 24, "30d": 46, "60d": 76, "100d": 102 }, categoryBreakdown: { G: 40, A: 46, PPP: 28, SHP: 2, SOG: 300, HIT: 32, BLK: 10, PIM: 20, "+/-": 18, FOW: 25, FOL: 20 }, matchupGames: 4 },
  { name: "Jack Hughes", position: "C", eligiblePositions: ["C"], secondaryPositions: [{ position: "LW", gamesPlayed: 10, acquired: false }], team: "NJD", points: 105, gamesPlayed: 58, dynastyValue: 8500, trend: "up", age: 23, contract: { salary: 8000000, yearsRemaining: 6, type: "Signed" }, statsByPeriod: { season: 105, "1d": 3, "7d": 12, "14d": 22, "30d": 42, "60d": 72, "100d": 95 }, categoryBreakdown: { G: 32, A: 50, PPP: 24, SHP: 1, SOG: 260, HIT: 18, BLK: 6, PIM: 12, "+/-": 14, FOW: 620, FOL: 480 }, matchupGames: 3 },
  { name: "Mikko Rantanen", position: "RW", eligiblePositions: ["RW", "LW"], secondaryPositions: [{ position: "LW", gamesPlayed: 30, acquired: true }], team: "COL", points: 110, gamesPlayed: 62, dynastyValue: 7900, trend: "stable", age: 27, contract: { salary: 9250000, yearsRemaining: 4, type: "Signed" }, statsByPeriod: { season: 110, "1d": 2, "7d": 13, "14d": 24, "30d": 44, "60d": 74, "100d": 100 }, categoryBreakdown: { G: 36, A: 48, PPP: 30, SHP: 0, SOG: 280, HIT: 40, BLK: 14, PIM: 18, "+/-": 22, FOW: 15, FOL: 12 }, matchupGames: 3 },
  { name: "Sebastian Aho", position: "C", eligiblePositions: ["C", "LW"], secondaryPositions: [{ position: "LW", gamesPlayed: 20, acquired: true }], team: "CAR", points: 95, gamesPlayed: 60, dynastyValue: 7600, trend: "stable", age: 27, contract: { salary: 8460000, yearsRemaining: 5, type: "Signed" }, statsByPeriod: { season: 95, "1d": 1, "7d": 11, "14d": 20, "30d": 38, "60d": 64, "100d": 85 }, categoryBreakdown: { G: 30, A: 42, PPP: 22, SHP: 3, SOG: 250, HIT: 28, BLK: 10, PIM: 14, "+/-": 16, FOW: 700, FOL: 540 }, matchupGames: 3 },
  { name: "Timo Meier", position: "LW", eligiblePositions: ["LW", "RW"], secondaryPositions: [{ position: "RW", gamesPlayed: 18, acquired: false }], team: "NJD", points: 82, gamesPlayed: 58, dynastyValue: 6800, trend: "down", age: 27, contract: { salary: 8800000, yearsRemaining: 6, type: "Signed" }, statsByPeriod: { season: 82, "1d": 1, "7d": 9, "14d": 16, "30d": 32, "60d": 56, "100d": 74 }, categoryBreakdown: { G: 28, A: 32, PPP: 18, SHP: 1, SOG: 240, HIT: 120, BLK: 18, PIM: 42, "+/-": 6, FOW: 8, FOL: 6 }, matchupGames: 4 },
  { name: "Rasmus Dahlin", position: "D", eligiblePositions: ["D"], secondaryPositions: [], team: "BUF", points: 72, gamesPlayed: 58, dynastyValue: 7800, trend: "up", age: 24, contract: { salary: 10900000, yearsRemaining: 7, type: "Signed" }, statsByPeriod: { season: 72, "1d": 1, "7d": 8, "14d": 14, "30d": 28, "60d": 50, "100d": 65 }, categoryBreakdown: { G: 14, A: 42, PPP: 22, SHP: 0, SOG: 190, HIT: 38, BLK: 78, PIM: 14, "+/-": 8, FOW: 0, FOL: 0 }, matchupGames: 3 },
  { name: "Adam Fox", position: "D", eligiblePositions: ["D"], secondaryPositions: [], team: "NYR", points: 80, gamesPlayed: 60, dynastyValue: 8200, trend: "stable", age: 26, contract: { salary: 9500000, yearsRemaining: 5, type: "Signed" }, statsByPeriod: { season: 80, "1d": 2, "7d": 9, "14d": 16, "30d": 32, "60d": 56, "100d": 72 }, categoryBreakdown: { G: 10, A: 54, PPP: 28, SHP: 0, SOG: 170, HIT: 24, BLK: 82, PIM: 12, "+/-": 20, FOW: 0, FOL: 0 }, matchupGames: 4 },
  { name: "Andrei Vasilevskiy", position: "G", eligiblePositions: ["G"], secondaryPositions: [], team: "TBL", points: 70, gamesPlayed: 50, dynastyValue: 6800, trend: "stable", age: 30, contract: { salary: 9500000, yearsRemaining: 4, type: "Signed" }, statsByPeriod: { season: 70, "1d": 0, "7d": 7, "14d": 12, "30d": 28, "60d": 48, "100d": 62 }, categoryBreakdown: { G: 0, A: 1, PPP: 0, SHP: 0, SOG: 0, HIT: 0, BLK: 0, PIM: 2, "+/-": 0, FOW: 0, FOL: 0 }, matchupGames: 2 },
  { name: "Miro Heiskanen", position: "D", eligiblePositions: ["D"], secondaryPositions: [], team: "DAL", points: 74, gamesPlayed: 60, dynastyValue: 8000, trend: "up", age: 25, contract: { salary: 8450000, yearsRemaining: 6, type: "Signed" }, statsByPeriod: { season: 74, "1d": 1, "7d": 8, "14d": 14, "30d": 30, "60d": 52, "100d": 66 }, categoryBreakdown: { G: 12, A: 44, PPP: 20, SHP: 1, SOG: 180, HIT: 36, BLK: 92, PIM: 10, "+/-": 24, FOW: 0, FOL: 0 }, matchupGames: 3 },
  { name: "Tim Stützle", position: "C", eligiblePositions: ["C", "LW"], secondaryPositions: [{ position: "LW", gamesPlayed: 22, acquired: true }], team: "OTT", points: 88, gamesPlayed: 60, dynastyValue: 7400, trend: "up", age: 22, contract: { salary: 8350000, yearsRemaining: 7, type: "Signed" }, statsByPeriod: { season: 88, "1d": 2, "7d": 10, "14d": 18, "30d": 36, "60d": 60, "100d": 78 }, categoryBreakdown: { G: 26, A: 40, PPP: 20, SHP: 1, SOG: 220, HIT: 22, BLK: 8, PIM: 16, "+/-": 10, FOW: 580, FOL: 460 }, matchupGames: 4 },
  { name: "Jake Oettinger", position: "G", eligiblePositions: ["G"], secondaryPositions: [], team: "DAL", points: 65, gamesPlayed: 48, dynastyValue: 6200, trend: "up", age: 25, contract: { salary: 4000000, yearsRemaining: 2, type: "RFA" }, statsByPeriod: { season: 65, "1d": 0, "7d": 6, "14d": 12, "30d": 26, "60d": 44, "100d": 58 }, categoryBreakdown: { G: 0, A: 1, PPP: 0, SHP: 0, SOG: 0, HIT: 0, BLK: 0, PIM: 0, "+/-": 0, FOW: 0, FOL: 0 }, matchupGames: 3 },
  { name: "Trevor Zegras", position: "C", eligiblePositions: ["C", "LW"], secondaryPositions: [{ position: "LW", gamesPlayed: 15, acquired: false }], team: "ANA", points: 58, gamesPlayed: 55, dynastyValue: 6000, trend: "down", age: 23, contract: { salary: 5750000, yearsRemaining: 2, type: "RFA" }, statsByPeriod: { season: 58, "1d": 1, "7d": 7, "14d": 12, "30d": 24, "60d": 40, "100d": 52 }, categoryBreakdown: { G: 18, A: 28, PPP: 14, SHP: 0, SOG: 180, HIT: 14, BLK: 4, PIM: 10, "+/-": -4, FOW: 420, FOL: 380 }, matchupGames: 3 },
  { name: "Moritz Seider", position: "D", eligiblePositions: ["D"], secondaryPositions: [], team: "DET", points: 62, gamesPlayed: 56, dynastyValue: 7200, trend: "up", age: 23, contract: { salary: 7875000, yearsRemaining: 6, type: "Signed" }, statsByPeriod: { season: 62, "1d": 1, "7d": 7, "14d": 12, "30d": 24, "60d": 42, "100d": 56 }, categoryBreakdown: { G: 8, A: 36, PPP: 14, SHP: 1, SOG: 160, HIT: 140, BLK: 120, PIM: 28, "+/-": 6, FOW: 0, FOL: 0 }, matchupGames: 4 },
  { name: "Juuse Saros", position: "G", eligiblePositions: ["G"], secondaryPositions: [], team: "NSH", points: 68, gamesPlayed: 50, dynastyValue: 6400, trend: "stable", age: 29, contract: { salary: 5000000, yearsRemaining: 2, type: "UFA" }, statsByPeriod: { season: 68, "1d": 0, "7d": 7, "14d": 12, "30d": 26, "60d": 46, "100d": 60 }, categoryBreakdown: { G: 0, A: 2, PPP: 0, SHP: 0, SOG: 0, HIT: 0, BLK: 0, PIM: 2, "+/-": 0, FOW: 0, FOL: 0 }, matchupGames: 2 },
  { name: "Matthew Tkachuk", position: "LW", eligiblePositions: ["LW", "RW"], secondaryPositions: [{ position: "RW", gamesPlayed: 26, acquired: true }], team: "FLA", points: 102, gamesPlayed: 60, dynastyValue: 8100, trend: "up", age: 26, contract: { salary: 9500000, yearsRemaining: 6, type: "Signed" }, statsByPeriod: { season: 102, "1d": 2, "7d": 12, "14d": 22, "30d": 42, "60d": 70, "100d": 92 }, categoryBreakdown: { G: 30, A: 48, PPP: 24, SHP: 2, SOG: 260, HIT: 160, BLK: 20, PIM: 88, "+/-": 16, FOW: 40, FOL: 32 }, matchupGames: 3 },
  { name: "Jason Robertson", position: "LW", eligiblePositions: ["LW"], secondaryPositions: [{ position: "RW", gamesPlayed: 6, acquired: false }], team: "DAL", points: 96, gamesPlayed: 60, dynastyValue: 7500, trend: "stable", age: 25, contract: { salary: 7750000, yearsRemaining: 3, type: "Signed" }, statsByPeriod: { season: 96, "1d": 2, "7d": 11, "14d": 20, "30d": 38, "60d": 66, "100d": 86 }, categoryBreakdown: { G: 34, A: 40, PPP: 22, SHP: 1, SOG: 270, HIT: 24, BLK: 8, PIM: 12, "+/-": 14, FOW: 12, FOL: 10 }, matchupGames: 4 },
  { name: "Elias Pettersson", position: "C", eligiblePositions: ["C"], secondaryPositions: [{ position: "LW", gamesPlayed: 12, acquired: false }], team: "VAN", points: 90, gamesPlayed: 60, dynastyValue: 7800, trend: "down", age: 25, contract: { salary: 11600000, yearsRemaining: 7, type: "Signed" }, statsByPeriod: { season: 90, "1d": 1, "7d": 10, "14d": 18, "30d": 36, "60d": 62, "100d": 80 }, categoryBreakdown: { G: 28, A: 42, PPP: 22, SHP: 2, SOG: 230, HIT: 16, BLK: 6, PIM: 14, "+/-": 10, FOW: 680, FOL: 520 }, matchupGames: 3 },
  { name: "Zach Werenski", position: "D", eligiblePositions: ["D"], secondaryPositions: [], team: "CBJ", points: 70, gamesPlayed: 58, dynastyValue: 7000, trend: "up", age: 27, contract: { salary: 9583000, yearsRemaining: 5, type: "Signed" }, statsByPeriod: { season: 70, "1d": 1, "7d": 8, "14d": 14, "30d": 28, "60d": 48, "100d": 62 }, categoryBreakdown: { G: 16, A: 38, PPP: 20, SHP: 0, SOG: 200, HIT: 30, BLK: 70, PIM: 18, "+/-": 2, FOW: 0, FOL: 0 }, matchupGames: 3 },
  { name: "Wyatt Johnston", position: "C", eligiblePositions: ["C"], secondaryPositions: [{ position: "RW", gamesPlayed: 8, acquired: false }], team: "DAL", points: 72, gamesPlayed: 58, dynastyValue: 7200, trend: "up", age: 21, contract: { salary: 925000, yearsRemaining: 1, type: "ELC" }, statsByPeriod: { season: 72, "1d": 2, "7d": 8, "14d": 14, "30d": 28, "60d": 50, "100d": 64 }, categoryBreakdown: { G: 24, A: 32, PPP: 14, SHP: 1, SOG: 200, HIT: 26, BLK: 10, PIM: 10, "+/-": 12, FOW: 540, FOL: 420 }, matchupGames: 4 },
  { name: "Luke Hughes", position: "D", eligiblePositions: ["D"], secondaryPositions: [], team: "NJD", points: 58, gamesPlayed: 55, dynastyValue: 7400, trend: "up", age: 21, contract: { salary: 925000, yearsRemaining: 1, type: "ELC" }, statsByPeriod: { season: 58, "1d": 1, "7d": 6, "14d": 12, "30d": 22, "60d": 40, "100d": 52 }, categoryBreakdown: { G: 10, A: 32, PPP: 14, SHP: 0, SOG: 160, HIT: 44, BLK: 68, PIM: 12, "+/-": 8, FOW: 0, FOL: 0 }, matchupGames: 3 },
  { name: "Alexandar Georgiev", position: "G", eligiblePositions: ["G"], secondaryPositions: [], team: "COL", points: 55, gamesPlayed: 45, dynastyValue: 4800, trend: "down", age: 28, contract: { salary: 3400000, yearsRemaining: 2, type: "UFA" }, statsByPeriod: { season: 55, "1d": 0, "7d": 5, "14d": 10, "30d": 22, "60d": 38, "100d": 48 }, categoryBreakdown: { G: 0, A: 0, PPP: 0, SHP: 0, SOG: 0, HIT: 0, BLK: 0, PIM: 2, "+/-": 0, FOW: 0, FOL: 0 }, matchupGames: 2 },
  { name: "Cole Caufield", position: "RW", eligiblePositions: ["RW"], secondaryPositions: [{ position: "LW", gamesPlayed: 4, acquired: false }], team: "MTL", points: 85, gamesPlayed: 60, dynastyValue: 7000, trend: "up", age: 23, contract: { salary: 7850000, yearsRemaining: 7, type: "Signed" }, statsByPeriod: { season: 85, "1d": 2, "7d": 10, "14d": 18, "30d": 34, "60d": 58, "100d": 76 }, categoryBreakdown: { G: 36, A: 28, PPP: 20, SHP: 1, SOG: 290, HIT: 12, BLK: 4, PIM: 8, "+/-": 8, FOW: 6, FOL: 4 }, matchupGames: 4 },
  { name: "Brock Boeser", position: "RW", eligiblePositions: ["RW"], secondaryPositions: [], team: "VAN", points: 78, gamesPlayed: 58, dynastyValue: 5600, trend: "stable", age: 27, contract: { salary: 6650000, yearsRemaining: 3, type: "Signed" }, statsByPeriod: { season: 78, "1d": 1, "7d": 9, "14d": 16, "30d": 32, "60d": 54, "100d": 70 }, categoryBreakdown: { G: 30, A: 30, PPP: 18, SHP: 0, SOG: 250, HIT: 20, BLK: 6, PIM: 10, "+/-": 6, FOW: 4, FOL: 3 }, matchupGames: 3 },
  { name: "Logan Cooley", position: "C", eligiblePositions: ["C"], secondaryPositions: [{ position: "LW", gamesPlayed: 5, acquired: false }], team: "ARI", points: 48, gamesPlayed: 50, dynastyValue: 7600, trend: "up", age: 20, contract: { salary: 925000, yearsRemaining: 2, type: "ELC" }, statsByPeriod: { season: 48, "1d": 1, "7d": 6, "14d": 10, "30d": 20, "60d": 34, "100d": 44 }, categoryBreakdown: { G: 14, A: 22, PPP: 10, SHP: 0, SOG: 150, HIT: 16, BLK: 4, PIM: 8, "+/-": 0, FOW: 380, FOL: 340 }, matchupGames: 3 },
  { name: "Lane Hutson", position: "D", eligiblePositions: ["D"], secondaryPositions: [], team: "MTL", points: 42, gamesPlayed: 38, dynastyValue: 7000, trend: "up", age: 20, contract: { salary: 925000, yearsRemaining: 2, type: "ELC" }, statsByPeriod: { season: 42, "1d": 1, "7d": 5, "14d": 8, "30d": 16, "60d": 28, "100d": 38 }, categoryBreakdown: { G: 6, A: 26, PPP: 12, SHP: 0, SOG: 120, HIT: 18, BLK: 52, PIM: 6, "+/-": 4, FOW: 0, FOL: 0 }, matchupGames: 4 },
];

export const slotLabels = LEAGUE_ROSTER_SLOTS.map((s) => s.label);

export const generateTeamRoster = (teamId: string, seed: number): Player[] => {
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

// ── Weekly matchups ────────────────────────────────────
export interface WeekMatchup {
  week: number;
  opponent: string;
  opponentFull: string;
  score: { mine: number; theirs: number };
  result: "W" | "L";
}

export const weeklyMatchups: WeekMatchup[] = [
  { week: 1, opponent: "ICE", opponentFull: "Ice Dragons", score: { mine: 412, theirs: 388 }, result: "W" },
  { week: 2, opponent: "BLZ", opponentFull: "Blazers", score: { mine: 380, theirs: 395 }, result: "L" },
  { week: 3, opponent: "THU", opponentFull: "Thunder", score: { mine: 425, theirs: 410 }, result: "W" },
  { week: 4, opponent: "WLV", opponentFull: "Wolverines", score: { mine: 398, theirs: 372 }, result: "W" },
  { week: 5, opponent: "PHX", opponentFull: "Phoenix", score: { mine: 445, theirs: 420 }, result: "W" },
  { week: 6, opponent: "STM", opponentFull: "Storm Chasers", score: { mine: 390, theirs: 402 }, result: "L" },
  { week: 7, opponent: "VPR", opponentFull: "Vipers", score: { mine: 0, theirs: 0 }, result: "W" },
];

export const currentWeek = 7;
