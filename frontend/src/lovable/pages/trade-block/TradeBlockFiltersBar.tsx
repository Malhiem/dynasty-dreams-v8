// Iter 230i — Filters + view-toggle bar extracted from TradeBlock.tsx.
// Stateless: receives the current filter values + setters, plus the
// prefs hook's `viewMode/hiddenIds/clearHidden` for the view toggle.
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Filter, LayoutGrid, List as ListIcon, Eye } from "lucide-react";

type Props = {
  positions: readonly string[];
  realOwners: string[];
  positionFilter: string;
  setPositionFilter: (v: string) => void;
  ownerFilter: string;
  setOwnerFilter: (v: string) => void;
  visibleCount: number;
  hiddenCountAfterFilters: number;
  viewMode: "tile" | "list";
  setViewMode: (m: "tile" | "list") => void;
  hiddenIds: number[];
  clearHidden: () => void;
};

export default function TradeBlockFiltersBar({
  positions,
  realOwners,
  positionFilter,
  setPositionFilter,
  ownerFilter,
  setOwnerFilter,
  visibleCount,
  hiddenCountAfterFilters,
  viewMode,
  setViewMode,
  hiddenIds,
  clearHidden,
}: Props) {
  return (
    <div className="flex items-center gap-4 mb-4">
      <div className="flex items-center gap-2">
        <Filter className="h-4 w-4 text-muted-foreground" />
        <span className="text-sm text-muted-foreground">Filter:</span>
      </div>
      <Select value={positionFilter} onValueChange={setPositionFilter}>
        <SelectTrigger className="w-36 bg-secondary border-border">
          <SelectValue placeholder="Position" />
        </SelectTrigger>
        <SelectContent>
          {positions.map((pos) => (
            <SelectItem key={pos} value={pos}>
              {pos === "All" ? "All Positions" : pos}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <Select value={ownerFilter} onValueChange={setOwnerFilter}>
        <SelectTrigger
          className="w-44 bg-secondary border-border"
          data-testid="trade-block-owner-filter"
        >
          <SelectValue placeholder="Team" />
        </SelectTrigger>
        <SelectContent>
          {realOwners.map((owner) => (
            <SelectItem key={owner} value={owner}>
              {owner}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <Badge variant="outline" className="ml-auto" data-testid="trade-block-count">
        {visibleCount} items
        {hiddenCountAfterFilters > 0 && (
          <span className="ml-1 text-muted-foreground/70">
            · {hiddenCountAfterFilters} hidden
          </span>
        )}
      </Badge>
      {/* View toggle — list ↔ tile. Selection persists per-league. */}
      <div
        className="inline-flex items-center rounded-md border border-border bg-secondary/40 overflow-hidden"
        data-testid="trade-block-view-toggle"
      >
        <button
          type="button"
          onClick={() => setViewMode("tile")}
          data-testid="trade-block-view-tile"
          aria-pressed={viewMode === "tile"}
          className={`flex items-center gap-1 px-2.5 py-1 text-xs ${
            viewMode === "tile"
              ? "bg-primary/15 text-primary"
              : "text-muted-foreground hover:text-foreground"
          }`}
          title="Tile view"
        >
          <LayoutGrid className="h-3.5 w-3.5" /> Tile
        </button>
        <button
          type="button"
          onClick={() => setViewMode("list")}
          data-testid="trade-block-view-list"
          aria-pressed={viewMode === "list"}
          className={`flex items-center gap-1 px-2.5 py-1 text-xs border-l border-border ${
            viewMode === "list"
              ? "bg-primary/15 text-primary"
              : "text-muted-foreground hover:text-foreground"
          }`}
          title="List view"
        >
          <ListIcon className="h-3.5 w-3.5" /> List
        </button>
      </div>
      {viewMode === "tile" && hiddenIds.length > 0 && (
        <Button
          variant="ghost"
          size="sm"
          onClick={clearHidden}
          data-testid="trade-block-show-hidden"
          className="text-xs h-7"
        >
          <Eye className="h-3.5 w-3.5 mr-1" />
          Show {hiddenIds.length} hidden
        </Button>
      )}
    </div>
  );
}
