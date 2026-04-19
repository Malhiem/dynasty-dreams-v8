import { useState, useEffect, useMemo } from "react";
import { AppLayout } from "@/components/layout/AppLayout";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Plus, ArrowRightLeft, MessageSquare, TrendingUp, TrendingDown, Filter, X, Send } from "lucide-react";
import { cn } from "@/lib/utils";
import api, { formatApiError } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";

export default function TradeBlockPage() {
  const { user } = useAuth();
  const [items, setItems] = useState([]);
  const [myPlayers, setMyPlayers] = useState([]);
  const [positionFilter, setPositionFilter] = useState("All");
  const [ownerFilter, setOwnerFilter] = useState("All");
  const [loading, setLoading] = useState(true);
  const [addModalOpen, setAddModalOpen] = useState(false);
  const [playerSearch, setPlayerSearch] = useState("");
  const [searchResults, setSearchResults] = useState([]);
  const [lookingFor, setLookingFor] = useState("");
  const [tradeModalOpen, setTradeModalOpen] = useState(false);
  const [selectedItem, setSelectedItem] = useState(null);

  useEffect(() => {
    const fetch = async () => {
      try {
        const { data } = await api.get("/trade-block");
        setItems(data);
      } catch (e) { console.error(e); }
      setLoading(false);
    };
    fetch();
  }, []);

  // Search players for adding to block
  useEffect(() => {
    if (!playerSearch.trim()) { setSearchResults([]); return; }
    const t = setTimeout(async () => {
      try {
        const { data } = await api.get(`/players?search=${playerSearch}&limit=10`);
        setSearchResults(data.players || []);
      } catch (e) { console.error(e); }
    }, 300);
    return () => clearTimeout(t);
  }, [playerSearch]);

  const handleAddToBlock = async (player) => {
    try {
      const tags = lookingFor.split(",").map(s => s.trim()).filter(Boolean);
      await api.post("/trade-block", {
        player_id: player._id,
        item_type: "player",
        looking_for: tags.length > 0 ? tags : ["Open to offers"]
      });
      setAddModalOpen(false);
      setPlayerSearch("");
      setLookingFor("");
      const { data } = await api.get("/trade-block");
      setItems(data);
    } catch (e) { alert(formatApiError(e)); }
  };

  const handleRemoveFromBlock = async (itemId) => {
    try {
      await api.delete(`/trade-block/${itemId}`);
      setItems(prev => prev.filter(i => i._id !== itemId));
    } catch (e) { console.error(e); }
  };

  const positions = ["All", "C", "LW", "RW", "D", "G"];
  const owners = ["All", ...new Set(items.map(i => i.owner_name))];

  const filtered = useMemo(() => {
    let result = [...items];
    if (positionFilter !== "All") result = result.filter(i => i.position === positionFilter);
    if (ownerFilter !== "All") result = result.filter(i => i.owner_name === ownerFilter);
    result.sort((a, b) => (b.points || 0) - (a.points || 0));
    return result;
  }, [items, positionFilter, ownerFilter]);

  return (
    <AppLayout>
      <div className="space-y-6" data-testid="trade-block-page">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-white">Trade Block</h1>
            <p className="text-[#A1A1AA]">Players available for trade across the league</p>
          </div>
          <Button className="bg-[#00D2FF] text-black hover:bg-[#33DBFF]" onClick={() => setAddModalOpen(true)} data-testid="add-to-block-btn">
            <Plus className="h-4 w-4 mr-2" /> Add to Trade Block
          </Button>
        </div>

        {/* Filters */}
        <div className="flex items-center gap-4">
          <Filter className="h-4 w-4 text-[#A1A1AA]" />
          <Select value={positionFilter} onValueChange={setPositionFilter}>
            <SelectTrigger className="w-36 bg-[#141414] border-white/10 text-white"><SelectValue /></SelectTrigger>
            <SelectContent className="bg-[#141414] border-white/10">
              {positions.map(p => <SelectItem key={p} value={p} className="text-white">{p === "All" ? "All Positions" : p}</SelectItem>)}
            </SelectContent>
          </Select>
          <Select value={ownerFilter} onValueChange={setOwnerFilter}>
            <SelectTrigger className="w-44 bg-[#141414] border-white/10 text-white"><SelectValue /></SelectTrigger>
            <SelectContent className="bg-[#141414] border-white/10">
              {owners.map(o => <SelectItem key={o} value={o} className="text-white">{o === "All" ? "All Teams" : o}</SelectItem>)}
            </SelectContent>
          </Select>
          <Badge variant="outline" className="ml-auto text-[#A1A1AA]">{filtered.length} items</Badge>
        </div>

        {/* Items */}
        <div className="grid gap-4">
          {loading ? (
            <Card className="border-white/10"><CardContent className="p-8 text-center text-[#A1A1AA]">Loading...</CardContent></Card>
          ) : filtered.length === 0 ? (
            <Card className="border-white/10"><CardContent className="p-8 text-center text-[#A1A1AA]">No items on the trade block yet</CardContent></Card>
          ) : filtered.map(item => (
            <Card key={item._id} className="border-white/10 hover:border-[#00D2FF]/30 transition-colors">
              <CardContent className="p-6">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex items-start gap-4">
                    <div className="h-14 w-14 rounded-lg bg-[#1A1A1A] flex items-center justify-center text-sm font-bold text-[#00D2FF]">
                      {item.nhl_team || item.position?.[0] || "?"}
                    </div>
                    <div>
                      <h3 className="font-semibold text-lg text-white">{item.name}</h3>
                      <div className="flex items-center gap-3 text-sm text-[#A1A1AA] mb-3">
                        <span>{item.position}</span>
                        {item.nhl_team && <><span>·</span><span>{item.nhl_team}</span></>}
                        {item.points > 0 && <><span>·</span><span className="text-[#00D2FF]">{item.points} pts</span></>}
                      </div>
                      {item.games_played > 0 && (
                        <div className="text-xs text-[#A1A1AA] mb-3 flex gap-3">
                          <span>GP {item.games_played}</span>
                          <span>{item.goals}G</span>
                          <span>{item.assists}A</span>
                          <span>{(item.plus_minus || 0) >= 0 ? "+" : ""}{item.plus_minus}</span>
                        </div>
                      )}
                      <div className="flex flex-wrap gap-2">
                        <span className="text-xs text-[#A1A1AA]">Looking for:</span>
                        {(item.looking_for || []).map((req, idx) => (
                          <Badge key={idx} variant="outline" className="bg-[#1A1A1A] text-[#A1A1AA] border-white/10">{req}</Badge>
                        ))}
                      </div>
                    </div>
                  </div>
                  <div className="flex flex-col items-end gap-3">
                    <span className="text-sm text-[#A1A1AA]">{item.owner_name}</span>
                    <div className="flex gap-2">
                      {item.owner_id === user?.id && (
                        <Button variant="outline" size="sm" className="text-[#FF3B30] border-[#FF3B30]/30" onClick={() => handleRemoveFromBlock(item._id)} data-testid={`remove-${item._id}`}>
                          <X className="h-4 w-4 mr-1" /> Remove
                        </Button>
                      )}
                      {item.owner_id !== user?.id && (
                        <Button size="sm" className="bg-[#00D2FF] text-black hover:bg-[#33DBFF]">
                          <ArrowRightLeft className="h-4 w-4 mr-1" /> Trade
                        </Button>
                      )}
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>

        {/* Add to Block Modal */}
        <Dialog open={addModalOpen} onOpenChange={setAddModalOpen}>
          <DialogContent className="bg-[#141414] border-white/10">
            <DialogHeader>
              <DialogTitle className="text-white">Add to Trade Block</DialogTitle>
              <DialogDescription className="text-[#A1A1AA]">Search for a player to add to the trade block</DialogDescription>
            </DialogHeader>
            <div className="space-y-4 py-4">
              <Input placeholder="Search players..." value={playerSearch} onChange={e => setPlayerSearch(e.target.value)} className="bg-[#0A0A0A] border-white/10 text-white" data-testid="block-search" />
              {searchResults.length > 0 && (
                <div className="space-y-2 max-h-[200px] overflow-y-auto">
                  {searchResults.map(p => (
                    <div key={p._id} className="flex items-center gap-3 p-3 rounded-lg border border-white/10 hover:border-[#00D2FF]/30 cursor-pointer" onClick={() => handleAddToBlock(p)}>
                      <Badge variant="outline" className="text-white">{p.position}</Badge>
                      <div className="flex-1">
                        <p className="text-sm font-medium text-white">{p.name}</p>
                        <p className="text-xs text-[#A1A1AA]">{p.team} · {p.points} pts</p>
                      </div>
                      <Plus className="h-4 w-4 text-[#00D2FF]" />
                    </div>
                  ))}
                </div>
              )}
              <Input placeholder="Looking for: Elite Center, Draft Picks (comma-separated)" value={lookingFor} onChange={e => setLookingFor(e.target.value)} className="bg-[#0A0A0A] border-white/10 text-white" />
            </div>
          </DialogContent>
        </Dialog>
      </div>
    </AppLayout>
  );
}
