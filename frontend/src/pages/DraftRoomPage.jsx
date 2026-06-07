import { useState, useMemo, useEffect, useCallback } from "react";
import { AppLayout } from "@/components/layout/AppLayout";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Progress } from "@/components/ui/progress";
import { LayoutGrid, Star, Search, Clock, Play, Pause, Timer, AlertCircle, X, ListOrdered, MessageSquare, Send, Info, Users } from "lucide-react";
import { cn } from "@/lib/utils";
import api from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { useParams } from "react-router-dom";
import { useDraftSocket } from "@/hooks/use-socket";
import TeamLogo from "@/lovable/components/TeamLogo";

const teamByAbbr = (teams, abbr) => {
  if (!abbr || !teams?.length) return null;
  return teams.find(t => (t.logo_abbr || (t.name || "").slice(0,3).toUpperCase()) === abbr) || null;
};

const positionColors = {
  C: "bg-blue-600/80 text-blue-100 border-blue-500/50",
  LW: "bg-emerald-600/80 text-emerald-100 border-emerald-500/50",
  RW: "bg-teal-600/80 text-teal-100 border-teal-500/50",
  D: "bg-amber-600/80 text-amber-100 border-amber-500/50",
  G: "bg-purple-600/80 text-purple-100 border-purple-500/50",
};

