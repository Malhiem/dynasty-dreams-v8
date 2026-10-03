// Iter 230i — Shared TradeBlock types. Lifted out of TradeBlock.tsx so
// the extracted child components (Card, ListView, FiltersBar,
// MyPlayersTab) can import from a single source of truth instead of
// re-declaring overlapping shapes.

export type ItemType = "player" | "prospect" | "pick";

export interface TradeBlockItem {
  id: number | string;
  name: string;
  position: string;
  team: string;
  team_id?: string;
  age?: number;
  dynastyValue: number;
  aav?: number | null;
  owner: string;
  owner_id?: string;
  ownerAvatar: string;
  // Iter 229k — Owner team's preset theme color (hex).
  ownerThemeColor?: string | null;
  lookingFor: string[];
  trend: "up" | "down" | "stable";
  weeklyPoints?: number;
  type: ItemType;
  year?: number;
  round?: string;
  // Skater stats
  gp?: number;
  g?: number;
  a?: number;
  plusMinus?: number;
  ppp?: number;
  shp?: number;
  gwg?: number;
  sog?: number;
  hit?: number;
  blk?: number;
  fow?: number;
  fol?: number;
  // Goalie stats
  w?: number;
  l?: number;
  sol?: number;
  sv?: number;
  ga?: number;
  so?: number;
}

export interface MyOnBlockPlayer {
  id: string;
  player_id: string;
  name: string;
  position: string;
  team: string;
  nhl_team?: string;
  lookingFor: string[];
  minor_eligible?: boolean;
  player_type?: string;
}
