// @ts-nocheck
/**
 * Iter 171 — DraftBoard
 *
 * Extracted from DraftRoom.tsx. Renders the full-width Draft Board card:
 *   • Header row with owner-filter chips (multi-select highlight/dim).
 *   • A sticky team-abbr column header strip + per-round grid of tiles.
 *   • Each tile shows: pick #, headshot/initial, name, position chip,
 *     NHL team (or feeder league for non-NHL players), conditional/
 *     traded-pick overlays, auto-pick badge, commissioner Swap popover,
 *     trade-block megaphone, trade-mode quick-add buttons.
 *
 * Iter 230x — Compressed view for massive drafts (>10 rounds). Defaults
 * to a sliding 5-round window centered on the current pick so the
 * Player List / My Roster / Draft Chat below stay visible without
 * scrolling. A "Show all rounds" toggle expands to the full grid. When
 * expanded, the inner scroll area is capped at 60vh so the bottom
 * panels remain reachable in a single page-down.
 *
 * Pure presentational. All state lives in the parent (DraftRoom) and is
 * forwarded via props; events flow back through the supplied callbacks.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import {
  Clock,
  ArrowRightLeft,
  Megaphone,
  Repeat,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";
import { cn } from "@/lib/utils";
import PickProvenance from "@/lovable/pages/draftroom/PickProvenance";
import DraftBoardCompressedControls from "@/lovable/pages/draftroom/DraftBoardCompressedControls";
import {
  positionColors,
  positionTints,
} from "@/lovable/pages/draftroom/draftConstants";

// Iter 230x — Number of rounds rendered when the board is compressed.
// Centered on the current pick's round. 5 rows fits comfortably above
// the bottom grid on a 1080-px viewport without scrolling.
const COMPRESSED_WINDOW = 5;
// Rounds beyond this auto-collapse the board on first mount. Smaller
// drafts (e.g. an 8-round entry draft) stay fully expanded by default.
const COMPRESS_AUTO_THRESHOLD = 10;

export default function DraftBoard({
  // grid shape
  boardTeams,
  boardTeamAbbrs,
  totalTeams,
  allPicks,
  // owner-filter state
  selectedOwnerAbbrs,
  setSelectedOwnerAbbrs,
  // live state
  draftConfig,
  onTheClockTeam,
  myTeam,
  liveTeams,
  livePicksByOrigKey,
  // trade-block + trade-mode
  tradeBlockPlayerIds,
  tradeBlockOverallKeys,
  tradeBlockMode,
  tradeMode,
  markAvailableForDraft,
  handleAddDraftPickToTrade,
  // commissioner swap
  isLeagueManager,
  swapPickOverall,
  setSwapPickOverall,
  swapSearch,
  setSwapSearch,
  handleSwapPickPlayer,
  players,
}) {
  // Iter 230x — Compressed view state. Auto-collapses on first mount
  // for drafts with more than COMPRESS_AUTO_THRESHOLD rounds so the
  // page-load doesn't push the Player List / Roster / Chat below the
  // fold. The toggle button lets the user flip between modes at any
  // time without losing scroll position.
  const totalRounds = allPicks.length;
  const [compressed, setCompressed] = useState(totalRounds > COMPRESS_AUTO_THRESHOLD);
  // One-shot auto-collapse the first time we learn the real round
  // count (DraftRoom's draftConfig starts at 5 and is overwritten
  // after the backend response, so the initial useState above sees
  // the stale default). After this fires once, the user is in full
  // control via the toggle button.
  const autoCollapsedRef = useRef(false);
  useEffect(() => {
    if (!autoCollapsedRef.current && totalRounds > COMPRESS_AUTO_THRESHOLD) {
      setCompressed(true);
      autoCollapsedRef.current = true;
    }
  }, [totalRounds]);

  // Round currently on the clock — drives the compressed-window
  // centering. Derived from `draftConfig.currentPick` / `totalTeams`
  // (snake-aware order doesn't matter for ROUND number).
  const currentRound = Math.max(
    1,
    Math.min(totalRounds, Math.ceil((draftConfig?.currentPick || 1) / Math.max(1, totalTeams))),
  );
  const [centerRound, setCenterRound] = useState(currentRound);

  // Keep the compressed window following the live pick. When the user
  // manually paginates (prev/next round), `centerRound` diverges from
  // `currentRound` — a "Jump to live" affordance lets them snap back.
  useEffect(() => {
    if (compressed) setCenterRound(currentRound);
  }, [compressed, currentRound]);

  // Slice the rounds to render. When compressed, show a sliding window
  // of COMPRESSED_WINDOW rounds clamped to the draft's actual range.
  const visibleRounds = useMemo(() => {
    if (!compressed) return allPicks;
    const half = Math.floor(COMPRESSED_WINDOW / 2);
    let start = Math.max(0, centerRound - 1 - half);
    let end = Math.min(totalRounds, start + COMPRESSED_WINDOW);
    start = Math.max(0, end - COMPRESSED_WINDOW); // re-clamp if we hit the tail
    return allPicks.slice(start, end);
  }, [compressed, allPicks, centerRound, totalRounds]);

  const windowStart = compressed
    ? Math.max(1, centerRound - Math.floor(COMPRESSED_WINDOW / 2))
    : 1;
  const windowEnd = compressed
    ? Math.min(totalRounds, windowStart + visibleRounds.length - 1)
    : totalRounds;
  const canStepBack = compressed && windowStart > 1;
  const canStepFwd = compressed && windowEnd < totalRounds;
  const isFollowingLive = compressed && centerRound === currentRound;

  return (
    <Card className="border-border">
      <CardHeader className="pb-2 space-y-2">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <div className="flex items-center gap-2 flex-wrap">
            <CardTitle className="text-base">Draft Board</CardTitle>
            <DraftBoardCompressedControls
              totalRounds={totalRounds}
              compressedWindow={COMPRESSED_WINDOW}
              compressed={compressed}
              setCompressed={setCompressed}
              windowStart={windowStart}
              windowEnd={windowEnd}
              canStepBack={canStepBack}
              canStepFwd={canStepFwd}
              isFollowingLive={isFollowingLive}
              draftStarted={!!draftConfig?.draftStarted}
              currentRound={currentRound}
              setCenterRound={setCenterRound}
            />
          </div>
          <div className="flex items-center gap-1 flex-wrap" data-testid="draft-board-owner-filter">
            <span className="text-[10px] uppercase text-muted-foreground tracking-wider mr-1">
              {selectedOwnerAbbrs.size === 0
                ? "Filter by owner"
                : `Showing ${selectedOwnerAbbrs.size} team${selectedOwnerAbbrs.size === 1 ? "" : "s"}`}
            </span>
            {boardTeamAbbrs.map((abbr) => {
              const isOn = selectedOwnerAbbrs.has(abbr);
              return (
                <button
                  key={abbr}
                  type="button"
                  onClick={() => {
                    setSelectedOwnerAbbrs((prev) => {
                      const next = new Set(prev);
                      if (next.has(abbr)) next.delete(abbr);
                      else next.add(abbr);
                      return next;
                    });
                  }}
                  className={cn(
                    "px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase border transition-colors",
                    isOn
                      ? "bg-primary/25 border-primary/60 text-primary"
                      : "bg-secondary/30 border-border/40 text-muted-foreground hover:border-primary/40 hover:text-foreground",
                  )}
                  data-testid={`draft-board-owner-chip-${abbr}`}
                  aria-pressed={isOn}
                >
                  {abbr}
                </button>
              );
            })}
            {selectedOwnerAbbrs.size > 0 && (
              <button
                type="button"
                onClick={() => setSelectedOwnerAbbrs(new Set())}
                className="px-1.5 py-0.5 rounded text-[10px] uppercase text-muted-foreground hover:text-foreground border border-transparent"
                data-testid="draft-board-owner-clear"
              >
                Clear
              </button>
            )}
          </div>
        </div>
      </CardHeader>
      <CardContent className="p-0">
        {/* Iter 230ah — Native horizontal-scrolling container for the
            draft board. Radix `ScrollArea` was suppressing touch-pan
            on mobile, so users on phones could see HC..OS14 but not
            scroll past — the board's 25-team grid is intrinsically
            ~1900px wide. Native `overflow-auto` with `touch-pan-x`
            restores touch momentum scrolling on iOS/Android while
            still rendering perfectly on desktop. The grid itself
            keeps its `min-w-[700px]` so it remains horizontally
            scrollable on every device. */}
        <div
          className={cn(
            "w-full overflow-auto touch-pan-x",
            // Iter 230x — Cap full-mode height so the Player List /
            // Roster / Chat below remain visible above the fold even
            // for 25-team boards. Compressed mode is naturally short
            // (5 rounds) and doesn't need the cap.
            !compressed && "max-h-[60vh]",
          )}
          data-testid="draft-board-scroll"
        >
          {/* Iter 230ah — Mobile "← swipe →" affordance. Hidden on
              md+ where horizontal scroll-bars are visible on hover. */}
          <div
            className="md:hidden sticky top-0 z-20 bg-card/95 backdrop-blur px-4 pt-2 pb-1 flex items-center justify-end gap-1.5 text-[10px] uppercase tracking-wider text-muted-foreground"
            data-testid="draft-board-swipe-hint"
          >
            <ChevronLeft className="h-3 w-3" />
            swipe to see all {totalTeams} teams
            <ChevronRight className="h-3 w-3" />
          </div>
          <div className="min-w-[700px] p-4 pt-0">
            <div
              className="grid gap-1 mb-1 sticky top-0 bg-card z-10 pt-2"
              style={{ gridTemplateColumns: `48px repeat(${totalTeams}, minmax(72px, 1fr))` }}
            >
              <div className="p-1.5 text-[10px] font-semibold text-muted-foreground uppercase">Rd</div>
              {boardTeamAbbrs.map((abbr) => {
                const teamEntry = boardTeams.find((t) => t.abbr === abbr);
                const themeColor = teamEntry?.theme_color || null;
                const isLive = abbr === onTheClockTeam && draftConfig.draftStarted;
                const isMine = abbr === myTeam?.abbr;
                // Iter 229k — Render the column header with the team's saved
                // theme_color when available; live/my-team highlights still
                // win via ring + colored text to remain visible.
                return (
                  <div
                    key={abbr}
                    className={cn(
                      "p-1.5 text-[10px] font-semibold text-center uppercase truncate rounded transition-colors",
                      themeColor ? "text-white drop-shadow" : "text-muted-foreground",
                      !themeColor && isLive && "bg-primary/15 text-primary",
                      !themeColor && !isLive && isMine && "bg-accent/10 text-accent",
                      !themeColor && !isLive && !isMine && "bg-secondary/50",
                      themeColor && isLive && "ring-1 ring-primary/70",
                      themeColor && !isLive && isMine && "ring-1 ring-accent/70",
                    )}
                    style={themeColor ? { backgroundColor: themeColor } : undefined}
                    data-testid={`draft-board-col-header-${abbr}`}
                    data-theme-color={themeColor || undefined}
                  >
                    {abbr}
                  </div>
                );
              })}
            </div>

            {visibleRounds.map((roundPicks, vIdx) => {
              // Iter 230x — When compressed, the slice starts at
              // `windowStart`, so the displayed round number maps from
              // the visible index back to the absolute draft round.
              const round = compressed ? windowStart + vIdx : vIdx + 1;
              return (
                <div
                  key={round}
                  className="grid gap-1 mb-1"
                  style={{ gridTemplateColumns: `48px repeat(${totalTeams}, minmax(72px, 1fr))` }}
                >
                  <div className="p-1.5 flex items-center justify-center text-[10px] font-bold text-muted-foreground bg-secondary/30 rounded">
                    {round}
                  </div>
                  {boardTeamAbbrs.map((teamAbbr) => {
                    const boardEntry = boardTeams.find((t) => t.abbr === teamAbbr);
                    // Iter 231x — Pick lookup matches by EITHER team_id
                    // (canonical) OR the legacy `team` abbr. Drafts created
                    // before iter229b backfilled "Open Slot N" team names
                    // stored their picks with `team: "TBD"`, `"TBD2"` etc.
                    // The current frontend derives column abbrs as "OS5",
                    // "OS9", "OS1", "OS12" (from `Open Slot N` initials) so
                    // a pure-abbr match leaves the cell blank. Resolving by
                    // `pick.team_id === boardEntry.id` (which the auto-pick
                    // worker stamps onto every pick) makes the rendering
                    // resilient to abbr drift.
                    const pick = roundPicks.find((p) => {
                      if (boardEntry?.id && p.team_id && String(p.team_id) === String(boardEntry.id)) return true;
                      return p.team === teamAbbr;
                    });
                    const isCurrentPick = pick?.overall === draftConfig.currentPick && draftConfig.draftStarted;
                    const ownerTeam = (liveTeams || []).find((t) => {
                      if (boardEntry?.id && (t.id || t._id) === boardEntry.id) return true;
                      const nameAbbr = (t.name || "").replace(/\s/g, "").slice(0, 3).toUpperCase();
                      const fullName = (t.name || "").split(" ").map((w) => w[0]).join("").toUpperCase();
                      return t.logo_abbr === teamAbbr || nameAbbr === teamAbbr || fullName === teamAbbr;
                    });
                    const isPlayerOnBlock = pick?.player && tradeBlockPlayerIds.has(String(pick.player.id));
                    const isPickOnBlock = ownerTeam?.id && tradeBlockOverallKeys.has(`${ownerTeam.id}|R${round}`);
                    const onBlock = isPlayerOnBlock || isPickOnBlock;
                    const isMyTile = ownerTeam?.id && ownerTeam.id === myTeam?.id;
                    const ownerFilterActive = selectedOwnerAbbrs.size > 0;
                    const livePick =
                      (ownerTeam?.id ? livePicksByOrigKey[`${round}|${ownerTeam.id}`] : null)
                      || (!ownerTeam?.id ? livePicksByOrigKey[`${round}|abbr:${teamAbbr}`] : null);
                    const tradeHistory = (livePick?.trade_history || []);
                    const isTradedPick = tradeHistory.length > 0;
                    const currentOwnerAbbrs = Array.from(new Set([
                            ...(livePick?._currentOwnerAbbrs || []),
                            teamAbbr,
                          ]));
                    const isOwnedBySelected = ownerFilterActive && currentOwnerAbbrs.some((a: string) => selectedOwnerAbbrs.has(a));
                    const isDimmedByFilter = ownerFilterActive && !isOwnedBySelected;
                    const conditionalProtections = (livePick?.pending_protections || []) as any[];
                    const isConditional = conditionalProtections.length > 0;

                    return (
                      <div
                        key={`${round}-${teamAbbr}`}
                        data-testid={`draft-board-tile-${teamAbbr}-${round}`}
                        className={cn(
                          "p-1.5 rounded border text-center min-h-[64px] flex flex-col items-center justify-center gap-0.5 transition-all relative",
                          isCurrentPick
                            ? "bg-primary/10 border-primary/50 ring-1 ring-primary/30"
                            : pick?.player
                            ? (positionTints[pick.player.position] || "bg-secondary/60 border-border")
                            : "bg-card/50 border-border/50",
                          onBlock && "ring-1 ring-amber-400/60 border-amber-400/40",
                          isOwnedBySelected && "ring-2 ring-primary/70 border-primary/50",
                          isDimmedByFilter && "opacity-30",
                        )}
                      >
                        <span className="text-[9px] text-muted-foreground">
                          #{pick?.overall}
                          {isConditional && (
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <span
                                  className="ml-0.5 text-amber-400 font-bold cursor-help"
                                  data-testid={`draft-board-pick-conditional-${teamAbbr}-${round}`}
                                >*</span>
                              </TooltipTrigger>
                              <TooltipContent className="max-w-sm">
                                <div className="space-y-1 text-xs">
                                  <p className="font-semibold">Conditional protection — locked from re-trade</p>
                                  {conditionalProtections.map((c, idx) => (
                                    <p key={idx} className="text-muted-foreground">
                                      {c.description || `${c.subject_type} ${c.metric} ${c.operator} ${c.threshold}`}
                                    </p>
                                  ))}
                                </div>
                              </TooltipContent>
                            </Tooltip>
                          )}
                        </span>

                        {pick?.player ? (
                          <>
                            {pick.auto_picked && (
                              <Tooltip>
                                <TooltipTrigger asChild>
                                  <span
                                    className="absolute top-0.5 right-0.5 inline-flex items-center justify-center h-4 w-4 rounded-sm bg-sky-500/25 text-sky-300"
                                    data-testid={`draft-board-auto-pick-${pick.overall}`}
                                  >
                                    <Clock className="h-2.5 w-2.5" />
                                  </span>
                                </TooltipTrigger>
                                <TooltipContent>
                                  Auto-picked on timeout — via {pick.auto_pick_via === "queue" ? "manager's queue" : "top-ranked eligible"}
                                </TooltipContent>
                              </Tooltip>
                            )}

                            {pick.player.photo || pick.player.headshot ? (
                              <img
                                src={pick.player.photo || pick.player.headshot}
                                alt={pick.player.name}
                                className="h-6 w-6 rounded-full object-cover border border-border/60"
                                data-testid={`draft-board-tile-photo-${teamAbbr}-${round}`}
                              />
                            ) : (
                              <span
                                className="h-6 w-6 rounded-full bg-card/70 border border-border/60 flex items-center justify-center text-[10px] font-bold text-foreground/80"
                                data-testid={`draft-board-tile-initial-${teamAbbr}-${round}`}
                              >
                                {pick.player.name.charAt(0)}
                              </span>
                            )}

                            <span className="text-[10px] font-medium text-foreground truncate w-full leading-tight">
                              {pick.player.name.split(" ").map((n, i) => i === 0 ? n[0] + "." : n).join(" ")}
                            </span>

                            <div className="flex items-center gap-1 justify-center">
                              <Badge className={cn("text-[9px] px-1 py-0 h-3.5 border", positionColors[pick.player.position] || "bg-muted text-muted-foreground")}>
                                {pick.player.position}
                              </Badge>
                              {/* Iter 171 — NHL team abbr for NHL players,
                                  otherwise the league they play in (OHL/WHL/SHL/…). */}
                              {(() => {
                                const isNhl = (pick.player.league || "").toUpperCase() === "NHL";
                                const label = isNhl
                                  ? (pick.player.nhlTeam || pick.player.team || pick.player.league)
                                  : (pick.player.league || pick.player.nhlTeam);
                                return label && label !== "—" ? (
                                  <span
                                    className="text-[8px] text-muted-foreground truncate"
                                    data-testid={`draft-board-tile-affiliation-${teamAbbr}-${round}`}
                                  >
                                    {label}
                                  </span>
                                ) : null;
                              })()}
                            </div>

                            {isLeagueManager && (
                              <Popover
                                open={swapPickOverall === pick.overall}
                                onOpenChange={(open) => {
                                  setSwapPickOverall(open ? pick.overall : null);
                                  if (!open) setSwapSearch("");
                                }}
                              >
                                <PopoverTrigger asChild>
                                  <button
                                    type="button"
                                    className="absolute bottom-0.5 right-0.5 h-4 w-4 rounded-sm bg-card/70 border border-border/60 flex items-center justify-center text-foreground/70 hover:bg-primary/20 hover:text-primary"
                                    data-testid={`draft-board-swap-btn-${pick.overall}`}
                                    aria-label="Swap player"
                                    onClick={(e) => e.stopPropagation()}
                                  >
                                    <ArrowRightLeft className="h-2.5 w-2.5" />
                                  </button>
                                </PopoverTrigger>
                                <PopoverContent
                                  align="end"
                                  className="w-72 p-2 space-y-2"
                                  onClick={(e) => e.stopPropagation()}
                                >
                                  <div className="text-xs font-semibold text-foreground">
                                    Swap pick #{pick.overall} ({pick.team})
                                  </div>
                                  <div className="text-[10px] text-muted-foreground">
                                    Currently: <span className="text-foreground">{pick.player.name}</span> ({pick.player.position})
                                  </div>
                                  <Input
                                    autoFocus
                                    value={swapSearch}
                                    onChange={(e) => setSwapSearch(e.target.value)}
                                    placeholder="Search for replacement player…"
                                    className="h-8 text-xs"
                                    data-testid="draft-board-swap-search"
                                  />
                                  <div className="max-h-48 overflow-y-auto space-y-0.5">
                                    {players
                                      .filter((p) => !p.drafted && (!swapSearch || p.name.toLowerCase().includes(swapSearch.toLowerCase()) || p.position.toLowerCase().includes(swapSearch.toLowerCase())))
                                      .slice(0, 12)
                                      .map((p) => (
                                        <button
                                          key={p.id}
                                          type="button"
                                          onClick={async () => {
                                            await handleSwapPickPlayer(pick.overall, String(p.id));
                                            setSwapPickOverall(null);
                                            setSwapSearch("");
                                          }}
                                          className="flex items-center justify-between w-full px-2 py-1 rounded hover:bg-secondary/60 text-left"
                                          data-testid={`draft-board-swap-option-${p.id}`}
                                        >
                                          <span className="text-xs text-foreground truncate">{p.name}</span>
                                          <span className="text-[10px] text-muted-foreground ml-2">{p.position}</span>
                                        </button>
                                      ))}
                                    {players.filter((p) => !p.drafted).length === 0 && (
                                      <p className="text-[11px] text-muted-foreground text-center py-2">No eligible players</p>
                                    )}
                                  </div>
                                </PopoverContent>
                              </Popover>
                            )}
                          </>
                        ) : (
                          <span className="text-[10px] text-muted-foreground/40">—</span>
                        )}

                        {onBlock && (
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <span
                                className="absolute top-0.5 left-0.5 inline-flex items-center justify-center h-4 w-4 rounded-sm bg-amber-500/25 text-amber-300"
                                data-testid={`draft-room-block-icon-${teamAbbr}-${pick?.overall ?? "x"}`}
                              >
                                <Megaphone className="h-2.5 w-2.5" />
                              </span>
                            </TooltipTrigger>
                            <TooltipContent>
                              {isPlayerOnBlock ? "Player available — on trade block" : "Upcoming pick available — on trade block"}
                            </TooltipContent>
                          </Tooltip>
                        )}

                        {isTradedPick && (
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <span
                                className="absolute top-0.5 right-0.5 inline-flex items-center justify-center h-4 w-4 rounded-sm bg-sky-500/25 text-sky-300 cursor-help"
                                data-testid={`draft-board-pick-traded-${teamAbbr}-${round}`}
                              >
                                <ArrowRightLeft className="h-2.5 w-2.5" />
                              </span>
                            </TooltipTrigger>
                            <TooltipContent className="max-w-sm">
                              <PickProvenance tradeHistory={tradeHistory} />
                            </TooltipContent>
                          </Tooltip>
                        )}

                        {tradeBlockMode && !onBlock && isMyTile && (
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <button
                                type="button"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  if (pick?.player) {
                                    markAvailableForDraft("player", { id: pick.player.id, name: pick.player.name });
                                  } else {
                                    markAvailableForDraft("pick", { year: new Date().getFullYear(), round, name: `R${round}` });
                                  }
                                }}
                                data-testid={`draft-room-block-add-${teamAbbr}-${pick?.overall ?? "x"}`}
                                aria-label="Mark available for draft"
                                className="absolute top-0.5 left-0.5 h-4 w-4 inline-flex items-center justify-center rounded-sm bg-amber-500/20 text-amber-300 hover:bg-amber-500/35"
                              >
                                <Megaphone className="h-2.5 w-2.5" />
                              </button>
                            </TooltipTrigger>
                            <TooltipContent>Mark available for draft</TooltipContent>
                          </Tooltip>
                        )}

                        {tradeMode && pick && (
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              handleAddDraftPickToTrade(pick.team, round, pick.overall, pick.player);
                            }}
                            data-testid={`draft-room-pick-trade-${pick.team}-${pick.overall}`}
                            aria-label="Add pick to trade"
                            className="absolute top-0.5 right-0.5 h-4 w-4 inline-flex items-center justify-center rounded-sm bg-emerald-500/15 text-emerald-300 hover:bg-emerald-500/30"
                          >
                            <Repeat className="h-2.5 w-2.5" />
                          </button>
                        )}
                      </div>
                    );
                  })}
                </div>
              );
            })}

            <div className="flex items-center gap-3 mt-3 pt-2 border-t border-border">
              <span className="text-[10px] text-muted-foreground">Positions:</span>
              {Object.entries(positionColors).map(([pos, colorClass]) => (
                <Badge key={pos} className={cn("text-[9px] px-1.5 py-0 h-3.5 border", colorClass)}>{pos}</Badge>
              ))}
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
