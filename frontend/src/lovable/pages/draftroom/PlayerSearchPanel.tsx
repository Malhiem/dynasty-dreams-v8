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
  // Iter 232N.50 — Server-side pool restriction for this draft. When
  // the draft is configured with `player_criteria` that already limits
  // the pool (e.g. an Entry draft restricted to `prospects`), the
  // ALL/NHL chips would be misleading — the backend won't return the
  // players they promise. We normalize this into `pinnedType` and use
  // it to disable / relabel the chip row.
  playerCriteria = null,
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
  // Iter 232N.62 — Cap View integration
  capView = false,
  setCapView,
  capEnabled = false,
  capApproaching = false,
  resolveCapHit,
  myTeamCap,
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
                Each segment carries a dedicated testid for E2E driving.
                Iter 232N.50 — When `playerCriteria` restricts the pool
                server-side (e.g. Entry draft with `prospects` criteria),
                pin the chip to the restricted type + show a lock icon
                so users understand the ALL/NHL chips would be no-ops. */}
            {setTypeFilter && (() => {
              // Normalise `player_criteria` (may be string OR
              // single-element array) into a single canonical value.
              const rawCrit = Array.isArray(playerCriteria)
                ? playerCriteria[0]
                : playerCriteria;
              const crit = String(rawCrit || "").toLowerCase();
              // Iter 232N.50 — Mirror the backend's `player_criteria`
              // → server-side filter mapping (see draft_inspection.py
              // `get_draft_eligible_players`). When the pool is
              // restricted server-side, pin the chip so the disallowed
              // segments don't lie about what a click will return.
              let pinnedType: "prospects" | "nhl" | null = null;
              if (crit === "entry" || crit === "prospects") {
                pinnedType = "prospects";
              } else if (crit && crit !== "all") {
                // "open" and any legacy / unknown value → NHL only.
                pinnedType = "nhl";
              }
              const chipItems =
                pinnedType === "prospects"
                  ? [{ id: "prospects", label: "Prospects only" }]
                  : pinnedType === "nhl"
                  ? [{ id: "nhl", label: "NHL only" }]
                  : [
                      { id: "all", label: "All" },
                      { id: "nhl", label: "NHL" },
                      { id: "prospects", label: "Prospects" },
                    ];
              return (
                <div
                  role="group"
                  aria-label={pinnedType ? "Draft pool restricted" : "Filter by player type"}
                  className="inline-flex items-center gap-0.5 rounded-md bg-secondary/40 p-0.5"
                  data-testid="draft-room-eligible-type-filter"
                  title={pinnedType ? "This draft's configuration restricts the pool" : undefined}
                >
                  {chipItems.map(({ id, label }) => {
                    const active = pinnedType ? id === pinnedType : typeFilter === id;
                    const disabled = !!pinnedType;
                    return (
                      <button
                        key={id}
                        type="button"
                        onClick={() => !disabled && setTypeFilter(id)}
                        aria-pressed={active}
                        disabled={disabled}
                        className={cn(
                          "px-2 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wider transition-colors",
                          active
                            ? "bg-primary text-primary-foreground shadow-sm"
                            : "text-muted-foreground hover:text-foreground hover:bg-secondary/60",
                          disabled && "cursor-not-allowed opacity-90",
                        )}
                        data-testid={`draft-room-eligible-type-${id}`}
                      >
                        {label}
                      </button>
                    );
                  })}
                </div>
              );
            })()}
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
            {/* Iter 232N.62 — Cap View toggle. Pulses when the current
                user's team crosses 90% (approaching cap). Toggle-on
                acknowledges the alert and stops the pulse. */}
            {capEnabled && setCapView && (
              <button
                type="button"
                role="switch"
                aria-checked={capView}
                onClick={() => setCapView(!capView)}
                className={cn(
                  "relative px-2 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wider transition-colors border",
                  capView
                    ? "bg-emerald-500/20 text-emerald-300 border-emerald-500/40"
                    : "bg-secondary/40 text-muted-foreground border-transparent hover:text-foreground",
                  capApproaching && !capView && "ring-2 ring-orange-400/70 animate-pulse",
                )}
                data-testid="draft-room-cap-view-toggle"
                data-approaching={capApproaching ? "true" : undefined}
                title={
                  capApproaching
                    ? "You're within 10% of your cap — toggle Cap View for details"
                    : "Show per-team cap usage + cap hit on each player card"
                }
              >
                Cap View
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
              // Iter 232N.62 — Cap-view derivations. Compute per-player
              // AAV via the shared resolver so unpriced players fall back
              // to the league's default_rookie_aav. When cap view is on
              // AND the player would push MY team over the ceiling, we
              // reduce opacity + show a red "over cap" chip (but keep
              // the row clickable so admins can still inspect / warn).
              const capHit =
                capEnabled && resolveCapHit ? resolveCapHit(player) : 0;
              const wouldExceedCap =
                capView && myTeamCap && capHit > myTeamCap.remaining;
              const pctOfCap =
                capView && myTeamCap && myTeamCap.salary_cap > 0
                  ? (capHit / myTeamCap.salary_cap) * 100
                  : 0;
              return (
                <div
                  key={player.id}
                  className={cn(
                    "flex items-center gap-2 p-2 rounded-md hover:bg-secondary/40 transition-colors group cursor-pointer",
                    isOnBlock && "ring-1 ring-amber-400/40 bg-amber-500/5",
                    String(selectedPlayerId) === String(player.id) && "bg-primary/10 ring-1 ring-primary/40",
                    (wouldExceedCap || player.salary_validation?.allowed === false) && "opacity-50",
                  )}
                  onClick={() => setSelectedPlayerId(String(player.id))}
                  data-testid={isOnBlock ? `draft-room-eligible-block-${player.id}` : `draft-room-eligible-row-${player.id}`}
                  data-over-cap={wouldExceedCap ? "true" : undefined}
                  data-salary-blocked={player.salary_validation?.allowed === false ? "true" : undefined}
                  title={player.salary_validation?.message || undefined}
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
                      {capView && capEnabled && (
                        <>
                          {" · "}
                          <span
                            className={cn(
                              "font-mono font-semibold",
                              wouldExceedCap
                                ? "text-rose-300"
                                : pctOfCap >= 10
                                ? "text-orange-300"
                                : "text-emerald-300",
                            )}
                            data-testid={`draft-room-cap-hit-${player.id}`}
                          >
                            {capHit >= 1_000_000
                              ? `$${(capHit / 1_000_000).toFixed(2)}M`
                              : `$${(capHit / 1_000).toFixed(0)}k`}
                          </span>
                          {" "}
                          <span className="text-muted-foreground">
                            ({pctOfCap.toFixed(1)}% cap)
                          </span>
                          {wouldExceedCap && (
                            <Badge
                              variant="outline"
                              className="ml-1 text-[9px] px-1 py-0 h-3.5 bg-rose-500/10 text-rose-300 border-rose-500/40"
                              data-testid={`draft-room-over-cap-${player.id}`}
                            >
                              Over cap
                            </Badge>
                          )}
                        </>
                      )}
                    </p>
                    {player.salary_validation?.message && <p className="text-[10px] text-amber-400 truncate" title={player.salary_validation.message}>{player.salary_validation.message}</p>}
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
