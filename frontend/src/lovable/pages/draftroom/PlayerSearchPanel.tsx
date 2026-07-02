// @ts-nocheck
/**
 * Iter 171 — PlayerSearchPanel
 *
 * Extracted from the LEFT sidebar of DraftRoom.tsx. Wraps the three
 * stacked tabs that make up the player search experience:
 *   • Eligible — searchable + position-filtered list of all undrafted
 *     players (rendered exactly as it was inline in DraftRoom).
 *   • Queue    — drag-to-reorder auto-pick queue (SortableQueue).
 *   • Shortlist — drag-to-reorder shortlist with "Promote to Queue".
 *
 * Pure presentational shell: parent owns state. All side effects
 * (setQueue, setShortlist, toggleShortlist, toggleQueue, removeFromQueue,
 * setSelectedPlayerId) are forwarded via callback props.
 */
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Search, Star, ListOrdered, Megaphone, Sprout } from "lucide-react";
import { PlayerStatusBadges } from "@/components/player/PlayerStatusBadges";
import { cn } from "@/lib/utils";
import SortableQueue from "@/lovable/pages/draftroom/SortableQueue";

export default function PlayerSearchPanel({
  // Eligible-tab state
  filteredPlayers,
  searchQuery,
  setSearchQuery,
  positionFilter,
  setPositionFilter,
  // Iter 231al — Player-type segment ("all" | "nhl" | "prospects").
  // Optional so legacy callers that don't yet pass it default to "all".
  typeFilter = "all",
  setTypeFilter,
  // Iter 232N.2 — "Undrafted only" toggle. Optional; when the parent
  // wires it, a small chip appears next to the type filter.
  undraftedOnly = false,
  setUndraftedOnly,
  positions,
  positionColors,
  selectedPlayerId,
  setSelectedPlayerId,
  tradeBlockPlayerIds,
  // Iter 173 — league flag drives the "Minor-eligible" badge surfacing.
  minorsEnabled,
  // Queue / Shortlist state
  queue,
  shortlist,
  queuedPlayers,
  shortlistedPlayers,
  setQueue,
  setShortlist,
  toggleQueue,
  toggleShortlist,
  removeFromQueue,
}) {
  return (
    <Tabs defaultValue="eligible" className="w-full">
      <TabsList className="w-full grid grid-cols-3">
        <TabsTrigger value="eligible" data-testid="draft-room-tab-eligible">Eligible</TabsTrigger>
        <TabsTrigger value="queue" data-testid="draft-room-tab-queue">
          <ListOrdered className="h-3.5 w-3.5 mr-1" />
          Queue ({queue.length})
        </TabsTrigger>
        <TabsTrigger value="shortlist" data-testid="draft-room-tab-shortlist">
          <Star className="h-3.5 w-3.5 mr-1" />
          Shortlist ({shortlistedPlayers.length})
        </TabsTrigger>
      </TabsList>

      <TabsContent value="eligible" className="mt-3 space-y-3">
        <div className="flex gap-2">
          <div className="relative flex-1">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
            <Input
              placeholder="Search players..."
              className="pl-8 h-8 text-sm bg-secondary/50"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </div>
          <Select value={positionFilter} onValueChange={setPositionFilter}>
            <SelectTrigger className="w-[100px] h-8 text-xs bg-secondary/50">
              <SelectValue />
            </SelectTrigger>
            <SelectContent className="bg-popover border-border z-50">
              {positions.map((p) => (
                <SelectItem key={p.value} value={p.value}>{p.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="flex items-center justify-between gap-2 flex-wrap">
          <Badge variant="secondary" className="text-[10px]" data-testid="draft-room-eligible-count">
            {filteredPlayers.length} players available
          </Badge>
          <div className="flex items-center gap-2">
            {/* Iter 231al — Tri-segment player-type chip. Lets the user
                isolate NHL skaters / goalies, the prospect tier, or show
                both. Defaults to "All" so legacy behaviour is preserved.
                Each segment carries a dedicated testid for E2E driving. */}
            {setTypeFilter && (
              <div
                role="group"
                aria-label="Filter by player type"
                className="inline-flex items-center gap-0.5 rounded-md bg-secondary/40 p-0.5"
                data-testid="draft-room-eligible-type-filter"
              >
                {[
                  { id: "all", label: "All" },
                  { id: "nhl", label: "NHL" },
                  { id: "prospects", label: "Prospects" },
                ].map(({ id, label }) => {
                  const active = typeFilter === id;
                  return (
                    <button
                      key={id}
                      type="button"
                      onClick={() => setTypeFilter(id)}
                      aria-pressed={active}
                      className={cn(
                        "px-2 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wider transition-colors",
                        active
                          ? "bg-primary text-primary-foreground shadow-sm"
                          : "text-muted-foreground hover:text-foreground hover:bg-secondary/60",
                      )}
                      data-testid={`draft-room-eligible-type-${id}`}
                    >
                      {label}
                    </button>
                  );
                })}
              </div>
            )}
            {/* Iter 232N.2 — "Undrafted only" toggle. Fresh-names filter
                surfaces prospects never picked before in this league. */}
            {setUndraftedOnly && (
              <button
                type="button"
                role="switch"
                aria-checked={undraftedOnly}
                onClick={() => setUndraftedOnly(!undraftedOnly)}
                className={cn(
                  "px-2 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wider transition-colors border",
                  undraftedOnly
                    ? "bg-emerald-500/20 text-emerald-300 border-emerald-500/40"
                    : "bg-secondary/40 text-muted-foreground border-transparent hover:text-foreground",
                )}
                data-testid="draft-room-eligible-undrafted-only"
                title="Show only players never picked in this league"
              >
                Undrafted only
              </button>
            )}
          </div>
        </div>

        <ScrollArea className="h-[400px]">
          <div className="space-y-1">
            {filteredPlayers.map((player) => {
              const isOnBlock = tradeBlockPlayerIds.has(String(player.id));
              const isQueued = queue.includes(player.id);
              const isShortlisted = shortlist.includes(player.id);
              return (
                <div
                  key={player.id}
                  className={cn(
                    "flex items-center gap-2 p-2 rounded-md hover:bg-secondary/40 transition-colors group cursor-pointer",
                    isOnBlock && "ring-1 ring-amber-400/40 bg-amber-500/5",
                    String(selectedPlayerId) === String(player.id) && "bg-primary/10 ring-1 ring-primary/40",
                  )}
                  onClick={() => setSelectedPlayerId(String(player.id))}
                  data-testid={isOnBlock ? `draft-room-eligible-block-${player.id}` : `draft-room-eligible-row-${player.id}`}
                >
                  <span className="text-[10px] font-mono text-muted-foreground w-5 text-right shrink-0">
                    {player.ranking}
                  </span>
                  <Badge className={cn("text-[9px] px-1 py-0 h-3.5 border shrink-0", positionColors[player.position])}>
                    {player.position}
                  </Badge>
                  {/* Iter 173 — Minor-eligible badge for prospects when
                      the league has minors_enabled. */}
                  {minorsEnabled && (player.minor_eligible || player.player_type === "prospect") && (
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <span
                          className="inline-flex h-4 w-4 items-center justify-center rounded-sm bg-emerald-500/20 text-emerald-300 shrink-0"
                          data-testid={`draft-room-minor-eligible-${player.id}`}
                        >
                          <Sprout className="h-2.5 w-2.5" />
                        </span>
                      </TooltipTrigger>
                      <TooltipContent>Minor-eligible — can be slotted into your minors</TooltipContent>
                    </Tooltip>
                  )}
                  {isShortlisted && (
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <span
                          className="inline-flex h-4 w-4 items-center justify-center rounded-sm bg-amber-500/20 text-amber-300 shrink-0"
                          data-testid={`draft-room-status-shortlisted-${player.id}`}
                        >
                          <Star className="h-2.5 w-2.5 fill-current" />
                        </span>
                      </TooltipTrigger>
                      <TooltipContent>Shortlisted</TooltipContent>
                    </Tooltip>
                  )}
                  {isQueued && (
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <span
                          className="inline-flex h-4 w-4 items-center justify-center rounded-sm bg-primary/20 text-primary shrink-0"
                          data-testid={`draft-room-status-queued-${player.id}`}
                        >
                          <ListOrdered className="h-2.5 w-2.5" />
                        </span>
                      </TooltipTrigger>
                      <TooltipContent>In queue (#{queue.indexOf(player.id) + 1})</TooltipContent>
                    </Tooltip>
                  )}
                  {isOnBlock && (
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <span className="inline-flex h-4 w-4 items-center justify-center rounded-sm bg-amber-500/25 text-amber-300 shrink-0">
                          <Megaphone className="h-2.5 w-2.5" />
                        </span>
                      </TooltipTrigger>
                      <TooltipContent>On trade block</TooltipContent>
                    </Tooltip>
                  )}
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-foreground truncate flex items-center gap-1.5">
                      <span className="truncate">{player.name}</span>
                      {/* Iter 232N — Player status symbols (injury /
                          minors / unsigned / previously-drafted). */}
                      <PlayerStatusBadges flags={player.status_flags} />
                    </p>
                    <p className="text-[10px] text-muted-foreground">
                      {player.league} · {player.age}y · {player.gp}GP {player.g}G {player.a}A {player.pts}P
                    </p>
                  </div>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Button
                        variant="ghost"
                        size="icon"
                        className={cn(
                          "h-7 w-7 shrink-0 transition-colors",
                          shortlist.includes(player.id)
                            ? "text-accent"
                            : "text-muted-foreground/30 hover:text-accent",
                        )}
                        onClick={(e) => { e.stopPropagation(); toggleShortlist(player.id); }}
                      >
                        <Star className={cn("h-3.5 w-3.5", shortlist.includes(player.id) && "fill-current")} />
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent>
                      {shortlist.includes(player.id) ? "Remove from shortlist" : "Add to shortlist"}
                    </TooltipContent>
                  </Tooltip>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Button
                        variant="ghost"
                        size="icon"
                        className={cn(
                          "h-7 w-7 shrink-0 transition-colors",
                          queue.includes(player.id)
                            ? "text-primary"
                            : "text-muted-foreground/30 hover:text-primary",
                        )}
                        onClick={(e) => { e.stopPropagation(); toggleQueue(player.id); }}
                      >
                        <ListOrdered className="h-3.5 w-3.5" />
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent>
                      {queue.includes(player.id) ? "Remove from queue" : "Add to queue"}
                    </TooltipContent>
                  </Tooltip>
                </div>
              );
            })}
          </div>
        </ScrollArea>
      </TabsContent>

      <TabsContent value="queue" className="mt-3">
        <p className="text-[10px] text-muted-foreground px-1 pb-2">
          Private — only you can see this. Drag rows to set auto-pick fallback order.
        </p>
        <ScrollArea className="h-[420px]" data-testid="draft-room-queue-list">
          <SortableQueue
            players={queuedPlayers}
            positionColors={positionColors}
            onReorder={(orderedIds) => setQueue(orderedIds)}
            onRemove={(id) => removeFromQueue(id)}
          />
        </ScrollArea>
      </TabsContent>

      <TabsContent value="shortlist" className="mt-3">
        <p className="text-[10px] text-muted-foreground px-1 pb-2">
          Drag to rank your shortlist manually. Use ⤴ to promote a player to the auto-pick queue.
        </p>
        <ScrollArea className="h-[450px]">
          <SortableQueue
            players={shortlistedPlayers}
            positionColors={positionColors}
            onReorder={(orderedIds) => setShortlist(orderedIds)}
            onRemove={(id) => toggleShortlist(id)}
            onPromote={(id) => {
              if (!queue.includes(id)) setQueue((prev) => [...prev, id]);
            }}
            isPromoted={(id) => queue.includes(id)}
            promoteLabel="Promote to auto-pick queue"
          />
        </ScrollArea>
      </TabsContent>
    </Tabs>
  );
}
