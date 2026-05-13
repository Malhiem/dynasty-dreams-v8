// @ts-nocheck
import React, { createContext, useContext } from "react";
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import {
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { GripVertical } from "lucide-react";

/**
 * "Context-based" sortable wrapper optimised for pages whose sections are
 * already declared inline as JSX. The parent renders a <SortableSections>
 * that provides the DndContext + ordered ids, and each section is wrapped
 * with a <SortableSection id="matchups">. dnd-kit handles the transform on
 * the section's root element without requiring a full JSX restructure.
 *
 * Used by the legacy League Home (LeagueDetailPage.jsx).
 */

const SortableCtx = createContext({ ids: [], onReorder: () => {} });

export function SortableSections({ ids, onReorder, children }) {
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  const handleDragEnd = (event) => {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    const oldIndex = ids.indexOf(active.id);
    const newIndex = ids.indexOf(over.id);
    if (oldIndex < 0 || newIndex < 0) return;
    const next = [...ids];
    const [moved] = next.splice(oldIndex, 1);
    next.splice(newIndex, 0, moved);
    onReorder(next);
  };

  return (
    <SortableCtx.Provider value={{ ids, onReorder }}>
      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
        <SortableContext items={ids} strategy={verticalListSortingStrategy}>
          {children}
        </SortableContext>
      </DndContext>
    </SortableCtx.Provider>
  );
}

export function SortableSection({ id, children, className = "", style: extraStyle = {} }) {
  useContext(SortableCtx);
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id });
  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.6 : 1,
    zIndex: isDragging ? 10 : "auto",
    position: "relative",
    ...extraStyle,
  };
  return (
    <div
      ref={setNodeRef}
      style={style}
      // Reserve 2.5rem on the right so the floating drag handle never overlaps
      // section titles or pinned content (League Home reorder fix, iter 82).
      className={`${className} pr-10`}
      data-testid={`sortable-section-${id}`}
    >
      <button
        type="button"
        {...attributes}
        {...listeners}
        data-testid={`section-drag-handle-${id}`}
        title="Drag to reorder"
        className="absolute top-3 right-3 z-20 h-7 w-7 rounded-md bg-background/90 backdrop-blur border border-border hover:bg-secondary text-muted-foreground hover:text-foreground transition-colors flex items-center justify-center cursor-grab active:cursor-grabbing"
      >
        <GripVertical className="h-4 w-4" />
      </button>
      {children}
    </div>
  );
}
