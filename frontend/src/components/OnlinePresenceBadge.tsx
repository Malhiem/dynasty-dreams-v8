/**
 * Iter 232b — `<OnlinePresenceBadge />` + `<OnlineDot />`
 *
 * Small, dependency-free UI primitives for surfacing who is
 * currently connected to a Socket.IO room. Powered by the existing
 * `presence_state` / `user_joined` / `user_left` events emitted by
 * the server on every connect/join/leave (see backend/server.py).
 *
 *  • `<OnlinePresenceBadge>` — pill rendered next to a section title
 *    (e.g. "Draft Room", "League Chat") showing live count.
 *  • `<OnlineDot>` — tiny green/grey dot to overlay on individual
 *    avatars or list rows.
 *
 * Both render nothing when the underlying `Set<string>` is empty
 * (loading / non-connected state) so the page layout never jumps.
 */
import { cn } from "@/lib/utils";

interface BadgeProps {
  /** Set of user_ids currently in the room (stringified). */
  onlineUserIds: Set<string> | undefined;
  /** Optional label override; default "online". */
  label?: string;
  /** Optional className escape hatch. */
  className?: string;
  /** Optional test-id suffix so multiple badges on the same page can be uniquely targeted. */
  testIdSuffix?: string;
}

export function OnlinePresenceBadge({
  onlineUserIds,
  label = "online",
  className,
  testIdSuffix = "",
}: BadgeProps) {
  const count = onlineUserIds?.size ?? 0;
  if (count <= 0) return null;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full",
        "border border-[#34C759]/30 bg-[#34C759]/10 text-[#34C759]",
        "px-2 py-0.5 text-[11px] font-medium leading-none",
        className,
      )}
      data-testid={`online-presence-badge${testIdSuffix ? `-${testIdSuffix}` : ""}`}
      aria-label={`${count} ${label}`}
      title={`${count} ${label}`}
    >
      <span
        className="relative inline-flex h-1.5 w-1.5"
        aria-hidden="true"
      >
        <span className="absolute inline-flex h-full w-full rounded-full bg-[#34C759] opacity-75 animate-ping" />
        <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-[#34C759]" />
      </span>
      <span data-testid={`online-presence-count${testIdSuffix ? `-${testIdSuffix}` : ""}`}>
        {count}
      </span>
      <span>{label}</span>
    </span>
  );
}

interface DotProps {
  /** Whether the entity (user) is currently online. */
  online: boolean;
  /** Optional className escape hatch. */
  className?: string;
  /** Optional test-id (e.g. user id) for Playwright. */
  testId?: string;
}

/**
 * Tiny pill-dot to overlay next to a person's name / avatar.
 * Grey when offline, pulsing green when online.
 */
export function OnlineDot({ online, className, testId }: DotProps) {
  return (
    <span
      className={cn(
        "inline-block h-1.5 w-1.5 rounded-full shrink-0",
        online
          ? "bg-[#34C759] ring-2 ring-[#34C759]/30"
          : "bg-[#3F3F46]",
        className,
      )}
      data-testid={testId}
      data-online={online ? "true" : "false"}
      aria-label={online ? "online" : "offline"}
      title={online ? "Online" : "Offline"}
    />
  );
}

export default OnlinePresenceBadge;
