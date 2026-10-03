// @ts-nocheck
/**
 * Iter 230at — Swipe-to-dismiss wrapper for notification rows.
 * Iter 230au — Now delegates to the generic `<SwipeableRow>` primitive
 * so the chat channel list can share the same gesture engine.
 *
 * Swipe RIGHT → mark as read (emerald reveal). Disabled on rows
 * already in the read state.
 * Swipe LEFT  → delete (rose reveal). Always enabled.
 */
import { Check, Trash2 } from "lucide-react";
import SwipeableRow from "@/components/SwipeableRow";

export default function SwipeableNotificationRow({
  notification,
  onMarkRead,
  onDelete,
  showOnboardingHint = false,
  onHintShown,
  children,
}) {
  const isRead = !!notification.read;
  return (
    <SwipeableRow
      testId={`notif-swipe-row-${notification._id}`}
      keepOnRight
      showOnboardingHint={showOnboardingHint}
      onHintShown={onHintShown}
      rightAction={{
        label: "Mark read",
        icon: <Check className="h-4 w-4" />,
        bg: "bg-emerald-600/25",
        color: "text-emerald-200",
        disabled: isRead,
        testId: `notif-swipe-read-hint-${notification._id}`,
      }}
      leftAction={{
        label: "Delete",
        icon: <Trash2 className="h-4 w-4" />,
        bg: "bg-rose-600/25",
        color: "text-rose-200",
        testId: `notif-swipe-delete-hint-${notification._id}`,
      }}
      onSwipeRight={() => onMarkRead?.(notification._id)}
      onSwipeLeft={() => onDelete?.(notification._id)}
    >
      {children}
    </SwipeableRow>
  );
}
