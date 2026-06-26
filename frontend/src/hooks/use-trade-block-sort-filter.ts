// Iter 230j — TradeBlock sort + filter + hidden-cards pipeline extracted
// from TradeBlock.tsx. Pure derivation — no side effects. List view
// honours the user's sortable column + direction; tile view always
// orders highest-FP → prospect → pick (sortable columns make sense
// only in table mode) and filters out user-hidden cards.
import { useMemo } from "react";
import type { TradeBlockItem } from "@/lovable/pages/trade-block/types";
import { tradeBlockItemsMock } from "@/lovable/pages/trade-block/mocks";

type Args = {
  realTradeItems: TradeBlockItem[];
  positionFilter: string;
  ownerFilter: string;
  viewMode: "tile" | "list";
  sort: { key: string; dir: "asc" | "desc" } | undefined;
  isHidden: (id: number | string) => boolean;
};

export default function useTradeBlockSortFilter({
  realTradeItems,
  positionFilter,
  ownerFilter,
  viewMode,
  sort,
  isHidden,
}: Args) {
  const sortedAndFilteredItems = useMemo(() => {
    // Prefer live items; fall back to seeded mock when league has no entries.
    let items: TradeBlockItem[] =
      realTradeItems.length > 0 ? [...realTradeItems] : [...tradeBlockItemsMock];

    if (positionFilter !== "All") {
      if (positionFilter === "Prospect") {
        items = items.filter((item) => item.type === "prospect");
      } else if (positionFilter === "Pick") {
        items = items.filter((item) => item.type === "pick");
      } else {
        items = items.filter(
          (item) => item.position === positionFilter && item.type === "player",
        );
      }
    }

    if (ownerFilter !== "All Teams") {
      items = items.filter((item) => item.owner === ownerFilter);
    }

    if (viewMode === "list") {
      const { key, dir } = sort || { key: "weeklyPoints", dir: "desc" };
      const factor = dir === "asc" ? 1 : -1;
      items.sort((a, b) => {
        const av = (a as any)[key];
        const bv = (b as any)[key];
        if (typeof av === "string" || typeof bv === "string") {
          return String(av || "").localeCompare(String(bv || "")) * factor;
        }
        return ((av ?? 0) - (bv ?? 0)) * factor;
      });
    } else {
      const typeOrder = { player: 0, prospect: 1, pick: 2 } as const;
      items.sort((a, b) => {
        if (typeOrder[a.type] !== typeOrder[b.type]) {
          return typeOrder[a.type] - typeOrder[b.type];
        }
        if (a.type === "player" && b.type === "player") {
          return (b.weeklyPoints || 0) - (a.weeklyPoints || 0);
        }
        return b.dynastyValue - a.dynastyValue;
      });
    }

    return items;
  }, [realTradeItems, positionFilter, ownerFilter, viewMode, sort]);

  // Tile view honours the per-league hidden list; list view always shows all.
  const visibleItems = useMemo(() => {
    if (viewMode !== "tile") return sortedAndFilteredItems;
    return sortedAndFilteredItems.filter((it) => !isHidden(it.id));
  }, [sortedAndFilteredItems, viewMode, isHidden]);

  const hiddenCountAfterFilters =
    sortedAndFilteredItems.length - visibleItems.length;

  return { sortedAndFilteredItems, visibleItems, hiddenCountAfterFilters };
}
