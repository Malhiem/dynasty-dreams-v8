// @ts-nocheck
import { forwardRef } from "react";
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
 * Thin DnD wrapper built on @dnd-kit — gives child widgets a drag handle
 * (grabable grip icon) and persists reorder via the parent-supplied
 * `onReorder(nextIdsInOrder)` callback. Keyboard-accessible (Space to pick
 * up, Arrow keys to move, Space to drop).
 *
 * Usage:
 *   <SortableList ids={["a","b","c"]} onReorder={(next)=>...}>
 *     {(id) => <WidgetForId id={id} />}
 *   </SortableList>
 */
export function SortableList({ ids, onReorder, children, className = "", dragHandleTestIdPrefix = "drag-handle" }) {
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
    <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
      <SortableContext items={ids} strategy={verticalListSortingStrategy}>
        <div className={className}>
          {ids.map((id) => (
            <SortableRow key={id} id={id} dragHandleTestId={`${dragHandleTestIdPrefix}-${id}`}>
              {children(id)}
            </SortableRow>
          ))}
        </div>
      </SortableContext>
    </DndContext>
  );
}

const SortableRow = forwardRef(function SortableRow({ id, children, dragHandleTestId }, _ref) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id });
  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.6 : 1,
    zIndex: isDragging ? 10 : "auto",
  };
  return (
    <div ref={setNodeRef} style={style} data-testid={`sortable-row-${id}`} data-dragging={isDragging ? "true" : "false"}>
      <div className="group relative">
        {/* Drag handle — positioned top-right so it never interferes with
            the underlying widget's own buttons/links. */}
        <button
          type="button"
          {...attributes}
          {...listeners}
          data-testid={dragHandleTestId}
          title="Drag to reorder"
          className="absolute top-2 right-2 z-20 h-6 w-6 rounded-md bg-black/40 hover:bg-black/70 text-white/70 hover:text-white opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center cursor-grab active:cursor-grabbing"
        >
          <GripVertical className="h-4 w-4" />
        </button>
        {children}
      </div>
    </div>
  );
});
