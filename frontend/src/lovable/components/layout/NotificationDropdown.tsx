// @ts-nocheck
import { useState } from "react";
import { Bell, Star, AlertTriangle, TrendingUp, TrendingDown, Clock, RefreshCw, Filter, Check } from "lucide-react";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";

type NotificationType = "injury" | "hot" | "cold" | "trade_proposal" | "news" | "watchlist";

interface Notification {
  id: number;
  type: NotificationType;
  title: string;
  message: string;
  time: string;
  read: boolean;
  player?: string;
  team?: string;
}

const mockNotifications: Notification[] = [
  { id: 1, type: "trade_proposal", title: "Trade Proposal Received", message: "Ice Breakers offer J. Hughes + 2025 2nd for your A. Matthews", time: "15m ago", read: false },
  { id: 2, type: "injury", title: "Injury Alert", player: "Connor McDavid", team: "EDM", message: "Day-to-day with lower-body injury — on your roster", time: "1h ago", read: false },
  { id: 3, type: "watchlist", title: "Watchlist Update", player: "Leon Draisaitl", team: "EDM", message: "6 goals in last 4 games — trending up", time: "2h ago", read: false },
  { id: 4, type: "news", title: "Player News", player: "Jack Hughes", team: "NJD", message: "Contract extension talks heating up", time: "3h ago", read: true },
  { id: 5, type: "trade_proposal", title: "Trade Proposal Accepted", message: "Your trade with Frozen Assets has been accepted by the league", time: "4h ago", read: true },
  { id: 6, type: "watchlist", title: "Watchlist Update", player: "Elias Pettersson", team: "VAN", message: "Could be available before trade deadline", time: "5h ago", read: true },
  { id: 7, type: "hot", title: "Hot Streak", player: "Nathan MacKinnon", team: "COL", message: "5 goals, 8 points in last 5 games", time: "6h ago", read: true },
  { id: 8, type: "news", title: "League Announcement", message: "Trade deadline is in 5 days — all proposals must be submitted", time: "8h ago", read: true },
  { id: 9, type: "cold", title: "Cold Streak", player: "Igor Shesterkin", team: "NYR", message: ".891 SV% in last 3 starts — on your roster", time: "10h ago", read: true },
];

const filterOptions: { value: NotificationType | "all"; label: string }[] = [
  { value: "all", label: "All" },
  { value: "news", label: "News" },
  { value: "trade_proposal", label: "Trades" },
  { value: "watchlist", label: "Watchlist" },
  { value: "injury", label: "Injuries" },
];

const getIcon = (type: NotificationType) => {
  switch (type) {
    case "injury": return <AlertTriangle className="h-4 w-4 text-destructive" />;
    case "hot": return <TrendingUp className="h-4 w-4 text-success" />;
    case "cold": return <TrendingDown className="h-4 w-4 text-blue-400" />;
    case "trade_proposal": return <RefreshCw className="h-4 w-4 text-accent" />;
    case "watchlist": return <Star className="h-4 w-4 text-accent fill-accent" />;
    case "news": return <Bell className="h-4 w-4 text-primary" />;
  }
};

const getIconBg = (type: NotificationType) => {
  switch (type) {
    case "injury": return "bg-destructive/15";
    case "hot": return "bg-success/15";
    case "cold": return "bg-blue-500/15";
    case "trade_proposal": return "bg-accent/15";
    case "watchlist": return "bg-accent/15";
    case "news": return "bg-primary/15";
  }
};

export function NotificationDropdown() {
  const [notifications, setNotifications] = useState(mockNotifications);
  const [filter, setFilter] = useState<NotificationType | "all">("all");
  const [open, setOpen] = useState(false);

  const unreadCount = notifications.filter(n => !n.read).length;

  const filtered = filter === "all"
    ? notifications
    : notifications.filter(n => n.type === filter);

  const markAllRead = () => {
    setNotifications(prev => prev.map(n => ({ ...n, read: true })));
  };

  const markRead = (id: number) => {
    setNotifications(prev => prev.map(n => n.id === id ? { ...n, read: true } : n));
  };

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="ghost" size="icon" className="relative">
          <Bell className="h-5 w-5" />
          {unreadCount > 0 && (
            <span className="absolute -top-0.5 -right-0.5 h-4 w-4 rounded-full bg-destructive text-[10px] font-medium flex items-center justify-center text-destructive-foreground">
              {unreadCount}
            </span>
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-[380px] p-0" align="end" sideOffset={8}>
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-border">
          <h3 className="font-semibold text-sm">Notifications</h3>
          {unreadCount > 0 && (
            <button
              onClick={markAllRead}
              className="text-xs text-primary hover:underline flex items-center gap-1"
            >
              <Check className="h-3 w-3" />
              Mark all read
            </button>
          )}
        </div>

        {/* Filter chips */}
        <div className="flex items-center gap-1.5 px-4 py-2 border-b border-border overflow-x-auto">
          <Filter className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
          {filterOptions.map(opt => (
            <button
              key={opt.value}
              onClick={() => setFilter(opt.value)}
              className={`text-xs px-2.5 py-1 rounded-full whitespace-nowrap transition-colors ${
                filter === opt.value
                  ? "bg-primary/20 text-primary border border-primary/30"
                  : "bg-secondary text-muted-foreground hover:text-foreground border border-transparent"
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>

        {/* Notification list */}
        <ScrollArea className="max-h-[400px]">
          {filtered.length === 0 ? (
            <div className="py-8 text-center text-sm text-muted-foreground">
              No notifications
            </div>
          ) : (
            <div className="divide-y divide-border/50">
              {filtered.map(n => (
                <button
                  key={n.id}
                  onClick={() => markRead(n.id)}
                  className={`w-full text-left px-4 py-3 hover:bg-secondary/30 transition-colors flex gap-3 ${
                    !n.read ? "bg-primary/5" : ""
                  }`}
                >
                  <div className={`shrink-0 p-2 rounded-lg mt-0.5 ${getIconBg(n.type)}`}>
                    {getIcon(n.type)}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-0.5">
                      <span className={`text-sm font-medium truncate ${!n.read ? "text-foreground" : "text-muted-foreground"}`}>
                        {n.title}
                      </span>
                      {!n.read && (
                        <span className="h-2 w-2 rounded-full bg-primary shrink-0" />
                      )}
                    </div>
                    {n.player && (
                      <div className="flex items-center gap-1.5 mb-0.5">
                        <span className="text-xs font-medium text-foreground">{n.player}</span>
                        <Badge variant="secondary" className="text-[10px] px-1 py-0 h-4">{n.team}</Badge>
                      </div>
                    )}
                    <p className="text-xs text-muted-foreground line-clamp-2">{n.message}</p>
                    <span className="text-[11px] text-muted-foreground/60 mt-1 block">{n.time}</span>
                  </div>
                </button>
              ))}
            </div>
          )}
        </ScrollArea>

        <Separator />
        <div className="p-2">
          <Button variant="ghost" size="sm" className="w-full text-xs text-muted-foreground hover:text-foreground">
            View all notifications
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  );
}
