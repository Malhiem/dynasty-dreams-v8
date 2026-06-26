import { useState, useEffect, useCallback, useRef } from "react";
import { Bell, Check, CheckCheck, ArrowRightLeft, Clock, Trophy, Users, Calendar, Settings, AlertTriangle, Megaphone, Info, ExternalLink } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cn } from "@/lib/utils";
import { toast } from "sonner";
import api from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { useSocket } from "@/hooks/use-socket";
import NotificationSettings from "@/components/NotificationSettings";

// Iter 230 — Notification icon + color map.
// Source of truth for event ids: /app/backend/routes/notification_events.py
const iconMap = {
  // Trades
  trade_proposed: ArrowRightLeft,
  trade_accepted: Check,
  trade_accepted_mine: Check,
  trade_accepted_any: ArrowRightLeft,
  trade_declined_or_vetoed_mine: AlertTriangle,
  trade_vetoed_any: AlertTriangle,
  trade_processed: Check,
  trade_block_updated: Megaphone,
  // Draft
  draft_pick_made: Users,
  draft_your_turn: AlertTriangle,
  draft_on_deck: Clock,
  draft_coming_up: Clock,
  draft_scheduled: Calendar,
  draft_started: Calendar,
  draft_pick: Users,
  // Players / Roster
  waiver_claim_success: Trophy,
  player_to_waivers: Bell,
  lineup_lock_reminder: Clock,
  lineup_problem: AlertTriangle,
  player_injured: AlertTriangle,
  // Other
  league_chat_message: Bell,
};

const colorMap = {
  trade_proposed: "text-[#00D2FF]",
  trade_accepted: "text-[#34C759]",
  trade_accepted_mine: "text-[#34C759]",
  trade_accepted_any: "text-[#00D2FF]",
  trade_declined_or_vetoed_mine: "text-[#FF3B30]",
  trade_vetoed_any: "text-[#FF9F0A]",
  trade_processed: "text-[#34C759]",
  trade_block_updated: "text-[#FF9F0A]",
  draft_pick_made: "text-[#00D2FF]",
  draft_your_turn: "text-[#FF9F0A]",
  draft_on_deck: "text-[#FF9F0A]",
  draft_coming_up: "text-[#A1A1AA]",
  draft_scheduled: "text-[#00D2FF]",
  waiver_claim_success: "text-[#34C759]",
  player_to_waivers: "text-[#A1A1AA]",
  lineup_lock_reminder: "text-[#FF9F0A]",
  lineup_problem: "text-[#FF3B30]",
  player_injured: "text-[#FF3B30]",
  league_chat_message: "text-[#A1A1AA]",
};

// Iter 230h — "Why am I being notified?" reason map. Mirrors the
// `description` field from /app/backend/routes/notification_events.py
// so users can click the (i) icon and immediately understand which
// event subscription fired this alert. Keep in lock-step with the
// backend catalog.
const reasonMap = {
  trade_proposed: "You're subscribed to trade offers in this league.",
  trade_accepted: "A trade involving your team reached the accepted state.",
  trade_accepted_mine: "A trade involving your team reached the accepted state.",
  trade_accepted_any: "You're subscribed to all accepted league trades.",
  trade_declined_or_vetoed_mine: "A trade you proposed was rejected, vetoed by a league vote, or overruled by the commissioner.",
  trade_vetoed_any: "A trade in your league was vetoed.",
  trade_processed: "A trade in your league finished processing — assets have swapped.",
  trade_block_updated: "Another manager added or removed a listing on the league trade block.",
  draft_pick_made: "You're subscribed to every pick made in your league's draft.",
  draft_your_turn: "Your team is on the clock — the timer has started.",
  draft_on_deck: "Your team picks immediately after the active pick.",
  draft_coming_up: "Your team picks within the next 5 picks.",
  draft_scheduled: "The commissioner created or rescheduled a draft in this league.",
  draft_started: "A draft you're in just started.",
  draft_pick: "A pick was made in this draft.",
  waiver_claim_success: "Your waiver claim was successfully processed.",
  player_to_waivers: "A player you were watching entered the waiver pool.",
  player_dropped: "A manager dropped a player to free agency.",
  lineup_lock_reminder: "Your weekly/daily lineup locks soon — last chance to set it.",
  lineup_problem: "Your active lineup has empty or invalid slots before lock.",
  player_injured: "One of your active players was placed on IR or marked OUT.",
  player_recovered: "One of your players has returned to active duty.",
  player_injury_status: "Status update on a rostered player (e.g. day-to-day → IR-LT).",
  player_sent_down: "One of your players was demoted to the minors.",
  player_called_up: "One of your minor-league players was promoted.",
  reminder_important: "Upcoming draft, trade deadline, or season start.",
  rule_changed: "The commissioner modified a league rule or setting.",
  league_admin_action: "The commissioner performed an action affecting the league.",
  league_chat_message: "A new message was posted in your league chat.",
};

