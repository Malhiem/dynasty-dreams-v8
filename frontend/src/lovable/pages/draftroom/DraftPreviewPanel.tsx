// @ts-nocheck
/**
 * Iter 230c — Extracted from DraftRoom.tsx.
 *
 * Renders the "Player Preview" panel above the Draft Board:
 *   • A small "Live View · Last Pick" / "Previewing" header strip.
 *   • A "Live View" button when the user is previewing a non-default pick
 *     (lets them snap back to the last-drafted player).
 *   • The `<SelectedPlayerCard>` itself.
 *
 * Pure presentation. Resolves the right player to preview from the
 * `selectedPlayerId` ?? `lastPickedPlayerId` fallback chain.
 */
import { Button } from "@/components/ui/button";
import { Activity } from "lucide-react";
import SelectedPlayerCard from "@/lovable/pages/draftroom/SelectedPlayerCard";

export default function DraftPreviewPanel({
  players,
  selectedPlayerId,
  setSelectedPlayerId,
  lastPickedPlayerId,
  draftStarted,
  queue,
  shortlist,
  canPickForCurrentTurn,
  minorsEnabled,
  onDraftPlayer,
  toggleQueue,
  toggleShortlist,
  setExpandedPlayer,
}) {
  const previewId = selectedPlayerId ?? lastPickedPlayerId;
  const isCustomPreview = !!selectedPlayerId && selectedPlayerId !== lastPickedPlayerId;
  const previewPlayer = previewId
    ? players.find((p) => String(p.id) === String(previewId)) || null
    : null;

  return (
    <>
      <div className="flex items-center justify-between mb-1 px-1">
        <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
          {isCustomPreview
            ? "Previewing"
            : lastPickedPlayerId
            ? "Live View · Last Pick"
            : "Player Preview"}
        </span>
        {isCustomPreview && lastPickedPlayerId && (
          <Button
            size="sm"
            variant="outline"
            className="h-5 px-2 text-[10px] gap-1"
            onClick={() => setSelectedPlayerId(null)}
            data-testid="draft-room-live-view-btn"
          >
            <Activity className="h-3 w-3" />
            Live View
          </Button>
        )}
      </div>
      <SelectedPlayerCard
        player={previewPlayer}
        isOnTheClock={draftStarted}
        isQueued={!!previewId && queue.includes(String(previewId))}
        isShortlisted={!!previewId && shortlist.includes(String(previewId))}
        canPick={canPickForCurrentTurn}
        minorsEnabled={minorsEnabled}
        onDraftPlayer={onDraftPlayer}
        onToggleQueue={(id) => toggleQueue(String(id))}
        onToggleShortlist={(id) => toggleShortlist(String(id))}
        onClose={() => setSelectedPlayerId(null)}
        onExpand={(p) => setExpandedPlayer(p)}
      />
    </>
  );
}
