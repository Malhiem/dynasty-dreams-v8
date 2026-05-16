import { useState, useEffect } from "react";
import { Link, useNavigate } from "react-router-dom";
import { AppLayout } from "@/components/layout/AppLayout";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Progress } from "@/components/ui/progress";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Clock, DollarSign, Plus, History, TrendingUp, Search, X, AlertTriangle, ArrowRight } from "lucide-react";
import { cn } from "@/lib/utils";
import { toast } from "sonner";
import api, { formatApiError } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";

export default function WaiversPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [available, setAvailable] = useState([]);
  const [myClaims, setMyClaims] = useState([]);
  const [history, setHistory] = useState([]);
  const [budget, setBudget] = useState({ total_budget: 100, spent: 0, remaining: 100 });
  const [waiverOrder, setWaiverOrder] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [posFilter, setPosFilter] = useState("all");
  const [claimModalOpen, setClaimModalOpen] = useState(false);
  const [selectedPlayer, setSelectedPlayer] = useState(null);
  const [bidAmount, setBidAmount] = useState(1);
  const [leagueId, setLeagueId] = useState(null);
  // Precheck result for the active claim attempt — populated when the modal
  // opens and re-runs whenever the bid changes (cap math depends on player,
  // not bid, but FAAB blocker re-evaluates).
  const [precheck, setPrecheck] = useState(null);
  const [prechecking, setPrechecking] = useState(false);

  // Get user's first league
  useEffect(() => {
    const init = async () => {
      try {
        const { data } = await api.get("/leagues?my_leagues=true");
        if (data.length > 0) setLeagueId(data[0].id);
      } catch (e) { console.error(e); }
    };
    init();
  }, []);

  // Fetch data
  useEffect(() => {
    if (!leagueId) return;
    const fetch = async () => {
      setLoading(true);
      try {
        const params = new URLSearchParams();
        if (search) params.append("search", search);
        if (posFilter !== "all") params.append("position", posFilter);
        params.append("limit", "30");

        const [avail, claims, hist, bud, order] = await Promise.all([
          api.get(`/waivers/available?${params}`),
          api.get(`/waivers/claims?my_claims=true&league_id=${leagueId}`),
          api.get(`/waivers/history?league_id=${leagueId}`),
          api.get(`/waivers/budget?league_id=${leagueId}`),
          api.get(`/waivers/order?league_id=${leagueId}`),
        ]);
        setAvailable(avail.data.players || []);
        setMyClaims(claims.data || []);
        setHistory(hist.data || []);
        setBudget(bud.data);
        setWaiverOrder(order.data || []);
      } catch (e) { console.error(e); }
      setLoading(false);
    };
    fetch();
  }, [leagueId, search, posFilter]);

  const handleClaim = async () => {
    if (!selectedPlayer || !leagueId) return;
    try {
      await api.post("/waivers/claim", {
        league_id: leagueId,
        player_id: selectedPlayer.id,
        bid_amount: bidAmount
      });
      setClaimModalOpen(false);
      setBidAmount(1);
      // Refresh
      const [claims, bud] = await Promise.all([
        api.get(`/waivers/claims?my_claims=true&league_id=${leagueId}`),
        api.get(`/waivers/budget?league_id=${leagueId}`),
      ]);
      setMyClaims(claims.data || []);
      setBudget(bud.data);
    } catch (e) { alert(formatApiError(e)); }
  };

  const handleCancelClaim = async (claimId) => {
    try {
      await api.delete(`/waivers/claims/${claimId}`);
      setMyClaims(prev => prev.filter(c => c._id !== claimId));
    } catch (e) { console.error(e); }
  };

  const pendingClaims = myClaims.filter(c => c.status === "pending");
  const faabPct = budget.total_budget > 0 ? (budget.remaining / budget.total_budget) * 100 : 0;

  return (
    <AppLayout>
      <div className="space-y-6" data-testid="waivers-page">
        <div>
          <h1 className="text-2xl font-bold text-white">Waiver Wire</h1>
          <p className="text-[#A1A1AA]">FAAB bidding and waiver claims</p>
        </div>

        {/* FAAB Overview */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <Card className="border-white/10">
            <CardContent className="p-6">
              <div className="flex items-center gap-3 mb-3">
                <div className="h-10 w-10 rounded-lg bg-[#00D2FF]/20 flex items-center justify-center">
                  <DollarSign className="h-5 w-5 text-[#00D2FF]" />
                </div>
                <div>
                  <p className="text-sm text-[#A1A1AA]">FAAB Remaining</p>
                  <p className="text-xl font-bold text-[#00D2FF]" data-testid="faab-remaining">${budget.remaining}</p>
                </div>
              </div>
              <Progress value={faabPct} className="h-2" />
              <p className="text-xs text-[#A1A1AA] mt-2">${budget.spent} spent of ${budget.total_budget} budget</p>
            </CardContent>
          </Card>

          <Card className="border-white/10">
            <CardContent className="p-6">
              <div className="flex items-center gap-3 mb-3">
                <div className="h-10 w-10 rounded-lg bg-[#FF3B30]/20 flex items-center justify-center">
                  <Clock className="h-5 w-5 text-[#FF3B30]" />
                </div>
                <div>
                  <p className="text-sm text-[#A1A1AA]">Waiver Priority</p>
                  <p className="text-xl font-bold text-white">#{waiverOrder.findIndex(o => o.owner_name === user?.name) + 1 || "—"}</p>
                </div>
              </div>
              <p className="text-xs text-[#A1A1AA]">Resets after successful claim</p>
            </CardContent>
          </Card>

          <Card className="border-white/10">
            <CardContent className="p-6">
              <div className="flex items-center gap-3 mb-3">
                <div className="h-10 w-10 rounded-lg bg-[#34C759]/20 flex items-center justify-center">
                  <History className="h-5 w-5 text-[#34C759]" />
                </div>
                <div>
                  <p className="text-sm text-[#A1A1AA]">Pending Claims</p>
                  <p className="text-xl font-bold text-white" data-testid="pending-count">{pendingClaims.length}</p>
                </div>
              </div>
              <p className="text-xs text-[#A1A1AA]">Processing: Commissioner initiated</p>
            </CardContent>
          </Card>
        </div>

        <Tabs defaultValue="available" className="space-y-4">
          <TabsList>
            <TabsTrigger value="available">Available Players</TabsTrigger>
            <TabsTrigger value="my-claims">My Claims ({pendingClaims.length})</TabsTrigger>
            <TabsTrigger value="history">Claim History</TabsTrigger>
          </TabsList>

          <TabsContent value="available">
            {/* Search */}
            <div className="flex gap-3 mb-4">
              <div className="relative flex-1">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-[#A1A1AA]" />
                <Input placeholder="Search players..." value={search} onChange={e => setSearch(e.target.value)} className="pl-9 bg-[#141414] border-white/10 text-white" data-testid="waiver-search" />
              </div>
              <Select value={posFilter} onValueChange={setPosFilter}>
                <SelectTrigger className="w-36 bg-[#141414] border-white/10 text-white"><SelectValue /></SelectTrigger>
                <SelectContent className="bg-[#141414] border-white/10">
                  {["all","C","LW","RW","D","G"].map(p => <SelectItem key={p} value={p} className="text-white">{p === "all" ? "All Positions" : p}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <Card className="border-white/10">
              <CardContent className="p-0">
                <Table>
                  <TableHeader>
                    <TableRow className="border-white/10">
                      <TableHead className="text-[#A1A1AA]">Player</TableHead>
                      <TableHead className="text-center text-[#A1A1AA]">POS</TableHead>
                      <TableHead className="text-right text-[#A1A1AA]">PTS</TableHead>
                      <TableHead className="text-right text-[#A1A1AA]">G</TableHead>
                      <TableHead className="text-right text-[#A1A1AA]">A</TableHead>
                      <TableHead className="text-right text-[#A1A1AA]">GP</TableHead>
                      <TableHead className="text-right text-[#A1A1AA]">Action</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {loading ? (
                      <TableRow><TableCell colSpan={7} className="text-center text-[#A1A1AA] py-8">Loading...</TableCell></TableRow>
                    ) : available.length === 0 ? (
                      <TableRow><TableCell colSpan={7} className="text-center text-[#A1A1AA] py-8">No players found</TableCell></TableRow>
                    ) : available.map(player => (
                      <TableRow key={player.id} className="border-white/10">
                        <TableCell>
                          <div className="flex items-center gap-3">
                            <div className="h-10 w-10 rounded-lg bg-[#1A1A1A] flex items-center justify-center text-xs font-bold text-[#00D2FF]">{player.team}</div>
                            <div>
                              <p className="font-medium text-white">{player.name}</p>
                              <p className="text-xs text-[#A1A1AA]">{player.team_name}</p>
                            </div>
                          </div>
                        </TableCell>
                        <TableCell className="text-center"><Badge variant="outline" className="text-white border-white/20">{player.position}</Badge></TableCell>
                        <TableCell className="text-right font-semibold text-[#00D2FF]">{player.points}</TableCell>
                        <TableCell className="text-right text-white">{player.goals}</TableCell>
                        <TableCell className="text-right text-white">{player.assists}</TableCell>
                        <TableCell className="text-right text-white">{player.games_played}</TableCell>
                        <TableCell className="text-right">
                          <Button size="sm" className="bg-[#00D2FF] text-black hover:bg-[#33DBFF]" onClick={() => { setSelectedPlayer(player); setClaimModalOpen(true); }} data-testid={`claim-${player.id}`}>
                            <Plus className="h-4 w-4 mr-1" /> Claim
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="my-claims">
            <Card className="border-white/10">
              <CardHeader><CardTitle className="text-white">Pending Claims</CardTitle></CardHeader>
              <CardContent>
                {pendingClaims.length === 0 ? (
                  <p className="text-[#A1A1AA] text-center py-8">No pending claims</p>
                ) : (
                  <div className="space-y-4">
                    {pendingClaims.map(claim => (
                      <div key={claim._id} className="flex items-center justify-between p-4 rounded-lg bg-[#1A1A1A]/30">
                        <div className="flex items-center gap-3">
                          <div className="h-10 w-10 rounded-lg bg-[#1A1A1A] flex items-center justify-center text-xs font-bold text-[#00D2FF]">{claim.player_team}</div>
                          <div>
                            <p className="font-medium text-white">{claim.player_name}</p>
                            {claim.drop_player_name && <p className="text-sm text-[#A1A1AA]">Dropping: {claim.drop_player_name}</p>}
                          </div>
                        </div>
                        <div className="flex items-center gap-4">
                          <div className="text-right">
                            <p className="font-semibold text-[#00D2FF]">${claim.bid_amount}</p>
                            <p className="text-xs text-[#A1A1AA]">FAAB Bid</p>
                          </div>
                          <Badge className="bg-[#FF3B30]/20 text-[#FF3B30] border-[#FF3B30]/30"><Clock className="h-3 w-3 mr-1" />Pending</Badge>
                          <Button variant="outline" size="sm" className="text-[#FF3B30] border-[#FF3B30]/30" onClick={() => handleCancelClaim(claim._id)} data-testid={`cancel-${claim._id}`}>Cancel</Button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="history">
            <Card className="border-white/10">
              <CardHeader><CardTitle className="text-white">Recent Claim History</CardTitle></CardHeader>
              <CardContent>
                {history.length === 0 ? (
                  <p className="text-[#A1A1AA] text-center py-8">No claim history yet</p>
                ) : (
                  <div className="space-y-4">
                    {history.map(claim => (
                      <div key={claim._id} className="flex items-center justify-between p-4 rounded-lg bg-[#1A1A1A]/30">
                        <div className="flex items-center gap-3">
                          <div className="h-10 w-10 rounded-lg bg-[#1A1A1A] flex items-center justify-center text-xs font-bold text-[#00D2FF]">{claim.player_team}</div>
                          <div>
                            <p className="font-medium text-white">{claim.player_name}</p>
                            <p className="text-sm text-[#A1A1AA]">Won by {claim.team_name}</p>
                          </div>
                        </div>
                        <div className="flex items-center gap-4">
                          <div className="text-right">
                            <p className="font-semibold text-[#00D2FF]">${claim.bid_amount}</p>
                            <p className="text-xs text-[#A1A1AA]">{claim.status === "won" ? "Winning" : "Your"} Bid</p>
                          </div>
                          <Badge className={claim.status === "won" ? "bg-[#34C759]/20 text-[#34C759]" : "bg-[#FF3B30]/20 text-[#FF3B30]"}>{claim.status}</Badge>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>

        {/* Claim Modal */}
        <Dialog open={claimModalOpen} onOpenChange={setClaimModalOpen}>
          <DialogContent className="bg-[#141414] border-white/10">
            <DialogHeader>
              <DialogTitle className="text-white">Place Waiver Claim</DialogTitle>
              <DialogDescription className="text-[#A1A1AA]">Place a FAAB bid for {selectedPlayer?.name}</DialogDescription>
            </DialogHeader>
            <div className="py-4 space-y-4">
              <div className="flex items-center gap-3 p-3 bg-[#1A1A1A] rounded-lg">
                <Badge variant="outline" className="text-white">{selectedPlayer?.position}</Badge>
                <div>
                  <p className="text-white font-medium">{selectedPlayer?.name}</p>
                  <p className="text-xs text-[#A1A1AA]">{selectedPlayer?.team} · {selectedPlayer?.points} pts</p>
                </div>
              </div>
              <div>
                <label className="text-sm text-[#A1A1AA]">FAAB Bid ($)</label>
                <Input type="number" min={0} max={budget.remaining} value={bidAmount} onChange={e => setBidAmount(parseFloat(e.target.value) || 0)} className="mt-2 bg-[#0A0A0A] border-white/10 text-white" data-testid="bid-amount" />
                <p className="text-xs text-[#A1A1AA] mt-1">Remaining budget: ${budget.remaining}</p>
              </div>

              {/* Precheck panel — surfaces roster space, cap fit, and any
                  illegal placement warnings before the user commits. */}
              {prechecking && (
                <p className="text-xs text-[#A1A1AA] italic" data-testid="precheck-loading">
                  Checking your roster…
                </p>
              )}
              {precheck && (
                <div
                  className="rounded-lg border border-white/10 p-3 space-y-2 bg-[#0A0A0A]"
                  data-testid="precheck-panel"
                >
                  <div className="flex items-center justify-between text-xs text-[#A1A1AA]">
                    <span data-testid="precheck-roster">
                      Roster: <span className="text-white font-medium">{precheck.roster.current}/{precheck.roster.max}</span>
                      {precheck.roster.has_room ? (
                        <Badge variant="outline" className="ml-2 text-[10px] py-0 px-1.5 border-green-500/40 text-green-300">Room</Badge>
                      ) : (
                        <Badge variant="outline" className="ml-2 text-[10px] py-0 px-1.5 border-red-500/40 text-red-300">Full</Badge>
                      )}
                    </span>
                    {precheck.cap.enabled && (
                      <span data-testid="precheck-cap">
                        Cap: <span className="text-white font-medium">${(precheck.cap.would_be / 1_000_000).toFixed(2)}M</span> / ${(precheck.cap.cap / 1_000_000).toFixed(1)}M
                        {precheck.cap.fits ? (
                          <Badge variant="outline" className="ml-2 text-[10px] py-0 px-1.5 border-green-500/40 text-green-300">Fits</Badge>
                        ) : (
                          <Badge variant="outline" className="ml-2 text-[10px] py-0 px-1.5 border-red-500/40 text-red-300">Over</Badge>
                        )}
                      </span>
                    )}
                  </div>

                  {(precheck.issues || []).map((iss, idx) => {
                    const isError = iss.severity === "error";
                    return (
                      <div
                        key={idx}
                        data-testid={`precheck-issue-${iss.code}`}
                        className={cn(
                          "flex items-start gap-2 p-2 rounded text-xs",
                          isError ? "bg-red-500/10 text-red-300 border border-red-500/30"
                                  : "bg-yellow-500/10 text-yellow-300 border border-yellow-500/30",
                        )}
                      >
                        <AlertTriangle className="h-3.5 w-3.5 mt-0.5 shrink-0" />
                        <span>{iss.message}</span>
                      </div>
                    );
                  })}

                  {precheck.requires_drop && precheck.team?.id && (
                    <Button
                      variant="outline"
                      size="sm"
                      className="w-full border-[#00D2FF]/40 text-[#00D2FF] hover:bg-[#00D2FF]/10 hover:text-[#33DBFF] gap-1"
                      data-testid="precheck-proceed-to-drop"
                      onClick={() => {
                        setClaimModalOpen(false);
                        navigate("/team");
                      }}
                    >
                      Proceed to Drop Player <ArrowRight className="h-3.5 w-3.5" />
                    </Button>
                  )}
                </div>
              )}
            </div>
            <DialogFooter>
              <Button variant="ghost" onClick={() => setClaimModalOpen(false)} className="text-white">Cancel</Button>
              <Button
                className="bg-[#00D2FF] text-black hover:bg-[#33DBFF]"
                onClick={handleClaim}
                disabled={
                  bidAmount > budget.remaining ||
                  (precheck && !precheck.can_claim)
                }
                data-testid="confirm-claim"
              >
                Place Claim
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
    </AppLayout>
  );
}
