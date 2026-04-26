import { useState, useEffect } from "react";
import { AppLayout } from "@/components/layout/AppLayout";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Users, Plus, X, Search, ArrowUpDown } from "lucide-react";
import { cn } from "@/lib/utils";
import api, { formatApiError } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import TeamLogo from "@/lovable/components/TeamLogo";
import TeamLogoUploader from "@/lovable/components/TeamLogoUploader";

const positionColors = {
  C: "bg-blue-600/80 text-blue-100",
  LW: "bg-emerald-600/80 text-emerald-100",
  RW: "bg-teal-600/80 text-teal-100",
  D: "bg-amber-600/80 text-amber-100",
  G: "bg-purple-600/80 text-purple-100",
};

export default function RosterPage() {
  const { user } = useAuth();
  const [roster, setRoster] = useState([]);
  const [team, setTeam] = useState(null);
  const [league, setLeague] = useState(null);
  const [loading, setLoading] = useState(true);
  const [addModalOpen, setAddModalOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [searchResults, setSearchResults] = useState([]);
  const [dropConfirm, setDropConfirm] = useState(null);

  useEffect(() => {
    const init = async () => {
      try {
        // Get user's first league and team
        const { data: leagues } = await api.get("/leagues?my_leagues=true");
        if (leagues.length > 0) {
          setLeague(leagues[0]);
          const { data: teams } = await api.get(`/teams?league_id=${leagues[0].id}`);
          const myTeam = teams.find(t => t.owner_id === user?.id);
          if (myTeam) {
            setTeam(myTeam);
            // Get roster
            const { data: rosterData } = await api.get(`/roster/${myTeam.id}`);
            setRoster(rosterData.players || []);
          }
        }
      } catch (e) { console.error(e); }
      setLoading(false);
    };
    init();
  }, [user]);

  // Search players to add
  useEffect(() => {
    if (!search.trim()) { setSearchResults([]); return; }
    const t = setTimeout(async () => {
      try {
        const { data } = await api.get(`/players?search=${search}&limit=10`);
        setSearchResults(data.players || []);
      } catch (e) { console.error(e); }
    }, 300);
    return () => clearTimeout(t);
  }, [search]);

  const handleAddPlayer = async (playerId) => {
    if (!team) return;
    try {
      await api.post(`/roster/${team.id}/add`, { player_id: playerId });
      // Refresh roster
      const { data } = await api.get(`/roster/${team.id}`);
      setRoster(data.players || []);
      setAddModalOpen(false);
      setSearch("");
    } catch (e) { alert(formatApiError(e)); }
  };

  const handleDropPlayer = async (playerId) => {
    if (!team) return;
    try {
      await api.post(`/roster/${team.id}/drop`, { player_id: playerId });
      setRoster(prev => prev.filter(p => p.player_id !== playerId));
      setDropConfirm(null);
    } catch (e) { alert(formatApiError(e)); }
  };

  // Group by position
  const forwards = roster.filter(p => ["C", "LW", "RW"].includes(p.position));
  const defensemen = roster.filter(p => p.position === "D");
  const goalies = roster.filter(p => p.position === "G");

  return (
    <AppLayout>
      <div className="space-y-6" data-testid="roster-page">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            {team ? (
              <TeamLogoUploader
                teamId={team.id}
                name={team.name}
                abbr={team.logo_abbr}
                logo={team.logo_url}
                size="lg"
                onChange={(newLogo) => setTeam(prev => prev ? { ...prev, logo_url: newLogo } : prev)}
              />
            ) : (
              <TeamLogo name="My Roster" size="lg" />
            )}
            <div>
              <h1 className="text-2xl font-bold text-white flex items-center gap-2">
                <Users className="h-6 w-6 text-[#00D2FF]" />
                {team ? team.name : "My Roster"}
              </h1>
              <p className="text-[#A1A1AA]">{league?.name || "No league"} · {roster.length} players</p>
            </div>
          </div>
          <Button className="bg-[#00D2FF] text-black hover:bg-[#33DBFF]" onClick={() => setAddModalOpen(true)} data-testid="add-player-btn">
            <Plus className="h-4 w-4 mr-2" /> Add Player
          </Button>
        </div>

        {loading ? (
          <Card className="border-white/10"><CardContent className="p-8 text-center text-[#A1A1AA]">Loading roster...</CardContent></Card>
        ) : !team ? (
          <Card className="border-white/10"><CardContent className="p-8 text-center text-[#A1A1AA]">Join a league and create a team first</CardContent></Card>
        ) : roster.length === 0 ? (
          <Card className="border-white/10">
            <CardContent className="p-12 text-center">
              <Users className="h-16 w-16 text-[#52525B] mx-auto mb-4" />
              <h3 className="text-xl text-white mb-2">Empty Roster</h3>
              <p className="text-[#A1A1AA] mb-4">Add players to build your team</p>
              <Button className="bg-[#00D2FF] text-black" onClick={() => setAddModalOpen(true)}>Add Players</Button>
            </CardContent>
          </Card>
        ) : (
          <>
            {/* Forwards */}
            {forwards.length > 0 && (
              <Card className="border-white/10">
                <CardHeader className="pb-2"><CardTitle className="text-base text-white">Forwards ({forwards.length})</CardTitle></CardHeader>
                <CardContent className="p-0">
                  <RosterTable players={forwards} onDrop={setDropConfirm} />
                </CardContent>
              </Card>
            )}
            {/* Defense */}
            {defensemen.length > 0 && (
              <Card className="border-white/10">
                <CardHeader className="pb-2"><CardTitle className="text-base text-white">Defense ({defensemen.length})</CardTitle></CardHeader>
                <CardContent className="p-0">
                  <RosterTable players={defensemen} onDrop={setDropConfirm} />
                </CardContent>
              </Card>
            )}
            {/* Goalies */}
            {goalies.length > 0 && (
              <Card className="border-white/10">
                <CardHeader className="pb-2"><CardTitle className="text-base text-white">Goalies ({goalies.length})</CardTitle></CardHeader>
                <CardContent className="p-0">
                  <RosterTable players={goalies} onDrop={setDropConfirm} isGoalie />
                </CardContent>
              </Card>
            )}
          </>
        )}

        {/* Add Player Modal */}
        <Dialog open={addModalOpen} onOpenChange={setAddModalOpen}>
          <DialogContent className="bg-[#141414] border-white/10 max-w-lg">
            <DialogHeader>
              <DialogTitle className="text-white">Add Player to Roster</DialogTitle>
              <DialogDescription className="text-[#A1A1AA]">Search for an NHL player</DialogDescription>
            </DialogHeader>
            <div className="py-4">
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-[#A1A1AA]" />
                <Input placeholder="Search players..." value={search} onChange={e => setSearch(e.target.value)} className="pl-9 bg-[#0A0A0A] border-white/10 text-white" data-testid="roster-search" />
              </div>
              {searchResults.length > 0 && (
                <div className="space-y-2 mt-4 max-h-[300px] overflow-y-auto">
                  {searchResults.map(p => (
                    <div key={p._id} className="flex items-center gap-3 p-3 rounded-lg border border-white/10 hover:border-[#00D2FF]/30 cursor-pointer" onClick={() => handleAddPlayer(p._id)}>
                      <Badge className={cn("text-xs", positionColors[p.position])}>{p.position}</Badge>
                      <div className="flex-1">
                        <p className="text-sm font-medium text-white">{p.name}</p>
                        <p className="text-xs text-[#A1A1AA]">{p.team} · {p.points} pts</p>
                      </div>
                      <Plus className="h-4 w-4 text-[#00D2FF]" />
                    </div>
                  ))}
                </div>
              )}
            </div>
          </DialogContent>
        </Dialog>

        {/* Drop Confirm */}
        <Dialog open={!!dropConfirm} onOpenChange={() => setDropConfirm(null)}>
          <DialogContent className="bg-[#141414] border-white/10">
            <DialogHeader>
              <DialogTitle className="text-white">Drop Player</DialogTitle>
              <DialogDescription className="text-[#A1A1AA]">Are you sure you want to drop {dropConfirm?.name}?</DialogDescription>
            </DialogHeader>
            <DialogFooter>
              <Button variant="ghost" onClick={() => setDropConfirm(null)} className="text-white">Cancel</Button>
              <Button className="bg-[#FF3B30] text-white" onClick={() => handleDropPlayer(dropConfirm?.player_id)} data-testid="confirm-drop">Drop Player</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
    </AppLayout>
  );
}

function RosterTable({ players, onDrop, isGoalie = false }) {
  return (
    <Table>
      <TableHeader>
        <TableRow className="border-white/10">
          <TableHead className="text-[#A1A1AA]">Player</TableHead>
          <TableHead className="text-center text-[#A1A1AA]">POS</TableHead>
          <TableHead className="text-right text-[#A1A1AA]">GP</TableHead>
          <TableHead className="text-right text-[#A1A1AA]">{isGoalie ? "W" : "G"}</TableHead>
          <TableHead className="text-right text-[#A1A1AA]">{isGoalie ? "SV%" : "A"}</TableHead>
          <TableHead className="text-right text-[#A1A1AA]">{isGoalie ? "GAA" : "PTS"}</TableHead>
          <TableHead className="text-right text-[#A1A1AA]">FPTS</TableHead>
          <TableHead className="text-right text-[#A1A1AA]">Action</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {players.map(p => (
          <TableRow key={p.player_id} className="border-white/10 hover:bg-[#1A1A1A]/40">
            <TableCell>
              <div className="flex items-center gap-3">
                <div className="h-10 w-10 rounded-lg bg-[#1A1A1A] flex items-center justify-center text-xs font-bold text-[#00D2FF]">{p.nhl_team || "?"}</div>
                <div>
                  <p className="font-medium text-white">{p.name}</p>
                  <p className="text-xs text-[#A1A1AA]">{p.team_name || ""}</p>
                </div>
              </div>
            </TableCell>
            <TableCell className="text-center"><Badge className={cn("text-xs", positionColors[p.position])}>{p.position}</Badge></TableCell>
            <TableCell className="text-right text-white">{p.games_played || 0}</TableCell>
            <TableCell className="text-right text-white">{isGoalie ? (p.wins || 0) : (p.goals || 0)}</TableCell>
            <TableCell className="text-right text-white">{isGoalie ? (p.save_pct || 0).toFixed(1) : (p.assists || 0)}</TableCell>
            <TableCell className="text-right text-white">{isGoalie ? (p.goals_against_avg || 0).toFixed(2) : (p.points || 0)}</TableCell>
            <TableCell className="text-right font-semibold text-[#00D2FF]">{p.fantasy_points?.toFixed(1) || "—"}</TableCell>
            <TableCell className="text-right">
              <Button variant="ghost" size="sm" className="text-[#FF3B30] hover:bg-[#FF3B30]/10" onClick={() => onDrop(p)} data-testid={`drop-${p.player_id}`}>
                <X className="h-4 w-4" />
              </Button>
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
