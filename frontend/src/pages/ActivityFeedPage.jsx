import { useState, useEffect } from "react";
import { AppLayout } from "@/components/layout/AppLayout";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Activity, ArrowRightLeft, Users, Calendar, DollarSign, MessageSquare, Trophy, Clock, Shield, Send, ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";
import api from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { useLeagueSocket } from "@/hooks/use-socket";

const eventConfig = {
  trade_proposed: { icon: ArrowRightLeft, color: "text-[#00D2FF]", bg: "bg-[#00D2FF]/20" },
  trade_accepted: { icon: ArrowRightLeft, color: "text-[#34C759]", bg: "bg-[#34C759]/20" },
  trade_rejected: { icon: ArrowRightLeft, color: "text-[#FF3B30]", bg: "bg-[#FF3B30]/20" },
  roster_add: { icon: Users, color: "text-[#34C759]", bg: "bg-[#34C759]/20" },
  roster_drop: { icon: Users, color: "text-[#FF3B30]", bg: "bg-[#FF3B30]/20" },
  contract_signed: { icon: DollarSign, color: "text-[#00D2FF]", bg: "bg-[#00D2FF]/20" },
  draft_pick: { icon: Trophy, color: "text-[#FF9F0A]", bg: "bg-[#FF9F0A]/20" },
  waiver_processed: { icon: Clock, color: "text-[#FF9F0A]", bg: "bg-[#FF9F0A]/20" },
  week_simulated: { icon: Calendar, color: "text-[#34C759]", bg: "bg-[#34C759]/20" },
  commissioner: { icon: Shield, color: "text-[#FF9F0A]", bg: "bg-[#FF9F0A]/20" },
  chat: { icon: MessageSquare, color: "text-[#A1A1AA]", bg: "bg-[#A1A1AA]/20" },
};

