/**
 * Iter 229 — Mock data extracted from DraftRoom.tsx.
 *
 * These constants are used ONLY as fallbacks when no live league is
 * active or the API is offline. The Draft Room's primary data path is
 * live (Socket.IO + /api/drafts), so this file should rarely be hit in
 * production traffic — keeping it isolated here lets tests assert on
 * the mock identities without scrolling past 200 lines of constants.
 */
import type { DraftEligiblePlayer } from "./types";

export const mockLeagueTeams = [
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

export const draftCriteria = [
  { value: "entry", label: "NHL Entry Draft", description: "Players aged 18-20 who have not been previously drafted by an NHL team. Includes CHL, European, and college players eligible for the first time." },
  { value: "rookies", label: "Rookies Only", description: "Players who have not played more than 25 games in any single preceding season or 6+ games in each of any two preceding seasons in the NHL." },
  { value: "prospects", label: "Prospects Only", description: "Players currently developing in junior, college, or minor professional leagues who have not yet established themselves on an NHL roster." },
  { value: "unsigned", label: "Unsigned / Draft Eligible", description: "Players who are currently without an NHL contract, including undrafted free agents and draft-eligible players whose rights have expired." },
  { value: "all", label: "All Players", description: "No restrictions. All players in the database are eligible to be selected regardless of age, contract status, or league affiliation." },
];

export const mockEligiblePlayers: DraftEligiblePlayer[] = [
  { id: "e1", name: "James Hagens", position: "C", nhlTeam: "—", age: 17, league: "NTDP", gp: 52, g: 28, a: 42, pts: 70, ranking: 1, drafted: false },
  { id: "e2", name: "Porter Martone", position: "RW", nhlTeam: "—", age: 17, league: "OHL", gp: 60, g: 38, a: 40, pts: 78, ranking: 2, drafted: false },
  { id: "e3", name: "Ivan Ryabkin", position: "C", nhlTeam: "—", age: 17, league: "KHL", gp: 48, g: 18, a: 30, pts: 48, ranking: 3, drafted: false },
  { id: "e4", name: "Cameron Schmidt", position: "C", nhlTeam: "—", age: 17, league: "WHL", gp: 58, g: 45, a: 38, pts: 83, ranking: 4, drafted: false },
  { id: "e5", name: "Lukas Fischer", position: "D", nhlTeam: "—", age: 17, league: "SHL", gp: 44, g: 8, a: 28, pts: 36, ranking: 5, drafted: false },
  { id: "e6", name: "Cole Reschny", position: "C", nhlTeam: "—", age: 17, league: "WHL", gp: 62, g: 30, a: 42, pts: 72, ranking: 6, drafted: false },
  { id: "e7", name: "Linus Eriksson", position: "LW", nhlTeam: "—", age: 18, league: "SHL", gp: 50, g: 22, a: 30, pts: 52, ranking: 7, drafted: false },
  { id: "e8", name: "Roger McQueen", position: "C", nhlTeam: "—", age: 17, league: "OHL", gp: 56, g: 40, a: 32, pts: 72, ranking: 8, drafted: false },
  { id: "e9", name: "Jack Macgregor", position: "D", nhlTeam: "—", age: 17, league: "OHL", gp: 60, g: 12, a: 38, pts: 50, ranking: 9, drafted: false },
  { id: "e10", name: "Jonathan Morello", position: "RW", nhlTeam: "—", age: 17, league: "OHL", gp: 58, g: 35, a: 28, pts: 63, ranking: 10, drafted: false },
  { id: "e11", name: "Austin Burnevik", position: "C", nhlTeam: "—", age: 18, league: "NCAA", gp: 40, g: 24, a: 30, pts: 54, ranking: 11, drafted: false },
  { id: "e12", name: "Vac Vojtech", position: "G", nhlTeam: "—", age: 17, league: "CZE", gp: 34, g: 0, a: 2, pts: 2, ranking: 12, drafted: false },
  { id: "e13", name: "Blake Fiddler", position: "D", nhlTeam: "—", age: 17, league: "WHL", gp: 62, g: 10, a: 32, pts: 42, ranking: 13, drafted: false },
  { id: "e14", name: "Adam Jecho", position: "C", nhlTeam: "—", age: 18, league: "OHL", gp: 58, g: 26, a: 36, pts: 62, ranking: 14, drafted: false },
  { id: "e15", name: "Alex Huang", position: "LW", nhlTeam: "—", age: 17, league: "USHL", gp: 54, g: 28, a: 26, pts: 54, ranking: 15, drafted: false },
  { id: "e16", name: "Ben Merrill", position: "D", nhlTeam: "—", age: 18, league: "NCAA", gp: 38, g: 6, a: 24, pts: 30, ranking: 16, drafted: false },
  { id: "e17", name: "Dmitri Petrov", position: "RW", nhlTeam: "—", age: 17, league: "MHL", gp: 50, g: 20, a: 22, pts: 42, ranking: 17, drafted: false },
  { id: "e18", name: "William Chen", position: "C", nhlTeam: "—", age: 17, league: "QMJHL", gp: 60, g: 22, a: 38, pts: 60, ranking: 18, drafted: false },
  { id: "e19", name: "Oscar Nilsson", position: "G", nhlTeam: "—", age: 18, league: "SHL", gp: 30, g: 0, a: 1, pts: 1, ranking: 19, drafted: false },
  { id: "e20", name: "Marcus Lindqvist", position: "LW", nhlTeam: "—", age: 17, league: "FIN", gp: 48, g: 18, a: 24, pts: 42, ranking: 20, drafted: false },
  { id: "e21", name: "Nolan Reid", position: "D", nhlTeam: "—", age: 18, league: "OHL", gp: 62, g: 8, a: 30, pts: 38, ranking: 21, drafted: false },
  { id: "e22", name: "Filip Andersson", position: "RW", nhlTeam: "—", age: 17, league: "SHL", gp: 46, g: 16, a: 20, pts: 36, ranking: 22, drafted: false },
  { id: "e23", name: "Tyler Walsh", position: "C", nhlTeam: "—", age: 18, league: "WHL", gp: 56, g: 20, a: 28, pts: 48, ranking: 23, drafted: false },
  { id: "e24", name: "Erik Sundberg", position: "D", nhlTeam: "—", age: 17, league: "SHL", gp: 42, g: 4, a: 18, pts: 22, ranking: 24, drafted: false },
  { id: "e25", name: "Jake Morrison", position: "G", nhlTeam: "—", age: 17, league: "OHL", gp: 44, g: 0, a: 1, pts: 1, ranking: 25, drafted: false },
  { id: "e26", name: "Ryan Thompson", position: "LW", nhlTeam: "—", age: 18, league: "USHL", gp: 52, g: 24, a: 20, pts: 44, ranking: 26, drafted: false },
  { id: "e27", name: "Max Dubois", position: "C", nhlTeam: "—", age: 17, league: "QMJHL", gp: 58, g: 18, a: 34, pts: 52, ranking: 27, drafted: false },
  { id: "e28", name: "Sami Korhonen", position: "D", nhlTeam: "—", age: 18, league: "FIN", gp: 46, g: 6, a: 22, pts: 28, ranking: 28, drafted: false },
  { id: "e29", name: "Connor Blake", position: "RW", nhlTeam: "—", age: 17, league: "WHL", gp: 60, g: 26, a: 22, pts: 48, ranking: 29, drafted: false },
  { id: "e30", name: "Alexei Volkov", position: "G", nhlTeam: "—", age: 18, league: "KHL", gp: 28, g: 0, a: 0, pts: 0, ranking: 30, drafted: false },
];

export const myRoster = [
  { name: "Connor McDavid", position: "C", pts: 128 },
  { name: "Leon Draisaitl", position: "C", pts: 110 },
  { name: "Cale Makar", position: "D", pts: 86 },
  { name: "Artemi Panarin", position: "LW", pts: 96 },
  { name: "Mika Zibanejad", position: "C", pts: 72 },
  { name: "Seth Jones", position: "D", pts: 52 },
  { name: "Jake Oettinger", position: "G", pts: 44 },
  { name: "Tage Thompson", position: "C", pts: 78 },
  { name: "Rasmus Dahlin", position: "D", pts: 64 },
  { name: "Andrei Svechnikov", position: "RW", pts: 74 },
];
