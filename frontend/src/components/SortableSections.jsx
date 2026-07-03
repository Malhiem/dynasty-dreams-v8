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

const SortableCtx = createContext({ ids: [], onReorder: () => {}, customize: false });

export function SortableSections({ ids, onReorder, children, customize = false }) {
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
    <SortableCtx.Provider value={{ ids, onReorder, customize }}>
      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
        <SortableContext items={ids} strategy={verticalListSortingStrategy}>
          {children}
        </SortableContext>
      </DndContext>
    </SortableCtx.Provider>
  );
}

export function SortableSection({ id, children, className = "", style: extraStyle = {} }) {
  const { customize } = useContext(SortableCtx);
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id });
  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.6 : 1,
    zIndex: isDragging ? 10 : "auto",
    position: "relative",
    ...extraStyle,
  };
  // Iter 232N.17 — In "customize" mode we outline the section itself
  // (dashed cyan border) so the whole card reads as draggable, not
  // just the tiny handle in the corner. Handle also grows to 36px and
  // pulses to catch the eye.
  const outline = customize
    ? "outline outline-2 outline-dashed outline-[#00D2FF]/50 outline-offset-2 rounded-lg"
    : "";
  const handleClass = customize
    ? "absolute top-3 right-3 z-20 h-9 w-9 rounded-md bg-[#00D2FF] text-black border border-[#00D2FF] shadow-lg shadow-cyan-500/30 flex items-center justify-center cursor-grab active:cursor-grabbing animate-pulse"
    : "absolute top-3 right-3 z-20 h-7 w-7 rounded-md bg-background/90 backdrop-blur border border-border hover:bg-secondary text-muted-foreground hover:text-foreground transition-colors flex items-center justify-center cursor-grab active:cursor-grabbing";
  return (
    <div
      ref={setNodeRef}
      style={style}
      // Reserve 2.5rem on the right so the floating drag handle never overlaps
      // section titles or pinned content (League Home reorder fix, iter 82).
      className={`${className} pr-10 ${outline}`}
      data-testid={`sortable-section-${id}`}
    >
      <button
        type="button"
        {...attributes}
        {...listeners}
        data-testid={`section-drag-handle-${id}`}
        title="Drag to reorder"
        aria-label="Drag to reorder section"
        className={handleClass}
      >
        <GripVertical className={customize ? "h-5 w-5" : "h-4 w-4"} />
      </button>
      {children}
    </div>
  );
}
