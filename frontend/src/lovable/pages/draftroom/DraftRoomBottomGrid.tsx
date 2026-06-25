// @ts-nocheck
/**
 * Iter 229j — Bottom 3-column grid of the Draft Room (Player Search /
 * Truncated Roster / Draft Chat). Extracted from DraftRoom.tsx to
 * shrink the parent component and isolate the trade-builder + roster
 * snapshot wiring.
 */
import { toast } from "sonner";
import PlayerSearchPanel from "@/lovable/pages/draftroom/PlayerSearchPanel";
import TruncatedRosterPanel from "@/lovable/pages/draftroom/TruncatedRosterPanel";
import DraftChatPanel from "@/lovable/pages/draftroom/DraftChatPanel";

export default function DraftRoomBottomGrid({
  // Player Search panel
  filteredPlayers, searchQuery, setSearchQuery, positionFilter, setPositionFilter,
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
  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
      {/* LEFT: Player Search */}
      <div className="lg:col-span-4">
        <PlayerSearchPanel
          filteredPlayers={filteredPlayers}
          searchQuery={searchQuery}
          setSearchQuery={setSearchQuery}
          positionFilter={positionFilter}
          setPositionFilter={setPositionFilter}
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
      </div>

      {/* CENTER: Truncated Roster */}
      <div className="lg:col-span-4">
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
      </div>

      {/* RIGHT: Draft Chat */}
      <div className="lg:col-span-4">
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
      </div>
    </div>
  );
}
