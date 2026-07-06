import { useState, useEffect } from "react";
import { AppLayout } from "@/components/layout/AppLayout";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { DollarSign, Plus, Users, Clock, FileText, AlertTriangle, TrendingUp, Shield, Search } from "lucide-react";
import { cn } from "@/lib/utils";
import api, { formatApiError } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
// Iter 232N.37 — Player-card modal opens on player-name click so users
// can drill into a contract row without leaving the Salary Cap page.
import PlayerCardModal from "@/lovable/components/dashboard/PlayerCardModal";

export default function SalaryCapPage() {
  const { user } = useAuth();
  const [leagueId, setLeagueId] = useState(null);
  const [leagues, setLeagues] = useState([]);
  const [overview, setOverview] = useState(null);
  const [contracts, setContracts] = useState([]);
  const [expiring, setExpiring] = useState([]);
  const [selectedTeam, setSelectedTeam] = useState("all");
  const [loading, setLoading] = useState(true);
  const [addModalOpen, setAddModalOpen] = useState(false);
  const [playerSearch, setPlayerSearch] = useState("");
  const [searchResults, setSearchResults] = useState([]);
  const [selectedPlayer, setSelectedPlayer] = useState(null);
  const [contractForm, setContractForm] = useState({ aav: 0, total_value: 0, signing_bonus: 0, years: 3, start_year: 2025, player_status: "signed", no_trade_clause: false, no_move_clause: false });
  // Iter 232N.37 — Player-card drilldown modal state.
  const [cardOpen, setCardOpen] = useState(false);
  const [cardPlayer, setCardPlayer] = useState(null);

  // Map a contract row to the shape PlayerCardModal expects. The modal
  // itself fetches live news + recent games via `player.id`, so the
  // shim just needs to satisfy the required fields; missing analytics
  // gracefully fall back to zero-state.
  const openPlayerCard = (contract) => {
    if (!contract?.player_id) return;
    setCardPlayer({
      id: contract.player_id,
      name: contract.player_name,
      position: contract.player_position,
      team: contract.player_nhl_team,
      points: 0,
      dynastyValue: 0,
      trend: "stable",
      age: 27,
      contract: {
        salary: contract.aav || 0,
        yearsRemaining: contract.years || 1,
        type: "Signed",
      },
      rosterSection: "bench",
      statsByPeriod: { season: 0, "1d": 0, "7d": 0, "14d": 0, "30d": 0, "60d": 0, "100d": 0 },
      categoryBreakdown: { G: 0, A: 0, PPP: 0, SHP: 0, SOG: 0, HIT: 0, BLK: 0, PIM: 0, "+/-": 0, FOW: 0, FOL: 0 },
      matchupGames: 0,
      schedule: [],
    });
    setCardOpen(true);
  };

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

  useEffect(() => {
    if (!leagueId) return;
    const fetch = async () => {
      setLoading(true);
      try {
        const [overviewRes, contractsRes, expiringRes] = await Promise.all([
          api.get(`/salary-cap/${leagueId}`),
          api.get(`/contracts?league_id=${leagueId}${selectedTeam !== "all" ? `&team_id=${selectedTeam}` : ""}`),
          api.get(`/salary-cap/${leagueId}/expiring`),
        ]);
        setOverview(overviewRes.data);
        setContracts(contractsRes.data);
        setExpiring(expiringRes.data);
      } catch (e) { console.error(e); }
      setLoading(false);
    };
    fetch();
  }, [leagueId, selectedTeam]);

  useEffect(() => {
    if (!playerSearch.trim()) { setSearchResults([]); return; }
    const t = setTimeout(async () => {
      try {
        const { data } = await api.get(`/players?search=${playerSearch}&limit=8`);
        setSearchResults(data.players || []);
      } catch (e) { console.error(e); }
    }, 300);
    return () => clearTimeout(t);
  }, [playerSearch]);

  const handleCreateContract = async () => {
    if (!selectedPlayer || !leagueId) return;
    const myTeam = overview?.teams?.find(t => t.owner_name === user?.name);
    if (!myTeam) { alert("You need a team in this league"); return; }
    try {
      await api.post("/contracts", {
        league_id: leagueId, team_id: myTeam.team_id, player_id: selectedPlayer._id,
        ...contractForm, total_value: contractForm.aav * contractForm.years
      });
      setAddModalOpen(false);
      setSelectedPlayer(null);
      setPlayerSearch("");
      // Refresh
      const [o, c] = await Promise.all([api.get(`/salary-cap/${leagueId}`), api.get(`/contracts?league_id=${leagueId}`)]);
      setOverview(o.data); setContracts(c.data);
    } catch (e) { alert(formatApiError(e)); }
  };

  const cap = overview?.salary_cap || 0;
  const teamsList = overview?.teams || [];

  return (
    <AppLayout>
      <div className="space-y-6" data-testid="salary-cap-page">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-white flex items-center gap-2"><DollarSign className="h-6 w-6 text-[#00D2FF]" />Salary Cap Manager</h1>
            <p className="text-[#A1A1AA]">Dynasty contracts, cap space, and free agency tracking</p>
          </div>
          <Button className="bg-[#00D2FF] text-black hover:bg-[#33DBFF]" onClick={() => setAddModalOpen(true)} data-testid="add-contract-btn"><Plus className="h-4 w-4 mr-2" />Add Contract</Button>
        </div>

        {/* Cap Overview */}
        {!loading && teamsList.length > 0 && (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            {teamsList.map(team => (
              <Card key={team.team_id} className={cn("border-white/10 cursor-pointer hover:border-[#00D2FF]/30 transition-colors", selectedTeam === team.team_id && "border-[#00D2FF]/50")} onClick={() => setSelectedTeam(selectedTeam === team.team_id ? "all" : team.team_id)}>
                <CardContent className="p-5">
                  <div className="flex justify-between items-start mb-3">
                    <div>
                      <p className="font-medium text-white">{team.team_name}</p>
                      <p className="text-xs text-[#A1A1AA]">{team.active_contracts} contracts</p>
                    </div>
                    <Badge className={cn("text-xs", team.cap_pct > 90 ? "bg-[#FF3B30]/20 text-[#FF3B30]" : team.cap_pct > 70 ? "bg-[#FF9F0A]/20 text-[#FF9F0A]" : "bg-[#34C759]/20 text-[#34C759]")}>{team.cap_pct}%</Badge>
                  </div>
                  <Progress value={team.cap_pct} className="h-2 mb-2" />
                  <div className="flex justify-between text-xs">
                    <span className="text-[#A1A1AA]">Used: ${(team.cap_used || 0).toLocaleString()}</span>
                    <span className="text-[#34C759]">${(team.cap_remaining || 0).toLocaleString()} free</span>
                  </div>
                  {(team.rfa_count > 0 || team.ufa_count > 0) && (
                    <div className="flex gap-2 mt-2">
                      {team.rfa_count > 0 && <Badge variant="outline" className="text-[9px] text-amber-400 border-amber-400/30">{team.rfa_count} RFA</Badge>}
                      {team.ufa_count > 0 && <Badge variant="outline" className="text-[9px] text-[#FF3B30] border-[#FF3B30]/30">{team.ufa_count} UFA</Badge>}
                    </div>
                  )}
                </CardContent>
              </Card>
            ))}
          </div>
        )}

        <Tabs defaultValue="contracts">
          <TabsList>
            <TabsTrigger value="contracts">Active Contracts ({contracts.filter(c => c.status === "active").length})</TabsTrigger>
            <TabsTrigger value="expiring">Expiring ({expiring.length})</TabsTrigger>
          </TabsList>

          <TabsContent value="contracts" className="mt-4">
            <Card className="border-white/10">
              <CardContent className="p-0">
                <Table>
                  <TableHeader>
                    <TableRow className="border-white/10">
                      <TableHead className="text-[#A1A1AA]">Player</TableHead>
                      <TableHead className="text-[#A1A1AA]">Team</TableHead>
                      <TableHead className="text-right text-[#A1A1AA]">AAV</TableHead>
                      <TableHead className="text-center text-[#A1A1AA]">Years</TableHead>
                      <TableHead className="text-center text-[#A1A1AA]">Expires</TableHead>
                      <TableHead className="text-center text-[#A1A1AA]">Status</TableHead>
                      <TableHead className="text-center text-[#A1A1AA]">Clauses</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {loading ? (
                      <TableRow><TableCell colSpan={7} className="text-center text-[#A1A1AA] py-8">Loading...</TableCell></TableRow>
                    ) : contracts.length === 0 ? (
                      <TableRow><TableCell colSpan={7} className="text-center text-[#A1A1AA] py-8">No contracts</TableCell></TableRow>
                    ) : contracts.filter(c => c.status === "active").map(c => (
                      <TableRow key={c._id} className="border-white/10">
                        <TableCell>
                          <div className="flex items-center gap-2">
                            <Badge variant="outline" className="text-white border-white/20 text-[9px]">{c.player_position}</Badge>
                            <div>
                              <button
                                onClick={() => openPlayerCard(c)}
                                className="text-white font-medium text-sm hover:text-[#00D2FF] hover:underline transition-colors cursor-pointer text-left"
                                data-testid={`salary-cap-player-link-${c._id}`}
                              >
                                {c.player_name}
                              </button>
                              <p className="text-[10px] text-[#A1A1AA]">{c.player_nhl_team}</p>
                            </div>
                          </div>
                        </TableCell>
                        <TableCell className="text-[#A1A1AA] text-sm">{c.team_name}</TableCell>
                        <TableCell className="text-right font-semibold text-[#00D2FF]">${c.aav?.toLocaleString()}</TableCell>
                        <TableCell className="text-center text-white">{c.years}yr</TableCell>
                        <TableCell className="text-center text-[#A1A1AA]">{c.free_agency_year}</TableCell>
                        <TableCell className="text-center">
                          <Badge className={cn("text-[9px]", c.player_status === "ufa" ? "bg-[#FF3B30]/20 text-[#FF3B30]" : c.player_status === "rfa" ? "bg-[#FF9F0A]/20 text-[#FF9F0A]" : "bg-[#34C759]/20 text-[#34C759]")}>
                            {c.player_status?.toUpperCase()}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-center">
                          <div className="flex gap-1 justify-center">
                            {c.no_trade_clause && <Badge variant="outline" className="text-[8px] text-[#FF9F0A]">NTC</Badge>}
                            {c.no_move_clause && <Badge variant="outline" className="text-[8px] text-[#FF3B30]">NMC</Badge>}
                            {!c.no_trade_clause && !c.no_move_clause && <span className="text-[#52525B] text-xs">—</span>}
                          </div>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="expiring" className="mt-4">
            <Card className="border-white/10">
              <CardHeader><CardTitle className="text-white flex items-center gap-2"><Clock className="h-5 w-5 text-[#FF9F0A]" />Expiring Contracts (2026)</CardTitle></CardHeader>
              <CardContent>
                {expiring.length === 0 ? (
                  <p className="text-[#A1A1AA] text-center py-8">No contracts expiring</p>
                ) : expiring.map(c => (
                  <div key={c._id} className="flex items-center justify-between p-3 rounded-lg bg-[#1A1A1A]/30 mb-2">
                    <div className="flex items-center gap-3">
                      <Badge className={cn("text-[9px]", c.player_status === "ufa" ? "bg-[#FF3B30]/20 text-[#FF3B30]" : "bg-[#FF9F0A]/20 text-[#FF9F0A]")}>{c.player_status?.toUpperCase()}</Badge>
                      <div>
                        <button
                          onClick={() => openPlayerCard(c)}
                          className="text-white font-medium hover:text-[#00D2FF] hover:underline transition-colors cursor-pointer text-left"
                          data-testid={`salary-cap-expiring-link-${c._id}`}
                        >
                          {c.player_name}
                        </button>
                        <p className="text-xs text-[#A1A1AA]">{c.team_name} · {c.player_position}</p>
                      </div>
                    </div>
                    <p className="text-[#00D2FF] font-semibold">${c.aav?.toLocaleString()} AAV</p>
                  </div>
                ))}
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>

        {/* Add Contract Modal */}
        <Dialog open={addModalOpen} onOpenChange={setAddModalOpen}>
          <DialogContent className="bg-[#141414] border-white/10 max-w-lg">
            <DialogHeader>
              <DialogTitle className="text-white">Sign Contract</DialogTitle>
              <DialogDescription className="text-[#A1A1AA]">Add a dynasty contract for a player</DialogDescription>
            </DialogHeader>
            <div className="space-y-4 py-2">
              {!selectedPlayer ? (
                <>
                  <div className="relative">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-[#A1A1AA]" />
                    <Input placeholder="Search players..." value={playerSearch} onChange={e => setPlayerSearch(e.target.value)} className="pl-9 bg-[#0A0A0A] border-white/10 text-white" data-testid="contract-player-search" />
                  </div>
                  <div className="space-y-1 max-h-48 overflow-y-auto">
                    {searchResults.map(p => (
                      <div key={p._id} className="flex items-center gap-3 p-2 rounded border border-white/10 hover:border-[#00D2FF]/30 cursor-pointer" onClick={() => setSelectedPlayer(p)}>
                        <Badge variant="outline" className="text-white text-xs">{p.position}</Badge>
                        <div className="flex-1"><p className="text-sm text-white">{p.name}</p><p className="text-xs text-[#A1A1AA]">{p.team}</p></div>
                      </div>
                    ))}
                  </div>
                </>
              ) : (
                <>
                  <div className="flex items-center gap-3 p-3 bg-[#1A1A1A] rounded-lg">
                    <Badge variant="outline" className="text-white">{selectedPlayer.position}</Badge>
                    <div className="flex-1"><p className="text-white font-medium">{selectedPlayer.name}</p><p className="text-xs text-[#A1A1AA]">{selectedPlayer.team}</p></div>
                    <Button variant="ghost" size="sm" className="text-[#A1A1AA]" onClick={() => setSelectedPlayer(null)}>Change</Button>
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div><Label className="text-[#A1A1AA] text-xs">AAV ($)</Label><Input type="number" min={0} value={contractForm.aav} onChange={e => setContractForm(f => ({...f, aav: parseFloat(e.target.value) || 0}))} className="mt-1 bg-[#0A0A0A] border-white/10 text-white" data-testid="contract-aav" /></div>
                    <div><Label className="text-[#A1A1AA] text-xs">Years</Label><Input type="number" min={1} max={8} value={contractForm.years} onChange={e => setContractForm(f => ({...f, years: parseInt(e.target.value) || 1}))} className="mt-1 bg-[#0A0A0A] border-white/10 text-white" data-testid="contract-years" /></div>
                    <div><Label className="text-[#A1A1AA] text-xs">Signing Bonus ($)</Label><Input type="number" min={0} value={contractForm.signing_bonus} onChange={e => setContractForm(f => ({...f, signing_bonus: parseFloat(e.target.value) || 0}))} className="mt-1 bg-[#0A0A0A] border-white/10 text-white" /></div>
                    <div><Label className="text-[#A1A1AA] text-xs">Status</Label>
                      <Select value={contractForm.player_status} onValueChange={v => setContractForm(f => ({...f, player_status: v}))}>
                        <SelectTrigger className="mt-1 bg-[#0A0A0A] border-white/10 text-white"><SelectValue /></SelectTrigger>
                        <SelectContent className="bg-[#141414] border-white/10">{["signed","rfa","ufa","entry_level"].map(s => <SelectItem key={s} value={s} className="text-white">{s.toUpperCase().replace("_"," ")}</SelectItem>)}</SelectContent>
                      </Select>
                    </div>
                  </div>
                  <div className="flex items-center justify-between p-3 bg-[#0A0A0A] rounded">
                    <span className="text-white text-sm">No-Trade Clause</span>
                    <Switch checked={contractForm.no_trade_clause} onCheckedChange={v => setContractForm(f => ({...f, no_trade_clause: v}))} />
                  </div>
                  <div className="flex items-center justify-between p-3 bg-[#0A0A0A] rounded">
                    <span className="text-white text-sm">No-Move Clause</span>
                    <Switch checked={contractForm.no_move_clause} onCheckedChange={v => setContractForm(f => ({...f, no_move_clause: v}))} />
                  </div>
                  <div className="bg-[#00D2FF]/10 p-3 rounded text-sm text-[#A1A1AA]">Total Value: ${(contractForm.aav * contractForm.years).toLocaleString()} over {contractForm.years} years · FA: {contractForm.start_year + contractForm.years}</div>
                </>
              )}
            </div>
            <DialogFooter>
              <Button variant="ghost" onClick={() => { setAddModalOpen(false); setSelectedPlayer(null); }} className="text-white">Cancel</Button>
              {selectedPlayer && <Button className="bg-[#00D2FF] text-black" onClick={handleCreateContract} data-testid="confirm-contract">Sign Contract</Button>}
            </DialogFooter>
          </DialogContent>
        </Dialog>

        {/* Iter 232N.37 — Player-card drilldown */}
        {cardPlayer && (
          <PlayerCardModal open={cardOpen} onOpenChange={setCardOpen} player={cardPlayer} />
        )}
      </div>
    </AppLayout>
  );
}
