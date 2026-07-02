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

// Iter 232L.4 — Rate stats can't be summed. For save-% / goals-against-
// average we surface a games-weighted average across the goalies on that
// side. Everything else is treated as a counting stat (sum).
const RATE_STAT_KEYS = new Set(["save_pct", "goals_against_avg"]);

/**
 * Compute per-side totals for the totals row rendered under each trade
 * table. Returns { capHit, gp, fpts, fptsPerGame, categories: {key:num} }.
 * Counting stats are summed; rate stats (save%, GAA) are weighted by GP.
 * FP/G is derived from total FPts / total GP so a low-GP player doesn't
 * distort the aggregate.
 */
export function computeAssetTotals(
  assets: TradeAsset[],
  categories: ScoringCategoryDef[],
): {
  capHit: number;
  gp: number;
  fpts: number;
  fptsPerGame: number;
  categories: Record<string, number>;
  hasPlayers: boolean;
} {
  const totals = {
    capHit: 0,
    gp: 0,
    fpts: 0,
    fptsPerGame: 0,
    categories: {} as Record<string, number>,
    hasPlayers: false,
  };
  // For each rate stat we track a weighted numerator + total GP so we can
  // finalise the average after the loop.
  const rateNumerators: Record<string, number> = {};
  const rateGpTotals: Record<string, number> = {};
  for (const a of assets) {
    if (a.type !== "player") continue;
    totals.hasPlayers = true;
    totals.capHit += Number((a as any).salary || 0);
    const gp = Number(a.gamesPlayed || 0);
    totals.gp += gp;
    totals.fpts += Number(a.fantasyPts || 0);
    for (const c of categories) {
      const v = Number(a.statCategories?.[c.key]?.value ?? 0);
      if (RATE_STAT_KEYS.has(c.key)) {
        rateNumerators[c.key] = (rateNumerators[c.key] || 0) + v * gp;
        rateGpTotals[c.key] = (rateGpTotals[c.key] || 0) + gp;
      } else {
        totals.categories[c.key] = (totals.categories[c.key] || 0) + v;
      }
    }
  }
  totals.fptsPerGame = totals.gp > 0 ? totals.fpts / totals.gp : 0;
  // Finalise rate-stat weighted averages
  for (const key of Object.keys(rateNumerators)) {
    const gp = rateGpTotals[key] || 0;
    totals.categories[key] = gp > 0 ? rateNumerators[key] / gp : 0;
  }
  return totals;
}

/**
 * Format a category total for display. Rate stats get the same 3-decimal
 * (save%) or 2-decimal (GAA) formatting they'd have on a player page.
 */
export function formatCategoryTotal(key: string, value: number): string {
  if (key === "save_pct") return value ? value.toFixed(3) : "—";
  if (key === "goals_against_avg") return value ? value.toFixed(2) : "—";
  // Everything else is a counting stat — integer sum.
  return Number.isFinite(value) ? String(Math.round(value)) : "—";
}