function formatPickTimer(seconds) {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

export default function DraftRoomPage() {
  const { id: draftId } = useParams();
  const { user } = useAuth();

  const [draft, setDraft] = useState(null);
  const [players, setPlayers] = useState([]);
  const [teams, setTeams] = useState([]);
  const [shortlist, setShortlist] = useState(new Set());
  const [queue, setQueue] = useState([]);
  const [chatMessages, setChatMessages] = useState([]);
  const [chatInput, setChatInput] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [positionFilter, setPositionFilter] = useState("all");
  const [pickTimeLeft, setPickTimeLeft] = useState(120);
  const [timerPaused, setTimerPaused] = useState(false);
  const [loading, setLoading] = useState(true);

  // Fetch draft data
  const fetchDraft = useCallback(async () => {
    if (!draftId) return;
    try {
      const { data } = await api.get(`/drafts/${draftId}`);
      setDraft(data);
      setChatMessages(data.chat_messages || []);
      if (data.time_per_pick) setPickTimeLeft(data.time_per_pick);
      setTimerPaused(data.timer_paused || false);
      // Fetch league teams so we can render team logos by abbr
      if (data.league_id) {
        try {
          const { data: t } = await api.get(`/teams?league_id=${data.league_id}`);
          setTeams(t || []);
        } catch (e) { /* ignore */ }
      }
    } catch (e) {
      console.error("Failed to fetch draft", e);
    }
  }, [draftId]);

  // Fetch eligible players
  const fetchPlayers = useCallback(async () => {
    if (!draftId) return;
    try {
      const params = new URLSearchParams();
      if (searchQuery) params.append("search", searchQuery);
      if (positionFilter !== "all") params.append("position", positionFilter);
      params.append("limit", "50");
      const { data } = await api.get(`/drafts/${draftId}/eligible-players?${params}`);
      setPlayers(data.players || []);
    } catch (e) {
      console.error("Failed to fetch players", e);
    }
  }, [draftId, searchQuery, positionFilter]);

  useEffect(() => {
    const init = async () => {
      setLoading(true);
      await fetchDraft();
      await fetchPlayers();
      setLoading(false);
    };
    init();
  }, [fetchDraft, fetchPlayers]);

  // Refresh eligible players on search/filter change
  useEffect(() => {
    const t = setTimeout(fetchPlayers, 300);
    return () => clearTimeout(t);
  }, [searchQuery, positionFilter, fetchPlayers]);

  // Pick timer
  useEffect(() => {
    if (!draft?.draft_started || draft?.early_start || timerPaused) return;
    const interval = setInterval(() => {
      setPickTimeLeft(prev => {
        if (prev <= 1) return draft.time_per_pick || 120;
        return prev - 1;
      });
    }, 1000);
    return () => clearInterval(interval);
  }, [draft, timerPaused]);

  // Poll for updates every 5 seconds
  useEffect(() => {
    if (!draftId) return;
    const interval = setInterval(async () => {
      await fetchDraft();
      await fetchPlayers();
    }, 30000); // Fallback polling every 30s (WebSocket handles real-time)
    return () => clearInterval(interval);
  }, [draftId, fetchDraft, fetchPlayers]);

  // WebSocket: real-time draft events + presence
  const { connected: wsConnected, onlineUserIds } = useDraftSocket(draftId, {
    userId: user?.id,
    onDraftStarted: () => { fetchDraft(); },
    onDraftPick: (pick) => {
      fetchDraft();
      fetchPlayers();
      setPickTimeLeft(draft?.time_per_pick || 120);
    },
    onChatMessage: (msg) => {
      setChatMessages(prev => [...prev, msg]);
    },
    onTimerToggle: (data) => {
      setTimerPaused(data.paused);
    },
    onConfigUpdated: () => { fetchDraft(); },
    onDraftCompleted: () => { fetchDraft(); },
  });

  // Actions
  const handleStartDraft = async (earlyStart) => {
    try {
      await api.post(`/drafts/${draftId}/start?early_start=${earlyStart}`);
      await fetchDraft();
    } catch (e) { console.error(e); }
  };

  const handleMakePick = async (playerId) => {
    try {
      await api.post(`/drafts/${draftId}/pick`, { player_id: playerId });
      await fetchDraft();
      await fetchPlayers();
    } catch (e) { console.error(e); }
  };

  const handlePauseTimer = async () => {
    try {
      const { data } = await api.post(`/drafts/${draftId}/pause`);
      setTimerPaused(data.paused);
    } catch (e) { console.error(e); }
  };

  const handleSendChat = async () => {
    if (!chatInput.trim()) return;
    try {
      await api.post(`/drafts/${draftId}/chat`, { text: chatInput.trim() });
      setChatInput("");
      await fetchDraft();
    } catch (e) { console.error(e); }
  };

  const toggleShortlist = (playerId) => {
    setShortlist(prev => {
      const next = new Set(prev);
      if (next.has(playerId)) next.delete(playerId);
      else next.add(playerId);
      return next;
    });
  };

  const toggleQueue = (playerId) => {
    setQueue(prev => prev.includes(playerId) ? prev.filter(id => id !== playerId) : [...prev, playerId]);
  };

  // Derived
  const teamAbbrs = draft?.team_abbrs || [];
  const totalTeams = teamAbbrs.length;
  const currentPick = draft?.current_pick || 1;
  const totalRounds = draft?.total_rounds || 5;
  const picks = draft?.picks || [];
  const isActive = draft?.status === "active";
  const isStarted = draft?.draft_started;
  const isEarlyStart = draft?.early_start;

  const getTeamForPick = (overall) => {
    if (!totalTeams) return "";
    const round = Math.ceil(overall / totalTeams);
    const pickInRound = (overall - 1) % totalTeams;
    const order = draft?.snake_draft && round % 2 === 0 ? [...teamAbbrs].reverse() : teamAbbrs;
    return order[pickInRound] || "";
  };

  const onTheClockTeam = getTeamForPick(currentPick);
  const currentRound = totalTeams ? Math.ceil(currentPick / totalTeams) : 1;
  const currentPickInRound = totalTeams ? ((currentPick - 1) % totalTeams) + 1 : 1;

  const filteredPlayers = players.filter(p => !p.drafted);
  const shortlistedPlayers = players.filter(p => shortlist.has(p.id) && !p.drafted);
  const queuedPlayers = queue.map(id => players.find(p => p.id === id)).filter(Boolean);

  // Build pick grid
  const allPicks = useMemo(() => {
    const grid = [];
    const pickMap = {};
    picks.forEach(p => { pickMap[p.overall] = p; });

    for (let r = 1; r <= totalRounds; r++) {
      const order = draft?.snake_draft && r % 2 === 0 ? [...teamAbbrs].reverse() : teamAbbrs;
      const roundPicks = order.map((team, idx) => {
        const overall = (r - 1) * totalTeams + idx + 1;
        return pickMap[overall] || { round: r, pick_in_round: idx + 1, overall, team, player: null };
      });
      grid.push(roundPicks);
    }
    return grid;
  }, [picks, totalRounds, teamAbbrs, totalTeams, draft?.snake_draft]);

  if (loading) {
    return (
      <AppLayout>
        <div className="flex items-center justify-center h-[60vh]">
          <div className="text-[#A1A1AA]">Loading draft room...</div>
        </div>
      </AppLayout>
    );
  }

  if (!draft) {
    return (
      <AppLayout>
        <div className="text-center py-20">
          <LayoutGrid className="h-16 w-16 text-[#52525B] mx-auto mb-4" />
          <h2 className="text-xl text-white mb-2">Draft not found</h2>
          <p className="text-[#A1A1AA]">This draft may not exist or has been removed.</p>
        </div>
      </AppLayout>
    );
  }

  return (
    <AppLayout>
      <div className="space-y-4" data-testid="draft-room-page">
        {/* Header */}
        <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-white flex items-center gap-2">
              <LayoutGrid className="h-6 w-6 text-[#00D2FF]" />
              Draft Room
            </h1>
            <p className="text-sm text-[#A1A1AA]">{draft.league_name || "League"} — {draft.draft_type} Draft</p>
          </div>

          {/* Timer Card */}
          <Card className="border-white/10 bg-[#141414] min-w-[320px]">
            <CardContent className="p-4 space-y-3">
              {!isStarted ? (
                <>
                  <p className="text-sm text-[#A1A1AA] flex items-center gap-2"><Clock className="h-4 w-4" /> Draft not started</p>
                  <Button size="sm" className="w-full bg-[#00D2FF] text-black hover:bg-[#33DBFF]" onClick={() => handleStartDraft(true)} data-testid="start-draft-early">
                    <Play className="h-3.5 w-3.5 mr-1" /> Start Draft (No Clock)
                  </Button>
                  <Button size="sm" variant="outline" className="w-full border-white/10 text-white" onClick={() => handleStartDraft(false)} data-testid="start-draft-timer">
                    <Timer className="h-3.5 w-3.5 mr-1" /> Start Draft (With Timer)
                  </Button>
                </>
              ) : draft.status === "completed" ? (
                <div className="text-center py-4">
                  <p className="text-lg font-bold text-[#34C759]">Draft Complete!</p>
                  <p className="text-sm text-[#A1A1AA]">All {picks.length} picks have been made</p>
                </div>
              ) : (
                <>
                  <div className="flex items-center gap-2">
                    <div className="h-2 w-2 rounded-full bg-[#34C759] animate-pulse" />
                    <span className="text-sm font-semibold text-white">Draft Live</span>
                    {isEarlyStart && <Badge variant="outline" className="text-[10px] text-amber-400 border-amber-400/30"><AlertCircle className="h-3 w-3 mr-1" />No Clock</Badge>}
                  </div>
                  <div className="bg-[#1A1A1A] rounded-lg p-3 text-center space-y-1">
                    <p className="text-[10px] uppercase tracking-wider text-[#A1A1AA]">On the Clock</p>
                    <div className="flex items-center justify-center gap-2">
                      {(() => {
                        const t = teamByAbbr(teams, onTheClockTeam);
                        return (
                          <TeamLogo
                            logo={t?.logo_url}
                            name={t?.name || onTheClockTeam}
                            abbr={onTheClockTeam}
                            size="sm"
                          />
                        );
                      })()}
                      <p className="text-lg font-bold text-white" data-testid="on-the-clock">
                        {teamByAbbr(teams, onTheClockTeam)?.name || onTheClockTeam}
                      </p>
                    </div>
                    <p className="text-xs text-[#A1A1AA]">Round {currentRound}, Pick {currentPickInRound} (#{currentPick} overall)</p>
                  </div>
                  {!isEarlyStart && (
                    <div className="space-y-1.5">
                      <div className="flex items-center justify-between text-xs">
                        <span className="text-[#A1A1AA] flex items-center gap-1"><Timer className="h-3 w-3" />Pick Timer</span>
                        <span className={cn("font-mono font-bold text-lg", timerPaused ? "text-[#A1A1AA]" : pickTimeLeft <= 15 ? "text-[#FF3B30]" : "text-[#00D2FF]")}>
                          {formatPickTimer(pickTimeLeft)}
                        </span>
                      </div>
                      <Progress value={(pickTimeLeft / (draft.time_per_pick || 120)) * 100} className="h-1.5" />
                      <Button variant={timerPaused ? "default" : "outline"} size="sm" className="w-full mt-1" onClick={handlePauseTimer} data-testid="pause-timer">
                        {timerPaused ? <><Play className="h-3.5 w-3.5 mr-1" />Resume</> : <><Pause className="h-3.5 w-3.5 mr-1" />Pause</>}
                      </Button>
                    </div>
                  )}
                </>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Draft Board */}
        <Card className="border-white/10">
          <CardHeader className="pb-2"><CardTitle className="text-base text-white">Draft Board</CardTitle></CardHeader>
          <CardContent className="p-0">
            <ScrollArea className="w-full">
              <div className="min-w-[700px] p-4 pt-0">
                <div className="grid gap-1 mb-1 sticky top-0 bg-[#141414] z-10 pt-2" style={{ gridTemplateColumns: `48px repeat(${totalTeams}, minmax(72px, 1fr))` }}>
                  <div className="p-1.5 text-[10px] font-semibold text-[#A1A1AA] uppercase">Rd</div>
                  {teamAbbrs.map(abbr => {
                    const t = teamByAbbr(teams, abbr);
                    const ownerOnline = !!(t?.owner_id && onlineUserIds?.has(String(t.owner_id)));
                    const isOnClock = abbr === onTheClockTeam && isActive;
                    return (
                      <div
                        key={abbr}
                        data-testid={`draft-team-header-${abbr}`}
                        data-online={ownerOnline ? "true" : "false"}
                        className={cn(
                          "p-1.5 text-[10px] font-semibold text-center uppercase truncate rounded border-2",
                          isOnClock
                            ? "bg-[#FFD700]/15 text-[#FFD700]"
                            : "bg-[#1A1A1A] text-[#A1A1AA] border-transparent",
                          // Iter 140 — green outline overlay when owner is online + in room
                          ownerOnline ? "border-[#34C759]/80 shadow-[0_0_0_1px_rgba(52,199,89,0.35)]" : "",
                        )}
                      >
                        {ownerOnline && (
                          <span
                            className="inline-block h-1.5 w-1.5 rounded-full bg-[#34C759] mr-1 align-middle"
                            data-testid={`draft-team-online-dot-${abbr}`}
                          />
                        )}
                        {abbr}
                      </div>
                    );
                  })}
                </div>
                {allPicks.map((roundPicks, rIdx) => (
                  <div key={rIdx + 1} className="grid gap-1 mb-1" style={{ gridTemplateColumns: `48px repeat(${totalTeams}, minmax(72px, 1fr))` }}>
                    <div className="p-1.5 flex items-center justify-center text-[10px] font-bold text-[#A1A1AA] bg-[#1A1A1A]/30 rounded">{rIdx + 1}</div>
                    {roundPicks.map(pick => {
                      const isCurrent = pick.overall === currentPick && isActive;
                      return (
                        <div key={`${rIdx}-${pick.team}`} className={cn("p-1.5 rounded border text-center min-h-[52px] flex flex-col items-center justify-center gap-0.5 transition-all",
                          isCurrent ? "bg-[#00D2FF]/10 border-[#00D2FF]/50 ring-1 ring-[#00D2FF]/30"
                          : pick.player ? "bg-[#1A1A1A]/60 border-white/10" : "bg-[#0A0A0A]/50 border-white/5"
                        )}>
                          <span className="text-[9px] text-[#A1A1AA]">#{pick.overall}</span>
                          {pick.player ? (
                            <>
                              <span className="text-[10px] font-medium text-white truncate w-full leading-tight">
                                {pick.player.name?.split(" ").map((n, i) => i === 0 ? n[0] + "." : n).join(" ")}
                              </span>
                              <Badge className={cn("text-[9px] px-1 py-0 h-3.5 border", positionColors[pick.player.position] || "bg-[#1A1A1A]")}>
                                {pick.player.position}
                              </Badge>
                            </>
                          ) : (
                            <span className="text-[10px] text-[#52525B]">—</span>
                          )}
                        </div>
                      );
                    })}
                  </div>
                ))}
              </div>
            </ScrollArea>
          </CardContent>
        </Card>

        {/* Bottom: Queue | Player Search | Chat */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
          {/* Queue */}
          <div className="lg:col-span-2">
            <Card className="border-white/10 h-full">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm flex items-center gap-2 text-white"><ListOrdered className="h-4 w-4 text-[#00D2FF]" />My Queue</CardTitle>
              </CardHeader>
              <CardContent className="p-2">
                <ScrollArea className="h-[400px]">
                  {queuedPlayers.length === 0 ? (
                    <div className="text-center py-8"><ListOrdered className="h-6 w-6 text-[#52525B] mx-auto" /><p className="text-xs text-[#A1A1AA] mt-2">Queue is empty</p></div>
                  ) : queuedPlayers.map((player, idx) => (
                    <div key={player.id} className="flex items-center gap-1.5 p-1.5 rounded-md bg-[#1A1A1A]/30 mb-1 group">
                      <span className="text-[10px] font-mono text-[#A1A1AA] w-4 text-right">{idx + 1}.</span>
                      <Badge className={cn("text-[9px] px-1 py-0 h-3.5 border", positionColors[player.position])}>{player.position}</Badge>
                      <span className="text-xs font-medium text-white truncate flex-1">{player.name}</span>
                      {isActive && (
                        <Button variant="ghost" size="icon" className="h-5 w-5 text-[#00D2FF] opacity-0 group-hover:opacity-100" onClick={() => handleMakePick(player.id)}>
                          <Play className="h-3 w-3" />
                        </Button>
                      )}
                    </div>
                  ))}
                </ScrollArea>
              </CardContent>
            </Card>
          </div>

          {/* Player Search */}
          <div className="lg:col-span-5">
            <Tabs defaultValue="eligible" className="w-full">
              <TabsList className="w-full grid grid-cols-2">
                <TabsTrigger value="eligible">Eligible Players</TabsTrigger>
                <TabsTrigger value="shortlist"><Star className="h-3.5 w-3.5 mr-1" />Shortlist ({shortlistedPlayers.length})</TabsTrigger>
              </TabsList>
              <TabsContent value="eligible" className="mt-3 space-y-3">
                <div className="flex gap-2">
                  <div className="relative flex-1">
                    <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-[#A1A1AA]" />
                    <Input placeholder="Search players..." className="pl-8 h-8 text-sm bg-[#1A1A1A] border-white/10 text-white" value={searchQuery} onChange={e => setSearchQuery(e.target.value)} data-testid="draft-search" />
                  </div>
                  <Select value={positionFilter} onValueChange={setPositionFilter}>
                    <SelectTrigger className="w-[100px] h-8 text-xs bg-[#1A1A1A] border-white/10 text-white"><SelectValue /></SelectTrigger>
                    <SelectContent className="bg-[#141414] border-white/10">
                      {[{v:"all",l:"All"},{v:"C",l:"C"},{v:"LW",l:"LW"},{v:"RW",l:"RW"},{v:"D",l:"D"},{v:"G",l:"G"}].map(p => (
                        <SelectItem key={p.v} value={p.v} className="text-white">{p.l}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <Badge variant="secondary" className="text-[10px]">{filteredPlayers.length} players available</Badge>
                <ScrollArea className="h-[400px]">
                  <div className="space-y-1">
                    {filteredPlayers.map(player => (
                      <div key={player.id} className="flex items-center gap-2 p-2 rounded-md hover:bg-[#1A1A1A]/40 transition-colors group">
                        <span className="text-[10px] font-mono text-[#A1A1AA] w-5 text-right">{player.ranking}</span>
                        <Badge className={cn("text-[9px] px-1 py-0 h-3.5 border", positionColors[player.position])}>{player.position}</Badge>
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium text-white truncate">{player.name}</p>
                          <p className="text-[10px] text-[#A1A1AA]">{player.nhlTeam} · {player.gp}GP {player.g}G {player.a}A {player.pts}P</p>
                        </div>
                        <Button variant="ghost" size="icon" className={cn("h-7 w-7", shortlist.has(player.id) ? "text-[#FF3B30]" : "text-[#52525B] hover:text-[#FF3B30]")} onClick={() => toggleShortlist(player.id)}>
                          <Star className={cn("h-3.5 w-3.5", shortlist.has(player.id) && "fill-current")} />
                        </Button>
                        <Button variant="ghost" size="icon" className={cn("h-7 w-7", queue.includes(player.id) ? "text-[#00D2FF]" : "text-[#52525B] hover:text-[#00D2FF]")} onClick={() => toggleQueue(player.id)}>
                          <ListOrdered className="h-3.5 w-3.5" />
                        </Button>
                        {isActive && (
                          <Button size="sm" className="h-7 bg-[#00D2FF] text-black text-xs opacity-0 group-hover:opacity-100" onClick={() => handleMakePick(player.id)} data-testid={`pick-${player.id}`}>
                            Pick
                          </Button>
                        )}
                      </div>
                    ))}
                  </div>
                </ScrollArea>
              </TabsContent>
              <TabsContent value="shortlist" className="mt-3">
                <ScrollArea className="h-[450px]">
                  {shortlistedPlayers.length === 0 ? (
                    <div className="text-center py-12"><Star className="h-8 w-8 text-[#52525B] mx-auto" /><p className="text-sm text-[#A1A1AA] mt-2">No players shortlisted</p></div>
                  ) : shortlistedPlayers.map((player, idx) => (
                    <div key={player.id} className="flex items-center gap-2 p-2 rounded-md bg-[#1A1A1A]/30 mb-1">
                      <span className="text-[10px] text-[#A1A1AA] w-4">{idx + 1}.</span>
                      <Badge className={cn("text-[9px] px-1 py-0 h-3.5 border", positionColors[player.position])}>{player.position}</Badge>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-white truncate">{player.name}</p>
                        <p className="text-[10px] text-[#A1A1AA]">#{player.ranking} · {player.nhlTeam} · {player.pts}P</p>
                      </div>
                    </div>
                  ))}
                </ScrollArea>
              </TabsContent>
            </Tabs>
          </div>

          {/* Chat */}
          <div className="lg:col-span-5 space-y-4">
            <Card className="border-white/10">
              <CardHeader className="pb-2"><CardTitle className="text-sm flex items-center gap-2 text-white"><MessageSquare className="h-4 w-4 text-[#00D2FF]" />Draft Chat</CardTitle></CardHeader>
              <CardContent className="p-2 space-y-2">
                <ScrollArea className="h-[200px]">
                  <div className="space-y-2 p-1">
                    {chatMessages.map(msg => (
                      <div key={msg.id} className={cn("text-xs rounded-md p-2", msg.type === "pick" ? "bg-[#00D2FF]/10 border border-[#00D2FF]/20" : "bg-[#1A1A1A]/40")}>
                        <div className="flex items-center justify-between mb-0.5">
                          <span className={cn("font-semibold text-[11px]", msg.type === "pick" ? "text-[#00D2FF]" : "text-white")}>{msg.sender}</span>
                          <span className="text-[9px] text-[#A1A1AA]">{new Date(msg.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</span>
                        </div>
                        <p className="text-[#A1A1AA]">{msg.text}</p>
                      </div>
                    ))}
                  </div>
                </ScrollArea>
                <div className="flex gap-2">
                  <Input placeholder="Type a message..." className="h-8 text-sm bg-[#1A1A1A] border-white/10 text-white flex-1" value={chatInput} onChange={e => setChatInput(e.target.value)} onKeyDown={e => e.key === "Enter" && handleSendChat()} data-testid="draft-chat-input" />
                  <Button size="icon" className="h-8 w-8 bg-[#00D2FF] text-black" onClick={handleSendChat} data-testid="draft-chat-send"><Send className="h-3.5 w-3.5" /></Button>
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    </AppLayout>
  );
}
