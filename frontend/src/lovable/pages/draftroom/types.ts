/**
 * Iter 229 — Draft Room types extracted from DraftRoom.tsx so child
 * components can import them without dragging the whole 1500-line file
 * into their type graph.
 */

export interface DraftEligiblePlayer {
  id: string;
  name: string;
  position: string;
  nhlTeam: string;
  age: number;
  league: string;
  gp: number;
  g: number;
  a: number;
  pts: number;
  ranking: number;
  drafted: boolean;
  draftedBy?: string;
  draftedRound?: number;
  draftedPick?: number;
}

export interface DraftPick {
  round: number;
  pickInRound: number;
  overall: number;
  team: string;
  player?: DraftEligiblePlayer;
}

export interface DraftConfig {
  scheduledTime: Date | null;
  draftStarted: boolean;
  earlyStart: boolean;
  pickTimerSeconds: number;
  currentPick: number;
  totalRounds: number;
  snakeDraft: boolean;
}

export interface ChatMessage {
  id: string;
  type: "chat" | "pick";
  sender: string;
  text: string;
  timestamp: Date;
}