function timeAgo(dateStr) {
  const diff = Date.now() - new Date(dateStr).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h`;
  return `${Math.floor(h / 24)}d`;
}

export default function ActivityFeedPage() {
  const { user } = useAuth();
  const [leagueId, setLeagueId] = useState(null);
  const [leagues, setLeagues] = useState([]);
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [filter, setFilter] = useState("all");
  const [chatInput, setChatInput] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const init = async () => {
      try {
        const { data } = await api.get("/leagues?my_leagues=true");
        setLeagues(data);
        if (data.length > 0) setLeagueId(data[0].id);
      } catch (e) { console.error(e); }
    };
    init();
  }, []);

  const fetchFeed = async (lid, f, p) => {
    if (!lid) return;
    setLoading(true);
    try {
      const params = new URLSearchParams({ limit: "30", page: p.toString() });
      if (f !== "all") params.append("event_type", f);
      const { data } = await api.get(`/activity/${lid}?${params}`);
      setItems(p === 1 ? data.items : prev => [...prev, ...data.items]);
      setTotal(data.total);
    } catch (e) { console.error(e); }
    setLoading(false);
  };

  useEffect(() => {
    setPage(1);
    fetchFeed(leagueId, filter, 1);
  }, [leagueId, filter]);

  // WebSocket: live feed updates
  const { connected } = useLeagueSocket(leagueId, {
    userId: user?.id,
    onTradeProposed: () => fetchFeed(leagueId, filter, 1),
    onTradeAccepted: () => fetchFeed(leagueId, filter, 1),
    onWaiversProcessed: () => fetchFeed(leagueId, filter, 1),
    onWeekSimulated: () => fetchFeed(leagueId, filter, 1),
  });

  // Also listen for activity_feed event directly (custom)
  useEffect(() => {
    if (!leagueId) return;
    const interval = setInterval(() => fetchFeed(leagueId, filter, 1), 15000);
    return () => clearInterval(interval);
  }, [leagueId, filter]);

  const handleSendChat = async () => {
    if (!chatInput.trim() || !leagueId) return;
    try {
      await api.post(`/activity/${leagueId}/chat`, { text: chatInput.trim() });
      setChatInput("");
      fetchFeed(leagueId, filter, 1);
    } catch (e) { console.error(e); }
  };

  const loadMore = () => {
    const next = page + 1;
    setPage(next);
    fetchFeed(leagueId, filter, next);
  };

  const filters = [
    { value: "all", label: "All Activity" },
    { value: "chat", label: "Chat" },
    { value: "roster_add", label: "Roster Adds" },
    { value: "roster_drop", label: "Roster Drops" },
    { value: "trade_proposed", label: "Trades" },
    { value: "contract_signed", label: "Contracts" },
    { value: "week_simulated", label: "Matchups" },
  ];

  return (
    <AppLayout>
      <div className="space-y-6" data-testid="activity-feed-page">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-white flex items-center gap-2">
              <Activity className="h-6 w-6 text-[#00D2FF]" />
              League Activity
            </h1>
            <div className="flex items-center gap-2 mt-1">
              <div className={cn("h-2 w-2 rounded-full", connected ? "bg-[#34C759]" : "bg-[#FF3B30]")} />
              <p className="text-[#A1A1AA] text-sm">{connected ? "Live updates" : "Connecting..."}</p>
            </div>
          </div>
          <div className="flex gap-3">
            <Select value={filter} onValueChange={setFilter}>
              <SelectTrigger className="w-40 bg-[#141414] border-white/10 text-white"><SelectValue /></SelectTrigger>
              <SelectContent className="bg-[#141414] border-white/10">{filters.map(f => <SelectItem key={f.value} value={f.value} className="text-white">{f.label}</SelectItem>)}</SelectContent>
            </Select>
            {leagues.length > 1 && (
              <Select value={leagueId || ""} onValueChange={setLeagueId}>
                <SelectTrigger className="w-44 bg-[#141414] border-white/10 text-white"><SelectValue /></SelectTrigger>
                <SelectContent className="bg-[#141414] border-white/10">{leagues.map(l => <SelectItem key={l.id} value={l.id} className="text-white">{l.name}</SelectItem>)}</SelectContent>
              </Select>
            )}
          </div>
        </div>

        {/* Chat input */}
        <Card className="border-white/10">
          <CardContent className="p-4">
            <div className="flex gap-3">
              <div className="h-9 w-9 rounded-full bg-[#00D2FF]/20 flex items-center justify-center text-sm font-bold text-[#00D2FF] shrink-0">{user?.name?.[0]?.toUpperCase()}</div>
              <Input placeholder="Post to league chat..." className="bg-[#1A1A1A] border-white/10 text-white flex-1" value={chatInput} onChange={e => setChatInput(e.target.value)} onKeyDown={e => e.key === "Enter" && handleSendChat()} data-testid="activity-chat-input" />
              <Button className="bg-[#00D2FF] text-black hover:bg-[#33DBFF]" onClick={handleSendChat} data-testid="activity-chat-send"><Send className="h-4 w-4" /></Button>
            </div>
          </CardContent>
        </Card>

        {/* Feed */}
        <div className="space-y-3">
          {loading && items.length === 0 ? (
            <Card className="border-white/10"><CardContent className="p-8 text-center text-[#A1A1AA]">Loading activity...</CardContent></Card>
          ) : items.length === 0 ? (
            <Card className="border-white/10"><CardContent className="p-8 text-center text-[#A1A1AA]">No activity yet. Be the first to post!</CardContent></Card>
          ) : (
            <>
              {items.map((item, i) => {
                const config = eventConfig[item.event_type] || { icon: Activity, color: "text-[#A1A1AA]", bg: "bg-[#A1A1AA]/20" };
                const Icon = config.icon;
                const isChat = item.event_type === "chat";

                return (
                  <div key={item._id || i} className={cn("flex gap-4 p-4 rounded-lg transition-colors", isChat ? "bg-transparent border border-white/5 hover:border-white/10" : "bg-[#141414] border border-white/10")}>
                    <div className={cn("h-10 w-10 rounded-lg flex items-center justify-center shrink-0", config.bg)}>
                      <Icon className={cn("h-5 w-5", config.color)} />
                    </div>
                    <div className="flex-1 min-w-0">
                      {isChat ? (
                        <div>
                          <span className="text-sm font-medium text-[#00D2FF]">{item.metadata?.sender || "User"}</span>
                          <p className="text-sm text-white mt-0.5">{item.message}</p>
                        </div>
                      ) : (
                        <p className="text-sm text-white">{item.message}</p>
                      )}
                      <div className="flex items-center gap-2 mt-1">
                        <span className="text-[10px] text-[#52525B]">{timeAgo(item.created_at)}</span>
                        <Badge variant="outline" className="text-[8px] text-[#A1A1AA] border-white/10">{item.event_type?.replace("_", " ")}</Badge>
                      </div>
                    </div>
                  </div>
                );
              })}
              {items.length < total && (
                <Button variant="outline" className="w-full border-white/10 text-[#A1A1AA]" onClick={loadMore}><ChevronDown className="h-4 w-4 mr-2" />Load More</Button>
              )}
            </>
          )}
        </div>
      </div>
    </AppLayout>
  );
}
