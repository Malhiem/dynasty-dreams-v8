// @ts-nocheck
// Iter 170k — Drag-to-reorder Queue. Uses @dnd-kit (already in
// package.json). The reorder is propagated up via `onReorder(ids[])`
// which the parent DraftRoom debounce-persists to /teams/{id}/draft-queue.

import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { GripVertical, ListOrdered, X, ArrowUpToLine } from "lucide-react";

interface QueuePlayer {
  id: string | number;
  name: string;
  position: string;
  ranking?: number;
  league?: string;
}

interface Props {
  players: QueuePlayer[]; // ordered list
  positionColors: Record<string, string>;
  onReorder: (orderedIds: string[]) => void;
  onRemove: (id: string) => void;
  // Iter 170n — Optional "Quick Promote" callback. When provided, each
  // row shows a small ⤴ button that copies the player into the parent's
  // target list (e.g. shortlist → queue). The `isPromoted(id)` predicate
  // controls disabled state so an already-promoted row dims the button.
  onPromote?: (id: string) => void;
  isPromoted?: (id: string) => boolean;
  promoteLabel?: string;
}

function SortableQueueRow({ player, idx, positionColors, onRemove, onPromote, isPromoted, promoteLabel }: any) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: String(player.id) });
  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.6 : 1,
  };
  return (
    <div
      ref={setNodeRef}
      style={style}
      data-testid={`draft-room-queue-row-${player.id}`}
      className={cn(
        "flex items-center gap-2 p-2 rounded-md bg-secondary/30 group",
        isDragging && "ring-1 ring-primary/40 bg-secondary/60",
      )}
    >
      <button
        type="button"
        {...attributes}
        {...listeners}
        className="h-6 w-6 -ml-1 flex items-center justify-center text-muted-foreground/60 hover:text-foreground cursor-grab active:cursor-grabbing"
        aria-label="Drag to reorder"
        data-testid={`draft-room-queue-handle-${player.id}`}
      >
        <GripVertical className="h-4 w-4" />
      </button>
      <span className="text-[10px] font-mono text-muted-foreground w-5 text-right shrink-0">{idx + 1}.</span>
      <Badge className={cn("text-[9px] px-1 py-0 h-3.5 border shrink-0", positionColors[player.position])}>
        {player.position}
      </Badge>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-foreground truncate">{player.name}</p>
        <p className="text-[10px] text-muted-foreground">
          {player.ranking ? `#${player.ranking} · ` : ""}{player.league || ""}
        </p>
      </div>
      <Button
        variant="ghost"
        size="icon"
        className="h-6 w-6 text-muted-foreground hover:text-destructive opacity-0 group-hover:opacity-100"
        onClick={() => onRemove(String(player.id))}
        data-testid={`draft-room-queue-remove-${player.id}`}
      >
        <X className="h-3 w-3" />
      </Button>
      {/* Iter 170n — Optional Quick Promote affordance (e.g. shortlist
          → queue) so a manager doesn't have to retype star-rated picks
          into the auto-pick fallback list. */}
      {onPromote && (
        <Button
          variant="ghost"
          size="icon"
          title={isPromoted?.(String(player.id)) ? "Already in queue" : (promoteLabel || "Promote to queue")}
          className="h-6 w-6 text-muted-foreground hover:text-primary opacity-0 group-hover:opacity-100 disabled:opacity-30"
          disabled={isPromoted?.(String(player.id))}
          onClick={() => onPromote(String(player.id))}
          data-testid={`draft-room-queue-promote-${player.id}`}
        >
          <ArrowUpToLine className="h-3 w-3" />
        </Button>
      )}
    </div>
  );
}

export default function SortableQueue({ players, positionColors, onReorder, onRemove, onPromote, isPromoted, promoteLabel }: Props) {
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  const handleDragEnd = (event: any) => {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    const ids = players.map((p) => String(p.id));
    const oldIdx = ids.indexOf(String(active.id));
    const newIdx = ids.indexOf(String(over.id));
    if (oldIdx === -1 || newIdx === -1) return;
    onReorder(arrayMove(ids, oldIdx, newIdx));
  };

  if (players.length === 0) {
    return (
      <div className="text-center py-12 space-y-2">
        <ListOrdered className="h-8 w-8 text-muted-foreground/20 mx-auto" />
        <p className="text-sm text-muted-foreground">Queue is empty</p>
        <p className="text-xs text-muted-foreground/60">Use the queue icon in eligible players. Drag rows to reorder fallback order.</p>
      </div>
    );
  }

  return (
    <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
      <SortableContext items={players.map((p) => String(p.id))} strategy={verticalListSortingStrategy}>
        <div className="space-y-1" data-testid="draft-room-sortable-queue">
          {players.map((p, idx) => (
            <SortableQueueRow
              key={p.id}
              player={p}
              idx={idx}
              positionColors={positionColors}
              onRemove={onRemove}
              onPromote={onPromote}
              isPromoted={isPromoted}
              promoteLabel={promoteLabel}
            />
          ))}
        </div>
      </SortableContext>
    </DndContext>
  );
}