function timeAgo(dateStr) {
  const diff = Date.now() - new Date(dateStr).getTime();
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

export function NotificationsPanel() {
  const { user } = useAuth();
  const [open, setOpen] = useState(false);
  const [notifications, setNotifications] = useState([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const panelRef = useRef(null);

  const fetchNotifications = useCallback(async () => {
    if (!user) return;
    try {
      const [notifsRes, countRes] = await Promise.all([
        api.get("/notifications?limit=20"),
        api.get("/notifications/count"),
      ]);
      setNotifications(notifsRes.data);
      setUnreadCount(countRes.data.count);
    } catch (e) { /* auth may not be ready yet */ }
  }, [user]);

  useEffect(() => {
    fetchNotifications();
    const interval = setInterval(fetchNotifications, 30000);
    return () => clearInterval(interval);
  }, [fetchNotifications]);

  // Iter 230 — Real-time delivery via Socket.IO. The backend auto-joins
  // each authenticated client to `user_{id}` server-side; the hook
  // double-joins (no-op) and registers our `notification` listener.
  useSocket(
    user?.id ? `user_${user.id}` : null,
    {
      notification: (payload) => {
        if (!payload) return;
        setNotifications((prev) => {
          if (prev.some((n) => n._id === payload._id)) return prev;
          return [payload, ...prev].slice(0, 50);
        });
        setUnreadCount((c) => c + 1);
        try {
          toast(payload.title || "New notification", {
            description: payload.message,
            action: {
              label: "Notification settings",
              onClick: () => setSettingsOpen(true),
            },
          });
        } catch { /* sonner missing — non-critical */ }
      },
    },
    user?.id,
  );

  // Close on outside click
  useEffect(() => {
    const handler = (e) => {
      if (panelRef.current && !panelRef.current.contains(e.target)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const handleMarkAllRead = async () => {
    try {
      await api.post("/notifications/read-all");
      setNotifications(prev => prev.map(n => ({ ...n, read: true })));
      setUnreadCount(0);
    } catch (e) { console.error(e); }
  };

  const handleMarkRead = async (id) => {
    try {
      await api.post(`/notifications/${id}/read`);
      setNotifications(prev => prev.map(n => n._id === id ? { ...n, read: true } : n));
      setUnreadCount(prev => Math.max(0, prev - 1));
    } catch (e) { console.error(e); }
  };

  return (
    <div className="relative" ref={panelRef}>
      <Button
        variant="ghost"
        size="icon"
        className="relative text-[#A1A1AA] hover:text-white"
        onClick={() => setOpen(!open)}
        data-testid="notifications-btn"
      >
        <Bell className="h-5 w-5" />
        {unreadCount > 0 && (
          <span className="absolute -top-0.5 -right-0.5 h-5 w-5 rounded-full bg-[#FF3B30] flex items-center justify-center text-[10px] font-bold text-white">
            {unreadCount > 9 ? "9+" : unreadCount}
          </span>
        )}
      </Button>

      {open && (
        <div className="absolute right-0 top-12 w-96 bg-[#141414] border border-white/10 rounded-lg shadow-2xl z-50" data-testid="notifications-panel">
          <div className="flex items-center justify-between p-4 border-b border-white/10">
            <h3 className="font-semibold text-white">Notifications</h3>
            <div className="flex items-center gap-1">
              {unreadCount > 0 && (
                <Button variant="ghost" size="sm" className="text-[#00D2FF] text-xs" onClick={handleMarkAllRead} data-testid="mark-all-read">
                  <CheckCheck className="h-3.5 w-3.5 mr-1" />Mark all read
                </Button>
              )}
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7 text-[#A1A1AA] hover:text-white"
                onClick={() => { setOpen(false); setSettingsOpen(true); }}
                data-testid="notification-settings-btn"
                title="Notification settings"
              >
                <Settings className="h-4 w-4" />
              </Button>
            </div>
          </div>
          <ScrollArea className="max-h-[400px]">
            {notifications.length === 0 ? (
              <div className="p-8 text-center text-[#A1A1AA]">
                <Bell className="h-8 w-8 mx-auto mb-2 opacity-50" />
                <p>No notifications yet</p>
              </div>
            ) : (
              <div className="divide-y divide-white/5">
                {notifications.map(n => {
                  const Icon = iconMap[n.type] || Bell;
                  const color = colorMap[n.type] || "text-[#A1A1AA]";
                  const reason = n.reason || reasonMap[n.type] || "You're subscribed to this notification type. Update your preferences any time.";
                  return (
                    <div
                      key={n._id}
                      className={cn("p-3 hover:bg-white/5 cursor-pointer transition-colors flex gap-3", !n.read && "bg-[#00D2FF]/5")}
                      onClick={() => handleMarkRead(n._id)}
                      data-testid={`notification-item-${n._id}`}
                    >
                      <div className={cn("h-8 w-8 rounded-lg flex items-center justify-center shrink-0", `${color.replace("text-", "bg-")}/20`)}>
                        <Icon className={cn("h-4 w-4", color)} />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <p className={cn("text-sm font-medium truncate", n.read ? "text-[#A1A1AA]" : "text-white")}>{n.title}</p>
                          {!n.read && <div className="h-2 w-2 rounded-full bg-[#00D2FF] shrink-0" />}
                        </div>
                        <p className="text-xs text-[#A1A1AA] truncate">{n.message}</p>
                        <p className="text-[10px] text-[#52525B] mt-0.5">{timeAgo(n.created_at)}</p>
                      </div>
                      <Popover>
                        <PopoverTrigger asChild>
                          <button
                            type="button"
                            aria-label="Why am I being notified?"
                            title="Why am I being notified?"
                            onClick={(e) => e.stopPropagation()}
                            data-testid={`notif-why-btn-${n._id}`}
                            className="h-6 w-6 rounded-md text-[#52525B] hover:text-[#00D2FF] hover:bg-white/5 flex items-center justify-center shrink-0 transition-colors self-start"
                          >
                            <Info className="h-3.5 w-3.5" />
                          </button>
                        </PopoverTrigger>
                        <PopoverContent
                          align="end"
                          side="left"
                          className="w-72 bg-[#141414] border border-white/10 text-white p-3"
                          onClick={(e) => e.stopPropagation()}
                          data-testid={`notif-why-popover-${n._id}`}
                        >
                          <div className="flex items-start gap-2 mb-2">
                            <Info className="h-4 w-4 text-[#00D2FF] shrink-0 mt-0.5" />
                            <div className="text-sm font-semibold text-white">Why am I being notified?</div>
                          </div>
                          <p className="text-xs text-[#A1A1AA] leading-relaxed">{reason}</p>
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              setOpen(false);
                              setSettingsOpen(true);
                            }}
                            data-testid={`notif-why-manage-${n._id}`}
                            className="mt-3 inline-flex items-center gap-1 text-[11px] font-semibold text-[#00D2FF] hover:underline"
                          >
                            Manage notification preferences
                            <ExternalLink className="h-3 w-3" />
                          </button>
                        </PopoverContent>
                      </Popover>
                    </div>
                  );
                })}
              </div>
            )}
          </ScrollArea>
        </div>
      )}

      {/* Iter 230 — Settings modal */}
      <NotificationSettings open={settingsOpen} onOpenChange={setSettingsOpen} />
    </div>
  );
}
