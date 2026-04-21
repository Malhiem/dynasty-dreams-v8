// @ts-nocheck
import { Bell, Star, AlertTriangle, TrendingUp, TrendingDown, Clock } from "lucide-react";
import { useState } from "react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

interface Notification {
  id: number;
  type: "injury" | "hot" | "cold" | "trade" | "news" | "lineup";
  player: string;
  team: string;
  message: string;
  time: string;
  isWatchlist?: boolean;
  priority: "high" | "medium" | "low";
}

const mockNotifications: Notification[] = [
  { id: 1, type: "injury", player: "Connor McDavid", team: "EDM", message: "Day-to-day with lower-body injury", time: "2h ago", priority: "high" },
  { id: 2, type: "hot", player: "Nathan MacKinnon", team: "COL", message: "5 goals, 8 points in last 5 games", time: "3h ago", priority: "medium" },
  { id: 3, type: "lineup", player: "Auston Matthews", team: "TOR", message: "Confirmed starting tonight vs BOS", time: "4h ago", priority: "low" },
  { id: 4, type: "trade", player: "Nikita Kucherov", team: "TBL", message: "Trade rumors linking to contenders", time: "5h ago", priority: "medium" },
  { id: 5, type: "cold", player: "Igor Shesterkin", team: "NYR", message: ".891 SV% in last 3 starts", time: "6h ago", priority: "medium" },
];

const mockWatchlistNotifications: Notification[] = [
  { id: 6, type: "hot", player: "Leon Draisaitl", team: "EDM", message: "6 goals in last 4 games", time: "1h ago", isWatchlist: true, priority: "high" },
  { id: 7, type: "injury", player: "Sidney Crosby", team: "PIT", message: "Expected to return next week", time: "2h ago", isWatchlist: true, priority: "medium" },
  { id: 8, type: "news", player: "Jack Hughes", team: "NJD", message: "Contract extension talks heating up", time: "4h ago", isWatchlist: true, priority: "low" },
  { id: 9, type: "trade", player: "Elias Pettersson", team: "VAN", message: "Could be available before deadline", time: "8h ago", isWatchlist: true, priority: "high" },
];

const getNotificationIcon = (type: Notification["type"]) => {
  switch (type) {
    case "injury": return <AlertTriangle className="h-4 w-4 text-destructive" />;
    case "hot": return <TrendingUp className="h-4 w-4 text-success" />;
    case "cold": return <TrendingDown className="h-4 w-4 text-blue-400" />;
    case "trade": return <Bell className="h-4 w-4 text-accent" />;
    case "lineup": return <Clock className="h-4 w-4 text-primary" />;
    case "news": return <Bell className="h-4 w-4 text-muted-foreground" />;
    default: return <Bell className="h-4 w-4 text-muted-foreground" />;
  }
};

const getNotificationBadge = (type: Notification["type"]) => {
  switch (type) {
    case "injury": return "bg-destructive/20 text-destructive";
    case "hot": return "bg-success/20 text-success";
    case "cold": return "bg-blue-500/20 text-blue-400";
    case "trade": return "bg-accent/20 text-accent";
    case "lineup": return "bg-primary/20 text-primary";
    case "news": return "bg-secondary text-secondary-foreground";
    default: return "bg-secondary text-secondary-foreground";
  }
};

const getPriorityIndicator = (priority: Notification["priority"]) => {
  switch (priority) {
    case "high": return "border-l-2 border-l-destructive";
    case "medium": return "border-l-2 border-l-accent";
    case "low": return "";
    default: return "";
  }
};

const NotificationItem = ({ notification }: { notification: Notification }) => (
  <div 
    className={`p-3 hover:bg-secondary/20 transition-colors ${getPriorityIndicator(notification.priority)}`}
  >
    <div className="flex items-start gap-3">
      <div className={`p-2 rounded-lg ${getNotificationBadge(notification.type)}`}>
        {getNotificationIcon(notification.type)}
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-1">
          <span className="font-medium text-sm text-foreground">{notification.player}</span>
          <span className="text-xs text-muted-foreground bg-secondary px-1.5 py-0.5 rounded">
            {notification.team}
          </span>
          {notification.isWatchlist && (
            <Star className="h-3 w-3 text-accent fill-accent" />
          )}
        </div>
        <p className="text-xs text-muted-foreground leading-relaxed">{notification.message}</p>
        <span className="text-xs text-muted-foreground/60 mt-1 block">{notification.time}</span>
      </div>
    </div>
  </div>
);

const PlayerNotifications = () => {
  const [activeTab, setActiveTab] = useState("roster");
  
  const rosterHighPriority = mockNotifications.filter(n => n.priority === "high").length;
  const watchlistHighPriority = mockWatchlistNotifications.filter(n => n.priority === "high").length;

  return (
    <div className="stat-card p-0 overflow-hidden">
      <div className="p-4 border-b border-border">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Bell className="h-5 w-5 text-primary" />
            <h3 className="text-lg font-semibold">Player Alerts</h3>
          </div>
          <span className="text-xs text-primary font-medium cursor-pointer hover:underline">Mark all read</span>
        </div>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
        <div className="px-4 pt-2">
          <TabsList className="grid w-full grid-cols-2 h-9">
            <TabsTrigger value="roster" className="text-xs relative">
              My Roster
              {rosterHighPriority > 0 && (
                <span className="absolute -top-1 -right-1 h-4 w-4 bg-destructive text-destructive-foreground text-xs rounded-full flex items-center justify-center">
                  {rosterHighPriority}
                </span>
              )}
            </TabsTrigger>
            <TabsTrigger value="watchlist" className="text-xs relative">
              Watchlist
              {watchlistHighPriority > 0 && (
                <span className="absolute -top-1 -right-1 h-4 w-4 bg-accent text-accent-foreground text-xs rounded-full flex items-center justify-center">
                  {watchlistHighPriority}
                </span>
              )}
            </TabsTrigger>
          </TabsList>
        </div>

        <TabsContent value="roster" className="m-0">
          <div className="divide-y divide-border/50 max-h-[300px] overflow-y-auto">
            {mockNotifications.map((notification) => (
              <NotificationItem key={notification.id} notification={notification} />
            ))}
          </div>
        </TabsContent>

        <TabsContent value="watchlist" className="m-0">
          <div className="divide-y divide-border/50 max-h-[300px] overflow-y-auto">
            {mockWatchlistNotifications.map((notification) => (
              <NotificationItem key={notification.id} notification={notification} />
            ))}
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
};

export default PlayerNotifications;