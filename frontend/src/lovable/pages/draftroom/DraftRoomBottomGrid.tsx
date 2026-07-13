// @ts-nocheck
/**
 * Iter 229j — Bottom 3-column grid of the Draft Room (Player Search /
 * Truncated Roster / Draft Chat). Extracted from DraftRoom.tsx to
 * shrink the parent component and isolate the trade-builder + roster
 * snapshot wiring.
 *
 * Iter 230ak — Mobile-only tabbed view. Below `md` (768px), the
 * 3-panel stack consumed multiple full screens of vertical space —
 * users had to scroll past Player Search to even see their roster
 * or chat. A `[Players] [Roster] [Chat]` tab strip gives each panel
 * the full viewport width per tab and keeps the visible portion of
 * the page bounded. Desktop (md+) is unchanged.
 */
import { useState } from "react";
import { toast } from "sonner";
import { Users, ListChecks, MessageSquare } from "lucide-react";
import { cn } from "@/lib/utils";
import PlayerSearchPanel from "@/lovable/pages/draftroom/PlayerSearchPanel";
import TruncatedRosterPanel from "@/lovable/pages/draftroom/TruncatedRosterPanel";
import DraftChatPanel from "@/lovable/pages/draftroom/DraftChatPanel";

type MobileTab = "players" | "roster" | "chat";

export default function DraftRoomBottomGrid({
  // Player Search panel
  filteredPlayers, searchQuery, setSearchQuery, positionFilter, setPositionFilter,
  typeFilter, setTypeFilter,
  // Iter 232N.50 — server-side pool restriction; passthrough to panel.
  playerCriteria,
  undraftedOnly, setUndraftedOnly,
  positions, positionColors, selectedPlayerId, setSelectedPlayerId,
  tradeBlockPlayerIds, minorsEnabled,
  queue, shortlist, queuedPlayers, shortlistedPlayers,
  setQueue, setShortlist, toggleQueue, toggleShortlist, removeFromQueue,
  // Truncated Roster
  activeLeagueCtx, myTeam, rosterReloadTick, liveTeams, tradeBlockItems,
  toggleMyTeamTradeBlock, tradeBuilder,
  // Draft Chat
  chatMessages, chatInput, setChatInput, handleSendChat, user,
}) {
  // Iter 230ak — Active mobile tab. Defaults to "players" since
  // making the next pick is the highest-frequency mobile action.
  const [mobileTab, setMobileTab] = useState<MobileTab>("players");

  const playerSearchEl = (
    <PlayerSearchPanel
      filteredPlayers={filteredPlayers}
      searchQuery={searchQuery}
      setSearchQuery={setSearchQuery}
      positionFilter={positionFilter}
      setPositionFilter={setPositionFilter}
      typeFilter={typeFilter}
      setTypeFilter={setTypeFilter}
      playerCriteria={playerCriteria}
      undraftedOnly={undraftedOnly}
      setUndraftedOnly={setUndraftedOnly}
      positions={positions}
      positionColors={positionColors}
      selectedPlayerId={selectedPlayerId}
      setSelectedPlayerId={setSelectedPlayerId}
      tradeBlockPlayerIds={tradeBlockPlayerIds}
      minorsEnabled={minorsEnabled}
      queue={queue}
      shortlist={shortlist}
      queuedPlayers={queuedPlayers}
      shortlistedPlayers={shortlistedPlayers}
      setQueue={setQueue}
      setShortlist={setShortlist}
      toggleQueue={toggleQueue}
      toggleShortlist={toggleShortlist}
      removeFromQueue={removeFromQueue}
    />
  );

  const rosterEl = (
    <TruncatedRosterPanel
      leagueId={activeLeagueCtx?.id}
      myTeamId={myTeam?.id}
      reloadTrigger={rosterReloadTick}
      teams={(liveTeams || []).map((t) => ({ id: t.id, name: t.name }))}
      tradeBlockItems={tradeBlockItems}
      capEnabled={!!activeLeagueCtx?.cap_enabled}
      onToggleTradeBlock={toggleMyTeamTradeBlock}
      onPickPlayerForTrade={(team, player) => {
        if (!team || !player) return;
        if (!tradeBuilder.isOpen) {
          tradeBuilder.openBuilder({ leagueId: activeLeagueCtx?.id, myTeam });
        }
        tradeBuilder.addAsset({
          id: String(player.id),
          name: player.name,
          position: player.position,
          ownerTeamId: team.id,
          ownerTeamName: team.name,
          capHit: player.cap_hit,
        });
        toast.success(`Added ${player.name} to trade — ${team.name}`);
      }}
    />
  );

  const chatEl = (
    <DraftChatPanel
      chatMessages={chatMessages}
      chatInput={chatInput}
      setChatInput={setChatInput}
      onSendChat={handleSendChat}
      mySender={myTeam?.name || "Team Frostbite"}
      leagueId={activeLeagueCtx?.id}
      myUserId={user?.id}
      isCommissioner={!!(activeLeagueCtx?.is_commissioner || activeLeagueCtx?.commissioner_id === user?.id)}
      league={activeLeagueCtx}
    />
  );

  return (
    <>
      {/* Mobile (< md): tabbed view — exactly one panel visible at full
          viewport width. Same `md:hidden` gate as the Draft Board's
          "← swipe →" hint so desktop is unaffected. */}
      <div className="md:hidden" data-testid="draft-room-mobile-tabs">
        <div
          role="tablist"
          aria-label="Draft Room panels"
          className="flex items-center gap-1 rounded-md bg-secondary/40 p-1 mb-3"
        >
          {[
            { id: "players" as const, label: "Players", icon: Users },
            { id: "roster"  as const, label: "Roster",  icon: ListChecks },
            { id: "chat"    as const, label: "Chat",    icon: MessageSquare },
          ].map(({ id, label, icon: Icon }) => {
            const active = mobileTab === id;
            return (
              <button
                key={id}
                role="tab"
                type="button"
                aria-selected={active}
                onClick={() => setMobileTab(id)}
                className={cn(
                  "flex-1 inline-flex items-center justify-center gap-1.5 rounded px-2 py-1.5 text-xs font-medium uppercase tracking-wider transition-colors",
                  active
                    ? "bg-primary text-primary-foreground shadow"
                    : "text-muted-foreground hover:text-foreground hover:bg-secondary/60",
                )}
                data-testid={`draft-room-mobile-tab-${id}`}
              >
                <Icon className="h-3.5 w-3.5" />
                {label}
              </button>
            );
          })}
        </div>
        <div role="tabpanel" data-testid={`draft-room-mobile-panel-${mobileTab}`}>
          {mobileTab === "players" && playerSearchEl}
          {mobileTab === "roster"  && rosterEl}
          {mobileTab === "chat"    && chatEl}
        </div>
      </div>

      {/* Desktop (md+): existing 3-column grid, unchanged. */}
      <div className="hidden md:grid grid-cols-1 lg:grid-cols-12 gap-4">
        <div className="lg:col-span-4">{playerSearchEl}</div>
        <div className="lg:col-span-4">{rosterEl}</div>
        <div className="lg:col-span-4">{chatEl}</div>
      </div>
    </>
  );
}
