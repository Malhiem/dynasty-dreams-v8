// @ts-nocheck
/**
 * Iter 232c — `<MobileBottomNav />`
 *
 * Persistent bottom-tab nav for touch devices. Surfaces the four
 * highest-traffic routes (Dashboard / Matchup / Chat / My Roster)
 * + a "More" trigger that opens the existing sidebar drawer.
 *
 * The Chat tab carries a tiny green presence bubble showing how
 * many league members are currently connected to the league chat
 * room ("X online"). Powered by the same Socket.IO presence events
 * as the in-page presence pills (iter 232b) so users on Lineups /
 * Matchup / Standings see incoming presence and can hop into Chat
 * to engage someone live without polling.
 *
 * Visibility:
 *   • Hidden on `md+` (desktop keeps the persistent left sidebar).
 *   • Hidden on `/login` / `/signup` / `/forgot-password` (no auth context).
 *   • When no active league is selected the presence bubble simply
 *     stays at 0 (the bar itself still renders so nav remains usable).
 *
 * Safe-area padding inset honours the iOS home-indicator (the PWA
 * runs in `standalone` mode — see iter 231as).
 */
import { useEffect, useRef, useState } from "react";
import { Home, MessageSquare, Users, ListChecks, Menu } from "lucide-react";
import { Link, useLocation } from "react-router-dom";
import { useSidebar } from "@/components/ui/sidebar";
import { useActiveLeague } from "@/hooks/use-active-league";
import { useAuth } from "@/contexts/AuthContext";
import { useLeagueSocket } from "@/hooks/use-socket";
import { triggerHaptic } from "@/hooks/use-haptic-preference";
import { cn } from "@/lib/utils";

const TABS = [
  { key: "home", label: "Home", icon: Home, path: "/dashboard" },
  { key: "matchup", label: "Matchup", icon: ListChecks, path: "/matchup" },
  { key: "chat", label: "Chat", icon: MessageSquare, path: "/chat" },
  { key: "team", label: "Roster", icon: Users, path: "/team" },
];

// Iter 232d — Length of the "someone just came online" bubble pulse
// (ms). Long enough to be felt in peripheral vision, short enough
// that a burst of joins doesn't turn the icon into a rave.
const PULSE_MS = 3000;

export default function MobileBottomNav() {
  const location = useLocation();
  const { user } = useAuth();
  const { leagueId } = useActiveLeague();
  const sidebar = useSidebar();

  // Subscribe to the league socket room so we can show the live
  // online count on the Chat tab. The socket singleton is shared
  // with the in-page hooks (see `use-socket.js`), so this does NOT
  // open a second connection — it just attaches another set of
  // event listeners on the existing one.
  const { onlineUserIds } = useLeagueSocket(leagueId, { userId: user?.id });
  const onlineCount = onlineUserIds?.size || 0;

  // Iter 232d — Pulse the Chat-tab bubble when the count *goes up*.
  // Ref-compare against the previous value so we only fire on
  // increases (not decreases / re-renders with same count). The
  // very first render establishes the baseline WITHOUT pulsing so
  // users don't see a mystery pulse on page load.
  const prevCountRef = useRef(null);
  const [pulsing, setPulsing] = useState(false);
  useEffect(() => {
    const prev = prevCountRef.current;
    prevCountRef.current = onlineCount;
    // Baseline — first observed value, no pulse.
    if (prev === null) return undefined;
    if (onlineCount > prev) {
      setPulsing(true);
      // Iter 232e — Layer a subtle 30ms haptic buzz alongside the
      // pulse when a manager comes online. Gated by
      // `useHapticPreference` (localStorage 'dd-haptics') so users
      // on shared devices can opt out. `triggerHaptic` is a safe
      // no-op on browsers without `navigator.vibrate` and when the
      // OS `prefers-reduced-motion` setting is on.
      triggerHaptic(30);
      const id = setTimeout(() => setPulsing(false), PULSE_MS);
      return () => clearTimeout(id);
    }
    return undefined;
  }, [onlineCount]);

  // Hide on auth routes.
  if (
    location.pathname.startsWith("/login") ||
    location.pathname.startsWith("/signup") ||
    location.pathname.startsWith("/forgot-password")
  ) {
    return null;
  }

  const isActive = (path) =>
    location.pathname === path || location.pathname.startsWith(`${path}/`);

  return (
    <nav
      className={cn(
        "fixed bottom-0 inset-x-0 z-40 md:hidden",
        "bg-[#0F0F14]/95 backdrop-blur-md",
        "border-t border-white/10",
        // Honour the iOS PWA home-indicator inset.
        "pb-[env(safe-area-inset-bottom)]",
      )}
      data-testid="mobile-bottom-nav"
      role="navigation"
      aria-label="Primary mobile navigation"
    >
      <ul className="grid grid-cols-5">
        {TABS.map(({ key, label, icon: Icon, path }) => {
          const active = isActive(path);
          const showChatBubble = key === "chat" && onlineCount > 0;
          return (
            <li key={key} className="flex">
              <Link
                to={path}
                data-testid={`mobile-bottom-nav-${key}`}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "flex flex-1 flex-col items-center justify-center gap-0.5",
                  "py-2 text-[10px] font-medium",
                  active ? "text-[#00D2FF]" : "text-[#A1A1AA]",
                  "transition-colors active:bg-white/5",
                )}
              >
                <span className="relative inline-flex">
                  <Icon className="h-5 w-5" />
                  {showChatBubble && (
                    <span
                      className={cn(
                        "absolute -top-1.5 -right-2",
                        "min-w-[16px] h-4 px-1 rounded-full",
                        "bg-[#34C759] text-[10px] font-bold text-[#0F0F14]",
                        "flex items-center justify-center",
                        "ring-2 ring-[#0F0F14]",
                        // Subtle ping ring so users notice the
                        // first time someone else comes online.
                        "shadow-[0_0_0_1px_rgba(52,199,89,0.5)]",
                        // Iter 232d — 3s pulse on count increase (a
                        // manager just came online). Halo ring + gentle
                        // scale so users feel the arrival in
                        // peripheral vision without the icon flashing
                        // aggressively.
                        pulsing && "mobile-nav-chat-pulse",
                      )}
                      data-testid="mobile-bottom-nav-chat-presence"
                      data-pulsing={pulsing ? "true" : "false"}
                      aria-label={`${onlineCount} online in league chat`}
                      title={`${onlineCount} online`}
                    >
                      {onlineCount > 99 ? "99+" : onlineCount}
                    </span>
                  )}
                </span>
                <span>{label}</span>
              </Link>
            </li>
          );
        })}
        {/* "More" — opens the existing sidebar drawer so users still
            have access to every other route (Standings, Draft, etc.). */}
        <li className="flex">
          <button
            type="button"
            data-testid="mobile-bottom-nav-more"
            onClick={() => sidebar?.setOpenMobile?.(true)}
            className={cn(
              "flex flex-1 flex-col items-center justify-center gap-0.5",
              "py-2 text-[10px] font-medium text-[#A1A1AA]",
              "transition-colors active:bg-white/5",
            )}
            aria-label="Open full navigation menu"
          >
            <Menu className="h-5 w-5" />
            <span>More</span>
          </button>
        </li>
      </ul>
    </nav>
  );
}
