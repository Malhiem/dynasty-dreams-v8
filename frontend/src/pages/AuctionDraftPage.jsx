import { useState, useEffect, useCallback } from "react";
import { AppLayout } from "@/components/layout/AppLayout";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Progress } from "@/components/ui/progress";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Gavel, DollarSign, Search, Timer, Users, TrendingUp, Send, MessageSquare, Play, AlertCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import api from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { useParams } from "react-router-dom";
import { useDraftSocket } from "@/hooks/use-socket";

const positionColors = {
  C: "bg-blue-600/80 text-blue-100 border-blue-500/50",
  LW: "bg-emerald-600/80 text-emerald-100 border-emerald-500/50",
  RW: "bg-teal-600/80 text-teal-100 border-teal-500/50",
  D: "bg-amber-600/80 text-amber-100 border-amber-500/50",
  G: "bg-purple-600/80 text-purple-100 border-purple-500/50",
};

export default function AuctionDraftPage() {
  const { id: draftId } = useParams();
  const { user } = useAuth();

  const [draft, setDraft] = useState(null);
  const [auctionState, setAuctionState] = useState(null);
  const [players, setPlayers] = useState([]);
  const [chatMessages, setChatMessages] = useState([]);
  const [chatInput, setChatInput] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [posFilter, setPosFilter] = useState("all");
  const [bidAmount, setBidAmount] = useState(1);
  const [nominateAmount, setNominateAmount] = useState(1);
  const [auctionTimer, setAuctionTimer] = useState(15);
  const [loading, setLoading] = useState(true);

  const fetchDraft = useCallback(async () => {
    if (!draftId) return;
    try {
      const [draftRes, auctionRes] = await Promise.all([
        api.get(`/drafts/${draftId}`),
        api.get(`/drafts/${draftId}/auction/state`),
      ]);
      setDraft(draftRes.data);
      setAuctionState(auctionRes.data);
      setChatMessages(draftRes.data.chat_messages || []);
    } catch (e) { console.error(e); }
  }, [draftId]);

  const fetchPlayers = useCallback(async () => {
    if (!draftId) return;
    try {
      const params = new URLSearchParams();
      if (searchQuery) params.append("search", searchQuery);
      if (posFilter !== "all") params.append("position", posFilter);
      params.append("limit", "30");
      const { data } = await api.get(`/drafts/${draftId}/eligible-players?${params}`);
      setPlayers(data.players || []);
    } catch (e) { console.error(e); }
  }, [draftId, searchQuery, posFilter]);

  useEffect(() => {
    const init = async () => {
      setLoading(true);
      await fetchDraft();
      await fetchPlayers();
      setLoading(false);
    };
    init();
  }, [fetchDraft, fetchPlayers]);

  useEffect(() => {
    const t = setTimeout(fetchPlayers, 300);
    return () => clearTimeout(t);
  }, [searchQuery, posFilter, fetchPlayers]);

  // Auction timer countdown
  useEffect(() => {
    const auction = auctionState?.active_auction;
    if (!auction) { setAuctionTimer(0); return; }
    setAuctionTimer(auction.timer_seconds || 15);
    const interval = setInterval(() => {
      setAuctionTimer(prev => Math.max(0, prev - 1));
    }, 1000);
    return () => clearInterval(interval);
  }, [auctionState?.active_auction?.current_bid]);

  // WebSocket
  const { connected } = useDraftSocket(draftId, {
    userId: user?.id,
    onDraftStarted: () => fetchDraft(),
    onDraftPick: () => { fetchDraft(); fetchPlayers(); },
    onChatMessage: (msg) => setChatMessages(prev => [...prev, msg]),
    onDraftCompleted: () => fetchDraft(),
  });

  // Poll for auction state
  useEffect(() => {
    if (!draftId || !draft?.draft_started) return;
    const interval = setInterval(fetchDraft, 3000);
    return () => clearInterval(interval);
  }, [draftId, draft?.draft_started, fetchDraft]);

  const handleNominate = async (playerId) => {
    try {
      await api.post(`/drafts/${draftId}/auction/nominate`, { player_id: playerId, opening_bid: nominateAmount });
      await fetchDraft();
    } catch (e) { alert(e.response?.data?.detail || "Failed"); }
  };

  const handleBid = async () => {
    try {
      await api.post(`/drafts/${draftId}/auction/bid`, { amount: bidAmount });
      await fetchDraft();
    } catch (e) { alert(e.response?.data?.detail || "Failed"); }
  };

  const handleResolve = async () => {
    try {
      await api.post(`/drafts/${draftId}/auction/resolve`);
      await fetchDraft();
      await fetchPlayers();
    } catch (e) { alert(e.response?.data?.detail || "Failed"); }
  };

  const handleStartDraft = async () => {
    try {
      await api.post(`/drafts/${draftId}/auction/init-budgets`);
      await api.post(`/drafts/${draftId}/start?early_start=true`);
      await fetchDraft();
    } catch (e) { alert(e.response?.data?.detail || "Failed"); }
  };

  const handleSendChat = async () => {
    if (!chatInput.trim()) return;
    try {
      await api.post(`/drafts/${draftId}/chat`, { text: chatInput.trim() });
      setChatInput("");
      await fetchDraft();
    } catch (e) { console.error(e); }
  };

  const activeAuction = auctionState?.active_auction;
  const budgets = auctionState?.budgets || [];
  const picks = draft?.picks || [];
  const isActive = draft?.status === "active";
  const isStarted = draft?.draft_started;
  const myBudget = budgets.find(b => b.team_name === user?.name || b.team_id)?.budget_remaining || 0;

  if (loading) {
    return <AppLayout><div className="flex items-center justify-center h-[60vh] text-[#A1A1AA]">Loading auction draft...</div></AppLayout>;
  }

  return (
    <AppLayout>
      <div className="space-y-4" data-testid="auction-draft-page">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-white flex items-center gap-2">
              <Gavel className="h-6 w-6 text-[#00D2FF]" />
              Auction Draft
            </h1>
            <p className="text-sm text-[#A1A1AA]">{draft?.league_name} — {picks.length} players drafted</p>
          </div>
          {!isStarted && (
            <Button className="bg-[#00D2FF] text-black hover:bg-[#33DBFF]" onClick={handleStartDraft} data-testid="start-auction">
              <Play className="h-4 w-4 mr-2" />Start Auction Draft
            </Button>
          )}
          <div className="flex items-center gap-2">
            <div className={cn("h-2 w-2 rounded-full", connected ? "bg-[#34C759]" : "bg-[#FF3B30]")} />
            <span className="text-xs text-[#A1A1AA]">{connected ? "Live" : "Connecting..."}</span>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
          {/* Active Auction Card */}
          <div className="lg:col-span-5">
            <Card className={cn("border-white/10", activeAuction && "border-[#00D2FF]/50 ring-1 ring-[#00D2FF]/20")}>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm text-white flex items-center gap-2"><Gavel className="h-4 w-4 text-[#00D2FF]" />Current Auction</CardTitle>
              </CardHeader>
              <CardContent>
                {!isStarted ? (
                  <div className="text-center py-8">
                    <Gavel className="h-12 w-12 text-[#52525B] mx-auto mb-3" />
                    <p className="text-[#A1A1AA]">Draft not started yet</p>
                  </div>
                ) : !activeAuction ? (
                  <div className="text-center py-8">
                    <p className="text-[#A1A1AA] mb-4">No active auction — nominate a player</p>
                  </div>
                ) : (
                  <div className="space-y-4">
                    {/* Player being auctioned */}
                    <div className="bg-[#1A1A1A] rounded-lg p-4">
                      <div className="flex items-center gap-3 mb-3">
                        <div className="h-14 w-14 rounded-lg bg-[#0A0A0A] flex items-center justify-center text-sm font-bold text-[#00D2FF]">
                          {activeAuction.player_team}
                        </div>
                        <div>
                          <h3 className="text-lg font-bold text-white">{activeAuction.player_name}</h3>
                          <Badge className={cn("text-xs", positionColors[activeAuction.player_position])}>{activeAuction.player_position}</Badge>
                        </div>
                      </div>
                      <div className="text-center py-3 bg-[#0A0A0A] rounded-lg">
                        <p className="text-xs text-[#A1A1AA] uppercase tracking-wider">Current Bid</p>
                        <p className="text-4xl font-bold text-[#00D2FF]" data-testid="current-bid">${activeAuction.current_bid}</p>
                        <p className="text-sm text-[#A1A1AA]">by {activeAuction.current_bidder_team_name}</p>
                      </div>
                    </div>

                    {/* Timer */}
                    <div className="space-y-1">
                      <div className="flex justify-between text-xs">
                        <span className="text-[#A1A1AA] flex items-center gap-1"><Timer className="h-3 w-3" />Auction Timer</span>
                        <span className={cn("font-mono font-bold text-lg", auctionTimer <= 5 ? "text-[#FF3B30]" : "text-[#00D2FF]")}>{auctionTimer}s</span>
                      </div>
                      <Progress value={(auctionTimer / 15) * 100} className="h-2" />
                    </div>

                    {/* Bid input */}
                    <div className="flex gap-2">
                      <div className="relative flex-1">
                        <DollarSign className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-[#A1A1AA]" />
                        <Input type="number" min={activeAuction.current_bid + 1} value={bidAmount} onChange={e => setBidAmount(parseFloat(e.target.value) || 0)} className="pl-8 bg-[#1A1A1A] border-white/10 text-white" data-testid="bid-input" />
                      </div>
                      <Button className="bg-[#00D2FF] text-black hover:bg-[#33DBFF] px-6" onClick={handleBid} data-testid="place-bid">
                        <TrendingUp className="h-4 w-4 mr-1" />Bid
                      </Button>
                    </div>

                    {/* Quick bid buttons */}
                    <div className="flex gap-2">
                      {[1, 5, 10, 25].map(inc => (
                        <Button key={inc} variant="outline" size="sm" className="flex-1 border-white/10 text-white" onClick={() => { setBidAmount(activeAuction.current_bid + inc); }}>
                          +${inc}
                        </Button>
                      ))}
                    </div>

                    {/* Resolve (commissioner) */}
                    {auctionTimer <= 0 && (
                      <Button className="w-full bg-[#34C759] text-black" onClick={handleResolve} data-testid="resolve-auction">
                        <Gavel className="h-4 w-4 mr-2" />Resolve — SOLD to {activeAuction.current_bidder_team_name}
                      </Button>
                    )}

                    {/* Bid history */}
                    <div className="space-y-1 max-h-32 overflow-y-auto">
                      {(activeAuction.bid_history || []).slice().reverse().map((bid, i) => (
                        <div key={i} className="flex items-center justify-between text-xs p-1.5 rounded bg-[#0A0A0A]/50">
                          <span className="text-[#A1A1AA]">{bid.team_name}</span>
                          <span className="text-[#00D2FF] font-semibold">${bid.amount}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Team Budgets */}
            <Card className="border-white/10 mt-4">
              <CardHeader className="pb-2"><CardTitle className="text-sm text-white flex items-center gap-2"><DollarSign className="h-4 w-4 text-[#00D2FF]" />Team Budgets</CardTitle></CardHeader>
              <CardContent>
                <div className="space-y-2">
                  {budgets.map(b => (
                    <div key={b.team_id} className="flex items-center justify-between p-2 rounded bg-[#1A1A1A]/30">
                      <div>
                        <p className="text-sm font-medium text-white">{b.team_name}</p>
                        <p className="text-[10px] text-[#A1A1AA]">{b.players_won} players</p>
                      </div>
                      <p className={cn("font-semibold", b.budget_remaining > 50 ? "text-[#34C759]" : b.budget_remaining > 20 ? "text-[#FF9F0A]" : "text-[#FF3B30]")}>
                        ${b.budget_remaining}
                      </p>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Player List + Chat */}
          <div className="lg:col-span-7 space-y-4">
            {/* Player Search & Nominate */}
            <Card className="border-white/10">
              <CardHeader className="pb-2"><CardTitle className="text-sm text-white">Nominate Player</CardTitle></CardHeader>
              <CardContent>
                <div className="flex gap-2 mb-3">
                  <div className="relative flex-1">
                    <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-[#A1A1AA]" />
                    <Input placeholder="Search players..." className="pl-8 h-8 text-sm bg-[#1A1A1A] border-white/10 text-white" value={searchQuery} onChange={e => setSearchQuery(e.target.value)} data-testid="auction-search" />
                  </div>
                  <Select value={posFilter} onValueChange={setPosFilter}>
                    <SelectTrigger className="w-24 h-8 text-xs bg-[#1A1A1A] border-white/10 text-white"><SelectValue /></SelectTrigger>
                    <SelectContent className="bg-[#141414] border-white/10">
                      {["all","C","LW","RW","D","G"].map(p => <SelectItem key={p} value={p} className="text-white">{p === "all" ? "All" : p}</SelectItem>)}
                    </SelectContent>
                  </Select>
                  <div className="flex items-center gap-1">
                    <span className="text-xs text-[#A1A1AA]">$</span>
                    <Input type="number" min={1} value={nominateAmount} onChange={e => setNominateAmount(parseFloat(e.target.value) || 1)} className="w-16 h-8 text-sm bg-[#1A1A1A] border-white/10 text-white text-center" data-testid="nominate-amount" />
                  </div>
                </div>
                <ScrollArea className="h-[250px]">
                  <div className="space-y-1">
                    {players.map(player => (
                      <div key={player.id} className="flex items-center gap-2 p-2 rounded-md hover:bg-[#1A1A1A]/40 transition-colors group">
                        <Badge className={cn("text-[9px] px-1 py-0 h-3.5 border", positionColors[player.position])}>{player.position}</Badge>
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium text-white truncate">{player.name}</p>
                          <p className="text-[10px] text-[#A1A1AA]">{player.nhlTeam} · {player.pts}P</p>
                        </div>
                        {isActive && !activeAuction && (
                          <Button size="sm" className="h-7 bg-[#00D2FF] text-black text-xs opacity-0 group-hover:opacity-100" onClick={() => handleNominate(player.id)} data-testid={`nominate-${player.id}`}>
                            Nominate
                          </Button>
                        )}
                      </div>
                    ))}
                  </div>
                </ScrollArea>
              </CardContent>
            </Card>

            {/* Chat */}
            <Card className="border-white/10">
              <CardHeader className="pb-2"><CardTitle className="text-sm text-white flex items-center gap-2"><MessageSquare className="h-4 w-4 text-[#00D2FF]" />Draft Chat</CardTitle></CardHeader>
              <CardContent className="p-2 space-y-2">
                <ScrollArea className="h-[180px]">
                  <div className="space-y-2 p-1">
                    {chatMessages.map(msg => (
                      <div key={msg.id} className={cn("text-xs rounded-md p-2", msg.type === "pick" ? "bg-[#00D2FF]/10 border border-[#00D2FF]/20" : "bg-[#1A1A1A]/40")}>
                        <span className={cn("font-semibold text-[11px] mr-2", msg.type === "pick" ? "text-[#00D2FF]" : "text-white")}>{msg.sender}</span>
                        <span className="text-[#A1A1AA]">{msg.text}</span>
                      </div>
                    ))}
                  </div>
                </ScrollArea>
                <div className="flex gap-2">
                  <Input placeholder="Type a message..." className="h-8 text-sm bg-[#1A1A1A] border-white/10 text-white flex-1" value={chatInput} onChange={e => setChatInput(e.target.value)} onKeyDown={e => e.key === "Enter" && handleSendChat()} />
                  <Button size="icon" className="h-8 w-8 bg-[#00D2FF] text-black" onClick={handleSendChat}><Send className="h-3.5 w-3.5" /></Button>
                </div>
              </CardContent>
            </Card>

            {/* Recent Picks */}
            {picks.length > 0 && (
              <Card className="border-white/10">
                <CardHeader className="pb-2"><CardTitle className="text-sm text-white">Recent Picks ({picks.length})</CardTitle></CardHeader>
                <CardContent>
                  <ScrollArea className="h-[120px]">
                    <div className="space-y-1">
                      {picks.slice().reverse().slice(0, 10).map((pick, i) => (
                        <div key={i} className="flex items-center justify-between p-2 rounded bg-[#1A1A1A]/30 text-xs">
                          <div className="flex items-center gap-2">
                            <span className="text-[#A1A1AA]">#{pick.overall}</span>
                            <Badge className={cn("text-[9px] px-1 py-0 h-3.5 border", positionColors[pick.player?.position])}>{pick.player?.position}</Badge>
                            <span className="text-white font-medium">{pick.player?.name}</span>
                          </div>
                          <div className="flex items-center gap-3">
                            <span className="text-[#A1A1AA]">{pick.team}</span>
                            {pick.auction_price && <span className="text-[#00D2FF] font-semibold">${pick.auction_price}</span>}
                          </div>
                        </div>
                      ))}
                    </div>
                  </ScrollArea>
                </CardContent>
              </Card>
            )}
          </div>
        </div>
      </div>
    </AppLayout>
  );
}
