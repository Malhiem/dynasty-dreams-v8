// @ts-nocheck
// Iter 232L (refactor) — Types + tiny helpers shared by every transactions
// component. Kept as a single file so the surface a downstream consumer
// has to reason about is one import.

export interface StatCategory {
  label: string;
  value: number;
}

export interface TradeAsset {
  name: string;
  position: string;
  age: number;
  capHit: string;
  goals: number;
  assists: number;
  points: number;
  fantasyPts: number;
  fantasyPtsPerGame?: number;
  gamesPlayed?: number;
  statCategories?: Record<string, StatCategory>;
  playerType?: string;
  type: "player" | "pick";
  minorEligible?: boolean;
}

export interface ScoringCategoryDef {
  key: string;
  label: string;
}
export interface ScoringCategoriesMap {
  skater: ScoringCategoryDef[];
  goalie: ScoringCategoryDef[];
}

export interface PendingTrade {
  id: string;
  teamA: string;
  teamB: string;
  assetsFromA: TradeAsset[];
  assetsFromB: TradeAsset[];
  status: "pending" | "accepted" | "vetoed" | "processed" | string;
  submittedAt: string;
  processesAt: string;
  votes: { approve: number; veto: number; total: number };
  salaryRetained?: { team: string; amount: string; duration: string };
  yourVote?: "approve" | "veto" | null;
  vetoThreshold?: number;
  onVote?: (vote: "approve" | "veto") => void;
  scoringCategories?: ScoringCategoriesMap;
}

// FPts (season + per-game) vs Categories (dynamic per-league scoring stats).
export type StatViewMode = "fpts" | "categories";

/** Format cap hit as "$X.XM" / "$XXXk" / "—". */
export function fmtCapHit(salary: number | undefined | null): string {
  if (!salary || salary <= 0) return "—";
  if (salary >= 1_000_000) return `$${(salary / 1_000_000).toFixed(2)}M`;
  if (salary >= 1_000) return `$${Math.round(salary / 1_000)}k`;
  return `$${salary}`;
}

/**
 * Derive the ordered list of counting-category columns to render for a
 * trade card given the league's scoring config and which player types
 * appear on the card. Skater cats come first, goalie cats appended when
 * the card contains a goalie.
 */
export function selectCategoriesForAssets(
  assets: TradeAsset[],
  categories?: ScoringCategoriesMap,
): ScoringCategoryDef[] {
  if (!categories) return [];
  const hasGoalie = assets.some(
    (a) => a.type === "player" && (a.playerType === "goalie" || a.position === "G"),
  );
  const hasSkater = assets.some(
    (a) => a.type === "player" && a.playerType !== "goalie" && a.position !== "G",
  );
  return [
    ...(hasSkater ? categories.skater || [] : []),
    ...(hasGoalie ? categories.goalie || [] : []),
  ];
}
